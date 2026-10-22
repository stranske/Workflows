"""Offline production-boundary tests; no GitHub/network or runtime queue execution."""

from __future__ import annotations

import concurrent.futures
import dataclasses
import io
import json
import subprocess
import sys
import threading
import urllib.error
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from scripts import check_checks_reported as producer
from scripts import closer_operation_github as gh
from scripts import closer_runtime as cr

from tests.scripts.test_closer_runtime import _executor, _spec

ROOT = Path(__file__).resolve().parents[2]


def claim(store, spec=None, executor=None):
    spec, executor = spec or _spec(action="verify"), executor or _executor()
    record, _ = store.claim(spec, executor, lease_deadline=datetime.now(UTC) + timedelta(hours=1))
    return spec, executor, cr.store_key_for_spec(spec), record


def auth(record, purpose="owner_update", epoch=None):
    owner = cr.ExecutorIdentity(record["executor"]["kind"], record["executor"]["identity"])
    return cr.WriteAuthority(
        purpose, owner, None if purpose == "claim" else epoch or record["lease"]["epoch"]
    )


class NativeHTTP:
    """Fake native HTTP (including HTTPError status), not an alternate store API."""

    def __init__(self):
        self.backend = gh.MockGitHubBackend()
        self.calls = []
        self.fault = None
        self.branch_exists = True
        self.lock = threading.Lock()
        self.barrier = None
        self.read_counts = {}

    def __call__(self, request, timeout):
        assert timeout == 30
        assert urlsplit(request.full_url).netloc == "api.github.com"
        path = urlsplit(request.full_url).path
        if urlsplit(request.full_url).query:
            path += "?" + urlsplit(request.full_url).query
        method = request.method
        body = json.loads(request.data) if request.data else None
        error = None
        wait = False
        with self.lock:
            self.calls.append((method, path, body))
            if self.fault == "403":
                raise urllib.error.HTTPError(request.full_url, 403, "forbidden", {}, io.BytesIO())
            if self.fault == "read_timeout" and method == "GET":
                raise TimeoutError("read timeout")
            if self.fault in {"409", "422"} and method == "PUT":
                raise urllib.error.HTTPError(
                    request.full_url, int(self.fault), "conflict", {}, io.BytesIO()
                )
            try:
                if (
                    method == "GET"
                    and path.endswith("/git/ref/heads/" + gh.PORTABLE_BRANCH)
                    and not self.branch_exists
                ):
                    raise urllib.error.HTTPError(path, 404, "not found", {}, io.BytesIO())
                if method == "POST":
                    self.branch_exists = True
                    response = {"object": {"sha": body["sha"]}}
                else:
                    response = self.backend.request(method, path, body)
            except urllib.error.HTTPError as exc:
                error = exc
            if method == "GET" and "/contents/" in path and self.barrier:
                ident = threading.get_ident()
                self.read_counts[ident] = self.read_counts.get(ident, 0) + 1
                wait = self.read_counts[ident] <= 2
            if method in {"PUT", "POST"} and self.fault == "timeout_after_write":
                raise TimeoutError("response lost after accepted write")
        if wait:
            self.barrier.wait(timeout=5)
        if error:
            raise error
        return io.BytesIO(json.dumps(response).encode())


def remote(http, **kwargs):
    return gh.GitHubContentsOperationStore(
        gh.NativeGitHubTransport("offline-test-token", opener=http), "stranske/Workflows", **kwargs
    )


def test_native_bootstrap_reuses_branch_and_separate_namespace():
    http = NativeHTTP()
    http.branch_exists = False
    store = remote(http)
    store.bootstrap()
    store.bootstrap()
    posts = [c for c in http.calls if c[0] == "POST"]
    assert len(posts) == 1
    assert posts[0][2]["ref"] == "refs/heads/keepalive-authority-state"
    spec, ex, key, rec = claim(store)
    assert store.claim(spec, ex, lease_deadline=datetime.now(UTC) + timedelta(hours=1)) == (
        rec,
        False,
    )
    assert all("closer-operation-portable/v1/" in c[1] for c in http.calls if c[0] == "PUT")


def test_native_bootstrap_timeout_after_write_reconciles_once():
    http = NativeHTTP()
    http.branch_exists = False
    http.fault = "timeout_after_write"
    remote(http).bootstrap()
    assert sum(c[0] == "POST" for c in http.calls) == 1


