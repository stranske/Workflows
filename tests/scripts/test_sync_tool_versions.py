from __future__ import annotations

from pathlib import Path

import pytest

from scripts import sync_tool_versions


def _write_env_file(path: Path, versions: dict[str, str]) -> None:
    lines = []
    for cfg in sync_tool_versions.TOOL_CONFIGS:
        if cfg.env_key in versions:
            lines.append(f"{cfg.env_key}={versions[cfg.env_key]}")
    lines.append("# comment")
    lines.append("INVALID")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _make_pyproject_content(versions: dict[str, str]) -> str:
    entries: list[str] = []
    for cfg in sync_tool_versions.TOOL_CONFIGS:
        version = versions[cfg.env_key]
        if cfg.package_name == "mypy":
            entries.append(f'"mypy>={version}",')
        else:
            entries.append(f'"{cfg.package_name}=={version}",')
    return "\n".join(entries) + "\n"


def test_parse_env_file_missing_path(tmp_path: Path) -> None:
    missing = tmp_path / "missing.env"

    with pytest.raises(sync_tool_versions.SyncError, match="does not exist"):
        sync_tool_versions.parse_env_file(missing)


def test_parse_env_file_missing_keys(tmp_path: Path) -> None:
    env_path = tmp_path / "pins.env"
    _write_env_file(env_path, {"BLACK_VERSION": "1"})

    with pytest.raises(sync_tool_versions.SyncError, match="missing keys"):
        sync_tool_versions.parse_env_file(env_path)


def test_parse_env_file_reads_values(tmp_path: Path) -> None:
    env_path = tmp_path / "pins.env"
    versions = {cfg.env_key: "1.0" for cfg in sync_tool_versions.TOOL_CONFIGS}
    _write_env_file(env_path, versions)

    parsed = sync_tool_versions.parse_env_file(env_path)

    assert parsed["BLACK_VERSION"] == "1.0"


def test_ensure_pyproject_missing_entry() -> None:
    versions = {cfg.env_key: "1.0" for cfg in sync_tool_versions.TOOL_CONFIGS}
    content = _make_pyproject_content(versions).replace('"ruff==1.0",\n', "")

    with pytest.raises(sync_tool_versions.SyncError, match="missing an entry"):
        sync_tool_versions.ensure_pyproject(
            content, sync_tool_versions.TOOL_CONFIGS, versions, False
        )


def test_ensure_pyproject_mismatch_without_apply() -> None:
    env_versions = {cfg.env_key: "2.0" for cfg in sync_tool_versions.TOOL_CONFIGS}
    content_versions = env_versions | {"RUFF_VERSION": "1.0"}
    content = _make_pyproject_content(content_versions)

    updated, mismatches = sync_tool_versions.ensure_pyproject(
        content, sync_tool_versions.TOOL_CONFIGS, env_versions, False
    )

    assert updated == content
    assert "ruff" in mismatches


def test_ensure_pyproject_apply_updates_version() -> None:
    env_versions = {cfg.env_key: "3.0" for cfg in sync_tool_versions.TOOL_CONFIGS}
    content_versions = env_versions | {"MYPY_VERSION": "1.0"}
    content = _make_pyproject_content(content_versions)

    updated, mismatches = sync_tool_versions.ensure_pyproject(
        content, sync_tool_versions.TOOL_CONFIGS, env_versions, True
    )

    assert "mypy" in mismatches
    assert '"mypy==3.0",' in updated


def test_ensure_pyproject_apply_no_changes() -> None:
    env_versions = {cfg.env_key: "5.0" for cfg in sync_tool_versions.TOOL_CONFIGS}
    content = _make_pyproject_content(env_versions)

    updated, mismatches = sync_tool_versions.ensure_pyproject(
        content, sync_tool_versions.TOOL_CONFIGS, env_versions, True
    )

    assert mismatches == {}
    assert updated == content


def test_main_reports_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env_path = tmp_path / "pins.env"
    pyproject_path = tmp_path / "pyproject.toml"
    env_versions = {cfg.env_key: "2.0" for cfg in sync_tool_versions.TOOL_CONFIGS}
    content_versions = env_versions | {"BLACK_VERSION": "1.0"}

    _write_env_file(env_path, env_versions)
    pyproject_path.write_text(_make_pyproject_content(content_versions), encoding="utf-8")

    monkeypatch.setattr(sync_tool_versions, "PIN_FILE", env_path)
    monkeypatch.setattr(sync_tool_versions, "PYPROJECT_FILE", pyproject_path)

    exit_code = sync_tool_versions.main([])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "black" in captured.err


def test_main_apply_updates_pyproject(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = tmp_path / "pins.env"
    pyproject_path = tmp_path / "pyproject.toml"
    env_versions = {cfg.env_key: "4.0" for cfg in sync_tool_versions.TOOL_CONFIGS}
    content_versions = env_versions | {"PYTEST_VERSION": "3.0"}

    _write_env_file(env_path, env_versions)
    pyproject_path.write_text(_make_pyproject_content(content_versions), encoding="utf-8")

    monkeypatch.setattr(sync_tool_versions, "PIN_FILE", env_path)
    monkeypatch.setattr(sync_tool_versions, "PYPROJECT_FILE", pyproject_path)

    exit_code = sync_tool_versions.main(["--apply"])

    assert exit_code == 0
    assert '"pytest==4.0",' in pyproject_path.read_text(encoding="utf-8")


def test_main_check_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env_path = tmp_path / "pins.env"
    pyproject_path = tmp_path / "pyproject.toml"
    env_versions = {cfg.env_key: "6.0" for cfg in sync_tool_versions.TOOL_CONFIGS}

    _write_env_file(env_path, env_versions)
    pyproject_path.write_text(_make_pyproject_content(env_versions), encoding="utf-8")

    monkeypatch.setattr(sync_tool_versions, "PIN_FILE", env_path)
    monkeypatch.setattr(sync_tool_versions, "PYPROJECT_FILE", pyproject_path)

    exit_code = sync_tool_versions.main(["--check"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""


def test_main_apply_no_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env_path = tmp_path / "pins.env"
    pyproject_path = tmp_path / "pyproject.toml"
    env_versions = {cfg.env_key: "7.0" for cfg in sync_tool_versions.TOOL_CONFIGS}

    _write_env_file(env_path, env_versions)
    pyproject_path.write_text(_make_pyproject_content(env_versions), encoding="utf-8")

    monkeypatch.setattr(sync_tool_versions, "PIN_FILE", env_path)
    monkeypatch.setattr(sync_tool_versions, "PYPROJECT_FILE", pyproject_path)

    exit_code = sync_tool_versions.main(["--apply"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "tool pins synced" not in captured.out


def test_main_rejects_check_and_apply_together() -> None:
    with pytest.raises(SystemExit):
        sync_tool_versions.main(["--check", "--apply"])
