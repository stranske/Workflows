"""Large receipts through the real single-attempt native transport; no network writes."""

from __future__ import annotations

import base64
import copy
import io
import json
import urllib.error
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import pytest
from scripts import closer_operation_github as gh
from scripts import closer_runtime as cr

from tests.scripts.test_closer_runtime import _executor, _spec


class LargeNativeAPI:
    """Contents omits >1 MB bytes; immutable Git objects retain every written version."""

    def __init__(self):
        self.backend = gh.MockGitHubBackend()
        self.blobs = {}
        self.calls = []
        self.blob_fault = None
        self.after_metadata = None
        self.metadata_size = None

    def __call__(self, request, timeout):
        assert timeout == 30
        url = urlsplit(request.full_url)
        assert url.netloc == "api.github.com"
        assert request.get_header("Accept") == "application/vnd.github+json"
        path = url.path + ("?" + url.query if url.query else "")
        method = request.method
        self.calls.append((method, path))
        if "/git/blobs/" in path:
            assert method == "GET"
            if isinstance(self.blob_fault, int):
                raise urllib.error.HTTPError(request.full_url, self.blob_fault, "failure", {}, None)
            sha = path.rsplit("/", 1)[1]
            result = copy.deepcopy(self.blobs[sha])
            if self.blob_fault == "wrong_sha":
                result["sha"] = "f" * 40
            elif self.blob_fault == "wrong_bytes":
                raw = bytearray(base64.b64decode(result["content"]))
                raw[-1] = ord(" ")
                result["content"] = base64.b64encode(raw).decode()
        else:
            body = json.loads(request.data) if request.data else None
            result = self.backend.request(method, path, body)
            if method == "PUT":
                entry = result["content"]
                raw = base64.b64decode(entry["content"])
                self.blobs[entry["sha"]] = {**entry, "size": len(raw)}
            elif method == "GET" and "?ref=" in path:
                size = len(base64.b64decode(result["content"]))
                result = {**result, "size": self.metadata_size or size}
                if size > gh.CONTENTS_INLINE_BYTES:
                    result.update(encoding="none", content="", download_url="https://invalid.test/")
                if self.after_metadata:
                    hook, self.after_metadata = self.after_metadata, None
                    hook()
        return io.BytesIO(json.dumps(result).encode())


def setup_store():
    api = LargeNativeAPI()
    store = gh.GitHubContentsOperationStore(
        gh.NativeGitHubTransport("offline-token", opener=api), "o/r"
    )
    spec, executor = _spec(action="verify"), _executor()
    # Override the helper's repo to keep all exact native paths obvious.
    from dataclasses import replace

    spec = replace(spec, repository="o/r")
    claimed, _ = store.claim(spec, executor, lease_deadline=datetime.now(UTC) + timedelta(hours=1))
    updated = copy.deepcopy(claimed)
    updated["lease"]["revision"] += 1
    updated["receipts"].append(
        {
            "kind": "local_verification",
            "passed": False,
            "producer_result": {
                "verdict": "FAIL",
                "request_evidence": [
                    {"path": f"repos/o/r/evidence/{i}", "body": "source provenance " * 2000}
                    for i in range(62)
                ],
            },
        }
    )
    assert len(base64.b64decode(gh.encode_record_blob(updated))) > 2_000_000
    return api, store, spec, executor, claimed, updated


def write_large(store, spec, executor, claimed, updated):
    return store.write_cas(
        cr.store_key_for_spec(spec),
        updated,
        expected_revision=claimed["lease"]["revision"],
        authority=cr.WriteAuthority("owner_update", executor, claimed["lease"]["epoch"]),
    )


def test_large_write_readback_and_restart_retain_all_provenance():
    api, store, spec, executor, claimed, updated = setup_store()
    assert write_large(store, spec, executor, claimed, updated) == updated
    restarted = gh.GitHubContentsOperationStore(
        gh.NativeGitHubTransport("offline-token", opener=api), "O/R"
    )
    assert restarted.read(cr.store_key_for_spec(spec)) == updated
    assert len([c for c in api.calls if c[0] == "PUT"]) == 2
    assert len([c for c in api.calls if "/git/blobs/" in c[1]]) == 2
    assert len(updated["receipts"][0]["producer_result"]["request_evidence"]) == 62


@pytest.mark.parametrize("fault", ["wrong_sha", "wrong_bytes", 404, 403, 503])
def test_large_post_write_failure_stays_unknown_and_never_retries(fault):
    api, store, spec, executor, claimed, updated = setup_store()
    api.blob_fault = fault
    with pytest.raises(gh.UnknownOutcome) as caught:
        write_large(store, spec, executor, claimed, updated)
    assert caught.value.no_fallback is (fault == 403)
    assert len([c for c in api.calls if c[0] == "PUT"]) == 2
    expected = (
        cr.PolicyDenied
        if fault == 403
        else gh.RemoteUnavailable if isinstance(fault, int) else cr.CloserRuntimeError
    )
    with pytest.raises(expected):
        store.read(cr.store_key_for_spec(spec))
    # Failure did not erase the landed bytes or turn a blob 404 into record absence.
    assert len(api.backend.files) == 1
    api.blob_fault = None
    assert store.read(cr.store_key_for_spec(spec)) == updated
    assert len([c for c in api.calls if c[0] == "PUT"]) == 2


def test_large_read_is_bound_to_metadata_sha_when_branch_moves():
    api, store, spec, executor, claimed, updated = setup_store()
    write_large(store, spec, executor, claimed, updated)
    key = cr.store_key_for_spec(spec)
    path = gh.contents_api_path("o/r", key)
    old_meta = dict(api.backend.files[path])

    def move_branch():
        api.backend.files[path] = {**old_meta, "sha": "e" * 40}

    api.after_metadata = move_branch
    assert store.read(key) == updated
    assert api.calls[-1] == ("GET", f"/repos/o/r/git/blobs/{old_meta['sha']}")


def test_unsupported_large_metadata_refused_before_blob_fetch():
    api, store, spec, executor, claimed, updated = setup_store()
    write_large(store, spec, executor, claimed, updated)
    api.calls.clear()
    api.metadata_size = gh.MAX_GIT_BLOB_BYTES + 1
    with pytest.raises(cr.CloserRuntimeError, match="unsupported large"):
        store.read(cr.store_key_for_spec(spec))
    assert not any("/git/blobs/" in path for _, path in api.calls)


def test_blob_transport_allowlist_is_get_exact_immutable_sha_only():
    path = "/repos/o/r/git/blobs/" + "a" * 40
    assert gh._allowed_native_call("GET", path)
    assert not gh._allowed_native_call("POST", path)
    assert not gh._allowed_native_call("GET", path + "?ref=main")
    assert not gh._allowed_native_call("GET", "/repos/o/r/git/blobs/main")
    assert not gh._allowed_native_call("GET", "https://invalid.test/blob")