@pytest.mark.parametrize("status", ["409", "422"])
def test_native_contents_conflicts_are_cas_conflicts(status):
    http = NativeHTTP()
    http.fault = status
    with pytest.raises(cr.CasConflict):
        claim(remote(http))
    assert sum(c[0] == "PUT" for c in http.calls) == 1


def test_native_two_contenders_share_global_sha_fence():
    http = NativeHTTP()
    http.barrier = threading.Barrier(2)

    def contender(name):
        try:
            _, _, _, rec = claim(remote(http), executor=_executor(name))
            return rec["executor"]["identity"]
        except (cr.OwnershipDenied, cr.CasConflict):
            return None

    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        results = list(pool.map(contender, ["one", "two"]))
    assert sum(r is not None for r in results) == 1
    assert len(http.backend.files) == 1
    puts = [c for c in http.calls if c[0] == "PUT"]
    assert len(puts) == 2 and all("sha" not in c[2] for c in puts)


def test_mock_enforces_blob_sha_even_when_revisions_equal():
    http = NativeHTTP()
    store = remote(http)
    _, _, key, record = claim(store)
    path = gh.contents_api_path(store.repository, key)
    old = dict(http.backend.files[path])
    changed = json.loads(json.dumps(record))
    changed["receipts"].append({"kind": "evidence", "payload": {"another": "writer"}})
    body = {
        "content": gh.encode_record_blob(changed),
        "sha": old["sha"],
        "branch": gh.PORTABLE_BRANCH,
    }
    http.backend.request("PUT", path, body)
    with pytest.raises(urllib.error.HTTPError) as caught:
        http.backend.request("PUT", path, body)
    assert caught.value.code == 409
    with pytest.raises(cr.CasConflict, match="create-only"):
        store.write_cas(key, record, expected_revision=None, authority=auth(record, "claim"))


@pytest.mark.parametrize(
    "fault,exception", [("403", cr.PolicyDenied), ("read_timeout", gh.RemoteUnavailable)]
)
def test_native_read_failure_never_uses_outage_cache(tmp_path, fault, exception):
    cache = cr.LocalOperationStore(tmp_path / "cache")
    _, _, key, rec = claim(cache)
    http = NativeHTTP()
    http.fault = fault
    store = remote(http, outage_cache=cache)
    assert store.cached_observation(key) == rec
    with pytest.raises(exception):
        store.read(key)
    with pytest.raises(exception):
        claim(store)
    assert not any(c[0] == "PUT" for c in http.calls)


def test_contents_404_without_accessible_branch_is_not_absence():
    http = NativeHTTP()
    http.branch_exists = False
    with pytest.raises(gh.RemoteUnavailable, match="absence"):
        claim(remote(http))
    assert not any(c[0] == "PUT" for c in http.calls)


def test_native_timeout_after_put_reconciles_exact_record_without_retry():
    http = NativeHTTP()
    http.fault = "timeout_after_write"
    store = remote(http)
    _, _, key, record = claim(store)
    assert store.read(key) == record
    assert sum(c[0] == "PUT" for c in http.calls) == 1


def test_unreconciled_timeout_is_unknown_and_restart_does_not_overwrite():
    http = NativeHTTP()
    native = gh.NativeGitHubTransport("offline", opener=http)
    wrote = False

    def request(method, path, body):
        nonlocal wrote
        if wrote and method == "GET":
            raise TimeoutError("cannot reconcile")
        if method == "PUT":
            native(method, path, body)
            wrote = True
            raise TimeoutError("after write")
        return native(method, path, body)

    with pytest.raises(gh.UnknownOutcome):
        claim(gh.GitHubContentsOperationStore(request, "stranske/Workflows"))
    # New process/store reads remote authority, rather than trusting a lost local response.
    with pytest.raises(cr.OwnershipDenied):
        claim(remote(http), executor=_executor("other"))
    assert sum(c[0] == "PUT" for c in http.calls) == 1


