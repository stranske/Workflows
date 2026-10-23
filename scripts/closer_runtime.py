#!/usr/bin/env python3
"""Portable closer-operation/v1 contract, local store, and basic runner.

Workflows-owned contract for durable merge/verify operations with explicit executor
identity (distinct from keepalive authority version-2 GitHub run attempts).
No Orchestrator imports; shipped schema validation uses jsonschema. GitHub Contents CAS adapters consume the
same record shape via separate transports (see docs/closer-operation/).
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import fcntl
import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

CONTRACT = "closer-operation/v1"
HEAD_RE = __import__("re").compile(r"^[0-9a-f]{40}$")
KEY_RE = __import__("re").compile(r"^[0-9a-f]{64}$")

ExecutorKind = Literal["github_actions_run", "portable_local", "orchestrator_local"]
TerminalStatus = Literal["succeeded", "denied", "unavailable", "uncertain"]
ActiveStatus = Literal["claimed", "intent_recorded", "submitted"]
OperationStatus = ActiveStatus | TerminalStatus

ACTIVE_STATUSES = frozenset({"claimed", "intent_recorded", "submitted", "uncertain"})

RUNTIME_AC_LABELS = frozenset(
    {
        "runtime-ac",
        "runtime-verification",
        "acceptance-criteria",
        "verification-spec",
        "verification-plan",
        "ac-checks",
        "runtime-checks",
    }
)

BOUNDED_ACTIONS = frozenset(
    {
        "record_evidence",
        "verify_unchanged_gate",
        "verify_expected_checks",
        "execute_local_verification",
        "reconcile_submitted",
    }
)

ALLOWED_VERIFICATION_ADAPTERS = frozenset({"expected_check_topology"})
DEFAULT_VERIFICATION_CONTEXT = ("pull_request", "synchronize")
# Fixed transport allowlist for GitHub reads performed by fixed producers: GET only.


class CloserRuntimeError(Exception):
    """Base error for contract or store violations."""


class CasConflict(CloserRuntimeError):
    """Compare-and-swap revision mismatch."""


class OwnershipDenied(CloserRuntimeError):
    """Another executor holds the lease or head/criteria no longer match."""


class PolicyDenied(CloserRuntimeError):
    """Permission or policy denial; must not fallback to another channel."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.no_fallback = True


@dataclasses.dataclass(frozen=True)
class OperationSpec:
    repository: str
    pr_number: int
    action: Literal["merge", "verify", "verify_request", "reconcile"]
    head_sha: str
    base_sha: str | None
    criteria_fingerprint: str
    review_revision: str
    guard_versions: Mapping[str, Any]
    required_capabilities: Sequence[str] = ()
    blocking_labels: Sequence[str] = ()
    # Exact producer event context the verification is bound to. Part of the
    # operation identity, so a caller cannot pick a convenient context later.
    verification_event: str | None = None
    verification_event_action: str | None = None

    def verification_context(self) -> tuple[str, str]:
        if self.verification_event is None and self.verification_event_action is None:
            return DEFAULT_VERIFICATION_CONTEXT
        return (str(self.verification_event), str(self.verification_event_action))

    def target_payload(self) -> dict[str, Any]:
        return {
            "contract": CONTRACT,
            "repository": self.repository.lower(),
            "target": {"kind": "pull_request", "number": self.pr_number},
            "action": self.action,
        }

    def canonical_payload(self) -> dict[str, Any]:
        bound: dict[str, Any] = {}
        if self.verification_event is not None or self.verification_event_action is not None:
            event, action = self.verification_context()
            bound = {"verification_context": {"event": event, "action": action}}
        return {
            **bound,
            **self.target_payload(),
            "head_sha": self.head_sha,
            "base_sha": self.base_sha,
            "criteria_fingerprint": self.criteria_fingerprint,
            "review_revision": self.review_revision,
            "guard_versions": dict(sorted(self.guard_versions.items())),
            "required_capabilities": sorted(self.required_capabilities),
            "blocking_labels": sorted(label.strip().lower() for label in self.blocking_labels),
        }


