import json
from pathlib import Path


def test_pilot_corpus_is_frozen_and_well_formed() -> None:
    root = Path(__file__).resolve().parents[2]
    payload = json.loads((root / "config" / "model_eval_pilot.json").read_text())
    cases = payload["cases"]

    assert payload["schema"] == "workflows-verifier-pilot-corpus/v1"
    assert len(cases) == 30
    assert len({case["case_id"] for case in cases}) == 30
    assert all(case["repo"].startswith("stranske/") for case in cases)
    assert all(isinstance(case["pr"], int) and case["pr"] > 0 for case in cases)
    assert {case["expected_verdict"] for case in cases} == {"PASS", "NON_PASS"}

    categories = {case["category"] for case in cases}
    assert {
        "clean-pass",
        "missing-acceptance-criterion",
        "stale-verifier-claim",
        "review-thread-debt",
        "follow-up-required",
    } <= categories
