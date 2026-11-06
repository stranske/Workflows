"""Lock the recorded Gate command and the thin acceptance path."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/issue-4426/gate-check.md"
GATE = ROOT / ".github/workflows/pr-00-gate.yml"
REUSABLE = ROOT / ".github/workflows/reusable-10-ci-python.yml"
PYPROJECT = ROOT / "pyproject.toml"


def test_gate_workflow_matches_recorded_coverage_command() -> None:
    evidence = EVIDENCE.read_text(encoding="utf-8")
    gate = GATE.read_text(encoding="utf-8")
    reusable = REUSABLE.read_text(encoding="utf-8")
    project = PYPROJECT.read_text(encoding="utf-8")

    assert "uses: ./.github/workflows/reusable-10-ci-python.yml" in gate
    assert "coverage-python-version: '3.14'" in gate
    assert 'python-versions: \'["3.13", "3.14"]\'' in gate
    assert "pytest-workers: '4'" in gate
    assert 'marker: "not quarantine and not slow"' in gate
    assert 'pytest_args: "-n auto --dist load"' in gate
    assert "coverage-min: '70'" in gate
    assert "artifact-prefix: 'gate-'" in gate

    assert 'pytest -p ci_test_growth "${args[@]}"' in reusable
    assert 'args+=("--cov-config=pyproject.toml")' in reusable
    assert 'args+=("--cov-report=term-missing")' in reusable
    assert 'args+=("--cov-report=json:coverage.json")' in reusable
    assert 'args+=("-n" "${PYTEST_WORKERS}" "--dist=loadgroup")' in reusable

    assert "branch = true" in project
    assert 'source = ["scripts", "tools", "src"]' in project

    for phrase in (
        "`coverage-python-version`: `3.14`",
        "not quarantine and not slow",
        "pytest -p ci_test_growth",
        "--cov-report=json:coverage.json",
        "--dist=loadgroup",
        'source = ["scripts", "tools", "src"]',
        "two failed runs",
        "10 minutes",
        "20 minutes",
        "under two minutes",
        "6 passed in 0.30s",
        "exit 0",
    ):
        assert phrase in evidence
