"""Keep first-party CI runtimes, workload selection and shared pins aligned."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
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
    assert inputs["primary-python-version"] == "3.14", str(path)
    assert inputs["coverage-python-version"] == "3.14", str(path)
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
    for key in ("PYTEST_MARKERS", "PYTEST_ARGS", "PYTEST_WORKERS"):
        assert "matrix." not in str(step["env"][key]), f"{REUSABLE}: version-specific {key}"
    script = step["run"]
    assert "matrix.python-version" not in script, f"{REUSABLE}: version-specific test script"
    assert '"-n" "${PYTEST_WORKERS}" "--dist=loadgroup"' in script, str(REUSABLE)
    assert 'args+=("--cov")' in script, f"{REUSABLE}: preserve coverage on the selected version"


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
    end = install.index('require_exact_pin "pytest"', start)
    prefix = install[start:end]
    # Include the production resolver, rather than reproducing its behavior.
    resolver_start = install.index("resolve_spec()")
    resolver_end = install.index("# Shared fallback pins", resolver_start)
    resolver = install[resolver_start:resolver_end]
    pins = tmp_path / ".github/workflows"
    pins.mkdir(parents=True)
    (pins / ENV.name).write_bytes((ROOT / ENV).read_bytes())
    expected_pins = {
        "BLACK_VERSION": ("black_spec", "black", "26.10.1"),
        "DOCFORMATTER_VERSION": ("docformatter_spec", "docformatter", "1.7.8"),
        "ISORT_VERSION": ("isort_spec", "isort", "9.0.2"),
        "RUFF_VERSION": ("ruff_spec", "ruff", "0.17.1"),
        "MYPY_VERSION": ("mypy_spec", "mypy", "2.4.0"),
        "PYTEST_VERSION": ("pytest_spec", "pytest", "9.1.1"),
        "PYTEST_COV_VERSION": ("pytest_cov_spec", "pytest-cov", "7.1.0"),
        "PYTEST_XDIST_VERSION": ("pytest_xdist_spec", "pytest-xdist", "3.8.0"),
        "COVERAGE_VERSION": ("coverage_spec", "coverage", "7.16.2"),
    }
    for override in (False, True):
        expected = {}
        for index, (_key, (variable, package, fallback)) in enumerate(expected_pins.items()):
            version = f"99.0.{index}" if override else fallback
            expected[variable] = f"{package}=={version}"
        if override:
            (pins / "autofix-versions.env").write_text(
                "".join(f"{key}=99.0.{index}\n" for index, key in enumerate(expected_pins))
            )
        output = "\n".join(f'printf "%s\\n" "${{{variable}}}"' for variable in expected)
        script = resolver + prefix + output
        result = subprocess.run(
            ["bash", "-eu", "-c", script],
            env={"PATH": os.defpath, "GITHUB_WORKSPACE": str(tmp_path)},
            text=True,
            capture_output=True,
            check=True,
        )
        assert result.stdout.splitlines() == list(
            expected.values()
        ), f"{REUSABLE}: {job} pin precedence"


def test_shared_default_runtime_is_consumed() -> None:
    workflow = _load(REUSABLE)
    validate = next(
        step
        for step in workflow["jobs"]["validate-inputs"]["steps"]
        if step.get("id") == "validate"
    )
    script = validate["run"].split("python <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    for default in ("3.13", "3.14"):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            env_path = work / ENV
            env_path.parent.mkdir(parents=True)
            env_path.write_text(f"CI_PYTHON_VERSION={default}\n")
            output = work / "output"
            result = subprocess.run(
                [os.sys.executable, "-c", script],
                cwd=work,
                env={"PATH": os.defpath, "GITHUB_OUTPUT": str(output)},
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stderr + result.stdout
            assert output.read_text() == f"primary_python={default}\n"


@pytest.mark.parametrize("enabled", ["true", "false"])
def test_coverage_mode_keeps_test_selection(enabled: str, tmp_path: Path) -> None:
    steps = _load(REUSABLE)["jobs"]["tests"]["steps"]
    script = next(step["run"] for step in steps if step.get("id") == "pytest")
    # Execute the shipped argument construction with actual installed plugins.
    script = script[: script.index("# Clear stale evidence")]
    script += '\nprintf "%s\\n" "${args[@]}"\n'
    (tmp_path / "pyproject.toml").write_text("[tool.coverage.run]\nbranch = true\n")
    result = subprocess.run(
        [
            "/opt/homebrew/bin/bash" if Path("/opt/homebrew/bin/bash").exists() else "bash",
            "-eu",
            "-c",
            script,
        ],
        cwd=tmp_path,
        env={
            "PATH": str(Path(os.sys.executable).parent) + os.pathsep + os.defpath,
            "COVERAGE_ENABLED": enabled,
            "PYTEST_MARKERS": "not slow",
            "PYTEST_ARGS": "tests",
            "PYTEST_WORKERS": "4",
        },
        capture_output=True,
        text=True,
        check=True,
    )
    args = result.stdout.splitlines()
    assert args[-3:] == ["-n", "4", "--dist=loadgroup"]
    assert args[1:3] == ["-m", "not slow"]
    assert "tests" in args and "--dist=loadgroup" in args
    assert ("--cov" in args) == (enabled == "true")
    assert ("--no-cov" in args) == (enabled == "false")
