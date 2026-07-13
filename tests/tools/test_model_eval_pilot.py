import hashlib
import json
from pathlib import Path


def test_pilot_corpus_is_frozen_and_well_formed() -> None:
    root = Path(__file__).resolve().parents[2]
    payload = json.loads((root / "config" / "model_eval_pilot.json").read_text())
    cases = payload["cases"]

    assert payload["schema"] == "workflows-verifier-pilot-corpus/v1"
    assert payload["corpus_version"] == "verifier-balanced-pilot-2026-07-12"
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

    identity = [
        {key: case[key] for key in ("case_id", "repo", "pr", "expected_verdict", "category")}
        for case in cases
    ]
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert digest == "a823e6fca7b3e16d5c6a8cff685ea9288cacedacc1ce7d9ca4c7af887227f287"
