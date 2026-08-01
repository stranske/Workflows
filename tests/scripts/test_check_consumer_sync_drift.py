import json
from datetime import UTC, datetime

from scripts import check_consumer_sync_drift
from scripts.sync_manifest_compiler import (
    ManifestEntry,
    SkipRepo,
    compile_manifest,
)


def test_comparable_lines_ignores_leading_comment_and_blank_headers() -> None:
    """maint-68 syncs header-insensitively; the drift checker must match so a
    header-only difference is not reported as eternal drift (review E1)."""
    a = "# header one\n\n# header two\nbody 1\nbody 2\n"
    b = "# a DIFFERENT header\nbody 1\nbody 2\n"
    assert check_consumer_sync_drift.comparable_lines(
        a
    ) == check_consumer_sync_drift.comparable_lines(b)
    # A real body difference is still detected.
    c = "# header\nbody 1\nCHANGED\n"
    assert check_consumer_sync_drift.comparable_lines(
        a
    ) != check_consumer_sync_drift.comparable_lines(c)
    # Only LEADING comment/blank lines are stripped; mid-file comments are kept.
    assert check_consumer_sync_drift.comparable_lines("body\n# mid\nmore\n") == [
        "body",
        "# mid",
        "more",
    ]


def test_build_report_returns_machine_readable_counts() -> None:
    token_diagnostics = {
        "schema": "workflows-drift-token-selection/v1",
        "attempted_sources": ["SERVICE_BOT_PAT"],
        "selected_source": "SERVICE_BOT_PAT",
    }
    report = check_consumer_sync_drift.build_report(
        repos=["owner/b", "owner/a"],
        drift={"owner/b: .github/workflows/a.yml"},
        missing={"owner/a: .github/scripts/a.js"},
        errors=set(),
        obsolete={"owner/a: old.yml"},
        token_diagnostics=token_diagnostics,
    )

    assert report["schema"] == "workflows-consumer-sync-drift/v1"
    assert report["status"] == "drift"
    assert report["repo_count"] == 2
    assert report["counts"] == {
        "drift": 1,
        "missing": 1,
        "errors": 0,
        "obsolete": 1,
    }
    assert report["repo_summaries"] == {
        "owner/a": {"drift": 0, "missing": 1, "errors": 0, "obsolete": 1},
        "owner/b": {"drift": 1, "missing": 0, "errors": 0, "obsolete": 0},
    }
    assert report["repo_summary_count"] == 2
    assert report["top_repo_gaps"] == [
        {"repo": "owner/a", "total": 2, "drift": 0, "missing": 1, "errors": 0, "obsolete": 1},
        {"repo": "owner/b", "total": 1, "drift": 1, "missing": 0, "errors": 0, "obsolete": 0},
    ]
    assert report["path_prefix_counts"] == {
        "drift": {".github/workflows": 1},
        "missing": {".github/scripts": 1},
        "errors": {},
        "obsolete": {"old.yml": 1},
    }
    assert report["follow_up"] == {
        "workflow": "maint-68-sync-consumer-repos.yml",
        "all_repos_command": (
            "gh workflow run maint-68-sync-consumer-repos.yml --repo stranske/Workflows --ref main"
        ),
        "targeted_repos_command": (
            "gh workflow run maint-68-sync-consumer-repos.yml "
            "--repo stranske/Workflows --ref main -f repos=owner/a,owner/b"
        ),
    }
    assert report["summary_limits"]["content_error_threshold_per_repo"] == 5
    assert report["sync_remediation"]["state"] == "drift"
    assert report["sync_remediation"]["repo_states"]["owner/a"]["state"] == "untracked_drift"
    assert report["drift"] == ["owner/b: .github/workflows/a.yml"]
    assert report["token_diagnostics"] == token_diagnostics


