import json
from pathlib import Path

import pytest
import yaml
from tools import post_ci_summary


def test_maint46_sparse_checkout_includes_post_ci_import_dependencies():
    workflow = yaml.safe_load(
        Path(".github/workflows/maint-46-post-ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["summary"]["steps"]
    checkout = next(step for step in steps if step.get("name") == "Checkout helpers")
    sparse_checkout = checkout["with"]["sparse-checkout"]

    assert "tools/post_ci_summary.py" in sparse_checkout
    assert "tools/__init__.py" in sparse_checkout
    assert "tools/ci_failure_triage.py" in sparse_checkout


def test_maint46_runs_post_ci_summary_as_importable_module():
    workflow = yaml.safe_load(
        Path(".github/workflows/maint-46-post-ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["summary"]["steps"]
    render = next(step for step in steps if step.get("name") == "Build summary body")

    assert "python -m tools.post_ci_summary" in render["run"]
    assert "python tools/post_ci_summary.py" not in render["run"]


def test_maint46_summary_reads_downloaded_gate_artifacts():
    workflow = yaml.safe_load(
        Path(".github/workflows/maint-46-post-ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["summary"]["steps"]
    download = next(step for step in steps if step.get("name") == "Download Gate artifacts")
    render = next(step for step in steps if step.get("name") == "Build summary body")

    assert render["env"]["GATE_ARTIFACTS_ROOT"] == "${{ env.ARTIFACT_ROOT }}"
    assert download["with"]["path"] == "${{ env.ARTIFACT_ROOT }}/downloads"


@pytest.mark.parametrize("artifact_kind", ["summary", "junit", "both", "none"])
def test_maint46_renderer_reads_artifacts_at_workflow_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, artifact_kind: str
):
    workflow = yaml.safe_load(
        Path(".github/workflows/maint-46-post-ci.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["summary"]
    steps = job["steps"]
    download = next(step for step in steps if step.get("name") == "Download Gate artifacts")
    render = next(step for step in steps if step.get("name") == "Build summary body")
    root = tmp_path / job["env"]["ARTIFACT_ROOT"]

    def resolve(value: str) -> Path:
        return Path(value.replace("${{ env.ARTIFACT_ROOT }}", str(root)))

    downloaded = resolve(download["with"]["path"])
    downloaded.mkdir(parents=True)
    if artifact_kind in {"summary", "both"}:
        (downloaded / "summary.json").write_text(
            json.dumps({"checks": {"type_check": {"outcome": "failure"}}}), encoding="utf-8"
        )
    if artifact_kind in {"junit", "both"}:
        (downloaded / "pytest-junit.xml").write_text(
            '<testsuite><testcase file="src/app.py"><failure message="ImportError: No module named foo">Traceback (most recent call last): ImportError: No module named foo</failure></testcase></testsuite>',
            encoding="utf-8",
        )

    output = tmp_path / "output.txt"
    monkeypatch.setenv("RUNS_JSON", "[]")
    monkeypatch.setenv("HEAD_SHA", "a" * 40)
    monkeypatch.setenv("GITHUB_REPOSITORY", "stranske/Workflows")
    monkeypatch.setenv("GATE_ARTIFACTS_ROOT", str(resolve(render["env"]["GATE_ARTIFACTS_ROOT"])))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    post_ci_summary.main()

    body = output.read_text(encoding="utf-8")
    assert ("error_type: mypy" in body) == (artifact_kind in {"summary", "both"})
    assert ("error_type: import_error" in body) == (artifact_kind in {"junit", "both"})
    if artifact_kind != "none":
        assert "blob/" + "a" * 40 + "/docs/CI_FAILURE_PLAYBOOK.md" in body


def test_maint46_gate_artifact_download_fails_open_to_metadata_summary():
    workflow = yaml.safe_load(
        Path(".github/workflows/maint-46-post-ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["summary"]["steps"]
    download = next(step for step in steps if step.get("name") == "Download Gate artifacts")
    note = next(
        step for step in steps if step.get("name") == "Note Gate artifact download limitation"
    )

    assert download["id"] == "download_gate_artifacts"
    assert download["continue-on-error"] is True
    assert note["if"] == "${{ steps.download_gate_artifacts.outcome == 'failure' }}"
    assert "artifact-only coverage detail" in note["run"]
