#!/usr/bin/env python
"""Compute and persist workflow state fingerprints.

The helper gives workflows a cheap unchanged-state gate.  Callers provide a
workflow name and a deliberately small JSON input surface; the script hashes the
canonical JSON representation, compares it with the prior stored value, and
emits GitHub Actions outputs that downstream steps can use for ``if:`` gates.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any, NamedTuple, Protocol

MARKER_VERSION = "v1"
MARKER_PREFIX = "fingerprint"


class Decision(NamedTuple):
    should_run: bool
    reason: str
    current_hash: str
    prior_hash: str | None


class FingerprintStorage(Protocol):
    def read_fingerprint(self, workflow_name: str) -> str | None: ...

    def write_fingerprint(self, workflow_name: str, fingerprint_hash: str) -> None: ...


def compute_fingerprint(workflow_name: str, inputs: dict[str, Any]) -> str:
    payload = {
        "workflow": workflow_name,
        "inputs": inputs,
        "version": MARKER_VERSION,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compare_fingerprint(
    workflow_name: str,
    current_inputs: dict[str, Any],
    storage: FingerprintStorage,
) -> Decision:
    current_hash = compute_fingerprint(workflow_name, current_inputs)
    prior_hash = storage.read_fingerprint(workflow_name)

    if prior_hash is None:
        return Decision(True, "no-prior-fingerprint", current_hash, None)
    if prior_hash == current_hash:
        return Decision(False, "fingerprint-match", current_hash, prior_hash)
    return Decision(True, "fingerprint-changed", current_hash, prior_hash)


def store_fingerprint(
    workflow_name: str,
    fingerprint_hash: str,
    storage: FingerprintStorage,
) -> None:
    storage.write_fingerprint(workflow_name, fingerprint_hash)


def _utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _marker_re(workflow_name: str) -> re.Pattern[str]:
    escaped = re.escape(workflow_name)
    return re.compile(
        rf"<!--\s*{MARKER_PREFIX}:{escaped}:{MARKER_VERSION}\s+(\{{.*?\}})\s*-->",
        re.DOTALL,
    )


def _build_marker(workflow_name: str, fingerprint_hash: str) -> str:
    payload = {"hash": fingerprint_hash, "ts": _utc_now()}
    return (
        f"<!-- {MARKER_PREFIX}:{workflow_name}:{MARKER_VERSION} "
        f"{json.dumps(payload, sort_keys=True, separators=(',', ':'))} -->"
    )


def _extract_hash(value: str | None, workflow_name: str) -> str | None:
    if not value:
        return None

    candidates: list[str] = []
    marker_match = _marker_re(workflow_name).search(value)
    if marker_match:
        candidates.append(marker_match.group(1))
    stripped = value.strip()
    if stripped.startswith("{"):
        candidates.append(stripped)

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        fingerprint_hash = payload.get("hash") if isinstance(payload, dict) else None
        if isinstance(fingerprint_hash, str) and re.fullmatch(r"[0-9a-f]{64}", fingerprint_hash):
            return fingerprint_hash
    return None


def _github_context() -> tuple[str, str]:
    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not repo:
        raise RuntimeError("GITHUB_REPOSITORY is required for GitHub storage")
    if not token:
        raise RuntimeError("GH_TOKEN or GITHUB_TOKEN is required for GitHub storage")
    return repo, token


class GitHubApi:
    def __init__(self, repo: str, token: str) -> None:
        self.repo = repo
        self.token = token
        default_api_url = "https://api." + "github.com"
        self.base_url = os.environ.get("GITHUB_API_URL", default_api_url).rstrip("/")

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        data = None
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub API {method} {path} failed: {exc.code} {detail}") from exc

        if not payload:
            return None
        return json.loads(payload)

    def paged_get(self, path: str) -> list[dict[str, Any]]:
        page = 1
        entries: list[dict[str, Any]] = []
        while True:
            separator = "&" if "?" in path else "?"
            batch = self.request("GET", f"{path}{separator}per_page=100&page={page}")
            if not isinstance(batch, list):
                raise RuntimeError(f"Expected list response from GitHub API path {path}")
            entries.extend(batch)
            if len(batch) < 100:
                return entries
            page += 1


class PrCommentStorage:
    def __init__(self, api: GitHubApi, pr_number: int) -> None:
        self.api = api
        self.pr_number = pr_number

    @classmethod
    def from_environment(cls) -> PrCommentStorage:
        repo, token = _github_context()
        return cls(GitHubApi(repo, token), _resolve_pr_number())

    def _comments(self) -> list[dict[str, Any]]:
        return self.api.paged_get(f"/repos/{self.api.repo}/issues/{self.pr_number}/comments")

    def _find_comment(self, workflow_name: str) -> dict[str, Any] | None:
        pattern = _marker_re(workflow_name)
        for comment in reversed(self._comments()):
            body = comment.get("body")
            if isinstance(body, str) and pattern.search(body):
                return comment
        return None

    def read_fingerprint(self, workflow_name: str) -> str | None:
        comment = self._find_comment(workflow_name)
        if not comment:
            return None
        body = comment.get("body")
        return _extract_hash(body if isinstance(body, str) else None, workflow_name)

    def write_fingerprint(self, workflow_name: str, fingerprint_hash: str) -> None:
        body = _build_marker(workflow_name, fingerprint_hash)
        existing = self._find_comment(workflow_name)
        if existing and existing.get("id"):
            self.api.request(
                "PATCH",
                f"/repos/{self.api.repo}/issues/comments/{existing['id']}",
                {"body": body},
            )
            return
        self.api.request(
            "POST",
            f"/repos/{self.api.repo}/issues/{self.pr_number}/comments",
            {"body": body},
        )


class RepoVariableStorage:
    def __init__(self, api: GitHubApi, variable_name: str | None = None) -> None:
        self.api = api
        self.variable_name = variable_name

    @classmethod
    def from_environment(cls, workflow_name: str) -> RepoVariableStorage:
        repo, token = _github_context()
        return cls(GitHubApi(repo, token), _variable_name(workflow_name))

    def read_fingerprint(self, workflow_name: str) -> str | None:
        variable_name = self.variable_name or _variable_name(workflow_name)
        try:
            payload = self.api.request(
                "GET",
                f"/repos/{self.api.repo}/actions/variables/{variable_name}",
            )
        except RuntimeError as exc:
            if " failed: 404 " in str(exc):
                return None
            raise
        value = payload.get("value") if isinstance(payload, dict) else None
        return _extract_hash(value if isinstance(value, str) else None, workflow_name)

    def write_fingerprint(self, workflow_name: str, fingerprint_hash: str) -> None:
        variable_name = self.variable_name or _variable_name(workflow_name)
        value = json.dumps({"hash": fingerprint_hash, "ts": _utc_now()}, sort_keys=True)
        try:
            self.api.request(
                "PATCH",
                f"/repos/{self.api.repo}/actions/variables/{variable_name}",
                {"name": variable_name, "value": value},
            )
        except RuntimeError as exc:
            if " failed: 404 " not in str(exc):
                raise
            self.api.request(
                "POST",
                f"/repos/{self.api.repo}/actions/variables",
                {"name": variable_name, "value": value},
            )


def _variable_name(workflow_name: str) -> str:
    slug = re.sub(r"[^A-Z0-9_]+", "_", workflow_name.upper()).strip("_")
    digest = hashlib.sha1(workflow_name.encode("utf-8")).hexdigest()[:12]
    prefix = "STATE_FINGERPRINT"
    max_slug_len = 100 - len(prefix) - len(digest) - 2
    slug = slug[:max_slug_len].strip("_") or "WORKFLOW"
    return f"{prefix}_{slug}_{digest}"


def _resolve_pr_number() -> int:
    if os.environ.get("PR_NUMBER"):
        return int(os.environ["PR_NUMBER"])

    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        raise RuntimeError("PR_NUMBER or GITHUB_EVENT_PATH is required for pr-comment storage")

    with open(event_path, encoding="utf-8") as handle:
        event = json.load(handle)

    pull_request = event.get("pull_request")
    if isinstance(pull_request, dict) and pull_request.get("number"):
        return int(pull_request["number"])

    issue = event.get("issue")
    if isinstance(issue, dict) and issue.get("pull_request") and issue.get("number"):
        return int(issue["number"])

    workflow_run = event.get("workflow_run")
    if isinstance(workflow_run, dict):
        prs = workflow_run.get("pull_requests")
        if isinstance(prs, list) and prs:
            number = prs[0].get("number")
            if number:
                return int(number)

    number = event.get("number")
    if number and "pull_request" in event:
        return int(number)

    raise RuntimeError("Could not resolve pull request number from event payload")


def _storage_from_name(storage_name: str, workflow_name: str) -> FingerprintStorage:
    if storage_name == "pr-comment":
        return PrCommentStorage.from_environment()
    if storage_name == "repo-variable":
        return RepoVariableStorage.from_environment(workflow_name)
    raise ValueError(f"unsupported storage backend: {storage_name}")


def _write_github_output(outputs: dict[str, str]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        for key, value in outputs.items():
            handle.write(f"{key}={value}\n")


def _compare_command(args: argparse.Namespace) -> int:
    try:
        inputs = json.loads(args.inputs)
    except json.JSONDecodeError as exc:
        print(f"invalid --inputs JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(inputs, dict):
        print("--inputs must decode to a JSON object", file=sys.stderr)
        return 2

    storage = _storage_from_name(args.storage, args.workflow)
    decision = compare_fingerprint(args.workflow, inputs, storage)

    should_run = decision.should_run
    reason = decision.reason
    if args.mode == "warning":
        print(
            "state fingerprint warning mode: "
            f"decision={decision.reason} prior={decision.prior_hash or ''} "
            f"current={decision.current_hash}",
            file=sys.stderr,
        )
        should_run = True
        reason = f"warning-mode:{decision.reason}"

    store_fingerprint(args.workflow, decision.current_hash, storage)

    outputs = {
        "should_run": "true" if should_run else "false",
        "reason": reason,
        "current_hash": decision.current_hash,
        "prior_hash": decision.prior_hash or "",
    }
    _write_github_output(outputs)
    print(json.dumps(outputs, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    compare = subparsers.add_parser("compare", help="compare current inputs with stored state")
    compare.add_argument("--workflow", required=True)
    compare.add_argument("--inputs", required=True)
    compare.add_argument("--storage", choices=["pr-comment", "repo-variable"], default="pr-comment")
    compare.add_argument("--mode", choices=["enforce", "warning"], default="enforce")
    compare.set_defaults(func=_compare_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