def test_token_candidates_deduplicates_without_exposing_values() -> None:
    candidates = check_consumer_sync_drift.token_candidates(
        {
            "OWNER_PR_PAT": "same-token",
            "SERVICE_BOT_PAT": "service-token",
            "GH_TOKEN": "same-token",
            "GITHUB_TOKEN": "same-token",
        }
    )

    assert candidates == [
        {"source": "SERVICE_BOT_PAT", "token": "service-token"},
        {"source": "OWNER_PR_PAT", "token": "same-token"},
    ]


def _make_entry(
    source: str = "AGENTS.md",
    target: str | None = None,
    sync_mode: str | None = None,
    skip_repos: tuple = (),
    overwrite_repos: tuple = (),
    is_directory: bool = False,
    template_sync: str | None = None,
    section: str = "workflows",
) -> ManifestEntry:
    return ManifestEntry(
        source=source,
        resolved_source=source,
        target=target if target is not None else source,
        description="",
        sync_mode=sync_mode,
        skip_repos=skip_repos,
        overwrite_repos=overwrite_repos,
        is_directory=is_directory,
        template_sync=template_sync,
        delivery="copy",
        section=section,
        content_sha256="sha256:" + "a" * 64,
        effect_fingerprint="sha256:" + "b" * 64,
    )


def test_manifest_skip_reason_supports_repo_specific_policy() -> None:
    entry = _make_entry(
        source="AGENTS.md",
        skip_repos=(SkipRepo(repo="owner/custom", reason="Uses historical Agents.md casing"),),
    )

    assert (
        check_consumer_sync_drift.manifest_skip_reason(entry, "owner/custom")
        == "Uses historical Agents.md casing"
    )
    assert check_consumer_sync_drift.manifest_skip_reason(entry, "owner/standard") == ""


def test_manifest_skip_reason_uses_default_for_empty_reason() -> None:
    entry = _make_entry(
        source="AGENTS.md",
        skip_repos=(SkipRepo(repo="owner/custom", reason=""),),
    )
    assert (
        check_consumer_sync_drift.manifest_skip_reason(entry, "owner/custom")
        == "Manifest skip for repo"
    )


def test_repo_overwrites_create_only_supports_template_override() -> None:
    entry = _make_entry(sync_mode="create_only", overwrite_repos=("stranske/Template",))

    assert check_consumer_sync_drift.repo_overwrites_create_only(entry, "stranske/Template")
    assert not check_consumer_sync_drift.repo_overwrites_create_only(entry, "stranske/Counter_Risk")


def test_build_report_surfaces_manifest_skips_without_failing() -> None:
    report = check_consumer_sync_drift.build_report(
        repos=["owner/custom"],
        drift=set(),
        missing=set(),
        errors=set(),
        obsolete=set(),
        skipped={"owner/custom: AGENTS.md (Uses historical Agents.md casing)"},
    )

    assert report["status"] == "converged"
    assert report["counts"] == {"drift": 0, "missing": 0, "errors": 0, "obsolete": 0}
    assert report["skip_count"] == 1
    assert report["skipped"] == ["owner/custom: AGENTS.md (Uses historical Agents.md casing)"]
    assert report["sync_remediation"]["state"] == "converged"


def test_build_report_marks_current_sync_pr_as_covered() -> None:
    report = check_consumer_sync_drift.build_report(
        repos=["owner/repo"],
        drift={"owner/repo: .github/workflows/a.yml"},
        missing=set(),
        errors=set(),
        obsolete=set(),
        open_sync_prs=[
            {
                "repo": "owner/repo",
                "number": 12,
                "url": "https://github.com/owner/repo/pull/12",
                "branch": "sync/workflows-aaaaaaaaaaaa",
                "head_repo": "owner/repo",
                "updated_at": "2026-04-26T01:00:00Z",
            }
        ],
        current_plan_id="sha256:" + "a" * 64,
        now=datetime(2026, 4, 26, 2, 0, tzinfo=UTC),
    )

    assert report["status"] == "covered"
    assert report["sync_remediation"]["expected_branch"] == "sync/workflows-aaaaaaaaaaaa"
    assert report["sync_remediation"]["repo_states"]["owner/repo"]["state"] == "covered"


