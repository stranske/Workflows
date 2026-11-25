"""Exercise tests-enabled and tests-disabled handling in the authored Node workflow."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(".github/workflows/reusable-11-ci-node.yml")
NO_TEST_PACKAGE = Path(".github/actions/maint78-codex-cli/package.json")
RUNNER_COVERAGE_CASES = [
    ("jest", False, ["--runInBand"]),
    (
        "jest",
        True,
        [
            "--runInBand",
            "--coverage",
            "--coverageReporters=text",
            "--coverageReporters=json-summary",
            "--coverageReporters=cobertura",
            "--coverageReporters=lcov",
        ],
    ),
    ("vitest", False, []),
    ("vitest", True, ["--coverage"]),
]


@pytest.fixture
def test_steps() -> tuple[dict, dict]:
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["tests"]["steps"]
    test = next(step for step in steps if step.get("id") == "run-tests")
    final = next(step for step in steps if step["name"] == "Finalize check results")
    return test, final


def run_shell(step: dict, directory: Path, **extra_env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-eo", "pipefail", "-c", step["run"]],
        cwd=directory,
        env={**os.environ, **extra_env},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def run_tests(step: dict, project: Path, runner: str, coverage: bool):
    if not shutil.which("node") or not shutil.which("npm"):
        pytest.skip("Node workflow replay requires node and npm")
    return run_shell(
        step,
        project,
        PACKAGE_MANAGER="npm",
        TEST_RUNNER=runner,
        COVERAGE_ENABLED=str(coverage).lower(),
        npm_config_cache=str(project / "npm-cache"),
    )


def install_local_runner(project: Path, runner: str) -> None:
    package = project / "node_modules" / runner
    package.mkdir(parents=True)
    (package / "package.json").write_text(
        json.dumps({"name": runner, "version": "1.0.0", "bin": {runner: "cli.js"}})
    )
    executable = package / "cli.js"
    executable.write_text(
        '#!/usr/bin/env node\nconsole.log("installed runner executed");\n'
        "console.log(JSON.stringify(process.argv.slice(2)));\n"
    )
    executable.chmod(0o755)
    bins = package.parent / ".bin"
    bins.mkdir()
    (bins / runner).symlink_to(Path("..") / runner / "cli.js")


def test_real_package_without_tests_fails_without_an_installed_runner(test_steps, tmp_path):
    test, _ = test_steps
    shutil.copyfile(NO_TEST_PACKAGE, tmp_path / "package.json")
    result = run_tests(test, tmp_path, "jest", coverage=True)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "No test script in package.json" in result.stdout


@pytest.mark.parametrize(("runner", "coverage", "expected"), RUNNER_COVERAGE_CASES)
def test_missing_script_can_use_an_installed_runner(
    test_steps, tmp_path, runner, coverage, expected
):
    test, _ = test_steps
    shutil.copyfile(NO_TEST_PACKAGE, tmp_path / "package.json")
    install_local_runner(tmp_path, runner)
    result = run_tests(test, tmp_path, runner, coverage)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "installed runner executed" in result.stdout
    fallback_only = ["run"] if runner == "vitest" else []
    assert json.loads(result.stdout.splitlines()[-1]) == fallback_only + expected


@pytest.mark.parametrize(("runner", "coverage", "expected"), RUNNER_COVERAGE_CASES)
def test_project_script_keeps_runner_arguments_and_verdict(
    test_steps, tmp_path, runner, coverage, expected
):
    test, _ = test_steps
    install_local_runner(tmp_path, runner)
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "node test.cjs"}}))
    script = tmp_path / "test.cjs"
    script.write_text("console.log(JSON.stringify(process.argv.slice(2)));")
    result = run_tests(test, tmp_path, runner, coverage)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == expected

    script.write_text("console.error('original test failure'); process.exit(17);")
    result = run_tests(test, tmp_path, runner, coverage)
    assert result.returncode == 17, result.stdout + result.stderr
    assert "original test failure" in result.stderr
    assert "installed runner executed" not in result.stdout


def test_tests_disabled_preserves_skipped_verdict(test_steps, tmp_path):
    test, final = test_steps
    assert test["if"] == "${{ inputs.tests }}"
    assert run_shell(final, tmp_path, TESTS_OUTCOME="skipped").returncode == 0
    assert run_shell(final, tmp_path, TESTS_OUTCOME="failure").returncode == 1


@pytest.mark.parametrize(
    ("name", "toggle", "script", "tool", "arguments"),
    [
        ("Run ESLint", "lint", "lint", "eslint", ["."]),
        (
            "Check formatting (Prettier)",
            "format_check",
            "format:check",
            "prettier",
            ["--check", "."],
        ),
        ("TypeScript type check", "typecheck", "typecheck", "tsc", ["--noEmit"]),
    ],
)
def test_enabled_quality_check_runs_tool_or_preserves_project_verdict(
    tmp_path, name, toggle, script, tool, arguments
):
    if not shutil.which("node") or not shutil.which("npm"):
        pytest.skip("Node workflow replay requires node and npm")

    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["tests"]["steps"]
    step = next(item for item in steps if item["name"] == name)
    assert step["if"] == "${{ inputs." + toggle + " }}"
    # Run the authored configuration, including each step's fallback command.
    env = dict(step.get("env", {}), PACKAGE_MANAGER="npm", npm_config_offline="true")
    shell = dict(step, run=step["run"].replace("${{ inputs['package-manager'] }}", "npm"))
    package = tmp_path / "package.json"
    shutil.copyfile(NO_TEST_PACKAGE, package)
    missing = run_shell(shell, tmp_path, **env)
    assert missing.returncode != 0, f"{name} reported success without {tool}"

    install_local_runner(tmp_path, tool)
    fallback = run_shell(shell, tmp_path, **env)
    assert fallback.returncode == 0, fallback.stderr
    assert json.loads(fallback.stdout.splitlines()[-1]) == arguments

    package.write_text(json.dumps({"scripts": {script: "node project-check.cjs"}}))
    project_check = tmp_path / "project-check.cjs"
    for status in (23, 0):
        project_check.write_text(f"console.log('project verdict'); process.exit({status});")
        result = run_shell(shell, tmp_path, **env)
        assert result.returncode == status, result.stdout + result.stderr
        assert "project verdict" in result.stdout
        assert "installed runner executed" not in result.stdout


def test_format_check_uses_hoisted_npm_workspace_binary(tmp_path):
    if not shutil.which("node") or not shutil.which("npm"):
        pytest.skip("Node workflow replay requires node and npm")
    (tmp_path / "package.json").write_text('{"private":true,"workspaces":["packages/*"]}')
    project = tmp_path / "packages" / "child"
    project.mkdir(parents=True)
    (project / "package.json").write_text('{"name":"child","version":"1.0.0"}')
    install_local_runner(tmp_path, "prettier")

    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["tests"]["steps"]
    step = next(item for item in steps if item["name"] == "Check formatting (Prettier)")
    result = run_shell(step, project, **dict(step["env"], PACKAGE_MANAGER="npm"))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == ["--check", "."]
