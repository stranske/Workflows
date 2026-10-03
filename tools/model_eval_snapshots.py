"""Pinned production verifier inputs for small, paired MAINT-78 screens."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any


def snapshot_digest(snapshot: dict[str, Any]) -> str:
    payload = {
        key: snapshot[key]
        for key in (
            "repository",
            "pr",
            "context",
            "diff_summary",
            "chain_depth",
            "merge_sha",
            "source_run_id",
        )
    }
    # Preserve the digest of legacy snapshots while binding every new capture
    # to the full diff that production compare mode actually consumed.
    if "diff" in snapshot:
        payload["diff"] = snapshot["diff"]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def verifier_prompt(snapshot: dict[str, Any]) -> str:
    """Build the same prompt production uses, including follow-up chain depth."""
    from scripts.langchain import pr_verifier

    previous = os.environ.get("CHAIN_DEPTH")
    os.environ["CHAIN_DEPTH"] = str(snapshot["chain_depth"])
    try:
        return pr_verifier._prepare_prompt(
            snapshot["context"], snapshot.get("diff", snapshot["diff_summary"])
        )
    finally:
        if previous is None:
            os.environ.pop("CHAIN_DEPTH", None)
        else:
            os.environ["CHAIN_DEPTH"] = previous


def verifier_prompt_coverage(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Report which acceptance and changed-code sources the production prompt keeps."""
    from scripts.langchain import pr_verifier

    return pr_verifier.prompt_coverage(
        snapshot["context"], snapshot.get("diff", snapshot["diff_summary"])
    ).to_dict()


def is_complex_coverage(coverage: dict[str, Any], *, min_files: int, min_code_chars: int) -> bool:
    """A case is complex when its changed code alone overflowed the historical prefix cap."""
    return (
        int(coverage.get("files_total", 0)) >= min_files
        or int(coverage.get("code_total_chars", 0)) > min_code_chars
    )


def coverage_blockers(
    cases: list[dict[str, Any]], stage: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[str, int], list[str]]:
    """No-spend preflight: paid confirmation needs complete, complex PASS and NON_PASS inputs."""
    min_files = int(stage.get("complex_case_min_files", 5))
    min_code_chars = int(stage.get("complex_case_min_code_chars", 8000))
    required = {
        "PASS": int(stage.get("minimum_complex_pass_cases", 1)),
        "NON_PASS": int(stage.get("minimum_complex_non_pass_cases", 1)),
    }
    coverage: dict[str, dict[str, Any]] = {}
    counts = {"PASS": 0, "NON_PASS": 0}
    blockers: list[str] = []
    for case in cases:
        snapshot = case.get("production_snapshot")
        if not isinstance(snapshot, dict) or not snapshot.get("context"):
            continue
        report = verifier_prompt_coverage(snapshot)
        report["complex"] = is_complex_coverage(
            report, min_files=min_files, min_code_chars=min_code_chars
        )
        coverage[case["case_id"]] = report
        if not report["sufficient"]:
            blockers.append(
                f"{case['case_id']}: production verifier prompt coverage is incomplete "
                f"({'; '.join(report['reasons'])})"
            )
        elif report["complex"] and case.get("expected_verdict") in counts:
            counts[case["expected_verdict"]] += 1
    for verdict, minimum in required.items():
        if counts[verdict] < minimum:
            blockers.append(
                f"Screen has {counts[verdict]} complex {verdict} case(s) with complete prompt "
                f"coverage; paid confirmation requires {minimum} (complex = at least "
                f"{min_files} changed files or more than {min_code_chars} changed-code characters)."
            )
    return coverage, counts, blockers


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
    lookup = {case["case_id"]: case for case in corpus.get("screen_cases", [])}
    if any(case_id not in lookup for case_id in ids):
        return [], ["A screen case ID is absent from the separately adjudicated screen cases."]
    cases = [lookup[case_id] for case_id in ids]
    non_pass = sum(case["expected_verdict"] == "NON_PASS" for case in cases)
    pass_count = sum(case["expected_verdict"] == "PASS" for case in cases)
    blockers = []
    seen_digests = set()
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
            "repository",
            "pr",
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
            or snapshot["repository"] != case.get("repo")
            or type(snapshot["pr"]) is not int
            or snapshot["pr"] != case.get("pr")
            or not snapshot["adjudication_evidence"]
            or not snapshot["adjudicated_by"]
            or not snapshot["adjudication_rationale"]
            or snapshot["input_kind"]
            not in {"production_capture", "retrospective_capture", "controlled_defect"}
            or (snapshot["input_kind"] == "controlled_defect" and not snapshot.get("mutation_note"))
            or (
                snapshot["input_kind"] == "controlled_defect"
                and case["expected_verdict"] != "NON_PASS"
            )
            or type(snapshot["chain_depth"]) is not int
            or snapshot["chain_depth"] < 0
            or len(str(snapshot["merge_sha"])) != 40
            or not str(snapshot["source_run_id"]).isdigit()
            or snapshot_digest(snapshot) != snapshot["sha256"]
        ):
            blockers.append(f"{case['case_id']}: invalid production snapshot or digest")
            continue
        if snapshot["sha256"] in seen_digests:
            blockers.append(f"{case['case_id']}: duplicate verifier prompt snapshot")
        seen_digests.add(snapshot["sha256"])
    return cases, blockers
