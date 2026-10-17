import base64
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

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
        "unmeasured_create_only": 0,
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
            "--repo stranske/Workflows --ref main -f phase=preview "
            "-f repos=owner/a,owner/b"
        ),
    }
    assert report["summary_limits"]["content_error_threshold_per_repo"] == 5
    assert report["sync_remediation"]["state"] == "drift"
    assert report["sync_remediation"]["repo_states"]["owner/a"]["state"] == "untracked_drift"
    assert report["drift"] == ["owner/b: .github/workflows/a.yml"]
    assert report["token_diagnostics"] == token_diagnostics


def test_report_counts_create_only_exclusions(tmp_path, monkeypatch) -> None:
    """Create-only reporting includes repos whose tree retrieval failed."""
    source = tmp_path / ".github" / "workflows" / "example.yml"
    source.parent.mkdir(parents=True)
    source.write_text("name: Example\n", encoding="utf-8")
    manifest = tmp_path / "sync-manifest.yml"
    manifest.write_text("version: 1\n", encoding="utf-8")
    report_path = tmp_path / "report.json"
    entry = _make_entry(
        source=str(source),
        target=".github/workflows/example.yml",
        sync_mode="create_only",
    )
    compiled = SimpleNamespace(
        to_plan=lambda: {"plan_id": "sha256:" + "a" * 64},
        section=lambda section: (entry,) if section == "workflows" else (),
        removals=(),
    )
    args = SimpleNamespace(
        repos="owner/a,owner/b",
        manifest=str(manifest),
        canaries="unused.json",
        report_json=str(report_path),
        summary="",
    )

    monkeypatch.setattr(check_consumer_sync_drift, "COPY_SYNCED_SECTIONS", ("workflows",))
    monkeypatch.setattr(check_consumer_sync_drift, "parse_args", lambda: args)
    monkeypatch.setattr(check_consumer_sync_drift, "token_candidates", lambda: [{"token": "x"}])
    monkeypatch.setattr(check_consumer_sync_drift, "compile_manifest", lambda _path: compiled)
    monkeypatch.setattr(check_consumer_sync_drift, "resolve_candidate_repos", lambda *_args: set())
    monkeypatch.setattr(
        check_consumer_sync_drift,
        "select_read_token",
        lambda **_kwargs: (object(), {}),
    )
    monkeypatch.setattr(
        check_consumer_sync_drift,
        "fetch_remote_tree",
        lambda _session, repo: (
            ({}, None) if repo == "owner/a" else (None, "owner/b: failed to fetch remote tree")
        ),
    )
    monkeypatch.setattr(
        check_consumer_sync_drift,
        "fetch_open_sync_prs",
        lambda _session, _repo: ([], None),
    )

    assert check_consumer_sync_drift.main() == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["counts"]["unmeasured_create_only"] == 2
    assert report["unmeasured_create_only"] == [
        "owner/a: .github/workflows/example.yml",
        "owner/b: .github/workflows/example.yml",
    ]
    assert report["errors"] == ["owner/b: failed to fetch remote tree"]
    assert report["status"] == "drift"


def test_create_only_scope_exclusion_survives_remote_tree_failure(tmp_path, monkeypatch) -> None:
    source = tmp_path / "example.yml"
    source.write_text("name: Example\n", encoding="utf-8")
    manifest = tmp_path / "sync-manifest.yml"
    manifest.write_text("version: 1\n", encoding="utf-8")
    report_path = tmp_path / "report.json"
    entry = _make_entry(
        source=str(source),
        target=".github/workflows/example.yml",
        sync_mode="create_only",
        include_repos=("owner/a",),
    )
    compiled = SimpleNamespace(
        to_plan=lambda: {"plan_id": "sha256:" + "a" * 64},
        section=lambda section: (entry,) if section == "workflows" else (),
        removals=(),
    )
    args = SimpleNamespace(
        repos="owner/a,owner/b",
        manifest=str(manifest),
        canaries="unused.json",
        report_json=str(report_path),
        summary="",
    )
    monkeypatch.setattr(check_consumer_sync_drift, "COPY_SYNCED_SECTIONS", ("workflows",))
    monkeypatch.setattr(check_consumer_sync_drift, "parse_args", lambda: args)
    monkeypatch.setattr(check_consumer_sync_drift, "token_candidates", lambda: [{"token": "x"}])
    monkeypatch.setattr(check_consumer_sync_drift, "compile_manifest", lambda _path: compiled)
    monkeypatch.setattr(check_consumer_sync_drift, "resolve_candidate_repos", lambda *_args: set())
    monkeypatch.setattr(
        check_consumer_sync_drift,
        "select_read_token",
        lambda **_kwargs: (object(), {}),
    )
    monkeypatch.setattr(
        check_consumer_sync_drift,
        "fetch_remote_tree",
        lambda _session, repo: (
            ({}, None) if repo == "owner/a" else (None, "owner/b: failed to fetch remote tree")
        ),
    )
    monkeypatch.setattr(check_consumer_sync_drift, "fetch_open_sync_prs", lambda *_args: ([], None))

    assert check_consumer_sync_drift.main() == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["unmeasured_create_only"] == ["owner/a: .github/workflows/example.yml"]
    assert report["skipped"] == [
        "owner/b: .github/workflows/example.yml (Manifest include_repos excludes repo)"
    ]
    assert report["errors"] == ["owner/b: failed to fetch remote tree"]


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
    include_repos: tuple = (),
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
        include_repos=include_repos,
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


