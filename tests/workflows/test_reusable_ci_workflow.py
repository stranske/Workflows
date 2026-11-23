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
CONTRACT_SCENARIOS = Path("tests/workflows/fixtures/reusable_ci_contract.json")
TREND_MEASUREMENT_CONDITION = "(!inputs['require-measured-coverage-trend'] || steps.coverage_trend.outputs.measured == 'true')"


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
        chosen = '["3.13", "3.14"]'
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
    return json.loads(CONTRACT_SCENARIOS.read_text(encoding="utf-8"))[name]


def _merged_inputs(fixture: dict) -> dict[str, object]:
    merged = _workflow_call_defaults(_load_workflow())
    merged.update(fixture["inputs"])
    return merged


def _step_outputs(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines())


def _run_ci_python(step: dict, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    block = _block(step["run"], "python - <<'PY'", "PY")
    code = "\n".join(block.splitlines()[1:-1])
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )


def _assert_ci_contract(tmp_path: Path, inputs: dict[str, object], fixture: dict) -> None:
    steps = {step["name"]: step for step in _load_workflow()["jobs"]["tests"]["steps"]}
    stage = steps["Stage coverage artifact layout"]
    summarize = steps["Record CI summary"]
    payload = steps["Record staged artifact paths"]
    minimum = steps["Enforce coverage minimum"]
    coverage_condition = (
        "inputs.coverage && (inputs['coverage-python-version'] == '' || "
        "inputs['coverage-python-version'] == matrix.python-version)"
    )
    for step in (stage, summarize, payload):
        assert _normalize_expr(step["env"]["COVERAGE_ENABLED"]) == _normalize_expr(
            "${{ (" + coverage_condition + ") }}"
        )
    assert _normalize_expr(minimum["if"]) == _normalize_expr(
        "${{ (" + coverage_condition + ") && inputs['coverage-min'] != '' }}"
    )

    matrix = _matrix_candidates(str(inputs["python-versions"]), str(inputs["python-version"]))
    assert matrix == fixture["matrix"]
    validation_output = tmp_path / "validated-inputs"
    validated = subprocess.run(
        [sys.executable, "-c", _validate_inputs_script()],
        env={
            "PYTHON_VERSIONS": str(inputs["python-versions"]),
            "PYTHON_VERSION": str(inputs["python-version"]),
            "PRIMARY_IN": str(inputs["primary-python-version"]),
            "COVERAGE_PYTHON_VERSION": str(inputs["coverage-python-version"]),
            "COVERAGE": str(inputs["coverage"]).lower(),
            "GITHUB_OUTPUT": str(validation_output),
        },
        capture_output=True,
        text=True,
    )
    assert validated.returncode == 0, validated.stdout + validated.stderr
    resolve_primary = steps["Resolve primary python version"]
    assert resolve_primary["env"]["RESOLVED_PRIMARY"] == (
        "${{ needs.validate-inputs.outputs.primary_python }}"
    )
    runtime_env = tmp_path / "runtime-env"
    resolved = subprocess.run(
        ["bash", "-c", resolve_primary["run"]],
        env={
            "RESOLVED_PRIMARY": _step_outputs(validation_output)["primary_python"],
            "GITHUB_ENV": str(runtime_env),
        },
        capture_output=True,
        text=True,
    )
    assert resolved.returncode == 0, resolved.stderr
    primary = _step_outputs(runtime_env)["PRIMARY_PYTHON_VERSION"]
    payloads = {}
    for runtime in matrix:
        work = tmp_path / runtime
        work.mkdir()
        files = {
            "coverage.xml": '<coverage line-rate="0.927"/>',
            "coverage.json": '{"totals": {"percent_covered": 91.284}}',
            "pytest-junit.xml": (
                '<testsuites><testsuite><testcase classname="tests.example" '
                'name="test_contract" time="0.01"/></testsuite></testsuites>'
            ),
        }
        # Leave source coverage in disabled scenarios too. The authored staging
        # step must exclude those files while retaining the pytest result.
        for name, content in files.items():
            (work / name).write_text(content, encoding="utf-8")

        enabled = inputs["coverage"] is True and inputs["coverage-python-version"] in ("", runtime)
        minimum_outcome = "skipped"
        if enabled and inputs["coverage-min"]:
            verdict = _run_ci_python(minimum, work, {"COVERAGE_MIN": str(inputs["coverage-min"])})
            minimum_outcome = "success" if verdict.returncode == 0 else "failure"
        output = work / "outputs"
        env = {
            "PATH": os.environ["PATH"],
            "COVERAGE_ENABLED": str(enabled).lower(),
            "PYTHON_VERSION": runtime,
            "PYTEST_OUTCOME": "success",
            "COVERAGE_MIN_OUTCOME": minimum_outcome,
            "GITHUB_OUTPUT": str(output),
        }
        run = subprocess.run(
            ["bash", "-c", stage["run"].replace("${{ matrix.python-version }}", runtime)],
            cwd=work,
            env=env,
            capture_output=True,
            text=True,
        )
        assert run.returncode == 0, run.stderr
        report = _run_ci_python(summarize, work, env)
        assert report.returncode == 0, report.stderr

        relative = Path("artifacts/coverage/runtimes") / runtime
        paths = {
            "coverage_xml": relative / "coverage.xml",
            "coverage_json": relative / "coverage.json",
            "pytest_junit": relative / "pytest-junit.xml",
        }
        summary_path = relative / "summary.json"
        assert _step_outputs(output)["summary_path"] == summary_path.as_posix()
        summary = json.loads((work / summary_path).read_text(encoding="utf-8"))
        assert summary["python_version"] == runtime
        assert summary["checks"] == {
            "tests": {"tool": "pytest", "outcome": "success"},
            "coverage_minimum": {
                "tool": "threshold",
                "outcome": fixture["coverage_minimum_outcome"],
            },
        }
        assert summary["artifacts"] == fixture["summary"]
        for key, path in paths.items():
            assert (work / path).is_file() is fixture["summary"][key]
            if fixture["summary"][key]:
                assert (work / path).read_text(encoding="utf-8") == files[path.name]
        assert summary.get("coverage") == (
            {"percent": 92.7, "source": "coverage.xml"} if enabled else None
        )
        index = work / "artifacts/coverage/index.ndjson"
        assert [json.loads(line) for line in index.read_text(encoding="utf-8").splitlines()] == [
            summary
        ]

        output.unlink()
        result = _run_ci_python(payload, work, {**env, "SUMMARY_PATH": summary_path.as_posix()})
        assert result.returncode == 0, result.stderr
        paths_output = _step_outputs(output)
        coverage_json = paths["coverage_json"] if fixture["summary"]["coverage_json"] else None
        assert paths_output == {
            "coverage_json": coverage_json.as_posix() if coverage_json else "",
            "junit_path": paths["pytest_junit"].as_posix(),
            "summary_path": summary_path.as_posix(),
            "has_payload": "true",
        }
        payloads[runtime] = paths_output["has_payload"]

    artifacts = _configured_artifact_names(steps, inputs, primary, payloads, coverage_condition)
    assert artifacts == fixture["expected_artifacts"]


