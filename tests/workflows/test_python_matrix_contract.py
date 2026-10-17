"""Keep first-party CI runtimes, workload selection and shared pins aligned."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml
from scripts.reusable_ci_scope import select_python_matrix

ROOT = Path(__file__).resolve().parents[2]
GATES = (
    Path(".github/workflows/pr-00-gate.yml"),
    Path("templates/consumer-repo/.github/workflows/pr-00-gate.yml"),
)
ENV = Path(".github/workflows/ci-python-versions.env")
REUSABLE = Path(".github/workflows/reusable-10-ci-python.yml")
VERSIONS = {"3.13", "3.14"}


def _load(path: Path) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def _pins(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in (ROOT / path).read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )


@pytest.mark.parametrize("path", GATES, ids=str)
def test_gate_matrix_and_workload(path: Path) -> None:
    gate = _load(path)["jobs"]["python-ci"]
    inputs = gate["with"]
    versions = json.loads(inputs["python-versions"])
    assert len(versions) == 2 and set(versions) == VERSIONS, f"{path}: matrix={versions}"
    assert inputs["primary-python-version"] in versions, str(path)
    assert inputs.get("changed-files-json", "[]") == "[]", f"{path}: keep full-suite selection"
    assert inputs["pytest-workers"] == "4", f"{path}: use the same four-way split"
    assert inputs["pytest_markers"] == "${{ needs.detect.outputs.pytest_markers }}", str(path)
    assert "pytest_args" not in inputs, f"{path}: do not narrow the canonical suite"
    assert "strategy" not in gate, f"{path}: let the reusable fan out both versions"


def test_root_and_template_gate_inputs_agree() -> None:
    root = _load(GATES[0])["jobs"]["python-ci"]["with"]
    template = _load(GATES[1])["jobs"]["python-ci"]["with"]
    for key in ("python-versions", "primary-python-version", "pytest-workers", "pytest_markers"):
        assert root[key] == template[key], f"{GATES}: {key} differs"


@pytest.mark.parametrize("changes", [[], ["tests/test_example.py"], ["docs/example.md"]])
@pytest.mark.parametrize("force_full", [False, True])
def test_scope_selection_keeps_both_runtimes(changes: list[str], force_full: bool) -> None:
    for versions in ("[]", '["3.13", "3.14"]'):
        result = select_python_matrix("Gate", versions, "", changes, force_full)
        expected = ["3.13", "3.14"] if force_full or changes != ["docs/example.md"] else []
        assert result.matrix == {
            "include": [{"python-version": version} for version in expected]
        }, f"scripts/reusable_ci_scope.py: {result.matrix}"


def test_reusable_defaults_and_parallel_suite() -> None:
    workflow = _load(REUSABLE)
    triggers = workflow.get("on", workflow.get(True))
    versions = json.loads(triggers["workflow_dispatch"]["inputs"]["python-versions"]["default"])
    assert len(versions) == 2 and set(versions) == VERSIONS, str(REUSABLE)
    tests = workflow["jobs"]["tests"]
    assert tests["strategy"] == {
        "fail-fast": False,
        "matrix": "${{ fromJson(needs.select-scope.outputs.python_matrix) }}",
    }, f"{REUSABLE}: keep runtime jobs parallel"
    step = next(s for s in tests["steps"] if s.get("id") == "pytest")
    assert "if" not in step, f"{REUSABLE}: both versions must execute pytest"
    for key in ("PYTEST_MARKERS", "PYTEST_ARGS", "PYTEST_WORKERS", "COVERAGE_ENABLED"):
        assert "matrix." not in str(step["env"][key]), f"{REUSABLE}: version-specific {key}"
    script = step["run"]
    assert "matrix.python-version" not in script, f"{REUSABLE}: version-specific test script"
    assert '"-n" "${PYTEST_WORKERS}" "--dist=loadgroup"' in script, str(REUSABLE)
    assert 'args+=("--cov")' in script, f"{REUSABLE}: preserve coverage on both versions"


def test_shared_env_and_manifest_delivery() -> None:
    template = Path("templates/consumer-repo") / ENV
    assert _pins(ENV)["CI_PYTHON_VERSION"] == "3.14", str(ENV)
    assert (ROOT / ENV).read_bytes() == (ROOT / template).read_bytes(), f"{ENV} != {template}"
    manifest = _load(Path(".github/sync-manifest.yml"))
    entries = [
        entry for entries in manifest.values() if isinstance(entries, list) for entry in entries
    ]
    entry = next(entry for entry in entries if entry.get("source") == str(ENV))
    assert entry["source_tree"] == "template", f"{ENV}: deliver the reviewed mirror"
    assert entry.get("target", str(ENV)) == str(ENV), str(ENV)
    assert "sync_mode" not in entry, f"{ENV}: updates must reach existing consumers"
    # The Gate is intentionally create-only; shared defaults do not rewrite a
    # consumer's explicit runtime policy or remove Python 3.12 runtime support.
    gate = next(entry for entry in manifest["workflows"] if entry["source"] == str(GATES[0]))
    assert gate["sync_mode"] == "create_only"


@pytest.mark.parametrize("job", ["lint-format", "lint-ruff", "typecheck-mypy", "tests"])
def test_shared_pins_are_loaded_before_repo_overrides(job: str, tmp_path: Path) -> None:
    steps = _load(REUSABLE)["jobs"][job]["steps"]
    install = next(step["run"] for step in steps if step.get("name") == "Install dependencies")
    # Execute the real source blocks, without installing packages or reading any
    # caller credentials, to prove both fallback and override precedence.
    start = install.index('ci_env="')
    end = install.index("  black_spec=", start)
    prefix = install[start:end]
    pins = tmp_path / ".github/workflows"
    pins.mkdir(parents=True)
    (pins / ENV.name).write_bytes((ROOT / ENV).read_bytes())
    for override in (False, True):
        if override:
            (pins / "autofix-versions.env").write_text("BLACK_VERSION=repo-override\n")
        script = prefix + ':\nfi\nprintf "%s" "$BLACK_VERSION"\n'
        result = subprocess.run(
            ["bash", "-eu", "-c", script],
            env={"PATH": os.defpath, "GITHUB_WORKSPACE": str(tmp_path)},
            text=True,
            capture_output=True,
            check=True,
        )
        expected = "repo-override" if override else _pins(ENV)["BLACK_VERSION"]
        assert result.stdout == expected, f"{REUSABLE}: {job} pin precedence"
