from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.check_template_drift import (
    AllowlistEntry,
    TemplateDriftAllowlist,
    drift_between,
    main,
    normalized_sha256,
)


def test_drift_between_false_for_identical_normalized_content() -> None:
    main = "name: Demo\r\njobs:\r\n  check: value  \r\n"
    template = "name: Demo\njobs:\n  check: value\n"

    assert drift_between(main, template) is False


def test_drift_between_detects_genuine_content_change() -> None:
    assert drift_between("jobs:\n  check: old\n", "jobs:\n  check: new\n") is True


def test_drift_between_honors_matching_fingerprinted_allowlist() -> None:
    main = "name: main\njobs:\n  check: true\n"
    template = "name: template\njobs:\n  check: true\n"
    allowlist = TemplateDriftAllowlist(
        (
            AllowlistEntry(
                main_path=".github/workflows/agents-demo.yml",
                template_path="templates/consumer-repo/.github/workflows/agents-demo.yml",
                main_sha256=normalized_sha256(main),
                template_sha256=normalized_sha256(template),
                reason="intentional baseline",
            ),
        )
    )

    assert (
        drift_between(
            main,
            template,
            allowlist,
            main_path=".github/workflows/agents-demo.yml",
            template_path="templates/consumer-repo/.github/workflows/agents-demo.yml",
        )
        is False
    )


def test_drift_between_rejects_stale_allowlist_fingerprint() -> None:
    main = "name: main\njobs:\n  check: true\n"
    template = "name: template\njobs:\n  check: true\n"
    stale_template = "name: template\njobs:\n  check: false\n"
    allowlist = TemplateDriftAllowlist(
        (
            AllowlistEntry(
                main_path=".github/workflows/agents-demo.yml",
                template_path="templates/consumer-repo/.github/workflows/agents-demo.yml",
                main_sha256=normalized_sha256(main),
                template_sha256=normalized_sha256(template),
                reason="intentional baseline",
            ),
        )
    )

    assert (
        drift_between(
            main,
            stale_template,
            allowlist,
            main_path=".github/workflows/agents-demo.yml",
            template_path="templates/consumer-repo/.github/workflows/agents-demo.yml",
        )
        is True
    )


def test_cli_fails_on_unallowlisted_agent_template_drift(tmp_path: Path) -> None:
    _write_pair(tmp_path, "agents-demo.yml", "one\n", "two\n")

    result = _run_checker(tmp_path)

    assert result.returncode == 1
    assert "Unallowlisted Drift" in result.stdout
    assert "agents-demo.yml" in result.stdout


def test_cli_fails_when_agent_template_counterpart_is_missing(tmp_path: Path) -> None:
    main_path = tmp_path / ".github" / "workflows" / "agents-demo.yml"
    main_path.parent.mkdir(parents=True)
    main_path.write_text("name: demo\n", encoding="utf-8")
    manifest_path = tmp_path / ".github" / "sync-manifest.yml"
    manifest_path.write_text(
        "\n".join(
            [
                "version: 1",
                "workflows:",
                "  - source: .github/workflows/agents-demo.yml",
                "    description: Demo workflow",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = _run_checker(tmp_path)

    assert result.returncode == 1
    assert "template counterpart is missing" in result.stdout
    assert "templates/consumer-repo/.github/workflows/agents-demo.yml" in result.stdout


def test_cli_passes_on_allowlisted_agent_template_drift(tmp_path: Path) -> None:
    main = "one\n"
    template = "two\n"
    _write_pair(tmp_path, "agents-demo.yml", main, template)
    allowlist = tmp_path / "config" / "template-drift-allowlist.txt"
    allowlist.parent.mkdir(parents=True)
    allowlist.write_text(
        "\n".join(
            [
                "[pair.demo]",
                "main = .github/workflows/agents-demo.yml",
                "template = templates/consumer-repo/.github/workflows/agents-demo.yml",
                f"main_sha256 = {normalized_sha256(main)}",
                f"template_sha256 = {normalized_sha256(template)}",
                "reason = intentional test baseline",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = _run_checker(tmp_path)

    assert result.returncode == 0
    assert "allowlisted baseline drift: 1" in result.stdout


def test_main_empty_argv_ignores_process_argv(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_template_drift.py",
            "--repo-root",
            str(tmp_path / "missing"),
        ],
    )

    assert main([]) == 0


def _write_pair(tmp_path: Path, filename: str, main: str, template: str) -> None:
    main_path = tmp_path / ".github" / "workflows" / filename
    template_path = tmp_path / "templates" / "consumer-repo" / ".github" / "workflows" / filename
    main_path.parent.mkdir(parents=True)
    template_path.parent.mkdir(parents=True)
    main_path.write_text(main, encoding="utf-8")
    template_path.write_text(template, encoding="utf-8")


def _run_checker(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[2] / "scripts" / "check_template_drift.py"),
            "--repo-root",
            str(tmp_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