def _configured_artifact_names(
    steps: dict,
    inputs: dict[str, object],
    primary: str,
    payloads: dict[str, str],
    coverage_condition: str,
    *,
    trend_measured: bool = False,
) -> dict[str, list[str]]:
    """Bind each runtime's names to the workflow's declared upload contract."""
    primary_condition = "matrix.python-version == env.PRIMARY_PYTHON_VERSION"
    prefix = str(inputs["artifact-prefix"])
    uploads = (
        ("Upload metrics artifact", "enable-metrics", False),
        ("Upload metrics history artifact", "enable-history", False),
        ("Upload classification artifact", "enable-classification", False),
        ("Upload coverage delta artifact", "enable-coverage-delta", True),
        ("Upload coverage summary artifact", "enable-soft-gate", True),
        ("Upload coverage trend artifact", "enable-soft-gate", True),
        ("Upload coverage trend history artifact", "enable-soft-gate", True),
    )
    coverage_upload = steps["Upload coverage artifact"]
    assert _normalize_expr(coverage_upload["if"]) == _normalize_expr(
        "${{ always() && steps.coverage_paths.outputs.has_payload == 'true' }}"
    )
    artifacts_by_runtime = {}
    for runtime, has_payload in payloads.items():
        artifacts: list[str] = []
        artifacts_by_runtime[runtime] = artifacts
        if has_payload == "true":
            name = coverage_upload["with"]["name"]
            artifacts.append(
                re.sub(r"\s+", "", name)
                .replace("${{inputs['artifact-prefix']}}", prefix)
                .replace("${{matrix.python-version}}", runtime)
                .replace("${{github.run_attempt}}", "1")
            )
        if runtime != primary:
            continue
        for name, toggle, requires_coverage in uploads:
            upload = steps[name]
            condition = f"inputs['{toggle}'] && "
            if toggle == "enable-soft-gate":
                condition += f"{TREND_MEASUREMENT_CONDITION} && "
            condition += primary_condition
            if requires_coverage:
                condition = f"({coverage_condition}) && {condition}"
            assert _normalize_expr(upload["if"]) == _normalize_expr("${{ " + condition + " }}")
            if (
                toggle == "enable-soft-gate"
                and inputs["require-measured-coverage-trend"]
                and not trend_measured
            ):
                continue
            if inputs[toggle] is True and (
                not requires_coverage
                or (
                    inputs["coverage"] is True
                    and inputs["coverage-python-version"] in ("", runtime)
                )
            ):
                artifacts.append(
                    upload["with"]["name"].replace("${{ inputs['artifact-prefix'] }}", prefix)
                )
    return artifacts_by_runtime


