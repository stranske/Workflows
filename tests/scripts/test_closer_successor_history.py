"""A terminal owner may be replaced, while its exact evidence remains available."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest
from scripts import closer_runtime as cr

from tests.scripts.test_closer_runtime import _executor, _spec


def drained(store, status="unavailable"):
    spec, owner = _spec(action="verify"), _executor()
    record, _ = store.claim(spec, owner, lease_deadline=datetime.now(UTC) + timedelta(hours=1))
    key = cr.store_key_for_spec(spec)
    record = cr.terminalize(
        store,
        key,
        status,
        expected_revision=1,
        expected_epoch=1,
        executor=owner,
        spec=spec,
        **({"denial_reason": "permission refused"} if status == "denied" else {}),
        receipt={"kind": "capacity", "observation": "not_started"},
    )
    return spec, owner, key, record


def test_acknowledged_successor_preserves_old_intent_and_receipts(tmp_path):
    store = cr.LocalOperationStore(tmp_path)
    spec, _, key, old = drained(store)
    new_spec = dataclasses.replace(spec, head_sha="b" * 40, review_revision="new-review")
    successor = cr.ExecutorIdentity("portable_local", "independent-next-run")
    deadline = datetime.now(UTC) + timedelta(hours=1)
    with pytest.raises(cr.OwnershipDenied):
        store.claim(new_spec, successor, lease_deadline=deadline)
    new, created = store.claim(
        new_spec,
        successor,
        lease_deadline=deadline,
        acknowledge_replacement=True,
    )
    assert created and new["lease"]["epoch"] == old["lease"]["epoch"] + 1
    assert new["target_fence_key"] == key
    assert new["prior_operations"][-1]["record"] == old
    assert new["prior_operations"][-1]["sha256"] == cr._hash_canonical(old)
    assert cr.validate_operation_record(new) == []
    corrupted = {**new, "prior_operations": [{**new["prior_operations"][0], "sha256": "f" * 64}]}
    assert any("digest" in e for e in cr.validate_operation_record(corrupted))


def test_same_owner_new_head_also_keeps_history(tmp_path):
    store = cr.LocalOperationStore(tmp_path)
    spec, owner, _, old = drained(store)
    changed = dataclasses.replace(spec, head_sha="b" * 40)
    record, _ = store.claim(changed, owner, lease_deadline=datetime.now(UTC) + timedelta(hours=1))
    assert record["prior_operations"][0]["record"] == old


def test_successor_acknowledgement_cannot_clear_denial(tmp_path):
    store = cr.LocalOperationStore(tmp_path)
    spec, _, _, old = drained(store, status="denied")
    changed = dataclasses.replace(spec, head_sha="b" * 40)
    with pytest.raises((cr.PolicyDenied, cr.OwnershipDenied)):
        store.claim(
            changed,
            cr.ExecutorIdentity("portable_local", "fallback"),
            lease_deadline=datetime.now(UTC) + timedelta(hours=1),
            acknowledge_replacement=True,
        )
    assert store.read(cr.store_key_for_spec(spec)) == old


def test_successor_acknowledgement_never_drains_unfinished_intent(tmp_path):
    store = cr.LocalOperationStore(tmp_path)
    spec, owner = _spec(action="verify"), _executor()
    store.claim(spec, owner, lease_deadline=datetime.now(UTC) + timedelta(hours=1))
    key = cr.store_key_for_spec(spec)
    intent = cr.record_mutation_intent(
        store,
        key,
        owner,
        {"operation": "unconfirmed"},
        expected_revision=1,
        expected_epoch=1,
        spec=spec,
    )
    with pytest.raises(cr.OwnershipDenied):
        store.claim(
            dataclasses.replace(spec, head_sha="b" * 40),
            cr.ExecutorIdentity("portable_local", "fallback"),
            lease_deadline=datetime.now(UTC) + timedelta(hours=1),
            acknowledge_replacement=True,
        )
    assert store.read(key) == intent


@pytest.mark.parametrize("api", ["terminalize", "cas"])
def test_unresolved_intent_cannot_become_unavailable(tmp_path, api):
    store = cr.LocalOperationStore(tmp_path)
    spec, owner = _spec(action="verify"), _executor()
    store.claim(spec, owner, lease_deadline=datetime.now(UTC) + timedelta(hours=1))
    key = cr.store_key_for_spec(spec)
    intent = cr.record_mutation_intent(
        store,
        key,
        owner,
        {"operation": "may_have_started"},
        expected_revision=1,
        expected_epoch=1,
        spec=spec,
    )
    with pytest.raises(cr.OwnershipDenied):
        if api == "terminalize":
            cr.terminalize(
                store,
                key,
                "unavailable",
                expected_revision=2,
                expected_epoch=1,
                executor=owner,
                spec=spec,
            )
        else:
            forged = {
                **intent,
                "status": "unavailable",
                "lease": {**intent["lease"], "revision": 3},
            }
            store.write_cas(
                key,
                forged,
                expected_revision=2,
                authority=cr.WriteAuthority("owner_update", owner, 1),
            )
    assert store.read(key) == intent
    with pytest.raises(cr.OwnershipDenied):
        store.claim(
            dataclasses.replace(spec, head_sha="b" * 40),
            cr.ExecutorIdentity("portable_local", "next"),
            lease_deadline=datetime.now(UTC) + timedelta(hours=1),
            acknowledge_replacement=True,
        )
