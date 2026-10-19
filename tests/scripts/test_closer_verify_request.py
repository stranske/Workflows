"""Request dispatch shares old ownership fencing, never topology verification success."""

from __future__ import annotations

import dataclasses
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
