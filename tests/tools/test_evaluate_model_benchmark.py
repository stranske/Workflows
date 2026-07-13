from __future__ import annotations

import math

import pytest
from tools import evaluate_model_benchmark as evaluator

CATEGORIES = [
    "clean-pass",
    "missing-acceptance-criterion",
    "stale-verifier-claim",
    "review-thread-debt",
    "follow-up-required",
]


def _policy():
    return {
        "policy_id": "test-policy",
        "profiles": {
            "verifier-balanced": {
                "candidate_stage": {"required_case_categories": CATEGORIES},
                "approval_stage": {
                    "minimum_adjudicated_cases": 75,
                    "minimum_cases_per_category": 10,
                    "quality_gates": {
                        "task_success_rate_wilson_lower_bound": 0.85,
                        "false_pass_rate_wilson_upper_bound": 0.05,
                        "false_fail_rate_wilson_upper_bound": 0.1,
                        "schema_error_rate_wilson_upper_bound": 0.05,
                        "paired_success_noninferiority_margin": 0.02,
                    },
                },
            }
        },
    }


def _cases(*, cost: float, latency: float, false_passes: int = 0):
    cases = []
    case_index = 0
    for category in CATEGORIES:
        count = 40 if category == "clean-pass" else 20
        expected = "PASS" if category == "clean-pass" else "NON_PASS"
        for _ in range(count):
            actual = expected
            if expected == "NON_PASS" and false_passes > 0:
                actual = "PASS"
                false_passes -= 1
            cases.append(
                {
                    "case_id": f"case-{case_index}",
                    "category": category,
                    "expected_verdict": expected,
                    "actual_verdict": actual,
                    "schema_valid": True,
                    "input_tokens": 100,
                    "output_tokens": 10,
                    "total_cost_usd": cost,
                    "latency_ms": latency,
                }
            )
            case_index += 1
    return cases


def _payload(*, candidate_false_passes: int = 0):
    return {
        "benchmark_id": "bench-1",
        "profile": "verifier-balanced",
        "corpus_version": "corpus-v1",
        "prompt_version": "prompt-v1",
        "measured_at": "2026-07-10",
        "baseline_model_id": "baseline",
        "candidates": [
            {
                "provider": "openai",
                "model_id": "baseline",
                "cases": _cases(cost=0.02, latency=900),
            },
            {
                "provider": "openai",
                "model_id": "candidate",
                "cases": _cases(
                    cost=0.01,
                    latency=800,
                    false_passes=candidate_false_passes,
                ),
            },
        ],
    }


def test_wilson_interval_is_conservative_for_zero_errors():
    lower, upper = evaluator.wilson_interval(0, 80)
    assert lower == 0.0
    assert 0.04 < upper < 0.05


def test_passing_models_rank_by_cost_after_quality_gates():
    report = evaluator.evaluate_benchmark(_payload(), _policy())
    assert all(result["status"] == "passed" for result in report["results"])
    assert report["recommended_model_id"] == "candidate"
    assert report["results"][1]["metrics"]["sample_count"] == 120
    assert report["registry_evidence"][1]["status"] == "passed"
    assert report["registry_evidence"][1]["model_id"] == "candidate"


def test_false_passes_cannot_be_offset_by_lower_cost():
    report = evaluator.evaluate_benchmark(_payload(candidate_false_passes=8), _policy())
    candidate = report["results"][1]
    assert candidate["status"] == "failed"
    assert candidate["gate_results"]["false_pass_rate_wilson_upper_bound"] is False
    assert report["recommended_model_id"] == "baseline"


def test_unpaired_candidate_cases_are_rejected():
    payload = _payload()
    payload["candidates"][1]["cases"].pop()
    try:
        evaluator.evaluate_benchmark(payload, _policy())
    except ValueError as exc:
        assert "paired case IDs" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("unpaired benchmark should fail")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("total_cost_usd", math.nan),
        ("total_cost_usd", math.inf),
        ("total_cost_usd", -0.01),
        ("latency_ms", math.nan),
        ("latency_ms", math.inf),
        ("latency_ms", -1),
    ],
)
def test_nonfinite_or_negative_metrics_are_rejected(field, value):
    payload = _payload()
    payload["candidates"][1]["cases"][0][field] = value
    with pytest.raises(ValueError, match=f"invalid {field}"):
        evaluator.evaluate_benchmark(payload, _policy())


def test_nonobject_candidate_is_rejected_as_configuration_error():
    payload = _payload()
    payload["candidates"][1] = None
    with pytest.raises(ValueError, match="candidate must be an object"):
        evaluator.evaluate_benchmark(payload, _policy())
