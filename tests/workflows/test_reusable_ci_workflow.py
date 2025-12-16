from __future__ import annotations

import json
from pathlib import Path

import yaml

WORKFLOW_PATH = Path(".github/workflows/reusable-10-ci-python.yml")


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
        chosen = '["3.11"]'
    return json.loads(chosen)


def _load_workflow() -> dict:
    assert WORKFLOW_PATH.exists(), "Reusable workflow should exist"
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_matrix_expression_supports_arrays_and_singletons() -> None:
    assert _matrix_candidates('["3.11", "3.12"]', "3.10") == ["3.11", "3.12"]
    assert _matrix_candidates("3.12", "3.11") == ["3.12"]
    assert _matrix_candidates("", "3.11") == ["3.11"]
    assert _matrix_candidates("[]", "") == ["3.11"]


def test_workflow_inputs_include_python_version_defaults() -> None:
    workflow = _load_workflow()

    triggers = workflow.get("on") or workflow.get(True) or {}
    workflow_call = triggers.get("workflow_call", {})
    dispatch = triggers.get("workflow_dispatch", {})

    call_inputs = workflow_call.get("inputs", {})
    dispatch_inputs = dispatch.get("inputs", {})

    # workflow_call inputs remain complete
    assert call_inputs.get("python-version", {}).get("default") == "3.11"
    assert call_inputs.get("python-versions", {}).get("default") == "[]"
    assert call_inputs.get("primary-python-version", {}).get("default") == "3.11"

    # workflow_dispatch has reduced inputs (10-input limit) but python-versions remains
    assert dispatch_inputs.get("python-versions", {}).get("default") == '["3.11"]'
    # python-version was removed from workflow_dispatch to meet GitHub's 10-input limit
    assert "python-version" not in dispatch_inputs


def test_artifact_names_normalized() -> None:
    workflow = _load_workflow()
    steps = workflow["jobs"]["tests"]["steps"]

    def _step(name: str) -> dict:
        for step in steps:
            if step.get("name") == name:
                return step
        raise AssertionError(f"Expected step `{name}` to exist")

    coverage_step = _step("Upload coverage artifact")
    assert (
        coverage_step["with"]["name"]
        == "${{ inputs['artifact-prefix'] }}coverage-${{ matrix.python-version }}"
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


def test_workflow_uses_shared_mypy_pin_helper() -> None:
    workflow = _load_workflow()
    steps = workflow["jobs"]["tests"]["steps"]

    resolve_step = next(step for step in steps if step.get("name") == "Resolve mypy python pin")

    run_block = resolve_step.get("run", "")
    assert "python tools/resolve_mypy_pin.py" in run_block