def _hash_canonical(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def canonical_target_fence_key(spec: OperationSpec) -> str:
    """Ownership fence: repo + PR + action (not head/criteria)."""
    payload = {**spec.target_payload(), "fence": "target-action-v1"}
    # Older Runtime pins used verify for request dispatch. Keep one atomic CAS
    # boundary across that upgrade while operation identities/producers remain distinct.
    if spec.action == "verify_request":
        payload["action"] = "verify"
    return _hash_canonical(payload)


def canonical_operation_key(spec: OperationSpec) -> str:
    """Per-revision evidence id (includes head/criteria/review)."""
    return _hash_canonical(spec.canonical_payload())


def store_key_for_spec(spec: OperationSpec) -> str:
    return canonical_target_fence_key(spec)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(microsecond=0)


def _iso_z(when: dt.datetime) -> str:
    return when.isoformat().replace("+00:00", "Z")


def _parse_iso_z(value: str) -> dt.datetime:
    text = value.replace("Z", "+00:00")
    return dt.datetime.fromisoformat(text).astimezone(dt.UTC).replace(microsecond=0)


def runtime_ac_requirement(labels: Sequence[str]) -> tuple[bool, list[str]]:
    matched: list[str] = []
    seen: set[str] = set()
    for raw in labels:
        normalized = raw.strip().lower()
        if not normalized:
            continue
        colon = normalized.find(":")
        suffix = (
            normalized[colon + 1 :].strip() if colon >= 0 and colon < len(normalized) - 1 else ""
        )
        hit = normalized in RUNTIME_AC_LABELS or (suffix and suffix in RUNTIME_AC_LABELS)
        if hit and normalized not in seen:
            matched.append(normalized)
            seen.add(normalized)
    return bool(matched), matched


def native_runtime_ac_authorized(record: Mapping[str, Any], spec: OperationSpec) -> bool:
    """Core cannot grant native runtime AC from caller-supplied receipts."""
    # Core has no independent runtime authorization authority. Receipts are data.
    return False


def basic_runner_blocks_merge(
    spec: OperationSpec,
    executor_kind: ExecutorKind,
    *,
    record: Mapping[str, Any],
) -> PolicyDenied | None:
    """Preserve runtime-AC merge barrier: basic portable runner cannot merge."""
    if spec.action != "merge":
        return None
    required, labels = runtime_ac_requirement(spec.blocking_labels)
    if not required:
        return None
    if executor_kind == "orchestrator_local" and native_runtime_ac_authorized(record, spec):
        return None
    return PolicyDenied(
        "runtime_ac_merge_blocked: "
        f"label(s) {', '.join(labels)} require local Orchestrator runtime acceptance; "
        f"executor_kind={executor_kind} cannot authorize merge"
    )


def verification_fingerprint(head_sha: str, criteria_fingerprint: str, review_revision: str) -> str:
    payload = {
        "head_sha": head_sha,
        "criteria_fingerprint": criteria_fingerprint,
        "review_revision": review_revision,
        "contract": CONTRACT,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def should_skip_unchanged_verification(prior: str | None, current: str) -> bool:
    return prior is not None and prior == current


def verification_receipt_matches(
    receipt: Mapping[str, Any],
    *,
    fingerprint: str,
    adapter_id: str,
    result_digest: str,
) -> bool:
    return (
        receipt.get("kind") == "local_verification"
        and receipt.get("passed") is True
        and receipt.get("fingerprint") == fingerprint
        and receipt.get("adapter") == adapter_id
        and receipt.get("result_digest") == result_digest
    )


def _load_producer() -> Any:
    try:
        from scripts import check_checks_reported as producer
    except ModuleNotFoundError:
        import check_checks_reported as producer
    return producer


def fetch_live_pr_labels(spec: OperationSpec) -> list[str]:
    """Fresh PR labels via the fixed read-only producer (GET only), bound to the head.

    Any failure raises PolicyDenied: a merge cannot proceed on labels that cannot be read.
    """
    producer = _load_producer()
    try:
        pr = producer.Evidence(producer.native_gh_pages).one(
            f"repos/{spec.repository}/pulls/{spec.pr_number}"
        )
    except (Exception, SystemExit) as exc:
        raise PolicyDenied(f"live_labels_unavailable: {exc}") from exc
    if (pr.get("head") or {}).get("sha") != spec.head_sha:
        raise PolicyDenied("live_labels_unavailable: live PR head differs from the operation")
    labels = pr.get("labels")
    if not isinstance(labels, list):
        raise PolicyDenied("live_labels_unavailable: PR labels not readable")
    return [str(item.get("name", "")) for item in labels if isinstance(item, dict)]


def spec_with_live_labels(spec: OperationSpec) -> OperationSpec:
    """Union caller labels with fresh PR labels; labels can only add blocks."""
    if spec.action != "merge":
        return spec
    live = fetch_live_pr_labels(spec)
    return dataclasses.replace(spec, blocking_labels=[*spec.blocking_labels, *live])


def merge_block(
    spec: OperationSpec, executor_kind: ExecutorKind, record: Mapping[str, Any]
) -> PolicyDenied | None:
    """Runtime-AC barrier from caller labels, then from fresh live PR labels (fail closed)."""
    block = basic_runner_blocks_merge(spec, executor_kind, record=record)
    if block is not None or spec.action != "merge":
        return block
    return basic_runner_blocks_merge(spec_with_live_labels(spec), executor_kind, record=record)


def run_verification_adapter(
    adapter_id: str, spec: OperationSpec, payload: Mapping[str, Any]
) -> dict[str, Any]:
    if adapter_id not in ALLOWED_VERIFICATION_ADAPTERS:
        raise PolicyDenied(f"verification_adapter_denied: {adapter_id!r} not allowlisted")
    producer = _load_producer()
    event, action = spec.verification_context()
    for field, bound in (("event", event), ("event_action", action)):
        if field in payload and str(payload[field]) != bound:
            raise PolicyDenied(
                f"verification_context_mismatch: payload {field}={payload[field]!r} "
                f"differs from the operation-bound {bound!r}"
            )
    source_paths = [
        Path(producer.__file__),
        Path(producer.__file__).with_name("reusable_ci_scope.py"),
    ]
    sources = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    evidence = producer.Evidence(producer.native_gh_pages)
    try:
        producer.validate_event_context(event, action)
        # Records use lowercase identities; existing producer provenance uses
        # GitHub's canonical display spelling (including status URL bindings).
        repository = evidence.one(f"repos/{spec.repository}").get("full_name")
        if not isinstance(repository, str) or repository.lower() != spec.repository.lower():
            raise producer.UnknownEvidence("repository identity does not match operation")
        result = producer.collect(
            evidence, repository, spec.pr_number, spec.head_sha, event, action
        )
    except (Exception, SystemExit) as exc:
        result = {
            "verdict": "UNKNOWN",
            "unknown": [str(exc)],
            "request_evidence": evidence.requests,
        }
    if any(hashlib.sha256(p.read_bytes()).hexdigest() != sources[p.name] for p in source_paths):
        result = {"verdict": "UNKNOWN", "unknown": ["producer source changed"]}
    if result.get("verdict") == "PASS" and (
        result.get("schema") != "expected-check-receipt/v1"
        or str(result.get("repository", "")).lower() != spec.repository.lower()
        or result.get("pr") != spec.pr_number
        or result.get("head") != spec.head_sha
        or (spec.base_sha is not None and result.get("base") != spec.base_sha)
        or result.get("event") != event
        or result.get("action") != action
        or not result.get("request_evidence")
    ):
        result = {
            **result,
            "verdict": "UNKNOWN",
            "unknown": ["producer context does not match operation"],
        }
    material = {
        "adapter": adapter_id,
        "head_sha": spec.head_sha,
        "criteria_fingerprint": spec.criteria_fingerprint,
        "review_revision": spec.review_revision,
        "event": event,
        "event_action": action,
        "source": sources,
        "producer_result": result,
        "verdict": result.get("verdict", "UNKNOWN"),
    }
    return {
        **material,
        "result_digest": _hash_canonical(material),
        "passed": result.get("verdict") == "PASS" and not result.get("unknown"),
    }


@dataclasses.dataclass(frozen=True)
class ExecutorIdentity:
    kind: ExecutorKind
    identity: str

    def matches_record(self, record: Mapping[str, Any]) -> bool:
        ex = record.get("executor") or {}
        return ex.get("kind") == self.kind and ex.get("identity") == self.identity


def new_operation_record(
    spec: OperationSpec,
    executor: ExecutorIdentity,
    *,
    lease_deadline: dt.datetime,
    epoch: int = 1,
    revision: int = 1,
) -> dict[str, Any]:
    fence = canonical_target_fence_key(spec)
    key = canonical_operation_key(spec)
    bound_context = (
        {
            "verification_context": dict(
                zip(("event", "action"), spec.verification_context(), strict=True)
            )
        }
        if spec.verification_event is not None or spec.verification_event_action is not None
        else {}
    )
    return {
        **bound_context,
        "contract": CONTRACT,
        "target_fence_key": fence,
        "operation_key": key,
        "repository": spec.repository.lower(),
        "target": {"kind": "pull_request", "number": spec.pr_number},
        "action": spec.action,
        "head_sha": spec.head_sha,
        "base_sha": spec.base_sha,
        "criteria_fingerprint": spec.criteria_fingerprint,
        "review_revision": spec.review_revision,
        "guard_versions": dict(spec.guard_versions),
        "required_capabilities": list(spec.required_capabilities),
        "blocking_labels": list(spec.blocking_labels),
        "executor": {"kind": executor.kind, "identity": executor.identity},
        "lease": {
            "epoch": epoch,
            "revision": revision,
            "deadline": _iso_z(lease_deadline),
            "owner_ack": True,
        },
        "status": "claimed",
        "ownership_scope": "execute",
        "mutation_intent": None,
        "receipts": [],
        "denial": None,
        "last_verification_fingerprint": None,
    }


def validate_operation_record(record: Mapping[str, Any]) -> list[str]:
    """Validate the shipped schema and recompute both identity boundaries."""
    from jsonschema import Draft202012Validator, FormatChecker

    schema_path = (
        Path(__file__).resolve().parents[1] / "fixtures/closer-operation/v1/operation.schema.json"
    )
    validator = Draft202012Validator(
        json.loads(schema_path.read_text()), format_checker=FormatChecker()
    )
    errors = [f"{'.'.join(map(str, e.path))}: {e.message}" for e in validator.iter_errors(record)]
    if errors:
        return errors
    try:
        deadline = dt.datetime.fromisoformat(record["lease"]["deadline"].replace("Z", "+00:00"))
        if deadline.tzinfo is None:
            errors.append("lease.deadline must include a timezone")
    except ValueError:
        errors.append("lease.deadline must be an ISO timestamp")
    spec = spec_from_record(record)
    if record["operation_key"] != canonical_operation_key(spec):
        errors.append("operation_key does not match canonical spec")
    if record["target_fence_key"] != canonical_target_fence_key(spec):
        errors.append("target_fence_key does not match canonical target/action")
    if record["status"] == "denied" and not (record.get("denial") or {}).get("no_fallback"):
        errors.append("denied operations must set denial.no_fallback")
    for entry in record.get("prior_operations") or []:
        prior = entry["record"]
        if prior.get("prior_operations"):
            errors.append("prior operation history must be flat")
            continue
        if _hash_canonical(prior) != entry["sha256"]:
            errors.append("prior operation digest does not match preserved bytes")
        if prior.get("target_fence_key") != record["target_fence_key"]:
            errors.append("prior operation belongs to another target/action")
        errors.extend(f"prior operation: {error}" for error in validate_operation_record(prior))
    return errors


def spec_from_record(record: Mapping[str, Any]) -> OperationSpec:
    return OperationSpec(
        record["repository"],
        record["target"]["number"],
        record["action"],
        record["head_sha"],
        record.get("base_sha"),
        record["criteria_fingerprint"],
        record["review_revision"],
        record["guard_versions"],
        record.get("required_capabilities", ()),
        record.get("blocking_labels", ()),
        (record.get("verification_context") or {}).get("event"),
        (record.get("verification_context") or {}).get("action"),
    )


def validate_store_record(store_key: str, record: Mapping[str, Any]) -> None:
    errors = validate_operation_record(record)
    if errors:
        raise CloserRuntimeError("invalid operation record: " + "; ".join(errors))
    if record["target_fence_key"] != store_key:
        raise CloserRuntimeError("store key differs from target fence")


WritePurpose = Literal["claim", "owner_update", "transfer", "read_only_recovery"]

IMMUTABLE_FIELDS = (
    "contract",
    "target_fence_key",
    "operation_key",
    "repository",
    "target",
    "action",
    "head_sha",
    "base_sha",
    "criteria_fingerprint",
    "review_revision",
    "guard_versions",
    "required_capabilities",
    "blocking_labels",
    "verification_context",
)

OWNER_STATUS_TRANSITIONS = {
    "claimed": {"claimed", "intent_recorded", "denied", "unavailable", "uncertain"},
    "intent_recorded": {"intent_recorded", "submitted", "denied", "uncertain"},
    "submitted": {"submitted", "uncertain", "succeeded", "denied"},
    "uncertain": {"uncertain", "succeeded", "denied"},
    "succeeded": {"succeeded"},
    "denied": {"denied"},
    "unavailable": {"unavailable"},
}
UNKNOWN_STATUSES = ("intent_recorded", "submitted", "uncertain")


@dataclasses.dataclass(frozen=True)
class WriteAuthority:
    """Who is writing, at which epoch, and why. Required by every store write.

    Supported portable contract: every public mutation path goes through a store write
    that validates this against the stored record (owner, live lease, epoch, immutable
    fields, append-only history). A process that holds the store credentials can still
    forge records by bypassing this module; Python cannot prevent that and no security
    boundary is claimed against a malicious credential holder.
    """

    purpose: WritePurpose
    writer: ExecutorIdentity
    expected_epoch: int | None
    # Read-only replacement of a claimed, no-intent operation must be acknowledged.
    acknowledge_replacement: bool = False
    now: dt.datetime | None = None


def lease_expired(record: Mapping[str, Any], *, now: dt.datetime | None = None) -> bool:
    deadline = (record.get("lease") or {}).get("deadline")
    return not isinstance(deadline, str) or (now or _utc_now()) >= _parse_iso_z(deadline)


def _reconciliation_receipt_ok(record: Mapping[str, Any], receipt: Mapping[str, Any]) -> bool:
    return (
        receipt.get("kind") == "reconciliation"
        and receipt.get("operation_key") == record["operation_key"]
        and receipt.get("target_fence_key") == record["target_fence_key"]
        and receipt.get("action") == record["action"]
        and receipt.get("head_sha") == record["head_sha"]
        and bool(receipt.get("source"))
        and bool(KEY_RE.fullmatch(str(receipt.get("observation_digest", ""))))
        and receipt.get("result") in {"desired_result_observed", "not_observed", "unknown"}
    )


@dataclasses.dataclass(frozen=True)
class VerificationRequestRejected:
    """Synchronous dispatch rejection, never inferred from missing run evidence."""

    mutation_kind: Literal["workflow_dispatch"]
    request_basis: str
    http_status: Literal[422]


def _request_rejection_ok(record: Mapping[str, Any], receipt: Mapping[str, Any]) -> bool:
    intent = record.get("mutation_intent") or {}
    binding = intent.get("native_binding")
    if not isinstance(binding, Mapping):
        return False
    mutation = binding.get("verification_mutation")
    return (
        record["action"] == "verify_request"
        and intent.get("action") == "verify_request"
        and intent.get("head_sha") == record["head_sha"]
        and _hash_canonical(binding) == record["guard_versions"].get("native_binding")
        and isinstance(mutation, Mapping)
        and mutation.get("mutation_kind") == "workflow_dispatch"
        and bool(KEY_RE.fullmatch(str(mutation.get("request_basis", ""))))
        and receipt
        == {
            "kind": "verification_request_not_accepted",
            "operation_key": record["operation_key"],
            "target_fence_key": record["target_fence_key"],
            "action": record["action"],
            "head_sha": record["head_sha"],
            "mutation_kind": "workflow_dispatch",
            "request_basis": mutation["request_basis"],
            "http_status": 422,
        }
        and type(receipt.get("http_status")) is int
    )


def verification_request_not_accepted(record: Mapping[str, Any]) -> bool:
    """Validate the preserved synchronous non-acceptance receipt, without mutation."""
    receipts = record.get("receipts") or []
    return (
        record.get("status") == "unavailable"
        and bool(receipts)
        and _request_rejection_ok(record, receipts[-1])
    )


def _rejected_retry_spec(record: Mapping[str, Any], spec: OperationSpec) -> bool:
    if not verification_request_not_accepted(record):
        return False
    old = spec_from_record(record).canonical_payload()
    new = spec.canonical_payload()
    old["guard_versions"] = dict(old["guard_versions"])
    new["guard_versions"] = dict(new["guard_versions"])
    old["guard_versions"].pop("native_binding", None)
    new["guard_versions"].pop("native_binding", None)
    return old == new


def validate_cas_transition(
    current: Mapping[str, Any] | None,
    record: Mapping[str, Any],
    expected_revision: int | None,
    authority: WriteAuthority,
) -> None:
    if record["lease"]["revision"] != (1 if current is None else expected_revision + 1):
        raise CasConflict("revision must advance exactly once")
    writer_is_record_owner = authority.writer.matches_record(record)
    if current is None:
        if (
            authority.purpose != "claim"
            or not writer_is_record_owner
            or record["lease"]["epoch"] != 1
            or record["status"] != "claimed"
            or record.get("receipts")
            or record.get("mutation_intent") is not None
            or record.get("denial")
            or record.get("prior_operations")
        ):
            raise CasConflict("new record must be a clean claim by its owner at epoch one")
        return
    if authority.expected_epoch != current["lease"]["epoch"]:
        raise OwnershipDenied("stale epoch")
    if current.get("denial") and record.get("denial") != current.get("denial"):
        raise PolicyDenied("denial/no_fallback cannot be erased without independent authorization")
    if current.get("denial") and record["status"] != "denied":
        raise PolicyDenied("denial/no_fallback cannot change status")
    old_lease, new_lease = current["lease"], record["lease"]
    changed_spec = current["operation_key"] != record["operation_key"]
    retry_rejected = (
        not changed_spec
        and authority.purpose == "claim"
        and verification_request_not_accepted(current)
        and current["executor"] == record["executor"]
    )
    if changed_spec or retry_rejected:
        # A new spec replaces only a legally drained record, as a clean claimed record.
        if authority.purpose != "claim" or not writer_is_record_owner:
            raise OwnershipDenied("new spec requires a claim by its own executor")
        assert_fence_allows_claim(current, spec_from_record(record))
        if verification_request_not_accepted(current) and current["executor"] != record["executor"]:
            raise OwnershipDenied("typed rejected request retry requires the same owner")
        if current["executor"] != record["executor"] and not authority.acknowledge_replacement:
            raise OwnershipDenied("successor must acknowledge the drained operation")
        archived = {k: v for k, v in current.items() if k != "prior_operations"}
        expected_history = [
            *(current.get("prior_operations") or []),
            {"sha256": _hash_canonical(archived), "record": archived},
        ]
        if record.get("prior_operations") != expected_history:
            raise OwnershipDenied("new claim must preserve prior operation evidence")
        if (
            current["status"] not in ("succeeded", "unavailable")
            or record["status"] != "claimed"
            or record.get("receipts")
            or record.get("mutation_intent") is not None
            or new_lease["epoch"] != old_lease["epoch"] + 1
            or record.get("ownership_scope", "execute") != "execute"
        ):
            raise OwnershipDenied("spec change requires a drained record and a clean claim")
        return
    for field in IMMUTABLE_FIELDS:
        if current.get(field) != record.get(field):
            raise OwnershipDenied(f"immutable field {field!r} cannot change")
    if record.get("prior_operations") != current.get("prior_operations"):
        raise OwnershipDenied("prior operation history is immutable")
    old_receipts = list(current.get("receipts") or [])
    new_receipts = list(record.get("receipts") or [])
    if new_receipts[: len(old_receipts)] != old_receipts:
        raise OwnershipDenied("receipts are append-only")
    if (
        current.get("mutation_intent") is not None
        and record.get("mutation_intent") != current["mutation_intent"]
    ):
        raise OwnershipDenied("mutation_intent is immutable once recorded")
    old_scope = current.get("ownership_scope", "execute")
    new_scope = record.get("ownership_scope", "execute")
    if (
        old_scope == "reconcile_only"
        and new_scope != "reconcile_only"
        and (authority.purpose != "read_only_recovery" or not authority.acknowledge_replacement)
    ):
        raise OwnershipDenied("reconciliation-only scope cannot grant execution")
    changed_owner = current["executor"] != record["executor"]
    if new_lease["epoch"] != old_lease["epoch"] + int(changed_owner):
        raise CasConflict("epoch must fence owner changes")
    old_status, new_status = current["status"], record["status"]
    new_intent_status = authority.purpose == "owner_update" and new_status in (
        "intent_recorded",
        "submitted",
    )
    if new_intent_status:
        if new_scope != "execute":
            raise OwnershipDenied("reconciliation-only owner cannot submit mutations")
        block = basic_runner_blocks_merge(
            spec_from_record(record), record["executor"]["kind"], record=record
        )
        if block is not None:
            raise block
    if authority.purpose == "owner_update":
        if changed_owner or not authority.writer.matches_record(current):
            raise OwnershipDenied("owner update must come from the current owner")
        assert_active_lease(current, now=authority.now)
        if (
            old_lease["deadline"] != new_lease["deadline"]
            or old_lease["owner_ack"] != new_lease["owner_ack"]
            or old_lease.get("prior_deadlines") != new_lease.get("prior_deadlines")
            or old_scope != new_scope
        ):
            raise OwnershipDenied("owner update cannot change lease deadline/ack/scope")
        rejected = (
            old_status == "intent_recorded"
            and new_status == "unavailable"
            and old_scope == "execute"
            and len(new_receipts) == len(old_receipts) + 1
            and _request_rejection_ok(current, new_receipts[-1])
        )
        if new_status not in OWNER_STATUS_TRANSITIONS[old_status] and not rejected:
            raise OwnershipDenied("illegal operation status transition")
        if new_status == "submitted" and (
            old_status != "intent_recorded" or record.get("mutation_intent") is None
        ):
            raise OwnershipDenied("submitted requires prior recorded intent")
        if record.get("mutation_intent") != current.get("mutation_intent") and (
            old_status != "claimed" or new_status != "intent_recorded"
        ):
            raise OwnershipDenied("mutation_intent may only be set when recording intent")
        if (
            new_status == "succeeded"
            and old_status != "succeeded"
            and (
                len(new_receipts) != len(old_receipts) + 1
                or not _success_receipt_ok(record, new_receipts[-1])
            )
        ):
            raise OwnershipDenied("success requires operation-bound reconciliation receipt")
        return
    if authority.purpose == "transfer":
        if not changed_owner or not authority.writer.matches_record(current):
            raise OwnershipDenied("transfer must come from the current owner")
        assert_active_lease(current, now=authority.now)
        if (
            old_lease["deadline"] != new_lease["deadline"]
            or old_lease.get("prior_deadlines") != new_lease.get("prior_deadlines")
            or new_status != old_status
            or new_receipts != old_receipts
            or record.get("mutation_intent") != current.get("mutation_intent")
        ):
            raise OwnershipDenied("transfer cannot change lease deadline, status or evidence")
        if old_status not in ("claimed", "intent_recorded", "unavailable", *UNKNOWN_STATUSES):
            raise OwnershipDenied("terminal operation cannot transfer")
        if old_status in UNKNOWN_STATUSES and new_scope != "reconcile_only":
            raise OwnershipDenied("unknown handoff must be reconciliation-only")
        if old_scope == "reconcile_only" and new_scope != "reconcile_only":
            raise OwnershipDenied("reconciliation-only owner cannot grant execution")
        return
    if authority.purpose != "read_only_recovery" or not writer_is_record_owner:
        raise OwnershipDenied("record writer must be the claimed purpose's executor")
    if changed_owner and not lease_expired(current, now=authority.now):
        raise OwnershipDenied("live lease: recovery by a non-owner is not permitted")
    if new_lease["owner_ack"] is not True and changed_owner:
        raise OwnershipDenied("recovery owner must be acknowledged")
    lease_changed = old_lease["deadline"] != new_lease["deadline"] or old_lease.get(
        "prior_deadlines"
    ) != new_lease.get("prior_deadlines")
    if record.get("mutation_intent") != current.get("mutation_intent") or (
        lease_changed and not _is_replacement(current, record)
    ):
        raise OwnershipDenied("recovery cannot change intent or extend the lease")
    if _is_replacement(current, record):
        _validate_readonly_replacement(current, record, authority, new_receipts, old_receipts)
        return
    if old_status not in UNKNOWN_STATUSES or new_status not in ("succeeded", "uncertain", "denied"):
        raise OwnershipDenied("read-only recovery drains only unknown operations")
    if new_scope != "reconcile_only" and changed_owner:
        raise OwnershipDenied("unknown handoff must be reconciliation-only")
    if len(new_receipts) != len(old_receipts) + 1 or not _reconciliation_receipt_ok(
        record, new_receipts[-1]
    ):
        raise OwnershipDenied("recovery must append one operation-bound reconciliation receipt")
    positive = new_receipts[-1]["result"] == "desired_result_observed"
    if new_status == "succeeded" and not positive:
        raise OwnershipDenied("success requires a positive independent observation")
    if new_status != "succeeded" and positive and not current.get("denial"):
        raise OwnershipDenied("a positive observation must drain the operation")
    if old_status == "intent_recorded" and not lease_expired(current, now=authority.now):
        raise OwnershipDenied("intent_recorded is reconciled only after lease expiry")


def _success_receipt_ok(record: Mapping[str, Any], receipt: Mapping[str, Any]) -> bool:
    return (
        _reconciliation_receipt_ok(record, receipt)
        and receipt.get("result") == "desired_result_observed"
    )


def _is_replacement(current: Mapping[str, Any], record: Mapping[str, Any]) -> bool:
    return (
        current["status"] == "claimed"
        and current.get("mutation_intent") is None
        and record["status"] == "claimed"
        and record.get("ownership_scope", "execute") == "execute"
    )


def _validate_readonly_replacement(
    current: Mapping[str, Any],
    record: Mapping[str, Any],
    authority: WriteAuthority,
    new_receipts: Sequence[Any],
    old_receipts: Sequence[Any],
) -> None:
    if not authority.acknowledge_replacement:
        raise OwnershipDenied("replacement of a claimed owner must be explicitly acknowledged")
    if record["action"] in {"merge", "verify_request"}:
        raise OwnershipDenied("only read-only claimed work can be replaced without a handoff")
    if current["executor"] == record["executor"]:
        raise OwnershipDenied("replacement must name a different executor")
    old_lease, new_lease = current["lease"], record["lease"]
    old_deadline = old_lease["deadline"]
    if (
        new_receipts != old_receipts
        or new_lease["owner_ack"] is not True
        or new_lease.get("prior_deadlines")
        != [*(old_lease.get("prior_deadlines") or []), old_deadline]
        or _parse_iso_z(new_lease["deadline"]) <= (authority.now or _utc_now())
    ):
        raise OwnershipDenied("replacement must retain the old deadline in audit and set a new one")


def head_stale(record: Mapping[str, Any], current_head_sha: str) -> bool:
    return str(record.get("head_sha")) != current_head_sha


def assert_fresh_target(record: Mapping[str, Any], spec: OperationSpec) -> None:
    if str(record.get("operation_key")) != canonical_operation_key(spec):
        raise OwnershipDenied("stale operation_key (head/criteria/review) for operation")
    if head_stale(record, spec.head_sha):
        raise OwnershipDenied("stale head_sha for operation")
    if str(record.get("criteria_fingerprint")) != spec.criteria_fingerprint:
        raise OwnershipDenied("stale criteria_fingerprint for operation")
    if str(record.get("review_revision")) != spec.review_revision:
        raise OwnershipDenied("stale review_revision for operation")


def assert_active_lease(record: Mapping[str, Any], *, now: dt.datetime | None = None) -> None:
    lease = record.get("lease") or {}
    if not lease.get("owner_ack"):
        raise OwnershipDenied("lease not acknowledged")
    deadline_raw = lease.get("deadline")
    if not isinstance(deadline_raw, str):
        raise OwnershipDenied("lease deadline missing")
    when = now or _utc_now()
    if when >= _parse_iso_z(deadline_raw):
        raise OwnershipDenied("lease expired")


def enforce_owner_lease(
    record: Mapping[str, Any],
    executor: ExecutorIdentity,
    *,
    spec: OperationSpec | None = None,
    now: dt.datetime | None = None,
) -> None:
    if not executor.matches_record(record):
        raise OwnershipDenied("not operation owner")
    assert_active_lease(record, now=now)
    if spec is not None:
        assert_fresh_target(record, spec)


def assert_fence_allows_claim(existing: Mapping[str, Any], spec: OperationSpec) -> None:
    if existing.get("status") == "unavailable" and existing.get("mutation_intent") is not None:
        if not (_rejected_retry_spec(existing, spec)):
            raise OwnershipDenied("unavailable operation retains unresolved mutation intent")
    op_key = canonical_operation_key(spec)
    if existing.get("denial") or existing.get("status") == "denied":
        raise OwnershipDenied("denied/no_fallback fence requires independent authorization")
    if existing.get("operation_key") == op_key:
        return
    status = existing.get("status")
    if status in ACTIVE_STATUSES:
        raise OwnershipDenied("target fence held by unresolved operation for prior head/criteria")
    if status in ("succeeded", "denied", "unavailable"):
        return
    raise OwnershipDenied(f"cannot claim fence in status {status!r}")


class LocalOperationStore:
    """File-backed CAS store for local-only progress during GitHub outages."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, store_key: str) -> Path:
        if not KEY_RE.match(store_key):
            raise CloserRuntimeError("invalid store key")
        return self.root / f"{store_key}.json"

    def _lock_path(self, store_key: str) -> Path:
        return self.root / f"{store_key}.lock"

    @contextlib.contextmanager
    def _exclusive_lock(self, store_key: str) -> Iterator[None]:
        lock_path = self._lock_path(store_key)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _atomic_write(self, path: Path, payload: str) -> None:
        fd, tmp_name = tempfile.mkstemp(dir=self.root, prefix="cas-", suffix=".json")
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            with open(tmp_path, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
            dir_fd = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    def read(self, store_key: str) -> dict[str, Any] | None:
        path = self._path(store_key)
        if not path.is_file():
            return None
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            validate_store_record(store_key, record)
            return record
        except json.JSONDecodeError:
            raise CloserRuntimeError("corrupt operation record json") from None

    def _write_cas_unlocked(
        self,
        store_key: str,
        record: dict[str, Any],
        *,
        expected_revision: int | None,
        authority: WriteAuthority,
    ) -> dict[str, Any]:
        path = self._path(store_key)
        payload = json.dumps(record, indent=2, sort_keys=True) + "\n"
        current = None
        if path.is_file():
            current = self.read(store_key)
        cur_rev = (current or {}).get("lease", {}).get("revision")
        if expected_revision is not None and cur_rev != expected_revision:
            raise CasConflict(f"revision {cur_rev!r} != expected {expected_revision!r}")
        if current is None and expected_revision not in (None, 0):
            raise CasConflict("missing record for positive expected_revision")
        if current is not None and expected_revision is None:
            raise CasConflict("create-only operation already exists")
        validate_store_record(store_key, record)
        validate_cas_transition(current, record, expected_revision, authority)
        self._atomic_write(path, payload)
        return record

    def write_cas(
        self,
        store_key: str,
        record: dict[str, Any],
        *,
        expected_revision: int | None,
        authority: WriteAuthority,
    ) -> dict[str, Any]:
        """Guarded store write. `authority` is required: purpose, writer and epoch are
        validated against the stored record (see WriteAuthority for the contract)."""
        with self._exclusive_lock(store_key):
            return self._write_cas_unlocked(
                store_key, record, expected_revision=expected_revision, authority=authority
            )

    def claim(
        self,
        spec: OperationSpec,
        executor: ExecutorIdentity,
        *,
        lease_deadline: dt.datetime,
        acknowledge_replacement: bool = False,
    ) -> tuple[dict[str, Any], bool]:
        """Claim operation; returns (record, created). Loses race if another owner holds lease."""
        fence = store_key_for_spec(spec)
        op_key = canonical_operation_key(spec)
        with self._exclusive_lock(fence):
            existing = self.read(fence)
            if existing is None:
                rec = new_operation_record(spec, executor, lease_deadline=lease_deadline)
                try:
                    return (
                        self._write_cas_unlocked(
                            fence,
                            rec,
                            expected_revision=None,
                            authority=WriteAuthority("claim", executor, None),
                        ),
                        True,
                    )
                except CasConflict:
                    existing = self.read(fence)
            if existing is None:
                raise CasConflict("claim CAS rejected with no winning record visible")
            assert_fence_allows_claim(existing, spec)
            changed_spec = existing.get("operation_key") != op_key
            drained = existing.get("status") in ("succeeded", "unavailable")
            if not executor.matches_record(existing) and not (
                changed_spec and drained and acknowledge_replacement
            ):
                raise OwnershipDenied(
                    f"operation owned by {existing['executor']['kind']}:{existing['executor']['identity']!r}"
                )
            retry_rejected = (
                verification_request_not_accepted(existing)
                and existing.get("operation_key") == op_key
            )
            if (
                retry_rejected
                or existing.get("operation_key") != op_key
                and existing.get("status")
                in (
                    "succeeded",
                    "denied",
                    "unavailable",
                )
            ):
                lease = dict(existing["lease"])
                lease["epoch"] = int(lease.get("epoch", 1)) + 1
                lease["revision"] = int(lease.get("revision", 1)) + 1
                lease["deadline"] = _iso_z(lease_deadline)
                rec = new_operation_record(
                    spec,
                    executor,
                    lease_deadline=lease_deadline,
                    epoch=int(lease["epoch"]),
                    revision=int(lease["revision"]),
                )
                archived = {k: v for k, v in existing.items() if k != "prior_operations"}
                rec["prior_operations"] = [
                    *(existing.get("prior_operations") or []),
                    {"sha256": _hash_canonical(archived), "record": archived},
                ]
                return (
                    self._write_cas_unlocked(
                        fence,
                        rec,
                        expected_revision=existing["lease"]["revision"],
                        authority=WriteAuthority(
                            "claim",
                            executor,
                            existing["lease"]["epoch"],
                            acknowledge_replacement=acknowledge_replacement,
                        ),
                    ),
                    True,
                )
            assert_fresh_target(existing, spec)
            enforce_owner_lease(existing, executor, spec=spec)
            if existing.get("status") in ("succeeded", "denied"):
                raise OwnershipDenied(f"terminal status {existing.get('status')}")
            return existing, False


def transfer_ownership(
    store: LocalOperationStore,
    store_key: str,
    from_executor: ExecutorIdentity,
    to_executor: ExecutorIdentity,
    *,
    expected_revision: int,
    expected_epoch: int,
    spec: OperationSpec,
    to_ack: bool = True,
    reconciliation_only: bool = False,
) -> dict[str, Any]:
    record = store.read(store_key)
    if record is None:
        raise CloserRuntimeError("missing operation")
    enforce_owner_lease(record, from_executor, spec=spec)
    if record["lease"]["epoch"] != expected_epoch:
        raise OwnershipDenied("stale epoch")
    unknown = record.get("status") in UNKNOWN_STATUSES
    if unknown and not reconciliation_only:
        raise CloserRuntimeError("unknown operation permits reconciliation-only transfer")
    if not unknown and record.get("status") not in ("claimed", "unavailable"):
        raise CloserRuntimeError("terminal operation cannot transfer")
    if record.get("ownership_scope") == "reconcile_only" and not reconciliation_only:
        raise OwnershipDenied("reconciliation-only owner cannot grant execution")
    lease = dict(record["lease"])
    lease["revision"] = expected_revision + 1
    lease["epoch"] = int(lease.get("epoch", 1)) + 1
    lease["owner_ack"] = to_ack
    updated = dict(record)
    updated["executor"] = {"kind": to_executor.kind, "identity": to_executor.identity}
    updated["ownership_scope"] = "reconcile_only" if reconciliation_only else "execute"
    updated["lease"] = lease
    return store.write_cas(
        store_key,
        updated,
        expected_revision=expected_revision,
        authority=WriteAuthority("transfer", from_executor, expected_epoch),
    )


def revalidate_live_head(record: Mapping[str, Any], live_head_sha: str) -> None:
    if head_stale(record, live_head_sha):
        raise OwnershipDenied("stale head_sha for operation")


def record_mutation_intent(
    store: LocalOperationStore,
    store_key: str,
    executor: ExecutorIdentity,
    intent: Mapping[str, Any],
    *,
    expected_revision: int,
    expected_epoch: int,
    spec: OperationSpec,
    live_head_sha: str | None = None,
) -> dict[str, Any]:
    record = store.read(store_key)
    if record is None:
        raise CloserRuntimeError("missing operation")
    enforce_owner_lease(record, executor, spec=spec)
    if record["lease"]["epoch"] != expected_epoch:
        raise OwnershipDenied("stale epoch")
    if live_head_sha is not None:
        revalidate_live_head(record, live_head_sha)
    if record.get("ownership_scope") == "reconcile_only":
        raise OwnershipDenied("reconciliation-only owner cannot submit mutations")
    block = merge_block(spec, executor.kind, record)
    if block is not None:
        terminalize(
            store,
            store_key,
            "denied",
            expected_revision=expected_revision,
            expected_epoch=expected_epoch,
            executor=executor,
            spec=spec,
            denial_reason=block.reason,
        )
        raise block
    if record.get("status") not in ("claimed", "intent_recorded"):
        raise CloserRuntimeError(f"cannot record intent from status {record.get('status')}")
    history = record.get("prior_operations") or []
    if history and verification_request_not_accepted(history[-1]["record"]):
        old_binding = dict(history[-1]["record"]["mutation_intent"]["native_binding"])
        new_binding = intent.get("native_binding")
        if not isinstance(new_binding, Mapping) or _hash_canonical(
            new_binding
        ) != spec.guard_versions.get("native_binding"):
            raise OwnershipDenied("retry intent requires exact new native binding digest")
        new_binding = dict(new_binding)
        old_binding.pop("queue_operation_id", None)
        new_binding.pop("queue_operation_id", None)
        if old_binding != new_binding:
            raise OwnershipDenied("rejected request retry may change only queue operation identity")
    updated = dict(record)
    updated["mutation_intent"] = dict(intent)
    updated["status"] = "intent_recorded"
    lease = dict(updated["lease"])
    lease["revision"] = expected_revision + 1
    updated["lease"] = lease
    return store.write_cas(
        store_key,
        updated,
        expected_revision=expected_revision,
        authority=WriteAuthority("owner_update", executor, expected_epoch),
    )


def mark_submitted(
    store: LocalOperationStore,
    store_key: str,
    executor: ExecutorIdentity,
    *,
    expected_revision: int,
    expected_epoch: int,
    spec: OperationSpec,
) -> dict[str, Any]:
    record = store.read(store_key)
    if record is None:
        raise CloserRuntimeError("missing operation")
    enforce_owner_lease(record, executor, spec=spec)
    if record["lease"]["epoch"] != expected_epoch:
        raise OwnershipDenied("stale epoch")
    if record.get("ownership_scope") == "reconcile_only":
        raise OwnershipDenied("reconciliation-only owner cannot submit mutations")
    if record.get("status") != "intent_recorded":
        raise OwnershipDenied("submission requires intent_recorded; reconcile unknown before retry")
    block = merge_block(spec, executor.kind, record)
    if block is not None:
        raise block
    if record.get("mutation_intent") is None:
        raise CloserRuntimeError("mutation_intent required before submitted")
    updated = dict(record)
    updated["status"] = "submitted"
    lease = dict(updated["lease"])
    lease["revision"] = expected_revision + 1
    updated["lease"] = lease
    return store.write_cas(
        store_key,
        updated,
        expected_revision=expected_revision,
        authority=WriteAuthority("owner_update", executor, expected_epoch),
    )


def reject_not_accepted(
    store: LocalOperationStore,
    store_key: str,
    executor: ExecutorIdentity,
    evidence: VerificationRequestRejected,
    *,
    expected_revision: int,
    expected_epoch: int,
    spec: OperationSpec,
) -> dict[str, Any]:
    """Record a synchronous, exact-bound HTTP 422 without claiming desired success.

    Missing this API is an unsupported recovery boundary for older Core packages.
    A crash before this CAS remains unresolved; it never implies non-acceptance.
    """
    if not isinstance(evidence, VerificationRequestRejected):
        raise OwnershipDenied("typed verification rejection evidence required")
    record = store.read(store_key)
    if record is None:
        raise CloserRuntimeError("missing operation")
    enforce_owner_lease(record, executor, spec=spec)
    if record["lease"]["epoch"] != expected_epoch:
        raise OwnershipDenied("stale epoch")
    if record["status"] != "intent_recorded" or record.get("ownership_scope") != "execute":
        raise OwnershipDenied("rejection requires live execute-owned intent before submission")
    receipt = {
        "kind": "verification_request_not_accepted",
        "operation_key": record["operation_key"],
        "target_fence_key": record["target_fence_key"],
        "action": record["action"],
        "head_sha": record["head_sha"],
        **dataclasses.asdict(evidence),
    }
    if not _request_rejection_ok(record, receipt):
        raise OwnershipDenied("rejection is not exact-bound workflow dispatch HTTP 422")
    updated = dict(record)
    updated["status"] = "unavailable"
    updated["receipts"] = [*record["receipts"], receipt]
    updated["lease"] = {**record["lease"], "revision": expected_revision + 1}
    return store.write_cas(
        store_key,
        updated,
        expected_revision=expected_revision,
        authority=WriteAuthority("owner_update", executor, expected_epoch),
    )


def terminalize(
    store: LocalOperationStore,
    store_key: str,
    status: TerminalStatus,
    *,
    expected_revision: int,
    executor: ExecutorIdentity,
    spec: OperationSpec,
    expected_epoch: int,
    denial_reason: str | None = None,
    receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    record = store.read(store_key)
    if record is None:
        raise CloserRuntimeError("missing operation")
    enforce_owner_lease(record, executor, spec=spec)
    if status not in {"succeeded", "denied", "unavailable", "uncertain"}:
        raise CloserRuntimeError("invalid terminal status")
    if record["lease"]["epoch"] != expected_epoch:
        raise OwnershipDenied("stale epoch")
    if record["status"] in ("denied", "succeeded", "uncertain", "submitted"):
        raise OwnershipDenied("terminal/unknown state requires reconciliation")
    if status == "unavailable" and record.get("mutation_intent") is not None:
        raise OwnershipDenied("recorded mutation intent requires reconciliation")
    if status == "succeeded":
        raise PolicyDenied("success requires typed reconciliation evidence")
    updated = dict(record)
    updated["status"] = status
    lease = dict(updated["lease"])
    lease["revision"] = expected_revision + 1
    updated["lease"] = lease
    if status == "denied":
        updated["denial"] = {"reason": denial_reason or "denied", "no_fallback": True}
    if receipt:
        receipts = list(updated.get("receipts") or [])
        receipts.append(dict(receipt))
        updated["receipts"] = receipts
    return store.write_cas(
        store_key,
        updated,
        expected_revision=expected_revision,
        authority=WriteAuthority("owner_update", executor, expected_epoch),
    )


@dataclasses.dataclass(frozen=True)
class ReconciliationEvidence:
    operation_key: str
    target_fence_key: str
    head_sha: str
    action: str
    result: Literal["desired_result_observed", "not_observed", "unknown"]
    source: str
    observation_digest: str
    # Observation context retained in the receipt (verify: event/action; merge:
    # merge commit and base as read). Optional; never a verdict.
    context: str = ""

    def __post_init__(self) -> None:
        if (
            any(
                not isinstance(value, str) or (not value and name != "context")
                for name, value in dataclasses.asdict(self).items()
            )
            or not KEY_RE.fullmatch(self.operation_key)
            or not KEY_RE.fullmatch(self.target_fence_key)
            or not HEAD_RE.fullmatch(self.head_sha)
            or not KEY_RE.fullmatch(self.observation_digest)
            or self.action not in {"merge", "verify", "verify_request", "reconcile"}
            or self.result not in {"desired_result_observed", "not_observed", "unknown"}
        ):
            raise OwnershipDenied("reconciliation evidence not bound to a typed observation")


def collect_reconciliation_evidence(
    spec: OperationSpec, payload: Mapping[str, Any]
) -> ReconciliationEvidence:
    """Only fixed read-only producers may turn CLI input into an observation.

    The caller chooses event context, never the verdict, observed mutation, or digest.
    """
    if spec.action == "verify":
        result = run_verification_adapter("expected_check_topology", spec, payload)
        observed = (
            "desired_result_observed"
            if result["passed"]
            else ("not_observed" if result["verdict"] == "FAIL" else "unknown")
        )
        source, digest = "WorkflowsCore/expected_check_topology", result["result_digest"]
        context = "/".join(spec.verification_context())
    elif spec.action == "merge":
        producer = _load_producer()
        endpoint = f"repos/{spec.repository}/pulls/{spec.pr_number}"
        try:
            pr = producer.Evidence(producer.native_gh_pages).one(endpoint)
        except (producer.UnknownEvidence, SystemExit) as exc:
            # Unreadable evidence is unknown, never absence of the merge.
            pr = {"unreadable": str(exc)}
            observed = "unknown"
            context = "unreadable"
        else:
            if pr.get("head", {}).get("sha") != spec.head_sha:
                raise OwnershipDenied("reconciliation observed different target head")
            if type(pr.get("merged")) is not bool:
                observed = "unknown"
            else:
                observed = "desired_result_observed" if pr["merged"] else "not_observed"
            context = json.dumps(
                {
                    "merge_commit_sha": pr.get("merge_commit_sha"),
                    "base_sha": (pr.get("base") or {}).get("sha"),
                    "merged_by": (pr.get("merged_by") or {}).get("login"),
                },
                sort_keys=True,
            )
        source, digest = endpoint, _hash_canonical(pr)
    else:
        raise PolicyDenied("no reconciliation producer for this action")
    return ReconciliationEvidence(
        canonical_operation_key(spec),
        store_key_for_spec(spec),
        spec.head_sha,
        spec.action,
        observed,
        source,
        digest,
        context,
    )


def reconcile_unknown(
    store: LocalOperationStore,
    store_key: str,
    *,
    expected_revision: int,
    executor: ExecutorIdentity,
    spec: OperationSpec,
    expected_epoch: int,
    evidence: ReconciliationEvidence,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Read-only reconciliation. Usable after lease expiry and by a different observer.

    Expiry never proves a write did not start and never authorizes a retry: the
    operation stays unknown (`uncertain`) unless an independently produced observation
    shows the desired result. A non-owner observer fences the old owner (epoch + 1,
    reconcile-only) and leaves the original deadline, intent and receipts untouched.
    """
    record = store.read(store_key)
    if record is None:
        raise CloserRuntimeError("missing operation")
    assert_fresh_target(record, spec)
    if (
        record["lease"]["epoch"] != expected_epoch
        or record["lease"]["revision"] != expected_revision
    ):
        raise OwnershipDenied("stale epoch")
    if record.get("status") not in UNKNOWN_STATUSES:
        raise CloserRuntimeError("reconcile only for intent_recorded/submitted/uncertain")
    if not isinstance(evidence, ReconciliationEvidence) or (
        evidence.operation_key != record["operation_key"]
        or evidence.target_fence_key != store_key
        or evidence.head_sha != spec.head_sha
        or evidence.action != spec.action
        or not evidence.source
        or not KEY_RE.fullmatch(evidence.observation_digest)
        or evidence.result not in {"desired_result_observed", "not_observed", "unknown"}
        or (spec.action == "verify" and evidence.context != "/".join(spec.verification_context()))
    ):
        raise OwnershipDenied("reconciliation evidence not bound to operation/result")
    updated = dict(record)
    updated["receipts"] = [
        *record.get("receipts", []),
        {"kind": "reconciliation", **dataclasses.asdict(evidence)},
    ]
    lease = {**record["lease"], "revision": expected_revision + 1}
    if not executor.matches_record(record):
        lease["epoch"] = expected_epoch + 1
        lease["owner_ack"] = True
        updated["executor"] = {"kind": executor.kind, "identity": executor.identity}
        updated["ownership_scope"] = "reconcile_only"
    updated["lease"] = lease
    updated["status"] = "succeeded" if evidence.result == "desired_result_observed" else "uncertain"
    if record.get("denial"):
        updated["status"] = "denied"
    return store.write_cas(
        store_key,
        updated,
        expected_revision=expected_revision,
        authority=WriteAuthority("read_only_recovery", executor, expected_epoch, now=now),
    )


def replace_readonly_claim(
    store: LocalOperationStore,
    store_key: str,
    replacement: ExecutorIdentity,
    *,
    expected_revision: int,
    expected_epoch: int,
    spec: OperationSpec,
    new_deadline: dt.datetime,
    acknowledge_replacement: bool,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Replace an expired owner of read-only claimed work that has no mutation intent.

    The old executor is fenced by the epoch bump; the old deadline is kept in
    `lease.prior_deadlines` rather than extended in place.
    """
    record = store.read(store_key)
    if record is None:
        raise CloserRuntimeError("missing operation")
    assert_fresh_target(record, spec)
    if (
        record["lease"]["epoch"] != expected_epoch
        or record["lease"]["revision"] != expected_revision
    ):
        raise OwnershipDenied("stale epoch")
    if record["status"] != "claimed" or record.get("mutation_intent") is not None:
        raise OwnershipDenied("only claimed work with no mutation intent can be replaced")
    lease = dict(record["lease"])
    lease["prior_deadlines"] = [*(lease.get("prior_deadlines") or []), lease["deadline"]]
    lease.update(
        revision=expected_revision + 1,
        epoch=expected_epoch + 1,
        deadline=_iso_z(new_deadline),
        owner_ack=True,
    )
    updated = dict(record)
    updated["executor"] = {"kind": replacement.kind, "identity": replacement.identity}
    updated["ownership_scope"] = "execute"
    updated["lease"] = lease
    return store.write_cas(
        store_key,
        updated,
        expected_revision=expected_revision,
        authority=WriteAuthority(
            "read_only_recovery",
            replacement,
            expected_epoch,
            acknowledge_replacement=acknowledge_replacement,
            now=now,
        ),
    )


def run_bounded_action(
    store: LocalOperationStore,
    store_key: str,
    executor: ExecutorIdentity,
    action: str,
    payload: Mapping[str, Any],
    *,
    spec: OperationSpec,
    expected_epoch: int,
    expected_revision: int,
) -> dict[str, Any]:
    if action not in BOUNDED_ACTIONS:
        raise CloserRuntimeError(f"action {action!r} not in bounded set")
    record = store.read(store_key)
    if record is None:
        raise CloserRuntimeError("missing operation")
    if action != "reconcile_submitted":
        enforce_owner_lease(record, executor, spec=spec)
    rev = int(record["lease"]["revision"])
    if record["lease"]["epoch"] != expected_epoch or rev != expected_revision:
        raise OwnershipDenied("stale bounded-action epoch/revision")
    if record.get("status") not in ("claimed", "intent_recorded", "submitted", "uncertain"):
        raise OwnershipDenied("bounded action cannot change terminal record")
    if action in ("verify_unchanged_gate", "verify_expected_checks"):
        # A fingerprint alone is never a successful verification receipt.
        action = "execute_local_verification"
        payload = {**payload, "adapter": "expected_check_topology"}
    if action == "execute_local_verification":
        adapter_id = str(payload.get("adapter", ""))
        fp = verification_fingerprint(
            spec.head_sha, spec.criteria_fingerprint, spec.review_revision
        )
        outcome = run_verification_adapter(adapter_id, spec, payload)
        digest = str(outcome["result_digest"])
        for prior in record.get("receipts") or []:
            if outcome["passed"] and verification_receipt_matches(
                prior, fingerprint=fp, adapter_id=adapter_id, result_digest=digest
            ):
                return {
                    "skipped": True,
                    "fingerprint": fp,
                    "adapter": adapter_id,
                    "result_digest": digest,
                    "record": record,
                }
        updated = dict(record)
        receipts = list(updated.get("receipts") or [])
        receipts.append(
            {
                "kind": "local_verification",
                "fingerprint": fp,
                "adapter": adapter_id,
                "result_digest": digest,
                "passed": outcome.get("passed"),
                "source": outcome.get("source"),
                "verdict": outcome.get("verdict"),
                "producer_result": outcome.get("producer_result"),
                "event": outcome.get("event"),
                "event_action": outcome.get("event_action"),
            }
        )
        updated["receipts"] = receipts
        updated["last_verification_fingerprint"] = fp if outcome["passed"] else None
        lease = dict(updated["lease"])
        lease["revision"] = rev + 1
        updated["lease"] = lease
        record = store.write_cas(
            store_key,
            updated,
            expected_revision=rev,
            authority=WriteAuthority("owner_update", executor, expected_epoch),
        )
        return {
            "skipped": False,
            "fingerprint": fp,
            "adapter": adapter_id,
            "result_digest": digest,
            "record": record,
        }
    if action == "record_evidence":
        block = merge_block(spec, executor.kind, record)
        if block is not None:
            terminalize(
                store,
                store_key,
                "denied",
                expected_revision=rev,
                executor=executor,
                spec=spec,
                denial_reason=block.reason,
                expected_epoch=record["lease"]["epoch"],
            )
            raise block
        updated = dict(record)
        receipts = list(updated.get("receipts") or [])
        receipts.append({"payload": dict(payload), "kind": "evidence"})
        updated["receipts"] = receipts
        lease = dict(updated["lease"])
        lease["revision"] = rev + 1
        updated["lease"] = lease
        record = store.write_cas(
            store_key,
            updated,
            expected_revision=rev,
            authority=WriteAuthority("owner_update", executor, expected_epoch),
        )
        return {"record": record}
    if action == "reconcile_submitted":
        return {
            "record": reconcile_unknown(
                store,
                store_key,
                expected_revision=rev,
                executor=executor,
                spec=spec,
                expected_epoch=expected_epoch,
                evidence=collect_reconciliation_evidence(spec, payload),
            )
        }
    raise CloserRuntimeError("unreachable")


def load_spec_from_json(path: Path) -> OperationSpec:
    data = json.loads(path.read_text(encoding="utf-8"))
    return OperationSpec(
        repository=data["repository"],
        pr_number=int(data["target"]["number"]),
        action=data["action"],
        head_sha=data["head_sha"],
        base_sha=data.get("base_sha"),
        criteria_fingerprint=data["criteria_fingerprint"],
        review_revision=data["review_revision"],
        guard_versions=data.get("guard_versions", {"authority": 2}),
        required_capabilities=data.get("required_capabilities", ()),
        blocking_labels=data.get("blocking_labels", ()),
        verification_event=(data.get("verification_context") or {}).get("event"),
        verification_event_action=(data.get("verification_context") or {}).get("action"),
    )


def operation_status(store: LocalOperationStore, spec: OperationSpec) -> dict[str, Any] | None:
    record = store.read(store_key_for_spec(spec))
    if record is None:
        return None
    return {
        "store_key": store_key_for_spec(spec),
        "operation_key": record.get("operation_key"),
        "status": record.get("status"),
        "executor": record.get("executor"),
        "lease": record.get("lease"),
    }


def _cli_validate(args: argparse.Namespace) -> int:
    record = json.loads(Path(args.record).read_text(encoding="utf-8"))
    errors = validate_operation_record(record)
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return 1
    print("ok")
    return 0


def _cli_status(args: argparse.Namespace) -> int:
    spec = load_spec_from_json(Path(args.spec))
    store = LocalOperationStore(Path(args.store))
    status = operation_status(store, spec)
    print(json.dumps(status or {"status": "missing"}, indent=2))
    return 0


def _cli_claim(args: argparse.Namespace) -> int:
    spec = load_spec_from_json(Path(args.spec))
    store = LocalOperationStore(Path(args.store))
    executor = ExecutorIdentity(args.executor_kind, args.executor_identity)
    deadline = _utc_now() + dt.timedelta(seconds=int(args.lease_seconds))
    try:
        record, created = store.claim(spec, executor, lease_deadline=deadline)
    except (OwnershipDenied, CasConflict) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    out = {
        "created": created,
        "store_key": store_key_for_spec(spec),
        "operation_key": record["operation_key"],
        "record": record,
    }
    print(json.dumps(out, indent=2))
    return 0


def _cli_run(args: argparse.Namespace) -> int:
    spec = load_spec_from_json(Path(args.spec))
    store = LocalOperationStore(Path(args.store))
    executor = ExecutorIdentity(args.executor_kind, args.executor_identity)
    key = store_key_for_spec(spec)
    try:
        result = run_bounded_action(
            store,
            key,
            executor,
            args.action,
            json.loads(args.payload or "{}"),
            spec=spec,
            expected_epoch=args.expected_epoch,
            expected_revision=args.expected_revision,
        )
    except PolicyDenied as exc:
        print(json.dumps({"denied": True, "reason": exc.reason}), file=sys.stderr)
        return 3
    except (OwnershipDenied, CloserRuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, default=str))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="closer-operation/v1 portable runtime")
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate", help="validate operation JSON record")
    p_val.add_argument("record")
    p_val.set_defaults(func=_cli_validate)

    p_status = sub.add_parser("status", help="read local store status for spec fence")
    p_status.add_argument("--store", required=True)
    p_status.add_argument("--spec", required=True)
    p_status.set_defaults(func=_cli_status)

    p_claim = sub.add_parser("claim", help="claim operation in local store")
    p_claim.add_argument("--store", required=True)
    p_claim.add_argument("--spec", required=True)
    p_claim.add_argument("--executor-kind", default="portable_local")
    p_claim.add_argument("--executor-identity", required=True)
    p_claim.add_argument("--lease-seconds", default="3600")
    p_claim.set_defaults(func=_cli_claim)

    p_run = sub.add_parser("run", help="run a bounded action")
    p_run.add_argument("--store", required=True)
    p_run.add_argument("--spec", required=True)
    p_run.add_argument("--executor-kind", default="portable_local")
    p_run.add_argument("--executor-identity", required=True)
    p_run.add_argument("--action", required=True, choices=sorted(BOUNDED_ACTIONS))
    p_run.add_argument("--payload", default="{}")
    p_run.add_argument("--expected-epoch", required=True, type=int)
    p_run.add_argument("--expected-revision", required=True, type=int)
    p_run.set_defaults(func=_cli_run)

    args = parser.parse_args(list(argv) if argv is not None else None)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