def test_denial_survives_new_head_and_caller_authorization_receipt(tmp_path):
    store = cr.LocalOperationStore(tmp_path)
    spec, ex, key, rec = claim(store, _spec(labels=("runtime-ac",), action="merge"))
    rec["receipts"].append(
        {
            "kind": "native_runtime_ac_authorization",
            "authorized": True,
            "guard": "v1",
            "repository": spec.repository,
            "pr_number": spec.pr_number,
        }
    )
    assert cr.basic_runner_blocks_merge(spec, "orchestrator_local", record=rec)
    with pytest.raises(cr.PolicyDenied):
        cr.record_mutation_intent(
            store, key, ex, {"merge": True}, expected_revision=1, expected_epoch=1, spec=spec
        )
    with pytest.raises(cr.OwnershipDenied, match="no_fallback"):
        claim(store, dataclasses.replace(spec, head_sha="d" * 40))
    with pytest.raises(cr.CloserRuntimeError):
        cr.transfer_ownership(
            store, key, ex, _executor("other"), expected_revision=2, expected_epoch=1, spec=spec
        )
    assert store.read(key)["denial"]["no_fallback"] is True


def test_owner_epoch_spec_are_mandatory_and_terminal_success_cannot_be_forged(tmp_path):
    store = cr.LocalOperationStore(tmp_path)
    spec, ex, key, _ = claim(store)
    with pytest.raises(TypeError):
        cr.terminalize(store, key, "succeeded", expected_revision=1)
    with pytest.raises(cr.OwnershipDenied):
        cr.terminalize(
            store, key, "unavailable", expected_revision=1, expected_epoch=2, executor=ex, spec=spec
        )
    with pytest.raises(cr.OwnershipDenied):
        cr.terminalize(
            store,
            key,
            "unavailable",
            expected_revision=1,
            expected_epoch=1,
            executor=_executor("other"),
            spec=spec,
        )
    with pytest.raises(cr.PolicyDenied):
        cr.terminalize(
            store, key, "succeeded", expected_revision=1, expected_epoch=1, executor=ex, spec=spec
        )
    with pytest.raises(cr.OwnershipDenied):
        cr.record_mutation_intent(
            store,
            key,
            ex,
            {},
            expected_revision=1,
            expected_epoch=1,
            spec=dataclasses.replace(spec, blocking_labels=("runtime-ac",)),
        )
    assert store.read(key)["lease"]["revision"] == 1


def submitted(store):
    spec, ex, key, _ = claim(store)
    cr.record_mutation_intent(
        store, key, ex, {"action": spec.action}, expected_revision=1, expected_epoch=1, spec=spec
    )
    rec = cr.mark_submitted(store, key, ex, expected_revision=2, expected_epoch=1, spec=spec)
    return spec, ex, key, rec


def test_unknown_handoff_only_allows_reconciliation(tmp_path):
    store = cr.LocalOperationStore(tmp_path)
    spec, ex, key, rec = submitted(store)
    backup = _executor("reader")
    with pytest.raises(cr.CloserRuntimeError, match="reconciliation-only"):
        cr.transfer_ownership(
            store, key, ex, backup, expected_revision=3, expected_epoch=1, spec=spec
        )
    moved = cr.transfer_ownership(
        store,
        key,
        ex,
        backup,
        expected_revision=3,
        expected_epoch=1,
        spec=spec,
        reconciliation_only=True,
    )
    assert moved["lease"]["epoch"] == 2
    with pytest.raises(cr.OwnershipDenied, match="reconciliation-only"):
        cr.record_mutation_intent(
            store, key, backup, {}, expected_revision=4, expected_epoch=2, spec=spec
        )
    with pytest.raises(cr.OwnershipDenied):
        cr.reconcile_unknown(
            store,
            key,
            expected_revision=4,
            expected_epoch=1,
            executor=ex,
            spec=spec,
            evidence=cr.ReconciliationEvidence(
                rec["operation_key"],
                key,
                spec.head_sha,
                spec.action,
                "not_observed",
                "read",
                "e" * 64,
            ),
        )
    ev = cr.ReconciliationEvidence(
        rec["operation_key"],
        key,
        spec.head_sha,
        spec.action,
        "not_observed",
        "native-read",
        "e" * 64,
        "/".join(spec.verification_context()),
    )
    out = cr.reconcile_unknown(
        store, key, expected_revision=4, expected_epoch=2, executor=backup, spec=spec, evidence=ev
    )
    assert out["status"] == "uncertain"
    assert out["ownership_scope"] == "reconcile_only"


