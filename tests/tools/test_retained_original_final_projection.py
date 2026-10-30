"""Versioned original-final revalidation; synthetic native origins remain test-only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.langchain import pr_verifier as verifier
from tools import verifier_event_recovery as recovery
from tools.verifier_corpus_evidence import admitted_decision

from tests.tools.test_retained_verification_recovery import setup_case, write_archive

PRODUCER = "5e8f7a842231f16d8f5ba3ae1a48ed7625afa2feafe774963cdba066196fd0b8"
FINAL = Path(__file__).parents[1] / "fixtures/verifier-original-final/opus-canary984-final.txt"


def failed_row():
    return verifier.EvaluationResult(
        verdict="CONCERNS",
        provider_used="anthropic",
        model="m",
        used_llm=True,
        raw_content=FINAL.read_text(),
        error=recovery._ORIGINAL_PARSE_ERROR + " retained repair refusal metadata",
        input_coverage={"sufficient": True},
    ).model_dump(mode="json")


def setup_projection(tmp_path, monkeypatch):
    origin, blobs, stem = setup_case(tmp_path, monkeypatch)
    origin["validator_sha256"] = PRODUCER
    origin["recovery_key"] = recovery._sha(
        recovery._canonical(
            {
                "schema": "retained-revalidation-key/v1",
                "event_id": origin["verification_event"]["event_id"],
                "assessment": origin["assessment_identity"],
                "selector": {"run_id": 10, "run_attempt": 1, "artifact_id": 30},
            }
        )
    )
    blobs[f"{stem}.json"] = recovery._canonical(failed_row())
    old = json.loads(blobs[f"{stem}-execution.json"])
    old["outputs"][f"{stem}.json"].update(
        sha256=recovery._sha(blobs[f"{stem}.json"]), bytes=len(blobs[f"{stem}.json"])
    )
    blobs[f"{stem}-execution.json"] = recovery._canonical(old)
    write_archive(tmp_path, origin, blobs)
    return origin, blobs, stem


def test_versioned_recovery_preserves_original_and_recomputes_admission(tmp_path, monkeypatch):
    origin, blobs, stem = setup_projection(tmp_path, monkeypatch)
    monkeypatch.setattr(
        verifier, "_build_verifier_repair_callback", lambda *a, **k: pytest.fail("repair forbidden")
    )
    receipt = recovery.revalidate_retained(directory=tmp_path)
    proof = receipt["retained_revalidation"]
    assert proof["schema"] == "retained-revalidation/v2"
    assert proof["provider_generation_performed"] is False
    assert receipt["execution_kind"] == "authenticated_retained_revalidation"
    assert receipt["verdict"] == "FAIL"
    derived = json.loads((tmp_path / f"{stem}.json").read_bytes())
    assert derived["error"] is None and derived["raw_content"] == failed_row()["raw_content"]
    original = tmp_path / "retained-source" / origin["archive_sha256"] / f"{stem}.json"
    assert original.read_bytes() == blobs[f"{stem}.json"]
    assert json.loads(original.read_bytes())["error"] == failed_row()["error"]
    assert recovery.verify_revalidation_admission(receipt, directory=tmp_path)
    event = origin["verification_event"]
    identity = {key: event[key] for key in ["repo", "pr", "head_sha", "evaluated_sha"]}
    identity.update(run_id="20", run_attempt="1")
    decision = admitted_decision(
        tmp_path / f"{stem}.json",
        tmp_path / f"{stem}-execution.json",
        identity,
        mode="evaluate",
        ci_failed="false",
    )
    assert decision["verdict"] == "NON_PASS"
    assert decision["retained_revalidation"]["schema"] == "retained-revalidation/v2"


@pytest.mark.parametrize(
    "defect",
    [
        "unknown-producer",
        "generation-error",
        "refusal",
        "used-false",
        "wrong-verdict",
        "coverage",
        "chunk",
        "partition",
        "summary",
        "unknown-field",
        "omitted-final",
        "bad-final",
        "duplicate-final",
        "extra-final",
    ],
)
def test_projection_rejects_unproven_or_ambiguous_original(defect):
    row = failed_row()
    producer = PRODUCER
    if defect == "unknown-producer":
        producer = "0" * 64
    elif defect == "generation-error":
        row["error"] = "LLM invocation failed"
    elif defect == "refusal":
        row["error"] = "Native refusal"
    elif defect == "used-false":
        row["used_llm"] = False
    elif defect == "wrong-verdict":
        row["verdict"] = "PASS"
    elif defect == "coverage":
        row["input_coverage"]["sufficient"] = False
    elif defect == "chunk":
        row["chunk_reviews"] = [{"untrusted": True}]
    elif defect == "partition":
        row["partition_recovery"] = {"untrusted": True}
    elif defect == "summary":
        row["summary"] = "postprocessing changed result"
    elif defect == "unknown-field":
        row["new_authority"] = True
    elif defect == "omitted-final":
        row["raw_content"] = row["raw_content"].replace(
            "{", '{"files_not_reviewed":["required.py"],', 1
        )
    elif defect == "bad-final":
        row["raw_content"] += "\nprose"
    elif defect == "duplicate-final":
        row["raw_content"] = row["raw_content"].replace(
            '"verdict": "FAIL"', '"verdict":"PASS", "verdict":"FAIL"', 1
        )
    elif defect == "extra-final":
        row["raw_content"] = row["raw_content"].replace("{", '{"new_authority":true,', 1)
    with pytest.raises((ValueError, TypeError)):
        recovery.original_final_projection(row, mode="evaluate", validator_sha256=producer)


@pytest.mark.parametrize(
    "defect",
    [
        "projection-bytes",
        "proof-slot",
        "proof-extra",
        "original-bytes",
        "archive-bytes",
        "v1-substitution",
        "copied-job",
    ],
)
def test_projection_admission_rejects_forgery(tmp_path, monkeypatch, defect):
    origin, blobs, stem = setup_projection(tmp_path, monkeypatch)
    receipt = recovery.revalidate_retained(directory=tmp_path)
    proof = receipt["retained_revalidation"]
    if defect == "projection-bytes":
        value = json.loads((tmp_path / f"{stem}.json").read_bytes())
        value["verdict"] = "PASS"
        (tmp_path / f"{stem}.json").write_bytes(recovery._canonical(value))
    elif defect == "proof-slot":
        proof["original_final_projection"]["slots"][0]["original_error_sha256"] = "0" * 64
    elif defect == "proof-extra":
        proof["original_final_projection"]["new_authority"] = True
    elif defect == "original-bytes":
        (tmp_path / "retained-source" / origin["archive_sha256"] / f"{stem}.json").write_bytes(
            b"{}"
        )
    elif defect == "archive-bytes":
        (tmp_path / "verification-recovery-source.zip").write_bytes(b"not archive")
    elif defect == "v1-substitution":
        proof["schema"] = "retained-revalidation/v1"
    elif defect == "copied-job":
        monkeypatch.setenv("GITHUB_RUN_ID", "21")
    assert recovery.verify_revalidation_admission(receipt, directory=tmp_path) is False


@pytest.mark.parametrize(
    "defect",
    [
        "wrong-model",
        "wrong-provider",
        "missing",
        "duplicate",
        "third",
        "unknown-model",
        "reordered",
    ],
)
def test_legacy_compare_projection_joins_exact_configured_native_slots(defect):
    from tools.llm_registry import resolve_slots

    slots = resolve_slots()[:2]
    assessment = {"mode": "compare", "model": slots[0].model, "model2": slots[1].model}
    row = failed_row()
    row.update(provider_used=slots[1].provider, model=slots[1].model)
    sibling = {**row, "provider_used": slots[0].provider, "model": slots[0].model}
    payload = {"results": [sibling, row], "report": "original report"}
    if defect == "wrong-model":
        row["model"] = "foreign-model"
    elif defect == "wrong-provider":
        row["provider_used"] = "foreign-provider"
    elif defect == "missing":
        payload["results"].pop()
    elif defect == "duplicate":
        payload["results"] = [row, row]
    elif defect == "third":
        payload["results"].append(row)
    elif defect == "unknown-model":
        assessment["model2"] = "unknown-alias"
    elif defect == "reordered":
        payload["results"].reverse()
    if defect == "reordered":
        result, proof = recovery.original_final_projection(
            payload, mode="compare", validator_sha256=PRODUCER, assessment=assessment
        )
        assert [(r["provider_used"], r["model"]) for r in result["results"]] == [
            (r["provider_used"], r["model"]) for r in payload["results"]
        ]
    else:
        with pytest.raises((ValueError, TypeError)):
            recovery.original_final_projection(
                payload, mode="compare", validator_sha256=PRODUCER, assessment=assessment
            )


@pytest.mark.parametrize(
    ("outcome", "effect", "retryable"),
    [
        ("skipped", "", True),
        ("failure", "none", True),
        ("failure", "uncertain", False),
        ("success", "none", False),
    ],
)
def test_pending_v1_to_projected_v2_interruption_and_history(
    tmp_path, monkeypatch, outcome, effect, retryable
):
    import os
    import re
    import subprocess

    from tests.workflows.test_repeat_verification_lifecycle import run_state_step

    origin, blobs, stem = setup_projection(tmp_path, monkeypatch)
    manifest_path = tmp_path / "verification-event-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["retained_revalidation"] = {
        "schema": "retained-revalidation/v1",
        "recovery_key": origin["recovery_key"],
    }
    manifest_path.write_bytes(recovery._canonical(manifest))
    env = {
        "GITHUB_REPOSITORY": "owner/repo",
        "RECOVERY_PUBLICATION_OUTCOME": outcome,
        "RECOVERY_PUBLICATION_EFFECT": effect,
    }
    pending = run_state_step(tmp_path, "Record verification event pending", extra_env=env)
    receipt = recovery.revalidate_retained(directory=tmp_path)
    manifest["retained_revalidation"] = receipt["retained_revalidation"]
    manifest_path.write_bytes(recovery._canonical(manifest))
    terminal = run_state_step(
        tmp_path, "Record verification event terminal", outcome="failure", extra_env=env
    )
    state = json.loads(re.search(r"(\{.*\}) -->", terminal["comments"][0]["body"])[1])
    assert state["retained_revalidation"]["schema"] == "retained-revalidation/v2"
    assert state["retryable"] is retryable
    comments = [
        {
            "author": "github-actions[bot]",
            "url": f"https://github.com/owner/repo/pull/7#issuecomment-{i}",
            "body": item["body"],
        }
        for i, item in enumerate([*pending["comments"], *terminal["comments"]], 1)
    ]
    script = "const fs=require('fs');const {guardRecoveryHistory}=require('./.github/scripts/verifier_pending_execution.js');try{process.stdout.write(guardRecoveryHistory(JSON.parse(fs.readFileSync(0,'utf8'))));}catch{process.stdout.write('blocked');}"
    result = subprocess.check_output(
        ["node", "-e", script],
        cwd=Path(__file__).parents[2],
        env=os.environ,
        text=True,
        input=json.dumps(
            {
                "event": origin["verification_event"],
                "assessment": manifest["assessment_identity"],
                "comments": comments,
                "sourceRun": 10,
                "currentRun": 21,
                "recoveryKey": origin["recovery_key"],
            }
        ),
    )
    assert result == ("ready" if retryable else "blocked")


def test_legacy_compare_projection_native_pair_revalidates_and_admits(tmp_path, monkeypatch):
    from tools.llm_registry import resolve_slots

    origin, blobs, stem = setup_case(tmp_path, monkeypatch, mode="compare")
    slots = resolve_slots()[:2]
    manifest = json.loads(blobs["verification-event-manifest.json"])
    assessment = manifest["assessment_identity"]
    assessment.update(model=slots[0].model, model2=slots[1].model)
    origin.update(assessment_identity=assessment, validator_sha256=PRODUCER)
    origin["recovery_key"] = recovery._sha(
        recovery._canonical(
            {
                "schema": "retained-revalidation-key/v1",
                "event_id": origin["verification_event"]["event_id"],
                "assessment": assessment,
                "selector": {"run_id": 10, "run_attempt": 1, "artifact_id": 30},
            }
        )
    )
    row = failed_row()
    row.update(provider_used=slots[1].provider, model=slots[1].model)
    sibling = verifier.EvaluationResult(
        verdict="PASS", used_llm=True, provider_used=slots[0].provider, model=slots[0].model
    ).model_dump(mode="json")
    original = {"results": [row, sibling], "report": "original report"}
    blobs[f"{stem}.json"] = recovery._canonical(original)
    old = json.loads(blobs[f"{stem}-execution.json"])
    old["outputs"][f"{stem}.json"].update(
        sha256=recovery._sha(blobs[f"{stem}.json"]), bytes=len(blobs[f"{stem}.json"])
    )
    blobs[f"{stem}-execution.json"] = recovery._canonical(old)
    blobs["verification-event-manifest.json"] = recovery._canonical(manifest)
    (tmp_path / "verification-event-manifest.json").write_bytes(
        blobs["verification-event-manifest.json"]
    )
    write_archive(tmp_path, origin, blobs)
    receipt = recovery.revalidate_retained(directory=tmp_path)
    assert receipt["retained_revalidation"]["schema"] == "retained-revalidation/v2"
    assert receipt["verdict"] == "FAIL"
    assert recovery.verify_revalidation_admission(receipt, directory=tmp_path)
    derived = json.loads((tmp_path / f"{stem}.json").read_bytes())
    assert derived["results"][1] == sibling
    assert [(r["provider_used"], r["model"]) for r in derived["results"]] == [
        (r["provider_used"], r["model"]) for r in original["results"]
    ]
