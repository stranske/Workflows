from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts import run_consumer_repo_tests


def test_ensure_destination_existing_non_empty_raises(tmp_path: Path) -> None:
    destination = tmp_path / "repo"
    destination.mkdir()
    (destination / "existing.txt").write_text("data", encoding="utf-8")

    with pytest.raises(FileExistsError):
        run_consumer_repo_tests.ensure_destination(destination, force=False)


def test_ensure_destination_force_clears(tmp_path: Path) -> None:
    destination = tmp_path / "repo"
    destination.mkdir()
    (destination / "existing.txt").write_text("data", encoding="utf-8")

    run_consumer_repo_tests.ensure_destination(destination, force=True)

    assert destination.exists()
    assert list(destination.iterdir()) == []


def test_build_pytest_command_uses_sys_executable() -> None:
    command = run_consumer_repo_tests.build_pytest_command(["-q"])

    assert command[0] == sys.executable
    assert command[1:] == ["-m", "pytest", "-q"]


def test_build_pytest_env_sets_pythonpath(tmp_path: Path) -> None:
    destination = tmp_path / "repo"
    env = run_consumer_repo_tests.build_pytest_env(destination)

    assert env["PYTHONPATH"].startswith(str(destination.resolve() / "src"))


def test_main_skip_render_missing_destination(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    destination = tmp_path / "missing"

    result = run_consumer_repo_tests.main(["--skip-render", "--destination", str(destination)])

    captured = capsys.readouterr()
    assert result == 1
    assert "Destination not found" in captured.err


def test_main_renders_and_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    destination = tmp_path / "rendered"
    calls: dict[str, object] = {}

    def fake_render(path: Path, workflow_ref: str) -> None:
        calls["render"] = (path, workflow_ref)

    def fake_run(path: Path, pytest_args: list[str]) -> int:
        calls["run"] = (path, pytest_args)
        return 0

    monkeypatch.setattr(run_consumer_repo_tests, "render_integration_repo", fake_render)
    monkeypatch.setattr(run_consumer_repo_tests, "run_pytest", fake_run)

    result = run_consumer_repo_tests.main(
        [
            "--destination",
            str(destination),
            "--workflow-ref",
            "owner/repo/.github/workflows/ci.yml@main",
            "--pytest-args",
            "-q",
        ]
    )

    assert result == 0
    assert calls["render"] == (
        destination,
        "owner/repo/.github/workflows/ci.yml@main",
    )
    assert calls["run"] == (destination, ["-q"])