def test_build_report_blocks_unattributed_errors_and_empty_repo_sets() -> None:
    report = check_consumer_sync_drift.build_report(
        repos=["owner/repo"],
        drift={"owner/repo: .github/workflows/a.yml"},
        missing=set(),
        errors={"sync-manifest.yml not found"},
        obsolete=set(),
    )

    assert report["status"] == "drift"
    assert report["sync_remediation"]["repo_states"]["owner/repo"]["state"] == "blocked"
    assert report["sync_remediation"]["global_errors"] == ["sync-manifest.yml not found"]

    # A global error must outrank the "no attributed gaps -> converged" branch,
    # otherwise an unattributable comparison failure reads as a clean repo.
    no_local_drift = check_consumer_sync_drift.build_report(
        repos=["owner/repo"],
        drift=set(),
        missing=set(),
        errors={"sync-manifest.yml not found"},
        obsolete=set(),
    )
    assert no_local_drift["sync_remediation"]["repo_states"]["owner/repo"]["state"] == "blocked"

    empty = check_consumer_sync_drift.build_report(
        repos=[], drift=set(), missing=set(), errors=set(), obsolete=set()
    )
    assert empty["status"] == "drift"
    assert empty["sync_remediation"]["global_errors"] == [
        "no registered consumer repositories supplied"
    ]


def test_build_report_rejects_stale_or_untrusted_coverage() -> None:
    base_pr = {
        "repo": "owner/repo",
        "number": 12,
        "branch": "sync/workflows-aaaaaaaaaaaa",
        "head_repo": "owner/repo",
    }
    report = check_consumer_sync_drift.build_report(
        repos=["owner/repo"],
        drift={"owner/repo: .github/workflows/a.yml"},
        missing=set(),
        errors=set(),
        obsolete=set(),
        open_sync_prs=[{**base_pr, "updated_at": "2026-04-24T01:00:00Z"}],
        current_plan_id="sha256:" + "a" * 64,
        now=datetime(2026, 4, 26, 2, 0, tzinfo=UTC),
    )
    assert report["sync_remediation"]["repo_states"]["owner/repo"]["state"] == "stale"

    untrusted = check_consumer_sync_drift.build_report(
        repos=["owner/repo"],
        drift={"owner/repo: .github/workflows/a.yml"},
        missing=set(),
        errors=set(),
        obsolete=set(),
        open_sync_prs=[
            {
                **base_pr,
                "head_repo": "fork/repo",
                "updated_at": "2026-04-26T01:00:00Z",
            }
        ],
        current_plan_id="sha256:" + "a" * 64,
        now=datetime(2026, 4, 26, 2, 0, tzinfo=UTC),
    )
    assert untrusted["sync_remediation"]["repo_states"]["owner/repo"]["state"] == "untracked_drift"


def test_parse_github_timestamp_rejects_naive_values() -> None:
    assert check_consumer_sync_drift.parse_github_timestamp("2026-04-26T01:00:00") is None


