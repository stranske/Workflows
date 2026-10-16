"""Preserve reviewed approval snapshots across weekly queue regeneration.

The ledger is local review state, not a source of new approvals. Every entry must
match an item in its hash-bound original approved queue. Related or expanded
findings belong in the backlog, not in the preserved approval's scope.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "repo-review-approval-ledger/v1"


def finding_id(repo: str, title: str) -> str:
    normalized = re.sub(r"\s+", " ", title.strip().lower())
    return f"{repo}#{hashlib.sha256(f'{repo}\x00{normalized}'.encode()).hexdigest()[:12]}"


def item_digest(item: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(item, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def scope_digest(item: dict[str, Any]) -> str:
    return item_digest(
        {key: item.get(key) for key in ("body", "review_evidence_trace", "priority", "labels")}
    )


def merge_approval_ledger(
    queue: dict[str, Any], ledger_path: Path, *, allowed_repos: set[str]
) -> dict[str, Any]:
    """Restore unfiled approvals; never requeue filed/unknown items or widen scope."""
    if not ledger_path.exists():
        return queue
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if ledger.get("schema") != SCHEMA:
        raise ValueError("Unsupported repo-review approval ledger schema")
    source_path = Path(ledger["source_queue_path"])
    if not source_path.is_absolute():
        source_path = ledger_path.parent / source_path
    raw = source_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ledger.get("source_queue_sha256"):
        raise ValueError("Original approved queue digest differs from approval ledger")
    source = json.loads(raw)["issues"]
    originals = {finding_id(item["repo"], item["title"]): item for item in source}
    if len(originals) != len(source):
        raise ValueError("Original approved queue contains duplicate finding identities")
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        raise ValueError("Approval ledger entries must be a list")
    result = copy.deepcopy(queue)
    identities: set[str] = set()
    preserved: dict[str, dict[str, Any]] = {}
    suppressed: set[str] = set()
    counts = {"unfiled": 0, "filed": 0, "unknown": 0}
    for entry in entries:
        if entry.get("repo") not in allowed_repos:
            continue
        identity = entry.get("finding_id")
        original = originals.get(identity)
        if (
            original is None
            or entry.get("repo") != original["repo"]
            or entry.get("title") != original["title"]
            or entry.get("approved_item_sha256") != item_digest(original)
            or identity in identities
        ):
            raise ValueError("Approval ledger entry does not match its original approved item")
        identities.add(identity)
        filing = entry.get("filing", {})
        status = filing.get("status")
        if status not in counts:
            raise ValueError("Approval ledger filing status must be filed, unfiled or unknown")
        if status == "filed" and not filing.get("issues"):
            raise ValueError("Filed ledger entry lacks issue evidence")
        if status == "unfiled" and filing.get("issues"):
            raise ValueError("Unfiled ledger entry contains conflicting filing evidence")
        counts[status] += 1
        suppressed.add(identity)
        if status != "unfiled":
            continue
        # Keep the authorized body, evidence, priority and title byte-for-byte.
        item = copy.deepcopy(original)
        item.update(
            finding_id=identity,
            approval_source={
                "queue_sha256": ledger["source_queue_sha256"],
                "item_sha256": entry["approved_item_sha256"],
                "authority": ledger["authority"],
                "cycle": ledger["source_cycle"],
            },
            materialization_status="unfiled",
        )
        preserved[identity] = item
    expected = {identity for identity, item in originals.items() if item["repo"] in allowed_repos}
    if identities != expected:
        raise ValueError("Approval ledger must account for every original approved finding")
    current = []
    filing_by_id = {
        entry["finding_id"]: entry["filing"]["status"]
        for entry in entries
        if entry.get("repo") in allowed_repos
    }
    for item in result["issues"]:
        identity = finding_id(item["repo"], item["title"])
        if identity not in suppressed:
            current.append(item)
        elif scope_digest(item) != scope_digest(originals[identity]):
            # A newly authorized changed scope is not the historical finding.
            # Retain its complete approval record rather than dropping it by title.
            result.setdefault("approval_scope_conflicts", []).append(
                {
                    "finding_id": identity,
                    "original_filing_status": filing_by_id[identity],
                    "original_approved_item_sha256": item_digest(originals[identity]),
                    "current_approved_issue": copy.deepcopy(item),
                    "current_approved_item_sha256": item_digest(item),
                    "disposition": "reconciliation_required",
                }
            )
            result.setdefault("warnings", []).append(
                f"{item['repo']}: newly approved same-title scope '{item['title']}' "
                "is preserved for reconciliation with the historical approval; no scope was silently replaced."
            )
    result["issues"] = [*preserved.values(), *current]
    result["issues"].sort(
        key=lambda item: (
            item.get("priority_rank", 1),
            item["repo"].lower(),
            item.get("candidate_index", 0),
        )
    )
    result["approval_ledger"] = {"schema": SCHEMA, "source": str(ledger_path), "counts": counts}
    hold = ledger.get("intake_hold")
    if not isinstance(hold, dict) or not isinstance(hold.get("active"), bool):
        raise ValueError("Approval ledger requires an explicit intake hold state")
    result["intake_hold"] = copy.deepcopy(hold)
    result["upload_allowed"] = not hold["active"]
    if hold["active"]:
        # Older consumers only inspect issues and may ignore new hold metadata.
        # Preserve approvals separately while exposing no materializable work.
        result["held_approved_issues"] = result["issues"]
        result["issues"] = []
    return result
