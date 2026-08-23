from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

WORKFLOW_PATH = Path(".github/workflows/reusable-10-ci-python.yml")
CONTRACT_FIXTURES = Path("tests/workflows/fixtures/reusable_ci_contract")


def _matrix_candidates(python_versions: str, python_version: str) -> list[str]:
    data = python_versions or ""
    fallback = python_version or ""

    if data and data != "[]" and "[" in data:
        chosen = data
    elif data and data != "[]" and "[" not in data:
        chosen = f"[{json.dumps(data)}]"
    elif fallback:
        chosen = f"[{json.dumps(fallback)}]"
    else:
        chosen = '["3.12"]'
    return json.loads(chosen)


def _load_workflow() -> dict:
    assert WORKFLOW_PATH.exists(), "Reusable workflow should exist"
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _normalize_expr(value: str) -> str:
    return re.sub(r"\s+", "", value).strip()


def _workflow_call_defaults(workflow: dict) -> dict[str, object]:
    triggers = workflow.get("on") or workflow.get(True) or {}
    inputs = triggers["workflow_call"]["inputs"]
    return {name: data.get("default") for name, data in inputs.items()}


def _contract_fixture(name: str) -> dict:
    return json.loads((CONTRACT_FIXTURES / name).read_text(encoding="utf-8"))


def _merged_inputs(fixture: dict) -> dict[str, object]:
    workflow = _load_workflow()
    merged = _workflow_call_defaults(workflow)
    merged.update(fixture.get("inputs", {}))
    return merged


def _expected_artifacts(
    inputs: dict[str, object], matrix: list[str], run_attempt: int = 1
) -> list[str]:
    prefix = str(inputs.get("artifact-prefix", "gate-"))
    primary = str(inputs.get("primary-python-version", "3.12"))
    artifacts: list[str] = []
    for version in matrix:
        artifacts.append(f"{prefix}coverage-{version}-{run_attempt}")
        if version != primary:
            continue
        if inputs.get("enable-metrics") is True:
            artifacts.append(f"{prefix}ci-metrics")
        if inputs.get("enable-history") is True:
            artifacts.append(f"{prefix}metrics-history")
        if inputs.get("enable-classification") is True:
            artifacts.append(f"{prefix}classification")
        if inputs.get("coverage") is True and inputs.get("enable-coverage-delta") is True:
            artifacts.append(f"{prefix}coverage-delta")
        if inputs.get("coverage") is True and inputs.get("enable-soft-gate") is True:
            artifacts.extend(
                [
                    f"{prefix}coverage-summary",
                    f"{prefix}coverage-trend",
                    f"{prefix}coverage-trend-history",
                ]
            )
    return artifacts


def _simulated_summary(inputs: dict[str, object], fixture: dict) -> dict[str, object]:
    artifacts = fixture["summary"]
    return {
        "python_version": fixture["matrix"][0],
        "checks": {
            "tests": {"tool": "pytest", "outcome": "success"},
            "coverage_minimum": {
                "tool": "threshold",
                "outcome": "success" if inputs.get("coverage") is True else "skipped",
            },
        },
        "artifacts": artifacts,
    }


def test_matrix_expression_supports_arrays_and_singletons() -> None:
    assert _matrix_candidates('["3.12", "3.13"]', "3.12") == ["3.12", "3.13"]
    assert _matrix_candidates("3.13", "3.12") == ["3.13"]
    assert _matrix_candidates("", "3.12") == ["3.12"]
    assert _matrix_candidates("[]", "") == ["3.12"]


def test_workflow_inputs_include_python_version_defaults() -> None:
    workflow = _load_workflow()

    triggers = workflow.get("on") or workflow.get(True) or {}
    workflow_call = triggers.get("workflow_call", {})
    dispatch = triggers.get("workflow_dispatch", {})

    call_inputs = workflow_call.get("inputs", {})
    dispatch_inputs = dispatch.get("inputs", {})

    # workflow_call inputs remain complete
    assert call_inputs.get("working-directory", {}).get("default") == "."
    assert call_inputs.get("python-version", {}).get("default") == "3.12"
    assert call_inputs.get("python-versions", {}).get("default") == "[]"
    assert call_inputs.get("primary-python-version", {}).get("default") == "3.12"
    assert call_inputs.get("pytest_args", {}).get("default") == ""

    # workflow_dispatch has reduced inputs (10-input limit) but python-versions remains
    assert dispatch_inputs.get("working-directory", {}).get("default") == "."
    assert dispatch_inputs.get("python-versions", {}).get("default") == '["3.12", "3.13"]'
    # python-version was removed from workflow_dispatch to meet GitHub's 10-input limit
    assert "python-version" not in dispatch_inputs
    assert "pytest_args" not in dispatch_inputs


