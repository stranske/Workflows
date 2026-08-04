import ast
import json
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


def test_tamper_os_error_is_broken(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    base, spec = _sound_spec(repo)
    monkeypatch.setattr(
        deliberate_break,
        "_changed_assertions",
        lambda *_args: (_ for _ in ()).throw(FileNotFoundError("git unavailable")),
    )

    result = verify_spec(spec, base=base, cwd=repo)

    assert result == {
        "verdict": VERDICT_BROKEN,
        "reason": "tamper-check-unavailable",
        "detail": "git unavailable",
    }


def test_tamper_timeout_has_distinct_reason(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    base, spec = _sound_spec(repo)
    command = ["git", "diff", f"{base}...HEAD"]
    monkeypatch.setattr(
        deliberate_break,
        "_changed_assertions",
        lambda *_args: (_ for _ in ()).throw(subprocess.TimeoutExpired(command, 17)),
    )

    result = verify_spec(spec, base=base, cwd=repo)

    assert result == {
        "verdict": VERDICT_BROKEN,
        "reason": "tamper-check-timeout",
        "command": command,
        "timeout": 17,
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


@pytest.mark.parametrize("installed_version", [None, "6.0.2"])
def test_runtime_dependency_installer_uses_locked_pyyaml(monkeypatch, installed_version) -> None:
    calls: list[tuple[object, dict[str, object]]] = []
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    def package_version(_name):
        if installed_version is None:
            raise deliberate_break.metadata.PackageNotFoundError
        return installed_version

    def record_install(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], 0, "", "")

    monkeypatch.setattr(deliberate_break.metadata, "version", package_version)
    monkeypatch.setattr(deliberate_break, "import_module", lambda _name: object())
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


def test_runtime_dependency_installer_accepts_exact_locked_pyyaml(monkeypatch) -> None:
    calls: list[object] = []

    monkeypatch.setattr(
        deliberate_break.metadata,
        "version",
        lambda _name: deliberate_break.PYYAML_VERSION,
    )
    monkeypatch.setattr(deliberate_break, "import_module", lambda _name: object())
    monkeypatch.setattr(
        deliberate_break.subprocess,
        "run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    deliberate_break._ensure_pytest_runtime_deps()

    assert calls == []


@pytest.mark.parametrize(
    ("installed_version", "supported"),
    [
        (None, False),
        ("6.0.2", False),
        ("6.0.3", True),
        ("6.0.3.0", True),
        ("6.0.3.post1", True),
        ("6.0.2.post1", False),
        ("6.0.3+local.1", True),
        ("6.0.4", True),
        ("6.0.4rc1", True),
        ("6.0.4.dev0", True),
        ("99.0.0", True),
        ("6.0.3rc1", False),
        ("6.0.3.dev0", False),
        ("not-a-version", False),
    ],
)
def test_supported_pyyaml_version_uses_stdlib_only(installed_version, supported) -> None:
    assert deliberate_break._supported_pyyaml_version(installed_version) is supported


def test_pyyaml_version_check_does_not_import_packaging() -> None:
    module = ast.parse(Path(deliberate_break.__file__).read_text(encoding="utf-8"))
    imported_modules: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module.split(".", 1)[0])

    assert "packaging" not in imported_modules


def test_runtime_dependency_installer_accepts_newer_compatible_pyyaml(monkeypatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(deliberate_break.metadata, "version", lambda _name: "99.0.0")
    monkeypatch.setattr(deliberate_break, "import_module", lambda _name: object())
    monkeypatch.setattr(
        deliberate_break.subprocess,
        "run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    deliberate_break._ensure_pytest_runtime_deps()

    assert calls == []
    assert not deliberate_break._pyyaml_runtime_needs_repair()


@pytest.mark.parametrize("import_error", [ImportError, OSError, AttributeError, SyntaxError])
def test_runtime_dependency_installer_repairs_broken_pyyaml_import(
    monkeypatch, import_error
) -> None:
    calls: list[tuple[object, dict[str, object]]] = []
    imports = 0
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    def broken_import(_name):
        nonlocal imports
        imports += 1
        if imports == 1:
            raise import_error("broken PyYAML install")
        return object()

    monkeypatch.setattr(
        deliberate_break.metadata,
        "version",
        lambda _name: deliberate_break.PYYAML_VERSION,
    )
    monkeypatch.setattr(deliberate_break, "import_module", broken_import)
    monkeypatch.setattr(
        deliberate_break.subprocess,
        "run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    deliberate_break._ensure_pytest_runtime_deps()

    assert len(calls) == 1
    assert calls[0][0][0][-1] == f"pyyaml=={deliberate_break.PYYAML_VERSION}"
    assert "--force-reinstall" in calls[0][0][0]
    assert imports == 2


def test_runtime_dependency_installer_preserves_initial_import_failure(
    monkeypatch,
) -> None:
    initial_error = OSError("broken PyYAML install")
    imports = 0
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    def broken_import(_name):
        nonlocal imports
        imports += 1
        if imports == 1:
            raise initial_error
        raise AttributeError("still broken after reinstall")

    monkeypatch.setattr(
        deliberate_break.metadata,
        "version",
        lambda _name: deliberate_break.PYYAML_VERSION,
    )
    monkeypatch.setattr(deliberate_break, "import_module", broken_import)
    monkeypatch.setattr(
        deliberate_break.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "", ""),
    )

    with pytest.raises(ImportError, match="still broken after reinstall") as caught:
        deliberate_break._ensure_pytest_runtime_deps()

    assert caught.value.__cause__ is initial_error
    assert imports == 2


def test_runtime_dependency_installer_does_not_modify_local_environment(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(
        deliberate_break.metadata,
        "version",
        lambda _name: (_ for _ in ()).throw(deliberate_break.metadata.PackageNotFoundError),
    )
    monkeypatch.setattr(
        deliberate_break.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("local dependency install should not run"),
    )

    with pytest.raises(ImportError, match=r"install 'PyYAML>=6\.0\.3'"):
        deliberate_break._ensure_pytest_runtime_deps()


def test_runtime_dependencies_are_not_installed_for_successful_custom_command(
    tmp_path, monkeypatch
) -> None:
    completed = subprocess.CompletedProcess(["custom-check"], 0, "ok", "")
    monkeypatch.setattr(deliberate_break, "_run", lambda *_args: completed)
    monkeypatch.setattr(
        deliberate_break,
        "_ensure_pytest_runtime_deps",
        lambda: pytest.fail("dependency repair should not run"),
    )

    assert deliberate_break._run_with_runtime_deps(("custom-check",), tmp_path) is completed


def test_runtime_dependencies_are_not_installed_for_unrelated_failure(
    tmp_path, monkeypatch
) -> None:
    completed = subprocess.CompletedProcess(["custom-check"], 1, "", "assertion failed")
    monkeypatch.setattr(deliberate_break, "_run", lambda *_args: completed)
    monkeypatch.setattr(
        deliberate_break,
        "_ensure_pytest_runtime_deps",
        lambda: pytest.fail("dependency repair should not run"),
    )

    assert deliberate_break._run_with_runtime_deps(("custom-check",), tmp_path) is completed


def test_runtime_dependencies_are_not_installed_for_unrelated_pyyaml_mention(
    tmp_path, monkeypatch
) -> None:
    completed = subprocess.CompletedProcess(
        ["custom-check"], 1, "", "test_pyyaml_behavior: assertion failed"
    )
    monkeypatch.setattr(deliberate_break, "_run", lambda *_args: completed)
    monkeypatch.setattr(
        deliberate_break,
        "_ensure_pytest_runtime_deps",
        lambda: pytest.fail("dependency repair should not run"),
    )

    assert deliberate_break._run_with_runtime_deps(("custom-check",), tmp_path) is completed


def test_runtime_dependencies_retry_pyyaml_import_failure(tmp_path, monkeypatch) -> None:
    attempts = [
        subprocess.CompletedProcess(
            ["pytest"],
            1,
            "",
            "ModuleNotFoundError: No module named 'yaml'",
        ),
        subprocess.CompletedProcess(["pytest"], 0, "passed", ""),
    ]
    repairs: list[bool] = []
    monkeypatch.setattr(deliberate_break, "_run", lambda *_args: attempts.pop(0))
    monkeypatch.setattr(
        deliberate_break,
        "_pyyaml_runtime_needs_repair",
        lambda: False,
    )
    monkeypatch.setattr(deliberate_break, "_pyyaml_probe_succeeds", lambda *_args: True)
    monkeypatch.setattr(
        deliberate_break,
        "_ensure_pytest_runtime_deps",
        lambda: repairs.append(True),
    )

    completed = deliberate_break._run_with_runtime_deps((sys.executable, "-m", "pytest"), tmp_path)

    assert completed.returncode == 0
    assert repairs == [True]
    assert attempts == []


def test_runtime_dependencies_retry_broken_pyyaml_traceback(tmp_path, monkeypatch) -> None:
    attempts = [
        subprocess.CompletedProcess(
            ["pytest"],
            1,
            "",
            'File "/venv/lib/site-packages/yaml/__init__.py", line 1\nSyntaxError: invalid syntax',
        ),
        subprocess.CompletedProcess(["pytest"], 0, "passed", ""),
    ]
    repairs: list[bool] = []
    monkeypatch.setattr(deliberate_break, "_run", lambda *_args: attempts.pop(0))
    monkeypatch.setattr(
        deliberate_break,
        "_pyyaml_runtime_needs_repair",
        lambda: True,
    )
    monkeypatch.setattr(deliberate_break, "_pyyaml_probe_succeeds", lambda *_args: True)
    monkeypatch.setattr(
        deliberate_break,
        "import_module",
        lambda _name: (_ for _ in ()).throw(SyntaxError("broken wheel")),
    )
    monkeypatch.setattr(
        deliberate_break,
        "_ensure_pytest_runtime_deps",
        lambda: repairs.append(True),
    )

    completed = deliberate_break._run_with_runtime_deps((sys.executable, "-m", "pytest"), tmp_path)

    assert completed.returncode == 0
    assert repairs == [True]
    assert attempts == []


def test_runtime_dependencies_do_not_preflight_pyyaml_for_successful_pytest(
    tmp_path, monkeypatch
) -> None:
    events: list[str] = []
    completed = subprocess.CompletedProcess(["pytest"], 0, "passed", "")
    monkeypatch.setattr(
        deliberate_break,
        "_run",
        lambda *_args: events.append("run") or completed,
    )
    monkeypatch.setattr(deliberate_break.metadata, "version", lambda _name: "0.0.0")
    monkeypatch.setattr(deliberate_break, "_pyyaml_probe_succeeds", lambda *_args: True)
    monkeypatch.setattr(
        deliberate_break,
        "_ensure_pytest_runtime_deps",
        lambda: events.append("repair"),
    )

    result = deliberate_break._run_with_runtime_deps((sys.executable, "-m", "pytest"), tmp_path)

    assert result is completed
    assert events == ["run"]


def test_managed_runtime_rejects_unrepairable_command_import_context(tmp_path, monkeypatch) -> None:
    repairs: list[bool] = []
    completed = subprocess.CompletedProcess(
        ["pytest"],
        1,
        "",
        "ModuleNotFoundError: No module named 'yaml'",
    )
    monkeypatch.setattr(deliberate_break, "_run", lambda *_args: completed)
    monkeypatch.setattr(deliberate_break, "_pyyaml_runtime_needs_repair", lambda: False)
    monkeypatch.setattr(deliberate_break, "_pyyaml_probe_succeeds", lambda *_args: False)
    monkeypatch.setattr(
        deliberate_break,
        "_ensure_pytest_runtime_deps",
        lambda: repairs.append(True),
    )

    with pytest.raises(deliberate_break.RuntimeDependencyError) as caught:
        deliberate_break._run_with_runtime_deps(
            (sys.executable, "-m", "pytest"),
            tmp_path,
        )

    assert repairs == [True]
    assert "managed pytest command environment" in str(caught.value.error)


def test_import_context_changed_active_python_is_not_repaired(tmp_path, monkeypatch) -> None:
    command = (sys.executable, "-s", "-m", "pytest")
    completed = subprocess.CompletedProcess(
        command,
        1,
        "",
        "ModuleNotFoundError: No module named 'yaml'",
    )
    monkeypatch.setattr(deliberate_break, "_run", lambda *_args: completed)
    monkeypatch.setattr(
        deliberate_break,
        "_ensure_pytest_runtime_deps",
        lambda: pytest.fail("flagged import context must not mutate the active environment"),
    )

    with pytest.raises(deliberate_break.RuntimeDependencyError) as caught:
        deliberate_break._run_with_runtime_deps(command, tmp_path)

    assert isinstance(caught.value.error, ImportError)
    assert "wrapped or custom" in str(caught.value.error)


@pytest.mark.parametrize(
    "command",
    [
        ("uv", "run", "pytest"),
        ("/other/venv/bin/python", "-m", "pytest"),
    ],
)
@pytest.mark.parametrize(
    "stderr",
    [
        "ModuleNotFoundError: No module named 'yaml'",
        "ERROR collecting tests/test_manifest.py\n"
        'File "/other/venv/lib/site-packages/yaml/__init__.py", line 1\n'
        "SyntaxError: broken wheel",
        "ERROR collecting tests/test_manifest.py\n"
        'File "/other/venv/lib/site-packages/yaml/__init__.py", line 1\n'
        "E   SyntaxError: broken wheel",
    ],
)
def test_runtime_dependencies_do_not_repair_unmanaged_command_environment(
    tmp_path, monkeypatch, command, stderr
) -> None:
    completed = subprocess.CompletedProcess(
        command,
        1,
        "",
        stderr,
    )
    attempts = [completed]
    if "No module named" not in stderr:
        attempts.append(subprocess.CompletedProcess(["probe"], 1, "", "broken import"))
    monkeypatch.setattr(
        deliberate_break,
        "_run",
        lambda *_args: attempts.pop(0),
    )
    monkeypatch.setattr(
        deliberate_break,
        "_pyyaml_probe_command",
        lambda _command, _cwd: ("probe",),
    )
    monkeypatch.setattr(
        deliberate_break,
        "_ensure_pytest_runtime_deps",
        lambda: pytest.fail("wrapper-owned environment must not be mutated"),
    )

    with pytest.raises(deliberate_break.RuntimeDependencyError) as caught:
        deliberate_break._run_with_runtime_deps(command, tmp_path)

    assert isinstance(caught.value.error, ImportError)
    assert "wrapped or custom" in str(caught.value.error)
    assert attempts == []


def test_unmanaged_yaml_test_failure_is_not_misclassified_as_dependency_error(
    tmp_path, monkeypatch
) -> None:
    completed = subprocess.CompletedProcess(
        ["uv", "run", "pytest"],
        1,
        "",
        'File "/other/venv/lib/site-packages/yaml/parser.py", line 98\n'
        "yaml.parser.ParserError: malformed fixture",
    )
    attempts = [
        completed,
        subprocess.CompletedProcess(["probe"], 0, deliberate_break.PYYAML_PROBE_SENTINEL, ""),
    ]
    monkeypatch.setattr(deliberate_break, "_run", lambda *_args: attempts.pop(0))
    monkeypatch.setattr(
        deliberate_break,
        "_pyyaml_probe_command",
        lambda _command, _cwd: ("probe",),
    )

    result = deliberate_break._run_with_runtime_deps(("uv", "run", "pytest"), tmp_path)

    assert result is completed
    assert attempts == []


def test_unmanaged_yaml_attribute_error_is_not_misclassified_as_import_failure(
    tmp_path, monkeypatch
) -> None:
    completed = subprocess.CompletedProcess(
        ["uv", "run", "pytest"],
        1,
        "",
        'File "/other/venv/lib/site-packages/yaml/__init__.py", line 125, in safe_load\n'
        "E   AttributeError: 'NoneType' object has no attribute 'read'",
    )
    attempts = [
        completed,
        subprocess.CompletedProcess(["probe"], 0, deliberate_break.PYYAML_PROBE_SENTINEL, ""),
    ]
    monkeypatch.setattr(deliberate_break, "_run", lambda *_args: attempts.pop(0))
    monkeypatch.setattr(
        deliberate_break,
        "_pyyaml_probe_command",
        lambda _command, _cwd: ("probe",),
    )

    result = deliberate_break._run_with_runtime_deps(("uv", "run", "pytest"), tmp_path)

    assert result is completed
    assert attempts == []


def test_interactive_probe_traceback_is_dependency_failure_despite_zero_exit(
    tmp_path, monkeypatch
) -> None:
    command = ("uv", "run", "python", "-im", "pytest")
    attempts = [
        subprocess.CompletedProcess(
            command,
            1,
            "",
            'File "/venv/lib/site-packages/yaml/__init__.py", line 1\n' "SyntaxError: broken wheel",
        ),
        subprocess.CompletedProcess(
            ["probe"],
            0,
            "",
            "Traceback (most recent call last):\nSyntaxError: broken wheel\n>>> ",
        ),
    ]
    monkeypatch.setattr(deliberate_break, "_run", lambda *_args: attempts.pop(0))
    monkeypatch.setattr(
        deliberate_break,
        "_pyyaml_probe_command",
        lambda _command, _cwd: ("probe",),
    )

    with pytest.raises(deliberate_break.RuntimeDependencyError):
        deliberate_break._run_with_runtime_deps(command, tmp_path)

    assert attempts == []


def test_probe_sentinel_ignores_unrelated_startup_traceback(tmp_path, monkeypatch) -> None:
    command = ("uv", "run", "python", "-im", "pytest")
    completed = subprocess.CompletedProcess(
        command,
        1,
        "",
        'File "/venv/lib/site-packages/yaml/parser.py", line 98\n'
        "yaml.parser.ParserError: malformed fixture",
    )
    attempts = [
        completed,
        subprocess.CompletedProcess(
            ["probe"],
            0,
            deliberate_break.PYYAML_PROBE_SENTINEL,
            "Traceback from unrelated .pth startup error",
        ),
    ]
    monkeypatch.setattr(deliberate_break, "_run", lambda *_args: attempts.pop(0))
    monkeypatch.setattr(
        deliberate_break,
        "_pyyaml_probe_command",
        lambda _command, _cwd: ("probe",),
    )

    result = deliberate_break._run_with_runtime_deps(command, tmp_path)

    assert result is completed
    assert attempts == []


def test_uv_pyyaml_probe_uses_resolved_pytest_shebang_interpreter(tmp_path, monkeypatch) -> None:
    pytest_launcher = tmp_path / "global" / "bin" / "pytest"
    pytest_launcher.parent.mkdir(parents=True)
    pytest_launcher.write_text("#!/global/python\n", encoding="utf-8")
    monkeypatch.setattr(
        deliberate_break,
        "_run",
        lambda *_args: subprocess.CompletedProcess(
            ["uv", "run", "which", "pytest"],
            0,
            f"{pytest_launcher}\n",
            "",
        ),
    )

    assert deliberate_break._pyyaml_probe_command(("uv", "run", "pytest"), tmp_path) == (
        "/global/python",
        "-c",
        deliberate_break.PYYAML_PROBE_CODE,
    )


def test_uv_pyyaml_probe_preserves_uv_run_options(tmp_path, monkeypatch) -> None:
    pytest_launcher = tmp_path / "bin" / "pytest"
    pytest_launcher.parent.mkdir()
    pytest_launcher.write_text("#!/project/.venv/bin/python\n", encoding="utf-8")
    calls: list[tuple[str, ...]] = []

    def run(command, _cwd):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, f"{pytest_launcher}\n", "")

    monkeypatch.setattr(deliberate_break, "_run", run)
    command = (
        "uv",
        "run",
        "--frozen",
        "--group",
        "test",
        "-w",
        "pytest-xdist",
        "-p",
        "3.13",
        "--config-file",
        "uv.toml",
        "--isolated",
        "pytest",
        "-q",
    )

    assert deliberate_break._pyyaml_probe_command(command, tmp_path) == (
        "/project/.venv/bin/python",
        "-c",
        deliberate_break.PYYAML_PROBE_CODE,
    )
    assert calls == [
        (
            "uv",
            "run",
            "--frozen",
            "--group",
            "test",
            "-w",
            "pytest-xdist",
            "-p",
            "3.13",
            "--config-file",
            "uv.toml",
            "--isolated",
            "which",
            "pytest",
        )
    ]


def test_uv_pyyaml_probe_preserves_python_shebang_flags(tmp_path, monkeypatch) -> None:
    pytest_launcher = tmp_path / "global" / "bin" / "pytest"
    pytest_launcher.parent.mkdir(parents=True)
    pytest_launcher.write_text("#!/usr/bin/python3 -I\n", encoding="utf-8")
    monkeypatch.setattr(
        deliberate_break,
        "_run",
        lambda *_args: subprocess.CompletedProcess(
            ["uv", "run", "which", "pytest"],
            0,
            f"{pytest_launcher}\n",
            "",
        ),
    )

    assert deliberate_break._pyyaml_probe_command(("uv", "run", "pytest"), tmp_path) == (
        "/usr/bin/python3",
        "-I",
        "-c",
        deliberate_break.PYYAML_PROBE_CODE,
    )


def test_uv_pyyaml_probe_omits_interactive_python_shebang_flag(tmp_path, monkeypatch) -> None:
    pytest_launcher = tmp_path / "global" / "bin" / "pytest"
    pytest_launcher.parent.mkdir(parents=True)
    pytest_launcher.write_text("#!/usr/bin/python3 -i\n", encoding="utf-8")
    monkeypatch.setattr(
        deliberate_break,
        "_run",
        lambda *_args: subprocess.CompletedProcess(
            ["uv", "run", "which", "pytest"],
            0,
            f"{pytest_launcher}\n",
            "",
        ),
    )

    assert deliberate_break._pyyaml_probe_command(("uv", "run", "pytest"), tmp_path) == (
        "/usr/bin/python3",
        "-c",
        deliberate_break.PYYAML_PROBE_CODE,
    )


def test_uv_pyyaml_probe_resolves_env_shebang_inside_uv_path(tmp_path, monkeypatch) -> None:
    pytest_launcher = tmp_path / "bin" / "pytest"
    pytest_launcher.parent.mkdir()
    pytest_launcher.write_text("#!/usr/bin/env -S python3 -I\n", encoding="utf-8")
    results = iter(
        (
            subprocess.CompletedProcess(["which", "pytest"], 0, f"{pytest_launcher}\n", ""),
            subprocess.CompletedProcess(
                ["which", "python3"], 0, "/project/.venv/bin/python3\n", ""
            ),
        )
    )
    monkeypatch.setattr(deliberate_break, "_run", lambda *_args: next(results))

    assert deliberate_break._pyyaml_probe_command(("uv", "run", "pytest"), tmp_path) == (
        "/project/.venv/bin/python3",
        "-I",
        "-c",
        deliberate_break.PYYAML_PROBE_CODE,
    )


def test_uv_pyyaml_probe_rejects_shell_shim_launcher(tmp_path, monkeypatch) -> None:
    pytest_launcher = tmp_path / "bin" / "pytest"
    pytest_launcher.parent.mkdir()
    pytest_launcher.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    calls: list[tuple[str, ...]] = []

    def run(command, _cwd):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, f"{pytest_launcher}\n", "")

    monkeypatch.setattr(deliberate_break, "_run", run)

    assert deliberate_break._pyyaml_probe_command(("uv", "run", "pytest"), tmp_path) is None
    assert calls == [("uv", "run", "which", "pytest")]


def test_bare_pytest_probe_uses_launcher_shebang(tmp_path, monkeypatch) -> None:
    pytest_launcher = tmp_path / "bin" / "pytest"
    pytest_launcher.parent.mkdir()
    pytest_launcher.write_text("#!/usr/bin/env -S python3 -I\n", encoding="utf-8")

    def which(name):
        return str(pytest_launcher) if name == "pytest" else "/venv/bin/python3"

    monkeypatch.setattr(deliberate_break.shutil, "which", which)

    assert deliberate_break._pyyaml_probe_command(("pytest", "-q"), tmp_path) == (
        "/venv/bin/python3",
        "-I",
        "-c",
        deliberate_break.PYYAML_PROBE_CODE,
    )


def test_python_module_probe_preserves_interpreter_flags(tmp_path) -> None:
    assert deliberate_break._pyyaml_probe_command(
        ("/venv/bin/python", "-I", "-m", "pytest", "-q"),
        tmp_path,
    ) == ("/venv/bin/python", "-I", "-c", deliberate_break.PYYAML_PROBE_CODE)


def test_active_python_with_flags_is_managed_pytest_runtime() -> None:
    assert deliberate_break._uses_pytest_runtime(
        (sys.executable, "-X", "dev", "-O", "-m", "pytest", "-q")
    )


def test_plain_pytest_with_active_python_shebang_is_managed(tmp_path, monkeypatch) -> None:
    pytest_launcher = tmp_path / "pytest"
    pytest_launcher.write_text(f"#!{sys.executable}\n", encoding="utf-8")
    monkeypatch.setattr(
        deliberate_break.shutil,
        "which",
        lambda name: str(pytest_launcher) if name == "pytest" else None,
    )

    assert deliberate_break._uses_pytest_runtime(("pytest", "-q"))


def test_plain_pytest_with_interactive_shebang_is_managed(tmp_path, monkeypatch) -> None:
    pytest_launcher = tmp_path / "pytest"
    pytest_launcher.write_text(f"#!{sys.executable} -i\n", encoding="utf-8")
    monkeypatch.setattr(
        deliberate_break.shutil,
        "which",
        lambda name: str(pytest_launcher) if name == "pytest" else None,
    )

    assert deliberate_break._uses_pytest_runtime(("pytest", "-q"))
    assert deliberate_break._pyyaml_probe_command(("pytest", "-q"), tmp_path) == (
        sys.executable,
        "-c",
        deliberate_break.PYYAML_PROBE_CODE,
    )


def test_plain_pytest_with_changed_import_context_is_not_managed(tmp_path, monkeypatch) -> None:
    pytest_launcher = tmp_path / "pytest"
    pytest_launcher.write_text(f"#!{sys.executable} -I\n", encoding="utf-8")
    monkeypatch.setattr(
        deliberate_break.shutil,
        "which",
        lambda name: str(pytest_launcher) if name == "pytest" else None,
    )

    assert not deliberate_break._uses_pytest_runtime(("pytest", "-q"))


def test_active_python_with_hash_policy_is_managed_pytest_runtime() -> None:
    assert deliberate_break._uses_pytest_runtime(
        (
            sys.executable,
            "--check-hash-based-pycs",
            "default",
            "-m",
            "pytest",
        )
    )


def test_invalid_hash_policy_is_not_managed_pytest_runtime() -> None:
    assert not deliberate_break._uses_pytest_runtime(
        (
            sys.executable,
            "--check-hash-based-pycs",
            "bogus",
            "-m",
            "pytest",
        )
    )


def test_unsupported_lowercase_r_is_not_managed_pytest_runtime() -> None:
    assert not deliberate_break._uses_pytest_runtime((sys.executable, "-r", "-m", "pytest"))


@pytest.mark.parametrize(
    "options",
    [
        ("-S", "-m", "pytest"),
        ("-OSm", "pytest"),
        ("-OSmpytest",),
    ],
)
def test_site_disabled_python_is_not_managed_pytest_runtime(options) -> None:
    assert not deliberate_break._uses_pytest_runtime((sys.executable, *options))


@pytest.mark.parametrize("context_flag", ["-E", "-I", "-P", "-s"])
def test_import_context_changed_python_is_not_managed_pytest_runtime(context_flag) -> None:
    assert not deliberate_break._uses_pytest_runtime((sys.executable, context_flag, "-m", "pytest"))


@pytest.mark.parametrize(
    "compact_option",
    ["-Empytest", "-Impytest", "-Pmpytest", "-smpytest"],
)
def test_compact_import_context_changed_python_is_not_managed(compact_option) -> None:
    assert not deliberate_break._uses_pytest_runtime((sys.executable, compact_option))


def test_empty_command_is_not_managed_pytest_runtime() -> None:
    assert not deliberate_break._uses_pytest_runtime(())


@pytest.mark.parametrize(
    ("compact_option", "preserved"),
    [
        ("-im", ()),  # lowercase -i must not reach the import probe
        ("-OOm", ("-OO",)),
        ("-tm", ("-t",)),
        ("-Oim", ("-O",)),
    ],
)
def test_active_python_with_compact_flags_is_managed_pytest_runtime(
    compact_option, preserved
) -> None:
    command = (sys.executable, compact_option, "pytest", "-q")

    assert deliberate_break._uses_pytest_runtime(command)
    assert deliberate_break._pyyaml_probe_command(command, Path.cwd()) == (
        sys.executable,
        *preserved,
        "-c",
        deliberate_break.PYYAML_PROBE_CODE,
    )


def test_active_python_separate_interactive_flag_omitted_from_probe() -> None:
    command = (sys.executable, "-i", "-m", "pytest", "-q")

    assert deliberate_break._uses_pytest_runtime(command)
    assert deliberate_break._pyyaml_probe_command(command, Path.cwd()) == (
        sys.executable,
        "-c",
        deliberate_break.PYYAML_PROBE_CODE,
    )


@pytest.mark.parametrize(
    ("compact_option", "preserved"),
    [("-mpytest", ()), ("-Ompytest", ("-O",)), ("-impytest", ())],
)
def test_active_python_with_attached_pytest_module_is_managed_runtime(
    compact_option, preserved
) -> None:
    command = (sys.executable, compact_option, "-q")

    assert deliberate_break._uses_pytest_runtime(command)
    assert deliberate_break._pyyaml_probe_command(command, Path.cwd()) == (
        sys.executable,
        *preserved,
        "-c",
        deliberate_break.PYYAML_PROBE_CODE,
    )


@pytest.mark.parametrize(
    "options",
    [
        ("-OW", "ignore"),
        ("-OX", "dev"),
        ("-OWignore",),
        ("-OXdev",),
    ],
)
def test_active_python_with_compact_value_option_is_managed_runtime(options) -> None:
    command = (sys.executable, *options, "-m", "pytest", "-q")

    assert deliberate_break._uses_pytest_runtime(command)
    assert deliberate_break._pyyaml_probe_command(command, Path.cwd()) == (
        sys.executable,
        *options,
        "-c",
        deliberate_break.PYYAML_PROBE_CODE,
    )


@pytest.mark.parametrize(
    ("interactive_option", "preserved"),
    [
        ("-iWerror", "-Werror"),
        ("-iXdev", "-Xdev"),
        ("-OiWerror", "-OWerror"),
        ("-OiXdev", "-OXdev"),
    ],
)
def test_compact_interactive_value_option_is_removed_from_probe(
    interactive_option, preserved
) -> None:
    command = (sys.executable, interactive_option, "-m", "pytest")

    assert deliberate_break._uses_pytest_runtime(command)
    assert deliberate_break._pyyaml_probe_command(command, Path.cwd()) == (
        sys.executable,
        preserved,
        "-c",
        deliberate_break.PYYAML_PROBE_CODE,
    )


@pytest.mark.parametrize(
    "terminator",
    [
        "--",
        "-",
        "-V",
        "-VV",
        "--version",
        "-h",
        "--help",
        "-cprint(1)",
        "-mthis",
        "-Icprint(1)",
        "-Imthis",
        "-IV",
        "-Ih",
        "-I?",
        "--bogus",
    ],
)
def test_python_terminator_prevents_managed_pytest_classification(terminator) -> None:
    assert not deliberate_break._uses_pytest_runtime((sys.executable, terminator, "-m", "pytest"))


def test_active_python_script_with_pytest_arguments_is_not_managed_runtime() -> None:
    assert not deliberate_break._uses_pytest_runtime(
        (sys.executable, "scripts/run_tests.py", "-m", "pytest")
    )


@pytest.mark.parametrize("module_option", ["-m", "--module"])
def test_uv_module_pytest_probe_uses_uv_selected_python(tmp_path, module_option) -> None:
    assert deliberate_break._pyyaml_probe_command(
        ("uv", "run", "--frozen", module_option, "pytest", "-q"),
        tmp_path,
    ) == (
        "uv",
        "run",
        "--frozen",
        "python",
        "-c",
        deliberate_break.PYYAML_PROBE_CODE,
    )


def test_uv_nested_python_module_probe_preserves_uv_and_python_options(tmp_path) -> None:
    assert deliberate_break._pyyaml_probe_command(
        (
            "uv",
            "run",
            "--no-project",
            "--python",
            "3.13",
            "python",
            "-I",
            "-m",
            "pytest",
            "-q",
        ),
        tmp_path,
    ) == (
        "uv",
        "run",
        "--no-project",
        "--python",
        "3.13",
        "python",
        "-I",
        "-c",
        deliberate_break.PYYAML_PROBE_CODE,
    )


@pytest.mark.parametrize(
    ("compact_option", "preserved"),
    [("-mpytest", ()), ("-Impytest", ("-I",))],
)
def test_minimal_uv_nested_attached_pytest_module_probe(
    tmp_path, compact_option, preserved
) -> None:
    assert deliberate_break._pyyaml_probe_command(
        ("uv", "run", "python", compact_option),
        tmp_path,
    ) == (
        "uv",
        "run",
        "python",
        *preserved,
        "-c",
        deliberate_break.PYYAML_PROBE_CODE,
    )


@pytest.mark.parametrize(
    "command",
    [
        ("uv", "run", "python", "scripts/run_tests.py", "-m", "pytest"),
        ("uv", "run", "python", "-c", "run_tests()", "-m", "pytest"),
        ("python", "scripts/run_tests.py", "-m", "pytest"),
    ],
)
def test_python_probe_stops_after_first_program_selector(tmp_path, command) -> None:
    assert deliberate_break._pyyaml_probe_command(command, tmp_path) is None


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

    monkeypatch.setattr(
        deliberate_break,
        "_run_with_runtime_deps",
        lambda *_args: (_ for _ in ()).throw(
            deliberate_break.RuntimeDependencyError(subprocess.TimeoutExpired(command, 17))
        ),
    )

    result = verify_spec(spec, base=base, cwd=repo, enforce_tamper=False)

    assert result == {
        "verdict": VERDICT_BROKEN,
        "reason": "dependency-install-timeout",
        "command": command,
        "timeout": 17,
    }


def test_dependency_install_failure_preserves_subprocess_context(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    base, spec = _sound_spec(repo)
    error = subprocess.CalledProcessError(
        17,
        ["pip", "install", "pyyaml==6.0.3"],
        output="resolver output",
        stderr="pip denied",
    )

    monkeypatch.setattr(
        deliberate_break,
        "_run_with_runtime_deps",
        lambda *_args: (_ for _ in ()).throw(deliberate_break.RuntimeDependencyError(error)),
    )

    result = verify_spec(spec, base=base, cwd=repo, enforce_tamper=False)

    assert result == {
        "verdict": VERDICT_BROKEN,
        "reason": "dependency-install-failed",
        "command": ["pip", "install", "pyyaml==6.0.3"],
        "returncode": 17,
        "stdout": "resolver output",
        "stderr": "pip denied",
    }


def test_dependency_install_failure_normalizes_byte_output(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    base, spec = _sound_spec(repo)
    error = subprocess.CalledProcessError(
        17,
        ["pip", "install", "pyyaml==6.0.3"],
        output=b"resolver \xff output",
        stderr=b"pip denied",
    )

    monkeypatch.setattr(
        deliberate_break,
        "_run_with_runtime_deps",
        lambda *_args: (_ for _ in ()).throw(deliberate_break.RuntimeDependencyError(error)),
    )

    result = verify_spec(spec, base=base, cwd=repo, enforce_tamper=False)

    assert result == {
        "verdict": VERDICT_BROKEN,
        "reason": "dependency-install-failed",
        "command": ["pip", "install", "pyyaml==6.0.3"],
        "returncode": 17,
        "stdout": "resolver \ufffd output",
        "stderr": "pip denied",
    }
    json.dumps(result)


def test_dependency_install_unavailable_is_broken(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    base, spec = _sound_spec(repo)

    monkeypatch.setattr(
        deliberate_break,
        "_run_with_runtime_deps",
        lambda *_args: (_ for _ in ()).throw(
            deliberate_break.RuntimeDependencyError(OSError("pip unavailable"))
        ),
    )

    result = verify_spec(spec, base=base, cwd=repo, enforce_tamper=False)

    assert result == {
        "verdict": VERDICT_BROKEN,
        "reason": "dependency-install-unavailable",
        "detail": "pip unavailable",
    }


def test_dependency_import_failure_is_broken(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    base, spec = _sound_spec(repo)
    original = OSError("original import failed")

    def failed() -> None:
        try:
            raise ImportError("retry failed") from original
        except ImportError as exc:
            raise deliberate_break.RuntimeDependencyError(exc) from exc

    monkeypatch.setattr(
        deliberate_break,
        "_run_with_runtime_deps",
        lambda *_args: failed(),
    )

    result = verify_spec(spec, base=base, cwd=repo, enforce_tamper=False)

    assert result == {
        "verdict": VERDICT_BROKEN,
        "reason": "dependency-import-failed",
        "detail": "retry failed",
        "cause": "original import failed",
    }


def test_base_archive_command_failure_is_not_dependency_failure(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    base, spec = _sound_spec(repo)
    error = subprocess.CalledProcessError(
        17,
        ["git", "archive", base],
        output=b"archive output",
        stderr=b"bad ref",
    )
    monkeypatch.setattr(
        deliberate_break,
        "_archive_ref",
        lambda *_args: (_ for _ in ()).throw(error),
    )

    result = verify_spec(spec, base=base, cwd=repo, enforce_tamper=False)

    assert result == {
        "verdict": VERDICT_BROKEN,
        "reason": "archive-command-failed",
        "command": ["git", "archive", base],
        "returncode": 17,
        "stdout": "archive output",
        "stderr": "bad ref",
    }
    json.dumps(result)


def test_base_setup_failure_is_not_dependency_failure(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    base, spec = _sound_spec(repo)
    monkeypatch.setattr(
        deliberate_break,
        "_archive_ref",
        lambda *_args: (_ for _ in ()).throw(OSError("disk unavailable")),
    )

    result = verify_spec(spec, base=base, cwd=repo, enforce_tamper=False)

    assert result == {
        "verdict": VERDICT_BROKEN,
        "reason": "base-setup-failed",
        "detail": "disk unavailable",
    }


def test_base_command_launch_failure_is_reported_as_command_unavailable(
    tmp_path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    base, spec = _sound_spec(repo)
    calls = 0

    def run_command(*_args):
        nonlocal calls
        calls += 1
        if calls == 1:
            return subprocess.CompletedProcess(spec.command, 0, "", "")
        error = FileNotFoundError("base-only command is unavailable")
        raise deliberate_break.CommandUnavailableError(error) from error

    monkeypatch.setattr(deliberate_break, "_run_with_runtime_deps", run_command)

    result = verify_spec(spec, base=base, cwd=repo, enforce_tamper=False)

    assert result == {
        "verdict": VERDICT_BROKEN,
        "reason": "command-unavailable",
        "command": list(spec.command),
        "detail": "base-only command is unavailable",
    }
