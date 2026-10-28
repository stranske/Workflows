"""Admitted retained NON_PASS retains truthful native correction finding seeds."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from scripts.langchain import pr_verifier
from tools import verifier_event_recovery as recovery
from tools.verifier_corpus_evidence import admitted_decision, event_metadata

from tests.tools.test_retained_original_final_projection import (
    PRODUCER,
    failed_row,
    setup_projection,
)
from tests.tools.test_retained_verification_recovery import setup_case, write_archive

ROOT = Path(__file__).parents[2]


def seed_step():
    data = yaml.safe_load((ROOT / ".github/workflows/reusable-agents-verifier.yml").read_text())
    return next(
        s
        for s in [step for job in data["jobs"].values() for step in job.get("steps", [])]
        if s["name"] == "Retain original correction finding seeds"
    )


def allowed(**overrides):
    values = {
        "steps.event_terminal.outputs.complete": "true",
        "inputs.verification_recovery": "selector",
        "steps.retained_recovery.outcome": "success",
        "steps.post_recovery.outputs.published": "true",
        "inputs.mode": "compare",
    }
    values.update(overrides)
    expression = seed_step()["if"]
    for name, value in values.items():
        expression = expression.replace(name, repr(value))
    return eval(
        expression.replace("always()", "True").replace("&&", " and ").replace("||", " or "),
        {"__builtins__": {}},
    )


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, True),
        ({"steps.event_terminal.outputs.complete": "false"}, False),
        ({"steps.retained_recovery.outcome": "failure"}, False),
        ({"steps.post_recovery.outputs.published": "false"}, False),
        ({"steps.post_recovery.outputs.published": ""}, False),
        ({"inputs.mode": "checkbox"}, False),
        (
            {
                "inputs.verification_recovery": "",
                "steps.retained_recovery.outcome": "skipped",
                "steps.post_recovery.outputs.published": "",
            },
            True,
        ),
    ],
)
def test_actual_seed_workflow_condition_requires_complete_published_revalidation(changes, expected):
    assert allowed(**changes) is expected


@pytest.mark.parametrize("mode", ["evaluate", "compare"])
def test_actual_v2_admission_and_authored_seed_step_retain_original_findings(
    tmp_path, monkeypatch, mode
):
    if mode == "evaluate":
        origin, blobs, stem = setup_projection(tmp_path, monkeypatch)
    else:
        origin, blobs, stem = setup_case(tmp_path, monkeypatch, mode="compare")
        origin["validator_sha256"] = PRODUCER
        original = json.loads(blobs["verification-event-manifest.json"])
        original["assessment_identity"].update(model="gpt-5.6-terra", model2="claude-opus-5-5")
        origin["assessment_identity"] = original["assessment_identity"]
        blobs["verification-event-manifest.json"] = recovery._canonical(original)
        failed = failed_row()
        failed.update(provider_used="anthropic", model="claude-opus-5-5")
        sibling = pr_verifier.EvaluationResult(
            verdict="FAIL",
            used_llm=True,
            provider_used="openai",
            model="gpt-5.6-terra",
            concerns=["CSV unavailable in the exact task."],
        ).model_dump(mode="json")
        blobs[f"{stem}.json"] = recovery._canonical(
            {"results": [sibling, failed], "report": "Original test comparison"}
        )
        old = json.loads(blobs[f"{stem}-execution.json"])
        old["outputs"][f"{stem}.json"].update(
            sha256=recovery._sha(blobs[f"{stem}.json"]), bytes=len(blobs[f"{stem}.json"])
        )
        blobs[f"{stem}-execution.json"] = recovery._canonical(old)
    manifest = json.loads(blobs["verification-event-manifest.json"])
    body = "Original acceptance requires CSV round-trip; keep original source."
    manifest["request"]["sources"] = [
        {
            "kind": "issue",
            "repository": "owner/repo",
            "number": "1",
            "body_sha256": recovery._sha(body.encode()),
        }
    ]
    event = manifest["verification_event"]
    event["request_sha256"] = recovery._sha(recovery._canonical(manifest["request"]))
    event.pop("event_id")
    event["event_id"] = recovery._sha(recovery._canonical(event))
    origin["verification_event"] = event
    origin["recovery_key"] = recovery._sha(
        recovery._canonical(
            {
                "schema": "retained-revalidation-key/v1",
                "event_id": event["event_id"],
                "assessment": origin["assessment_identity"],
                "selector": {"run_id": 10, "run_attempt": 1, "artifact_id": 30},
            }
        )
    )
    blobs["verification-event-manifest.json"] = recovery._canonical(manifest)
    (tmp_path / "verification-event-manifest.json").write_bytes(
        blobs["verification-event-manifest.json"]
    )
    write_archive(tmp_path, origin, blobs)
    receipt = recovery.revalidate_retained(directory=tmp_path)
    identity = {k: event[k] for k in ["repo", "pr", "head_sha", "evaluated_sha"]}
    identity.update(run_id="20", run_attempt="1")
    decision = admitted_decision(
        tmp_path / f"{stem}.json",
        tmp_path / f"{stem}-execution.json",
        identity,
        mode=mode,
        ci_failed="false",
    )
    decision.update(event_metadata(tmp_path / "verification-event-manifest.json"))
    assert (
        decision["verdict"] == "NON_PASS"
        and decision["retained_revalidation"]["schema"] == "retained-revalidation/v2"
    )
    pull = {
        "number": 7,
        "merged": True,
        "head": {"sha": event["head_sha"]},
        "merge_commit_sha": event["evaluated_sha"],
        "base": {"sha": "c" * 40, "repo": {"full_name": "owner/repo"}},
    }
    source = {"number": 1, "node_id": "I_1", "body": body}
    comment = {
        "id": 700,
        "user": {"id": 41898282, "login": "github-actions[bot]", "type": "Bot"},
        "html_url": "https://github.com/owner/repo/pull/7#issuecomment-700",
        "body": "<!-- verifier-corpus-decision/v1 "
        + json.dumps(decision, separators=(",", ":"))
        + " -->",
    }
    (tmp_path / ".workflows-lib").symlink_to(ROOT, target_is_directory=True)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "python3").symlink_to(sys.executable)
    env = {
        **os.environ,
        "PATH": str(bindir) + os.pathsep + os.environ["PATH"],
        "VERIFIER_MODE": mode,
        "PR_NUMBER": "7",
        "PR_HEAD_SHA": event["head_sha"],
        "EVALUATED_SHA": event["evaluated_sha"],
        "CI_FAILED": "false",
    }
    runner = """
