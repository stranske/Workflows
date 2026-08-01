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
                    "confidence_level": 0.95,
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


def test_invalid_confidence_level_is_rejected():
    policy = _policy()
    policy["profiles"]["verifier-balanced"]["approval_stage"]["confidence_level"] = 1.0
    with pytest.raises(ValueError, match="confidence_level"):
        evaluator.evaluate_benchmark(_payload(), policy)


def test_near_one_confidence_level_has_finite_interval():
    policy = _policy()
    policy["profiles"]["verifier-balanced"]["approval_stage"]["confidence_level"] = math.nextafter(
        1.0, 0.0
    )
    report = evaluator.evaluate_benchmark(_payload(), policy)
    wilson_metrics = (
        "task_success_rate_wilson_lower_bound",
        "false_pass_rate_wilson_upper_bound",
        "false_fail_rate_wilson_upper_bound",
        "schema_error_rate_wilson_upper_bound",
    )
    assert all(
        math.isfinite(result["metrics"][metric])
        for result in report["results"]
        for metric in wilson_metrics
    )


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


def _thin_owner_cases(*, cost: float, latency: float):
    """Corpus shaped like the real one: owner-sourced categories are thin.

    clean-pass is at its harvest cap and follow-up-required is machine-grown, but
    the three owner-sourced categories only ever get hand-labelled examples.
    """
    counts = {
        "clean-pass": 50,
        "follow-up-required": 20,
        "stale-verifier-claim": 5,
        "review-thread-debt": 2,
        "missing-acceptance-criterion": 1,
    }
    cases = []
    index = 0
    for category, count in counts.items():
        expected = "PASS" if category == "clean-pass" else "NON_PASS"
        for _ in range(count):
            cases.append(
                {
                    "case_id": f"thin-{index}",
                    "category": category,
                    "expected_verdict": expected,
                    "actual_verdict": expected,
                    "schema_valid": True,
                    "input_tokens": 100,
                    "output_tokens": 10,
                    "total_cost_usd": cost,
                    "latency_ms": latency,
                }
            )
            index += 1
    return cases


def _thin_payload():
    payload = _payload()
    payload["candidates"] = [
        {
            "provider": "openai",
            "model_id": "baseline",
            "cases": _thin_owner_cases(cost=0.02, latency=900),
        },
        {
            "provider": "openai",
            "model_id": "candidate",
            "cases": _thin_owner_cases(cost=0.01, latency=800),
        },
    ]
    return payload


def _gate(report, model_id, gate_name):
    result = next(r for r in report["results"] if r["model_id"] == model_id)
    return result["gate_results"][gate_name]


def test_owner_sourced_categories_block_approval_without_overrides():
    """Without overrides the thin owner-sourced categories fail the floor."""
    report = evaluator.evaluate_benchmark(_thin_payload(), _policy())

    assert _gate(report, "candidate", "minimum_cases_per_category") is False
    assert _gate(report, "candidate", "minimum_adjudicated_cases") is True


def test_per_category_overrides_admit_thin_owner_sourced_categories():
    """Overrides let the un-harvestable categories assert representation only."""
    policy = _policy()
    policy["profiles"]["verifier-balanced"]["approval_stage"][
        "minimum_cases_per_category_overrides"
    ] = {
        "stale-verifier-claim": 1,
        "review-thread-debt": 1,
        "missing-acceptance-criterion": 1,
    }

    report = evaluator.evaluate_benchmark(_thin_payload(), policy)

    assert _gate(report, "candidate", "minimum_cases_per_category") is True
    # The machine-harvestable floor is untouched.
    assert (
        policy["profiles"]["verifier-balanced"]["approval_stage"]["minimum_cases_per_category"]
        == 10
    )


def test_override_still_requires_each_category_to_be_represented():
    """A category with zero cases fails even at the lowest legal floor of 1."""
    policy = _policy()
    policy["profiles"]["verifier-balanced"]["approval_stage"][
        "minimum_cases_per_category_overrides"
    ] = {"missing-acceptance-criterion": 1}
    payload = _thin_payload()
    for candidate in payload["candidates"]:
        candidate["cases"] = [
            case
            for case in candidate["cases"]
            if case["category"] != "missing-acceptance-criterion"
        ]

    report = evaluator.evaluate_benchmark(payload, policy)

    assert _gate(report, "candidate", "minimum_cases_per_category") is False


@pytest.mark.parametrize("floor", [0, -1])
def test_override_floor_below_one_is_rejected(floor):
    policy = _policy()
    policy["profiles"]["verifier-balanced"]["approval_stage"][
        "minimum_cases_per_category_overrides"
    ] = {"review-thread-debt": floor}

    with pytest.raises(ValueError, match="must be >= 1"):
        evaluator.evaluate_benchmark(_thin_payload(), policy)


def test_override_for_unknown_category_is_rejected():
    policy = _policy()
    policy["profiles"]["verifier-balanced"]["approval_stage"][
        "minimum_cases_per_category_overrides"
    ] = {"not-a-category": 1}

    with pytest.raises(ValueError, match="not.*required"):
        evaluator.evaluate_benchmark(_thin_payload(), policy)


def test_override_must_be_an_object():
    policy = _policy()
    policy["profiles"]["verifier-balanced"]["approval_stage"][
        "minimum_cases_per_category_overrides"
    ] = ["stale-verifier-claim"]

    with pytest.raises(ValueError, match="must be an object"):
        evaluator.evaluate_benchmark(_thin_payload(), policy)
