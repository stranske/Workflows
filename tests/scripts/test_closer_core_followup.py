"""Independent-review follow-ups: expired-lease drain, guarded CAS, outcome classification,
context binding, and runtime-AC derivation. Offline; real processes where it matters."""

from __future__ import annotations

import dataclasses
import io
import json
import multiprocessing as mp
import subprocess
import sys
import time
import urllib.error
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from scripts import check_checks_reported as producer
from scripts import closer_operation_github as gh
from scripts import closer_runtime as cr

from tests.scripts.test_closer_portable_boundaries import NativeHTTP, auth, claim, remote
from tests.scripts.test_closer_runtime import _executor, _spec

ROOT = Path(__file__).resolve().parents[2]
HOUR = timedelta(hours=1)


@pytest.fixture(autouse=True)
def _no_live_pr_labels(monkeypatch):
    monkeypatch.setattr(cr, "fetch_live_pr_labels", lambda spec: [])


def _submitted(store, spec, ex, *, deadline=None):
    store.claim(spec, ex, lease_deadline=deadline or datetime.now(UTC) + HOUR)
    key = cr.store_key_for_spec(spec)
    cr.record_mutation_intent(
        store, key, ex, {"op": 1}, expected_revision=1, expected_epoch=1, spec=spec
    )
    return key, cr.mark_submitted(store, key, ex, expected_revision=2, expected_epoch=1, spec=spec)


def _evidence(rec, key, spec, result, digest="d" * 64):
    return cr.ReconciliationEvidence(
        rec["operation_key"],
        key,
        spec.head_sha,
        spec.action,
        result,
        "native-read",
        digest,
        "/".join(spec.verification_context()) if spec.action == "verify" else "",
    )


def _py(code: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", code, *args], cwd=ROOT, capture_output=True, text=True, timeout=60
    )


WORKER_CRASH = """
import os, sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from scripts import closer_runtime as cr
from tests.scripts.test_closer_runtime import _spec, _executor
cr.fetch_live_pr_labels = lambda spec: []
store = cr.LocalOperationStore(Path(sys.argv[1])); spec = _spec(action="merge"); ex = _executor("worker")
store.claim(spec, ex, lease_deadline=datetime.now(UTC) + timedelta(seconds=10))
key = cr.store_key_for_spec(spec)
cr.record_mutation_intent(store, key, ex, {"op": "merge"}, expected_revision=1, expected_epoch=1, spec=spec)
cr.mark_submitted(store, key, ex, expected_revision=2, expected_epoch=1, spec=spec)
os._exit(9)  # crash after submission, before any result is known
"""

OBSERVER = """
import json, sys
from pathlib import Path
from scripts import closer_runtime as cr
from scripts import check_checks_reported as producer
from tests.scripts.test_closer_runtime import _spec, _executor
store = cr.LocalOperationStore(Path(sys.argv[1])); spec = _spec(action="merge")
pr = json.loads(sys.argv[2])
producer.native_gh_pages = lambda endpoint: [pr]
key = cr.store_key_for_spec(spec); rec = store.read(key)
try:
    out = cr.run_bounded_action(store, key, _executor("observer"), "reconcile_submitted", {}, spec=spec,
        expected_epoch=rec["lease"]["epoch"], expected_revision=rec["lease"]["revision"])
    print(json.dumps(out["record"]))
except Exception as exc:
    print(json.dumps({"error": type(exc).__name__ + ": " + str(exc)})); sys.exit(4)
"""


