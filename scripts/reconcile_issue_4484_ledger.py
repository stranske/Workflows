#!/usr/bin/env python3
"""Emit the bounded issue-4484 ledger correction without writing the input file.

An authorized writer must review and apply the output, then run ledger_validate.
Use --check CANDIDATE with the retained original ledger to verify that applying
the correction preserved its evidence. This does not validate Git objects.
Retained external receipts establish lint/classification, not a passing local
workflow suite or a consumer merge.
"""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

import yaml

RECEIPT_COMMIT = "a0547eff1150b59ca8009a226c1dfca3d4f6118b"
CONSUMER_HEAD = "58dc10da4b4f7f11e283a9a49c34084b3e258f59"


def _same_evidence(expected: object, candidate: object) -> bool:
    """Compare YAML values without equating booleans and numeric evidence."""
    if type(expected) is not type(candidate):
        return False
    if isinstance(expected, dict) and isinstance(candidate, dict):
        return len(expected) == len(candidate) and all(
            any(
                _same_evidence(key, other_key) and _same_evidence(value, other_value)
                for other_key, other_value in candidate.items()
            )
            for key, value in expected.items()
        )
    if isinstance(expected, list) and isinstance(candidate, list):
        return len(expected) == len(candidate) and all(
            _same_evidence(value, other) for value, other in zip(expected, candidate, strict=True)
        )
    return expected == candidate


def reconcile_ledger(original: dict) -> dict:
    """Preserve original records while reconciling the four requested tasks."""
    if original.get("version") != 1 or original.get("issue") != 4484:
        raise ValueError("expected the version-1 issue-4484 ledger")
    result = copy.deepcopy(original)
    tasks = result["tasks"]
    by_id = {task["id"]: task for task in tasks}
    if len(by_id) != len(tasks):
        raise ValueError("duplicate task IDs")
    required = {"task-02", "task-03", "task-04", "task-05", "task-09", "task-11"}
    if not required <= by_id.keys():
        raise ValueError("expected the original, unconsolidated task records")

    for target_id, fragment_id, title in (
        (
            "task-02",
            "task-03",
            "Locate the authoritative upstream sources for scripts/langchain/_llm_client.py "
            "and scripts/langchain/pr_verifier.py in the sync manifest.",
        ),
        (
            "task-04",
            "task-05",
            "Fix the ARG002 unused config argument near line 40 of _llm_client.py "
            "by using it or marking it intentionally unused.",
        ),
    ):
        target, fragment = by_id[target_id], by_id[fragment_id]
        if target["status"] != "done" or fragment["status"] != "done":
            raise ValueError("consolidation requires both original tasks to be done")
        target["consolidated_from"] = [copy.deepcopy(target), copy.deepcopy(fragment)]
        target["title"] = title
        target["notes"] = target.get("notes", []) + fragment.get("notes", [])
        tasks.remove(fragment)

    lint = by_id["task-09"]
    lint["previous_evidence"] = copy.deepcopy(lint)
    lint.update(
        title="Verify regenerated consumer lint and the documented local workflow suite.",
        status="blocked",
        started_at=None,
        finished_at=None,
        commit="",
        notes=[
            "Retained verified receipt: Travel-Plan-Permission run 42325500360 completed "
            f"successfully at head {CONSUMER_HEAD}; Python CI / lint-ruff succeeded "
            "2026-11-07T01:44:17Z.",
            "Local workflow acceptance remains incomplete: retained exhaustive batches "
            "report 3534 passed, 3 skipped, 12 failed; the earlier incomplete suite "
            "remains UNKNOWN, not PASS.",
            "Successful consumer lint and classification do not establish consumer merge.",
            "Receipt provenance: docs/ops/issue-4484-validation.md, PR #4531 continuation.",
        ],
    )

    classification = by_id["task-11"]
    classification["previous_evidence"] = copy.deepcopy(classification)
    classification.update(
        status="done",
        started_at="2026-11-07T01:46:54Z",
        finished_at="2026-11-07T01:47:11Z",
        commit=RECEIPT_COMMIT,
        notes=[
            f"Retained completed round 20261107T014654Z at head {CONSUMER_HEAD}: "
            "Travel-Plan-Permission#1716 is waiting, owner ci, no handoffs, only "
            "delivery_sealed_checks_pending; the issue-4484 shipment finding is absent.",
            "Maint 71 report 42325528409 binds the same head and source "
            "75d4c8360c7a31db51366ca08d736cf4be1bc894.",
            "Successful consumer lint and classification do not establish consumer merge.",
            "Receipt provenance: docs/ops/issue-4484-validation.md, PR #4531 continuation.",
        ],
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument(
        "--check",
        type=Path,
        metavar="CANDIDATE",
        help="check candidate YAML against the correction derived from the original ledger",
    )
    args = parser.parse_args(argv)
    try:
        corrected = reconcile_ledger(yaml.safe_load(args.ledger.read_text(encoding="utf-8")))
        if args.check is not None:
            candidate = yaml.safe_load(args.check.read_text(encoding="utf-8"))
            if not _same_evidence(corrected, candidate):
                print(
                    "Candidate does not match the evidence-preserving correction.", file=sys.stderr
                )
                return 1
            return 0
    except (OSError, KeyError, TypeError, AttributeError, ValueError, yaml.YAMLError) as exc:
        parser.error(str(exc))
    yaml.safe_dump(corrected, sys.stdout, sort_keys=False, width=100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
