#!/usr/bin/env python3
"""No-spend readiness report for verifier model cost/quality selection."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def build_plan(
    corpus: dict[str, Any],
    registry: dict[str, Any],
    policy: dict[str, Any],
    candidates: dict[str, Any] | None = None,
    cli_catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = policy["profiles"]["verifier-balanced"]
    approval = profile["approval_stage"]
    cases = corpus["cases"]
    counts = Counter(str(case["category"]) for case in cases)
    minimum = int(approval["minimum_adjudicated_cases"])
    default_category_minimum = int(approval["minimum_cases_per_category"])
    overrides = approval.get("minimum_cases_per_category_overrides", {})
    category_shortfalls = {
        category: max(0, int(overrides.get(category, default_category_minimum)) - counts[category])
        for category in profile["candidate_stage"]["required_case_categories"]
    }
    category_shortfalls = {key: value for key, value in category_shortfalls.items() if value}
    current_models = [
        model
        for model in registry["models"]
        if model.get("provider") == "openai"
        and model.get("lifecycle") == "current"
        and not model.get("blocked", False)
    ]
    priced = [
        model
        for model in current_models
        if isinstance(model.get("pricing"), dict)
        and all(
            key in model["pricing"]
            for key in ("input_per_million_tokens", "output_per_million_tokens")
        )
    ]
    unpriced = [model["model_id"] for model in current_models if model not in priced]
    catalog_advisory = [
        str(entry["model_id"])
        for entry in (candidates or {}).get("candidates", [])
        if entry.get("provider") == "openai" and entry.get("role") == "catalog-advisory"
    ]
    unpriced_advisory = [
        model for model in catalog_advisory if model not in {entry["model_id"] for entry in priced}
    ]
    listed_cli_models = {
        str(model.get("slug"))
        for model in (cli_catalog or {}).get("models", [])
        if model.get("visibility") == "list" and model.get("supported_in_api") is True
    }
    cli_unavailable = (
        [model["model_id"] for model in priced if model["model_id"] not in listed_cli_models]
        if cli_catalog is not None
        else []
    )
    incumbent = next(
        (
            selection["model_id"]
            for selection in registry["selections"]
            if selection.get("profile") == "verifier-balanced"
            and selection.get("provider") == "openai"
        ),
        None,
    )
    reasons = []
    if len(cases) < minimum:
        reasons.append(f"Corpus has {len(cases)} adjudicated cases; approval requires {minimum}.")
    if category_shortfalls:
        reasons.append(f"Category minimums are unmet: {category_shortfalls}.")
    if incumbent not in {model["model_id"] for model in priced}:
        reasons.append("The OpenAI incumbent is missing or has no verified price.")
    if len(priced) < 2:
        reasons.append("At least one priced alternative to the incumbent is required.")
    if unpriced or unpriced_advisory:
        reasons.append(
            "Current or newly discovered OpenAI models lack verified prices: "
            f"{sorted(set(unpriced + unpriced_advisory))}."
        )
    if cli_unavailable:
        reasons.append(
            "Priced models absent from the pinned Codex CLI catalog need a separate, "
            f"bounded API compatibility check: {cli_unavailable}."
        )
    if not corpus.get("cases"):
        reasons.append("No adjudicated cases are available.")
    benchmark_inputs_ready = not reasons
    reasons.append(
        "MAINT-78 has no paired production API benchmark with measured tokens and cost; "
        "a model selection cannot be approved from the existing pilot artifacts."
    )
    fingerprint_input = {
        "corpus": corpus,
        "policy": profile,
        "models": current_models,
        "catalog_advisory": catalog_advisory,
        "cli_available": sorted(listed_cli_models) if cli_catalog is not None else None,
        "incumbent": incumbent,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_input, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "schema": "workflows-verifier-model-eval-plan/v1",
        "objective": "Choose the lowest cost per accepted verifier review among models that pass quality gates.",
        "input_fingerprint": fingerprint,
        "approval_ready": False,
        "benchmark_inputs_ready": benchmark_inputs_ready,
        "approval_blockers": reasons,
        "corpus_cases": len(cases),
        "approval_minimum_cases": minimum,
        "category_counts": dict(sorted(counts.items())),
        "category_shortfalls": category_shortfalls,
        "incumbent": incumbent,
        "priced_openai_models": [model["model_id"] for model in priced],
        "unpriced_openai_models": unpriced,
        "catalog_advisory_models": catalog_advisory,
        "pinned_cli_unavailable_models": cli_unavailable,
        "automatic_api_calls": 0,
        "screen_limit": {"cases": 8, "models": 4, "maximum_cli_calls": 32, "api_calls": 0},
        "next_action": "Use existing results to narrow candidates; grow the corpus to policy minimums, "
        "then run a capped paired production API confirmation with measured tokens "
        "and cost before promotion.",
    }


def markdown(plan: dict[str, Any]) -> str:
    lines = [
        "## MAINT-78 verifier model decision readiness",
        "",
        f"**Objective:** {plan['objective']}",
        f"**Approval ready:** {'yes' if plan['approval_ready'] else 'no'}",
        f"**Benchmark inputs ready:** {'yes' if plan['benchmark_inputs_ready'] else 'no'}",
        f"**Automatic API calls:** {plan['automatic_api_calls']}",
        f"**Input fingerprint:** `{plan['input_fingerprint']}`",
        f"**Corpus:** {plan['corpus_cases']} / {plan['approval_minimum_cases']} cases",
        f"**Priced OpenAI models:** {', '.join(plan['priced_openai_models']) or 'none'}",
    ]
    if plan["unpriced_openai_models"]:
        lines.append("**Models missing prices:** " + ", ".join(plan["unpriced_openai_models"]))
    if plan["catalog_advisory_models"]:
        lines.append(
            "**New catalog models needing review:** " + ", ".join(plan["catalog_advisory_models"])
        )
    if plan["pinned_cli_unavailable_models"]:
        lines.append(
            "**Absent from pinned CLI catalog:** "
            + ", ".join(plan["pinned_cli_unavailable_models"])
        )
    if plan["approval_blockers"]:
        lines += ["", "### Why a selection cannot be approved", ""]
        lines += [f"- {reason}" for reason in plan["approval_blockers"]]
    lines += ["", f"**Next action:** {plan['next_action']}", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=ROOT / "config/model_eval_pilot.json")
    parser.add_argument("--registry", type=Path, default=ROOT / "config/model_registry.json")
    parser.add_argument("--policy", type=Path, default=ROOT / "config/model_selection_policy.json")
    parser.add_argument(
        "--candidates", type=Path, default=ROOT / "config/model_eval_candidates.json"
    )
    parser.add_argument("--cli-catalog", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args(argv)
    plan = build_plan(
        json.loads(args.corpus.read_text()),
        json.loads(args.registry.read_text()),
        json.loads(args.policy.read_text()),
        json.loads(args.candidates.read_text()),
        json.loads(args.cli_catalog.read_text()) if args.cli_catalog else None,
    )
    args.output.write_text(json.dumps(plan, indent=2) + "\n")
    if args.summary:
        with args.summary.open("a") as stream:
            stream.write(markdown(plan))
    else:
        print(markdown(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