def test_crashed_worker_expired_lease_then_independent_observer_drains(tmp_path):
    crashed = _py(WORKER_CRASH, str(tmp_path))
    assert crashed.returncode == 9, crashed.stderr
    store = cr.LocalOperationStore(tmp_path)
    spec = _spec(action="merge")
    key = cr.store_key_for_spec(spec)
    before = store.read(key)
    assert before["status"] == "submitted"
    time.sleep(10.2)
    # Latch check: every owner-path mutator is closed after expiry (expiry never retries)...
    worker = _executor("worker")
    with pytest.raises(cr.OwnershipDenied, match="expired"):
        cr.record_mutation_intent(
            store, key, worker, {"op": 2}, expected_revision=3, expected_epoch=1, spec=spec
        )
    with pytest.raises(cr.OwnershipDenied, match="expired"):
        cr.transfer_ownership(
            store,
            key,
            worker,
            _executor("x"),
            expected_revision=3,
            expected_epoch=1,
            spec=spec,
            reconciliation_only=True,
        )
    # ...but an independently scheduled observer process can still reconcile.
    head = {"sha": spec.head_sha}
    absent = _py(OBSERVER, str(tmp_path), json.dumps({"head": head}))  # `merged` absent
    assert absent.returncode == 0, absent.stdout + absent.stderr
    unknown = json.loads(absent.stdout)
    assert unknown["status"] == "uncertain"  # an absent result never proves success or no-write
    assert unknown["receipts"][-1]["result"] == "unknown"
    assert unknown["executor"]["identity"] == "observer"
    assert unknown["ownership_scope"] == "reconcile_only"
    assert unknown["lease"]["epoch"] == 2
    assert unknown["lease"]["deadline"] == before["lease"]["deadline"]  # old deadline preserved
    assert unknown["mutation_intent"] == before["mutation_intent"]
    # Old owner is fenced and cannot resume writing.
    with pytest.raises(cr.OwnershipDenied):
        cr.mark_submitted(store, key, worker, expected_revision=4, expected_epoch=1, spec=spec)
    not_observed = _py(OBSERVER, str(tmp_path), json.dumps({"head": head, "merged": False}))
    assert json.loads(not_observed.stdout)["status"] == "uncertain"
    merged = _py(
        OBSERVER,
        str(tmp_path),
        json.dumps(
            {"head": head, "merged": True, "merge_commit_sha": "f" * 40, "base": {"sha": "b" * 40}}
        ),
    )
    final = json.loads(merged.stdout)
    assert final["status"] == "succeeded"
    ctx = json.loads(final["receipts"][-1]["context"])
    assert ctx["merge_commit_sha"] == "f" * 40 and ctx["base_sha"] == "b" * 40
    assert len(final["receipts"]) == 3  # every earlier observation is retained


def test_live_lease_blocks_non_owner_recovery_and_intent_waits_for_expiry(tmp_path):
    store = cr.LocalOperationStore(tmp_path)
    spec, ex = _spec(action="verify"), _executor()
    key, rec = _submitted(store, spec, ex)
    with pytest.raises(cr.OwnershipDenied, match="live lease"):
        cr.reconcile_unknown(
            store,
            key,
            expected_revision=3,
            expected_epoch=1,
            executor=_executor("other"),
            spec=spec,
            evidence=_evidence(rec, key, spec, "not_observed"),
        )
    # past the deadline the observer may drain; evidence bound to another context is refused
    later = datetime.now(UTC) + 2 * HOUR
    bad = dataclasses.replace(
        _evidence(rec, key, spec, "not_observed"), context="pull_request/labeled"
    )
    with pytest.raises(cr.OwnershipDenied, match="not bound"):
        cr.reconcile_unknown(
            store,
            key,
            expected_revision=3,
            expected_epoch=1,
            executor=_executor("other"),
            spec=spec,
            evidence=bad,
            now=later,
        )
    out = cr.reconcile_unknown(
        store,
        key,
        expected_revision=3,
        expected_epoch=1,
        executor=_executor("other"),
        spec=spec,
        evidence=_evidence(rec, key, spec, "not_observed"),
        now=later,
    )
    assert out["status"] == "uncertain" and out["lease"]["epoch"] == 2
    again = cr.reconcile_unknown(
        store,
        key,
        expected_revision=4,
        expected_epoch=2,
        executor=_executor("other"),
        spec=spec,
        evidence=_evidence(rec, key, spec, "unknown", "e" * 64),
        now=later,
    )
    assert again["status"] == "uncertain" and len(again["receipts"]) == 2


