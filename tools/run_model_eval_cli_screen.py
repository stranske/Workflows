#!/usr/bin/env python3
"""Bounded Codex subscription screen; makes no billable API-key model calls.

This is exploratory evidence. Codex CLI is a different harness from the production
LangChain verifier, so its modeled API cost cannot be treated as observed spend or
used for an approval-stage promotion.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from scripts.langchain import pr_verifier
from tools.plan_model_eval import ROOT, build_plan
from tools.run_model_eval_pilot import fetch_pr

MAX_CASES = 8
MAX_MODELS = 4
DEFAULT_MODELS = "gpt-5.6-terra,gpt-6-luna,gpt-6-sol,gpt-6-astra"


def select_cases(cases: list[dict[str, Any]], limit: int = MAX_CASES) -> list[dict[str, Any]]:
    """Cover every present category first, then round robin across categories."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        groups[str(case["category"])].append(case)
    if len(groups) > limit:
        raise ValueError("more categories than the bounded screen can cover")
    selected: list[dict[str, Any]] = []
    while len(selected) < limit and any(groups.values()):
        for category in sorted(groups):
            if groups[category] and len(selected) < limit:
                selected.append(groups[category].pop(0))
    return selected


def token_usage(stream: str) -> tuple[int, int]:
    """Sum per-turn usage and fail closed when the CLI omits telemetry."""
    input_tokens = output_tokens = 0
    seen = False
    for line in stream.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") != "turn.completed":
            continue
        usage = event.get("usage") or event.get("token_usage") or {}
        if not isinstance(usage, dict):
            continue
        input_tokens += int(usage.get("input_tokens") or 0)
        output_tokens += int(usage.get("output_tokens") or 0)
        seen = True
    if not seen or input_tokens <= 0 or output_tokens <= 0:
        raise ValueError("Codex CLI did not report turn token usage")
    return input_tokens, output_tokens


def api_list_price_estimate(
    input_tokens: int, output_tokens: int, pricing: dict[str, Any]
) -> float:
    """Conservative standard-rate estimate; no prompt-cache discount assumed."""
    return round(
        (
            input_tokens * float(pricing["input_per_million_tokens"])
            + output_tokens * float(pricing["output_per_million_tokens"])
        )
        / 1_000_000,
        6,
    )


def cli_model_ids(codex: str) -> set[str]:
    response = subprocess.run(
        [codex, "debug", "models"], capture_output=True, text=True, timeout=30, check=True
    )
    payload = json.loads(response.stdout)
    return {
        str(model["slug"])
        for model in payload["models"]
        if model.get("visibility") == "list" and model.get("supported_in_api") is True
    }