@pytest.mark.parametrize(
    "field,value",
    [
        ("head_sha", "d" * 40),
        ("action", "merge"),
        ("target_fence_key", "e" * 64),
        ("observation_digest", "bad"),
    ],
)
def test_reconciliation_rejects_wrong_observation_binding(tmp_path, field, value):
    store = cr.LocalOperationStore(tmp_path)
    spec, ex, key, rec = submitted(store)
    ev = cr.ReconciliationEvidence(
        rec["operation_key"],
        key,
        spec.head_sha,
        spec.action,
        "desired_result_observed",
        "native-read",
        "e" * 64,
    )
    with pytest.raises(cr.OwnershipDenied, match="bound"):
        cr.reconcile_unknown(
            store,
            key,
            expected_revision=3,
            expected_epoch=1,
            executor=ex,
            spec=spec,
            evidence=dataclasses.replace(ev, **{field: value}),
        )
    assert store.read(key)["status"] == "submitted"


def test_expired_lease_never_evicts_owner_or_clears_unknown(tmp_path):
    store = cr.LocalOperationStore(tmp_path)
    spec, ex, key, rec = submitted(store)
    # Deterministic clock expiry without sleeping or rewriting the lease.
    deadline = cr._parse_iso_z(rec["lease"]["deadline"])
    with pytest.raises(cr.OwnershipDenied, match="expired"):
        cr.assert_active_lease(rec, now=deadline)
    with pytest.raises(cr.OwnershipDenied, match="expired"):
        cr.enforce_owner_lease(rec, ex, spec=spec, now=deadline + timedelta(seconds=1))
    with pytest.raises(cr.OwnershipDenied):
        claim(store, executor=_executor("takeover"))
    with pytest.raises(cr.OwnershipDenied):
        claim(store, dataclasses.replace(spec, head_sha="d" * 40))
    assert store.read(key) == rec


def test_expired_owner_cannot_resume_or_transfer(tmp_path, monkeypatch):
    store = cr.LocalOperationStore(tmp_path)
    spec, ex, key, rec = claim(store)
    monkeypatch.setattr(cr, "_utc_now", lambda: cr._parse_iso_z(rec["lease"]["deadline"]))
    with pytest.raises(cr.OwnershipDenied, match="expired"):
        claim(store, spec, ex)
    with pytest.raises(cr.OwnershipDenied, match="expired"):
        cr.transfer_ownership(
            store, key, ex, _executor("other"), expected_revision=1, expected_epoch=1, spec=spec
        )
    assert store.read(key) == rec


@pytest.mark.parametrize("corrupt", ["epoch", "extra", "key", "criteria", "deadline", "denial"])
def test_schema_and_store_boundaries_reject_malformed_records(tmp_path, corrupt):
    store = cr.LocalOperationStore(tmp_path)
    spec = _spec(action="verify")
    key = cr.store_key_for_spec(spec)
    rec = cr.new_operation_record(
        spec, _executor(), lease_deadline=datetime.now(UTC) + timedelta(hours=1)
    )
    if corrupt == "epoch":
        rec["lease"]["epoch"] = False
    if corrupt == "extra":
        rec["unknown_field"] = "not in schema"
    if corrupt == "key":
        rec["target_fence_key"] = "f" * 64
    if corrupt == "criteria":
        rec["criteria_fingerprint"] = "d" * 64
    if corrupt == "deadline":
        rec["lease"]["deadline"] = "tomorrow"
    if corrupt == "denial":
        rec["status"] = "denied"
    with pytest.raises(cr.CloserRuntimeError):
        store.write_cas(key, rec, expected_revision=None, authority=auth(rec, "claim"))
    store._path(key).write_text(json.dumps(rec))
    with pytest.raises(cr.CloserRuntimeError):
        store.read(key)


