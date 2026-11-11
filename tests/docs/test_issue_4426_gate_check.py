"""Lock the recorded Gate command and the thin acceptance path."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/issue-4426/gate-check.md"
GATE = ROOT / ".github/workflows/pr-00-gate.yml"
REUSABLE = ROOT / ".github/workflows/reusable-10-ci-python.yml"
PYPROJECT = ROOT / "pyproject.toml"


def _present(haystack: str, expected: tuple[str, ...]) -> tuple[str, ...]:
    """Return expected needles that actually occur in haystack, in order."""
    return tuple(needle for needle in expected if needle in haystack)


def test_gate_workflow_matches_recorded_coverage_command() -> None:
    evidence = EVIDENCE.read_text(encoding="utf-8")
    gate = GATE.read_text(encoding="utf-8")
    reusable = REUSABLE.read_text(encoding="utf-8")
    project = PYPROJECT.read_text(encoding="utf-8")

    gate_expected = (
        "uses: ./.github/workflows/reusable-10-ci-python.yml",
        "coverage-python-version: '3.14'",
        'python-versions: \'["3.13", "3.14"]\'',
        "pytest-workers: '4'",
        'marker: "not quarantine and not slow"',
        # Since Workflows#3904 the coverage call ignores the three verifier grammar
        # suites, which python-ci-grammar runs without coverage.
        'pytest_args: "-n auto --dist load --ignore=tests/scripts/test_pr_verifier_',
        "coverage-min: '70'",
        "artifact-prefix: 'gate-'",
    )
    reusable_expected = (
        'pytest -p ci_test_growth "${args[@]}"',
        'args+=("--cov-config=pyproject.toml")',
        'args+=("--cov-report=term-missing")',
        'args+=("--cov-report=json:coverage.json")',
        'args+=("-n" "${PYTEST_WORKERS}" "--dist=loadgroup")',
    )
    project_expected = (
        "branch = true",
        'source = ["scripts", "tools", "src"]',
    )
    evidence_expected = (
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
    )

    assert _present(gate, gate_expected) == (
        "uses: ./.github/workflows/reusable-10-ci-python.yml",
        "coverage-python-version: '3.14'",
        'python-versions: \'["3.13", "3.14"]\'',
        "pytest-workers: '4'",
        'marker: "not quarantine and not slow"',
        'pytest_args: "-n auto --dist load --ignore=tests/scripts/test_pr_verifier_',
        "coverage-min: '70'",
        "artifact-prefix: 'gate-'",
    )
    assert _present(reusable, reusable_expected) == (
        'pytest -p ci_test_growth "${args[@]}"',
        'args+=("--cov-config=pyproject.toml")',
        'args+=("--cov-report=term-missing")',
        'args+=("--cov-report=json:coverage.json")',
        'args+=("-n" "${PYTEST_WORKERS}" "--dist=loadgroup")',
    )
    assert _present(project, project_expected) == (
        "branch = true",
        'source = ["scripts", "tools", "src"]',
    )
    assert _present(evidence, evidence_expected) == (
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
    )


def test_documented_observer_extracts_generated_workflow_hooks(tmp_path, monkeypatch, capsys):
    import ast

    import yaml

    evidence = EVIDENCE.read_text()
    command = evidence.split(
        "growth_plugin_dir=\"$(/opt/anaconda3/bin/python3 - <<'PYOBSERVER'\n", 1
    )[1].split("\nPYOBSERVER", 1)[0]
    workflow_path = tmp_path / ".github/workflows/reusable-10-ci-python.yml"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_bytes(REUSABLE.read_bytes())
    monkeypatch.chdir(tmp_path)
    exec(compile(command, "<documented-observer>", "exec"), {})
    generated = Path(capsys.readouterr().out.strip()) / "ci_test_growth.py"
    observer = generated.read_text()
    ast.parse(observer)
    assert "def pytest_collection_finish" in observer
    assert "def pytest_sessionfinish" in observer
    workflow = yaml.safe_load(REUSABLE.read_text())
    step = next(
        step
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if 'cat > "${growth_plugin_dir}/ci_test_growth.py"' in step.get("run", "")
    )
    assert observer.rstrip() in step["run"]
