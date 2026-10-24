"""Authenticated retained revalidation never invokes a provider or rewrites history."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
import yaml
from tools.verifier_corpus_evidence import admitted_decision
from tools.verifier_event_recovery import revalidate_retained, verify_revalidation_admission


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def setup_case(tmp_path, monkeypatch, *, mode="evaluate"):
    head, merge = "a" * 40, "b" * 40
    request = {"schema": "verification-request/v1", "sources": []}
    diff, context, summary = b"diff original", b"authentic original requirements", b"one file"
    material = {
        "schema": "verification-material/v1",
        "code": {"head_sha": head, "evaluated_sha": merge, "diff_sha256": sha(diff)},
    }
    event = {
        "schema": "verification-event/v1",
        "repo": "owner/repo",
        "pr": "7",
        "head_sha": head,
        "evaluated_sha": merge,
        "request_sha256": sha(encoded(request)),
        "material_sha256": sha(encoded(material)),
    }
    event["event_id"] = sha(encoded(event))
    assessment = {
        "mode": mode,
        "provider": "anthropic" if mode == "evaluate" else "",
        "model": "m",
        "model2": "" if mode == "evaluate" else "n",
        "canonical": True,
    }
    manifest = {
        "verification_event": event,
        "assessment_identity": assessment,
        "request": request,
        "material": material,
    }
    row = {
        "verdict": "PASS",
        "concerns": [],
        "summary": "Complete retained review",
        "used_llm": True,
        "provider_used": "anthropic",
        "model": "m",
    }
    payload = (
        row
        if mode == "evaluate"
        else {"results": [row, {**row, "provider_used": "openai", "model": "n"}]}
    )
    stem = "evaluation" if mode == "evaluate" else "comparison"
    raw = encoded(payload)
    snapshot = {
        "schema": "workflows-verifier-input-snapshot/v1",
        "capture_kind": "production",
        "repository": "owner/repo",
        "pr": 7,
        "merge_sha": merge,
        "mode": mode,
        "source_run_id": "10",
        "context_sha256": sha(context),
        "diff_sha256": sha(diff),
        "diff_summary_sha256": sha(summary),
    }
    snapshot_raw = encoded(snapshot)
    receipt = {
        "schema": f"workflows-verifier-{stem}-execution/v1",
        "mode": mode,
        "status": "invalid_output",
        "exit_code": 0,
        "validation_error_type": "ImportError",
        "decision_available": False,
        "repository": "owner/repo",
        "source_run_id": "10",
        "source_run_attempt": "1",
        "input_manifest": {"sha256": sha(snapshot_raw)},
        "outputs": {
            f"{stem}.json": {
                "sha256": sha(raw),
                "bytes": len(raw),
                "original_complete": True,
                "truncated": False,
            }
        },
    }
    blobs = {
        f"{stem}.json": raw,
        f"{stem}-execution.json": encoded(receipt),
        "verifier-input-manifest.json": snapshot_raw,
        "verification-event-manifest.json": encoded(manifest),
        "verifier-context.md": context,
        "verifier-pr-diff.patch": diff,
        "verifier-diff-summary.md": summary,
    }
    origin = {
        "schema": "workflows-retained-origin/v1",
        "repository": "owner/repo",
        "current_run_id": "20",
        "source_run_id": "10",
        "source_run_attempt": "1",
        "artifact_id": 30,
        "helper_sha": "c" * 40,
        "validator_sha256": "d" * 64,
        "verification_event": event,
        "assessment_identity": assessment,
        "recovery_key": "e" * 64,
    }
    (tmp_path / "verification-event-manifest.json").write_bytes(encoded(manifest))
    for key, value in {
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_RUN_ID": "20",
        "GITHUB_RUN_ATTEMPT": "1",
        "VERIFICATION_RECOVERY": json.dumps({"run_id": 10, "run_attempt": 1, "artifact_id": 30}),
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("VERIFIER_EVIDENCE_PROFILE", raising=False)
    write_archive(tmp_path, origin, blobs)
    return origin, blobs, stem


def write_archive(directory, origin, blobs, *, duplicate=False):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, raw in blobs.items():
            archive.writestr(name, raw)
        if duplicate:
            with pytest.warns(UserWarning, match="Duplicate name"):
                archive.writestr("evaluation.json", b"{}")
    raw = stream.getvalue()
    origin.update(archive_bytes=len(raw), archive_sha256=sha(raw))
    (directory / "verification-recovery-source.zip").write_bytes(raw)
    (directory / "verification-recovery-origin.json").write_bytes(encoded(origin))


@pytest.mark.parametrize("mode", ["evaluate", "compare"])
def test_invalid_wrapper_revalidates_without_generation_and_preserves_originals(
    tmp_path, monkeypatch, mode
):
    origin, blobs, stem = setup_case(tmp_path, monkeypatch, mode=mode)
    receipt = revalidate_retained(directory=tmp_path)
    assert receipt["status"] == "completed"
    assert receipt["retained_revalidation"]["provider_generation_performed"] is False
    retained = tmp_path / "retained-source" / origin["archive_sha256"]
    assert all((retained / name).read_bytes() == raw for name, raw in blobs.items())
    assert (
        json.loads((retained / f"{stem}-execution.json").read_bytes())["status"] == "invalid_output"
    )
    assert verify_revalidation_admission(receipt, directory=tmp_path)
    event = origin["verification_event"]
    identity = {key: event[key] for key in ["repo", "pr", "head_sha", "evaluated_sha"]}
    identity.update(run_id="20", run_attempt="1")
    result = admitted_decision(
        tmp_path / f"{stem}.json",
        tmp_path / f"{stem}-execution.json",
        identity,
        mode=mode,
        ci_failed="false",
    )
    assert result["verdict"] == "PASS"
    assert result["retained_revalidation"]["source_run_id"] == "10"
    monkeypatch.setenv("GITHUB_RUN_ID", "21")
    assert not verify_revalidation_admission(receipt, directory=tmp_path)


@pytest.mark.parametrize(
    "mutation",
    [
        "tamper",
        "missing",
        "duplicate",
        "path",
        "truncated",
        "input",
        "foreign",
        "event",
        "assessment",
        "selector",
        "raw_error",
    ],
)
def test_bad_source_never_creates_current_receipt(tmp_path, monkeypatch, mutation):
    origin, blobs, stem = setup_case(tmp_path, monkeypatch)
    if mutation == "missing":
        del blobs["verifier-context.md"]
    elif mutation == "path":
        blobs["../overwrite"] = b"untrusted"
    elif mutation in {"truncated", "input", "foreign", "raw_error"}:
        receipt = json.loads(blobs[f"{stem}-execution.json"])
        if mutation == "truncated":
            receipt["outputs"][f"{stem}.json"]["truncated"] = True
        elif mutation == "input":
            receipt["input_manifest"]["sha256"] = "0" * 64
        elif mutation == "foreign":
            receipt["repository"] = "foreign/repo"
        else:
            data = json.loads(blobs[f"{stem}.json"])
            data.update(error="provider unavailable", used_llm=False)
            blobs[f"{stem}.json"] = encoded(data)
        blobs[f"{stem}-execution.json"] = encoded(receipt)
    elif mutation in {"event", "assessment"}:
        original = json.loads(blobs["verification-event-manifest.json"])
        if mutation == "event":
            original["verification_event"]["request_sha256"] = "f" * 64
        else:
            original["assessment_identity"]["model"] = "another-model"
        blobs["verification-event-manifest.json"] = encoded(original)
    elif mutation == "selector":
        monkeypatch.setenv(
            "VERIFICATION_RECOVERY", '{"run_id":10,"run_attempt":2,"artifact_id":30}'
        )
    write_archive(tmp_path, origin, blobs, duplicate=mutation == "duplicate")
    if mutation == "tamper":
        with (tmp_path / "verification-recovery-source.zip").open("ab") as stream:
            stream.write(b"changed")
    with pytest.raises((ValueError, KeyError)):
        revalidate_retained(directory=tmp_path)
    assert not (tmp_path / f"{stem}-execution.json").exists()


def test_authored_workflow_presence_guard_excludes_all_generation_routes():
    workflow = yaml.safe_load(Path(".github/workflows/reusable-agents-verifier.yml").read_text())
    steps = workflow["jobs"]["verifier"]["steps"]
    generation = [
        "Run LLM evaluation",
        "Run multi-provider comparison",
        "Check provider secrets",
        "Validate Codex auth for checkbox/compare modes",
        "Setup Codex auth",
        "Install Codex CLI",
        "Shadow candidate verifier judges (recorded only; never posted, never counted)",
    ]
    for name in generation:
        step = next(step for step in steps if step["name"] == name)
        assert "inputs.verification_recovery == ''" in step["if"]
    recovery = next(step for step in steps if step.get("id") == "retained_recovery")
    assert "--revalidate-retained" in recovery["run"]
    assert not any(
        "KEY" in key or "SECRET" in key or "TOKEN" in key for key in recovery.get("env", {})
    )


def test_authored_recovery_shell_runs_without_credentials_or_provider_generation(
    tmp_path, monkeypatch
):
    import os
    import subprocess
    import sys

    setup_case(tmp_path, monkeypatch)
    root = Path(__file__).resolve().parents[2]
    (tmp_path / ".workflows-lib").symlink_to(root, target_is_directory=True)
    workflow = yaml.safe_load((root / ".github/workflows/reusable-agents-verifier.yml").read_text())
    step = next(
        step
        for step in workflow["jobs"]["verifier"]["steps"]
        if step.get("id") == "retained_recovery"
    )
    # Count every external generation boundary in the actual authored process.
    # The startup guard is test-only; it records and refuses even an attempted
    # network connection, so absent credentials cannot hide a provider attempt.
    guard = tmp_path / "guard"
    guard.mkdir()
    counter = tmp_path / "provider-network-attempts"
    (guard / "sitecustomize.py").write_text(
        "import os,sys\nfrom pathlib import Path\n"
        "def audit(event,args):\n"
        " if event in {'socket.connect','socket.getaddrinfo'}:\n"
        "  Path(os.environ['PROVIDER_COUNTER']).write_text(event)\n"
        "  raise RuntimeError('provider/network forbidden during recovery')\n"
        "sys.addaudithook(audit)\n"
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if not any(secret in key for secret in ["API_KEY", "TOKEN", "SECRET", "CLAUDE_API"])
    }
    env.update(
        PYTHONPATH=str(guard),
        PROVIDER_COUNTER=str(counter),
        GITHUB_OUTPUT=str(tmp_path / "outputs"),
    )
    # Pin this test's interpreter while executing the authored shell verbatim.
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "python3").symlink_to(sys.executable)
    env["PATH"] = str(bindir) + os.pathsep + env["PATH"]
    result = subprocess.run(
        ["bash", "-c", step["run"]],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "verdict=PASS" in (tmp_path / "outputs").read_text()
    assert not counter.exists()
    receipt = json.loads((tmp_path / "verification-revalidation-receipt.json").read_text())
    assert receipt["retained_revalidation"]["provider_generation_performed"] is False


@pytest.mark.parametrize("ci_failed", ["false", "true"])
def test_authored_recovery_publisher_event_and_unified_share_current_admission(
    tmp_path, monkeypatch, ci_failed
):
    import os
    import re
    import subprocess
    import sys

    from tests.workflows.test_repeat_verification_lifecycle import authored, run_state_step

    origin, _, _ = setup_case(tmp_path, monkeypatch)
    revalidate_retained(directory=tmp_path)
    root = Path(__file__).resolve().parents[2]
    (tmp_path / ".workflows-lib").symlink_to(root, target_is_directory=True)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "python3").symlink_to(sys.executable)
    event = origin["verification_event"]
    env = {
        **os.environ,
        "PATH": str(bindir) + os.pathsep + os.environ["PATH"],
        "PR_NUMBER": event["pr"],
        "PR_HEAD_SHA": event["head_sha"],
        "EVALUATED_SHA": event["evaluated_sha"],
        "CI_FAILED": ci_failed,
        "VERIFIER_MODE": "evaluate",
    }
    script = authored("Publish retained revalidation through verifier lifecycle")["with"]["script"]
    runner = """
