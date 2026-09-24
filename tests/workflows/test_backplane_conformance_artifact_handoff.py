from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_reusable_backplane_conformance_restores_caller_reference_artifact() -> None:
    workflow = (ROOT / ".github" / "workflows" / "reusable-backplane-conformance.yml").read_text(
        encoding="utf-8"
    )

    # The contract exposes exactly one caller-configurable artifact name and
    # exactly one restore step; duplicate declarations would make the handoff
    # ambiguous even if the expected strings were still present somewhere.
    assert workflow.count("reference_artifact_name:") == 1
    assert workflow.count("name: Restore emitted reference run") == 1
    assert "reference_artifact_name:" in workflow
    assert "default: 'reference-run'" in workflow
    assert "name: Restore emitted reference run" in workflow
    assert "continue-on-error: true" in workflow
    assert "uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c" in workflow
    assert "name: ${{ inputs.reference_artifact_name }}" in workflow
    assert "path: artifacts/reference" in workflow


def test_backplane_workflows_install_required_format_checkers() -> None:
    for name in (
        "reusable-backplane-conformance.yml",
        "health-78-backplane-contract.yml",
    ):
        workflow = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert "jsonschema rfc3339-validator rfc3986-validator" in workflow


def test_reusable_backplane_conformance_binds_registry_repo_to_caller() -> None:
    workflow = (ROOT / ".github" / "workflows" / "reusable-backplane-conformance.yml").read_text(
        encoding="utf-8"
    )
    assert "CALLER_REPO: ${{ github.repository }}" in workflow
    assert "DECLARED_REPO: ${{ inputs.repo }}" in workflow
    assert 'if [ "${REPO}" != "${CALLER_REPO}" ]; then' in workflow
    assert 'ARGS=( "${RUN_JSON_PATH}"' in workflow
    assert 'ARGS+=( --manifest "${MANIFEST_PATH}" )' in workflow
