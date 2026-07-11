from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_reusable_backplane_conformance_restores_caller_reference_artifact() -> None:
    workflow = (ROOT / ".github" / "workflows" / "reusable-backplane-conformance.yml").read_text(
        encoding="utf-8"
    )

    assert "reference_artifact_name:" in workflow
    assert "default: 'reference-run'" in workflow
    assert "name: Restore emitted reference run" in workflow
    assert "uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c" in workflow
    assert "name: ${{ inputs.reference_artifact_name }}" in workflow
    assert "path: artifacts/reference" in workflow
