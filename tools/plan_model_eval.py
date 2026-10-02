#!/usr/bin/env python3
"""No-spend readiness report for verifier model cost/quality selection."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import NormalDist
from typing import Any

from tools.evaluate_model_benchmark import wilson_interval
from tools.model_eval_snapshots import screen_cases

ROOT = Path(__file__).resolve().parent.parent
SCREEN_HARNESS_FILES = (
    ".github/workflows/maint-78-model-evaluation-pilot.yml",
    ".github/actions/maint78-codex-cli/package-lock.json",
    "scripts/langchain/pr_verifier.py",
    "scripts/langchain/prompts/pr_evaluation.md",
    "scripts/langchain/verifier_config.py",
    "scripts/langchain/issue_pr_context.py",
    "scripts/langchain/structured_output.py",
    "scripts/langchain/injection_guard.py",
    "tools/run_model_eval_pilot.py",
    "tools/run_model_eval_cli_screen.py",
    "tools/model_eval_snapshots.py",
)


def screen_harness_fingerprint() -> str:
    """Bind a screen to its prompt, parser, case fetcher and CLI harness.

    The API confirmer is intentionally excluded: fixing its request adapter
    must not force another subscription screen of unchanged model inputs.
    """
    digest = hashlib.sha256()
    for name in SCREEN_HARNESS_FILES:
        path = ROOT / name
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _zero_error_denominator(maximum_rate: float, confidence_level: float) -> int:
    """Smallest sample whose Wilson upper bound passes with zero errors."""
    if not 0 < maximum_rate < 1 or not 0 < confidence_level < 1:
        raise ValueError("quality gate rates and confidence must be between 0 and 1")
    z = NormalDist().inv_cdf((1 + confidence_level) / 2)
    return next(
        count for count in range(1, 100_001) if wilson_interval(0, count, z=z)[1] <= maximum_rate
    )


def build_plan(
    corpus: dict[str, Any],
    registry: dict[str, Any],
    policy: dict[str, Any],
    candidates: dict[str, Any] | None = None,
    cli_catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = policy["profiles"]["verifier-balanced"]
    candidate_stage = profile["candidate_stage"]
    approval = profile["approval_stage"]
    cases = corpus["cases"]
    counts = Counter(str(case["category"]) for case in cases)
    minimum = int(approval["minimum_adjudicated_cases"])
    positive_cases = sum(case.get("expected_verdict") == "PASS" for case in cases)
    negative_cases = sum(case.get("expected_verdict") == "NON_PASS" for case in cases)
    false_pass_floor = _zero_error_denominator(
        float(approval["quality_gates"]["false_pass_rate_wilson_upper_bound"]),
        float(approval["confidence_level"]),
    )
    false_fail_floor = _zero_error_denominator(
        float(approval["quality_gates"]["false_fail_rate_wilson_upper_bound"]),
        float(approval["confidence_level"]),
    )
    additional_non_pass = max(0, false_pass_floor - negative_cases)
    additional_pass = max(0, false_fail_floor - positive_cases)
    best_case_total = len(cases) + additional_non_pass + additional_pass
    confidence_label = f"{float(approval['confidence_level']):.0%}"
    default_category_minimum = int(approval["minimum_cases_per_category"])
    overrides = approval.get("minimum_cases_per_category_overrides", {})
    category_shortfalls = {
        category: max(0, int(overrides.get(category, default_category_minimum)) - counts[category])
        for category in candidate_stage["required_case_categories"]
    }
    category_shortfalls = {key: value for key, value in category_shortfalls.items() if value}
    provisional = profile["provisional_stage"]
    selected_cases, snapshot_blockers = screen_cases(corpus, provisional)
    screen_category_shortfalls = sorted(
        set(provisional["required_screen_categories"])
        - {case["category"] for case in selected_cases}
    )
    if screen_category_shortfalls:
        snapshot_blockers.append(
            f"Selected screen cases omit required categories: {screen_category_shortfalls}."
        )
    screen_corpus_ready = (
        len(selected_cases) == int(provisional["screen_cases"]) and not snapshot_blockers
    )
    input_alignment_ready = (
        corpus.get("screen_input_status") == "production_context_adjudicated"
        and not snapshot_blockers
    )
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
    incumbent_selection = next(
        (
            selection
            for selection in registry["selections"]
            if selection.get("profile") == "verifier-balanced"
            and selection.get("provider") == "openai"
        ),
        None,
    )
    incumbent = incumbent_selection["model_id"] if incumbent_selection else None
    evidence_by_id = {
        item["evidence_id"]: item
        for item in registry.get("evidence", [])
        if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
    }
    provisional_evidence = (
        next(
            (
                evidence_by_id[evidence_id]
                for evidence_id in incumbent_selection.get("evidence_ids", [])
                if evidence_id in evidence_by_id
                and evidence_by_id[evidence_id].get("kind") == "provisional-workload-comparison"
                and evidence_by_id[evidence_id].get("status") == "provisional"
                and evidence_by_id[evidence_id].get("model_id") == incumbent
            ),
            None,
        )
        if incumbent_selection
        else None
    )
    screen_model_ids = {
        model["model_id"]
        for model in priced
        if cli_catalog is None or model["model_id"] in listed_cli_models
    }
    screen_ready = (
        screen_corpus_ready
        and input_alignment_ready
        and incumbent in screen_model_ids
        and len(screen_model_ids) >= 2
    )
    screen_blockers = []
    if not screen_corpus_ready:
        screen_blockers.append(
            f"Candidate screen needs {provisional['screen_cases']} separately adjudicated paired "
            f"cases, at least {provisional['minimum_non_pass_cases']} NON_PASS cases, "
            f"and every required category; missing categories: {screen_category_shortfalls}."
        )
    if not input_alignment_ready:
        screen_blockers.append(
            "The historical labels describe later issue disposition, while the CLI screen "
            "did not receive the production verifier's exact context and diff summary. "
            "Capture production verifier inputs and independently adjudicate a small paired "
            "PASS/NON_PASS set before another model screen."
        )
        screen_blockers.extend(snapshot_blockers)
    if incumbent not in screen_model_ids or len(screen_model_ids) < 2:
        screen_blockers.append(
            "Candidate screen needs the priced incumbent and at least one priced alternative "
            "in the pinned Codex CLI catalog."
        )
    reasons = []
    if len(cases) < minimum:
        reasons.append(f"Corpus has {len(cases)} adjudicated cases; approval requires {minimum}.")
    if additional_non_pass:
        reasons.append(
            f"Even with zero false passes, the {confidence_label} Wilson gate needs {false_pass_floor} "
            f"NON_PASS cases; only {negative_cases} exist ({additional_non_pass} more needed)."
        )
    if additional_pass:
        reasons.append(
            f"Even with zero false fails, the {confidence_label} Wilson gate needs {false_fail_floor} "
            f"PASS cases; only {positive_cases} exist ({additional_pass} more needed)."
        )
    maximum_corpus = int(profile["corpus_growth"]["max_corpus_size"])
    if max(minimum, best_case_total) > maximum_corpus:
        reasons.append(
            f"Best-case sample needs at least {max(minimum, best_case_total)} cases, above the "
            f"configured corpus cap of {maximum_corpus}."
        )
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
        "Statistical approval still lacks an approval-stage paired API benchmark on "
        "the frozen adjudicated corpus; the completed eight-case provisional comparison "
        "does not establish the population error-rate bounds."
        if provisional_evidence
        else "MAINT-78 has no paired production API benchmark with measured tokens and cost; "
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
        "objective": (
            "Keep the provisional verifier model cost-efficient and safe on live work; "
            "reconsider it promptly when model or workload facts change."
            if provisional_evidence
            else "Find a cost-efficient verifier model quickly, then review a reversible "
            "provisional choice with explicit quality limits."
        ),
        "input_fingerprint": fingerprint,
        "screen_harness_fingerprint": screen_harness_fingerprint(),
        "provisional_thresholds": {
            key: profile["provisional_stage"][key]
            for key in (
                "maximum_false_passes",
                "maximum_schema_errors",
                "minimum_accuracy_delta_vs_incumbent",
                "minimum_pass_recall",
            )
        },
        "approval_ready": False,
        "screen_ready": screen_ready,
        "input_alignment_ready": input_alignment_ready,
        "screen_case_kinds": {
            case["case_id"]: case.get("production_snapshot", {}).get("input_kind")
            for case in selected_cases
        },
        "screen_blockers": screen_blockers,
        "benchmark_inputs_ready": benchmark_inputs_ready,
        "approval_blockers": reasons,
        "corpus_cases": len(cases),
        "expected_pass_cases": positive_cases,
        "expected_non_pass_cases": negative_cases,
        "zero_error_false_pass_denominator": false_pass_floor,
        "zero_error_false_fail_denominator": false_fail_floor,
        "additional_non_pass_cases_for_best_case_gate": additional_non_pass,
        "best_case_minimum_corpus_cases": max(minimum, best_case_total),
        "approval_minimum_cases": minimum,
        "category_counts": dict(sorted(counts.items())),
        "category_shortfalls": category_shortfalls,
        "incumbent": incumbent,
        "provisional_evidence_id": (
            provisional_evidence["evidence_id"] if provisional_evidence else None
        ),
        "provisional_review_by": (
            incumbent_selection.get("review_by") if provisional_evidence else None
        ),
        "priced_openai_models": [model["model_id"] for model in priced],
        "unpriced_openai_models": unpriced,
        "catalog_advisory_models": catalog_advisory,
        "pinned_cli_unavailable_models": cli_unavailable,
        "automatic_api_calls": 0,
        "screen_limit": {
            "cases": int(provisional["screen_cases"]),
            "models": 4,
            "maximum_cli_calls": 4 * int(provisional["screen_cases"]),
            "api_calls": 0,
        },
        "next_action": (
            "Monitor the first ten live verifier outcomes or review by "
            f"{incumbent_selection['review_by']}, whichever comes first; revert on false "
            "PASS or material regression. Rerun the bounded screen when the catalog, "
            "price, prompt, or workload changes."
            if provisional_evidence
            else (
                "Run one bounded, paired Codex CLI screen of the incumbent and up to three "
                "priced candidates. Advance any candidate that meets the provisional-stage "
                "false-PASS, schema-error, and accuracy limits, then compare modeled cost "
                "per accepted review in a small capped "
                "API confirmation; review a provisional selection without waiting for the "
                "long-term statistical approval sample."
                if screen_ready
                else "Resolve the candidate screen blockers, then compare the incumbent with "
                "priced alternatives."
            )
        ),
    }


def markdown(plan: dict[str, Any]) -> str:
    lines = [
        "## MAINT-78 current verifier model decision",
        "",
        f"**Objective:** {plan['objective']}",
        f"**Current OpenAI selection:** {plan['incumbent']}",
        f"**Provisional paired evidence:** {plan['provisional_evidence_id'] or 'none'}",
        f"**Eight-case subscription screen ready:** {'yes' if plan['screen_ready'] else 'no'}",
        f"**Next action:** {plan['next_action']}",
        f"**Automatic API calls:** {plan['automatic_api_calls']}",
        (
            "**Decision horizon:** Review the provisional choice on live outcomes and new "
            "model or workload information; statistical approval is separate."
            if plan["provisional_evidence_id"]
            else "**Decision horizon:** Produce a retain-or-advance result from the bounded "
            "screen; do not wait for the statistical approval sample."
        ),
        f"**Input fingerprint:** `{plan['input_fingerprint']}`",
        f"**Screen harness fingerprint:** `{plan['screen_harness_fingerprint']}`",
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
    if plan["screen_blockers"]:
        lines += ["", "### Candidate screen blockers", ""]
        lines += [f"- {reason}" for reason in plan["screen_blockers"]]
    lines += [
        "",
        "### Separate long-term statistical approval",
        "",
        f"**Ready:** {'yes' if plan['approval_ready'] else 'no'}",
        f"**Benchmark inputs ready:** {'yes' if plan['benchmark_inputs_ready'] else 'no'}",
        f"**Historical corpus:** {plan['corpus_cases']} / {plan['approval_minimum_cases']} cases",
        f"**Best-case statistical floor:** {plan['best_case_minimum_corpus_cases']} total "
        f"including {plan['zero_error_false_pass_denominator']} NON_PASS cases",
    ]
    lines += [f"- {reason}" for reason in plan["approval_blockers"]]
    lines.append("")
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