def test_readonly_replacement_fences_old_owner_and_falls_back_and_back(tmp_path):
    store = cr.LocalOperationStore(tmp_path)
    spec, a, b = _spec(action="verify"), _executor("a"), _executor("b")
    d1 = datetime.now(UTC) + HOUR
    store.claim(spec, a, lease_deadline=d1)
    key = cr.store_key_for_spec(spec)
    original_deadline = store.read(key)["lease"]["deadline"]
    t1, t2 = datetime.now(UTC) + 2 * HOUR, datetime.now(UTC) + 4 * HOUR
    with pytest.raises(cr.OwnershipDenied, match="acknowledged"):
        cr.replace_readonly_claim(
            store,
            key,
            b,
            expected_revision=1,
            expected_epoch=1,
            spec=spec,
            new_deadline=t2,
            acknowledge_replacement=False,
            now=t1,
        )
    with pytest.raises(cr.OwnershipDenied, match="live lease"):
        cr.replace_readonly_claim(
            store,
            key,
            b,
            expected_revision=1,
            expected_epoch=1,
            spec=spec,
            new_deadline=t2,
            acknowledge_replacement=True,
        )
    rec = cr.replace_readonly_claim(
        store,
        key,
        b,
        expected_revision=1,
        expected_epoch=1,
        spec=spec,
        new_deadline=t2,
        acknowledge_replacement=True,
        now=t1,
    )
    assert rec["lease"]["epoch"] == 2 and rec["executor"]["identity"] == "b"
    assert rec["lease"]["prior_deadlines"] == [original_deadline]
    with pytest.raises(cr.OwnershipDenied):  # old owner fenced
        cr.run_bounded_action(
            store, key, a, "record_evidence", {}, spec=spec, expected_epoch=1, expected_revision=2
        )
    cr.run_bounded_action(
        store, key, b, "record_evidence", {}, spec=spec, expected_epoch=2, expected_revision=2
    )
    # fall back and back: b expires, a replaces b; exactly one owner at each epoch
    t3, t4 = datetime.now(UTC) + 5 * HOUR, datetime.now(UTC) + 8 * HOUR
    back = cr.replace_readonly_claim(
        store,
        key,
        a,
        expected_revision=3,
        expected_epoch=2,
        spec=spec,
        new_deadline=t4,
        acknowledge_replacement=True,
        now=t3,
    )
    assert back["executor"]["identity"] == "a" and back["lease"]["epoch"] == 3
    assert len(back["lease"]["prior_deadlines"]) == 2 and len(back["receipts"]) == 1
    with pytest.raises(cr.OwnershipDenied):
        cr.run_bounded_action(
            store, key, b, "record_evidence", {}, spec=spec, expected_epoch=2, expected_revision=4
        )


def test_replacement_refused_for_intent_or_merge(tmp_path):
    store = cr.LocalOperationStore(tmp_path)
    spec, a, b = _spec(action="merge"), _executor("a"), _executor("b")
    store.claim(spec, a, lease_deadline=datetime.now(UTC) + HOUR)
    key = cr.store_key_for_spec(spec)
    late = datetime.now(UTC) + 2 * HOUR
    with pytest.raises(cr.OwnershipDenied, match="read-only"):
        cr.replace_readonly_claim(
            store,
            key,
            b,
            expected_revision=1,
            expected_epoch=1,
            spec=spec,
            new_deadline=late + HOUR,
            acknowledge_replacement=True,
            now=late,
        )
    vspec = _spec(action="verify", head="1" * 40)
    vkey, _ = _submitted(store, vspec, a)
    with pytest.raises(cr.OwnershipDenied, match="no mutation intent"):
        cr.replace_readonly_claim(
            store,
            vkey,
            b,
            expected_revision=3,
            expected_epoch=1,
            spec=vspec,
            new_deadline=late + HOUR,
            acknowledge_replacement=True,
            now=late,
        )


