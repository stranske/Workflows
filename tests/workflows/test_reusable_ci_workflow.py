from __future__ import annotations

import json
import re
from pathlib import Path

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
        langsmith_helper_step["uses"] == "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0"
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
