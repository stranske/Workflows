"""Exercise the delivered integration validator through its documented CLI."""

import subprocess
import sys
from pathlib import Path

import pytest
from tools.integration_repo import render_integration_repo


def run_validator(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/validate_dependency_test_setup.py"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def rendered_repo(tmp_path: Path) -> Path:
    repo = render_integration_repo(tmp_path / "integration")
    (repo / "tests/test_regression.py").write_text(
        "assert confidence == 0.4\nassert offenders == ['python-version: \"3.12\"']\n",
        encoding="utf-8",
    )
    return repo


def test_unlocked_fixture_ignores_confidence_and_ci_axis_values(rendered_repo: Path) -> None:
    result = run_validator(rendered_repo)
    assert result.returncode == 0, result.stdout
    assert "Skipping lock checks for the unlocked integration fixture" in result.stdout


@pytest.mark.parametrize(
    "assertion",
    [
        'import pytest\nassert pytest.__version__ == "9.2.0"\n',
        'from importlib.metadata import version as installed\nassert "9.2.0" == installed("pytest")\n',
    ],
)
def test_direct_version_assertions_fail(rendered_repo: Path, assertion: str) -> None:
    (rendered_repo / "tests/test_regression.py").write_text(assertion, encoding="utf-8")
    result = run_validator(rendered_repo)
    assert result.returncode == 1
    assert "tests/test_regression.py:2: hardcoded dependency version" in result.stdout


@pytest.mark.parametrize(
    ("extras", "pin", "diagnostic"),
    [
        ("--all-extras", "pytest==9.2.0", ""),
        ("--extra app --extra dev --extra=test", "pytest==9.2.0", ""),
        ("--extra app --extra dev", "pytest==9.2.0", "header is missing --extra test"),
        ("--all-extras", "", "has no pin for pytest"),
        ("--all-extras", "pytest==7.3.0", "incompatible with pytest>=7.4"),
    ],
)
def test_lock_covers_declared_extras_and_constraints(
    rendered_repo: Path, extras: str, pin: str, diagnostic: str
) -> None:
    (rendered_repo / "requirements.lock").write_text(
        f"#    uv pip compile pyproject.toml {extras} --universal\n{pin}\n",
        encoding="utf-8",
    )
    result = run_validator(rendered_repo)
    assert result.returncode == (1 if diagnostic else 0), result.stdout
    if diagnostic:
        assert diagnostic in result.stdout


def test_existing_receiver_needs_its_lock(rendered_repo: Path) -> None:
    (rendered_repo / ".github/workflows/maint-dependabot-auto-lock.yml").touch()
    result = run_validator(rendered_repo)
    assert result.returncode == 1
    assert "requirements.lock is missing" in result.stdout