def test_public_cas_requires_authority_and_rejects_forged_transitions(tmp_path):
    store = cr.LocalOperationStore(tmp_path)
    spec, ex, key, rec = claim(store)
    other = _executor("thief")

    def bump(**changes):
        new = json.loads(json.dumps(rec))
        new["lease"]["revision"] = 2
        for k, v in changes.items():
            new[k] = v
        return new

    with pytest.raises(TypeError):
        store.write_cas(key, bump(), expected_revision=1)  # type: ignore[call-arg]
    stolen = bump(executor={"kind": "portable_local", "identity": "thief"})
    stolen["lease"]["epoch"] = 2
    for purpose in ("owner_update", "transfer", "claim"):
        with pytest.raises(cr.OwnershipDenied):
            store.write_cas(
                key, stolen, expected_revision=1, authority=cr.WriteAuthority(purpose, other, 1)
            )
    extended = bump()
    extended["lease"]["deadline"] = "2099-01-01T00:00:00Z"
    with pytest.raises(cr.OwnershipDenied, match="deadline"):
        store.write_cas(key, extended, expected_revision=1, authority=auth(rec))
    with pytest.raises(cr.OwnershipDenied):
        store.write_cas(key, bump(status="submitted"), expected_revision=1, authority=auth(rec))
    with pytest.raises(
        cr.CloserRuntimeError, match="operation_key"
    ):  # identity fields feed the key
        store.write_cas(key, bump(head_sha="1" * 40), expected_revision=1, authority=auth(rec))
    with pytest.raises(cr.OwnershipDenied):  # live-lease, wrong writer
        store.write_cas(
            key, bump(), expected_revision=1, authority=cr.WriteAuthority("owner_update", other, 1)
        )
    with pytest.raises(cr.OwnershipDenied, match="stale epoch"):
        store.write_cas(key, bump(), expected_revision=1, authority=auth(rec, epoch=9))
    assert store.read(key) == rec


def test_cas_protects_receipts_intent_and_new_spec_only_after_drain(tmp_path):
    store = cr.LocalOperationStore(tmp_path)
    spec, ex = _spec(action="verify"), _executor()
    key, sub = _submitted(store, spec, ex)
    truncated = json.loads(json.dumps(sub))
    truncated["lease"]["revision"] = 4
    truncated["mutation_intent"] = {"op": "other"}
    with pytest.raises(cr.OwnershipDenied, match="intent"):
        store.write_cas(key, truncated, expected_revision=3, authority=auth(sub))
    # a new spec cannot replace a record that is not drained, nor arrive as submitted
    new = cr.new_operation_record(
        _spec(action="verify", head="2" * 40),
        ex,
        lease_deadline=datetime.now(UTC) + HOUR,
        epoch=2,
        revision=4,
    )
    with pytest.raises(cr.OwnershipDenied):
        store.write_cas(key, new, expected_revision=3, authority=cr.WriteAuthority("claim", ex, 1))
    new["status"] = "submitted"
    with pytest.raises(cr.OwnershipDenied):
        store.write_cas(key, new, expected_revision=3, authority=cr.WriteAuthority("claim", ex, 1))
    assert store.read(key) == sub


def _forge_worker(args):
    root, key, name = args
    store = cr.LocalOperationStore(Path(root))
    rec = store.read(key)
    forged = json.loads(json.dumps(rec))
    forged["lease"]["revision"] += 1
    forged["lease"]["epoch"] += 1
    forged["executor"] = {"kind": "portable_local", "identity": name}
    forged["lease"]["deadline"] = "2099-01-01T00:00:00Z"
    try:
        store.write_cas(
            key,
            forged,
            expected_revision=rec["lease"]["revision"],
            authority=cr.WriteAuthority(
                "owner_update", cr.ExecutorIdentity("portable_local", name), rec["lease"]["epoch"]
            ),
        )
        return "forged"
    except (cr.OwnershipDenied, cr.CasConflict):
        return "rejected"