def test_native_gh_complete_page_transport_and_cli(monkeypatch, tmp_path):
    from tests.test_check_checks_reported import fixture_transport

    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, json.dumps([[{"id": 1}], [{"id": 2}]]), "")

    monkeypatch.setattr(producer.subprocess, "run", fake_run)
    pages = producer.native_gh_pages("repos/o/r/pulls/1/files?per_page=100")
    assert len(pages) == 2
    assert calls[0][:7] == [
        "gh",
        "api",
        "--method",
        "GET",
        "--paginate",
        "--slurp",
        "repos/o/r/pulls/1/files?per_page=100",
    ]
    monkeypatch.setattr(producer, "native_gh_pages", fixture_transport())
    output = tmp_path / "receipt.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_checks_reported.py",
            "--repo",
            "o/r",
            "--pr",
            "1",
            "--head",
            "a" * 40,
            "--event",
            "pull_request",
            "--action",
            "opened",
            "--transport",
            "native-gh",
            "--output",
            str(output),
        ],
    )
    assert producer.main() == 0
    rec = json.loads(output.read_text())
    assert rec["transport"]["kind"] == "native-gh"
    assert rec["transport"]["sha256"]
    assert rec["evidence_complete"] and rec["merge_authorization"] is False
    assert "presence_reporter" not in rec


def test_real_subprocess_crash_after_submission_keeps_unknown_fence(tmp_path):
    code = """
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from scripts import closer_runtime as cr
from tests.scripts.test_closer_runtime import _spec, _executor
s=cr.LocalOperationStore(Path(sys.argv[1])); spec=_spec(action="verify"); ex=_executor("crashed")
r,_=s.claim(spec,ex,lease_deadline=datetime.now(UTC)+timedelta(hours=1)); key=cr.store_key_for_spec(spec)
cr.record_mutation_intent(s,key,ex,{"action":"verify"},expected_revision=1,expected_epoch=1,spec=spec)
cr.mark_submitted(s,key,ex,expected_revision=2,expected_epoch=1,spec=spec)
print("SUBMITTED",flush=True)
sys.stdin.read()
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", code, str(tmp_path)],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout.readline().strip() == "SUBMITTED"
        proc.kill()
        assert proc.wait(timeout=10) != 0
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.communicate(timeout=10)
    restart = """
import json,sys
from pathlib import Path
from scripts import closer_runtime as cr
from tests.scripts.test_closer_runtime import _spec,_executor
s=cr.LocalOperationStore(Path(sys.argv[1])); spec=_spec(action="verify"); key=cr.store_key_for_spec(spec)
r=s.read(key)
try:
 cr.record_mutation_intent(s,key,_executor("crashed"),{},expected_revision=3,expected_epoch=1,spec=spec)
except cr.CloserRuntimeError:
 print(json.dumps({"status":r["status"],"revision":r["lease"]["revision"],"retry_blocked":True}))
"""
    result = subprocess.run(
        [sys.executable, "-c", restart, str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    assert json.loads(result.stdout) == {
        "status": "submitted",
        "revision": 3,
        "retry_blocked": True,
    }


def test_real_subprocess_crash_before_atomic_replace_preserves_prior_record(tmp_path):
    store = cr.LocalOperationStore(tmp_path)
    spec, _, key, original = claim(store)
    code = """
import os,sys
from pathlib import Path
from scripts import closer_runtime as cr
s=cr.LocalOperationStore(Path(sys.argv[1])); key=sys.argv[2]; r=s.read(key)
r["lease"]["revision"]+=1
original=os.replace
def stop_before_replace(*args):
 print("TEMP_FSYNCED",flush=True)
 sys.stdin.read()
 original(*args)
