from pathlib import Path

WORKFLOW = Path(".github/workflows/maint-81-langsmith-fleet-conformance.yml")


def test_conformance_download_accepts_prefixed_fleet_artifacts() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert source.count("listArtifactsForRepo") == 1
    assert source.count("name: entry.artifact_name") == 0
    assert (
        source.count("item.name === entry.artifact_name || item.name.endsWith(entry.artifact_name)")
        == 1
    )
    assert source.count("const exactCandidates = candidates.filter") == 1
    assert source.count("trusted_artifact_workflow_paths") == 1
    assert source.count("github.rest.actions.getWorkflowRun") == 1
    assert source.count("trustedWorkflowPaths.has(run.data.path)") == 1