def test_multiprocess_invalid_transitions_never_land(tmp_path):
    store = cr.LocalOperationStore(tmp_path)
    _, _, key, rec = claim(store)
    with mp.get_context("spawn").Pool(4) as pool:
        results = pool.map(_forge_worker, [(str(tmp_path), key, f"w{i}") for i in range(6)])
    assert results == ["rejected"] * 6
    assert store.read(key) == rec


# --- write outcome classification ---------------------------------------------------------


class Scripted:
    """Wrap NativeHTTP: let the PUT land (or not), then fail later GETs as scripted."""

    def __init__(self, http, *, put=None, after_put_get=None):
        self.http, self.put, self.after_put_get, self.put_calls, self.landed = (
            http,
            put,
            after_put_get,
            0,
            False,
        )

    def __call__(self, request, timeout):
        if request.method == "PUT":
            self.put_calls += 1
            if self.put == "denied":
                raise urllib.error.HTTPError(request.full_url, 403, "forbidden", {}, io.BytesIO())
            if self.put == "rate":
                raise urllib.error.HTTPError(
                    request.full_url, 403, "forbidden", {"X-RateLimit-Remaining": "0"}, io.BytesIO()
                )
            response = self.http(request, timeout)
            self.landed = True
            if self.put == "timeout_after_write":
                raise TimeoutError("response lost")
            return response
        if request.method == "GET" and self.landed and self.after_put_get:
            raise self.after_put_get(request)
        return self.http(request, timeout)


def _forbidden(request):
    return urllib.error.HTTPError(request.full_url, 403, "forbidden", {}, io.BytesIO())


def _second_write(script_kwargs):
    http = NativeHTTP()
    first = remote(http)
    spec, ex, key, rec = claim(first)
    scripted = Scripted(http, **script_kwargs)
    store = gh.GitHubContentsOperationStore(
        gh.NativeGitHubTransport("t", opener=scripted), "stranske/Workflows"
    )
    new = json.loads(json.dumps(rec))
    new["lease"]["revision"] = 2
    new["receipts"].append({"kind": "evidence", "payload": {"x": 1}})
    return scripted, store, key, rec, new, ex


@pytest.mark.parametrize("put", [None, "timeout_after_write"])
def test_write_accepted_then_readback_403_is_unknown_not_denied(put):
    scripted, store, key, rec, new, ex = _second_write({"put": put, "after_put_get": _forbidden})
    with pytest.raises(gh.UnknownOutcome) as caught:
        store.write_cas(key, new, expected_revision=1, authority=auth(rec))
    assert caught.value.no_fallback is True  # deny barrier kept, but no "definitely not written"
    assert not isinstance(caught.value, cr.PolicyDenied)
    assert scripted.put_calls == 1 and scripted.landed
    # a later independent read reconciles what actually landed
    assert remote(scripted.http).read(key) == new


def test_write_accepted_then_readback_timeout_is_unknown():
    scripted, store, key, rec, new, ex = _second_write(
        {"after_put_get": lambda request: TimeoutError("read timeout")}
    )
    with pytest.raises(gh.UnknownOutcome) as caught:
        store.write_cas(key, new, expected_revision=1, authority=auth(rec))
    assert caught.value.no_fallback is False and scripted.put_calls == 1


def test_put_origin_403_is_known_refusal_with_no_fallback():
    scripted, store, key, rec, new, ex = _second_write({"put": "denied"})
    with pytest.raises(cr.PolicyDenied) as caught:
        store.write_cas(key, new, expected_revision=1, authority=auth(rec))
    assert caught.value.no_fallback is True and scripted.put_calls == 1
    assert remote(scripted.http).read(key) == rec


