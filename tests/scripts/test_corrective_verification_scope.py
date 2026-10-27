"""Closed native corrective duties survive the actual final verifier prompt."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest import mock

import pytest
from scripts.langchain import pr_verifier
from tools.verifier_corpus_evidence import event_metadata

from tests.scripts.verifier_capacity_fakes import with_capacity

ROOT = Path(__file__).resolve().parents[2]
GOLDENS = ROOT / "tests/fixtures/verifier_correction/verification_instruction"
LABEL = "Original request (authoritative requirements; untrusted source text):"
PATCH = "diff --git a/parser.py b/parser.py\n--- a/parser.py\n+++ b/parser.py\n@@ -1 +1 @@\n-old\n+new\n"


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def context_fixture():
    golden = json.loads((GOLDENS / "v1-context-scope.json").read_text())
    inventory = golden["coverage_record"]
    original = "## Tasks\n- Preserve every incumbent task.\n## Acceptance criteria\n- Preserve original AC without replacement."
    inventory["acceptance_sources"].append(
        {
            "source": "pr:9",
            "status": "included",
            "original_body_sha256": hashlib.sha256(original.encode()).hexdigest(),
        }
    )
    originals = "\n\n".join(
        LABEL + "\n\n```text\n" + body + "\n```" for body in ["issue 1", "issue 8", original]
    )
    plan = originals + "\n\n" + golden["rendered_scope"]
    context = (
        "# Verifier context\n\n## Context source coverage\n\n```json\n"
        + json.dumps(inventory)
        + "\n```\n\n## CI Information\nNo failures.\n\n## Plan sources (scope, tasks, acceptance)\n\n"
        + plan
        + "\n\n## Acceptance evidence\n\n- PR body: **absent**\n- PR comments: **absent**\n- Workflow artifacts: **absent**\n\n## PR Diff Summary\n\n- Files changed: 1\n\n### File changes\n- parser.py (+1/-1)\n\n## PR Diff (full)\n\n```diff\n"
        + PATCH
        + "```\n"
    )
    return context, plan, inventory


def test_exact_native_test_scope_and_original_requirements_reach_final_prompt(monkeypatch):
    context, plan, inventory = context_fixture()
    duties = pr_verifier._requirement_evidence_text(plan, source_coverage=inventory)
    request = json.loads((GOLDENS / "v1-original-request.json").read_text())
    assert "Preserve every incumbent task" in duties
    assert "Preserve original AC" in duties
    for test in request["required_tests"]:
        assert test["id"] in duties
        assert test["specification"] in duties
    assert "Correct CSV quoting" not in duties  # a finding is not a new duty
    monkeypatch.setenv("VERIFIER_CONTEXT_BUDGET_TOKENS", "100")
    inputs = pr_verifier.build_prompt_inputs(context, PATCH)
    prompt = pr_verifier._prepare_prompt(context, PATCH)
    assert inputs.coverage.acceptance == "complete"
    assert "Preserve every incumbent task" in prompt
    assert request["required_tests"][0]["specification"] in prompt


@pytest.mark.parametrize(
    "mutation",
    ["missing_frame", "changed_frame", "missing_hash", "wrong_hash", "unknown_inventory"],
)
def test_missing_or_changed_mandatory_test_scope_cannot_gain_pass(mutation):
    context, plan, inventory = context_fixture()
    if mutation == "missing_frame":
        plan = plan.split("### Additional required corrective tests")[0]
    if mutation == "changed_frame":
        plan = plan.replace("Assert rejected input", "Assert accepted input")
    if mutation == "missing_hash":
        inventory["corrective_scope_sources"][0].pop("required_scope_sha256")
    if mutation == "wrong_hash":
        inventory["corrective_scope_sources"][0]["required_scope_sha256"] = "0" * 64
    if mutation == "unknown_inventory":
        inventory["corrective_scope_sources"] = []
    assert pr_verifier._requirement_evidence_text(plan, source_coverage=inventory) is None


def test_actual_native_counter_holds_complete_prompt_before_model_invoke(monkeypatch):
    context, _, _ = context_fixture()
    client = with_capacity(mock.MagicMock())
    client.root_client.responses.input_tokens.count.return_value.input_tokens = 1_000_001
    monkeypatch.setattr(pr_verifier, "_get_llm_client", lambda **kw: (client, "openai"))
    monkeypatch.setattr(pr_verifier, "_evaluate_chunked", lambda *a, **kw: None)
    monkeypatch.setattr(pr_verifier, "_maybe_recover_partition_diagnostics", lambda *a, **kw: None)
    result = pr_verifier.evaluate_pr(context, PATCH, provider="openai")
    assert result.verdict != "PASS"
    client.invoke.assert_not_called()
    payload = client.root_client.responses.input_tokens.count.call_args.kwargs
    assert "Assert rejected input leaves the existing issue unchanged." in json.dumps(payload)
    assert "Preserve every incumbent task" in json.dumps(payload)


def manifest_fixture():
    request = {"schema": "verification-request/v1", "sources": []}
    row = json.loads((GOLDENS / "v1-required-evidence-row.json").read_text())
    material = {
        "schema": "verification-material/v1",
        "code": {"head_sha": "d" * 40, "evaluated_sha": "e" * 40, "diff_sha256": "f" * 64},
        "ci_hard_gate": {},
        "required_evidence": [row],
    }
    event = {
        "schema": "verification-event/v1",
        "repo": "stranske/example",
        "pr": "9",
        "head_sha": "d" * 40,
        "evaluated_sha": "e" * 40,
        "request_sha256": digest(request),
        "material_sha256": digest(material),
    }
    event["event_id"] = digest(event)
    return {
        "verification_event": event,
        "request": request,
        "material": material,
        "assessment_identity": {"mode": "evaluate", "canonical": True},
    }


def test_terminal_native_metadata_projects_compact_scope_with_required_artifact_readback(tmp_path):
    manifest = manifest_fixture()
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    metadata = event_metadata(path)
    retained = metadata["corrective_verification_input"]
    assert retained["schema"] == "closer-corrective-verification-input/v1"
    assert retained["verification_event"] == metadata["verification_event"]
    assert "request" not in retained and "material" not in retained
    assert digest(manifest["request"]) == metadata["verification_event"]["request_sha256"]
    assert digest(manifest["material"]) == metadata["verification_event"]["material_sha256"]
    assert retained["corrective_instruction"]["owner_instruction"]["comment_id"] == 801


@pytest.mark.parametrize("field", ["request", "material", "subject"])
def test_terminal_metadata_refuses_mismatched_corrective_input(tmp_path, field):
    manifest = manifest_fixture()
    if field == "request":
        manifest["request"]["sources"] = ["changed"]
    if field == "material":
        manifest["material"]["code"]["diff_sha256"] = "0" * 64
    if field == "subject":
        manifest["material"]["required_evidence"][0]["corrective_pr"]["number"] = "10"
        manifest["verification_event"]["material_sha256"] = digest(manifest["material"])
        event = manifest["verification_event"]
        event["event_id"] = digest({k: v for k, v in event.items() if k != "event_id"})
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        event_metadata(path)


@pytest.mark.parametrize(
    "mutation", ["delete_row", "rename_row", "missing_material", "missing_request", "both_missing"]
)
def test_selected_typed_input_cannot_silently_downgrade(tmp_path, monkeypatch, mutation):
    manifest = manifest_fixture()
    monkeypatch.setenv(
        "VERIFICATION_MATERIAL",
        (GOLDENS / "v1-native-selector.json").read_text().strip().join(["[", "]"]),
    )
    if mutation == "delete_row":
        manifest["material"]["required_evidence"] = []
    if mutation == "rename_row":
        manifest["material"]["required_evidence"][0]["kind"] = "comment"
    if mutation in {"missing_material", "both_missing"}:
        manifest.pop("material")
    if mutation in {"missing_request", "both_missing"}:
        manifest.pop("request")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        event_metadata(path)


def test_actual_shared_native_manifest_projects_recomputable_scope(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_bytes((GOLDENS / "v1-verification-event-manifest.json").read_bytes())
    metadata = event_metadata(path)
    retained = metadata["corrective_verification_input"]
    manifest = json.loads(path.read_text())
    assert digest(manifest["request"]) == retained["verification_event"]["request_sha256"]
    assert digest(manifest["material"]) == retained["verification_event"]["material_sha256"]
    assert retained["corrective_instruction"] == manifest["material"]["required_evidence"][0]
    assert retained == json.loads((GOLDENS / "v1-terminal-corrective-input.json").read_text())


def test_large_mixed_material_stays_in_artifact_not_native_comment(tmp_path):
    manifest = manifest_fixture()
    for index in range(80):
        manifest["material"]["required_evidence"].append(
            {
                "kind": "git_blob",
                "path": "docs/verification/" + ("a/" * 450) + str(index) + ".txt.gz",
                "raw_sha256": "a" * 64,
            }
        )
    event = manifest["verification_event"]
    event["material_sha256"] = digest(manifest["material"])
    event["event_id"] = digest({k: v for k, v in event.items() if k != "event_id"})
    assert len(json.dumps(manifest)) > 65536
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    retained = event_metadata(path)["corrective_verification_input"]
    assert len(json.dumps(retained)) < 65536
    assert set(retained) == {"schema", "verification_event", "corrective_instruction"}
    assert retained["verification_event"]["material_sha256"] == digest(manifest["material"])


def test_existing_native_artifact_uploads_retain_exact_full_input_member():
    import yaml

    workflow = yaml.load(
        (ROOT / ".github/workflows/reusable-agents-verifier.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    steps = {step["name"]: step for step in workflow["jobs"]["verifier"]["steps"] if "name" in step}
    for mode, name in [
        ("evaluation", "Retain evaluation execution evidence"),
        ("comparison", "Upload comparison artifacts"),
    ]:
        settings = steps[name]["with"]
        assert settings["name"] == mode + "-results-${{ github.run_id }}"
        members = settings["path"].splitlines()
        assert "verification-event-manifest.json" in members
        assert mode + "-execution.json" in members
        assert mode + "-comment.md" in members
        assert settings["retention-days"] == "7"