def test_matrix_expression_supports_arrays_and_singletons() -> None:
    assert _matrix_candidates('["3.12", "3.13"]', "3.12") == ["3.12", "3.13"]
    assert _matrix_candidates("3.13", "3.12") == ["3.13"]
    assert _matrix_candidates("", "3.12") == ["3.12"]
    assert _matrix_candidates("[]", "") == ["3.13", "3.14"]


def test_workflow_inputs_include_python_version_defaults() -> None:
    workflow = _load_workflow()

    triggers = workflow.get("on") or workflow.get(True) or {}
    workflow_call = triggers.get("workflow_call", {})
    dispatch = triggers.get("workflow_dispatch", {})

    call_inputs = workflow_call.get("inputs", {})
    dispatch_inputs = dispatch.get("inputs", {})

    # workflow_call inputs remain complete
    assert call_inputs.get("working-directory", {}).get("default") == "."
    assert call_inputs.get("python-version", {}).get("default") == ""
    assert call_inputs.get("python-versions", {}).get("default") == "[]"
    assert call_inputs.get("primary-python-version", {}).get("default") == ""
    assert call_inputs.get("pytest_args", {}).get("default") == ""
    assert call_inputs.get("pytest-workers", {}).get("default") == "auto"

    # workflow_dispatch has reduced inputs (10-input limit) but python-versions remains
    assert dispatch_inputs.get("working-directory", {}).get("default") == "."
    assert dispatch_inputs.get("python-versions", {}).get("default") == '["3.13", "3.14"]'
    # python-version was removed from workflow_dispatch to meet GitHub's 10-input limit
    assert "python-version" not in dispatch_inputs
    assert "pytest_args" not in dispatch_inputs


