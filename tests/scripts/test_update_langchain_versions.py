from __future__ import annotations

import subprocess

import pytest
from scripts import update_langchain_versions as updater


def test_get_major_minor_parses_valid_versions() -> None:
    assert updater.get_major_minor("0.3.27") == (0, 3)
    assert updater.get_major_minor("1.12.0rc1") == (1, 12)
    assert updater.get_major_minor("42.7") == (42, 7)


@pytest.mark.parametrize("version", ["", "v1.2.3", "1", "latest"])
def test_get_major_minor_rejects_invalid_versions(version: str) -> None:
    with pytest.raises(ValueError, match=f"Cannot parse version: {version}"):
        updater.get_major_minor(version)


def test_get_latest_pypi_version_uses_subprocess_json(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert capture_output is True
        assert text is True
        assert check is True
        return subprocess.CompletedProcess(command, 0, '{"info": {"version": "0.3.27"}}', "")

    monkeypatch.setattr(updater.subprocess, "run", fake_run)

    assert updater.get_latest_pypi_version("langchain-core") == "0.3.27"
    assert calls == [["curl", "-s", "https://pypi.org/pypi/langchain-core/json"]]


def test_main_prints_recommended_major_minor_constraints(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    versions = {
        "langchain": "0.3.27",
        "langchain-core": "0.3.72",
        "langchain-community": "0.3.26",
        "langchain-openai": "0.3.28",
    }

    monkeypatch.setattr(updater, "get_latest_pypi_version", versions.__getitem__)

    assert updater.main() == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert "Fetching latest versions from PyPI..." in captured.out
    for package, version in versions.items():
        major, minor = updater.get_major_minor(version)
        assert f"  {package}: {version} (^{major}.{minor})" in captured.out
        assert f'    "{package}>={major}.{minor},<{major}.{minor + 1}",' in captured.out


def test_main_returns_nonzero_and_writes_stderr_on_fetch_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_fetch(package: str) -> str:
        raise RuntimeError(f"{package} unavailable")

    monkeypatch.setattr(updater, "get_latest_pypi_version", fail_fetch)

    assert updater.main() == 1

    captured = capsys.readouterr()
    assert "Fetching latest versions from PyPI..." in captured.out
    assert "ERROR fetching langchain: langchain unavailable" in captured.err
    assert "Recommended pyproject.toml entries" not in captured.out
