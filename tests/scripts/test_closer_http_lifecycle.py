"""Core owns HTTP error responses at every native/store consumption boundary."""

from __future__ import annotations

import copy
import gc
import io
import urllib.error
from datetime import UTC, datetime, timedelta

import pytest
from scripts import closer_operation_github as gh
from scripts import closer_runtime as cr

from tests.scripts.test_closer_runtime import _executor, _spec


class TrackedBody(io.BytesIO):
    def __init__(self, *, close_error=False):
        super().__init__(b"not needed for classification")
        self.close_calls = 0
        self.close_error = close_error

    def close(self):
        self.close_calls += 1
        super().close()
        if self.close_error:
            raise RuntimeError("response close failed after releasing body")


def response_error(status, *, headers=None, close_error=False):
    body = TrackedBody(close_error=close_error)
    error = urllib.error.HTTPError(
        "https://api.github.com/repos/o/r", status, "original HTTP refusal", headers or {}, body
    )
    return error, body


@pytest.mark.parametrize("status", [401, 403, 404, 409, 422, 429, 503])
def test_native_transport_closes_response_and_preserves_same_http_error(status):
    error, body = response_error(status, headers={"X-RateLimit-Remaining": "0"})
    calls = []

    def opener(request, timeout):
        calls.append(request.method)
        raise error

    transport = gh.NativeGitHubTransport("offline-token", opener=opener)
    with pytest.raises(urllib.error.HTTPError) as caught:
        transport("GET", "/repos/o/r", None)
    assert caught.value is error and error.code == status
    assert error.headers == {"X-RateLimit-Remaining": "0"}
    assert error.reason == "original HTTP refusal"
    assert error.closed and body.closed and body.close_calls == 1
    assert calls == ["GET"]
    gc.collect()


def test_close_failure_cannot_replace_original_permission_refusal():
    error, body = response_error(403, close_error=True)

    def opener(request, timeout):
        raise error

    store = gh.GitHubContentsOperationStore(
        gh.NativeGitHubTransport("offline-token", opener=opener), "o/r"
    )
    with pytest.raises(cr.PolicyDenied) as caught:
        store.read("a" * 64)
    assert caught.value.no_fallback and caught.value.__cause__ is error
    assert error.closed and body.closed and body.close_calls == 1
    assert any("close failed: RuntimeError" in note for note in error.__notes__)


@pytest.mark.parametrize(
    "status,expected",
    [
        (401, cr.PolicyDenied),
        (403, cr.PolicyDenied),
        (429, gh.RemoteUnavailable),
        (503, gh.RemoteUnavailable),
        (404, None),
    ],
)
def test_injected_store_get_closes_before_status_classification(status, expected):
    error, body = response_error(status)
    calls = []

    def request(method, path, payload):
        calls.append((method, path))
        if "/contents/" in path:
            raise error
        if "/git/ref/" in path:
            return {"object": {"sha": "b" * 40}}
        return {"default_branch": "main"}

    store = gh.GitHubContentsOperationStore(request, "o/r")
    if expected:
        with pytest.raises(expected):
            store.read("a" * 64)
    else:
        assert store.read("a" * 64) is None
    assert error.closed and body.closed and body.close_calls == 1
    assert all(method == "GET" for method, _ in calls)


@pytest.mark.parametrize(
    "phase,status,expected",
    [
        ("put", 403, cr.PolicyDenied),
        ("put", 409, cr.CasConflict),
        ("put_landed", 503, None),
        ("readback", 403, gh.UnknownOutcome),
        ("readback", 503, gh.UnknownOutcome),
        ("readback", 404, gh.UnknownOutcome),
    ],
)
def test_put_error_cleanup_keeps_single_attempt_and_unknown_reconciliation(phase, status, expected):
    backend = gh.MockGitHubBackend()
    error, body = response_error(status)
    armed, puts, landed = False, 0, False

    def request(method, path, payload):
        nonlocal puts, landed
        if method == "PUT":
            puts += 1
            if armed and phase == "put":
                raise error
            result = backend.request(method, path, payload)
            if armed:
                landed = True
                if phase == "put_landed":
                    raise error
            return result
        if armed and landed and phase == "readback" and "/contents/" in path:
            raise error
        return backend.request(method, path, payload)

    spec, executor = _spec(action="verify"), _executor()
    store = gh.GitHubContentsOperationStore(request, spec.repository)
    old, _ = store.claim(spec, executor, lease_deadline=datetime.now(UTC) + timedelta(hours=1))
    new = copy.deepcopy(old)
    new["lease"]["revision"] += 1
    new["receipts"].append({"kind": "evidence", "payload": "retained"})
    armed = True

    def write():
        return store.write_cas(
            cr.store_key_for_spec(spec),
            new,
            expected_revision=1,
            authority=cr.WriteAuthority("owner_update", executor, 1),
        )

    if expected:
        with pytest.raises(expected) as caught:
            write()
        if phase == "readback":
            assert caught.value.no_fallback is (status == 403)
    else:
        assert write() == new  # independently observed landed PUT after lost error response
    assert error.closed and body.closed and body.close_calls == 1
    assert puts == 2  # one initial claim + one update, never a resubmission
    armed = False
    assert store.read(cr.store_key_for_spec(spec)) == (new if landed else old)
    gc.collect()


def test_branch_bootstrap_closes_post_error_before_permission_classification():
    error, body = response_error(403)
    backend = gh.MockGitHubBackend()
    initial = True

    def request(method, path, payload):
        nonlocal initial
        if method == "POST":
            raise error
        if initial and path.endswith(gh.PORTABLE_BRANCH):
            initial = False
            raise backend._error(path, 404, "absent authority branch")
        return backend.request(method, path, payload)

    with pytest.raises(cr.PolicyDenied):
        gh.GitHubContentsOperationStore(request, "o/r").bootstrap()
    assert error.closed and body.closed and body.close_calls == 1


@pytest.mark.parametrize(
    "method,branch,status",
    [("GET", gh.PORTABLE_BRANCH, 404), ("GET", "missing", 404), ("PUT", "missing", 422)],
)
def test_owned_mock_metadata_errors_release_implicit_empty_response(method, branch, status):
    backend = gh.MockGitHubBackend()
    path = "/repos/o/r/contents/example?ref=" + branch
    with pytest.raises(urllib.error.HTTPError) as caught:
        backend.request(method, path, {"branch": branch})
    assert caught.value.code == status and caught.value.closed
    assert caught.value.fp.closed
    gc.collect()
