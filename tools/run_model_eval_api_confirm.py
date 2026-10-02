#!/usr/bin/env python3
"""Small paired API confirmation after a Codex CLI screen.

Only a manual MAINT-78 dispatch calls this. It uses the verifier prompt and parser,
disables SDK retries and schema-repair calls, and reserves worst-case standard-rate
cost before each *pair*. The reported dollar amounts are estimates from measured
API tokens, not invoice charges or statistical approval evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import Any

from scripts.langchain import pr_verifier
from tools.model_eval_snapshots import screen_cases, verifier_prompt
from tools.plan_model_eval import ROOT, build_plan

MAX_OUTPUT_TOKENS = 4096


def _price(tokens_in: int, tokens_out: int, price: dict[str, Any]) -> float:
    rates = [
        float(price["input_per_million_tokens"]),
        float(price["output_per_million_tokens"]),
    ]
    if any(not math.isfinite(rate) or rate < 0 for rate in rates):
        raise ValueError("API confirmation requires finite, nonnegative registry prices")
    return (tokens_in * rates[0] + tokens_out * rates[1]) / 1_000_000


def _invoke_api(client: Any, model: dict[str, Any], prompt: str) -> tuple[str, int, int]:
    model_id = model["model_id"]
    if model["api"] == "responses":
        kwargs: dict[str, Any] = {}
        if model_id.startswith("gpt-6-astra"):
            kwargs["reasoning"] = {"effort": "high"}
        response = client.responses.create(
            model=model_id, input=prompt, max_output_tokens=MAX_OUTPUT_TOKENS, **kwargs
        )
        content = response.output_text
        usage = response.usage
        return content, int(usage.input_tokens), int(usage.output_tokens)
    if model["api"] == "chat":
        response = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=MAX_OUTPUT_TOKENS,
            temperature=0.1,
        )
        content = response.choices[0].message.content or ""
        usage = response.usage
        return content, int(usage.prompt_tokens), int(usage.completion_tokens)
    raise ValueError(f"unsupported API route for {model_id}")


def confirm(
    corpus: dict[str, Any],
    registry: dict[str, Any],
    policy: dict[str, Any],
    screen: dict[str, Any],
    *,
    github_token: str,
    client: Any,
    api_only_candidate: str | None = None,
    cli_catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan = build_plan(corpus, registry, policy)
    if not plan["input_alignment_ready"]:
        raise ValueError(
            "provisional API confirmation requires adjudicated production-context inputs"
        )
    stage = policy["profiles"]["verifier-balanced"]["provisional_stage"]
    if (
        screen.get("schema") != "workflows-verifier-cli-screen/v1"
        or screen.get("stopped_early")
        or screen.get("input_fingerprint") != plan["input_fingerprint"]
        or screen.get("screen_harness_fingerprint") != plan["screen_harness_fingerprint"]
    ):
        raise ValueError("a complete, current CLI screen is required")
    candidate = api_only_candidate or screen.get("provisional_shortlist_model_id")
    incumbent = plan["incumbent"]
    if not isinstance(candidate, str) or candidate == incumbent:
        raise ValueError("a distinct candidate is required")
    if api_only_candidate:
        if cli_catalog is None:
            raise ValueError("API-only comparison requires the pinned CLI catalog")
        cli_models = {
            model.get("slug")
            for model in cli_catalog.get("models", [])
            if model.get("visibility") == "list" and model.get("supported_in_api") is True
        }
        if candidate in cli_models:
            raise ValueError("API-only exception is limited to models absent from the pinned CLI")
    elif screen.get("screen_decision") != "advance_to_api_confirmation":
        raise ValueError("a complete, current CLI screen shortlist is required")
    if len(screen.get("case_ids", [])) != int(stage["screen_cases"]):
        raise ValueError("screen must contain exactly the configured paired cases")
    if len(screen["case_ids"]) > int(stage["maximum_api_confirmation_cases"]):
        raise ValueError("screen exceeds the API confirmation case cap")
    if len({incumbent, candidate}) != int(stage["maximum_api_confirmation_models"]):
        raise ValueError("API confirmation must compare exactly two models")
    catalog = {
        row["model_id"]: row
        for row in registry["models"]
        if row.get("provider") == "openai"
        and row.get("lifecycle") == "current"
        and not row.get("blocked", False)
        and isinstance(row.get("pricing"), dict)
    }
    if incumbent not in catalog or candidate not in catalog:
        raise ValueError("both models need current registry prices")
    selected, snapshot_blockers = screen_cases(corpus, stage)
    if snapshot_blockers:
        raise ValueError(f"production-context inputs are invalid: {snapshot_blockers}")
    case_map = {case["case_id"]: case for case in selected}
    case_ids = screen["case_ids"]
    if (
        not case_ids
        or len(case_ids) != len(set(case_ids))
        or any(case_id not in case_map for case_id in case_ids)
    ):
        raise ValueError("screen case IDs do not identify unique corpus cases")
    if sum(case_map[case_id]["expected_verdict"] == "NON_PASS" for case_id in case_ids) < int(
        stage["minimum_non_pass_cases"]
    ):
        raise ValueError("screen does not cover the required NON_PASS cases")
    prompt_hashes = screen.get("prompt_sha256_by_case")
    if not isinstance(prompt_hashes, dict) or set(prompt_hashes) != set(case_ids):
        raise ValueError("screen is missing case-level verifier prompt hashes")
    # Validate immutable captured inputs before making the first billable model call.
    prompts: dict[str, str] = {}
    for case_id in case_ids:
        case = case_map[case_id]
        prompt = verifier_prompt(case["production_snapshot"])
        if hashlib.sha256(prompt.encode("utf-8")).hexdigest() != prompt_hashes[case_id]:
            raise ValueError(f"verifier prompt changed after screen for {case_id}")
        prompts[case_id] = prompt

    limit = float(stage["maximum_api_confirmation_cost_usd"])
    spent_upper = 0.0
    rows: list[dict[str, Any]] = []
    for case_id in case_ids:
        case = case_map[case_id]
        prompt = prompts[case_id]
        # Byte length is a conservative upper bound for text BPE tokens. Reserve
        # the full output cap for both models before starting a pair.
        input_bound = len(prompt.encode("utf-8")) + 256  # chat framing and tokenizer margin
        pair_bound = sum(
            _price(input_bound, MAX_OUTPUT_TOKENS, catalog[model]["pricing"])
            for model in (incumbent, candidate)
        )
        if spent_upper + pair_bound > limit:
            break
        spent_upper += pair_bound
        for model_id in (incumbent, candidate):
            started = time.perf_counter()
            try:
                content, input_tokens, output_tokens = _invoke_api(
                    client, catalog[model_id], prompt
                )
                parsed = pr_verifier._parse_llm_response(content, "openai")
                valid = parsed.error is None
                actual = "PASS" if parsed.verdict == "PASS" else "NON_PASS"
                error = parsed.error
            except Exception as exc:
                # Stop after a request error: its provider-side billable usage is
                # unknown, so no further call can be justified by this cap.
                rows.append({"case_id": case_id, "model_id": model_id, "error": str(exc)})
                return _report(
                    plan,
                    case_ids,
                    rows,
                    limit,
                    spent_upper,
                    incomplete=True,
                    comparison_path="api_only" if api_only_candidate else "cli_shortlist",
                    thresholds=plan["provisional_thresholds"],
                )
            rows.append(
                {
                    "case_id": case_id,
                    "model_id": model_id,
                    "category": case["category"],
                    "expected_verdict": case["expected_verdict"],
                    "actual_verdict": actual,
                    "schema_valid": valid,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "modeled_api_cost_usd": round(
                        _price(input_tokens, output_tokens, catalog[model_id]["pricing"]), 6
                    ),
                    "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                    "error": error,
                }
            )
    return _report(
        plan,
        case_ids,
        rows,
        limit,
        spent_upper,
        incomplete=len(rows) != 2 * len(case_ids),
        comparison_path="api_only" if api_only_candidate else "cli_shortlist",
        thresholds=plan["provisional_thresholds"],
    )


def _report(
    plan: dict[str, Any],
    case_ids: list[str],
    rows: list[dict[str, Any]],
    limit: float,
    reserved_cost: float,
    *,
    incomplete: bool,
    comparison_path: str,
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    incumbent = plan["incumbent"]
    models = sorted({row["model_id"] for row in rows})
    scores = {}
    for model in models:
        subset = [row for row in rows if row["model_id"] == model]
        correct = sum(
            row.get("schema_valid") is True
            and row.get("actual_verdict") == row.get("expected_verdict")
            for row in subset
        )
        cost = sum(float(row.get("modeled_api_cost_usd", 0)) for row in subset)
        expected_pass = sum(row.get("expected_verdict") == "PASS" for row in subset)
        expected_non_pass = sum(row.get("expected_verdict") == "NON_PASS" for row in subset)
        scores[model] = {
            "correct": correct,
            "pass_correct": sum(
                row.get("schema_valid") is True
                and row.get("expected_verdict") == "PASS"
                and row.get("actual_verdict") == "PASS"
                for row in subset
            ),
            "expected_pass": expected_pass,
            "non_pass_correct": sum(
                row.get("schema_valid") is True
                and row.get("expected_verdict") == "NON_PASS"
                and row.get("actual_verdict") == "NON_PASS"
                for row in subset
            ),
            "expected_non_pass": expected_non_pass,
            "false_pass": sum(
                row.get("expected_verdict") == "NON_PASS" and row.get("actual_verdict") == "PASS"
                for row in subset
            ),
            "schema_errors": sum(row.get("schema_valid") is not True for row in subset),
            "modeled_cost_per_accepted_review_usd": round(cost / correct, 6) if correct else None,
        }
    challenger = next((model for model in models if model != incumbent), None)
    baseline = scores.get(incumbent)
    alternative = scores.get(challenger) if challenger else None
    max_false_passes = int(thresholds["maximum_false_passes"])
    max_schema_errors = int(thresholds["maximum_schema_errors"])
    min_accuracy_delta = int(thresholds["minimum_accuracy_delta_vs_incumbent"])
    minimum_pass_recall = float(thresholds["minimum_pass_recall"])
    ready = (
        not incomplete
        and alternative is not None
        and baseline is not None
        and alternative["false_pass"] <= max_false_passes
        and alternative["schema_errors"] <= max_schema_errors
        and alternative["correct"] - baseline["correct"] >= min_accuracy_delta
        and alternative["expected_pass"] > 0
        and alternative["pass_correct"] / alternative["expected_pass"] >= minimum_pass_recall
        and alternative["pass_correct"] >= baseline["pass_correct"]
        and alternative["non_pass_correct"] >= baseline["non_pass_correct"]
        and alternative["modeled_cost_per_accepted_review_usd"] is not None
        and (
            baseline["false_pass"] > alternative["false_pass"]
            or baseline["modeled_cost_per_accepted_review_usd"] is None
            or alternative["modeled_cost_per_accepted_review_usd"]
            < baseline["modeled_cost_per_accepted_review_usd"]
        )
    )
    return {
        "schema": "workflows-verifier-api-confirmation/v1",
        "input_fingerprint": plan["input_fingerprint"],
        "screen_harness_fingerprint": plan["screen_harness_fingerprint"],
        "comparison_path": comparison_path,
        "case_ids": case_ids,
        "case_input_kinds": plan["screen_case_kinds"],
        "rows": rows,
        "models": scores,
        "api_call_cap": 2 * len(case_ids),
        "api_calls_made": len(rows),
        "maximum_api_cost_usd": limit,
        "reserved_standard_rate_upper_bound_usd": round(reserved_cost, 6),
        "complete": not incomplete,
        "decision": "provisional_change_for_human_review" if ready else "retain_or_inconclusive",
        "provisional_model_id": challenger if ready else None,
        "statistical_approval": False,
        "next_action": (
            "Review a reversible provisional registry change; monitor live verifier outcomes "
            "and revert on false PASS or material regression."
            if ready
            else "Retain the incumbent and inspect the paired case errors."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=ROOT / "config/model_eval_pilot.json")
    parser.add_argument("--registry", type=Path, default=ROOT / "config/model_registry.json")
    parser.add_argument("--policy", type=Path, default=ROOT / "config/model_selection_policy.json")
    parser.add_argument("--screen", type=Path, required=True)
    parser.add_argument("--cli-catalog", type=Path)
    parser.add_argument("--api-only-candidate", default="")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args(argv)
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required for the manual API confirmation")
    from openai import OpenAI

    payload = confirm(
        json.loads(args.corpus.read_text()),
        json.loads(args.registry.read_text()),
        json.loads(args.policy.read_text()),
        json.loads(args.screen.read_text()),
        github_token=os.environ.get("GH_TOKEN", ""),
        client=OpenAI(max_retries=0, timeout=120),
        api_only_candidate=args.api_only_candidate or None,
        cli_catalog=json.loads(args.cli_catalog.read_text()) if args.cli_catalog else None,
    )
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    summary = (
        "## MAINT-78 bounded API confirmation\n\n"
        f"**Decision:** {payload['decision']}\n\n"
        f"**Calls:** {payload['api_calls_made']}/{payload['api_call_cap']}\n\n"
        f"**Worst-case reserved standard-rate cost:** "
        f"${payload['reserved_standard_rate_upper_bound_usd']:.4f} / "
        f"${payload['maximum_api_cost_usd']:.2f}\n\n"
        f"{payload['next_action']}\n"
    )
    if args.summary:
        with args.summary.open("a") as stream:
            stream.write(summary)
    else:
        print(summary)
    return int(not payload["complete"])


if __name__ == "__main__":
    raise SystemExit(main())
