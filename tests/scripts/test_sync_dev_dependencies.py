from __future__ import annotations

from pathlib import Path

import pytest

from scripts import sync_dev_dependencies as sdd


def _write_env_file(path: Path, versions: dict[str, str]) -> None:
    lines = [f"{key}={value}" for key, value in versions.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_pyproject(path: Path, ruff_version: str, black_version: str) -> None:
    content = "\n".join(
        [
            "[project.optional-dependencies]",
            "dev = [",
            f'  "ruff=={ruff_version}",',
            f'  "black=={black_version}",',
            "]",
            "",
        ]
    )
    path.write_text(content, encoding="utf-8")


def test_sync_lockfile_skips_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "requirements.lock"
    pins = {"RUFF_VERSION": "1.0.0"}

    changes, errors = sdd.sync_lockfile(missing, pins, apply=False)

    assert changes == []
    assert errors == []


def test_sync_lockfile_apply_updates_versions(tmp_path: Path) -> None:
    lockfile = tmp_path / "requirements.lock"
    lockfile.write_text(
        "\n".join(
            [
                "ruff==0.1.0",
                "black==0.2.0",
                "requests==2.0.0",
                "# comment",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    pins = {"RUFF_VERSION": "1.0.0", "BLACK_VERSION": "2.0.0"}

    changes, errors = sdd.sync_lockfile(lockfile, pins, apply=True)

    assert errors == []
    assert "requirements.lock:ruff: 0.1.0 -> ==1.0.0" in changes
    assert "requirements.lock:black: 0.2.0 -> ==2.0.0" in changes
    updated = lockfile.read_text(encoding="utf-8")
    assert "ruff==1.0.0" in updated
    assert "black==2.0.0" in updated
    assert "requests==2.0.0" in updated


def test_main_apply_updates_pyproject_and_lockfile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / "pins.env"
    pyproject_path = tmp_path / "pyproject.toml"
    lockfile = tmp_path / "requirements.lock"
    pins = {"RUFF_VERSION": "1.0.0", "BLACK_VERSION": "2.0.0"}

    _write_env_file(env_path, pins)
    _write_pyproject(pyproject_path, "0.9.0", "2.0.0")
    lockfile.write_text("ruff==0.9.0\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    exit_code = sdd.main(
        [
            "--apply",
            "--lockfile",
            "--pin-file",
            str(env_path),
            "--pyproject",
            str(pyproject_path),
        ]
    )

    assert exit_code == 0
    assert "ruff==1.0.0" in pyproject_path.read_text(encoding="utf-8")
    assert "ruff==1.0.0" in lockfile.read_text(encoding="utf-8")


def test_main_check_reports_lockfile_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env_path = tmp_path / "pins.env"
    pyproject_path = tmp_path / "pyproject.toml"
    lockfile = tmp_path / "requirements.lock"
    pins = {"RUFF_VERSION": "1.0.0", "BLACK_VERSION": "2.0.0"}

    _write_env_file(env_path, pins)
    _write_pyproject(pyproject_path, "1.0.0", "2.0.0")
    lockfile.write_text("ruff==0.9.0\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    exit_code = sdd.main(
        [
            "--check",
            "--lockfile",
            "--pin-file",
            str(env_path),
            "--pyproject",
            str(pyproject_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "requirements.lock:ruff" in captured.out


def test_main_check_skips_missing_lockfile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = tmp_path / "pins.env"
    pyproject_path = tmp_path / "pyproject.toml"
    pins = {"RUFF_VERSION": "1.0.0", "BLACK_VERSION": "2.0.0"}

    _write_env_file(env_path, pins)
    _write_pyproject(pyproject_path, "1.0.0", "2.0.0")

    monkeypatch.chdir(tmp_path)

    exit_code = sdd.main(
        [
            "--check",
            "--lockfile",
            "--pin-file",
            str(env_path),
            "--pyproject",
            str(pyproject_path),
        ]
    )

    assert exit_code == 0
