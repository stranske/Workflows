import hashlib
import io
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from scripts import state_fingerprint


class MemoryStorage:
    def __init__(self, value: str | None = None) -> None:
        self.value = value
        self.writes: list[str] = []

    def read_fingerprint(self, workflow_name: str) -> str | None:
        return state_fingerprint._extract_hash(self.value, workflow_name)

    def write_fingerprint(self, workflow_name: str, fingerprint_hash: str) -> None:
        self.value = state_fingerprint._build_marker(workflow_name, fingerprint_hash)
        self.writes.append(fingerprint_hash)


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


class FakeApi:
    def __init__(self, values: dict[str, object] | None = None) -> None:
        self.repo = "owner/repo"
        self.values = values or {}
        self.requests: list[tuple[str, str, dict | None]] = []

    def request(self, method: str, path: str, body: dict | None = None) -> object:
        self.requests.append((method, path, body))
        key = f"{method} {path}"
        value = self.values.get(key)
        if isinstance(value, Exception):
            raise value
        return value

    def paged_get(self, path: str) -> list[dict]:
        """Simplified stand-in for GitHubApi.paged_get: callers (PrCommentStorage)
        only care about the final assembled list, not the page-by-page HTTP
        mechanics -- those are pinned separately against the real GitHubApi
        below. Bookkeeping goes through the same `requests` log as `request()`
        so callers can assert on it uniformly."""
        self.requests.append(("GET", path, None))
        key = f"GET {path}"
        value = self.values.get(key)
        if isinstance(value, Exception):
            raise value
        return [] if value is None else value  # type: ignore[return-value]


def test_compute_fingerprint_canonicalizes_key_order() -> None:
    first = state_fingerprint.compute_fingerprint("wf", {"b": 2, "a": {"d": 4, "c": 3}})
    second = state_fingerprint.compute_fingerprint("wf", {"a": {"c": 3, "d": 4}, "b": 2})

    assert first == second


def test_compare_detects_changed_inputs() -> None:
    prior = state_fingerprint.compute_fingerprint("wf", {"head_sha": "old"})
    storage = MemoryStorage(state_fingerprint._build_marker("wf", prior))

    decision = state_fingerprint.compare_fingerprint("wf", {"head_sha": "new"}, storage)

    assert decision.should_run is True
    assert decision.reason == "fingerprint-changed"
    assert decision.prior_hash == prior
    assert decision.current_hash != prior


def test_compare_skips_when_state_is_unchanged() -> None:
    current = {"head_sha": "abc", "labels": ["autofix"]}
    prior = state_fingerprint.compute_fingerprint("wf", current)
    storage = MemoryStorage(state_fingerprint._build_marker("wf", prior))

    decision = state_fingerprint.compare_fingerprint("wf", current, storage)

    assert decision.should_run is False
    assert decision.reason == "fingerprint-match"
    assert decision.prior_hash == decision.current_hash


def test_missing_marker_is_first_run_behavior() -> None:
    storage = MemoryStorage()

    decision = state_fingerprint.compare_fingerprint("wf", {"head_sha": "abc"}, storage)

    assert decision.should_run is True
    assert decision.reason == "no-prior-fingerprint"
    assert decision.prior_hash is None


