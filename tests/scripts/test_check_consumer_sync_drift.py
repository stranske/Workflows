import json

from scripts import check_consumer_sync_drift


def test_build_report_returns_machine_readable_counts() -> None:
    report = check_consumer_sync_drift.build_report(
        repos=["owner/b", "owner/a"],
        drift={"owner/b: .github/workflows/a.yml"},
        missing={"owner/a: .github/scripts/a.js"},
        errors=set(),
        obsolete={"owner/a: old.yml"},
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
    assert report["path_prefix_counts"] == {
        "drift": {".github/workflows": 1},
        "missing": {".github/scripts": 1},
        "errors": {},
        "obsolete": {"old.yml": 1},
    }
    assert report["summary_limits"]["content_error_threshold_per_repo"] == 5
    assert report["drift"] == ["owner/b: .github/workflows/a.yml"]


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
    assert loaded["status"] == "pass"


def test_write_summary_markdown_groups_and_bounds_items(tmp_path) -> None:
    output = tmp_path / "summary.md"
    drift = {f"owner/repo: .github/workflows/{index}.yml" for index in range(55)}
    report = check_consumer_sync_drift.build_report(
        repos=["owner/repo"],
        drift=drift,
        missing={"owner/repo: scripts/langchain/formatter.py"},
        errors=set(),
        obsolete=set(),
    )

    check_consumer_sync_drift.write_summary_markdown(str(output), report)

    contents = output.read_text(encoding="utf-8")
    assert "### Counts" in contents
    assert "- drift: 55" in contents
    assert "- owner/repo: drift=55, missing=1, errors=0, obsolete=0" in contents
    assert "- drift: .github/workflows=55" in contents
    assert "... 5 more in consumer-sync-drift-report.json" in contents


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