def test_fetch_open_sync_prs_filters_to_workflows_sync_branches() -> None:
    class Response:
        status_code = 200

        def json(self) -> list[dict[str, object]]:
            return [
                {
                    "number": 5,
                    "title": "ordinary",
                    "html_url": "https://github.com/owner/repo/pull/5",
                    "head": {
                        "ref": "feature/example",
                        "sha": "bad",
                        "repo": {"full_name": "owner/repo"},
                    },
                },
                {
                    "number": 6,
                    "title": "sync",
                    "html_url": "https://github.com/owner/repo/pull/6",
                    "head": {
                        "ref": "sync/workflows-abc123",
                        "sha": "good",
                        "repo": {"full_name": "owner/repo"},
                    },
                    "created_at": "2026-04-26T01:00:00Z",
                    "updated_at": "2026-04-26T02:00:00Z",
                },
                {
                    "number": 7,
                    "title": "newer sync",
                    "html_url": "https://github.com/owner/repo/pull/7",
                    "head": {
                        "ref": "sync/workflows-def456",
                        "sha": "newer",
                        "repo": {"full_name": "owner/repo"},
                    },
                    "created_at": "2026-04-26T03:00:00Z",
                    "updated_at": "2026-04-26T04:00:00Z",
                },
            ]

    class Session:
        requested_urls: list[str] = []

        def get(self, url: str) -> Response:
            self.requested_urls.append(url)
            return Response()

    session = Session()

    prs, error = check_consumer_sync_drift.fetch_open_sync_prs(session, "owner/repo")

    assert error is None
    assert session.requested_urls == [
        "https://api.github.com/repos/owner/repo/pulls?state=open&per_page=50"
    ]
    assert prs == [
        {
            "repo": "owner/repo",
            "number": 7,
            "title": "newer sync",
            "url": "https://github.com/owner/repo/pull/7",
            "branch": "sync/workflows-def456",
            "head_sha": "newer",
            "head_repo": "owner/repo",
            "created_at": "2026-04-26T03:00:00Z",
            "updated_at": "2026-04-26T04:00:00Z",
        },
        {
            "repo": "owner/repo",
            "number": 6,
            "title": "sync",
            "url": "https://github.com/owner/repo/pull/6",
            "branch": "sync/workflows-abc123",
            "head_sha": "good",
            "head_repo": "owner/repo",
            "created_at": "2026-04-26T01:00:00Z",
            "updated_at": "2026-04-26T02:00:00Z",
        },
    ]


def test_select_read_token_rejects_rate_limited_candidate() -> None:
    class Response:
        def __init__(self, status_code: int, message: str = "", remaining: str = "42") -> None:
            self.status_code = status_code
            self.headers = {"x-ratelimit-remaining": remaining}
            self._message = message

        def json(self) -> dict[str, str]:
            return {"message": self._message}

    class Session:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}

        def get(self, url: str) -> Response:
            token = self.headers["Authorization"].removeprefix("Bearer ")
            if token == "rate-limited":
                if "/contents/" in url:
                    return Response(403, "API rate limit exceeded", "0")
                return Response(200)
            if token == "service-token":
                return Response(200)
            return Response(403, "Resource not accessible by token")

    session, diagnostics = check_consumer_sync_drift.select_read_token(
        candidates=[
            {"source": "OWNER_PR_PAT", "token": "rate-limited"},
            {"source": "SERVICE_BOT_PAT", "token": "service-token"},
        ],
        repos=["owner/repo"],
        paths=[".github/workflows/agents.yml"],
        session_factory=Session,
    )

    assert session is not None
    assert diagnostics["selected_source"] == "SERVICE_BOT_PAT"
    assert diagnostics["rejected"] == [
        {
            "source": "OWNER_PR_PAT",
            "reason": (
                "content preflight failed for owner/repo/.github/workflows/agents.yml: rate_limited"
            ),
        }
    ]


def test_select_read_token_reports_no_usable_token() -> None:
    class Response:
        status_code = 403
        headers = {"x-ratelimit-remaining": "42"}

        def json(self) -> dict[str, str]:
            return {"message": "Resource not accessible by token"}

    class Session:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}

        def get(self, _url: str) -> Response:
            return Response()

    session, diagnostics = check_consumer_sync_drift.select_read_token(
        candidates=[{"source": "GITHUB_TOKEN", "token": "repo-token"}],
        repos=["owner/private"],
        paths=[".github/workflows/agents.yml"],
        session_factory=Session,
    )

    assert session is None
    assert diagnostics["error"] == "no_usable_token"
    assert diagnostics["selected_source"] == ""
    assert diagnostics["rejected"] == [
        {
            "source": "GITHUB_TOKEN",
            "reason": (
                "repo preflight failed for owner/private: "
                "HTTP 403: Resource not accessible by token"
            ),
        }
    ]