def test_warning_mode_bypasses_skip_and_logs_delta(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    current = {"head_sha": "abc"}
    prior = state_fingerprint.compute_fingerprint("wf", current)
    storage = MemoryStorage(state_fingerprint._build_marker("wf", prior))

    monkeypatch.setattr(state_fingerprint, "_storage_from_name", lambda _name, _workflow: storage)

    exit_code = state_fingerprint.main(
        [
            "compare",
            "--workflow",
            "wf",
            "--inputs",
            json.dumps(current),
            "--storage",
            "pr-comment",
            "--mode",
            "warning",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "state fingerprint warning mode" in captured.err
    outputs = json.loads(captured.out)
    assert outputs["should_run"] == "true"
    assert outputs["reason"] == "warning-mode:fingerprint-match"
    assert storage.writes == []


def test_enforce_mode_does_not_rewrite_matching_fingerprint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    current = {"head_sha": "abc"}
    prior = state_fingerprint.compute_fingerprint("wf", current)
    storage = MemoryStorage(state_fingerprint._build_marker("wf", prior))

    monkeypatch.setattr(state_fingerprint, "_storage_from_name", lambda _name, _workflow: storage)

    exit_code = state_fingerprint.main(
        [
            "compare",
            "--workflow",
            "wf",
            "--inputs",
            json.dumps(current),
            "--storage",
            "pr-comment",
        ]
    )

    outputs = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert outputs["should_run"] == "false"
    assert outputs["reason"] == "fingerprint-match"
    assert storage.writes == []


def test_store_command_persists_current_hash(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    storage = MemoryStorage()
    fingerprint = "d" * 64

    monkeypatch.setattr(state_fingerprint, "_storage_from_name", lambda _name, _workflow: storage)

    exit_code = state_fingerprint.main(
        [
            "store",
            "--workflow",
            "wf",
            "--hash",
            fingerprint,
            "--storage",
            "pr-comment",
        ]
    )

    outputs = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert outputs["stored"] == "true"
    assert storage.writes == [fingerprint]


def test_pr_comment_marker_includes_visible_guidance() -> None:
    marker = state_fingerprint._build_marker("wf", "a" * 64)

    assert marker.startswith("Workflow state fingerprint for wf. Do not edit.")
    assert state_fingerprint._extract_hash(marker, "wf") == "a" * 64


def test_malformed_prior_marker_is_tolerated() -> None:
    storage = MemoryStorage('<!-- fingerprint:wf:v1 {"hash": -->')

    decision = state_fingerprint.compare_fingerprint("wf", {"head_sha": "abc"}, storage)

    assert decision.should_run is True
    assert decision.reason == "no-prior-fingerprint"
    assert decision.prior_hash is None


def test_extract_hash_accepts_raw_json_storage_value() -> None:
    fingerprint_hash = "a" * 64

    assert (
        state_fingerprint._extract_hash(json.dumps({"hash": fingerprint_hash}), "wf")
        == fingerprint_hash
    )


def test_variable_name_is_stable_and_within_github_limit() -> None:
    workflow_name = "Verifier " + ("very-long-name-" * 20)

    first = state_fingerprint._variable_name(workflow_name)
    second = state_fingerprint._variable_name(workflow_name)

    assert first == second
    assert first.startswith("STATE_FINGERPRINT_VERIFIER_")
    assert len(first) <= 100


def test_repo_variable_storage_reads_existing_variable() -> None:
    fingerprint_hash = "b" * 64
    api = FakeApi(
        {
            "GET /repos/owner/repo/actions/variables/STATE_FINGERPRINT_TEST": {
                "value": json.dumps({"hash": fingerprint_hash})
            }
        }
    )
    storage = state_fingerprint.RepoVariableStorage(api, "STATE_FINGERPRINT_TEST")  # type: ignore[arg-type]

    assert storage.read_fingerprint("wf") == fingerprint_hash


def test_repo_variable_storage_creates_missing_variable() -> None:
    api = FakeApi(
        {
            "PATCH /repos/owner/repo/actions/variables/STATE_FINGERPRINT_TEST": RuntimeError(
                "GitHub API PATCH /repos/owner/repo/actions/variables/STATE_FINGERPRINT_TEST failed: 404 missing"
            )
        }
    )
    storage = state_fingerprint.RepoVariableStorage(api, "STATE_FINGERPRINT_TEST")  # type: ignore[arg-type]

    storage.write_fingerprint("wf", "c" * 64)

    assert api.requests[0][0] == "PATCH"
    assert api.requests[1][0] == "POST"
    assert api.requests[1][1] == "/repos/owner/repo/actions/variables"


def test_github_api_wraps_url_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_url_error(*args: object, **kwargs: object) -> None:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(state_fingerprint.urllib.request, "urlopen", raise_url_error)

    api = state_fingerprint.GitHubApi("owner/repo", "token")
    with pytest.raises(RuntimeError, match=r"GitHub API GET /repos/owner/repo failed:"):
        api.request("GET", "/repos/owner/repo")


def test_github_api_wraps_json_decode_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        state_fingerprint.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(b"{not json"),
    )

    api = state_fingerprint.GitHubApi("owner/repo", "token")
    with pytest.raises(
        RuntimeError, match=r"GitHub API GET /repos/owner/repo returned invalid JSON:"
    ):
        api.request("GET", "/repos/owner/repo")


def test_main_catches_unexpected_exceptions(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def raise_value_error(_name: str, _workflow: str) -> MemoryStorage:
        raise ValueError("storage exploded")

    monkeypatch.setattr(state_fingerprint, "_storage_from_name", raise_value_error)

    exit_code = state_fingerprint.main(
        ["compare", "--workflow", "wf", "--inputs", "{}", "--storage", "pr-comment"]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err.strip() == "storage exploded"


# ---------------------------------------------------------------------------
# Everything below closes gaps left after the tests above: the JSON-decode
# failure branch of _extract_hash, _github_context, the body/error/pagination
# paths of GitHubApi, the entire PrCommentStorage class (previously exercised
# only through MemoryStorage/RepoVariableStorage fakes, never itself),
# _resolve_pr_number (entirely untested), _storage_from_name's error path,
# and _write_github_output. All are pure or fake-backed -- no real network
# calls, no real GitHub state.
# ---------------------------------------------------------------------------


def test_extract_hash_ignores_marker_with_invalid_json() -> None:
    """A marker comment whose captured JSON blob fails to parse is treated as
    "no fingerprint" rather than raising. The existing malformed-marker test
    never reaches this branch: a marker missing its closing brace fails the
    regex before JSON parsing is even attempted, so the try/except around
    json.loads was entirely unexercised.
    """
    value = "<!-- fingerprint:wf:v1 {not: valid, json} -->"
    assert state_fingerprint._extract_hash(value, "wf") is None


def test_extract_hash_ignores_raw_value_with_invalid_json() -> None:
    """A storage value that looks like raw JSON (starts with '{') but fails to
    parse reaches the same JSONDecodeError branch via the second candidate
    path -- distinct from the marker-comment path above, since a raw storage
    value never passes through the marker regex at all.
    """
    assert state_fingerprint._extract_hash("{not valid json", "wf") is None


def test_extract_hash_ignores_malformed_hash_value() -> None:
    """A payload whose `hash` field parses fine as JSON but isn't a 64-hex-char
    string must still be treated as absent, not returned verbatim -- guards
    against a truncated or corrupted value being silently accepted as a real
    fingerprint.
    """
    marker = state_fingerprint._build_marker("wf", "a" * 64)
    corrupted = marker.replace("a" * 64, "not-a-real-hash")
    assert state_fingerprint._extract_hash(corrupted, "wf") is None


def test_github_context_raises_without_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.setenv("GH_TOKEN", "token")

    with pytest.raises(RuntimeError, match="GITHUB_REPOSITORY is required"):
        state_fingerprint._github_context()


def test_github_context_raises_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="GH_TOKEN or GITHUB_TOKEN is required"):
        state_fingerprint._github_context()


def test_github_context_prefers_gh_token_over_github_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GH_TOKEN takes precedence when both are set -- pins the `or` order in
    `os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")`.
    """
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GH_TOKEN", "gh-token-value")
    monkeypatch.setenv("GITHUB_TOKEN", "github-token-value")

    assert state_fingerprint._github_context() == ("owner/repo", "gh-token-value")


def test_github_context_falls_back_to_github_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "fallback-token")

    assert state_fingerprint._github_context() == ("owner/repo", "fallback-token")


def test_github_api_sends_json_body_with_content_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """A request with a body must be JSON-encoded and receive an explicit
    Content-Type header. The existing direct-GitHubApi tests only exercise
    the no-body GET path (they test error handling), so a broken PATCH/POST
    body encoding could regress unnoticed.
    """
    captured: dict[str, object] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: float | None = None) -> FakeResponse:
        captured["data"] = request.data
        captured["content_type"] = request.get_header("Content-type")
        return FakeResponse(b'{"ok": true}')

    monkeypatch.setattr(state_fingerprint.urllib.request, "urlopen", fake_urlopen)

    api = state_fingerprint.GitHubApi("owner/repo", "token")
    result = api.request("POST", "/repos/owner/repo/issues/1/comments", {"body": "hi"})

    assert captured["content_type"] == "application/json"
    assert json.loads(captured["data"]) == {"body": "hi"}  # type: ignore[arg-type]
    assert result == {"ok": True}


def test_github_api_wraps_http_error_with_response_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_http_error(*args: object, **kwargs: object) -> None:
        raise urllib.error.HTTPError(
            "https://api.github.com/repos/owner/repo",
            404,
            "Not Found",
            {},  # type: ignore[arg-type]
            io.BytesIO(b"no such repo"),
        )

    monkeypatch.setattr(state_fingerprint.urllib.request, "urlopen", raise_http_error)

    api = state_fingerprint.GitHubApi("owner/repo", "token")
    with pytest.raises(
        RuntimeError, match=r"GitHub API GET /repos/owner/repo failed: 404 no such repo"
    ):
        api.request("GET", "/repos/owner/repo")


def test_github_api_request_returns_none_for_empty_response_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        state_fingerprint.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(b""),
    )

    api = state_fingerprint.GitHubApi("owner/repo", "token")

    assert api.request("DELETE", "/repos/owner/repo/x") is None


def test_paged_get_stops_at_first_short_page_and_uses_query_separator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pins two things at once: the pagination stop condition (a page with
    fewer than 100 items ends the loop) and the '?' vs '&' query-separator
    choice, by requesting a path that already carries a query string.
    """
    api = state_fingerprint.GitHubApi("owner/repo", "token")
    calls: list[str] = []
    pages = {
        1: [{"id": i} for i in range(100)],
        2: [{"id": 100}, {"id": 101}],
    }

    def fake_request(method: str, path: str, body: dict | None = None) -> list[dict]:
        calls.append(path)
        page = int(path.rsplit("page=", 1)[1])
        return pages[page]

    monkeypatch.setattr(api, "request", fake_request)

    entries = api.paged_get("/repos/owner/repo/issues/1/comments?direction=asc")

    assert len(entries) == 102
    assert calls == [
        "/repos/owner/repo/issues/1/comments?direction=asc&per_page=100&page=1",
        "/repos/owner/repo/issues/1/comments?direction=asc&per_page=100&page=2",
    ]


def test_paged_get_rejects_non_list_response(monkeypatch: pytest.MonkeyPatch) -> None:
    api = state_fingerprint.GitHubApi("owner/repo", "token")
    monkeypatch.setattr(api, "request", lambda method, path, body=None: {"not": "a list"})

    with pytest.raises(RuntimeError, match="Expected list response"):
        api.paged_get("/repos/owner/repo/issues/1/comments")


def test_pr_comment_storage_prefers_most_recent_matching_comment() -> None:
    """GitHub's issues-comments API returns comments oldest-first; _find_comment
    must walk them in reverse so a newer fingerprint comment always wins over
    a stale one left by an earlier run on the same PR.
    """
    old_marker = state_fingerprint._build_marker("wf", "a" * 64)
    new_marker = state_fingerprint._build_marker("wf", "b" * 64)
    api = FakeApi(
        {
            "GET /repos/owner/repo/issues/5/comments": [
                {"id": 1, "body": old_marker},
                {"id": 2, "body": new_marker},
            ],
        }
    )
    storage = state_fingerprint.PrCommentStorage(api, 5)  # type: ignore[arg-type]

    assert storage.read_fingerprint("wf") == "b" * 64


def test_pr_comment_storage_read_fingerprint_returns_none_without_match() -> None:
    api = FakeApi(
        {
            "GET /repos/owner/repo/issues/5/comments": [
                {"id": 1, "body": "an unrelated comment"},
            ],
        }
    )
    storage = state_fingerprint.PrCommentStorage(api, 5)  # type: ignore[arg-type]

    assert storage.read_fingerprint("wf") is None


def test_pr_comment_storage_write_patches_existing_comment() -> None:
    existing_marker = state_fingerprint._build_marker("wf", "a" * 64)
    api = FakeApi(
        {
            "GET /repos/owner/repo/issues/5/comments": [
                {"id": 42, "body": existing_marker},
            ],
        }
    )
    storage = state_fingerprint.PrCommentStorage(api, 5)  # type: ignore[arg-type]

    storage.write_fingerprint("wf", "b" * 64)

    method, path, payload = api.requests[-1]
    assert method == "PATCH"
    assert path == "/repos/owner/repo/issues/comments/42"
    assert state_fingerprint._extract_hash(payload["body"], "wf") == "b" * 64  # type: ignore[index]


def test_pr_comment_storage_write_posts_new_comment_when_absent() -> None:
    api = FakeApi({"GET /repos/owner/repo/issues/5/comments": []})
    storage = state_fingerprint.PrCommentStorage(api, 5)  # type: ignore[arg-type]

    storage.write_fingerprint("wf", "c" * 64)

    method, path, payload = api.requests[-1]
    assert method == "POST"
    assert path == "/repos/owner/repo/issues/5/comments"
    assert state_fingerprint._extract_hash(payload["body"], "wf") == "c" * 64  # type: ignore[index]


def test_pr_comment_storage_from_environment_wires_repo_token_and_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GH_TOKEN", "token-value")
    monkeypatch.setenv("PR_NUMBER", "99")

    storage = state_fingerprint.PrCommentStorage.from_environment()

    assert storage.pr_number == 99
    assert storage.api.repo == "owner/repo"
    assert storage.api.token == "token-value"


def test_resolve_pr_number_prefers_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PR_NUMBER", "42")

    assert state_fingerprint._resolve_pr_number() == 42


def test_resolve_pr_number_reads_pull_request_event(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("PR_NUMBER", raising=False)
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps({"pull_request": {"number": 7}}), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))

    assert state_fingerprint._resolve_pr_number() == 7


def test_resolve_pr_number_reads_issue_comment_event(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("PR_NUMBER", raising=False)
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps({"issue": {"pull_request": {"url": "..."}, "number": 9}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))

    assert state_fingerprint._resolve_pr_number() == 9


def test_resolve_pr_number_reads_workflow_run_event(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("PR_NUMBER", raising=False)
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps({"workflow_run": {"pull_requests": [{"number": 11}]}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))

    assert state_fingerprint._resolve_pr_number() == 11


def test_resolve_pr_number_reads_top_level_number_when_pull_request_key_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The final fallback checks for the *key* `pull_request`, not a truthy
    value: an event with a top-level `number` and `pull_request: null` still
    resolves. That is easy to accidentally break by testing truthiness of the
    value instead of membership of the key, so it is pinned explicitly.
    """
    monkeypatch.delenv("PR_NUMBER", raising=False)
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps({"number": 13, "pull_request": None}), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))

    assert state_fingerprint._resolve_pr_number() == 13


def test_resolve_pr_number_falls_through_when_workflow_run_has_no_usable_pr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """workflow_run.pull_requests can be present but empty, or non-empty with a
    falsy `number` on its first entry -- both must fall through to the final
    unresolved-event error rather than raising an unrelated exception (e.g.
    IndexError or TypeError) or returning a bogus PR number.
    """
    monkeypatch.delenv("PR_NUMBER", raising=False)
    event_path = tmp_path / "event.json"

    event_path.write_text(json.dumps({"workflow_run": {"pull_requests": []}}), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    with pytest.raises(RuntimeError, match="Could not resolve pull request number"):
        state_fingerprint._resolve_pr_number()

    event_path.write_text(
        json.dumps({"workflow_run": {"pull_requests": [{"number": None}]}}), encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="Could not resolve pull request number"):
        state_fingerprint._resolve_pr_number()


def test_resolve_pr_number_raises_without_any_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PR_NUMBER", raising=False)
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)

    with pytest.raises(RuntimeError, match="PR_NUMBER or GITHUB_EVENT_PATH is required"):
        state_fingerprint._resolve_pr_number()


def test_resolve_pr_number_raises_when_event_has_no_pr_reference(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("PR_NUMBER", raising=False)
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps({"action": "push"}), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))

    with pytest.raises(RuntimeError, match="Could not resolve pull request number"):
        state_fingerprint._resolve_pr_number()


def test_storage_from_name_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError, match="unsupported storage backend: bogus"):
        state_fingerprint._storage_from_name("bogus", "wf")


def test_write_github_output_appends_lines_to_target_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output_path = tmp_path / "github_output.txt"
    output_path.write_text("existing=1\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))

    state_fingerprint._write_github_output({"should_run": "true", "reason": "fingerprint-changed"})

    assert output_path.read_text(encoding="utf-8") == (
        "existing=1\nshould_run=true\nreason=fingerprint-changed\n"
    )


def test_write_github_output_is_a_noop_without_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    # Must not raise even though there is nowhere to write.
    state_fingerprint._write_github_output({"key": "value"})


def test_variable_name_falls_back_to_workflow_placeholder_when_slug_empties() -> None:
    """A workflow name that sanitizes to an empty slug (e.g. only punctuation)
    must still produce a valid, non-empty variable name via the WORKFLOW
    fallback rather than a name with a blank segment.
    """
    digest = hashlib.sha1(b"!!!").hexdigest()[:12]

    assert state_fingerprint._variable_name("!!!") == f"STATE_FINGERPRINT_WORKFLOW_{digest}"


def test_repo_variable_storage_read_returns_none_for_missing_variable() -> None:
    """A 404 on read means "no prior fingerprint" -- distinct from the 404
    handling in write_fingerprint (which creates the variable); this is the
    read side and was entirely untested.
    """
    api = FakeApi(
        {
            "GET /repos/owner/repo/actions/variables/STATE_FINGERPRINT_TEST": RuntimeError(
                "GitHub API GET /repos/owner/repo/actions/variables/STATE_FINGERPRINT_TEST "
                "failed: 404 missing"
            )
        }
    )
    storage = state_fingerprint.RepoVariableStorage(api, "STATE_FINGERPRINT_TEST")  # type: ignore[arg-type]

    assert storage.read_fingerprint("wf") is None


def test_repo_variable_storage_read_treats_permission_error_as_no_prior_fingerprint(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A 401/403 on read means the token can't see repo variables -- treated as
    "no prior fingerprint" (should_run=true) rather than a hard failure, with
    a warning so the misconfiguration is visible in workflow logs. Also pins
    the `_storage_unavailable` flag this sets, which write_fingerprint
    consumes (see the skip test below).
    """
    api = FakeApi(
        {
            "GET /repos/owner/repo/actions/variables/STATE_FINGERPRINT_TEST": RuntimeError(
                "GitHub API GET /repos/owner/repo/actions/variables/STATE_FINGERPRINT_TEST "
                "failed: 403 Resource not accessible by integration"
            )
        }
    )
    storage = state_fingerprint.RepoVariableStorage(api, "STATE_FINGERPRINT_TEST")  # type: ignore[arg-type]

    result = storage.read_fingerprint("wf")

    assert result is None
    assert storage._storage_unavailable is True  # type: ignore[attr-defined]
    assert "storage unavailable" in capsys.readouterr().err


def test_repo_variable_storage_read_reraises_unexpected_errors() -> None:
    api = FakeApi(
        {
            "GET /repos/owner/repo/actions/variables/STATE_FINGERPRINT_TEST": RuntimeError(
                "GitHub API GET /repos/owner/repo/actions/variables/STATE_FINGERPRINT_TEST "
                "failed: 500 internal error"
            )
        }
    )
    storage = state_fingerprint.RepoVariableStorage(api, "STATE_FINGERPRINT_TEST")  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="failed: 500"):
        storage.read_fingerprint("wf")


def test_repo_variable_storage_write_skips_when_previously_marked_unavailable() -> None:
    """Once a read has failed with 401/403 on a storage instance, a later write
    on that *same* instance must not attempt any API call at all -- pins the
    short-circuit at the top of write_fingerprint that avoids a doomed write
    after a known-bad token.
    """
    api = FakeApi(
        {
            "GET /repos/owner/repo/actions/variables/STATE_FINGERPRINT_TEST": RuntimeError(
                "GitHub API GET ... failed: 401 Bad credentials"
            )
        }
    )
    storage = state_fingerprint.RepoVariableStorage(api, "STATE_FINGERPRINT_TEST")  # type: ignore[arg-type]
    storage.read_fingerprint("wf")

    storage.write_fingerprint("wf", "d" * 64)

    assert api.requests == [
        ("GET", "/repos/owner/repo/actions/variables/STATE_FINGERPRINT_TEST", None)
    ]


def test_repo_variable_storage_write_skips_on_permission_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A fresh storage instance (no prior read) whose PATCH itself comes back
    401/403 must warn and return rather than raise or attempt a POST.
    """
    api = FakeApi(
        {
            "PATCH /repos/owner/repo/actions/variables/STATE_FINGERPRINT_TEST": RuntimeError(
                "GitHub API PATCH ... failed: 403 Resource not accessible by integration"
            )
        }
    )
    storage = state_fingerprint.RepoVariableStorage(api, "STATE_FINGERPRINT_TEST")  # type: ignore[arg-type]

    storage.write_fingerprint("wf", "e" * 64)

    assert len(api.requests) == 1
    assert api.requests[0][0] == "PATCH"
    assert "write skipped" in capsys.readouterr().err


def test_repo_variable_storage_write_reraises_unexpected_errors() -> None:
    api = FakeApi(
        {
            "PATCH /repos/owner/repo/actions/variables/STATE_FINGERPRINT_TEST": RuntimeError(
                "GitHub API PATCH ... failed: 500 internal error"
            )
        }
    )
    storage = state_fingerprint.RepoVariableStorage(api, "STATE_FINGERPRINT_TEST")  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="failed: 500"):
        storage.write_fingerprint("wf", "f" * 64)


def test_storage_from_name_dispatches_pr_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    """_storage_from_name's two valid branches were never actually exercised:
    every other test either monkeypatches this function away or constructs
    the storage class directly, bypassing the dispatcher itself.
    """
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setenv("PR_NUMBER", "1")

    storage = state_fingerprint._storage_from_name("pr-comment", "wf")

    assert isinstance(storage, state_fingerprint.PrCommentStorage)
    assert storage.pr_number == 1


def test_storage_from_name_dispatches_repo_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GH_TOKEN", "token")

    storage = state_fingerprint._storage_from_name("repo-variable", "wf")

    assert isinstance(storage, state_fingerprint.RepoVariableStorage)


def test_compare_command_rejects_invalid_inputs_json(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = state_fingerprint.main(
        ["compare", "--workflow", "wf", "--inputs", "{not json", "--storage", "pr-comment"]
    )

    assert exit_code == 2
    assert "invalid --inputs JSON" in capsys.readouterr().err


def test_compare_command_rejects_non_object_inputs(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = state_fingerprint.main(
        ["compare", "--workflow", "wf", "--inputs", "[1, 2, 3]", "--storage", "pr-comment"]
    )

    assert exit_code == 2
    assert "--inputs must decode to a JSON object" in capsys.readouterr().err


def test_store_command_rejects_malformed_hash(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = state_fingerprint.main(
        ["store", "--workflow", "wf", "--hash", "not-a-hash", "--storage", "pr-comment"]
    )

    assert exit_code == 2
    assert "--hash must be a 64-character hex SHA-256 fingerprint" in capsys.readouterr().err
