from pathlib import Path

import yaml


def test_model_eval_pilot_runs_as_importable_module() -> None:
    root = Path(__file__).resolve().parents[2]
    workflow = yaml.safe_load(
        (root / ".github/workflows/maint-78-model-evaluation-pilot.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["pilot"]["steps"]
    pilot = next(step for step in steps if step.get("name") == "Run paired 30-case pilot")
    summary = next(step for step in steps if step.get("name") == "Summarize pilot")
    upload = next(step for step in steps if "actions/upload-artifact@" in step.get("uses", ""))

    assert pilot["run"].count("python -m tools.run_model_eval_pilot") == 1
    assert pilot["run"].count("--extra langchain") == 1
    assert pilot["env"]["GH_TOKEN"] == "${{ secrets.OWNER_PR_PAT }}"
    assert pilot["env"]["GITHUB_TOKEN"] == "${{ github.token }}"
    assert "python tools/run_model_eval_pilot.py" not in pilot["run"]
    assert summary["if"] == "always()"
    assert "if [ ! -f pilot-results.json ]" in summary["run"]
    assert upload["if"] == "always()"
    assert upload["with"]["if-no-files-found"] == "warn"


def test_auto_dispatch_maint77_chains_to_maint78_on_catalog_drift() -> None:
    root = Path(__file__).resolve().parents[2]
    workflow = yaml.safe_load(
        (root / ".github/workflows/maint-77-model-registry-freshness.yml").read_text(encoding="utf-8")
    )
    dispatch_job = workflow["jobs"]["dispatch-evaluation-pilot"]
    assert "discovery_drift == 'true'" in dispatch_job["if"]
    needs = dispatch_job["needs"]
    assert needs == ["freshness"] or needs == "freshness"
    steps = dispatch_job["steps"]
    refresh = next(step for step in steps if step.get("name") == "Refresh pilot candidates from registry")
    assert "tools.refresh_model_eval_candidates --write" in refresh["run"]
    dispatch = next(
        step for step in steps if step.get("name") == "Dispatch evaluation pilot on catalog drift"
    )
    script = dispatch["with"]["script"]
    assert "maint-78-model-evaluation-pilot.yml" in script
    assert "createWorkflowDispatch" in script
    assert dispatch["with"]["github-token"] == "${{ secrets.GITHUB_TOKEN }}"


def test_corpus_decision_publisher_uses_evaluated_context_identity():
    root = Path(__file__).resolve().parents[2]
    workflow = yaml.safe_load((root / ".github/workflows/reusable-agents-verifier.yml").read_text())
    steps = next(job["steps"] for job in workflow["jobs"].values() if "steps" in job)
    publish = next(step for step in steps if step.get("name") == "Post comparison report comment")
    assert publish["env"]["PR_HEAD_SHA"] == "${{ steps.context.outputs.pr_head_sha }}"
    assert publish["env"]["EVALUATED_SHA"] == "${{ steps.context.outputs.target_sha }}"
    assert publish["env"]["CI_FAILED"] == "${{ steps.context.outputs.ci_failed }}"
    assert "python .workflows-lib/tools/verifier_corpus_evidence.py" in publish["run"]
    assert publish["run"].index("tools/verifier_corpus_evidence.py") < publish["run"].index(
        "gh pr comment"
    )
