from __future__ import annotations

import pytest

from src import cli_parser


def test_cli_parser_requires_repo_sources(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli_parser.parse_args([])

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "At least one of --repo, --repos, or --repos-file is required." in captured.err


def test_cli_parser_missing_repos_file(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    missing = tmp_path / "missing.txt"

    with pytest.raises(SystemExit) as excinfo:
        cli_parser.parse_args(["--repos-file", str(missing), "--repo", "owner/repo"])

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "File not found" in captured.err


def test_cli_parser_missing_metrics_dir(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    missing_dir = tmp_path / "missing"

    with pytest.raises(SystemExit) as excinfo:
        cli_parser.parse_args(["--repos", "owner/repo", "--metrics-dir", str(missing_dir)])

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "Directory not found" in captured.err
