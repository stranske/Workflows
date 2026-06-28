from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from scripts import list_registered_consumer_repos as lrcr

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_manifest(tmp_path: Path, lines: list[str]) -> Path:
    manifest = tmp_path / "manifest.yml"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def test_extract_repos_reads_literal_block(tmp_path) -> None:
    manifest = _write_manifest(
        tmp_path,
        [
            "name: Example",
            "env:",
            "  REGISTERED_CONSUMER_REPOS: |",
            "    stranske/Foo",
            "    stranske/Bar",
            "",
            "concurrency:",
            "  group: example",
        ],
    )

    assert lrcr.extract_repos(manifest) == ["stranske/Foo", "stranske/Bar"]


def test_extract_repos_stops_at_next_top_level_key(tmp_path) -> None:
    manifest = _write_manifest(
        tmp_path,
        [
            "env:",
            "  REGISTERED_CONSUMER_REPOS: |",
            "    stranske/Only-One",
            "jobs:",
            "  noop:",
            "    runs-on: ubuntu-latest",
        ],
    )

    assert lrcr.extract_repos(manifest) == ["stranske/Only-One"]


def test_extract_repos_returns_empty_for_missing_block(tmp_path) -> None:
    manifest = _write_manifest(
        tmp_path,
        [
            "name: Example",
            "env:",
            "  OTHER_VAR: value",
        ],
    )

    assert lrcr.extract_repos(manifest) == []


def test_extract_repos_returns_empty_for_empty_block(tmp_path) -> None:
    manifest = _write_manifest(
        tmp_path,
        [
            "env:",
            "  REGISTERED_CONSUMER_REPOS: |",
            "",
            "concurrency:",
            "  group: example",
        ],
    )

    assert lrcr.extract_repos(manifest) == []


def test_main_custom_separator(tmp_path) -> None:
    manifest = _write_manifest(
        tmp_path,
        [
            "env:",
            "  REGISTERED_CONSUMER_REPOS: |",
            "    stranske/Alpha",
            "    stranske/Beta",
        ],
    )

    exit_code = subprocess.run(
        [
            sys.executable,
            "scripts/list_registered_consumer_repos.py",
            "--manifest",
            str(manifest),
            "--separator",
            ",",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert exit_code.returncode == 0
    assert exit_code.stdout == "stranske/Alpha,stranske/Beta\n"


def test_main_default_separator_uses_newlines(tmp_path) -> None:
    manifest = _write_manifest(
        tmp_path,
        [
            "env:",
            "  REGISTERED_CONSUMER_REPOS: |",
            "    stranske/Alpha",
            "    stranske/Beta",
        ],
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/list_registered_consumer_repos.py",
            "--manifest",
            str(manifest),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout == "stranske/Alpha\nstranske/Beta\n"


def test_main_missing_manifest_exits_with_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing.yml"
    monkeypatch.setattr(
        sys,
        "argv",
        ["list_registered_consumer_repos.py", "--manifest", str(missing)],
    )

    with pytest.raises(SystemExit, match="Manifest not found"):
        lrcr.main()