def test_ruff_lint_preserves_consumer_rule_selection() -> None:
    workflow = _load_workflow()
    steps = workflow["jobs"]["lint-ruff"]["steps"]
    ruff_step = next(step for step in steps if step.get("name") == "Ruff (lint)")
    script = ruff_step["run"]

    assert "if python - <<'PY'" in script
    assert 'SELECT_KEYS = ("select", "extend-select")' in script
    assert "import tomli as tomllib" in script
    assert "text_has_selection(" in script
    assert "Path.cwd().parents" in script
    assert (
        "ruff check --select E4,E7,E9,F --output-format github "
        "--extend-exclude .workflows-lib ." in script
    )
    assert "ruff check --output-format github --extend-exclude .workflows-lib ." in script


def test_ruff_selection_probe_uses_nearest_config_and_parent_discovery(
    tmp_path: Path,
) -> None:
    workflow = _load_workflow()
    steps = workflow["jobs"]["lint-ruff"]["steps"]
    script = next(step for step in steps if step.get("name") == "Ruff (lint)")["run"]
    probe = script.split("if python - <<'PY'\n", 1)[1].split("\nPY\n", 1)[0]

    explicit = tmp_path / "explicit"
    explicit.mkdir()
    (explicit / "ruff.toml").write_text('[lint]\nextend-select = ["I"]\n', encoding="utf-8")
    assert subprocess.run([sys.executable, "-c", probe], cwd=explicit).returncode == 0

    no_selection = tmp_path / "no-selection"
    no_selection.mkdir()
    (no_selection / "pyproject.toml").write_text(
        "[tool.ruff]\nline-length = 88\n", encoding="utf-8"
    )
    assert subprocess.run([sys.executable, "-c", probe], cwd=no_selection).returncode == 1

    inherited = tmp_path / "inherited"
    nested = inherited / "src" / "package"
    nested.mkdir(parents=True)
    (inherited / "pyproject.toml").write_text(
        '[tool.ruff.lint]\nselect = ["E4"]\n', encoding="utf-8"
    )
    assert subprocess.run([sys.executable, "-c", probe], cwd=nested).returncode == 0


def test_default_input_contract_fixture_matches_artifacts() -> None:
    fixture = _contract_fixture("default_inputs.json")
    inputs = _merged_inputs(fixture)

    assert (
        _matrix_candidates(
            str(inputs["python-versions"]),
            str(inputs["python-version"]),
        )
        == fixture["matrix"]
    )
    assert inputs["coverage"] is True
    assert inputs["typecheck"] is True
    assert _expected_artifacts(inputs, fixture["matrix"]) == fixture["expected_artifacts"]


def test_modified_input_contract_fixture_matches_artifacts() -> None:
    fixture = _contract_fixture("coverage_typecheck_disabled.json")
    inputs = _merged_inputs(fixture)

    assert inputs["coverage"] is False
    assert inputs["typecheck"] is False
    assert inputs["run-mypy"] is False
    assert _expected_artifacts(inputs, fixture["matrix"]) == fixture["expected_artifacts"]
    assert _simulated_summary(inputs, fixture)["artifacts"] == {
        "coverage_xml": False,
        "coverage_json": False,
        "pytest_junit": True,
    }


def test_observability_artifact_contract_fixture_matches_names() -> None:
    fixture = _contract_fixture("observability_artifacts.json")
    inputs = _merged_inputs(fixture)

    assert _expected_artifacts(inputs, fixture["matrix"]) == fixture["expected_artifacts"]
    assert _simulated_summary(inputs, fixture)["checks"]["coverage_minimum"] == {
        "tool": "threshold",
        "outcome": "success",
    }