os.replace=stop_before_replace
s.write_cas(key,r,expected_revision=1,authority=cr.WriteAuthority("owner_update",cr.ExecutorIdentity(r["executor"]["kind"],r["executor"]["identity"]),1))
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", code, str(tmp_path), key],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout.readline().strip() == "TEMP_FSYNCED"
        proc.kill()
        proc.wait(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.communicate(timeout=10)
    assert cr.LocalOperationStore(tmp_path).read(key) == original
    assert list(tmp_path.glob("cas-*.json"))  # ignored partial attempt, never authority


def test_bounded_reconciliation_ignores_caller_fabricated_success(tmp_path, monkeypatch):
    from tests.test_check_checks_reported import fixture_transport

    store = cr.LocalOperationStore(tmp_path)
    spec = dataclasses.replace(
        _spec(action="verify"),
        repository="o/r",
        pr_number=1,
        verification_event="pull_request",
        verification_event_action="opened",
    )
    ex = _executor()
    _, _, key, _ = claim(store, spec, ex)
    cr.record_mutation_intent(store, key, ex, {}, expected_revision=1, expected_epoch=1, spec=spec)
    cr.mark_submitted(store, key, ex, expected_revision=2, expected_epoch=1, spec=spec)
    monkeypatch.setattr(producer, "native_gh_pages", fixture_transport())
    forged = {
        "event": "pull_request",
        "event_action": "typo",
        "verdict": "PASS",
        "mutation_observed": True,
        "result": "desired_result_observed",
        "observation_digest": "e" * 64,
    }
    # The caller cannot substitute a different context than the operation-bound one.
    with pytest.raises(cr.PolicyDenied, match="verification_context_mismatch"):
        cr.run_bounded_action(
            store,
            key,
            ex,
            "reconcile_submitted",
            forged,
            spec=spec,
            expected_epoch=1,
            expected_revision=3,
        )
    assert store.read(key)["lease"]["revision"] == 3
    forged["event_action"] = "opened"
    out = cr.run_bounded_action(
        store,
        key,
        ex,
        "reconcile_submitted",
        forged,
        spec=spec,
        expected_epoch=1,
        expected_revision=3,
    )
    assert out["record"]["status"] == "succeeded"
    assert out["record"]["receipts"][-1]["observation_digest"] != "e" * 64


def test_merge_reconciliation_reads_bound_actual_result(monkeypatch):
    spec = _spec(action="merge")
    pr = {"head": {"sha": spec.head_sha}, "merged": False}
    requests = []

    def pages(endpoint):
        requests.append(endpoint)
        return [pr]

    monkeypatch.setattr(producer, "native_gh_pages", pages)
    assert (
        cr.collect_reconciliation_evidence(spec, {"mutation_observed": True}).result
        == "not_observed"
    )
    pr["merged"] = True
    assert cr.collect_reconciliation_evidence(spec, {}).result == "desired_result_observed"
    pr["head"]["sha"] = "d" * 40
    with pytest.raises(cr.OwnershipDenied, match="different target head"):
        cr.collect_reconciliation_evidence(spec, {})
    assert requests == [f"repos/{spec.repository}/pulls/{spec.pr_number}"] * 3


def test_topology_fail_is_not_cached_and_context_change_is_not_reused(tmp_path, monkeypatch):
    from tests.test_check_checks_reported import fixture_transport

    store = cr.LocalOperationStore(tmp_path)
    spec = dataclasses.replace(
        _spec(action="verify"),
        repository="o/r",
        pr_number=1,
        verification_event="pull_request",
        verification_event_action="opened",
    )
    ex = _executor()
    _, _, key, _ = claim(store, spec, ex)
    actual = fixture_transport()

    def missing_check(endpoint):
        pages = actual(endpoint)
        if "/check-runs?" in endpoint:
            return [{"total_count": 0, "check_runs": []}]
        return pages

    monkeypatch.setattr(producer, "native_gh_pages", missing_check)
    payload = {"event": "pull_request", "event_action": "opened"}
    for revision in [1, 2]:
        out = cr.run_bounded_action(
            store,
            key,
            ex,
            "verify_expected_checks",
            payload,
            spec=spec,
            expected_epoch=1,
            expected_revision=revision,
        )
        assert not out["skipped"]
        assert out["record"]["receipts"][-1]["verdict"] == "FAIL"
        assert out["record"]["last_verification_fingerprint"] is None
    monkeypatch.setattr(producer, "native_gh_pages", actual)
    passed = cr.run_bounded_action(
        store,
        key,
        ex,
        "verify_expected_checks",
        payload,
        spec=spec,
        expected_epoch=1,
        expected_revision=3,
    )
    assert passed["record"]["receipts"][-1]["passed"] is True
    with pytest.raises(cr.OwnershipDenied):
        cr.run_bounded_action(
            store,
            key,
            ex,
            "verify_expected_checks",
            payload,
            spec=dataclasses.replace(spec, criteria_fingerprint="d" * 64),
            expected_epoch=1,
            expected_revision=4,
        )
    with pytest.raises(cr.OwnershipDenied, match="stale bounded-action"):
        cr.run_bounded_action(
            store,
            key,
            ex,
            "verify_expected_checks",
            payload,
            spec=spec,
            expected_epoch=2,
            expected_revision=4,
        )


def test_evidence_payload_cannot_inject_reserved_receipt_kind(tmp_path):
    store = cr.LocalOperationStore(tmp_path)
    spec, ex, key, _ = claim(store)
    out = cr.run_bounded_action(
        store,
        key,
        ex,
        "record_evidence",
        {"kind": "local_verification", "passed": True},
        spec=spec,
        expected_epoch=1,
        expected_revision=1,
    )
    assert out["record"]["receipts"][-1]["kind"] == "evidence"
    assert out["record"]["receipts"][-1]["payload"]["passed"] is True


def test_store_rejects_illegal_success_and_revision_boundaries(tmp_path):
    store = cr.LocalOperationStore(tmp_path)
    spec, ex, key, original = claim(store)
    bad = json.loads(json.dumps(original))
    bad["status"] = "succeeded"
    bad["lease"]["revision"] = 2
    with pytest.raises(cr.OwnershipDenied, match="illegal"):
        store.write_cas(key, bad, expected_revision=1, authority=auth(original))
    bad["status"] = "claimed"
    bad["lease"]["revision"] = 3
    with pytest.raises(cr.CasConflict, match="exactly once"):
        store.write_cas(key, bad, expected_revision=1, authority=auth(original))
    assert store.read(key) == original


def test_native_failed_page_command_is_unknown_not_partial_evidence(monkeypatch):
    def incomplete(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, '[{"id": 1}]', "HTTP 403")

    monkeypatch.setattr(producer.subprocess, "run", incomplete)
    with pytest.raises(producer.UnknownEvidence):
        producer.native_gh_pages("repos/o/r/pulls/1/files?per_page=100")


def test_native_update_race_uses_observed_blob_sha():
    http = NativeHTTP()
    store = remote(http)
    _, _, key, record = claim(store)
    path = gh.contents_api_path(store.repository, key)
    original_sha = http.backend.files[path]["sha"]
    http.barrier = threading.Barrier(2)

    def update(name):
        updated = json.loads(json.dumps(record))
        updated["lease"]["revision"] = 2
        updated["receipts"].append({"kind": "evidence", "payload": {"writer": name}})
        try:
            remote(http).write_cas(key, updated, expected_revision=1, authority=auth(record))
            return True
        except cr.CasConflict:
            return False

    # Only one pre-write read per contender, then readback: synchronize first reads.
    original_barrier = http.barrier

    class FirstReadOnly:
        def wait(self, timeout):
            ident = threading.get_ident()
            if http.read_counts[ident] == 1:
                original_barrier.wait(timeout=timeout)

    http.barrier = FirstReadOnly()
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(update, ["one", "two"]))
    assert outcomes.count(True) == 1
    puts = [c for c in http.calls if c[0] == "PUT"]
    assert len(puts) == 3  # initial claim plus two conditional update attempts
    assert all(c[2]["sha"] == original_sha for c in puts[1:])
    http.barrier = None
    assert store.read(key)["lease"]["revision"] == 2


