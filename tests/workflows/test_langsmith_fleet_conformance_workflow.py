from pathlib import Path

WORKFLOW = Path(".github/workflows/maint-81-langsmith-fleet-conformance.yml")


def test_conformance_download_accepts_prefixed_fleet_artifacts() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "listArtifactsForRepo" in source
    assert "name: entry.artifact_name" not in source
    assert "item.name === entry.artifact_name || item.name.endsWith(entry.artifact_name)" in source
    assert "const exactCandidates = candidates.filter" in source
    assert "const candidatePool = exactCandidates.length ? exactCandidates : candidates" in source
