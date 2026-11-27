"""Preserve reviewed approval snapshots across weekly queue regeneration.

The ledger is local review state, not a source of new approvals. Every entry must
match an item in its hash-bound original approved queue. Related or expanded
findings belong in the backlog, not in the preserved approval's scope.
"""

from __future__ import annotations

import copy
import fcntl
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


def preserve_scope_conflicts(
    result: dict[str, Any],
    ledger_path: Path,
    originals: dict[str, dict[str, Any]],
    allowed_repos: set[str],
) -> None:
    """Retain unresolved new approval snapshots independently of generated queues."""
    path = ledger_path.with_name("approval-scope-conflicts.json")
    incoming = result.get("approval_scope_conflicts", [])
    if not incoming and not path.exists():
        return
    with path.with_suffix(".lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Approval conflict store has a live writer; retry later") from exc
        before = path.read_bytes() if path.exists() else None
        store = (
            json.loads(before)
            if before is not None
            else {"schema": "repo-review-approval-scope-conflicts/v1", "entries": []}
        )
        if store.get("schema") != "repo-review-approval-scope-conflicts/v1" or not isinstance(
            store.get("entries"), list
        ):
            raise ValueError("Invalid persistent approval conflict store")
        records = store["entries"]
        by_id = {}
        for conflict in records:
            issue = conflict.get("current_approved_issue", {})
            # Retained history must validate even while its repository is paused.
            original = originals.get(conflict.get("finding_id"))
            current_digest = item_digest(issue)
            if (
                original is None
                or conflict.get("current_approved_item_sha256") != current_digest
                or conflict.get("original_approved_item_sha256") != item_digest(original)
            ):
                raise ValueError("Persistent approval conflict snapshot digest differs")
            key = (conflict["finding_id"], current_digest)
            if key in by_id:
                raise ValueError("Duplicate persistent approval conflict snapshot")
            disposition = conflict.get("disposition")
            if disposition not in {"reconciliation_required", "resolved", "superseded"}:
                raise ValueError("Invalid approval conflict disposition")
            if disposition in {"resolved", "superseded"} and not conflict.get("resolution", {}).get(
                "authority"
            ):
                raise ValueError("Resolved approval conflict lacks explicit resolution authority")
            if disposition == "resolved" and conflict["resolution"].get(
                "accepted_item_sha256"
            ) not in {conflict["original_approved_item_sha256"], current_digest}:
                raise ValueError(
                    "Resolved approval conflict requires an explicit accepted snapshot digest"
                )
            by_id[key] = conflict
        for key, record in by_id.items():
            seen = {key}
            while record["disposition"] == "superseded":
                target = (key[0], record.get("resolution", {}).get("superseded_by_item_sha256"))
                if target in seen or target not in by_id:
                    raise ValueError(
                        "Approval supersession must reference an existing snapshot without cycles"
                    )
                seen.add(target)
                record = by_id[target]
        changed = False
        for conflict in incoming:
            key = (conflict["finding_id"], conflict["current_approved_item_sha256"])
            if key not in by_id:
                saved = copy.deepcopy(conflict)
                records.append(saved)
                by_id[key] = saved
                changed = True
        unresolved = [
            copy.deepcopy(record)
            for record in by_id.values()
            if record["disposition"] == "reconciliation_required"
            and record["current_approved_issue"].get("repo") in allowed_repos
        ]
        accepted = {}
        for record in by_id.values():
            if record["disposition"] != "resolved":
                continue
            identity = record["finding_id"]
            digest = record["resolution"]["accepted_item_sha256"]
            if identity in accepted and accepted[identity][0] != digest:
                raise ValueError("Conflicting accepted approval snapshots require reconciliation")
            accepted[identity] = (digest, record)
        if changed:
            if (path.read_bytes() if path.exists() else None) != before:
                raise ValueError("Approval conflict store changed concurrently; retry")
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(store, indent=2) + "\n", encoding="utf-8")
            temporary.replace(path)
        for identity, (digest, record) in accepted.items():
            if record["current_approved_issue"].get("repo") not in allowed_repos:
                continue
            if digest == record["original_approved_item_sha256"]:
                continue
            result["issues"] = [
                item
                for item in result["issues"]
                if finding_id(item["repo"], item["title"]) != identity
            ]
            item = copy.deepcopy(record["current_approved_issue"])
            item.update(
                finding_id=identity,
                approval_source={
                    "item_sha256": digest,
                    "authority": record["resolution"]["authority"],
                    "conflict_store": str(path),
                },
                materialization_status="unfiled",
            )
            result["issues"].append(item)
        result["approval_scope_conflicts"] = unresolved
        result["approval_scope_conflict_store"] = str(path)
        for conflict in unresolved:
            issue = conflict["current_approved_issue"]
            message = (
                f"{issue['repo']}: approved same-title scope '{issue['title']}' "
                "remains preserved in the persistent conflict store for reconciliation."
            )
            if message not in result.setdefault("warnings", []):
                result["warnings"].append(message)


def merge_approval_ledger(
    queue: dict[str, Any], ledger_path: Path, *, allowed_repos: set[str]
) -> dict[str, Any]:
    """Restore unfiled approvals; never requeue filed/unknown items or widen scope."""
    if not ledger_path.exists():
        if any(
            (ledger_path.parent / name).exists()
            for name in ("approval-scope-conflicts.json", "reconciled-backlog.json")
        ):
            raise ValueError(
                "Approval ledger is missing from existing reconciliation state; restore it before regeneration"
            )
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
    result["issues"] = [*preserved.values(), *current]
    result["approval_ledger"] = {"schema": SCHEMA, "source": str(ledger_path), "counts": counts}
    hold = ledger.get("intake_hold")
    if not isinstance(hold, dict) or not isinstance(hold.get("active"), bool):
        raise ValueError("Approval ledger requires an explicit intake hold state")
    result["intake_hold"] = copy.deepcopy(hold)
    preserve_scope_conflicts(result, ledger_path, originals, allowed_repos)
    result["issues"].sort(
        key=lambda item: (
            item.get("priority_rank", 1),
            item["repo"].lower(),
            item.get("candidate_index", 0),
        )
    )
    result["upload_allowed"] = not (hold["active"] or result.get("approval_scope_conflicts"))
    if result.get("approval_scope_conflicts"):
        result["materialization_hold_reason"] = "unresolved_approval_scope_conflicts"
    if not result["upload_allowed"]:
        # Older consumers only inspect issues and may ignore new hold metadata.
        # Preserve approvals separately while exposing no materializable work.
        result["held_approved_issues"] = result["issues"]
        result["issues"] = []
    return result
