#!/usr/bin/env python3
"""Portable Contents CAS in the existing authority branch, separate from v2.

Transport construction performs no network IO. Callers explicitly bootstrap/claim.
A local observation cache never confers shared ownership.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

from scripts import api_client
from scripts.closer_runtime import (
    CONTRACT,
    KEY_RE,
    CasConflict,
    CloserRuntimeError,
    LocalOperationStore,
    PolicyDenied,
    WriteAuthority,
    validate_cas_transition,
    validate_store_record,
)

PORTABLE_BRANCH = "keepalive-authority-state"
PORTABLE_NAMESPACE = "closer-operation-portable/v1"
RequestFn = Callable[[str, str, Mapping[str, Any] | None], Mapping[str, Any]]


class RemoteUnavailable(CloserRuntimeError):
    """Read/service unavailable; not evidence of a missing record."""


class UnknownOutcome(CloserRuntimeError):
    """A submitted write cannot yet be reconciled; never blindly retry.

    `no_fallback` is True when a post-write readback was denied: the denial barrier
    still applies, but it says nothing about whether the write landed.
    """

    def __init__(self, message: str, *, no_fallback: bool = False) -> None:
        super().__init__(message)
        self.no_fallback = no_fallback


_REPO = r"/repos/[\w.-]+/[\w.-]+"
_NATIVE_ALLOWED = (
    ("GET", re.compile(_REPO + r"(?:/git/ref/heads/[\w./-]+)?")),
    (
        "GET",
        re.compile(
            _REPO + r"/contents/\.github/" + re.escape(PORTABLE_NAMESPACE) + r"/[0-9a-f]{64}\.json"
            r"\?ref=" + re.escape(PORTABLE_BRANCH)
        ),
    ),
    (
        "PUT",
        re.compile(
            _REPO + r"/contents/\.github/" + re.escape(PORTABLE_NAMESPACE) + r"/[0-9a-f]{64}\.json"
        ),
    ),
    ("POST", re.compile(_REPO + r"/git/refs")),
)


def _allowed_native_call(method: str, path: str) -> bool:
    """Authority refs/contents only: this transport can never reach pulls/merge etc."""
    if ".." in path or "://" in path:
        return False
    return any(m == method and rx.fullmatch(path) for m, rx in _NATIVE_ALLOWED)


def _rate_limited(exc: BaseException) -> bool:
    """An authoritative 403/429 rate-limit response: capacity, not a permission grant."""
    if _status(exc) == 429:
        return True
    headers = getattr(exc, "headers", None) or {}
    try:
        get = headers.get
        if get("Retry-After") is not None or get("X-RateLimit-Remaining") == "0":
            return True
    except AttributeError:
        pass
    reason = f"{getattr(exc, 'reason', '')} {getattr(exc, 'msg', '')}".lower()
    return "rate limit" in reason


class NativeGitHubTransport:
    """Single-attempt native HTTP; never automatically retries POST/PUT.

    The injected opener is the HTTP boundary for offline conformance tests.
    """

    def __init__(self, token: str | None = None, *, opener=None) -> None:
        self.token = token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        self.opener = opener or urllib.request.urlopen

    def __call__(self, method: str, path: str, body: Mapping[str, Any] | None):
        if not _allowed_native_call(method, path):
            raise PolicyDenied("unsupported native API operation")
        if not self.token:
            raise PolicyDenied("native transport requires an independently supplied GitHub token")
        return api_client.request_json_once(method, path, self.token, body, opener=self.opener)


def contents_api_path(repository: str, store_key: str) -> str:
    if not KEY_RE.fullmatch(store_key) or not re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
        raise CloserRuntimeError("invalid repository/store key")
    return f"/repos/{repository.lower()}/contents/.github/{PORTABLE_NAMESPACE}/{store_key}.json"


def encode_record_blob(record: Mapping[str, Any]) -> str:
    return base64.b64encode((json.dumps(dict(record), sort_keys=True) + "\n").encode()).decode()


def decode_record_blob(meta: Mapping[str, Any]) -> dict[str, Any]:
    if (
        not re.fullmatch(r"[0-9a-f]{40}", str(meta.get("sha", "")))
        or meta.get("encoding") != "base64"
    ):
        raise CloserRuntimeError("invalid contents blob metadata")
    try:
        data = json.loads(base64.b64decode(str(meta["content"]).replace("\n", ""), validate=True))
    except (ValueError, KeyError) as exc:
        raise CloserRuntimeError("malformed contents blob") from exc
    if not isinstance(data, dict):
        raise CloserRuntimeError("operation record must be object")
    return data


def _status(exc):
    return getattr(exc, "status", getattr(exc, "code", None))


class GitHubContentsOperationStore(LocalOperationStore):
    """Same claim protocol as local store; GitHub blob SHA is the global fence.

    Local flock is intentionally absent: all contenders must win remote CAS.
    """

    def __init__(
        self, request: RequestFn, repository: str, *, outage_cache=None, allow_shared_mutation=True
    ):
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
            raise CloserRuntimeError("invalid repository")
        self._request = request
        self.repository = repository.lower()
        self._cache = outage_cache
        self._allow_shared = allow_shared_mutation

    def _exclusive_lock(self, store_key):
        return contextlib.nullcontext()

    def _get(self, path):
        try:
            return self._request("GET", path, None)
        except Exception as exc:
            if isinstance(exc, PolicyDenied):
                raise PolicyDenied("github permission denied; no fallback") from exc
            if _rate_limited(exc):
                raise RemoteUnavailable("github rate limited; capacity unavailable") from exc
            if _status(exc) in (401, 403):
                raise PolicyDenied("github permission denied; no fallback") from exc
            if _status(exc) == 404:
                raise
            raise RemoteUnavailable("github read unavailable") from exc

    def _branch_head(self):
        ref = self._get(f"/repos/{self.repository}/git/ref/heads/{PORTABLE_BRANCH}")
        sha = ref.get("object", {}).get("sha")
        if not re.fullmatch(r"[0-9a-f]{40}", str(sha)):
            raise RemoteUnavailable("invalid authority branch metadata")
        return sha

    def bootstrap(self) -> None:
        """Reuse authority branch or create it at current default branch head.

        No keepalive v2 contents are written or interpreted.
        """
        if not self._allow_shared:
            raise PolicyDenied("github_outage: shared mutation unavailable")
        try:
            self._branch_head()
            return
        except Exception as exc:
            if _status(exc) != 404:
                raise
        repo = self._get(f"/repos/{self.repository}")
        default = self._get(f"/repos/{self.repository}/git/ref/heads/{repo['default_branch']}")
        sha = default["object"]["sha"]
        try:
            self._request(
                "POST",
                f"/repos/{self.repository}/git/refs",
                {"ref": f"refs/heads/{PORTABLE_BRANCH}", "sha": sha},
            )
            self._branch_head()
        except Exception as exc:
            if isinstance(exc, PolicyDenied) or _status(exc) in (401, 403):
                raise PolicyDenied("github branch creation denied") from exc
            # Includes 422 (another bootstrap won) and timeout-after-write.
            try:
                if self._branch_head():
                    return
            except PolicyDenied:
                raise
            except Exception as read_exc:
                raise UnknownOutcome(
                    "branch create outcome unknown; reconcile before retry"
                ) from read_exc
            raise UnknownOutcome("branch create outcome unknown; reconcile before retry") from exc

    def _read_remote(self, store_key):
        path = contents_api_path(self.repository, store_key)
        try:
            meta = self._get(f"{path}?ref={PORTABLE_BRANCH}")
        except Exception as exc:
            if isinstance(exc, PolicyDenied):
                raise
            if _status(exc) == 404:
                # A contents 404 alone also means inaccessible repo or absent branch.
                try:
                    self._get(f"/repos/{self.repository}")
                    self._branch_head()
                except PolicyDenied:
                    raise
                except Exception as read_exc:
                    raise RemoteUnavailable("record absence not established") from read_exc
                return None, None
            raise RemoteUnavailable(
                "shared read unavailable; cache cannot grant ownership"
            ) from exc
        record = decode_record_blob(meta)
        validate_store_record(store_key, record)
        if record["repository"] != self.repository:
            raise CloserRuntimeError("record repository differs from authority repository")
        return record, meta["sha"]

    def read(self, store_key):
        record, _ = self._read_remote(store_key)
        return record

    def cached_observation(self, store_key):
        """Explicit non-authoritative diagnostic only; never used by claim/write."""
        return self._cache.read(store_key) if self._cache else None

    def _write_cas_unlocked(self, store_key, record, *, expected_revision, authority):
        return self.write_cas(
            store_key, record, expected_revision=expected_revision, authority=authority
        )

    def write_cas(
        self,
        store_key,
        record,
        *,
        expected_revision,
        authority: WriteAuthority,
        prior_blob_sha=None,
    ):
        if not self._allow_shared:
            raise PolicyDenied(
                "github_outage: shared mutation unavailable; cache cannot acquire ownership"
            )
        validate_store_record(store_key, record)
        if record["repository"] != self.repository:
            raise CloserRuntimeError("record repository mismatch")
        current, sha = self._read_remote(store_key)
        revision = (current or {}).get("lease", {}).get("revision")
        if expected_revision is None:
            if current is not None:
                raise CasConflict("create-only record already exists")
        elif current is None or revision != expected_revision:
            raise CasConflict("remote revision mismatch")
        if prior_blob_sha is not None and prior_blob_sha != sha:
            raise CasConflict("blob SHA mismatch")
        validate_cas_transition(current, record, expected_revision, authority)
        body = {
            "message": f"{CONTRACT} revision {record['lease']['revision']}",
            "content": encode_record_blob(record),
            "branch": PORTABLE_BRANCH,
        }
        if sha is not None:
            body["sha"] = sha
        # Phase 1: the PUT itself. Only a denial that originates here is a known refusal.
        put_error: Exception | None = None
        try:
            self._request("PUT", contents_api_path(self.repository, store_key), body)
        except Exception as exc:
            if _status(exc) in (409, 422):
                raise CasConflict("github contents SHA CAS lost race") from exc
            if isinstance(exc, PolicyDenied):
                raise PolicyDenied("github contents write denied; no fallback") from exc
            if _rate_limited(exc):
                raise RemoteUnavailable("github rate limited; write not accepted") from exc
            if _status(exc) in (401, 403):
                raise PolicyDenied("github contents write denied; no fallback") from exc
            put_error = exc
        # Phase 2: readback. Any failure here leaves the write unknown; never resubmit.
        try:
            observed, _ = self._read_remote(store_key)
        except Exception as read_exc:
            raise UnknownOutcome(
                "PUT outcome unknown; reconcile remote before retry",
                no_fallback=isinstance(read_exc, PolicyDenied),
            ) from read_exc
        if observed == record:
            return record
        if put_error is None:
            raise UnknownOutcome("PUT readback differs from submitted record")
        raise UnknownOutcome(
            "PUT desired record not observed; reconcile before retry"
        ) from put_error


class MockGitHubBackend:
    """Offline Contents model enforcing GitHub's create-only and blob-SHA CAS."""

    def __init__(self, *, branch=PORTABLE_BRANCH):
        self.branch = branch
        self.files = {}

    def request(self, method, path, body):
        if method == "GET" and "?ref=" not in path:
            if "/git/ref/" in path:
                return {"object": {"sha": "a" * 40}}
            return {"default_branch": "main"}
        if method == "GET":
            if path.split("?ref=", 1)[-1] != self.branch:
                raise urllib.error.HTTPError(path, 404, "branch not found", {}, None)
            entry = self.files.get(path.split("?", 1)[0])
            if entry is None:
                raise urllib.error.HTTPError(path, 404, "not found", {}, None)
            return dict(entry)
        if method == "PUT":
            if body.get("branch") != self.branch:
                raise urllib.error.HTTPError(path, 422, "invalid branch", {}, None)
            prior = self.files.get(path)
            if (prior and body.get("sha") != prior["sha"]) or (not prior and body.get("sha")):
                raise urllib.error.HTTPError(path, 409 if prior else 422, "CAS conflict", {}, None)
            raw = base64.b64decode(body["content"])
            blob_sha = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            self.files[path] = {
                "content": body["content"],
                "sha": blob_sha,
                "encoding": "base64",
            }
            return {"content": self.files[path]}
        raise CloserRuntimeError(f"unsupported mock request {method} {path}")
