"""Opaque launch correlation never changes event identity or verdict authority."""

import json
from pathlib import Path

import pytest
import yaml
from tools.verifier_corpus_evidence import event_metadata

ROOT = Path(__file__).resolve().parents[2]


def test_trusted_result_metadata_copies_only_typed_optional_basis(tmp_path):
    fixture = json.loads((ROOT / "tests/fixtures/verification_event/canonical.json").read_text())
    fixture["assessment_identity"] = {"mode": "evaluate", "canonical": True}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(fixture))
    before = event_metadata(path)
    assert "verification_request_basis" not in before
    fixture["verification_request_basis"] = "e" * 64
    path.write_text(json.dumps(fixture))
    after = event_metadata(path)
    assert after["verification_request_basis"] == "e" * 64
    assert before["verification_event"] == after["verification_event"]
    for bad in ["", "E" * 64, None, 13]:
        fixture["verification_request_basis"] = bad
        path.write_text(json.dumps(fixture))
        with pytest.raises(ValueError):
            event_metadata(path)


def test_workflow_and_template_forward_basis_to_authenticated_manifest_and_markers():
    for relative in [
        ".github/workflows/agents-verifier.yml",
        "templates/consumer-repo/.github/workflows/agents-verifier.yml",
    ]:
        workflow = yaml.load((ROOT / relative).read_text(), Loader=yaml.BaseLoader)
        assert (
            workflow["on"]["workflow_dispatch"]["inputs"]["verification_request_basis"]["default"]
            == ""
        )
        call = next(
            job
            for job in workflow["jobs"].values()
            if job.get("uses", "").endswith("reusable-agents-verifier.yml@main")
        )
        assert (
            call["with"]["verification_request_basis"]
            == "${{ inputs.verification_request_basis || '' }}"
        )
    reusable = yaml.load(
        (ROOT / ".github/workflows/reusable-agents-verifier.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    assert reusable["on"]["workflow_call"]["inputs"]["verification_request_basis"]["default"] == ""
    job = reusable["jobs"]["verifier"]
    assert job["env"]["VERIFICATION_REQUEST_BASIS"] == "${{ inputs.verification_request_basis }}"
    steps = {step["name"]: step for step in job["steps"]}
    for name in ["Record verification event pending", "Record verification event terminal"]:
        assert (
            "verification_request_basis:manifest.verification_request_basis"
            in steps[name]["with"]["script"]
        )
    duplicate = steps["Correlate an already completed verification event"]
    assert duplicate["if"] == "steps.context.outputs.verification_request_correlation != ''"
    assert "withRetry(() => github.rest.issues.createComment" in duplicate["with"]["script"]
    assert "correlation_run_id !== String(context.runId)" in duplicate["with"]["script"]
    for name in ["verification_event.js", "agents_verifier_context.js"]:
        assert (ROOT / ".github/scripts" / name).read_bytes() == (
            ROOT / "templates/consumer-repo/.github/scripts" / name
        ).read_bytes()


def test_shared_fixture_preserves_unicode_canonical_bytes_and_execution_strings():
    import hashlib

    fixture = json.loads(
        (ROOT / "tests/fixtures/verification_event/request_correlation.json").read_text()
    )
    canonical = json.dumps(
        fixture["decision"], sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    assert canonical == fixture["canonical_decision"]
    assert (
        hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        == fixture["correlation"]["result_decision_sha256"]
    )
    example = fixture["unicode_canonical_example"]
    text = json.dumps(example["value"], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    assert text == example["canonical"]
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == example["sha256"]
    for field in [
        "result_run_id",
        "result_run_attempt",
        "correlation_run_id",
        "correlation_run_attempt",
    ]:
        assert isinstance(fixture["correlation"][field], str)