def test_probe_targets_samples_each_manifest_section(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    workflow = (
        tmp_path
        / "templates"
        / "consumer-repo"
        / ".github"
        / "workflows"
        / "agents-weekly-metrics.yml"
    )
    script = tmp_path / ".github" / "scripts" / "keepalive_gate.js"
    docs = tmp_path / "templates" / "consumer-repo" / "docs" / "AGENT_ISSUE_FORMAT.md"
    workflow.parent.mkdir(parents=True)
    script.parent.mkdir(parents=True)
    docs.parent.mkdir(parents=True)
    workflow.write_text("workflow\n", encoding="utf-8")
    script.write_text("script\n", encoding="utf-8")
    docs.write_text("docs\n", encoding="utf-8")

    manifest_path = tmp_path / ".github" / "sync-manifest.yml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        "\n".join(
            [
                "version: 1",
                "workflows:",
                "  - source: .github/workflows/agents-weekly-metrics.yml",
                "    description: Metrics",
                "scripts:",
                "  - source: .github/scripts/keepalive_gate.js",
                "    description: Gate",
                "docs:",
                "  - source: docs/AGENT_ISSUE_FORMAT.md",
                "    description: Format",
                "",
            ]
        ),
        encoding="utf-8",
    )
    compiled = compile_manifest(manifest_path)

    assert check_consumer_sync_drift.probe_targets(compiled, ["workflows", "scripts", "docs"]) == [
        ".github/workflows/agents-weekly-metrics.yml",
        ".github/scripts/keepalive_gate.js",
        "docs/AGENT_ISSUE_FORMAT.md",
    ]


def test_write_report_json_creates_parent_directory(tmp_path) -> None:
    output = tmp_path / "artifacts" / "consumer-sync-drift-report.json"
    report = check_consumer_sync_drift.build_report(
        repos=["owner/repo"],
        drift=set(),
        missing=set(),
        errors=set(),
        obsolete=set(),
    )

    check_consumer_sync_drift.write_report_json(str(output), report)

    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded["schema"] == "workflows-consumer-sync-drift/v1"
    assert loaded["status"] == "converged"


def test_write_summary_markdown_groups_and_bounds_items(tmp_path) -> None:
    output = tmp_path / "summary.md"
    drift = {f"owner/repo: .github/workflows/{index}.yml" for index in range(55)}
    open_sync_prs = [
        {
            "repo": "owner/repo",
            "number": index,
            "url": f"https://github.com/owner/repo/pull/{index}",
            "branch": f"sync/workflows-{index}",
        }
        for index in range(12)
    ]
    report = check_consumer_sync_drift.build_report(
        repos=["owner/repo"],
        drift=drift,
        missing={"owner/repo: scripts/langchain/formatter.py"},
        errors=set(),
        obsolete=set(),
        open_sync_prs=open_sync_prs,
    )

    check_consumer_sync_drift.write_summary_markdown(str(output), report)

    contents = output.read_text(encoding="utf-8")
    assert "### Counts" in contents
    assert "- drift: 55" in contents
    assert "- owner/repo: drift=55, missing=1, errors=0, obsolete=0" in contents
    assert "- owner/repo: total=56, drift=55, missing=1, errors=0, obsolete=0" in contents
    assert "- drift: .github/workflows=55" in contents
    assert "gh workflow run maint-68-sync-consumer-repos.yml" in contents
    assert "- owner/repo#0: `sync/workflows-0` https://github.com/owner/repo/pull/0" in contents
    assert "- owner/repo#9: `sync/workflows-9` https://github.com/owner/repo/pull/9" in contents
    assert "- owner/repo#10: `sync/workflows-10`" not in contents
    assert "... 2 more in consumer-sync-drift-report.json" in contents
    assert "... 5 more in consumer-sync-drift-report.json" in contents