def invoke_cli(codex: str, model: str, prompt: str) -> tuple[dict[str, Any], int, int, float]:
    with tempfile.TemporaryDirectory(prefix="maint78-cli-") as scratch:
        final = Path(scratch) / "final.json"
        started = time.perf_counter()
        response = subprocess.run(
            [
                codex,
                "exec",
                "--json",
                "--ignore-user-config",
                "--strict-config",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--ephemeral",
                "--model",
                model,
                "--output-last-message",
                str(final),
                "-",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            cwd=scratch,
            timeout=240,
            check=False,
        )
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        if response.returncode:
            raise ValueError(f"Codex CLI exited {response.returncode}: {response.stderr[-500:]}")
        input_tokens, output_tokens = token_usage(response.stdout)
        if not final.is_file():
            raise ValueError("Codex CLI produced no final message")
        result = pr_verifier.EvaluationPayload.model_validate_json(final.read_text())
        return result.model_dump(), input_tokens, output_tokens, latency_ms


def run_screen(
    corpus: dict[str, Any],
    registry: dict[str, Any],
    policy: dict[str, Any],
    *,
    models: list[str],
    token: str,
    codex: str = "codex",
) -> dict[str, Any]:
    if not token:
        raise ValueError("GH_TOKEN is required to load the paired PR cases")
    if len(models) < 2 or len(models) > MAX_MODELS or len(set(models)) != len(models):
        raise ValueError(f"select 2 to {MAX_MODELS} distinct models")
    plan = build_plan(corpus, registry, policy)
    if plan["incumbent"] not in models:
        raise ValueError(f"include the incumbent {plan['incumbent']} for a paired comparison")
    prices = {
        model["model_id"]: model["pricing"]
        for model in registry["models"]
        if model.get("provider") == "openai"
        and isinstance(model.get("pricing"), dict)
        and all(
            key in model["pricing"]
            for key in ("input_per_million_tokens", "output_per_million_tokens")
        )
    }
    unknown = sorted(set(models) - set(prices))
    if unknown:
        raise ValueError(f"models lack verified registry prices: {unknown}")
    available = cli_model_ids(codex)
    unavailable = sorted(set(models) - available)
    if unavailable:
        raise ValueError(f"models unavailable to Codex CLI: {unavailable}")
    cases = select_cases(corpus["cases"])
    prepared = {case["case_id"]: fetch_pr(case["repo"], case["pr"], token) for case in cases}
    rows: list[dict[str, Any]] = []
    for model in models:
        for case in cases:
            context, diff = prepared[case["case_id"]]
            prompt = (
                "Evaluate this PR using the following verifier instructions. Do not use tools. "
                "Return only one JSON object with verdict, scores, confidence, concerns, and summary.\n\n"
                + pr_verifier._prepare_prompt(context, diff)
            )
            try:
                result, input_tokens, output_tokens, latency_ms = invoke_cli(codex, model, prompt)
                verdict = "PASS" if result["verdict"] == "PASS" else "NON_PASS"
                row = {
                    "case_id": case["case_id"],
                    "category": case["category"],
                    "expected_verdict": case["expected_verdict"],
                    "actual_verdict": verdict,
                    "schema_valid": True,
                    "model_id": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "latency_ms": latency_ms,
                    "modeled_api_cost_usd": api_list_price_estimate(
                        input_tokens, output_tokens, prices[model]
                    ),
                }
            except Exception as exc:
                row = {
                    "case_id": case["case_id"],
                    "category": case["category"],
                    "expected_verdict": case["expected_verdict"],
                    "actual_verdict": "NON_PASS",
                    "schema_valid": False,
                    "model_id": model,
                    "error": str(exc),
                }
            rows.append(row)
            # A missing usage record destroys the cost comparison. Stop after one
            # failed invocation instead of spending more subscription capacity.
            if not row["schema_valid"]:
                return report(plan, cases, models, rows, stopped_early=True)
    return report(plan, cases, models, rows, stopped_early=False)


def report(
    plan: dict[str, Any],
    cases: list[dict[str, Any]],
    models: list[str],
    rows: list[dict[str, Any]],
    *,
    stopped_early: bool,
) -> dict[str, Any]:
    by_model = []
    for model in models:
        subset = [row for row in rows if row["model_id"] == model]
        accepted = sum(
            row["schema_valid"] and row["actual_verdict"] == row["expected_verdict"]
            for row in subset
        )
        cost = sum(float(row.get("modeled_api_cost_usd", 0)) for row in subset)
        by_model.append(
            {
                "model_id": model,
                "rows": len(subset),
                "accepted": accepted,
                "false_pass": sum(
                    row["expected_verdict"] == "NON_PASS" and row["actual_verdict"] == "PASS"
                    for row in subset
                ),
                "schema_errors": sum(not row["schema_valid"] for row in subset),
                "modeled_api_cost_usd": round(cost, 6),
                "modeled_cost_per_accepted_review_usd": round(cost / accepted, 6)
                if accepted and len(subset) == len(cases)
                else None,
            }
        )
    return {
        "schema": "workflows-verifier-cli-screen/v1",
        "input_fingerprint": plan["input_fingerprint"],
        "scope": "exploratory Codex CLI screen; not production API evidence",
        "api_key_calls": 0,
        "approval_ready": False,
        "stopped_early": stopped_early,
        "case_ids": [case["case_id"] for case in cases],
        "models": by_model,
        "rows": rows,
        "next_action": "Grow to 75 adjudicated cases; confirm finalists in the production API with observed costs.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=ROOT / "config/model_eval_pilot.json")
    parser.add_argument("--registry", type=Path, default=ROOT / "config/model_registry.json")
    parser.add_argument("--policy", type=Path, default=ROOT / "config/model_selection_policy.json")
    parser.add_argument("--models", default=DEFAULT_MODELS)
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args(argv)
    payload = run_screen(
        json.loads(args.corpus.read_text()),
        json.loads(args.registry.read_text()),
        json.loads(args.policy.read_text()),
        models=[model.strip() for model in args.models.split(",") if model.strip()],
        token=os.environ.get("GH_TOKEN", ""),
        codex=args.codex,
    )
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    summary = [
        "## MAINT-78 bounded CLI screen",
        "",
        "Exploratory only. This used Codex subscription auth and made **zero API-key model calls**.",
        f"Cases: {len(payload['case_ids'])}; stopped early: {payload['stopped_early']}.",
        "Modeled API costs assume standard uncached rates; they are not observed API charges.",
        "",
        "| Model | Correct / rows | False PASS | Modeled API cost / accepted review |",
        "|---|---:|---:|---:|",
    ]
    for model in payload["models"]:
        value = model["modeled_cost_per_accepted_review_usd"]
        summary.append(
            f"| {model['model_id']} | {model['accepted']} / {model['rows']} | "
            f"{model['false_pass']} | {'unknown' if value is None else f'${value:.4f}'} |"
        )
    summary += ["", payload["next_action"], ""]
    if args.summary:
        with args.summary.open("a") as stream:
            stream.write("\n".join(summary))
    else:
        print("\n".join(summary))
    return int(payload["stopped_early"])


if __name__ == "__main__":
    raise SystemExit(main())
