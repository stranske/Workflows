"""Conformance tests for closer-operation/v1 portable runtime."""

from __future__ import annotations

import dataclasses
import json
import multiprocessing as mp
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from scripts import closer_operation_github as gh
from scripts import closer_runtime as cr

REPO_ROOT = Path(__file__).resolve().parents[2]


def _spec(
    head: str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    labels: tuple[str, ...] = (),
    action: str = "merge",
) -> cr.OperationSpec:
    return cr.OperationSpec(
        repository="stranske/Workflows",
        pr_number=42,
        action=action,
        head_sha=head,
        base_sha="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        criteria_fingerprint="c" * 64,
        review_revision="rev-1",
        guard_versions={"authority": 2, "runtime_ac_guard": "v1"},
        required_capabilities=("bounded_merge",),
        blocking_labels=labels,
    )


def _executor(
    name: str = "portable:a", kind: cr.ExecutorKind = "portable_local"
) -> cr.ExecutorIdentity:
    return cr.ExecutorIdentity(kind, name)


def _fence_key(spec: cr.OperationSpec) -> str:
    return cr.store_key_for_spec(spec)


def _mp_claim_worker(args: tuple[str, str, str]) -> str:
    root_s, name, deadline_s = args
    root = Path(root_s)
    spec = _spec()
    deadline = datetime.fromisoformat(deadline_s)
    local_store = cr.LocalOperationStore(root)
    try:
        _, created = local_store.claim(spec, _executor(name), lease_deadline=deadline)
        return json.dumps({"name": name, "created": created})
    except cr.OwnershipDenied:
        return json.dumps({"name": name, "created": False})


def _mp_cas_bump_worker(args: tuple[str, str, int, int]) -> str:
    root_s, key, rev, worker_id = args
    local = cr.LocalOperationStore(Path(root_s))
    try:
        record = local.read(key)
        if record is None:
            return "lose"
        updated = dict(record)
        lease = dict(updated["lease"])
        lease["revision"] = rev + 1
        updated["lease"] = lease
        updated["receipts"] = list(updated.get("receipts") or []) + [{"worker": worker_id}]
        owner = cr.ExecutorIdentity(record["executor"]["kind"], record["executor"]["identity"])
        local.write_cas(
            key,
            updated,
            expected_revision=rev,
            authority=cr.WriteAuthority("owner_update", owner, record["lease"]["epoch"]),
        )
        return "win"
    except cr.CasConflict:
        return "lose"


@pytest.fixture(autouse=True)
def _no_live_pr_labels(monkeypatch):
    """Offline default: fresh live PR labels read as empty; live-label tests override it."""
    monkeypatch.setattr(cr, "fetch_live_pr_labels", lambda spec: [])


@pytest.fixture
def store(tmp_path: Path) -> cr.LocalOperationStore:
    return cr.LocalOperationStore(tmp_path / "ops")


def test_canonical_operation_key_independent_of_executor(store: cr.LocalOperationStore) -> None:
    spec = _spec()
    key1 = cr.canonical_operation_key(spec)
    fence = _fence_key(spec)
    ex_a = _executor("a")
    ex_b = _executor("b")
    deadline = datetime.now(UTC) + timedelta(hours=1)
    store.claim(spec, ex_a, lease_deadline=deadline)
    with pytest.raises(cr.OwnershipDenied):
        store.claim(spec, ex_b, lease_deadline=deadline)
    assert cr.canonical_operation_key(spec) == key1
    assert cr.canonical_target_fence_key(spec) == fence


def test_claim_race_one_owner_multiprocess(tmp_path: Path) -> None:
    root = tmp_path / "ops"
    root.mkdir()
    deadline = datetime.now(UTC) + timedelta(hours=1)

    ctx = mp.get_context("spawn")
    deadline_s = deadline.isoformat()
    tasks = [(str(root), f"e{i}", deadline_s) for i in range(8)]
    with ctx.Pool(8) as pool:
        lines = pool.map(_mp_claim_worker, tasks)
    results = [json.loads(line) for line in lines]
    winners = [r["name"] for r in results if r["created"]]
    assert len(winners) == 1
    assert sum(1 for r in results if not r["created"]) >= 1