def test_artifact_names_normalized() -> None:
    workflow = _load_workflow()
    steps = workflow["jobs"]["tests"]["steps"]

    def _step(name: str) -> dict:
        for step in steps:
            if step.get("name") == name:
                return step
        raise AssertionError(f"Expected step `{name}` to exist")

    coverage_step = _step("Upload coverage artifact")
    assert _normalize_expr(coverage_step["with"]["name"]) == _normalize_expr(
        "${{ inputs['artifact-prefix'] }}coverage-${{ matrix.python-version }}-${{ github.run_attempt }}"
    )
    assert coverage_step["with"]["retention-days"] == 7

    metrics_step = _step("Upload metrics artifact")
    assert metrics_step["with"]["name"] == "${{ inputs['artifact-prefix'] }}ci-metrics"

    history_step = _step("Upload metrics history artifact")
    assert history_step["with"]["name"] == "${{ inputs['artifact-prefix'] }}metrics-history"

    classification_step = _step("Upload classification artifact")
    assert classification_step["with"]["name"] == "${{ inputs['artifact-prefix'] }}classification"

    coverage_trend_step = _step("Upload coverage trend artifact")
    assert coverage_trend_step["with"]["name"] == "${{ inputs['artifact-prefix'] }}coverage-trend"

    coverage_summary_step = _step("Upload coverage summary artifact")
    assert (
        coverage_summary_step["with"]["name"] == "${{ inputs['artifact-prefix'] }}coverage-summary"
    )

    delta_step = _step("Upload coverage delta artifact")
    assert delta_step["with"]["name"] == "${{ inputs['artifact-prefix'] }}coverage-delta"

    primary_step = _step("Resolve primary python version")
    assert _normalize_expr(primary_step["if"]) == "${{always()}}"

    workflows_helper_step = _step("Checkout Workflows artifact cache action")
    assert workflows_helper_step["with"]["persist-credentials"] is False
    helper_sparse_checkout = workflows_helper_step["with"]["sparse-checkout"]
    assert ".github/actions/artifact-cache" in helper_sparse_checkout
    assert "config/langsmith_fleet_registry.json" in helper_sparse_checkout
    assert "scripts/ensure_langsmith_fleet_artifact.py" in helper_sparse_checkout

    langsmith_helper_step = _step("Checkout Workflows LangSmith fleet helper")
    assert (
        langsmith_helper_step["uses"] == "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
    )
    assert langsmith_helper_step["with"]["persist-credentials"] is False
    assert _normalize_expr(langsmith_helper_step["if"]) == (
        "${{always()&&!inputs.cache&&matrix.python-version==env.PRIMARY_PYTHON_VERSION}}"
    )
    assert (
        "config/langsmith_fleet_registry.json" in langsmith_helper_step["with"]["sparse-checkout"]
    )
    assert (
        "scripts/ensure_langsmith_fleet_artifact.py"
        in langsmith_helper_step["with"]["sparse-checkout"]
    )

    langsmith_ensure_step = _step("Ensure LangSmith fleet telemetry artifact")
    assert _normalize_expr(langsmith_ensure_step["if"]) == (
        "${{always()&&matrix.python-version==env.PRIMARY_PYTHON_VERSION}}"
    )
    assert "scripts/ensure_langsmith_fleet_artifact.py" in langsmith_ensure_step["run"]
    assert (
        ".workflows-lib/scripts/ensure_langsmith_fleet_artifact.py" in langsmith_ensure_step["run"]
    )
    assert "fallback helper is unavailable" in langsmith_ensure_step["run"]
    assert (
        "::warning::LangSmith fleet fallback helper is unavailable" in langsmith_ensure_step["run"]
    )
    assert "--registry" in langsmith_ensure_step["run"]
    assert "--project-root" in langsmith_ensure_step["run"]
    assert "--repository" in langsmith_ensure_step["run"]

    langsmith_check_step = _step("Check LangSmith fleet telemetry artifact")
    assert langsmith_check_step["id"] == "langsmith_fleet_artifact"
    assert "artifacts/langsmith/langsmith-fleet.ndjson" in langsmith_check_step["run"]
    assert "exists=true" in langsmith_check_step["run"]

    langsmith_upload_step = _step("Upload LangSmith fleet telemetry artifact")
    assert langsmith_upload_step["uses"] == "actions/upload-artifact@v7"
    assert langsmith_upload_step["continue-on-error"] is True
    assert langsmith_upload_step["with"]["name"] == "langsmith-fleet.ndjson"
    assert (
        langsmith_upload_step["with"]["path"]
        == "${{ env.PROJECT_ROOT }}/artifacts/langsmith/langsmith-fleet.ndjson"
    )
    assert langsmith_upload_step["with"]["if-no-files-found"] == "warn"
    assert langsmith_upload_step["with"]["retention-days"] == 90
    assert langsmith_upload_step["with"]["overwrite"] is True

    upload_if = _normalize_expr(langsmith_upload_step["if"])
    assert "always()" in upload_if
    assert "matrix.python-version==env.PRIMARY_PYTHON_VERSION" in upload_if
    assert "steps.langsmith_fleet_artifact.outputs.exists=='true'" in upload_if

    step_names = [step.get("name") for step in steps]
    assert step_names.index("Check LangSmith fleet telemetry artifact") > step_names.index(
        "Upload coverage trend history artifact"
    )
    assert step_names.index("Ensure LangSmith fleet telemetry artifact") > step_names.index(
        "Upload coverage trend history artifact"
    )
    assert step_names.index("Check LangSmith fleet telemetry artifact") == (
        step_names.index("Ensure LangSmith fleet telemetry artifact") + 1
    )
    assert step_names.index("Upload LangSmith fleet telemetry artifact") == (
        step_names.index("Check LangSmith fleet telemetry artifact") + 1
    )


