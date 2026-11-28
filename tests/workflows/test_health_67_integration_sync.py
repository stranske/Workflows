"""Exercise the published Health 67 CI comparison without any GitHub writes."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/health-67-integration-sync-check.yml"
SYNC_WORKFLOW = ROOT / ".github/workflows/maint-69-sync-integration-repo.yml"
CI = Path(".github/workflows/ci.yml")
VERSIONS = Path(".github/workflows/autofix-versions.env")

requires_yq_jq = pytest.mark.skipif(
    not (shutil.which("yq") and shutil.which("jq")), reason="Health 67 uses the runner's yq and jq"
)


def _run_step(tmp_path: Path, step_id: str) -> tuple[str, str]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["check-sync"]["steps"]
    script = next(step["run"] for step in steps if step.get("id") == step_id)
    output = tmp_path / f"outputs-{step_id}"
    output.touch()
    summary = tmp_path / f"summary-{step_id}"
    subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", script],
        cwd=tmp_path,
        env={
            **os.environ,
            "GITHUB_OUTPUT": str(output),
            "GITHUB_STEP_SUMMARY": str(summary),
        },
        check=True,
        timeout=10,
    )
    return output.read_text(encoding="utf-8"), summary.read_text(encoding="utf-8")


def _compare_ci(tmp_path, template, actual):
    for relative, text in (
        (Path("workflows/templates/integration-repo") / CI, template),
        (Path("integration-tests") / CI, actual),
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")

    return _run_step(tmp_path, "compare-ci")


@pytest.fixture
def template():
    return (ROOT / "templates/integration-repo" / CI).read_text(encoding="utf-8")


@pytest.fixture
def receiver(template):
    return template.replace(
        "__WORKFLOW_REF__", "stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main"
    )


@requires_yq_jq
def test_health_67_accepts_matching_prefixes_and_unprefixed_job(tmp_path, template, receiver):
    jobs = yaml.safe_load(receiver)["jobs"]
    assert "artifact-prefix" not in jobs["notify-failure"].get("with", {})
    output, summary = _compare_ci(
        tmp_path, template, receiver.replace("artifact-prefix: basic-", "artifact-prefix: 'basic-'")
    )
    assert not output
    assert "Artifact prefixes match by job" in summary


@requires_yq_jq
def test_health_67_detects_job_structure_drift(tmp_path, template, receiver):
    extra_job = receiver + (
        "\n  lint-only:\n"
        "    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main\n"
        "    with:\n"
        "      artifact-prefix: lint-\n"
    )
    output, summary = _compare_ci(tmp_path, template, extra_job)
    assert "drift=true\n" in output
    assert "Job structure differs" in summary
    assert "Artifact prefixes differ by job" in summary


@requires_yq_jq
@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        ("artifact-prefix: basic-", "# artifact-prefix: basic-", '["basic","basic-"]'),
        (
            "artifact-prefix: full-",
            "artifact-prefix: wrongly-routed-",
            '["full-coverage","wrongly-routed-"]',
        ),
        ("artifact-prefix: typecheck-", "artifact-prefix: ''", '["typecheck-only","typecheck-"]'),
    ],
)
def test_health_67_detects_prefix_drift_by_job(
    tmp_path, template, receiver, before, after, expected
):
    assert receiver.count(before) == 1
    output, summary = _compare_ci(tmp_path, template, receiver.replace(before, after))
    assert output == "drift=true\n"
    assert "Artifact prefixes differ by job" in summary
    assert expected in summary


@requires_yq_jq
def test_health_67_detects_swapped_prefixes(tmp_path, template, receiver):
    swapped = re.sub(
        r"artifact-prefix: (basic-|full-)",
        lambda match: "artifact-prefix: " + {"basic-": "full-", "full-": "basic-"}[match[1]],
        receiver,
    )
    output, summary = _compare_ci(tmp_path, template, swapped)
    assert output == "drift=true\n"
    assert '["basic","full-"]' in summary
    assert '["full-coverage","basic-"]' in summary


@requires_yq_jq
def test_health_67_preserves_missing_template_prefix_guard(tmp_path, template, receiver):
    no_prefixes = re.sub(r"^      artifact-prefix: .*\n", "", template, flags=re.M)
    assert template != no_prefixes
    output, summary = _compare_ci(tmp_path, no_prefixes, receiver)
    assert output == "drift=true\n"
    assert "Template missing artifact-prefix" in summary


@requires_yq_jq
def test_health_67_detects_prefix_on_unexpected_job(tmp_path, template, receiver):
    new_route = receiver.replace(
        "  notify-failure:\n", "  notify-failure:\n    with:\n      artifact-prefix: unexpected-\n"
    )
    output, summary = _compare_ci(tmp_path, template, new_route)
    assert output == "drift=true\n"
    assert '["notify-failure","unexpected-"]' in summary


@requires_yq_jq
@pytest.mark.parametrize(
    ("after", "expected_error"),
    [
        ("artifact-prefix: false", "Expected string artifact prefixes"),
        ("artifact-prefix: [", "Expected one jobs mapping"),
    ],
)
def test_health_67_fails_on_unusable_prefix_data(
    tmp_path, template, receiver, capfd, after, expected_error
):
    with pytest.raises(subprocess.CalledProcessError):
        _compare_ci(tmp_path, template, receiver.replace("artifact-prefix: basic-", after))
    assert expected_error in capfd.readouterr().err


@requires_yq_jq
def test_health_67_fails_on_multiple_yaml_documents(tmp_path, template, receiver, capfd):
    with pytest.raises(subprocess.CalledProcessError):
        _compare_ci(tmp_path, template, receiver + "\n---\njobs: {}\n")
    assert "Expected one jobs mapping" in capfd.readouterr().err


def test_health_67_version_and_input_checks_pass_for_current_templates(tmp_path, receiver):
    canonical_versions = (ROOT / VERSIONS).read_text(encoding="utf-8")
    template_versions = (ROOT / "templates/integration-repo" / VERSIONS).read_text(encoding="utf-8")
    for relative, text in (
        (Path("workflows") / VERSIONS, canonical_versions),
        (Path("workflows/templates/integration-repo") / VERSIONS, template_versions),
        (Path("integration-tests") / VERSIONS, canonical_versions),
        (Path("integration-tests") / CI, receiver),
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    versions_out, versions_summary = _run_step(tmp_path, "compare-versions")
    inputs_out, inputs_summary = _run_step(tmp_path, "compare-inputs")
    assert versions_out == ""
    assert inputs_out == ""
    assert "Versions in sync" in versions_summary
    assert "All input names valid" in inputs_summary


@pytest.mark.parametrize("drifted_target", ["template", "actual"])
def test_health_67_detects_version_drift(tmp_path, drifted_target):
    canonical_versions = (ROOT / VERSIONS).read_text(encoding="utf-8")
    drifted_versions = re.sub(
        r"^RUFF_VERSION=.*$", "RUFF_VERSION=0.0.0", canonical_versions, flags=re.M
    )
    assert drifted_versions != canonical_versions

    template_text = drifted_versions if drifted_target == "template" else canonical_versions
    actual_text = drifted_versions if drifted_target == "actual" else canonical_versions
    for relative, text in (
        (Path("workflows") / VERSIONS, canonical_versions),
        (Path("workflows/templates/integration-repo") / VERSIONS, template_text),
        (Path("integration-tests") / VERSIONS, actual_text),
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    output, summary = _run_step(tmp_path, "compare-versions")
    assert output == "drift=true\n"
    assert "Version drift detected" in summary


@pytest.mark.parametrize(
    ("invalid_line", "expected_hint"),
    [
        ("      enable-mypy: true\n", "enable-mypy(should be typecheck)"),
        ("      enable-coverage: true\n", "enable-coverage(should be coverage)"),
        ("      coverage-threshold: 80\n", "coverage-threshold(should be coverage-min)"),
    ],
)
def test_health_67_detects_invalid_inputs(tmp_path, receiver, invalid_line, expected_hint):
    path = tmp_path / "integration-tests" / CI
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(receiver + invalid_line, encoding="utf-8")

    output, summary = _run_step(tmp_path, "compare-inputs")
    assert output == "drift=true\n"
    assert expected_hint in summary


def test_health_67_runs_after_maint_69_instead_of_racing_push_to_main():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    sync_workflow = yaml.safe_load(SYNC_WORKFLOW.read_text(encoding="utf-8"))
    triggers = workflow.get("on") or workflow.get(True)

    assert "push" not in triggers
    assert "pull_request" in triggers
    assert "repository_dispatch" in triggers
    assert "schedule" in triggers
    assert "workflow_dispatch" in triggers

    workflow_run = triggers["workflow_run"]
    assert workflow_run["workflows"] == [sync_workflow["name"]]
    assert workflow_run["types"] == ["completed"]

    job_if = " ".join(str(workflow["jobs"]["check-sync"].get("if", "")).split())
    assert "github.event_name != 'workflow_run'" in job_if
    assert "github.event.workflow_run.conclusion == 'success'" in job_if
    assert "github.event.workflow_run.head_branch == 'main'" in job_if
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in job_if
    assert "zizmor: ignore[dangerous-triggers]" in WORKFLOW.read_text(encoding="utf-8")


def test_health_67_drift_issue_steps_never_mutate_issues_on_pull_requests():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = {step["name"]: step for step in workflow["jobs"]["check-sync"]["steps"]}

    close_cond = str(steps["Close resolved drift issue"]["if"])
    create_step = steps["Create drift issue"]
    create_cond = " ".join(str(create_step["if"]).split())

    assert "github.event_name != 'pull_request'" in close_cond
    assert "!cancelled() && github.event_name != 'pull_request' && (" in create_cond
    assert create_cond.rstrip(" }").endswith(")")

    script = str(create_step["with"]["script"])
    assert "maint-69-sync-integration-repo.yml" in script
    assert "maint-65-sync-label-docs.yml" not in script
