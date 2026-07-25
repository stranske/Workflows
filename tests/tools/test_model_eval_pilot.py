import hashlib
import json
from pathlib import Path

# The owner-adjudicated seed is digest-frozen: it may never be silently edited.
# Machine-harvested cases (provenance == "harvested") are allowed to grow the
# corpus over time (stranske/Workflows#2819 move 2) and are validated
# structurally rather than by digest.
FROZEN_SEED_DIGEST = "a823e6fca7b3e16d5c6a8cff685ea9288cacedacc1ce7d9ca4c7af887227f287"
MACHINE_LABELABLE_CATEGORIES = {
    "clean-pass",
    "regression-after-merge",
    "follow-up-required",
}


def _load_cases():
    root = Path(__file__).resolve().parents[2]
    payload = json.loads((root / "config" / "model_eval_pilot.json").read_text())
    return payload, payload["cases"]


def test_pilot_seed_is_frozen() -> None:
    payload, cases = _load_cases()
    seed = [case for case in cases if case.get("provenance") != "harvested"]

    assert payload["schema"] == "workflows-verifier-pilot-corpus/v1"
    # Version keeps its adjudicated base; harvest runs append a "+harvestN" suffix.
    assert payload["corpus_version"].startswith("verifier-balanced-pilot-2026-07-12")
    assert len(seed) == 30

    identity = [
        {key: case[key] for key in ("case_id", "repo", "pr", "expected_verdict", "category")}
        for case in seed
    ]
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert digest == FROZEN_SEED_DIGEST, "the owner-adjudicated seed cases must not change"

    categories = {case["category"] for case in seed}
    assert {
        "clean-pass",
        "missing-acceptance-criterion",
        "stale-verifier-claim",
        "review-thread-debt",
        "follow-up-required",
    } <= categories


def test_corpus_is_well_formed_and_ids_unique() -> None:
    _payload, cases = _load_cases()
    assert len({case["case_id"] for case in cases}) == len(cases)
    assert all(case["repo"].startswith("stranske/") for case in cases)
    assert all(isinstance(case["pr"], int) and case["pr"] > 0 for case in cases)
    assert {case["expected_verdict"] for case in cases} <= {"PASS", "NON_PASS"}


def test_harvested_cases_are_constrained() -> None:
    _payload, cases = _load_cases()
    harvested = [case for case in cases if case.get("provenance") == "harvested"]
    for case in harvested:
        # Harvesting may only produce categories it can label from realized outcomes.
        assert case["category"] in MACHINE_LABELABLE_CATEGORIES
        assert "harvested_at" in case