def test_workflow_uses_shared_mypy_pin_helper() -> None:
    workflow = _load_workflow()
    steps = workflow["jobs"]["tests"]["steps"]

    resolve_step = next(step for step in steps if step.get("name") == "Resolve mypy python pin")

    run_block = resolve_step.get("run", "")
    assert 'python "${GITHUB_WORKSPACE}/tools/resolve_mypy_pin.py"' in run_block


def test_workflow_requires_exact_test_tool_pins() -> None:
    run_block = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert 'pytest_spec="pytest"' not in run_block
    assert 'pytest_cov_spec="pytest-cov"' not in run_block
    assert 'coverage_spec="coverage"' not in run_block
    assert 'pytest_xdist_spec="pytest-xdist"' not in run_block
    assert "installing latest tool versions" not in run_block
    assert (
        run_block.count(
            'echo "Error: ${autofix_env} is required; refusing to install unpinned tooling." >&2'
        )
        == 4
    )
    assert run_block.count('require_exact_pin "pytest" "$pytest_spec"') == 4
    assert run_block.count('require_exact_pin "pytest-xdist" "$pytest_xdist_spec"') == 4
    assert run_block.count('require_exact_pin "pytest-cov" "$pytest_cov_spec"') == 4
    assert run_block.count('require_exact_pin "coverage" "$coverage_spec"') == 4


def test_working_directory_propagates_to_steps() -> None:
    workflow = _load_workflow()
    job = workflow["jobs"]["tests"]

    defaults = job.get("defaults", {}).get("run", {})
    assert defaults.get("working-directory") == "${{ inputs['working-directory'] || '.' }}"

    env = job.get("env", {})
    assert env.get("WORKDIR") == "${{ inputs['working-directory'] || '.' }}"
    assert _normalize_expr(env.get("PROJECT_ROOT", "")) == _normalize_expr(
        "${{ inputs['working-directory'] != '' && inputs['working-directory'] != '.' "
        "&& format('{0}/{1}', github.workspace, inputs['working-directory']) || github.workspace }}"
    )

    steps = job["steps"]
    checkout_sparse = next(
        step for step in steps if step.get("name") == "Checkout repository (sparse)"
    )
    assert (
        checkout_sparse["if"]
        == "${{ inputs['working-directory'] != '' && inputs['working-directory'] != '.' }}"
    )
    sparse_with = checkout_sparse.get("with", {})
    assert ".github/workflows" in sparse_with.get("sparse-checkout", "")
    assert "${{ inputs['working-directory'] }}" in sparse_with.get("sparse-checkout", "")
    assert sparse_with.get("sparse-checkout-cone-mode") is True

    cache_steps = {step["name"]: step for step in steps if "Cache" in step.get("name", "")}
    assert cache_steps["Cache mypy state"]["with"]["path"] == (
        "${{ inputs['working-directory'] || '.' }}/.mypy_cache"
    )
    assert cache_steps["Cache pytest state"]["with"]["path"] == (
        "${{ inputs['working-directory'] || '.' }}/.pytest_cache"
    )

    coverage_upload = next(step for step in steps if step.get("name") == "Upload coverage artifact")
    assert coverage_upload["with"]["path"] == "${{ env.PROJECT_ROOT }}/artifacts/coverage"


