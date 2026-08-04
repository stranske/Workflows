import builtins
import os
import subprocess
import sys
from pathlib import Path

import pytest
import scripts.check_deliberate_break as deliberate_break
from scripts.check_deliberate_break import (
    PYTEST_RUNTIME_DEPENDENCIES,
    VERDICT_BROKEN,
    VERDICT_HOLLOW,
    VERDICT_PASS,
    parse_deliberate_break_spec,
    verify_spec,
)


def _run(repo: Path, *args: str) -> None:
    subprocess.run(args, cwd=repo, check=True, text=True, capture_output=True)


def _init_repo(repo: Path) -> None:
    _run(repo, "git", "init", "-q")
    _run(repo, "git", "config", "user.email", "test@example.com")
    _run(repo, "git", "config", "user.name", "Test User")


def _commit(repo: Path, message: str) -> str:
    _run(repo, "git", "add", ".")
    _run(repo, "git", "commit", "-qm", message)
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
    ).strip()


def _write_app(repo: Path, value: int) -> None:
    (repo / "app.py").write_text(
        f"def value():\n    return {value}\n",
        encoding="utf-8",
    )


def _write_test(repo: Path, expected: int) -> None:
    test_file = repo / "tests" / "test_app.py"
    test_file.parent.mkdir(exist_ok=True)
    test_file.write_text(
        f"import app\n\n\ndef test_value():\n    assert app.value() == {expected}\n",
        encoding="utf-8",
    )