def test_join_remote_path_normalizes_manifest_directory_targets() -> None:
    assert (
        check_consumer_sync_drift.join_remote_path(
            ".github/scripts/node_modules/minimatch/",
            "dist/commonjs/index.js",
        )
        == ".github/scripts/node_modules/minimatch/dist/commonjs/index.js"
    )
    assert (
        check_consumer_sync_drift.join_remote_path(
            ".github/actions/setup-api-client/",
            "/action.yml",
        )
        == ".github/actions/setup-api-client/action.yml"
    )


def test_git_blob_hash_matches_git_object_hash() -> None:
    assert (
        check_consumer_sync_drift.git_blob_hash(b"hello\n")
        == "ce013625030ba8dba906f756967f9e9ca394464a"
    )


def test_local_path_for_uses_root_for_script_sources(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    root_script = tmp_path / "scripts" / "langchain" / "issue_optimizer.py"
    template_script = (
        tmp_path / "templates" / "consumer-repo" / "scripts" / "langchain" / "issue_optimizer.py"
    )
    root_script.parent.mkdir(parents=True)
    template_script.parent.mkdir(parents=True)
    root_script.write_text("root source\n", encoding="utf-8")
    template_script.write_text("stale template source\n", encoding="utf-8")

    resolved = check_consumer_sync_drift.local_path_for(
        "scripts/langchain/issue_optimizer.py", "scripts"
    )
    assert resolved is not None
    assert resolved.resolve() == root_script


def test_local_path_for_uses_templates_for_workflow_sources(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    root_workflow = tmp_path / ".github" / "workflows" / "agents-issue-optimizer.yml"
    template_workflow = (
        tmp_path
        / "templates"
        / "consumer-repo"
        / ".github"
        / "workflows"
        / "agents-issue-optimizer.yml"
    )
    root_workflow.parent.mkdir(parents=True)
    template_workflow.parent.mkdir(parents=True)
    root_workflow.write_text("orchestrator source\n", encoding="utf-8")
    template_workflow.write_text("consumer template source\n", encoding="utf-8")

    resolved = check_consumer_sync_drift.local_path_for(
        ".github/workflows/agents-issue-optimizer.yml", "workflows"
    )
    assert resolved is not None
    assert resolved.resolve() == template_workflow


def test_local_path_for_falls_back_to_root_for_template_sections(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    root_doc = tmp_path / "docs" / "AGENT_ISSUE_FORMAT.md"
    root_doc.parent.mkdir(parents=True)
    root_doc.write_text("root-only doc\n", encoding="utf-8")

    resolved = check_consumer_sync_drift.local_path_for("docs/AGENT_ISSUE_FORMAT.md", "docs")
    assert resolved is not None
    assert resolved.resolve() == root_doc


def test_local_path_for_without_section_preserves_legacy_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    root_doc = tmp_path / "docs" / "contract.md"
    template_doc = tmp_path / "templates" / "consumer-repo" / "docs" / "contract.md"
    root_doc.parent.mkdir(parents=True)
    template_doc.parent.mkdir(parents=True)
    root_doc.write_text("root\n", encoding="utf-8")
    template_doc.write_text("template\n", encoding="utf-8")

    resolved = check_consumer_sync_drift.local_path_for("docs/contract.md")
    assert resolved is not None
    assert resolved.resolve() == template_doc

    template_doc.unlink()
    resolved = check_consumer_sync_drift.local_path_for("docs/contract.md")
    assert resolved is not None
    assert resolved.resolve() == root_doc


def test_record_content_error_skips_after_threshold() -> None:
    errors: set[str] = set()
    counts: dict[str, int] = {}
    skipped: set[str] = set()

    for index in range(4):
        check_consumer_sync_drift.record_content_error(
            errors=errors,
            repo_error_counts=counts,
            skipped_repos=skipped,
            repo="owner/repo",
            target=f".github/workflows/{index}.yml",
            status_code=403,
            threshold=3,
        )

    assert counts == {"owner/repo": 3}
    assert skipped == {"owner/repo"}
    assert "owner/repo: .github/workflows/0.yml (HTTP 403)" in errors
    assert (
        "owner/repo: content comparison skipped after 3 HTTP errors; "
        "last path .github/workflows/2.yml (HTTP 403)"
    ) in errors
    assert not any(".github/workflows/3.yml" in item for item in errors)


def test_repo_access_error_reports_single_preflight_failure() -> None:
    class Response:
        status_code = 403

    class Session:
        requested_urls: list[str] = []

        def get(self, url: str) -> Response:
            self.requested_urls.append(url)
            return Response()

    session = Session()

    error = check_consumer_sync_drift.repo_access_error(session, "owner/private-repo")

    assert error == "owner/private-repo: repository access preflight failed (HTTP 403)"
    assert session.requested_urls == ["https://api.github.com/repos/owner/private-repo"]


def test_repo_access_error_allows_readable_repo() -> None:
    class Response:
        status_code = 200

    class Session:
        def get(self, url: str) -> Response:
            return Response()

    assert check_consumer_sync_drift.repo_access_error(Session(), "owner/repo") is None


def test_fetch_remote_tree_uses_default_branch_tree() -> None:
    class Response:
        def __init__(self, status_code: int, payload: dict[str, object]) -> None:
            self.status_code = status_code
            self._payload = payload

        def json(self) -> dict[str, object]:
            return self._payload

    class Session:
        requested_urls: list[str] = []

        def get(self, url: str) -> Response:
            self.requested_urls.append(url)
            if url.endswith("/repos/owner/repo"):
                return Response(200, {"default_branch": "trunk"})
            if url.endswith("/repos/owner/repo/git/trees/trunk?recursive=1"):
                return Response(
                    200,
                    {
                        "tree": [
                            {"path": ".github/workflows/a.yml", "type": "blob", "sha": "abc"},
                            {"path": ".github/workflows", "type": "tree", "sha": "def"},
                        ],
                        "truncated": False,
                    },
                )
            return Response(404, {})

    session = Session()

    tree, error = check_consumer_sync_drift.fetch_remote_tree(session, "owner/repo")

    assert error is None
    assert tree == {
        ".github/workflows/a.yml": {
            "path": ".github/workflows/a.yml",
            "type": "blob",
            "sha": "abc",
        },
        ".github/workflows": {"path": ".github/workflows", "type": "tree", "sha": "def"},
    }
    assert session.requested_urls == [
        "https://api.github.com/repos/owner/repo",
        "https://api.github.com/repos/owner/repo/git/trees/trunk?recursive=1",
    ]


def test_fetch_remote_tree_reports_truncated_tree() -> None:
    class Response:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {"default_branch": "main", "tree": [], "truncated": True}

    class Session:
        def get(self, _url: str) -> Response:
            return Response()

    tree, error = check_consumer_sync_drift.fetch_remote_tree(Session(), "owner/repo")

    assert tree is None
    assert error == "owner/repo: repository tree fetch was truncated"


def test_fetch_remote_tree_reports_rate_limit_reason() -> None:
    class Response:
        status_code = 403
        headers = {"x-ratelimit-remaining": "0"}

        def json(self) -> dict[str, str]:
            return {"message": "API rate limit exceeded"}

    class Session:
        def get(self, _url: str) -> Response:
            return Response()

    tree, error = check_consumer_sync_drift.fetch_remote_tree(Session(), "owner/repo")

    assert tree is None
    assert error == "owner/repo: repository access preflight failed (rate_limited)"
