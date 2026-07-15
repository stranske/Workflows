#!/usr/bin/env python3
"""Evaluate paired model candidates against the repository selection policy."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from statistics import NormalDist
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_POLICY_PATH = _REPO_ROOT / "config" / "model_selection_policy.json"
Z_95 = 1.959963984540054


def wilson_interval(successes: int, total: int, *, z: float = Z_95) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 1.0
    rate = successes / total
    denominator = 1 + (z * z / total)
    center = (rate + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((rate * (1 - rate) + z * z / (4 * total)) / total) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def _nearest_rank_p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _case_outcome(case: dict[str, Any]) -> tuple[str, str, bool]:
    expected = str(case.get("expected_verdict", "")).strip().upper()
    actual = str(case.get("actual_verdict", "")).strip().upper()
    schema_valid = case.get("schema_valid") is True
    if expected not in {"PASS", "NON_PASS"}:
        raise ValueError(f"case {case.get('case_id')} has invalid expected_verdict")
    if actual not in {"PASS", "NON_PASS"}:
        raise ValueError(f"case {case.get('case_id')} has invalid actual_verdict")
    return expected, actual, schema_valid


def _metrics(cases: list[dict[str, Any]], *, z: float = Z_95) -> dict[str, Any]:
    success = false_pass = false_fail = schema_error = 0
    expected_pass = expected_non_pass = 0
    categories: dict[str, int] = {}
    total_cost = 0.0
    latencies: list[float] = []
    case_success: dict[str, bool] = {}
    for case in cases:
        case_id = str(case.get("case_id", "")).strip()
        category = str(case.get("category", "")).strip()
        if not case_id or not category:
            raise ValueError("every case requires case_id and category")
        if case_id in case_success:
            raise ValueError(f"duplicate case_id {case_id}")
        expected, actual, schema_valid = _case_outcome(case)
        correct = schema_valid and expected == actual
        case_success[case_id] = correct
        success += int(correct)
        schema_error += int(not schema_valid)
        expected_pass += int(expected == "PASS")
        expected_non_pass += int(expected == "NON_PASS")
        false_pass += int(expected == "NON_PASS" and actual == "PASS")
        false_fail += int(expected == "PASS" and actual == "NON_PASS")
        categories[category] = categories.get(category, 0) + 1
        cost = float(case.get("total_cost_usd", 0.0))
        latency = float(case.get("latency_ms", 0.0))
        if not math.isfinite(cost) or cost < 0:
            raise ValueError(f"case {case_id} has invalid total_cost_usd")
        if not math.isfinite(latency) or latency < 0:
            raise ValueError(f"case {case_id} has invalid latency_ms")
        total_cost += cost
        latencies.append(latency)

    count = len(cases)
    success_interval = wilson_interval(success, count, z=z)
    false_pass_interval = wilson_interval(false_pass, expected_non_pass, z=z)
    false_fail_interval = wilson_interval(false_fail, expected_pass, z=z)
    schema_interval = wilson_interval(schema_error, count, z=z)
    return {
        "sample_count": count,
        "category_counts": categories,
        "task_success_rate": success / count if count else 0.0,
        "task_success_rate_wilson_lower_bound": success_interval[0],
        "false_pass_rate": false_pass / expected_non_pass if expected_non_pass else 0.0,
        "false_pass_rate_wilson_upper_bound": false_pass_interval[1],
        "false_fail_rate": false_fail / expected_pass if expected_pass else 0.0,
        "false_fail_rate_wilson_upper_bound": false_fail_interval[1],
        "schema_error_rate": schema_error / count if count else 0.0,
        "schema_error_rate_wilson_upper_bound": schema_interval[1],
        "total_cost_usd": total_cost,
        "cost_per_accepted_review_usd": total_cost / success if success else None,
        "p95_latency_ms": _nearest_rank_p95(latencies),
        "case_success": case_success,
    }


def _validate_paired_cases(candidates: list[Any]) -> None:
    expected_ids: set[str] | None = None
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("each candidate must be an object")
        cases = candidate.get("cases")
        if not isinstance(cases, list):
            raise ValueError("each candidate requires a cases list")
        case_ids = {str(case.get("case_id", "")) for case in cases if isinstance(case, dict)}
        if len(case_ids) != len(cases) or "" in case_ids:
            raise ValueError("candidate cases require unique non-empty case_id values")
        if expected_ids is None:
            expected_ids = case_ids
        elif case_ids != expected_ids:
            raise ValueError("all candidates must evaluate the same paired case IDs")


def evaluate_benchmark(payload: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    profile = str(payload.get("profile", "")).strip()
    profiles = policy.get("profiles", {})
    if not isinstance(profiles, dict) or profile not in profiles:
        raise ValueError(f"unknown benchmark profile: {profile}")
    profile_policy = profiles[profile]
    approval = profile_policy["approval_stage"]
    gates = approval["quality_gates"]
    confidence_level = float(approval.get("confidence_level", 0.95))
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("approval_stage.confidence_level must be between 0 and 1")
    z = NormalDist().inv_cdf((1.0 + confidence_level) / 2.0)
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) < 2:
        raise ValueError("benchmark requires a baseline and at least one candidate")
    _validate_paired_cases(candidates)

    baseline_model = str(payload.get("baseline_model_id", "")).strip()
    results: list[dict[str, Any]] = []
    metrics_by_model: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        model_id = str(candidate.get("model_id", "")).strip()
        provider = str(candidate.get("provider", "")).strip()
        if not model_id or not provider or model_id in metrics_by_model:
            raise ValueError("candidate provider/model_id values must be non-empty and unique")
        metrics_by_model[model_id] = _metrics(candidate["cases"], z=z)
    if baseline_model not in metrics_by_model:
        raise ValueError("baseline_model_id must identify one candidate")

    baseline = metrics_by_model[baseline_model]
    required_categories = profile_policy["candidate_stage"]["required_case_categories"]
    minimum_cases = int(approval["minimum_adjudicated_cases"])
    minimum_per_category = int(approval["minimum_cases_per_category"])
    noninferiority_margin = float(gates["paired_success_noninferiority_margin"])

    for candidate in candidates:
        model_id = str(candidate["model_id"]).strip()
        metrics = metrics_by_model[model_id]
        gate_results = {
            "minimum_adjudicated_cases": metrics["sample_count"] >= minimum_cases,
            "minimum_cases_per_category": all(
                metrics["category_counts"].get(category, 0) >= minimum_per_category
                for category in required_categories
            ),
            "task_success_rate_wilson_lower_bound": metrics["task_success_rate_wilson_lower_bound"]
            >= float(gates["task_success_rate_wilson_lower_bound"]),
            "false_pass_rate_wilson_upper_bound": metrics["false_pass_rate_wilson_upper_bound"]
            <= float(gates["false_pass_rate_wilson_upper_bound"]),
            "false_fail_rate_wilson_upper_bound": metrics["false_fail_rate_wilson_upper_bound"]
            <= float(gates["false_fail_rate_wilson_upper_bound"]),
            "schema_error_rate_wilson_upper_bound": metrics["schema_error_rate_wilson_upper_bound"]
            <= float(gates["schema_error_rate_wilson_upper_bound"]),
            "paired_success_noninferiority": (
                metrics["task_success_rate"] - baseline["task_success_rate"]
            )
            >= -noninferiority_margin,
        }
        public_metrics = {key: value for key, value in metrics.items() if key != "case_success"}
        results.append(
            {
                "provider": str(candidate["provider"]),
                "model_id": model_id,
                "status": "passed" if all(gate_results.values()) else "failed",
                "gate_results": gate_results,
                "metrics": public_metrics,
            }
        )

    passing = [result for result in results if result["status"] == "passed"]
    ranked = sorted(
        passing,
        key=lambda item: (
            (
                float("inf")
                if item["metrics"]["cost_per_accepted_review_usd"] is None
                else item["metrics"]["cost_per_accepted_review_usd"]
            ),
            item["metrics"]["p95_latency_ms"],
        ),
    )
    benchmark_id = str(payload.get("benchmark_id", "")).strip()
    corpus_version = str(payload.get("corpus_version", "")).strip()
    prompt_version = str(payload.get("prompt_version", "")).strip()
    measured_at = str(payload.get("measured_at", "")).strip()
    if not benchmark_id or not corpus_version or not prompt_version or not measured_at:
        raise ValueError(
            "benchmark_id, corpus_version, prompt_version, and measured_at are required"
        )
    registry_evidence = [
        {
            "evidence_id": f"{benchmark_id}:{result['provider']}:{result['model_id']}",
            "schema": "workflows-model-benchmark-evidence/v1",
            "kind": "workload-benchmark",
            "status": result["status"],
            "measured_at": measured_at,
            "policy_id": str(policy.get("policy_id", "")).strip(),
            "profile": profile,
            "corpus_version": corpus_version,
            "prompt_version": prompt_version,
            "provider": result["provider"],
            "model_id": result["model_id"],
            "gate_results": result["gate_results"],
            "metrics": result["metrics"],
        }
        for result in results
    ]
    return {
        "schema": "workflows-model-benchmark-evidence/v1",
        "benchmark_id": benchmark_id,
        "policy_id": str(policy.get("policy_id", "")).strip(),
        "profile": profile,
        "corpus_version": corpus_version,
        "prompt_version": prompt_version,
        "measured_at": measured_at,
        "baseline_model_id": baseline_model,
        "results": results,
        "registry_evidence": registry_evidence,
        "recommended_model_id": ranked[0]["model_id"] if ranked else None,
        "recommendation_rule": "quality gates, then cost per accepted review, then p95 latency",
    }


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a paired model benchmark.")
    parser.add_argument("benchmark", type=Path)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = evaluate_benchmark(_load_object(args.benchmark), _load_object(args.policy))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"benchmark error: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["recommended_model_id"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