const fs=require('fs'); const input=JSON.parse(fs.readFileSync(0,'utf8'));
const comments=[],outputs={};
const github={rest:{pulls:{get:async()=>({data:{merged:true,head:{sha:process.env.PR_HEAD_SHA},merge_commit_sha:process.env.EVALUATED_SHA}})},issues:{listComments:async()=>({data:[],headers:{}}),createComment:async row=>{comments.push(row);return {data:{id:5}};}}}};
const context={runId:Number(process.env.GITHUB_RUN_ID)};
const core={setOutput:(key,value)=>{outputs[key]=value;}};
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
new AsyncFunction('require','github','context','core',input.script)(require,github,context,core)
.then(()=>process.stdout.write(JSON.stringify({comments,outputs}))).catch(error=>{console.error(error);process.exitCode=1;});
"""
    published = subprocess.run(
        ["node", "-e", runner],
        input=json.dumps({"script": script}),
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert published.returncode == 0, published.stderr
    result = json.loads(published.stdout)
    assert result["outputs"]["published"] == "true"
    report = result["comments"][0]["body"]
    expected = "PASS" if ci_failed == "false" else "CONCERNS"
    assert f"**Verdict:** {expected}" in report
    decision = json.loads(
        re.search(r"<!-- verifier-corpus-decision/v1 (\{[^\n]+\}) -->", report)[1]
    )
    assert decision["verdict"] == ("PASS" if ci_failed == "false" else "NON_PASS")
    assert decision["verification_event"] == event
    assert not decision.get("predecessor_event_id")
    terminal = run_state_step(
        tmp_path, "Record verification event terminal", posted=True, extra_env=env
    )
    assert terminal["outputs"]["complete"] == "true"
    unified = authored("Set unified verdict")["run"]
    values = {
        "steps.verdict.outputs.verdict": "",
        "steps.llm_evaluate.outputs.verdict": "",
        "steps.llm_compare.outputs.verdict": "",
        "steps.context.outputs.ci_failed": ci_failed,
    }
    unified = re.sub(r"\$\{\{\s*(.*?)\s*\}\}", lambda match: values[match[1]], unified)
    env.update(
        RETAINED_RECOVERY_VERDICT="PASS",
        RETAINED_RECOVERY_PUBLISHED="true",
        GITHUB_OUTPUT=str(tmp_path / "unified-output"),
    )
    settled = subprocess.run(
        ["bash", "-c", unified], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30
    )
    assert settled.returncode == 0, settled.stderr
    assert (tmp_path / "unified-output").read_text().strip() == f"verdict={expected}"
    env.update(
        RETAINED_RECOVERY_PUBLISHED="false", GITHUB_OUTPUT=str(tmp_path / "unpublished-output")
    )
    refused = subprocess.run(
        ["bash", "-c", unified], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30
    )
    assert refused.returncode == 0, refused.stderr
    assert (tmp_path / "unpublished-output").read_text().strip() == "verdict=UNVERIFIABLE_INPUT"


def test_actual_comparison_receipt_shape_joins_complete_authenticated_archive(
    tmp_path, monkeypatch
):
    origin, blobs, stem = setup_case(tmp_path, monkeypatch, mode="compare")
    receipt = json.loads(blobs[f"{stem}-execution.json"])
    # The authored pre-recovery compare producer has result hash/bytes but no
    # input_manifest/transport flags. The authenticated whole archive supplies
    # that missing cross-member join; every original input hash still verifies.
    receipt.pop("input_manifest")
    receipt["outputs"][f"{stem}.json"].pop("original_complete")
    receipt["outputs"][f"{stem}.json"].pop("truncated")
    blobs[f"{stem}-execution.json"] = encoded(receipt)
    write_archive(tmp_path, origin, blobs)
    result = revalidate_retained(directory=tmp_path)
    assert result["verdict"] == "PASS"
    retained = tmp_path / "retained-source" / origin["archive_sha256"]
    assert (retained / f"{stem}-execution.json").read_bytes() == blobs[f"{stem}-execution.json"]


def test_unicode_required_material_uses_the_actual_collector_canonical_digest(
    tmp_path, monkeypatch
):
    import subprocess

    origin, blobs, _ = setup_case(tmp_path, monkeypatch)
    manifest = json.loads(blobs["verification-event-manifest.json"])
    material = manifest["material"]
    material["required_evidence"] = [
        {
            "kind": "artifact_member",
            "run_id": 5,
            "artifact_id": 6,
            "path": "résumé-評価.txt",
            "raw_sha256": "a" * 64,
        }
    ]
    root = Path(__file__).resolve().parents[2]
    js = "const fs=require('fs'); const {digest}=require('./.github/scripts/verification_event.js'); process.stdout.write(digest(JSON.parse(fs.readFileSync(0,'utf8'))));"
    material_sha = subprocess.check_output(
        ["node", "-e", js], input=json.dumps(material), cwd=root, text=True
    )
    event = manifest["verification_event"]
    event["material_sha256"] = material_sha
    event.pop("event_id")
    event["event_id"] = sha(encoded(event))
    origin["verification_event"] = event
    blobs["verification-event-manifest.json"] = encoded(manifest)
    (tmp_path / "verification-event-manifest.json").write_bytes(encoded(manifest))
    write_archive(tmp_path, origin, blobs)
    result = revalidate_retained(directory=tmp_path)
    assert result["verdict"] == "PASS"


@pytest.mark.parametrize("verdict", ["CONCERNS", "FAIL"])
def test_recovered_report_keeps_actionable_findings_without_summary(tmp_path, monkeypatch, verdict):
    origin, blobs, stem = setup_case(tmp_path, monkeypatch)
    payload = json.loads(blobs[f"{stem}.json"])
    payload.update(
        verdict=verdict,
        summary=None,
        concerns=["Repair the login timeout", "Retain proof <without forging markers>"],
        input_coverage={"files_total": 13, "files_complete": 13},
    )
    raw = encoded(payload)
    blobs[f"{stem}.json"] = raw
    receipt = json.loads(blobs[f"{stem}-execution.json"])
    receipt["outputs"][f"{stem}.json"].update(sha256=sha(raw), bytes=len(raw))
    blobs[f"{stem}-execution.json"] = encoded(receipt)
    write_archive(tmp_path, origin, blobs)
    result = revalidate_retained(directory=tmp_path)
    assert result["verdict"] == verdict
    report = (tmp_path / f"{stem}-comment.md").read_text()
    assert f"**Verdict:** {verdict}" in report
    assert "files reviewed 13 of 13" in report
    assert "- Repair the login timeout" in report
    assert "- Retain proof &lt;without forging markers&gt;" in report
    assert (
        tmp_path / "retained-source" / origin["archive_sha256"] / f"{stem}.json"
    ).read_bytes() == raw


@pytest.mark.parametrize(
    ("publication_outcome", "publication_effect", "retryable"),
    [
        ("skipped", "", True),
        ("failure", "none", True),
        ("failure", "uncertain", False),
        ("success", "none", False),
    ],
)
def test_authored_failed_recovery_can_retry_only_before_publication(
    tmp_path, monkeypatch, publication_outcome, publication_effect, retryable
):
    import os
    import re
    import subprocess

    from tests.workflows.test_repeat_verification_lifecycle import run_state_step

    origin, _, _ = setup_case(tmp_path, monkeypatch)
    manifest_path = tmp_path / "verification-event-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    key = "c" * 64
    manifest["retained_revalidation"] = {"schema": "retained-revalidation/v1", "recovery_key": key}
    manifest_path.write_text(json.dumps(manifest))
    env = {
        "GITHUB_REPOSITORY": "owner/repo",
        "RECOVERY_PUBLICATION_OUTCOME": publication_outcome,
        "RECOVERY_PUBLICATION_EFFECT": publication_effect,
    }
    pending = run_state_step(tmp_path, "Record verification event pending", extra_env=env)
    terminal = run_state_step(
        tmp_path, "Record verification event terminal", outcome="failure", extra_env=env
    )
    state = json.loads(re.search(r"(\{.*\}) -->", terminal["comments"][0]["body"])[1])
    assert state["retryable"] is retryable
    assert state["retained_revalidation"]["recovery_key"] == key
    comments = [
        {
            "author": "github-actions[bot]",
            "url": f"https://github.com/owner/repo/pull/7#issuecomment-{index}",
            "body": item["body"],
        }
        for index, item in enumerate([*pending["comments"], *terminal["comments"]], 1)
    ]
    root = Path(__file__).resolve().parents[2]
    script = """
const fs=require('fs'); const data=JSON.parse(fs.readFileSync(0,'utf8'));
const {guardRecoveryHistory}=require('./.github/scripts/verifier_pending_execution.js');
try {process.stdout.write(guardRecoveryHistory(data));} catch {process.stdout.write('blocked');}
"""
    result = subprocess.check_output(
        ["node", "-e", script],
        input=json.dumps(
            {
                "event": origin["verification_event"],
                "assessment": manifest["assessment_identity"],
                "comments": comments,
                "sourceRun": 10,
                "currentRun": 21,
                "recoveryKey": key,
            }
        ),
        text=True,
        cwd=root,
        env=os.environ,
    )
    assert result == ("ready" if retryable else "blocked")