def test_manifest_skip_reason_honors_include_repos() -> None:
    entry = _make_entry(source="schema.json", include_repos=("owner/selected",))

    assert check_consumer_sync_drift.manifest_skip_reason(entry, "owner/selected") == ""
    assert (
        check_consumer_sync_drift.manifest_skip_reason(entry, "owner/other")
        == "Manifest include_repos excludes repo"
    )


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
    assert report["counts"] == {
        "drift": 0,
        "missing": 0,
        "errors": 0,
        "obsolete": 0,
        "unmeasured_create_only": 0,
    }
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
                "branch": "sync/workflows-delivery",
                "head_repo": "owner/repo",
                "updated_at": "2026-04-26T01:00:00Z",
            }
        ],
        current_plan_id="sha256:" + "a" * 64,
        now=datetime(2026, 4, 26, 2, 0, tzinfo=UTC),
    )

    assert report["status"] == "covered"
    assert report["sync_remediation"]["expected_branch"] == "sync/workflows-delivery"
    assert report["sync_remediation"]["delivery_branch"] == "sync/workflows-delivery"
    assert report["sync_remediation"]["repo_states"]["owner/repo"]["state"] == "covered"


def test_build_report_accepts_the_stable_candidate_branch_only_for_canaries() -> None:
    candidate_pr = {
        "repo": "owner/canary",
        "number": 13,
        "url": "https://github.com/owner/canary/pull/13",
        "branch": "sync/workflows-candidate",
        "head_repo": "owner/canary",
        "updated_at": "2026-04-26T01:00:00Z",
    }
    report = check_consumer_sync_drift.build_report(
        repos=["owner/canary", "owner/regular"],
        drift={
            "owner/canary: .github/workflows/a.yml",
            "owner/regular: .github/workflows/a.yml",
        },
        missing=set(),
        errors=set(),
        obsolete=set(),
        open_sync_prs=[candidate_pr],
        current_plan_id="sha256:" + "a" * 64,
        candidate_repos={"owner/canary"},
        now=datetime(2026, 4, 26, 2, 0, tzinfo=UTC),
    )

    states = report["sync_remediation"]["repo_states"]
    assert states["owner/canary"]["state"] == "covered"
    assert states["owner/canary"]["expected_branch"] == "sync/workflows-candidate"
    assert states["owner/regular"]["state"] == "untracked_drift"
    assert states["owner/regular"]["expected_branch"] == "sync/workflows-delivery"
    assert "-f phase=preview" in report["follow_up"]["targeted_repos_command"]


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
        "branch": "sync/workflows-delivery",
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
    assert "- unmeasured_create_only: 0" in contents
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


