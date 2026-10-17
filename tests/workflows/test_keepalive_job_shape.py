"""Bound runner scaffolding while preserving keepalive ordering and isolation."""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = (
    ".github/workflows/agents-keepalive-loop.yml",
    "templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml",
)


def dependencies(job: dict) -> list[str]:
    needs = job.get("needs", [])
    return [needs] if isinstance(needs, str) else needs


def keepalive_chain(jobs: dict) -> set[str]:
    # Follow the actual dependencies, rather than counting a fixed list of job
    # names: splitting finish into summary + completion must increase the count.
    pending = ["finish", *(name for name in jobs if name.startswith("run-"))]
    chain: set[str] = set()
    while pending:
        name = pending.pop()
        if name in chain:
            continue
        chain.add(name)
        pending.extend(dependencies(jobs[name]))
    return {name for name in chain if not name.startswith("run-")}


@pytest.fixture(params=WORKFLOWS, ids=WORKFLOWS)
def workflow(request):
    path = request.param
    return path, yaml.safe_load((ROOT / path).read_text())["jobs"]


def test_keepalive_job_and_api_setup_budget(workflow):
    path, jobs = workflow
    chain = keepalive_chain(jobs)
    assert len(chain) <= 4, f"{path}: {len(chain)} non-run keepalive jobs: {sorted(chain)}"
    setups = sum(
        step.get("uses", "") == "./.github/actions/setup-api-client"
        for name in chain
        for step in jobs[name].get("steps", [])
    )
    assert setups <= 4, f"{path}: {setups} keepalive setup-api-client calls"
    # Count setup calls across the whole file, including the root's alternate
    # review branch and the consumer hub's untouched non-keepalive jobs.
    assert (
        sum(
            step.get("uses", "") == "./.github/actions/setup-api-client"
            for job in jobs.values()
            for step in job.get("steps", [])
        )
        <= 4
    ), path


def test_preflight_precedes_running_and_authority_finalization(workflow):
    path, jobs = workflow
    assert "mark-running" not in jobs, path
    steps = jobs["preflight"]["steps"]
    names = [step.get("name") for step in steps]
    assert names.index("Check secrets") < names.index("Update summary with running status"), path
    assert (
        names.index("Update summary with running status")
        < names.index("Finalize authority challenge after mark-running")
        < names.index("Release prepared challenge after mark-running failure")
    ), path
    cleanup = next(
        s for s in steps if s.get("name") == "Release prepared challenge after mark-running failure"
    )
    assert "always() && (failure() || cancelled())" in cleanup["if"], path
    for name, job in jobs.items():
        if name.startswith("run-"):
            assert "preflight" in dependencies(job), path
            assert "always()" not in job.get("if", ""), path


def test_finish_reconciles_before_measuring_and_records_after_summary_failure(workflow):
    path, jobs = workflow
    assert "summary" not in jobs and "record-keepalive-completion" not in jobs, path
    finish = jobs["finish"]
    assert "always()" in finish["if"], path
    steps = finish["steps"]
    names = [s.get("name") for s in steps]
    assert names.index("Auto-reconcile task checkboxes") < names.index(
        "Update summary comment"
    ), path
    assert (
        names.index("Update summary comment")
        < names.index("Measure runner productivity")
        < names.index("Record completion")
    ), path
    for name in ("Measure runner productivity", "Record completion"):
        condition = next(s["if"] for s in steps if s.get("name") == name)
        assert "always()" in condition and "dispatch_should_run == 'true'" in condition, path
        for runner in (name for name in jobs if name.startswith("run-")):
            assert f"needs.{runner}.result != 'skipped'" in condition, path
    record = next(s for s in steps if s.get("name") == "Record completion")
    assert "steps.productivity.outcome == 'success'" in record["if"], path
    for action in (
        "actions/checkout@",
        "actions/setup-node@",
        "./.github/actions/setup-api-client",
    ):
        assert sum(s.get("uses", "").startswith(action) for s in steps) == 1, (path, action)


def test_root_acceptance_gate_remains_isolated_before_privileged_running():
    jobs = yaml.safe_load((ROOT / WORKFLOWS[0]).read_text())["jobs"]
    gate = jobs["acceptance-gates"]
    assert gate["permissions"] == {"contents": "read"}
    assert "secrets." not in str(gate)
    assert "setup-api-client" not in str(gate)
    assert "acceptance-gates" in dependencies(jobs["preflight"])
    assert dependencies(gate) == ["evaluate"]
    for step in gate["steps"]:
        if step.get("uses", "").startswith("actions/checkout@"):
            assert step["with"]["persist-credentials"] is False


@pytest.mark.parametrize(
    "dispatch,runner_result,measurement,expected_measure,expected_record",
    [
        ("true", "success", "success", True, True),
        ("true", "failure", "success", True, True),
        ("true", "cancelled", "success", True, True),
        ("true", "skipped", "success", False, False),
        ("false", "success", "success", False, False),
        ("true", "success", "failure", True, False),
    ],
)
def test_completion_predicates_after_summary_failure(
    workflow, dispatch, runner_result, measurement, expected_measure, expected_record
):
    path, jobs = workflow
    steps = {step.get("name"): step for step in jobs["finish"]["steps"]}

    def condition_value(name):
        condition = steps[name]["if"]
        # Evaluate only the small, boolean workflow expression under test.
        # A preceding summary failure must not introduce a success() dependency.
        condition = condition.replace("always()", "True").replace("success()", "False")
        condition = condition.replace("needs.evaluate.outputs.dispatch_should_run", repr(dispatch))
        condition = re.sub(
            r"needs\.(run-[\w-]+)\.result",
            lambda match: repr(runner_result if match[1] == "run-codex" else "skipped"),
            condition,
        )
        condition = condition.replace("steps.productivity.outcome", repr(measurement))
        condition = condition.replace("&&", " and ").replace("||", " or ")
        return eval(" ".join(condition.split()), {"__builtins__": {}})

    assert condition_value("Measure runner productivity") is expected_measure, path
    assert condition_value("Record completion") is expected_record, path
