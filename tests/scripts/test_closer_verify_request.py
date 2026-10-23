"""Request dispatch shares old ownership fencing, never topology verification success."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from scripts import closer_runtime as cr

from tests.scripts.test_closer_runtime import _executor, _spec


def test_request_and_old_verify_share_cas_but_not_operation_or_producer(tmp_path):
    topology = _spec(action="verify")
    request = dataclasses.replace(topology, action="verify_request")
    assert cr.canonical_target_fence_key(request) == cr.canonical_target_fence_key(topology)
    assert cr.canonical_operation_key(request) != cr.canonical_operation_key(topology)
    store = cr.LocalOperationStore(tmp_path)
    record, _ = store.claim(
        request, _executor(), lease_deadline=datetime.now(UTC) + timedelta(hours=1)
    )
    assert cr.validate_operation_record(record) == []
    with pytest.raises(cr.OwnershipDenied):
        store.claim(topology, _executor(), lease_deadline=datetime.now(UTC) + timedelta(hours=1))
    with pytest.raises(cr.PolicyDenied, match="no reconciliation producer"):
        cr.collect_reconciliation_evidence(request, {"verdict": "PASS"})


def _dispatch_intent(tmp_path):
    binding = {
        "verification_mutation": {"mutation_kind": "workflow_dispatch", "request_basis": "d" * 64}
    }
    spec = dataclasses.replace(
        _spec(action="verify_request"),
        guard_versions={
            "authority": 2,
            "native_binding": hashlib.sha256(
                json.dumps(binding, sort_keys=True).encode()
            ).hexdigest(),
        },
    )
    store = cr.LocalOperationStore(tmp_path)
    record, _ = store.claim(
        spec, _executor(), lease_deadline=datetime.now(UTC) + timedelta(hours=1)
    )
    record = cr.record_mutation_intent(
        store,
        record["target_fence_key"],
        _executor(),
        {"action": "verify_request", "head_sha": spec.head_sha, "native_binding": binding},
        expected_revision=1,
        expected_epoch=1,
        spec=spec,
    )
    return store, spec, record


def test_typed_422_rejection_retains_intent_and_allows_same_owner_same_operation_retry(tmp_path):
    store, spec, record = _dispatch_intent(tmp_path)
    rejected = cr.reject_not_accepted(
        store,
        record["target_fence_key"],
        _executor(),
        cr.VerificationRequestRejected("workflow_dispatch", "d" * 64, 422),
        expected_revision=2,
        expected_epoch=1,
        spec=spec,
    )
    assert rejected["status"] == "unavailable"
    assert rejected["mutation_intent"] == record["mutation_intent"]
    assert cr.validate_operation_record(rejected) == []
    with pytest.raises(cr.OwnershipDenied):
        store.claim(
            spec,
            _executor("foreign"),
            lease_deadline=datetime.now(UTC) + timedelta(hours=1),
        )
    retry, created = store.claim(
        spec, _executor(), lease_deadline=datetime.now(UTC) + timedelta(hours=1)
    )
    assert created and retry["status"] == "claimed"
    assert retry["lease"]["epoch"] == 2 and retry["lease"]["revision"] == 4
    assert retry["mutation_intent"] is None
    assert retry["prior_operations"][-1]["record"] == rejected
    assert retry["prior_operations"][-1]["sha256"] == cr._hash_canonical(rejected)


@pytest.mark.parametrize(
    "evidence",
    [
        cr.VerificationRequestRejected("workflow_dispatch", "e" * 64, 422),
        cr.VerificationRequestRejected("label", "d" * 64, 422),
        cr.VerificationRequestRejected("workflow_dispatch", "d" * 64, 500),
        cr.VerificationRequestRejected("workflow_dispatch", "d" * 64, True),
        {"mutation_kind": "workflow_dispatch", "request_basis": "d" * 64, "http_status": 422},
    ],
)
def test_rejection_requires_exact_typed_binding_and_status(tmp_path, evidence):
    store, spec, record = _dispatch_intent(tmp_path)
    with pytest.raises(cr.OwnershipDenied):
        cr.reject_not_accepted(
            store,
            record["target_fence_key"],
            _executor(),
            evidence,
            expected_revision=2,
            expected_epoch=1,
            spec=spec,
        )
    assert store.read(record["target_fence_key"]) == record


@pytest.mark.parametrize("status", ["submitted", "uncertain"])
def test_submitted_or_uncertain_rejection_never_clears_effect_fence(tmp_path, status):
    store, spec, record = _dispatch_intent(tmp_path)
    if status == "submitted":
        record = cr.mark_submitted(
            store,
            record["target_fence_key"],
            _executor(),
            expected_revision=2,
            expected_epoch=1,
            spec=spec,
        )
    else:
        record = cr.terminalize(
            store,
            record["target_fence_key"],
            "uncertain",
            executor=_executor(),
            expected_revision=2,
            expected_epoch=1,
            spec=spec,
        )
    with pytest.raises(cr.OwnershipDenied):
        cr.reject_not_accepted(
            store,
            record["target_fence_key"],
            _executor(),
            cr.VerificationRequestRejected("workflow_dispatch", "d" * 64, 422),
            expected_revision=3,
            expected_epoch=1,
            spec=spec,
        )
    assert store.read(record["target_fence_key"]) == record


def test_rejected_retry_new_queue_id_preserves_exact_request_basis(tmp_path):
    store, spec, record = _dispatch_intent(tmp_path)
    rejected = cr.reject_not_accepted(
        store,
        record["target_fence_key"],
        _executor(),
        cr.VerificationRequestRejected("workflow_dispatch", "d" * 64, 422),
        expected_revision=2,
        expected_epoch=1,
        spec=spec,
    )
    binding = {
        **record["mutation_intent"]["native_binding"],
        "queue_operation_id": "new-queue-operation",
    }
    successor = dataclasses.replace(
        spec,
        guard_versions={
            **spec.guard_versions,
            "native_binding": hashlib.sha256(
                json.dumps(binding, sort_keys=True).encode()
            ).hexdigest(),
        },
    )
    retry, created = store.claim(
        successor, _executor(), lease_deadline=datetime.now(UTC) + timedelta(hours=1)
    )
    assert created and retry["prior_operations"][-1]["record"] == rejected
    intent = {**record["mutation_intent"], "native_binding": binding}
    claimed = cr.record_mutation_intent(
        store,
        retry["target_fence_key"],
        _executor(),
        intent,
        expected_revision=4,
        expected_epoch=2,
        spec=successor,
    )
    assert claimed["status"] == "intent_recorded"
    assert cr.verification_request_not_accepted(rejected)
    assert not cr.verification_request_not_accepted(claimed)


@pytest.mark.parametrize("failure", ["foreign", "epoch", "revision", "expired", "guard_digest"])
def test_rejection_requires_current_owned_live_intent_and_native_protocol_digest(tmp_path, failure):
    store, spec, record = _dispatch_intent(tmp_path)
    executor = _executor("foreign") if failure == "foreign" else _executor()
    epoch = 2 if failure == "epoch" else 1
    revision = 1 if failure == "revision" else 2
    if failure in {"expired", "guard_digest"}:
        raw = dict(record)
        if failure == "expired":
            raw["lease"] = {**raw["lease"], "deadline": "2000-01-01T00:00:00Z"}
        else:
            binding = raw["mutation_intent"]["native_binding"]
            assert cr._native_binding_digest(binding) != cr._hash_canonical(binding)
            raw["mutation_intent"] = {
                **raw["mutation_intent"],
                "native_binding": {**binding, "queue_operation_id": "tampered"},
            }
        # Simulate a pre-existing malformed/expired authority record, never a supported write.
        store.read = lambda key: raw
    with pytest.raises((cr.OwnershipDenied, cr.CasConflict)):
        cr.reject_not_accepted(
            store,
            record["target_fence_key"],
            executor,
            cr.VerificationRequestRejected("workflow_dispatch", "d" * 64, 422),
            expected_revision=revision,
            expected_epoch=epoch,
            spec=spec,
        )


@pytest.mark.parametrize("new_queue_id", [False, True])
def test_acknowledged_later_owner_can_retry_authentic_terminal_rejection(tmp_path, new_queue_id):
    store, spec, record = _dispatch_intent(tmp_path)
    rejected = cr.reject_not_accepted(
        store,
        record["target_fence_key"],
        _executor(),
        cr.VerificationRequestRejected("workflow_dispatch", "d" * 64, 422),
        expected_revision=2,
        expected_epoch=1,
        spec=spec,
    )
    binding = dict(record["mutation_intent"]["native_binding"])
    if new_queue_id:
        binding["queue_operation_id"] = "successor-owned-queue-operation"
        spec = dataclasses.replace(
            spec,
            guard_versions={
                **spec.guard_versions,
                "native_binding": hashlib.sha256(
                    json.dumps(binding, sort_keys=True).encode()
                ).hexdigest(),
            },
        )
    later = _executor("later-qualified-owner")
    retry, created = store.claim(
        spec,
        later,
        lease_deadline=datetime.now(UTC) + timedelta(hours=1),
        acknowledge_replacement=True,
    )
    assert created and retry["lease"]["epoch"] == 2
    assert retry["prior_operations"][-1]["record"] == rejected
    assert store.read(record["target_fence_key"])["prior_operations"][-1]["record"] == rejected
    intent = {**record["mutation_intent"], "native_binding": binding}
    submitted = cr.record_mutation_intent(
        store,
        retry["target_fence_key"],
        later,
        intent,
        expected_revision=4,
        expected_epoch=2,
        spec=spec,
    )
    assert submitted["status"] == "intent_recorded"


@pytest.mark.parametrize("change", ["material", "head", "criteria", "review_revision"])
def test_authentic_rejection_does_not_block_new_authorized_operation(tmp_path, change):
    store, old_spec, record = _dispatch_intent(tmp_path)
    rejected = cr.reject_not_accepted(
        store,
        record["target_fence_key"],
        _executor(),
        cr.VerificationRequestRejected("workflow_dispatch", "d" * 64, 422),
        expected_revision=2,
        expected_epoch=1,
        spec=old_spec,
    )
    binding = {
        "queue_operation_id": "fresh-operation",
        "verification_mutation": {"mutation_kind": "workflow_dispatch", "request_basis": "e" * 64},
    }
    changes = {
        "guard_versions": {
            **old_spec.guard_versions,
            "native_binding": hashlib.sha256(
                json.dumps(binding, sort_keys=True).encode()
            ).hexdigest(),
        }
    }
    if change == "head":
        changes["head_sha"] = "e" * 40
    elif change == "criteria":
        changes["criteria_fingerprint"] = "e" * 64
    elif change == "review_revision":
        changes["review_revision"] = "fresh-review"
    spec = dataclasses.replace(old_spec, **changes)
    later = _executor("fresh-qualified-owner")
    with pytest.raises(cr.OwnershipDenied):
        store.claim(spec, later, lease_deadline=datetime.now(UTC) + timedelta(hours=1))
    retry, created = store.claim(
        spec,
        later,
        lease_deadline=datetime.now(UTC) + timedelta(hours=1),
        acknowledge_replacement=True,
    )
    assert created and retry["operation_key"] != rejected["operation_key"]
    assert retry["prior_operations"][-1]["record"] == rejected
    fresh = cr.record_mutation_intent(
        store,
        retry["target_fence_key"],
        later,
        {"action": "verify_request", "head_sha": spec.head_sha, "native_binding": binding},
        expected_revision=4,
        expected_epoch=2,
        spec=spec,
    )
    assert fresh["status"] == "intent_recorded"
    assert fresh["prior_operations"][-1]["record"] == rejected


def test_changed_basis_under_old_spec_is_refused_after_known_rejection(tmp_path):
    store, spec, record = _dispatch_intent(tmp_path)
    cr.reject_not_accepted(
        store,
        record["target_fence_key"],
        _executor(),
        cr.VerificationRequestRejected("workflow_dispatch", "d" * 64, 422),
        expected_revision=2,
        expected_epoch=1,
        spec=spec,
    )
    retry, _ = store.claim(spec, _executor(), lease_deadline=datetime.now(UTC) + timedelta(hours=1))
    binding = {
        "verification_mutation": {"mutation_kind": "workflow_dispatch", "request_basis": "e" * 64}
    }
    with pytest.raises(cr.OwnershipDenied, match="exact current native binding"):
        cr.record_mutation_intent(
            store,
            retry["target_fence_key"],
            _executor(),
            {**record["mutation_intent"], "native_binding": binding},
            expected_revision=4,
            expected_epoch=2,
            spec=spec,
        )
    assert store.read(retry["target_fence_key"])["status"] == "claimed"


@pytest.mark.parametrize(
    "defect",
    ["extra", "missing", "operation_hex", "request_hex", "head_hex", "status_500", "status_bool"],
)
def test_rejection_receipt_schema_rejects_malformed_fields_independently(tmp_path, defect):
    store, spec, record = _dispatch_intent(tmp_path)
    rejected = cr.reject_not_accepted(
        store,
        record["target_fence_key"],
        _executor(),
        cr.VerificationRequestRejected("workflow_dispatch", "d" * 64, 422),
        expected_revision=2,
        expected_epoch=1,
        spec=spec,
    )
    invalid = json.loads(json.dumps(rejected))
    receipt = invalid["receipts"][-1]
    if defect == "extra":
        receipt["unexpected"] = "not allowed"
    elif defect == "missing":
        del receipt["request_basis"]
    elif defect == "operation_hex":
        receipt["operation_key"] = "z" * 64
    elif defect == "request_hex":
        receipt["request_basis"] = "D" * 64
    elif defect == "head_hex":
        receipt["head_sha"] = "a" * 39
    elif defect == "status_500":
        receipt["http_status"] = 500
    else:
        receipt["http_status"] = True
    assert cr.validate_operation_record(invalid)
    assert not cr.verification_request_not_accepted(invalid)