def test_rate_limit_403_is_capacity_not_permission():
    scripted, store, key, rec, new, ex = _second_write({"put": "rate"})
    with pytest.raises(gh.RemoteUnavailable):
        store.write_cas(key, new, expected_revision=1, authority=auth(rec))
    assert scripted.put_calls == 1  # never auto-retried

    def limited(request):
        return urllib.error.HTTPError(
            request.full_url, 403, "rate limit", {"Retry-After": "30"}, io.BytesIO()
        )

    http = NativeHTTP()
    reader = gh.GitHubContentsOperationStore(
        gh.NativeGitHubTransport("t", opener=Scripted(http, after_put_get=limited)),
        "stranske/Workflows",
    )
    reader.bootstrap()  # branch exists
    http2 = Scripted(http)
    http2.landed = True
    http2.after_put_get = limited
    reader = gh.GitHubContentsOperationStore(
        gh.NativeGitHubTransport("t", opener=http2), "stranske/Workflows"
    )
    with pytest.raises(gh.RemoteUnavailable):
        reader.read("a" * 64)


def test_native_transport_allowlist_is_authority_refs_and_contents_only():
    key = "a" * 64
    ns = f"/repos/o/r/contents/.github/{gh.PORTABLE_NAMESPACE}/{key}.json"
    assert gh._allowed_native_call("PUT", ns)
    assert gh._allowed_native_call("GET", f"{ns}?ref={gh.PORTABLE_BRANCH}")
    assert gh._allowed_native_call("POST", "/repos/o/r/git/refs")
    for method, path in (
        ("PUT", "/repos/o/r/pulls/1/merge"),
        ("POST", "/repos/o/r/pulls/1/merge"),
        ("PUT", "/repos/o/r/contents/README.md"),
        ("POST", "/repos/o/r/issues/1/labels"),
        ("GET", "/repos/o/r/pulls/1"),
        ("DELETE", ns),
        ("PUT", ns + "/../x"),
    ):
        assert not gh._allowed_native_call(method, path), (method, path)


# --- context binding and runtime-AC -------------------------------------------------------


def test_verification_context_is_part_of_identity_and_payload_cannot_substitute():
    base = _spec(action="verify")
    synced = dataclasses.replace(
        base, verification_event="pull_request", verification_event_action="synchronize"
    )
    labeled = dataclasses.replace(
        base, verification_event="pull_request", verification_event_action="labeled"
    )
    assert len({cr.canonical_operation_key(s) for s in (base, synced, labeled)}) == 3
    assert cr.canonical_target_fence_key(synced) == cr.canonical_target_fence_key(labeled)
    rec = cr.new_operation_record(labeled, _executor(), lease_deadline=datetime.now(UTC) + HOUR)
    assert cr.validate_operation_record(rec) == []
    assert cr.canonical_operation_key(cr.spec_from_record(rec)) == cr.canonical_operation_key(
        labeled
    )
    for spec in (base, synced):  # unbound specs use the producer default, never a caller choice
        with pytest.raises(cr.PolicyDenied, match="verification_context_mismatch"):
            cr.run_verification_adapter(
                "expected_check_topology", spec, {"event_action": "labeled"}
            )
    with pytest.raises(cr.PolicyDenied, match="verification_context_mismatch"):
        cr.run_verification_adapter(
            "expected_check_topology", synced, {"event": "pull_request", "event_action": "labeled"}
        )


def test_live_labels_block_merge_even_when_caller_spec_omits_them(tmp_path, monkeypatch):
    store = cr.LocalOperationStore(tmp_path)
    spec, ex = _spec(action="merge"), _executor("orchestrator-like")
    store.claim(spec, ex, lease_deadline=datetime.now(UTC) + HOUR)
    key = cr.store_key_for_spec(spec)
    monkeypatch.setattr(cr, "fetch_live_pr_labels", lambda s: ["runtime-ac"])
    with pytest.raises(cr.PolicyDenied, match="runtime_ac_merge_blocked"):
        cr.record_mutation_intent(
            store, key, ex, {"op": "merge"}, expected_revision=1, expected_epoch=1, spec=spec
        )
    assert store.read(key)["status"] == "denied"