const fs=require('fs');const input=JSON.parse(fs.readFileSync(0,'utf8'));let reads=0;
const github={rest:{pulls:{get:async()=>{reads++;return {data:input.pull}}},issues:{get:async()=>{reads++;return {data:input.source}},listComments:async()=>{reads++;return {data:[input.comment]}}}}};
const context={runId:20};const core={warning:()=>{throw new Error('seed refusal')}};
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
new AsyncFunction('require','github','context','core',input.script)(require,github,context,core).then(()=>process.stdout.write(JSON.stringify({reads}))).catch(e=>{console.error(e.message);process.exitCode=1});
"""
    result = subprocess.run(
        ["node", "-e", runner],
        cwd=tmp_path,
        env=env,
        input=json.dumps(
            {
                "script": seed_step()["with"]["script"],
                "pull": pull,
                "source": source,
                "comment": comment,
            }
        ),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["reads"] == 3
    bundle = json.loads((tmp_path / "closer-correction-seeds.json").read_bytes())
    derived = json.loads((tmp_path / f"{stem}.json").read_bytes())
    concerns = (
        derived["concerns"]
        if mode == "evaluate"
        else [c for row in derived["results"] for c in row["concerns"]]
    )
    assert len(bundle["seeds"]) == len(concerns) == (6 if mode == "evaluate" else 7)
    assert bundle["result_sha256"] == recovery._sha((tmp_path / f"{stem}.json").read_bytes())
    assert all(
        s["original_verifier"]["run_id"] == "20"
        and s["original_verifier"]["run_attempt"] == "1"
        and s["original_verifier"]["comment_id"] == "700"
        for s in bundle["seeds"]
    )
    assert all(
        s["original_verifier"]["decision_sha256"] == recovery._sha(recovery._canonical(decision))
        for s in bundle["seeds"]
    )
    original = tmp_path / "retained-source" / origin["archive_sha256"] / f"{stem}.json"
    assert original.read_bytes() == blobs[f"{stem}.json"]
    originals = json.loads(original.read_bytes())
    assert (originals if mode == "evaluate" else originals["results"][1])["error"]
    assert receipt["retained_revalidation"]["provider_generation_performed"] is False


def test_native_upload_preserves_original_zip_without_shadowing_current_inputs():
    data = yaml.safe_load((ROOT / ".github/workflows/reusable-agents-verifier.yml").read_text())
    steps = [step for job in data["jobs"].values() for step in job.get("steps", [])]
    for name in ["Upload comparison artifacts", "Retain evaluation execution evidence"]:
        step = next(step for step in steps if step.get("name") == name)
        paths = step["with"]["path"].splitlines()
        assert "verification-recovery-source.zip" in paths
        assert "verification-recovery-origin.json" in paths
        assert "verification-revalidation-receipt.json" in paths
        assert "closer-correction-seeds.json" in paths
        assert "retained-source/" not in paths
        assert not any(path.startswith("retained-source/") for path in paths)