def test_main_writes_actionable_reports_for_early_preflight_failures(tmp_path, monkeypatch) -> None:
    """Every early exit must leave machine-readable evidence for the maintainer."""
    # resolve_repos("") falls back to this variable; a maintainer shell must not change case one.
    monkeypatch.delenv("REGISTERED_CONSUMER_REPOS", raising=False)
    report_path = tmp_path / "report.json"
    args = SimpleNamespace(
        repos="",
        manifest=str(tmp_path / "missing.yml"),
        canaries=str(tmp_path / "canaries.json"),
        report_json=str(report_path),
        summary="",
    )
    monkeypatch.setattr(check_consumer_sync_drift, "parse_args", lambda: args)

    assert check_consumer_sync_drift.main() == 1
    assert json.loads(report_path.read_text(encoding="utf-8"))["errors"] == [
        "No repos provided or found in REGISTERED_CONSUMER_REPOS"
    ]

    args.repos = "owner/repo"
    assert check_consumer_sync_drift.main() == 1
    assert json.loads(report_path.read_text(encoding="utf-8"))["errors"] == [
        "sync-manifest.yml not found"
    ]

    manifest = tmp_path / "manifest.yml"
    manifest.write_text("version: 1\n", encoding="utf-8")
    args.manifest = str(manifest)
    monkeypatch.setattr(check_consumer_sync_drift, "token_candidates", lambda: [])
    assert check_consumer_sync_drift.main() == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["errors"] == ["No GitHub token available for cross-repo reads"]
    assert report["token_diagnostics"]["error"] == "no_token_candidates"


def test_main_rejects_invalid_configuration_and_unusable_tokens(tmp_path, monkeypatch) -> None:
    manifest = tmp_path / "manifest.yml"
    manifest.write_text("version: 1\n", encoding="utf-8")
    report_path = tmp_path / "report.json"
    args = SimpleNamespace(
        repos="owner/repo",
        manifest=str(manifest),
        canaries=str(tmp_path / "canaries.json"),
        report_json=str(report_path),
        summary="",
    )
    compiled = SimpleNamespace(
        to_plan=lambda: {"plan_id": "sha256:" + "a" * 64}, section=lambda _section: ()
    )
    monkeypatch.setattr(check_consumer_sync_drift, "parse_args", lambda: args)
    monkeypatch.setattr(check_consumer_sync_drift, "token_candidates", lambda: [{"token": "token"}])

    def invalid_manifest(_path):
        raise check_consumer_sync_drift.ManifestCompileError(["bad manifest"])

    monkeypatch.setattr(check_consumer_sync_drift, "compile_manifest", invalid_manifest)
    assert check_consumer_sync_drift.main() == 1
    assert json.loads(report_path.read_text(encoding="utf-8"))["errors"] == [
        "Invalid manifest: bad manifest"
    ]

    monkeypatch.setattr(check_consumer_sync_drift, "compile_manifest", lambda _path: compiled)
    monkeypatch.setattr(
        check_consumer_sync_drift,
        "resolve_candidate_repos",
        lambda *_args: (_ for _ in ()).throw(ValueError("bad canaries")),
    )
    assert check_consumer_sync_drift.main() == 1
    assert json.loads(report_path.read_text(encoding="utf-8"))["errors"] == [
        "Invalid consumer sync canary config: bad canaries"
    ]

    monkeypatch.setattr(check_consumer_sync_drift, "resolve_candidate_repos", lambda *_args: set())
    monkeypatch.setattr(
        check_consumer_sync_drift,
        "select_read_token",
        lambda **_kwargs: (None, {"error": "no_usable_token"}),
    )
    assert check_consumer_sync_drift.main() == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["errors"] == ["No usable GitHub token available for consumer repo contents reads"]
    assert report["token_diagnostics"] == {"error": "no_usable_token"}