def test_label_fetch_failure_fails_closed_and_mark_submitted_rechecks(tmp_path, monkeypatch):
    store = cr.LocalOperationStore(tmp_path)
    spec, ex = _spec(action="merge"), _executor()
    store.claim(spec, ex, lease_deadline=datetime.now(UTC) + HOUR)
    key = cr.store_key_for_spec(spec)
    cr.record_mutation_intent(
        store, key, ex, {"op": "merge"}, expected_revision=1, expected_epoch=1, spec=spec
    )

    def unreadable(s):
        raise cr.PolicyDenied("live_labels_unavailable: down")

    monkeypatch.setattr(cr, "fetch_live_pr_labels", unreadable)
    with pytest.raises(cr.PolicyDenied, match="live_labels_unavailable"):
        cr.mark_submitted(store, key, ex, expected_revision=2, expected_epoch=1, spec=spec)
    monkeypatch.setattr(cr, "fetch_live_pr_labels", lambda s: ["verify:runtime-ac"])
    with pytest.raises(cr.PolicyDenied, match="runtime_ac_merge_blocked"):
        cr.mark_submitted(store, key, ex, expected_revision=2, expected_epoch=1, spec=spec)
    assert store.read(key)["status"] == "intent_recorded"


def test_raw_cas_cannot_submit_a_runtime_ac_merge(tmp_path):
    store = cr.LocalOperationStore(tmp_path)
    spec, ex = _spec(action="merge", labels=("runtime-ac",)), _executor()
    _, _, key, rec = claim(store, spec, ex)
    new = json.loads(json.dumps(rec))
    new.update(status="intent_recorded", mutation_intent={"op": "merge"})
    new["lease"]["revision"] = 2
    with pytest.raises(cr.PolicyDenied, match="runtime_ac_merge_blocked"):
        store.write_cas(key, new, expected_revision=1, authority=auth(rec))


def test_fetch_live_pr_labels_reads_fixed_get_producer_and_binds_head(monkeypatch):
    monkeypatch.undo()
    spec = _spec(action="merge")
    seen = []

    def pages(endpoint):
        seen.append(endpoint)
        return [{"head": {"sha": spec.head_sha}, "labels": [{"name": "Runtime-AC"}]}]

    monkeypatch.setattr(producer, "native_gh_pages", pages)
    assert cr.fetch_live_pr_labels(spec) == ["Runtime-AC"]
    assert seen == [f"repos/{spec.repository}/pulls/{spec.pr_number}"]
    monkeypatch.setattr(
        producer, "native_gh_pages", lambda e: [{"head": {"sha": "9" * 40}, "labels": []}]
    )
    with pytest.raises(cr.PolicyDenied, match="head differs"):
        cr.fetch_live_pr_labels(spec)


def test_merge_reconciliation_unreadable_evidence_is_unknown_not_traceback(monkeypatch):
    spec = _spec(action="merge")

    def broken(endpoint):
        raise producer.UnknownEvidence("gh api failed")

    monkeypatch.setattr(producer, "native_gh_pages", broken)
    ev = cr.collect_reconciliation_evidence(spec, {})
    assert ev.result == "unknown" and ev.context == "unreadable"


@pytest.mark.parametrize(
    "status,expected", [(401, False), (404, False), (500, False), (403, True), (429, True)]
)
def test_rate_limit_headers_never_reclassify_other_http_statuses(status, expected):
    error = urllib.error.HTTPError(
        "https://example.invalid",
        status,
        "rate limit",
        {"Retry-After": "30", "X-RateLimit-Remaining": "0"},
        None,
    )
    assert gh._rate_limited(error) is expected
