"""Maint 90 regression runner on real git repositories.

The negative control must come from the named test running and failing on the
unfixed code: a fix that adds its own test still runs that test after the
revert, and a collection error is never evidence.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "maint90_run_regression.py"
TEST_BODY = "from lib import inc\n\n\ndef test_inc():\n    assert inc(1) == 2\n"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _repo_with_fix(tmp_path: Path, base_lib: str, fixed_lib: str) -> tuple[Path, str]:
    """A repo whose fix commit changes lib.py AND adds the regression test."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "maint90@example.invalid")
    _git(repo, "config", "user.name", "maint90")
    (repo / "lib.py").write_text(base_lib)
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    (repo / "lib.py").write_text(fixed_lib)
    (repo / "test_reg.py").write_text(TEST_BODY)
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "fix")
    return repo, _git(repo, "rev-parse", "HEAD")


def _run(tmp_path: Path, repo: Path, fix_sha: str, command: str) -> dict:
    assessment = {
        "ok": True,
        "assessment": {
            "verdict": "PASS",
            "fix": {"kind": "source", "sha": fix_sha},
            "validation": {"repository": "workflows", "command": command},
        },
    }
    (tmp_path / "assessment.json").write_text(json.dumps(assessment))
    (tmp_path / "item.json").write_text("{}")
    # The command runs `python -m pytest`; point `python` at this interpreter.
    shim = tmp_path / "bin"
    shim.mkdir()
    wrapper = shim / "python"
    wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    wrapper.chmod(0o755)
    env = {**os.environ, "PATH": f"{shim}{os.pathsep}{os.environ.get('PATH', '')}"}
    out = tmp_path / "regression.json"
    subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--assessment",
            str(tmp_path / "assessment.json"),
            "--item",
            str(tmp_path / "item.json"),
            "--receiver",
            str(repo),
            "--workflows",
            str(repo),
            "--output",
            str(out),
            "--no-install",
        ],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return json.loads(out.read_text())


@pytest.fixture(autouse=True)
def _needs_git() -> None:
    pytest.importorskip("defusedxml")
    if subprocess.run(["git", "--version"], capture_output=True).returncode != 0:
        pytest.skip("git unavailable")


def test_fix_that_adds_its_test_is_established(tmp_path: Path) -> None:
    repo, fix_sha = _repo_with_fix(
        tmp_path, "def inc(x):\n    return x + 2\n", "def inc(x):\n    return x + 1\n"
    )
    result = _run(tmp_path, repo, fix_sha, "python -m pytest test_reg.py -q -p no:cacheprovider")
    assert result["reason"] == "", result["with_fix"].get("tail")
    assert result["without_fix"]["test_present"] is True
    assert result["with_fix"]["tests"] == {"passed": 1, "failed": 0, "errors": 0, "skipped": 0}
    assert result["without_fix"]["exit_code"] == 1
    assert result["without_fix"]["tests"]["failed"] == 1
    assert result["negative_failed_tests"] == ["test_reg::test_inc"]


def test_collection_error_is_not_a_negative_control(tmp_path: Path) -> None:
    # Without the fix, `inc` does not exist: the test fails to import, never runs.
    repo, fix_sha = _repo_with_fix(tmp_path, "X = 1\n", "def inc(x):\n    return x + 1\n")
    result = _run(
        tmp_path,
        repo,
        fix_sha,
        "python -m pytest test_reg.py -q -p no:cacheprovider --continue-on-collection-errors",
    )
    assert result["without_fix"]["exit_code"] == 1
    assert result["without_fix"]["tests"]["errors"] == 1
    assert result["negative_failed_tests"] == []
    assert result["reason"] == "negative_control_collection_or_setup_error"


def test_test_that_ignores_the_fix_is_rejected(tmp_path: Path) -> None:
    repo, fix_sha = _repo_with_fix(
        tmp_path, "def inc(x):\n    return x + 1\n", "def inc(x):\n    return x + 1\n\n\n# no-op\n"
    )
    result = _run(tmp_path, repo, fix_sha, "python -m pytest test_reg.py -q -p no:cacheprovider")
    assert result["reason"] == "negative_control_passed_without_fix"