@pytest.mark.parametrize("method", ["PUT", "POST"])
def test_native_write_permission_denial_is_no_fallback(method):
    http = NativeHTTP()
    if method == "POST":
        http.branch_exists = False
    native = gh.NativeGitHubTransport("offline", opener=http)

    def denied_write(verb, path, body):
        if verb == method:
            raise urllib.error.HTTPError(path, 403, "forbidden", {}, io.BytesIO())
        return native(verb, path, body)

    store = gh.GitHubContentsOperationStore(denied_write, "stranske/Workflows")
    with pytest.raises(cr.PolicyDenied) as caught:
        store.bootstrap() if method == "POST" else claim(store)
    assert caught.value.no_fallback
    assert not http.backend.files


def test_unknown_bootstrap_outcome_does_not_retry_post():
    http = NativeHTTP()
    http.branch_exists = False
    native = gh.NativeGitHubTransport("offline", opener=http)
    posts = 0

    def lost_post(verb, path, body):
        nonlocal posts
        if verb == "POST":
            posts += 1
            raise TimeoutError("outcome unknown")
        return native(verb, path, body)

    with pytest.raises(gh.UnknownOutcome):
        gh.GitHubContentsOperationStore(lost_post, "stranske/Workflows").bootstrap()
    assert posts == 1
    assert not http.branch_exists
