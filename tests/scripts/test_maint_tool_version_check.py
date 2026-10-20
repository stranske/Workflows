from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from scripts import maint_tool_version_check as check


def test_parse_tool_version_outputs_cover_common_tools() -> None:
    samples = {
        "black": "black, 25.11.0 (compiled: yes)",
        "ruff": "ruff 0.14.10",
        "mypy": "mypy 1.19.0 (compiled: yes)",
        "pytest": "pytest 8.4.2",
    }

    assert {
        tool: check.parse_tool_version_output(tool, output) for tool, output in samples.items()
    } == {
        "black": "25.11.0",
        "ruff": "0.14.10",
        "mypy": "1.19.0",
        "pytest": "8.4.2",
    }


def test_compare_versions_renders_updates_and_check_failures() -> None:
    current = {
        "black": "black, 25.1.0",
        "coverage": "coverage 7.10.7",
        "docformatter": "docformatter 1.7.7",
        "isort": "isort 6.0.1",
        "mypy": "mypy 1.19.0",
        "pytest": "pytest 8.4.2",
        "pytest-cov": "pytest-cov 7.0.0",
        "ruff": "ruff 0.14.10",
    }
    latest = {
        "black": "25.11.0",
        "coverage": "7.10.7",
        "docformatter": "not a version",
        "isort": "6.0.1",
        "mypy": "1.19.0",
        "pytest": "8.4.2",
        "pytest-cov": "7.0.0",
        "ruff": "0.14.10",
    }

    statuses = check.compare_versions(current, latest)
    by_tool = {item.tool: item for item in statuses}

    assert by_tool["black"].has_update is True
    assert by_tool["black"].status == "Update available"
    assert by_tool["docformatter"].has_update is False
    assert by_tool["docformatter"].status == "Check failed"
    assert by_tool["pytest"].status == "Current"

    report = check.render_report(statuses)
    assert "| black | 25.1.0 | 25.11.0 | Update available |" in report
    assert "| docformatter | 1.7.7 | not a version | Check failed |" in report

    updates = check.render_updates(statuses)
    assert updates == "- **black**: 25.1.0 -> 25.11.0"


def test_malformed_current_version_is_reported_without_update() -> None:
    current = {spec.name: "unexpected output" for spec in check.TOOLS}
    latest = {spec.name: "1.2.3" for spec in check.TOOLS}

    statuses = check.compare_versions(current, latest)

    assert all(item.status == "Current version invalid" for item in statuses)
    assert not any(item.has_update for item in statuses)


def test_render_issue_body_has_expected_update_instructions() -> None:
    body = check.render_issue_body(
        report="## Tool Version Status\n\n| Tool | Current | Latest | Status |",
        updates="- **ruff**: 0.13.2 -> 0.14.10",
        workflow_url="https://github.com/stranske/Workflows/actions/workflows/maint-50.yml",
        timestamp="2026-05-06T12:00:00+00:00",
    )

    assert "### Updates Available" in body
    assert "- **ruff**: 0.13.2 -> 0.14.10" in body
    assert "pip install" in body
    assert "black==$BLACK_VERSION" in body
    assert "[Tool Version Check workflow]" in body
    assert body.endswith("*Last checked: 2026-05-06T12:00:00+00:00*")


def test_compare_command_writes_github_outputs(monkeypatch, tmp_path: Path) -> None:
    output_path = tmp_path / "github-output.txt"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))
    monkeypatch.setenv("WORKFLOW_URL", "https://example.test/workflow")
    monkeypatch.setenv("CHECK_TIMESTAMP", "2026-05-06T12:00:00+00:00")
    for spec in check.TOOLS:
        monkeypatch.setenv(spec.current_env, "1.0.0")
        monkeypatch.setenv(spec.latest_env, "1.1.0")

    assert check.command_compare() == 0

    output = output_path.read_text(encoding="utf-8")
    assert "report<<REPORT_EOF" in output
    assert "updates<<UPDATES_EOF" in output
    assert "has_updates=true" in output
    assert (tmp_path / "tool-version-issue-body.md").exists()


def test_latest_command_and_main_dispatch(monkeypatch, tmp_path: Path, capsys) -> None:
    output = tmp_path / "github-output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(
        check, "latest_pypi_version", lambda package: "9.9.9" if package == "black" else None
    )

    assert check.main(["latest"]) == 0

    lines = output.read_text(encoding="utf-8")
    assert "black_latest=9.9.9" in lines
    assert "ruff_latest=unknown" in lines
    assert "black: 9.9.9" in capsys.readouterr().out


def test_latest_pypi_failure_and_compare_without_updates(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "github-output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        check.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("offline")),
    )
    assert check.latest_pypi_version("black") is None
    for spec in check.TOOLS:
        monkeypatch.setenv(spec.current_env, "1.0.0")
        monkeypatch.setenv(spec.latest_env, "1.0.0")
    assert check.main(["compare"]) == 0
    assert "updates=\n" in output.read_text(encoding="utf-8")


def test_parse_tool_version_rejects_unknown_and_empty() -> None:
    assert check.parse_tool_version_output("black", "") is None
    assert check.parse_tool_version_output("black", "unknown") is None
    assert check.parse_tool_version_output("black", "no version here") is None


def test_latest_pypi_version_success_and_missing_info(monkeypatch) -> None:
    payload = json.dumps({"info": {"version": "9.9.9"}}).encode("utf-8")
    response = MagicMock()
    response.read.return_value = payload
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    monkeypatch.setattr(check.urllib.request, "urlopen", lambda *_a, **_k: response)
    assert check.latest_pypi_version("black") == "9.9.9"

    empty = MagicMock()
    empty.read.return_value = json.dumps({"info": {}}).encode("utf-8")
    empty.__enter__.return_value = empty
    empty.__exit__.return_value = False
    monkeypatch.setattr(check.urllib.request, "urlopen", lambda *_a, **_k: empty)
    assert check.latest_pypi_version("black") is None
