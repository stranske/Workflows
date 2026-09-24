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
    disposable_root = tmp_path / ".consumer-tests"
    destination = disposable_root / "repo"
    destination.mkdir(parents=True)
    (destination / "existing.txt").write_text("data", encoding="utf-8")

    run_consumer_repo_tests.ensure_destination(
        destination,
        force=True,
        disposable_root=disposable_root,
    )

    assert destination.exists()
    assert list(destination.iterdir()) == []


def test_ensure_destination_force_rejects_outside_disposable_root(
    tmp_path: Path,
) -> None:
    disposable_root = tmp_path / ".consumer-tests"
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    survivor = outside_dir / "survivor.txt"
    survivor.write_text("keep", encoding="utf-8")

    with pytest.raises(run_consumer_repo_tests.UnsafeDestinationError):
        run_consumer_repo_tests.ensure_destination(
            outside_dir,
            force=True,
            disposable_root=disposable_root,
        )

    assert outside_dir.is_dir()
    assert survivor.read_text(encoding="utf-8") == "keep"


def test_ensure_destination_force_rejects_disposable_root(tmp_path: Path) -> None:
    disposable_root = tmp_path / ".consumer-tests"
    disposable_root.mkdir()
    survivor = disposable_root / "survivor.txt"
    survivor.write_text("keep", encoding="utf-8")

    with pytest.raises(run_consumer_repo_tests.UnsafeDestinationError):
        run_consumer_repo_tests.ensure_destination(
            disposable_root,
            force=True,
            disposable_root=disposable_root,
        )

    assert survivor.read_text(encoding="utf-8") == "keep"


def test_ensure_destination_force_rejects_symlink_destination(tmp_path: Path) -> None:
    disposable_root = tmp_path / ".consumer-tests"
    disposable_root.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    survivor = outside_dir / "survivor.txt"
    survivor.write_text("keep", encoding="utf-8")
    destination = disposable_root / "repo"
    destination.symlink_to(outside_dir, target_is_directory=True)

    with pytest.raises(run_consumer_repo_tests.UnsafeDestinationError):
        run_consumer_repo_tests.ensure_destination(
            destination,
            force=True,
            disposable_root=disposable_root,
        )

    assert destination.is_symlink()
    assert survivor.read_text(encoding="utf-8") == "keep"


def test_ensure_destination_force_rejects_symlink_disposable_root(
    tmp_path: Path,
) -> None:
    physical_root = tmp_path / "outside-disposable"
    destination = physical_root / "repo"
    destination.mkdir(parents=True)
    survivor = destination / "survivor.txt"
    survivor.write_text("keep", encoding="utf-8")
    disposable_root = tmp_path / ".consumer-tests"
    disposable_root.symlink_to(physical_root, target_is_directory=True)

    with pytest.raises(run_consumer_repo_tests.UnsafeDestinationError):
        run_consumer_repo_tests.ensure_destination(
            disposable_root / "repo",
            force=True,
            disposable_root=disposable_root,
        )

    assert disposable_root.is_symlink()
    assert survivor.read_text(encoding="utf-8") == "keep"


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


def test_main_force_outside_disposable_root_returns_1(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    survivor = outside_dir / "survivor.txt"
    survivor.write_text("keep", encoding="utf-8")

    result = run_consumer_repo_tests.main(["--destination", str(outside_dir), "--force"])

    captured = capsys.readouterr()
    assert result == 1
    assert str(outside_dir) in captured.err
    assert ".consumer-tests" in captured.err
    assert survivor.read_text(encoding="utf-8") == "keep"


def test_main_skip_render_force_does_not_apply_disposable_root_guard(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    calls: dict[str, object] = {}

    def fake_run(path: Path, pytest_args: list[str]) -> int:
        calls["run"] = (path, pytest_args)
        return 7

    monkeypatch.setattr(run_consumer_repo_tests, "run_pytest", fake_run)

    result = run_consumer_repo_tests.main(
        [
            "--skip-render",
            "--destination",
            str(outside_dir),
            "--force",
            "--pytest-args",
            "-q",
        ]
    )

    assert result == 7
    assert calls["run"] == (outside_dir, ["-q"])


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