# --- Coverage config / editable-install gating -----------------------------
#
# Regression cover for a pair of mutually exclusive assumptions: the pytest
# step used to pass --cov-config=pyproject.toml unconditionally (fatal for a
# consumer without that file), while the install steps treated the mere
# presence of pyproject.toml as proof of an installable distribution. A
# non-package consumer could satisfy neither, so `coverage: true` was unusable.

_ARGS_START = 'args=("--junitxml=pytest-junit.xml")'
_PREDICATE_START = "pyproject_declares_distribution() {"
_EDITABLE_SPEC = "specs+=('-e' '.[app,dev]')"


def _install_steps() -> list[dict]:
    workflow = _load_workflow()
    steps = [
        step
        for job in workflow["jobs"].values()
        for step in (job.get("steps") or [])
        if step.get("name") == "Install dependencies"
    ]
    assert len(steps) == 4, f"expected 4 install steps, found {len(steps)}"
    return steps


def _pytest_step_script() -> str:
    workflow = _load_workflow()
    steps = workflow["jobs"]["tests"]["steps"]
    step = next(s for s in steps if s.get("name") == "Pytest (unit tests with coverage)")
    return step["run"]


def _block(script: str, opener: str, terminator: str) -> str:
    """Extract the shell block starting at `opener`, up to its matching terminator.

    Matching is by indentation rather than by a literal end marker, so the block
    survives reformatting of its interior. YAML block scalars arrive dedented.
    """
    lines = script.splitlines()
    starts = [n for n, line in enumerate(lines) if line.strip().startswith(opener)]
    assert starts, f"no line starting {opener!r} in step script"
    start = starts[0]
    indent = len(lines[start]) - len(lines[start].lstrip())
    for n in range(start + 1, len(lines)):
        line = lines[n]
        if not line.strip():
            continue
        if (len(line) - len(line.lstrip())) == indent and line.strip() == terminator:
            return textwrap.dedent("\n".join(lines[start : n + 1]))
    raise AssertionError(f"unterminated {opener!r} block (expected {terminator!r})")


def _coverage_arg_script() -> str:
    """The shipped coverage-arg builder, wrapped so it prints the args it built."""
    script = _pytest_step_script()
    assert _ARGS_START in script, "pytest step no longer seeds args the expected way"
    block = _block(script, 'if [ "${COVERAGE_ENABLED}" = "true" ]; then', "fi")
    assert "--cov" in block, "coverage conditional no longer builds coverage args"
    return (
        "set -euo pipefail\n"
        + _ARGS_START
        + "\n"
        + block
        + '\nif [ ${#args[@]} -gt 0 ]; then printf "%s\\n" "${args[@]}"; fi\n'
    )