def _validate_inputs_script() -> str:
    workflow = _load_workflow()
    steps = workflow["jobs"]["validate-inputs"]["steps"]
    script = next(step for step in steps if step.get("name") == "Validate workflow inputs")["run"]
    return script.split("python <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]


@pytest.mark.parametrize("value", ["NaN", "inf", "-inf"])
def test_validate_inputs_rejects_non_finite_numbers(value: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", _validate_inputs_script()],
        env={"COVERAGE_MIN": value},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "coverage-min must be a finite number" in result.stdout


def test_validate_inputs_accepts_finite_number() -> None:
    result = subprocess.run(
        [sys.executable, "-c", _validate_inputs_script()],
        env={"COVERAGE_MIN": "75.5"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


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


def test_default_input_contract_fixture_matches_artifacts(tmp_path: Path) -> None:
    fixture = _contract_fixture("default_inputs")
    inputs = _merged_inputs(fixture)
    assert inputs["coverage"] is True
    assert inputs["typecheck"] is True
    _assert_ci_contract(tmp_path, inputs, fixture)


def test_modified_input_contract_fixture_matches_artifacts(tmp_path: Path) -> None:
    fixture = _contract_fixture("coverage_typecheck_disabled")
    inputs = _merged_inputs(fixture)
    assert inputs["coverage"] is False
    assert inputs["typecheck"] is False
    assert inputs["run-mypy"] is False
    _assert_ci_contract(tmp_path, inputs, fixture)


def test_observability_artifact_contract_fixture_matches_names(tmp_path: Path) -> None:
    fixture = _contract_fixture("observability_artifacts")
    _assert_ci_contract(tmp_path, _merged_inputs(fixture), fixture)


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


def test_pinned_verifier_history_fetch_deepens_the_checkout_ref(tmp_path: Path) -> None:
    """Execute the workflow shell against a local depth-1 pull merge checkout.

    The fixture substitutes only the two history anchors; dates, fetch
    commands and ancestry checks come from the production step. No GitHub access is needed.
    """
    steps = _load_workflow()["jobs"]["tests"]["steps"]
    step = next(
        item for item in steps if item.get("name") == "Fetch pinned verifier revision history"
    )
    script = step["run"]
    pinned_sha = "021ec67ef580c83a88402a1574e27ea34db14dde"
    assert pinned_sha in script, "Workflow pin changed; update this fixture"
    assert step["if"] == "${{ hashFiles('tests/test_verifier_4422_audit.py') != '' }}"
    inventory_pin = "5b1c6424716c413871d4eda7f6a125fa070e097f"
    source = tmp_path / "source.git"
    checkout = tmp_path / "checkout"
    main_only_checkout = tmp_path / "main-only-checkout"
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Regression fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "Regression fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        "GITHUB_REF": "refs/pull/1/merge",
    }

    def git(
        cwd: Path, *args: str, input: str | None = None, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=env,
            input=input,
            text=True,
            capture_output=True,
            check=check,
            timeout=20,
        )

    git(tmp_path, "init", "--bare", "--initial-branch=main", str(source))
    tree = git(source, "mktree", input="").stdout.strip()

    def commit(day: int, *parents: str) -> str:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"2026-10-{day}T12:00:00Z"
        parent_args = [arg for parent in parents for arg in ("-p", parent)]
        return git(source, "commit-tree", tree, *parent_args, input=f"day {day}\n").stdout.strip()

    root = commit(16)
    inventory_sha = commit(17, root)
    pin = commit(18, inventory_sha)
    main = commit(19, pin)
    feature = commit(20, pin)
    merge = commit(21, main, feature)
    git(source, "update-ref", "refs/heads/main", main)
    git(source, "update-ref", env["GITHUB_REF"], merge)

    def shallow_checkout(path: Path) -> None:
        git(tmp_path, "init", "--initial-branch=main", str(path))
        git(path, "remote", "add", "origin", source.as_uri())
        git(path, "fetch", "--depth=1", "origin", env["GITHUB_REF"])
        git(path, "checkout", "--detach", "FETCH_HEAD")

    shallow_checkout(checkout)

    before = git(checkout, "merge-base", "--is-ancestor", pin, "origin/main", check=False)
    assert before.returncode == 128, before.stderr
    print(f"before (depth 1): pinned ancestry exit {before.returncode}: {before.stderr.strip()}")
    shallow_checkout(main_only_checkout)
    git(
        main_only_checkout,
        "fetch",
        "--no-tags",
        "--shallow-since=2026-10-17T00:00:00Z",
        "origin",
        "main",
    )
    git(main_only_checkout, "merge-base", "--is-ancestor", pin, "origin/main")
    main_only = git(main_only_checkout, "merge-base", "--is-ancestor", pin, "HEAD", check=False)
    assert main_only.returncode == 1, main_only.stderr
    print(f"before (main-only fetch): checkout ancestry exit {main_only.returncode}")

    script = script.replace(pinned_sha, pin).replace(inventory_pin, inventory_sha)
    completed = subprocess.run(
        ["bash", "-c", script],
        cwd=checkout,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    git(checkout, "merge-base", "--is-ancestor", pin, "origin/main")
    git(checkout, "merge-base", "--is-ancestor", pin, "HEAD")
    print("after (workflow fetch): pinned and checkout ancestry exit 0")

    # Simulate refs/pull/1/merge advancing after a depth-1 checkout (e.g. a
    # reopened PR or rerun after main moves): HEAD must still be deepened.
    moved_checkout = tmp_path / "moved-checkout"
    shallow_checkout(moved_checkout)
    newer_main = commit(22, main)
    newer_merge = commit(23, newer_main, feature)
    git(source, "update-ref", "refs/heads/main", newer_main)
    git(source, "update-ref", env["GITHUB_REF"], newer_merge)

    moved = subprocess.run(
        ["bash", "-c", script],
        cwd=moved_checkout,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert moved.returncode == 0, moved.stderr
    git(moved_checkout, "merge-base", "--is-ancestor", pin, "origin/main")
    git(moved_checkout, "merge-base", "--is-ancestor", inventory_sha, merge)
    assert git(moved_checkout, "rev-parse", "HEAD").stdout.strip() == merge

    disconnected = commit(24, root)
    git(source, "update-ref", env["GITHUB_REF"], disconnected)
    disconnected_checkout = tmp_path / "disconnected-checkout"
    shallow_checkout(disconnected_checkout)
    rejected = subprocess.run(
        ["bash", "-c", script],
        cwd=disconnected_checkout,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert rejected.returncode == 1, rejected.stderr
    assert f"Unable to establish #4426 inventory ancestry for exact checkout {disconnected}" in (
        rejected.stdout
    )


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


@pytest.mark.parametrize(
    "versions,single,primary,expected",
    [
        ("[]", "", "", "3.14"),
        ("[]", "3.12", "", "3.12"),
        ("[]", "3.12", "3.12", "3.12"),
        ('["3.12", "3.13"]', "", "", "3.12"),
        ('["3.13", "3.14"]', "", "3.14", "3.14"),
    ],
)
def test_validated_primary_is_shared_by_setup_caches_and_artifacts(
    tmp_path, versions, single, primary, expected
):
    output = tmp_path / "outputs"
    result = subprocess.run(
        [sys.executable, "-c", _validate_inputs_script()],
        env={
            **os.environ,
            "PYTHON_VERSIONS": versions,
            "PYTHON_VERSION": single,
            "PRIMARY_IN": primary,
            "GITHUB_OUTPUT": str(output),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert output.read_text() == f"primary_python={expected}\n"
    workflow = _load_workflow()
    for job_id in ("lint-format", "lint-ruff", "typecheck-mypy"):
        job = workflow["jobs"][job_id]
        assert job["needs"] == "validate-inputs"
        setup = next(step for step in job["steps"] if step.get("name") == "Set up Python")
        assert "needs.validate-inputs.outputs.primary_python" in setup["with"]["python-version"]
    tests = workflow["jobs"]["tests"]
    assert "max-parallel" not in tests["strategy"]
    assert tests["strategy"]["fail-fast"] is False
    pytest_step = next(
        step for step in tests["steps"] if step.get("name") == "Pytest (unit tests with coverage)"
    )
    assert '"-n" "${PYTEST_WORKERS}" "--dist=loadgroup"' in pytest_step["run"]


@pytest.mark.parametrize("workers", ["0", "-1", "four"])
def test_validate_inputs_rejects_invalid_worker_requests(workers):
    result = subprocess.run(
        [sys.executable, "-c", _validate_inputs_script()],
        env={"PYTEST_WORKERS": workers},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "pytest-workers must be auto or a positive integer" in result.stdout


@pytest.mark.parametrize(
    "versions,primary",
    [
        ("[]", "3.13\ninjected=value"),
        ('["3.13\\r\\ninjected=value"]', ""),
        ('["3.13\\u0000"]', ""),
    ],
)
def test_primary_output_rejects_control_characters(tmp_path, versions, primary):
    output = tmp_path / "outputs"
    result = subprocess.run(
        [sys.executable, "-c", _validate_inputs_script()],
        env={"PYTHON_VERSIONS": versions, "PRIMARY_IN": primary, "GITHUB_OUTPUT": str(output)},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "must not contain CR, LF or NUL" in result.stdout
    assert not output.exists()


@pytest.mark.parametrize(
    "versions,single,primary",
    [
        ('["3.13", "3.14"]', "", "3.12"),
        ("[]", "3.12", "3.13"),
    ],
)
def test_primary_output_rejects_a_runtime_outside_the_selected_matrix(
    tmp_path, versions, single, primary
):
    output = tmp_path / "outputs"
    result = subprocess.run(
        [sys.executable, "-c", _validate_inputs_script()],
        env={
            "PYTHON_VERSIONS": versions,
            "PYTHON_VERSION": single,
            "PRIMARY_IN": primary,
            "GITHUB_OUTPUT": str(output),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "primary-python-version must be one of the selected Python runtimes" in result.stdout
    assert not output.exists()


@pytest.mark.parametrize(
    "upstream,workflow_cancelled,expected",
    [
        ("success", False, True),
        ("failure", False, True),
        ("cancelled", False, True),
        ("success", True, False),
        ("failure", True, False),
        ("cancelled", True, False),
    ],
)
def test_logs_summary_preserves_failures_but_releases_cancelled_workflows(
    upstream, workflow_cancelled, expected
):
    condition = _load_workflow()["jobs"]["logs_summary"]["if"]
    expression = condition.removeprefix("${{").removesuffix("}}").strip()
    # Execute the authored status-function expression with Actions status values.
    # success()/failure() also catch a regression to ordinary success-only gating.
    script = """
const vm = require('node:vm');
const [expression, upstream, cancelled] = process.argv.slice(1);
const result = vm.runInNewContext(expression, {
  always: () => true,
  cancelled: () => cancelled === 'true',
  success: () => upstream === 'success',
  failure: () => upstream === 'failure',
});
process.stdout.write(JSON.stringify(result));
"""
    result = subprocess.run(
        ["node", "-e", script, expression, upstream, json.dumps(workflow_cancelled)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout) is expected


def test_test_job_temp_storage_is_scoped_and_effective_before_python_starts() -> None:
    workflow = _load_workflow()
    assert "TMPDIR" not in workflow.get("env", {})
    for name, job in workflow["jobs"].items():
        if name != "tests":
            assert "TMPDIR" not in job.get("env", {}), name
    job = workflow["jobs"]["tests"]
    assert "TMPDIR" not in job["env"]
    first = job["steps"][0]
    assert first["id"] == "test-temp"
    assert first["working-directory"] == "${{ runner.temp }}"
    assert "TMPDIR=%s" in first["run"] and '"$GITHUB_ENV"' in first["run"]
    # A late step override must not send pytest or its child tools back to /tmp.
    assert all("TMPDIR" not in step.get("env", {}) for step in job["steps"])


@pytest.mark.parametrize("apply_job_env", [True, False])
def test_fresh_pytest_and_nested_tempfile_honor_job_temp_storage(
    tmp_path: Path, apply_job_env: bool
) -> None:
    first = _load_workflow()["jobs"]["tests"]["steps"][0]
    runner_temp = tmp_path / "runner owned temp"
    runner_temp.mkdir()
    github_env = tmp_path / "github-env"
    setup = subprocess.run(
        ["bash", "-e", "-c", first["run"]],
        cwd=runner_temp,
        env={**os.environ, "RUNNER_TEMP": str(runner_temp), "GITHUB_ENV": str(github_env)},
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert setup.returncode == 0, setup.stdout + setup.stderr
    assert github_env.read_text() == f"TMPDIR={runner_temp}\n"
    case = tmp_path / "case"
    case.mkdir()
    (case / "test_temp_route.py").write_text(
        "import os, pathlib, subprocess, sys, tempfile\n"
        "def test_effective_temp(tmp_path):\n"
        "    expected = pathlib.Path(os.environ['EXPECTED_RUNNER_TEMP']).resolve()\n"
        "    assert pathlib.Path(tempfile.gettempdir()).resolve() == expected, 'wrong-first-tempfile-location'\n"
        "    assert tmp_path.resolve().is_relative_to(expected), 'wrong-pytest-temp-location'\n"
        "    nested = subprocess.check_output([sys.executable, '-c', 'import tempfile; print(tempfile.gettempdir())'], text=True).strip()\n"
        "    assert pathlib.Path(nested).resolve() == expected, 'wrong-child-temp-location'\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    for key in ("TMPDIR", "TEMP", "TMP", "PYTEST_DEBUG_TEMPROOT", "PYTEST_ADDOPTS"):
        env.pop(key, None)
    env.update(
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        EXPECTED_RUNNER_TEMP=str(runner_temp),
    )
    if apply_job_env:
        key, value = github_env.read_text().rstrip("\n").split("=", 1)
        env[key] = value
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--confcutdir", str(case), str(case)],
        cwd=case,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if apply_job_env:
        assert result.returncode == 0, result.stdout + result.stderr
        assert "1 passed" in result.stdout
    else:
        # Causal counterfactual: removing the job environment fails before the
        # fixture and nested-tool checks can falsely certify the selected disk.
        assert result.returncode == 1, result.stdout + result.stderr
        assert "wrong-first-tempfile-location" in result.stdout


@pytest.mark.parametrize(
    ("case", "report", "require_measured", "coverage"),
    [
        ("missing", None, True, None),
        ("invalid-json", "{", True, None),
        ("no-measurement", "{}", True, None),
        ("nonfinite", '{"totals":{"percent_covered":NaN}}', True, None),
        ("boolean", '{"totals":{"percent_covered":false}}', True, None),
        ("measured-zero", '{"totals":{"percent_covered":0},"files":{}}', True, 0.0),
        ("legacy-missing", None, False, 0.0),
    ],
    ids=lambda value: value if isinstance(value, str) and value.isidentifier() else None,
)
def test_opt_in_trend_rejects_unmeasured_reports(
    tmp_path: Path,
    case: str,
    report: str | None,
    require_measured: bool,
    coverage: float | None,
) -> None:
    steps = _load_workflow()["jobs"]["tests"]["steps"]
    generate = next(s for s in steps if s.get("name") == "Generate coverage trend summary")
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "coverage_trend.py").symlink_to(Path("tools/coverage_trend.py").resolve())
    if report is not None:
        (tmp_path / "coverage.json").write_text(report, encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python").symlink_to(sys.executable)
    outputs = tmp_path / "outputs"
    outputs.touch()
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", generate["run"]],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
            "COVERAGE_MIN": "70",
            "REQUIRE_MEASURED_COVERAGE_TREND": str(require_measured).lower(),
            "GITHUB_WORKSPACE": str(tmp_path),
            "WORKSPACE_ROOT": str(tmp_path),
            "PROJECT_ROOT": str(tmp_path),
            "GITHUB_OUTPUT": str(outputs),
            "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
        },
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    trend = tmp_path / "coverage-trend.json"
    if coverage is None:
        assert not trend.exists(), case
        assert "not measured" in result.stdout
    else:
        assert json.loads(trend.read_text(encoding="utf-8"))["current"] == coverage
    assert ("measured=true" in outputs.read_text(encoding="utf-8")) == (
        require_measured and coverage is not None
    )


def test_integration_full_coverage_owns_the_measured_trend() -> None:
    option = "require-measured-coverage-trend"
    workflow = _load_workflow()
    assert _workflow_call_defaults(workflow)[option] is False
    template = Path("templates/integration-repo/.github/workflows/ci.yml")
    jobs = yaml.safe_load(template.read_text(encoding="utf-8"))["jobs"]
    assert jobs["full-coverage"]["with"]["enable-soft-gate"] is True
    assert jobs["full-coverage"]["with"][option] is True
    assert jobs["full-coverage"]["with"]["artifact-prefix"] == "full-"
    for role in ("basic", "typecheck-only"):
        assert jobs[role]["with"]["enable-soft-gate"] is False
        assert option not in jobs[role]["with"]

    steps = workflow["jobs"]["tests"]["steps"]
    starts = next(i for i, step in enumerate(steps) if step.get("id") == "coverage_trend")
    trend_steps = steps[starts : starts + 6]
    assert all(
        "matrix.python-version == env.PRIMARY_PYTHON_VERSION" in s["if"] for s in trend_steps
    )
    for step in trend_steps[1:]:
        assert TREND_MEASUREMENT_CONDITION in step["if"]

    inputs = {**_workflow_call_defaults(workflow), **jobs["full-coverage"]["with"]}
    by_name = {step["name"]: step for step in steps if "name" in step}
    coverage_condition = (
        "inputs.coverage && (inputs['coverage-python-version'] == '' || "
        "inputs['coverage-python-version'] == matrix.python-version)"
    )
    payloads = {"3.13": "true", "3.14": "true"}
    payload_names = {"3.13": ["full-coverage-3.13-1"], "3.14": ["full-coverage-3.14-1"]}
    args = (by_name, inputs, "3.14", payloads, coverage_condition)
    assert _configured_artifact_names(*args) == payload_names
    assert _configured_artifact_names(*args, trend_measured=True) == {
        **payload_names,
        "3.14": [
            "full-coverage-3.14-1",
            "full-coverage-summary",
            "full-coverage-trend",
            "full-coverage-trend-history",
        ],
    }


def test_integration_coverage_helpers_ship_through_both_existing_paths(tmp_path: Path) -> None:
    from scripts import publish_integration_sync
    from scripts.sync_integration_manifest_subset import apply_subset, select_copy_sources
    from tools.integration_repo import render_integration_repo

    helpers = ("tools/coverage_trend.py", "scripts/coverage_history_append.py")
    fresh = render_integration_repo(tmp_path / "fresh")
    manifest = yaml.safe_load(Path(".github/sync-manifest.yml").read_text(encoding="utf-8"))
    subset = {"scripts": [entry for entry in manifest["scripts"] if entry["source"] in helpers]}
    assert set(select_copy_sources(subset)) == set(helpers)

    workflow = yaml.safe_load(
        Path(".github/workflows/maint-69-sync-integration-repo.yml").read_text(encoding="utf-8")
    )
    checkout = next(
        step
        for step in workflow["jobs"]["sync"]["steps"]
        if step.get("name") == "Checkout Workflows delivery tree"
    )
    assert set(helpers) <= set(checkout["with"]["sparse-checkout"].split())
    delivery = publish_integration_sync.DELIVERY_PATHS
    assert all(
        any(path == name or Path(path) in Path(name).parents for path in delivery)
        for name in helpers
    )

    # Maint 69 upgrades an existing copy and materializes the other missing helper.
    existing = tmp_path / "existing"
    old_tool = existing / helpers[0]
    old_tool.parent.mkdir(parents=True)
    old_tool.write_text("# previous coverage helper\n", encoding="utf-8")
    result = apply_subset(subset, Path.cwd(), existing)
    assert result.ok and set(result.copied) == set(helpers)
    for target in (fresh, existing):
        for helper in helpers:
            disk = target / helper
            assert disk.read_bytes() == Path(helper).read_bytes()
            assert disk.stat().st_mode == Path(helper).stat().st_mode

    missing = apply_subset(subset, tmp_path / "missing-source", tmp_path / "failed")
    assert not missing.ok and set(missing.missing_sources) == set(helpers)
