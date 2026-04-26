import json
import subprocess
from pathlib import Path

from scripts import check_codex_cli_freshness


def test_extracts_pinned_codex_cli_version(tmp_path: Path) -> None:
    workflow = tmp_path / "workflow.yml"
    workflow.write_text(
        'run: npm install -g "@openai/codex@0.125.0"\n',
        encoding="utf-8",
    )

    assert check_codex_cli_freshness.extract_pinned_cli_version(workflow) == "0.125.0"


def test_build_contract_reports_current_pin() -> None:
    report = check_codex_cli_freshness.build_contract(
        pinned_version="0.125.0",
        latest_version="0.125.0",
        generated_at="2026-04-26T19:00:00Z",
    )

    assert report["schema"] == "workflows-codex-cli-freshness/v1"
    assert report["status"] == "current"
    assert report["version_delta"] == {"major": 0, "minor": 0, "patch": 0}
    assert report["update_targets"][0]["path"] == ".github/workflows/reusable-agents-verifier.yml"


def test_build_contract_reports_outdated_pin() -> None:
    report = check_codex_cli_freshness.build_contract(
        pinned_version="0.125.0",
        latest_version="0.127.3",
        generated_at="2026-04-26T19:00:00Z",
    )
    markdown = check_codex_cli_freshness.format_markdown(report)

    assert report["status"] == "outdated"
    assert report["version_delta"] == {"major": 0, "minor": 2, "patch": 3}
    assert "@openai/codex@0.127.3" in markdown


def test_query_latest_npm_version_uses_isolated_cache(monkeypatch) -> None:
    captured_env = {}

    def fake_run(command, **kwargs):
        captured_env.update(kwargs["env"])
        assert command == ["npm", "view", "@openai/codex", "version", "--silent"]
        return subprocess.CompletedProcess(command, 0, stdout="0.126.0\n", stderr="")

    monkeypatch.setenv("NPM_CONFIG_CACHE", "/bad/shared/cache")
    monkeypatch.setattr(check_codex_cli_freshness.subprocess, "run", fake_run)

    latest, error = check_codex_cli_freshness.query_latest_npm_version()

    assert latest == "0.126.0"
    assert error == ""
    assert captured_env["NPM_CONFIG_CACHE"] != "/bad/shared/cache"
    assert "codex-cli-freshness-npm-" in captured_env["NPM_CONFIG_CACHE"]


def test_main_writes_machine_readable_outputs(tmp_path: Path) -> None:
    workflow = tmp_path / "workflow.yml"
    output_json = tmp_path / "freshness.json"
    output_md = tmp_path / "freshness.md"
    output_ndjson = tmp_path / "freshness.ndjson"
    workflow.write_text(
        'run: npm install -g "@openai/codex@0.125.0"\n',
        encoding="utf-8",
    )

    exit_code = check_codex_cli_freshness.main(
        [
            "--workflow-path",
            str(workflow),
            "--latest-version",
            "0.126.0",
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
            "--output-ndjson",
            str(output_ndjson),
        ]
    )

    assert exit_code == 0
    report = json.loads(output_json.read_text(encoding="utf-8"))
    assert report["status"] == "outdated"
    assert report["pinned_version"] == "0.125.0"
    assert report["latest_version"] == "0.126.0"
    assert "Codex CLI Freshness" in output_md.read_text(encoding="utf-8")
    ndjson_report = json.loads(output_ndjson.read_text(encoding="utf-8"))
    assert ndjson_report["schema"] == "workflows-codex-cli-freshness/v1"