def test_main_compares_manifest_files_and_writes_converged_summary(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source.yml"
    source.write_text("name: Example\n", encoding="utf-8")
    summary_path = tmp_path / "summary.md"
    report_path = tmp_path / "report.json"
    entry = _make_entry(source=str(source), target=".github/workflows/example.yml")
    compiled = SimpleNamespace(
        to_plan=lambda: {"plan_id": "sha256:" + "a" * 64},
        section=lambda section: (entry,) if section == "workflows" else (),
        removals=(),
    )
    args = SimpleNamespace(
        repos="owner/repo",
        manifest=str(tmp_path / "manifest.yml"),
        canaries=str(tmp_path / "canaries.json"),
        report_json=str(report_path),
        summary=str(summary_path),
    )
    Path(args.manifest).write_text("version: 1\n", encoding="utf-8")
    monkeypatch.setattr(check_consumer_sync_drift, "COPY_SYNCED_SECTIONS", ("workflows",))
    monkeypatch.setattr(check_consumer_sync_drift, "parse_args", lambda: args)
    monkeypatch.setattr(check_consumer_sync_drift, "token_candidates", lambda: [{"token": "token"}])
    monkeypatch.setattr(check_consumer_sync_drift, "compile_manifest", lambda _path: compiled)
    monkeypatch.setattr(check_consumer_sync_drift, "resolve_candidate_repos", lambda *_args: set())
    monkeypatch.setattr(
        check_consumer_sync_drift, "select_read_token", lambda **_kwargs: (object(), {})
    )
    monkeypatch.setattr(
        check_consumer_sync_drift,
        "fetch_remote_tree",
        lambda _session, _repo: (
            {
                ".github/workflows/example.yml": {
                    "type": "blob",
                    "sha": check_consumer_sync_drift.git_blob_hash(source.read_bytes()),
                }
            },
            None,
        ),
    )
    monkeypatch.setattr(check_consumer_sync_drift, "fetch_open_sync_prs", lambda *_args: ([], None))

    assert check_consumer_sync_drift.main() == 0
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "converged"
    assert "No drift detected." in summary_path.read_text(encoding="utf-8")


def test_main_reports_body_drift_but_ignores_syncer_header_differences(
    tmp_path, monkeypatch
) -> None:
    source = tmp_path / "source.yml"
    source.write_text("# local header\nname: Example\n", encoding="utf-8")
    report_path = tmp_path / "report.json"
    entry = _make_entry(source=str(source), target=".github/workflows/example.yml")
    compiled = SimpleNamespace(
        to_plan=lambda: {"plan_id": "sha256:" + "a" * 64},
        section=lambda section: (entry,) if section == "workflows" else (),
        removals=(),
    )
    args = SimpleNamespace(
        repos="owner/repo",
        manifest=str(tmp_path / "manifest.yml"),
        canaries=str(tmp_path / "canaries.json"),
        report_json=str(report_path),
        summary="",
    )
    Path(args.manifest).write_text("version: 1\n", encoding="utf-8")
    monkeypatch.setattr(check_consumer_sync_drift, "COPY_SYNCED_SECTIONS", ("workflows",))
    monkeypatch.setattr(check_consumer_sync_drift, "parse_args", lambda: args)
    monkeypatch.setattr(check_consumer_sync_drift, "token_candidates", lambda: [{"token": "token"}])
    monkeypatch.setattr(check_consumer_sync_drift, "compile_manifest", lambda _path: compiled)
    monkeypatch.setattr(check_consumer_sync_drift, "resolve_candidate_repos", lambda *_args: set())
    monkeypatch.setattr(
        check_consumer_sync_drift, "select_read_token", lambda **_kwargs: (object(), {})
    )
    monkeypatch.setattr(
        check_consumer_sync_drift,
        "fetch_remote_tree",
        lambda _session, _repo: (
            {".github/workflows/example.yml": {"type": "blob", "sha": "remote-sha"}},
            None,
        ),
    )
    monkeypatch.setattr(check_consumer_sync_drift, "fetch_open_sync_prs", lambda *_args: ([], None))
    monkeypatch.setattr(
        check_consumer_sync_drift,
        "remote_blob_text",
        lambda *_args: "# remote header\nname: Example\n",
    )

    assert check_consumer_sync_drift.main() == 0
    monkeypatch.setattr(
        check_consumer_sync_drift, "remote_blob_text", lambda *_args: "name: Changed\n"
    )
    assert check_consumer_sync_drift.main() == 1
    assert json.loads(report_path.read_text(encoding="utf-8"))["drift"] == [
        "owner/repo: .github/workflows/example.yml"
    ]


def test_drift_cli_and_remote_read_boundaries(tmp_path, monkeypatch) -> None:
    """Exercise fail-closed CLI parsing and remote-content fallback branches."""
    monkeypatch.setattr(
        "sys.argv",
        [
            "check_consumer_sync_drift.py",
            "--repos",
            "owner/a,owner/b",
            "--manifest",
            "manifest.yml",
            "--canaries",
            "canaries.json",
            "--summary",
            "summary.md",
            "--report-json",
            "report.json",
        ],
    )
    args = check_consumer_sync_drift.parse_args()
    assert (args.repos, args.manifest, args.canaries, args.summary, args.report_json) == (
        "owner/a,owner/b",
        "manifest.yml",
        "canaries.json",
        "summary.md",
        "report.json",
    )

    canaries = tmp_path / "canaries.json"
    canaries.write_text('{"canaries": [{"repo": "owner/a"}]}', encoding="utf-8")
    assert check_consumer_sync_drift.resolve_candidate_repos(str(canaries), ["owner/a"]) == {
        "owner/a"
    }
    for contents in ("{}", '{"canaries": []}', '{"canaries": [{"repo": "owner/missing"}]}'):
        canaries.write_text(contents, encoding="utf-8")
        try:
            check_consumer_sync_drift.resolve_candidate_repos(str(canaries), ["owner/a"])
        except ValueError:
            pass
        else:
            raise AssertionError("invalid canary configuration must fail closed")

    class Response:
        def __init__(self, status_code=200, payload=None):
            self.status_code = status_code
            self._payload = payload or {}

        def json(self):
            return self._payload

    class Session:
        def __init__(self, response):
            self.response = response

        def get(self, _url):
            return self.response

    assert (
        check_consumer_sync_drift.remote_blob_text(Session(Response(404)), "owner/a", "sha") is None
    )
    assert (
        check_consumer_sync_drift.remote_blob_text(
            Session(Response(200, {"encoding": "hex"})), "owner/a", "sha"
        )
        is None
    )
    payload = {"encoding": "base64", "content": base64.b64encode(b"name: Example\n").decode()}
    assert (
        check_consumer_sync_drift.remote_blob_text(
            Session(Response(200, payload)), "owner/a", "sha"
        )
        == "name: Example\n"
    )


def test_drift_summary_renders_actionable_nested_report_data(tmp_path: Path) -> None:
    """Do not silently drop malformed optional report sections or open-PR overflow."""
    report_path = tmp_path / "nested" / "summary.md"
    report = {
        "counts": {
            "drift": 12,
            "missing": 0,
            "errors": 0,
            "obsolete": 0,
            "unmeasured_create_only": 0,
        },
        "repos": ["owner/a"],
        "repo_summaries": {
            "owner/a": {"drift": 12, "missing": 0, "errors": 0, "obsolete": 0},
            "bad": [],
        },
        "top_repo_gaps": [
            {"repo": "owner/a", "total": 12, "drift": 12, "missing": 0, "errors": 0, "obsolete": 0},
            "bad",
        ],
        "path_prefix_counts": {"drift": {"scripts": 12}, "bad": []},
        "follow_up": {"all_repos_command": "all", "targeted_repos_command": "targeted"},
        "sync_remediation": {
            "open_prs": [
                {
                    "repo": "owner/a",
                    "number": number,
                    "branch": "sync/workflows-delivery",
                    "url": "u",
                }
                for number in range(11)
            ]
        },
        "drift": [
            f"owner/a: scripts/{number}.py"
            for number in range(check_consumer_sync_drift.SUMMARY_ITEM_LIMIT + 2)
        ],
        "missing": [],
        "errors": [],
        "obsolete": [],
        "skipped": [],
        "unmeasured_create_only": [],
    }
    check_consumer_sync_drift.write_summary_markdown(str(report_path), report)
    rendered = report_path.read_text(encoding="utf-8")
    assert "### Repo summary" in rendered
    assert (
        "- owner/a: drift=12, missing=0, errors=0, obsolete=0, unmeasured_create_only=0" in rendered
    )
    assert "### Highest-impact repos" in rendered
    assert "- owner/a: total=12, drift=12, missing=0, errors=0, obsolete=0" in rendered
    assert "### Path prefixes" in rendered
    assert "- drift: scripts=12" in rendered
    assert "### Follow-up commands" in rendered
    assert "### Open sync PRs" in rendered
    assert "bad" not in rendered
    assert "... 1 more in consumer-sync-drift-report.json" in rendered
    assert "... 2 more in consumer-sync-drift-report.json" in rendered
    check_consumer_sync_drift.write_report_json("", report)


def test_drift_network_helpers_fail_closed_without_readable_probe_targets() -> None:
    """A missing credential or malformed API response must not claim a clean drift check."""
    session, diagnostics = check_consumer_sync_drift.select_read_token(
        candidates=[], repos=["owner/a"], paths=[]
    )
    assert session is None
    assert diagnostics["error"] == "no_token_candidates"
    session, diagnostics = check_consumer_sync_drift.select_read_token(
        candidates=[{"source": "TOKEN", "token": "secret"}], repos=[], paths=[]
    )
    assert session is None
    assert diagnostics["error"] == "no_repos_to_probe"

    class Response:
        status_code = 500
        headers = {}

        def json(self):
            raise ValueError("not-json")

    assert check_consumer_sync_drift.response_message(Response()) == ""
    assert check_consumer_sync_drift.response_failure_reason(Response()) == "HTTP 500"
    assert check_consumer_sync_drift.parse_github_timestamp(None) is None
    assert check_consumer_sync_drift.parse_github_timestamp("not-a-timestamp") is None