def _built_coverage_args(cwd: Path, coverage_enabled: str = "true") -> list[str]:
    result = subprocess.run(
        ["bash", "-c", _coverage_arg_script()],
        cwd=cwd,
        env={"PATH": os.environ["PATH"], "COVERAGE_ENABLED": coverage_enabled},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.split()


def _predicate_definition() -> str:
    """The shipped pyproject_declares_distribution helper."""
    script = _install_steps()[0]["run"]
    assert _PREDICATE_START in script, "install step no longer defines the predicate"
    return _block(script, _PREDICATE_START, "}")


def _predicate_script() -> str:
    return _predicate_definition() + "\npyproject_declares_distribution\n"


def test_coverage_args_omit_cov_config_when_pyproject_absent(tmp_path: Path) -> None:
    """A consumer with no pyproject.toml must fall back to coverage's discovery."""
    absent = tmp_path / "absent"
    absent.mkdir()
    args = _built_coverage_args(absent)
    assert "--cov" in args
    assert not any(a.startswith("--cov-config") for a in args), args
    # Reporting is unaffected by the guard.
    assert "--cov-report=xml:coverage.xml" in args

    present = tmp_path / "present"
    present.mkdir()
    (present / "pyproject.toml").write_text(
        "[tool.coverage.run]\nbranch = true\n", encoding="utf-8"
    )
    assert "--cov-config=pyproject.toml" in _built_coverage_args(present)

    # Coverage disabled: no coverage args at all, with or without the file.
    assert _built_coverage_args(present, "false") == ["--junitxml=pytest-junit.xml"]


def test_pytest_collects_with_coverage_and_no_pyproject(tmp_path: Path) -> None:
    """End-to-end: the built args must let pytest actually collect and run.

    Before the fix this died with
    `coverage.exceptions.ConfigError: Couldn't read 'pyproject.toml' as a
    config file` for every test on every matrix runtime.
    """
    pytest.importorskip("pytest_cov", reason="pytest-cov not installed in this environment")

    consumer = tmp_path / "flat-module-consumer"
    consumer.mkdir()
    # Mirrors a non-package consumer: flat root modules, no build backend.
    (consumer / "thing.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (consumer / "test_thing.py").write_text(
        "from thing import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    assert not (consumer / "pyproject.toml").exists()

    args = _built_coverage_args(consumer)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *args, "-p", "no:cacheprovider", "-q"],
        cwd=consumer,
        env={**os.environ, "PYTHONPATH": str(consumer)},
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    assert "ConfigError" not in combined, combined
    assert result.returncode == 0, combined
    assert (consumer / "coverage.xml").is_file(), "coverage report should still be produced"


def test_pyproject_declares_distribution_requires_real_metadata(tmp_path: Path) -> None:
    """Only a pyproject that declares a distribution should mean "installable"."""
    probe = _predicate_script()

    def declares(name: str, content: str | None) -> bool:
        case = tmp_path / name
        case.mkdir()
        if content is not None:
            (case / "pyproject.toml").write_text(content, encoding="utf-8")
        return subprocess.run(["bash", "-c", probe], cwd=case).returncode == 0

    # Not a distribution.
    assert not declares("missing", None)
    assert not declares("config-only", "[tool.coverage.run]\nbranch = true\n")
    assert not declares(
        "tool-only", "[tool.ruff]\nline-length = 88\n\n[tool.mypy]\nstrict = true\n"
    )

    # Genuine distributions, in each form the fleet uses.
    assert declares("pep621", '[project]\nname = "demo"\nversion = "0.1.0"\n')
    assert declares("backend-only", '[build-system]\nrequires = ["setuptools"]\n')
    assert declares("poetry", '[tool.poetry]\nname = "demo"\nversion = "0.1.0"\n')
    # Whitespace and trailing comments are still table headers.
    assert declares("spaced", "  [ project ]  # metadata\nname = 'demo'\n")
    # A [project] mention that is not a table header must not count.
    assert not declares(
        "mention",
        '[tool.coverage.run]\nomit = ["[project]"]\n',
    )


def test_all_install_steps_gate_editable_install_on_distribution_metadata() -> None:
    """All four install steps must share the gate, not just the tests job.

    Fixing one leaves lint/format/mypy still failing for the same consumer.
    """
    for step in _install_steps():
        script = step["run"]
        assert _PREDICATE_START in script, "install step lost the distribution predicate"
        assert "if pyproject_declares_distribution" in script
        # The bare filename gate must not survive anywhere near the editable install.
        assert "if [ -f pyproject.toml ]; then\n            specs+=" not in script
        assert "if [ -f pyproject.toml ]; then\n              specs+=" not in script


def test_config_only_pyproject_does_not_request_editable_install(tmp_path: Path) -> None:
    """The gate's actual effect on the install spec list."""
    script = _install_steps()[-1]["run"]
    gate = _block(script, "if pyproject_declares_distribution", "fi")
    assert _EDITABLE_SPEC in gate, "gate no longer guards the editable install"

    probe = (
        "set -euo pipefail\n"
        + _predicate_definition()
        + "\nspecs=()\n"
        + gate
        + '\nif [ ${#specs[@]} -gt 0 ]; then printf "%s\\n" "${specs[@]}"; fi\n'
    )

    def specs_for(name: str, files: dict[str, str]) -> list[str]:
        case = tmp_path / name
        case.mkdir()
        for fname, content in files.items():
            (case / fname).write_text(content, encoding="utf-8")
        result = subprocess.run(["bash", "-c", probe], cwd=case, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        return result.stdout.split()

    assert (
        specs_for("config-only", {"pyproject.toml": "[tool.coverage.run]\nbranch = true\n"}) == []
    )
    assert specs_for("nothing", {}) == []
    # Still installs where it should.
    assert specs_for("pep621", {"pyproject.toml": '[project]\nname = "d"\nversion = "1"\n'}) == [
        "-e",
        ".[app,dev]",
    ]
    # A config-only pyproject alongside a legacy setup.py is still a package.
    assert specs_for(
        "legacy",
        {"pyproject.toml": "[tool.coverage.run]\nbranch = true\n", "setup.py": "pass\n"},
    ) == ["-e", ".[app,dev]"]
