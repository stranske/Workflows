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