def test_hollow_detected(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _write_app(repo, 1)
    base = _commit(repo, "base behavior")
    _write_test(repo, 1)
    _commit(repo, "candidate test")
    monkeypatch.chdir(repo)

    spec = parse_deliberate_break_spec(
        "<!-- deliberate-break: "
        "test=tests/test_app.py::test_value "
        "test-file=tests/test_app.py "
        "break-file=app.py -->"
    )
    assert spec is not None

    result = verify_spec(spec, base=base, enforce_tamper=False)

    assert result["verdict"] == VERDICT_HOLLOW


def test_sound_passes(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _write_app(repo, 0)
    base = _commit(repo, "base behavior")
    _write_app(repo, 1)
    _write_test(repo, 1)
    _commit(repo, "implementation and test")
    monkeypatch.chdir(repo)

    spec = parse_deliberate_break_spec(
        "<!-- deliberate-break: "
        "test=tests/test_app.py::test_value "
        "test-file=tests/test_app.py "
        "break-file=app.py -->"
    )
    assert spec is not None

    result = verify_spec(spec, base=base, enforce_tamper=False)

    assert result["verdict"] == VERDICT_PASS


def test_no_marker_returns_none() -> None:
    assert parse_deliberate_break_spec("## Acceptance Criteria\n- [ ] normal check") is None


def test_issue_acceptance_wording_is_supported() -> None:
    spec = parse_deliberate_break_spec(
        "## Acceptance Criteria\n\n"
        "- [ ] Named test: add `tests/scripts/test_check_deliberate_break.py` "
        "with `test_hollow_detected` (build a tmp git repo).\n"
        "- [ ] **Deliberate-break gate:** temporarily edit "
        "`scripts/check_deliberate_break.py` to skip the base-rerun.\n"
    )

    assert spec is not None
    assert spec.test_id == "tests/scripts/test_check_deliberate_break.py::test_hollow_detected"
    assert spec.test_file == "tests/scripts/test_check_deliberate_break.py"
    assert spec.break_file == "scripts/check_deliberate_break.py"


def test_assertion_tamper_is_flagged(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _write_app(repo, 0)
    _write_test(repo, 0)
    base = _commit(repo, "base test")
    _write_app(repo, 1)
    _write_test(repo, 1)
    _commit(repo, "tampered candidate")
    monkeypatch.chdir(repo)

    spec = parse_deliberate_break_spec(
        "<!-- deliberate-break: "
        "test=tests/test_app.py::test_value "
        "test-file=tests/test_app.py "
        "break-file=app.py -->"
    )
    assert spec is not None

    result = verify_spec(spec, base=base)

    assert result["verdict"] == VERDICT_BROKEN
    assert result["reason"] == "test-assertion-tamper"


def test_tamper_git_failure_is_broken(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _write_app(repo, 0)
    _write_test(repo, 0)
    base = _commit(repo, "base test")
    spec = parse_deliberate_break_spec(
        "<!-- deliberate-break: "
        "test=tests/test_app.py::test_value "
        "test-file=tests/test_app.py "
        "break-file=app.py -->"
    )
    assert spec is not None

    def fail_tamper_check(*_args, **_kwargs):
        raise subprocess.CalledProcessError(
            128,
            ["git", "diff", f"{base}...HEAD"],
            output="",
            stderr="bad revision",
        )

    monkeypatch.setattr(deliberate_break, "_changed_assertions", fail_tamper_check)

    result = verify_spec(spec, base=base, cwd=repo)

    assert result == {
        "verdict": VERDICT_BROKEN,
        "reason": "tamper-check-failed",
        "command": ["git", "diff", f"{base}...HEAD"],
        "returncode": 128,
        "stdout": "",
        "stderr": "bad revision",
    }


def test_new_assertion_in_existing_test_file_is_not_tamper(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _write_app(repo, 0)
    test_file = repo / "tests" / "test_app.py"
    test_file.parent.mkdir(exist_ok=True)
    test_file.write_text(
        "def test_existing_value():\n    assert 1 + 1 == 2\n",
        encoding="utf-8",
    )
    base = _commit(repo, "base test")
    _write_app(repo, 1)
    test_file.write_text(
        "import app\n\n\n"
        "def test_existing_value():\n"
        "    assert 1 + 1 == 2\n\n\n"
        "def test_value():\n"
        "    assert app.value() == 1\n",
        encoding="utf-8",
    )
    _commit(repo, "implementation and added assertion")
    monkeypatch.chdir(repo)

    spec = parse_deliberate_break_spec(
        "<!-- deliberate-break: "
        "test=tests/test_app.py::test_value "
        "test-file=tests/test_app.py "
        "break-file=app.py -->"
    )
    assert spec is not None

    result = verify_spec(spec, base=base)

    assert result["verdict"] == VERDICT_PASS


def test_added_acceptance_test_is_not_tamper(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _write_app(repo, 0)
    base = _commit(repo, "base behavior")
    _write_app(repo, 1)
    _write_test(repo, 1)
    _commit(repo, "implementation and new test")
    monkeypatch.chdir(repo)

    spec = parse_deliberate_break_spec(
        "<!-- deliberate-break: "
        "test=tests/test_app.py::test_value "
        "test-file=tests/test_app.py "
        "break-file=app.py -->"
    )
    assert spec is not None

    result = verify_spec(spec, base=base)

    assert result["verdict"] == VERDICT_PASS


def test_cli_skips_without_marker(tmp_path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[2] / "scripts" / "check_deliberate_break.py"),
            "--base",
            "HEAD",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        env={**os.environ, "PR_BODY": "## Acceptance Criteria\n- [ ] normal"},
    )

    assert completed.returncode == 0
    assert "skipped: no deliberate-break marker" in completed.stdout


def test_runtime_dependency_installer_uses_locked_pyyaml(monkeypatch) -> None:
    real_import = builtins.__import__
    calls: list[tuple[object, dict[str, object]]] = []

    def missing_yaml(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("PyYAML missing")
        return real_import(name, *args, **kwargs)

    def record_install(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], 0, "", "")

    monkeypatch.setattr(builtins, "__import__", missing_yaml)
    monkeypatch.setattr(deliberate_break.subprocess, "run", record_install)

    deliberate_break._ensure_pytest_runtime_deps()

    assert calls == [
        (
            (
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    *PYTEST_RUNTIME_DEPENDENCIES,
                ],
            ),
            {
                "check": True,
                "text": True,
                "capture_output": True,
                "timeout": deliberate_break.DEFAULT_TIMEOUT_SECONDS,
            },
        )
    ]


def _sound_spec(repo: Path) -> tuple[str, object]:
    _write_app(repo, 0)
    base = _commit(repo, "base behavior")
    _write_app(repo, 1)
    _write_test(repo, 1)
    _commit(repo, "implementation and test")
    spec = parse_deliberate_break_spec(
        "<!-- deliberate-break: "
        "test=tests/test_app.py::test_value "
        "test-file=tests/test_app.py "
        "break-file=app.py -->"
    )
    assert spec is not None
    return base, spec


def test_dependency_install_timeout_is_broken(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    base, spec = _sound_spec(repo)
    command = [sys.executable, "-m", "pip", "install", *PYTEST_RUNTIME_DEPENDENCIES]

    def timed_out() -> None:
        raise subprocess.TimeoutExpired(command, 17)

    monkeypatch.setattr(deliberate_break, "_ensure_pytest_runtime_deps", timed_out)

    result = verify_spec(spec, base=base, cwd=repo, enforce_tamper=False)

    assert result == {
        "verdict": VERDICT_BROKEN,
        "reason": "command-timeout",
        "command": command,
        "timeout": 17,
    }


@pytest.mark.parametrize(
    ("error", "reason", "detail"),
    [
        (
            subprocess.CalledProcessError(1, ["pip"], stderr="pip denied"),
            "dependency-install-failed",
            "pip denied",
        ),
        (OSError("pip unavailable"), "dependency-install-unavailable", "pip unavailable"),
    ],
)
def test_dependency_install_errors_are_broken(tmp_path, monkeypatch, error, reason, detail) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    base, spec = _sound_spec(repo)

    def failed() -> None:
        raise error

    monkeypatch.setattr(deliberate_break, "_ensure_pytest_runtime_deps", failed)

    result = verify_spec(spec, base=base, cwd=repo, enforce_tamper=False)

    assert result == {"verdict": VERDICT_BROKEN, "reason": reason, "detail": detail}