def test_cas_update_race_multiprocess(tmp_path: Path) -> None:
    root = tmp_path / "ops"
    store = cr.LocalOperationStore(root)
    spec = _spec(action="verify")
    deadline = datetime.now(UTC) + timedelta(hours=1)
    ex = _executor("race")
    rec, _ = store.claim(spec, ex, lease_deadline=deadline)
    key = _fence_key(spec)
    rev = rec["lease"]["revision"]

    ctx = mp.get_context("spawn")
    tasks = [(str(root), key, rev, wid) for wid in (1, 2)]
    with ctx.Pool(2) as pool:
        outcomes = pool.map(_mp_cas_bump_worker, tasks)
    assert outcomes.count("win") == 1
    assert outcomes.count("lose") == 1


def test_interrupted_create_not_valid_json(tmp_path: Path) -> None:
    root = tmp_path / "ops"
    store = cr.LocalOperationStore(root)
    spec = _spec(action="verify")
    key = _fence_key(spec)
    path = store._path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{", encoding="utf-8")
    with pytest.raises(cr.CloserRuntimeError, match="corrupt"):
        store.read(key)


def test_cross_head_unknown_hold(store: cr.LocalOperationStore) -> None:
    spec_a = _spec(head="a" * 40, action="verify")
    spec_b = _spec(head="d" * 40, action="verify")
    assert _fence_key(spec_a) == _fence_key(spec_b)
    deadline = datetime.now(UTC) + timedelta(hours=1)
    ex = _executor()
    rec, _ = store.claim(spec_a, ex, lease_deadline=deadline)
    key = _fence_key(spec_a)
    rev = rec["lease"]["revision"]
    rec = cr.record_mutation_intent(
        store, key, ex, {"op": "x"}, expected_revision=rev, spec=spec_a, expected_epoch=1
    )
    rev = rec["lease"]["revision"]
    rec = cr.mark_submitted(store, key, ex, expected_revision=rev, spec=spec_a, expected_epoch=1)
    assert rec["status"] == "submitted"
    with pytest.raises(cr.OwnershipDenied, match="prior head"):
        store.claim(spec_b, ex, lease_deadline=deadline)


def test_executor_kind_mismatch_denied(store: cr.LocalOperationStore) -> None:
    spec = _spec(action="verify")
    deadline = datetime.now(UTC) + timedelta(hours=1)
    store.claim(spec, _executor("same-id", kind="portable_local"), lease_deadline=deadline)
    with pytest.raises(cr.OwnershipDenied):
        store.claim(spec, _executor("same-id", kind="orchestrator_local"), lease_deadline=deadline)


def test_stale_head_rejected(store: cr.LocalOperationStore) -> None:
    spec = _spec()
    deadline = datetime.now(UTC) + timedelta(hours=1)
    ex = _executor()
    rec, _ = store.claim(spec, ex, lease_deadline=deadline)
    key = _fence_key(spec)
    live = "dddddddddddddddddddddddddddddddddddddddd"
    with pytest.raises(cr.OwnershipDenied, match="stale head"):
        cr.record_mutation_intent(
            store,
            key,
            ex,
            {"merge": True},
            expected_revision=rec["lease"]["revision"],
            spec=spec,
            live_head_sha=live,
            expected_epoch=1,
        )


def test_denial_nonfallback(store: cr.LocalOperationStore) -> None:
    spec = _spec(labels=("runtime-ac",))
    deadline = datetime.now(UTC) + timedelta(hours=1)
    rec, _ = store.claim(spec, _executor(), lease_deadline=deadline)
    key = _fence_key(spec)
    with pytest.raises(cr.PolicyDenied) as exc:
        cr.run_bounded_action(
            store,
            key,
            _executor(),
            "record_evidence",
            {"note": "try merge"},
            spec=spec,
            expected_epoch=store.read(key)["lease"]["epoch"],
            expected_revision=store.read(key)["lease"]["revision"],
        )
    assert exc.value.no_fallback is True
    terminal = store.read(key)
    assert terminal is not None
    assert terminal["status"] == "denied"
    assert terminal["denial"]["no_fallback"] is True
    with pytest.raises(cr.OwnershipDenied):
        store.claim(spec, _executor("fallback"), lease_deadline=deadline)


def test_caller_flag_cannot_self_grant_runtime_ac(store: cr.LocalOperationStore) -> None:
    spec = _spec(labels=("runtime-ac",))
    deadline = datetime.now(UTC) + timedelta(hours=1)
    rec, _ = store.claim(
        spec, cr.ExecutorIdentity("orchestrator_local", "orch"), lease_deadline=deadline
    )
    key = _fence_key(spec)
    with pytest.raises(cr.PolicyDenied):
        cr.run_bounded_action(
            store,
            key,
            cr.ExecutorIdentity("orchestrator_local", "orch"),
            "record_evidence",
            {},
            spec=spec,
            expected_epoch=store.read(key)["lease"]["epoch"],
            expected_revision=store.read(key)["lease"]["revision"],
        )


def test_unknown_mutation_reconciliation(store: cr.LocalOperationStore) -> None:
    spec = _spec(action="verify")
    ex = _executor()
    rec, _ = store.claim(spec, ex, lease_deadline=datetime.now(UTC) + timedelta(hours=1))
    key = _fence_key(spec)
    rec = cr.record_mutation_intent(
        store, key, ex, {"op": "verify"}, expected_revision=1, expected_epoch=1, spec=spec
    )
    rec = cr.mark_submitted(store, key, ex, expected_revision=2, expected_epoch=1, spec=spec)
    for result in ["unknown", "not_observed", "desired_result_observed"]:
        ev = cr.ReconciliationEvidence(
            rec["operation_key"],
            key,
            spec.head_sha,
            spec.action,
            result,
            "native-read",
            "d" * 64,
            "/".join(spec.verification_context()),
        )
        rec = cr.reconcile_unknown(
            store,
            key,
            executor=ex,
            spec=spec,
            expected_epoch=1,
            expected_revision=rec["lease"]["revision"],
            evidence=ev,
        )
        assert rec["status"] == (
            "succeeded" if result == "desired_result_observed" else "uncertain"
        )


def test_crash_restart_preserves_state(store: cr.LocalOperationStore) -> None:
    spec = _spec(action="verify")
    deadline = datetime.now(UTC) + timedelta(hours=1)
    ex = _executor("restart")
    rec, created = store.claim(spec, ex, lease_deadline=deadline)
    assert created
    revived = cr.LocalOperationStore(store.root)
    again, created2 = revived.claim(spec, ex, lease_deadline=deadline)
    assert not created2
    assert again["operation_key"] == rec["operation_key"]
    assert again["executor"]["identity"] == "restart"


def test_fallback_and_back_single_owner(store: cr.LocalOperationStore) -> None:
    spec = _spec(action="verify")
    deadline = datetime.now(UTC) + timedelta(hours=1)
    primary = _executor("primary")
    backup = cr.ExecutorIdentity("portable_local", "backup")
    rec, _ = store.claim(spec, primary, lease_deadline=deadline)
    key = _fence_key(spec)
    rev = rec["lease"]["revision"]
    transferred = cr.transfer_ownership(
        store, key, primary, backup, expected_revision=rev, spec=spec, to_ack=True, expected_epoch=1
    )
    assert transferred["executor"]["identity"] == "backup"
    assert transferred["lease"]["epoch"] == 2
    with pytest.raises(cr.OwnershipDenied):
        cr.record_mutation_intent(
            store,
            key,
            primary,
            {"x": 1},
            expected_revision=transferred["lease"]["revision"],
            spec=spec,
            expected_epoch=1,
        )
    rev2 = transferred["lease"]["revision"]
    cr.record_mutation_intent(
        store, key, backup, {"x": 1}, expected_revision=rev2, spec=spec, expected_epoch=2
    )
    rec3 = store.read(key)
    assert rec3 is not None
    rev3 = rec3["lease"]["revision"]
    with pytest.raises(cr.CloserRuntimeError):  # recorded intent cannot be handed off to write
        cr.transfer_ownership(
            store, key, backup, primary, expected_revision=rev3, spec=spec, expected_epoch=2
        )
    cr.transfer_ownership(
        store,
        key,
        backup,
        primary,
        expected_revision=rev3,
        spec=spec,
        expected_epoch=2,
        reconciliation_only=True,
    )
    final = store.read(key)
    assert final is not None
    assert final["executor"]["identity"] == "primary"


def test_no_duplicate_unchanged_verification(store, monkeypatch):
    # Exercise the real Workflows collector over offline, complete REST pages.
    from scripts import check_checks_reported as producer

    from tests.test_check_checks_reported import fixture_transport

    monkeypatch.setattr(producer, "native_gh_pages", fixture_transport())
    spec = dataclasses.replace(
        _spec(action="verify"),
        repository="o/r",
        pr_number=1,
        verification_event="pull_request",
        verification_event_action="opened",
    )
    ex = _executor()
    store.claim(spec, ex, lease_deadline=datetime.now(UTC) + timedelta(hours=1))
    key = _fence_key(spec)
    payload = {"event": "pull_request", "event_action": "opened"}
    first = cr.run_bounded_action(
        store,
        key,
        ex,
        "verify_unchanged_gate",
        payload,
        spec=spec,
        expected_epoch=store.read(key)["lease"]["epoch"],
        expected_revision=store.read(key)["lease"]["revision"],
    )
    second = cr.run_bounded_action(
        store,
        key,
        ex,
        "verify_unchanged_gate",
        payload,
        spec=spec,
        expected_epoch=store.read(key)["lease"]["epoch"],
        expected_revision=store.read(key)["lease"]["revision"],
    )
    assert not first["skipped"] and second["skipped"]
    receipt = first["record"]["receipts"][-1]
    assert receipt["passed"] is True
    assert receipt["producer_result"]["schema"] == "expected-check-receipt/v1"
    assert receipt["producer_result"]["request_evidence"]
    assert receipt["source"]["check_checks_reported.py"]
    assert second["record"]["lease"]["revision"] == first["record"]["lease"]["revision"]


def test_local_verification_receipt_cache(store, monkeypatch):
    from scripts import check_checks_reported as producer

    from tests.test_check_checks_reported import fixture_transport

    monkeypatch.setattr(producer, "native_gh_pages", fixture_transport())
    spec = dataclasses.replace(
        _spec(action="verify"),
        repository="o/r",
        pr_number=1,
        verification_event="pull_request",
        verification_event_action="invalid",
    )
    ex = _executor()
    store.claim(spec, ex, lease_deadline=datetime.now(UTC) + timedelta(hours=1))
    key = _fence_key(spec)
    with pytest.raises(cr.PolicyDenied):
        cr.run_bounded_action(
            store,
            key,
            ex,
            "execute_local_verification",
            {"adapter": "fixture_static_gate", "verdict": "pass"},
            spec=spec,
            expected_epoch=store.read(key)["lease"]["epoch"],
            expected_revision=store.read(key)["lease"]["revision"],
        )
    payload = {
        "adapter": "expected_check_topology",
        "verdict": "pass",
        "event": "pull_request",
        "event_action": "invalid",
    }
    first = cr.run_bounded_action(
        store,
        key,
        ex,
        "execute_local_verification",
        payload,
        spec=spec,
        expected_epoch=store.read(key)["lease"]["epoch"],
        expected_revision=store.read(key)["lease"]["revision"],
    )
    second = cr.run_bounded_action(
        store,
        key,
        ex,
        "execute_local_verification",
        payload,
        spec=spec,
        expected_epoch=store.read(key)["lease"]["epoch"],
        expected_revision=store.read(key)["lease"]["revision"],
    )
    assert not first["skipped"] and not second["skipped"]
    assert second["record"]["receipts"][-1]["verdict"] == "UNKNOWN"
    assert second["record"]["last_verification_fingerprint"] is None


def test_github_outage_blocks_shared_mutation(tmp_path: Path) -> None:
    backend = gh.MockGitHubBackend()
    cache = cr.LocalOperationStore(tmp_path / "cache")
    remote = gh.GitHubContentsOperationStore(
        backend.request,
        "stranske/Workflows",
        outage_cache=cache,
        allow_shared_mutation=False,
    )
    spec = _spec(action="verify")
    fence = _fence_key(spec)
    rec = cr.new_operation_record(
        spec, _executor(), lease_deadline=datetime.now(UTC) + timedelta(hours=1)
    )
    cache.write_cas(
        fence, rec, expected_revision=None, authority=cr.WriteAuthority("claim", _executor(), None)
    )
    with pytest.raises(cr.PolicyDenied, match="outage"):
        remote.write_cas(
            fence,
            rec,
            expected_revision=1,
            authority=cr.WriteAuthority("owner_update", _executor(), 1),
        )


def test_github_cas_same_fence_as_local(tmp_path: Path) -> None:
    backend = gh.MockGitHubBackend()
    cache = cr.LocalOperationStore(tmp_path / "cache")
    remote = gh.GitHubContentsOperationStore(
        backend.request, "stranske/Workflows", outage_cache=cache
    )
    spec = _spec(action="verify")
    fence = _fence_key(spec)
    rec = cr.new_operation_record(
        spec, _executor("gh"), lease_deadline=datetime.now(UTC) + timedelta(hours=1)
    )
    written = remote.write_cas(
        fence,
        rec,
        expected_revision=None,
        authority=cr.WriteAuthority("claim", _executor("gh"), None),
    )
    assert written["target_fence_key"] == fence
    read_back = remote.read(fence)
    assert read_back is not None
    assert read_back["operation_key"] == rec["operation_key"]


def test_runtime_ac_guard_matches_js_semantics() -> None:
    required, labels = cr.runtime_ac_requirement(["verify:runtime-ac", "other"])
    assert required is True
    assert "verify:runtime-ac" in labels


def test_validate_minimal_fixture() -> None:
    path = REPO_ROOT / "fixtures/closer-operation/v1/minimal-operation.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    spec = cr.OperationSpec(
        repository=record["repository"],
        pr_number=record["target"]["number"],
        action=record["action"],
        head_sha=record["head_sha"],
        base_sha=record["base_sha"],
        criteria_fingerprint=record["criteria_fingerprint"],
        review_revision=record["review_revision"],
        guard_versions=record["guard_versions"],
        blocking_labels=record.get("blocking_labels", ()),
        required_capabilities=record.get("required_capabilities", ()),
    )
    assert record["target_fence_key"] == cr.canonical_target_fence_key(spec)
    assert record["operation_key"] == cr.canonical_operation_key(spec)
    errors = cr.validate_operation_record(record)
    assert errors == []


def test_cli_validate_roundtrip(tmp_path: Path) -> None:
    spec = _spec(action="verify")
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        json.dumps(
            {
                "repository": spec.repository,
                "target": {"kind": "pull_request", "number": spec.pr_number},
                "action": spec.action,
                "head_sha": spec.head_sha,
                "base_sha": spec.base_sha,
                "criteria_fingerprint": spec.criteria_fingerprint,
                "review_revision": spec.review_revision,
                "guard_versions": spec.guard_versions,
            }
        ),
        encoding="utf-8",
    )
    assert (
        cr.main(
            [
                "claim",
                "--store",
                str(tmp_path / "s"),
                "--spec",
                str(spec_path),
                "--executor-identity",
                "cli",
            ]
        )
        == 0
    )
