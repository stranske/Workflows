from __future__ import annotations

from pathlib import Path

from scripts import sync_dev_dependencies as sdd


def _write_pins(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "BLACK_VERSION=26.5.1",
                "RUFF_VERSION=0.16.2",
                "MYPY_VERSION=2.3.0",
                "ISORT_VERSION=7.0.0",
                "DOCFORMATTER_VERSION=1.7.7",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_pyproject(path: Path) -> None:
    path.write_text(
        '[project.optional-dependencies]\ndev = [\n  "black==26.5.1",\n  "ruff==0.16.2",\n]\n',
        encoding="utf-8",
    )


def test_precommit_rev_pins_follow_autofix_versions(tmp_path: Path, monkeypatch) -> None:
    """Named gate: detect, repair, preserve prefixes, and remain idempotent."""
    pins = tmp_path / "pins.env"
    pyproject = tmp_path / "pyproject.toml"
    config = tmp_path / ".pre-commit-config.yaml"
    _write_pins(pins)
    _write_pyproject(pyproject)
    config.write_text(
        "repos:\n"
        "  - repo: https://github.com/psf/black\n"
        '    rev: "v24.8.0"  # managed\n'
        "  - repo: https://github.com/astral-sh/ruff-pre-commit\n"
        "    rev: 'v0.15.0'\n"
        "  - repo: https://github.com/pre-commit/mirrors-mypy\n"
        "    rev: v2.2.0\n"
        "  - repo: https://github.com/PyCQA/isort\n"
        "    rev: 6.0.0\n"
        "  - repo: https://github.com/PyCQA/docformatter\n"
        "    rev: v1.7.6\n"
        "  - repo: local\n"
        "    hooks:\n"
        "      - id: keep-local\n"
        "        entry: echo keep-local\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    assert (
        sdd.main(
            ["--check", "--pre-commit", "--pin-file", str(pins), "--pyproject", str(pyproject)]
        )
        == 1
    )
    assert (
        sdd.main(
            ["--apply", "--pre-commit", "--pin-file", str(pins), "--pyproject", str(pyproject)]
        )
        == 0
    )
    applied = config.read_text(encoding="utf-8")
    assert 'rev: "v26.5.1"  # managed' in applied
    assert "rev: 'v0.16.2'" in applied
    assert "rev: v2.3.0" in applied
    assert "rev: 7.0.0" in applied
    assert "rev: v1.7.7" in applied
    assert "entry: echo keep-local" in applied
    assert (
        sdd.main(
            ["--check", "--pre-commit", "--pin-file", str(pins), "--pyproject", str(pyproject)]
        )
        == 0
    )
    assert (
        sdd.main(
            ["--apply", "--pre-commit", "--pin-file", str(pins), "--pyproject", str(pyproject)]
        )
        == 0
    )
    assert config.read_text(encoding="utf-8") == applied


def test_precommit_sync_recognizes_legacy_ruff_repository(tmp_path: Path) -> None:
    config = tmp_path / ".pre-commit-config.yaml"
    config.write_text(
        "repos:\n"
        "  - repo: https://github.com/charliermarsh/ruff-pre-commit\n"
        "    rev: v0.5.0\n",
        encoding="utf-8",
    )

    changes, errors = sdd.sync_pre_commit_config(config, {"RUFF_VERSION": "0.16.2"}, apply=True)

    assert errors == []
    assert changes == [".pre-commit-config.yaml:charliermarsh/ruff-pre-commit: v0.5.0 -> v0.16.2"]
    assert "rev: v0.16.2" in config.read_text(encoding="utf-8")


def test_default_check_defers_precommit_until_maint52_wave(tmp_path: Path, monkeypatch) -> None:
    pins = tmp_path / "pins.env"
    pyproject = tmp_path / "pyproject.toml"
    config = tmp_path / ".pre-commit-config.yaml"
    _write_pins(pins)
    _write_pyproject(pyproject)
    original = "repos:\n  - repo: https://github.com/psf/black\n    rev: 24.8.0\n"
    config.write_text(original, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert sdd.main(["--check", "--pin-file", str(pins), "--pyproject", str(pyproject)]) == 0
    assert sdd.main(["--apply", "--pin-file", str(pins), "--pyproject", str(pyproject)]) == 0
    assert config.read_text(encoding="utf-8") == original


def test_precommit_sync_preserves_revision_line_endings_and_ignores_untrusted_hosts(
    tmp_path: Path,
) -> None:
    config = tmp_path / ".pre-commit-config.yaml"
    config.write_bytes(
        b"repos:\r\n"
        b"  - repo: https://not-github.example/github.com/psf/black\r\n"
        b"    rev: 24.8.0\r\n"
        b"  - repo: https://github.com/psf/black\r\n"
        b"    rev: 24.8.0\r\n"
        b"    hooks:\r\n"
    )

    changes, errors = sdd.sync_pre_commit_config(config, {"BLACK_VERSION": "26.5.1"}, apply=True)

    assert errors == []
    assert changes == [".pre-commit-config.yaml:psf/black: 24.8.0 -> 26.5.1"]
    assert config.read_bytes() == (
        b"repos:\r\n"
        b"  - repo: https://not-github.example/github.com/psf/black\r\n"
        b"    rev: 24.8.0\r\n"
        b"  - repo: https://github.com/psf/black\r\n"
        b"    rev: 26.5.1\r\n"
        b"    hooks:\r\n"
    )


def test_precommit_sync_skips_missing_config(tmp_path: Path) -> None:
    changes, errors = sdd.sync_pre_commit_config(
        tmp_path / ".pre-commit-config.yaml", {"BLACK_VERSION": "26.5.1"}
    )
    assert changes == []
    assert errors == []
