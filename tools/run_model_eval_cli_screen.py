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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.langchain import pr_verifier
from tools.plan_model_eval import ROOT, build_plan
from tools.run_model_eval_pilot import fetch_pr

MAX_CASES = 8
MAX_MODELS = 4
DEFAULT_MODELS = "gpt-5.6-terra,gpt-6-luna,gpt-6-sol"


@dataclass(frozen=True)
class CliResult:
    payload: dict[str, Any] | None
    input_tokens: int
    output_tokens: int
    latency_ms: float
    error: str | None = None
    stop_screen: bool = False


def select_cases(cases: list[dict[str, Any]], limit: int = MAX_CASES) -> list[dict[str, Any]]:
    """Cover every category, then balance PASS and NON_PASS examples."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        groups[str(case["category"])].append(case)
    if len(groups) > limit:
        raise ValueError("more categories than the bounded screen can cover")
    selected: list[dict[str, Any]] = []
    for category in sorted(groups):
        selected.append(groups[category].pop(0))
    while len(selected) < limit and any(groups.values()):
        non_pass = sum(case["expected_verdict"] == "NON_PASS" for case in selected)
        preferred = "NON_PASS" if non_pass < limit // 2 else "PASS"
        eligible = [
            category
            for category in sorted(groups)
            if any(case["expected_verdict"] == preferred for case in groups[category])
        ]
        if not eligible:
            eligible = [category for category in sorted(groups) if groups[category]]
        category = min(eligible, key=lambda key: sum(c["category"] == key for c in selected))
        index = next(
            (i for i, case in enumerate(groups[category]) if case["expected_verdict"] == preferred),
            0,
        )
        selected.append(groups[category].pop(index))
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


def has_tool_events(stream: str) -> bool:
    """Reject any CLI tool activity in an untrusted PR evaluation."""
    for line in stream.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        event_type = str(event.get("type", ""))
        if "tool" in event_type or "command" in event_type:
            return True
        if event_type.startswith("item."):
            item = event.get("item")
            if not isinstance(item, dict) or item.get("type") not in {"agent_message", "reasoning"}:
                return True
    return False


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
        [codex, "debug", "models", "--bundled"],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    payload = json.loads(response.stdout)
    return {
        str(model["slug"])
        for model in payload["models"]
        if model.get("visibility") == "list" and model.get("supported_in_api") is True
    }


def invoke_cli(codex: str, model: str, prompt: str) -> CliResult:
    with tempfile.TemporaryDirectory(prefix="maint78-cli-") as scratch:
        final = Path(scratch) / "final.json"
        started = time.perf_counter()
        command = [
            codex,
            "exec",
            "--json",
            "--ignore-user-config",
            "--ignore-rules",
            "--strict-config",
            "--disable",
            "shell_tool",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--ephemeral",
            "--model",
            model,
            "--output-last-message",
            str(final),
            "-",
        ]
        child_env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"GH_TOKEN", "GITHUB_TOKEN", "CODEX_AUTH_JSON", "OPENAI_API_KEY"}
            and not key.endswith(("_TOKEN", "_KEY"))
        }
        try:
            response = subprocess.run(
                command,
                input=prompt,
                capture_output=True,
                text=True,
                cwd=scratch,
                timeout=240,
                check=False,
                env=child_env,
            )
        except subprocess.TimeoutExpired as exc:
            stream = exc.stdout or b""
            if isinstance(stream, bytes):
                stream = stream.decode("utf-8", errors="replace")
            input_tokens, output_tokens = token_usage(stream)
            return CliResult(
                None,
                input_tokens,
                output_tokens,
                round((time.perf_counter() - started) * 1000, 3),
                "Codex CLI timed out",
                True,
            )
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        input_tokens, output_tokens = token_usage(response.stdout)
        if has_tool_events(response.stdout):
            return CliResult(
                None,
                input_tokens,
                output_tokens,
                latency_ms,
                "Codex CLI emitted a tool event; result excluded",
                True,
            )
        if response.returncode:
            return CliResult(
                None,
                input_tokens,
                output_tokens,
                latency_ms,
                f"Codex CLI exited {response.returncode}",
                True,
            )
        if not final.is_file():
            return CliResult(
                None,
                input_tokens,
                output_tokens,
                latency_ms,
                "Codex CLI produced no final message",
                True,
            )
        try:
            result = pr_verifier.EvaluationPayload.model_validate_json(final.read_text())
        except ValueError:
            return CliResult(
                None, input_tokens, output_tokens, latency_ms, "Invalid verifier JSON", False
            )
        return CliResult(result.model_dump(), input_tokens, output_tokens, latency_ms)


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
    if not plan["screen_ready"]:
        raise ValueError(f"candidate screen is not ready: {plan['screen_blockers']}")
    if plan["incumbent"] not in models:
        raise ValueError(f"include the incumbent {plan['incumbent']} for a paired comparison")
    prices = {
        model["model_id"]: model["pricing"]
        for model in registry["models"]
        if model.get("provider") == "openai"
        and model.get("lifecycle") == "current"
        and not model.get("blocked", False)
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
                outcome = invoke_cli(codex, model, prompt)
                verdict = (
                    "PASS"
                    if outcome.payload and outcome.payload["verdict"] == "PASS"
                    else "NON_PASS"
                )
                row = {
                    "case_id": case["case_id"],
                    "category": case["category"],
                    "expected_verdict": case["expected_verdict"],
                    "actual_verdict": verdict,
                    "schema_valid": outcome.payload is not None,
                    "model_id": model,
                    "input_tokens": outcome.input_tokens,
                    "output_tokens": outcome.output_tokens,
                    "latency_ms": outcome.latency_ms,
                    "modeled_api_cost_usd": api_list_price_estimate(
                        outcome.input_tokens, outcome.output_tokens, prices[model]
                    ),
                }
                if outcome.error:
                    row["error"] = outcome.error
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
                outcome = None
            rows.append(row)
            # A schema error is quality evidence and preserves its token cost.
            # Missing usage or tool activity invalidates the screen itself.
            if outcome is None or outcome.stop_screen:
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
                "modeled_cost_per_accepted_review_usd": (
                    round(cost / accepted, 6) if accepted and len(subset) == len(cases) else None
                ),
            }
        )
    incumbent = next((row for row in by_model if row["model_id"] == plan["incumbent"]), None)
    complete = not stopped_early and all(row["rows"] == len(cases) for row in by_model)
    eligible = (
        [
            row
            for row in by_model
            if row["model_id"] != plan["incumbent"]
            and row["false_pass"] == 0
            and row["schema_errors"] == 0
            and row["accepted"] >= incumbent["accepted"]
            and row["modeled_cost_per_accepted_review_usd"] is not None
            and (
                incumbent["false_pass"] > 0
                or incumbent["modeled_cost_per_accepted_review_usd"] is None
                or row["modeled_cost_per_accepted_review_usd"]
                < incumbent["modeled_cost_per_accepted_review_usd"]
            )
        ]
        if complete and incumbent is not None
        else []
    )
    shortlisted = min(
        eligible,
        key=lambda row: (row["modeled_cost_per_accepted_review_usd"], -row["accepted"]),
        default=None,
    )
    return {
        "schema": "workflows-verifier-cli-screen/v1",
        "input_fingerprint": plan["input_fingerprint"],
        "scope": "exploratory Codex CLI screen; not production API evidence",
        "api_key_calls": 0,
        "approval_ready": False,
        "screen_decision": (
            "advance_to_api_confirmation"
            if shortlisted
            else "inconclusive" if not complete else "retain_incumbent_on_screen"
        ),
        "provisional_shortlist_model_id": shortlisted["model_id"] if shortlisted else None,
        "decision_rule": "On the same eight cases: zero observed false PASS and schema errors, "
        "at least incumbent accuracy, then lower modeled cost per accepted review "
        "(or replacement of an incumbent with an observed false PASS).",
        "stopped_early": stopped_early,
        "case_ids": [case["case_id"] for case in cases],
        "models": by_model,
        "rows": rows,
        "next_action": (
            "Run a capped paired production API confirmation against the incumbent. "
            "If it agrees, review a reversible provisional model change and monitor live outcomes."
            if shortlisted
            else "Keep the incumbent; inspect case-level errors and screen another priced candidate "
            "when the catalog or verifier workload changes."
        ),
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
    summary.insert(
        2,
        f"**Screen decision:** {payload['screen_decision']}; "
        f"shortlist: {payload['provisional_shortlist_model_id'] or 'none'}.",
    )
    if args.summary:
        with args.summary.open("a") as stream:
            stream.write("\n".join(summary))
    else:
        print("\n".join(summary))
    return int(payload["stopped_early"])


if __name__ == "__main__":
    raise SystemExit(main())
