"""Pinned production verifier inputs for small, paired MAINT-78 screens."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any


def snapshot_digest(snapshot: dict[str, Any]) -> str:
    payload = {
        key: snapshot[key]
        for key in ("context", "diff_summary", "chain_depth", "merge_sha", "source_run_id")
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def verifier_prompt(snapshot: dict[str, Any]) -> str:
    """Build the same prompt production uses, including follow-up chain depth."""
    from scripts.langchain import pr_verifier

    previous = os.environ.get("CHAIN_DEPTH")
    os.environ["CHAIN_DEPTH"] = str(snapshot["chain_depth"])
    try:
        return pr_verifier._prepare_prompt(snapshot["context"], snapshot["diff_summary"])
    finally:
        if previous is None:
            os.environ.pop("CHAIN_DEPTH", None)
        else:
            os.environ["CHAIN_DEPTH"] = previous


def screen_cases(
    corpus: dict[str, Any], stage: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Check labels and immutable input snapshots before any model is invoked."""
    ids = corpus.get("screen_case_ids")
    required = int(stage["screen_cases"])
    if (
        not isinstance(ids, list)
        or len(ids) != required
        or any(not isinstance(case_id, str) for case_id in ids)
        or len(set(ids)) != len(ids)
    ):
        return [], [f"Select exactly {required} unique production-context screen case IDs."]
    lookup = {case["case_id"]: case for case in corpus["cases"]}
    if any(case_id not in lookup for case_id in ids):
        return [], ["A screen case ID is absent from the adjudicated corpus."]
    cases = [lookup[case_id] for case_id in ids]
    non_pass = sum(case["expected_verdict"] == "NON_PASS" for case in cases)
    pass_count = sum(case["expected_verdict"] == "PASS" for case in cases)
    blockers = []
    if non_pass < int(stage["minimum_non_pass_cases"]) or pass_count < required // 2:
        blockers.append(
            "The paired screen needs at least half PASS and the required NON_PASS cases."
        )
    for case in cases:
        snapshot = case.get("production_snapshot")
        if not isinstance(snapshot, dict):
            blockers.append(f"{case['case_id']}: missing production input snapshot")
            continue
        required_fields = (
            "context",
            "diff_summary",
            "chain_depth",
            "merge_sha",
            "source_run_id",
            "adjudication_evidence",
            "adjudicated_by",
            "adjudication_rationale",
            "input_kind",
            "sha256",
        )
        if any(field not in snapshot for field in required_fields):
            blockers.append(f"{case['case_id']}: incomplete snapshot or independent adjudication")
            continue
        if (
            not snapshot["context"]
            or not snapshot["diff_summary"]
            or not snapshot["adjudication_evidence"]
            or not snapshot["adjudicated_by"]
            or not snapshot["adjudication_rationale"]
            or snapshot["input_kind"] not in {"production_capture", "controlled_defect"}
            or (snapshot["input_kind"] == "controlled_defect" and not snapshot.get("mutation_note"))
            or not isinstance(snapshot["chain_depth"], int)
            or snapshot["chain_depth"] < 0
            or len(str(snapshot["merge_sha"])) != 40
            or not str(snapshot["source_run_id"]).isdigit()
            or snapshot_digest(snapshot) != snapshot["sha256"]
        ):
            blockers.append(f"{case['case_id']}: invalid production snapshot or digest")
    return cases, blockers
