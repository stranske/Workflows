"""Exercise authored production state/result publication offline, without models."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/reusable-agents-verifier.yml"
FIXTURE = ROOT / "tests/fixtures/verification_event/canonical.json"
ASSESSMENT = {
    "mode": "evaluate",
    "provider": "anthropic",
    "model": "",
    "model2": "",
    "canonical": True,
}


def authored(name):
    workflow = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    return next(step for step in workflow["jobs"]["verifier"]["steps"] if step.get("name") == name)


def run_state_step(tmp_path, name, *, posted=False, outcome="success"):
    if not (tmp_path / ".workflows-lib").exists():
        (tmp_path / ".workflows-lib").symlink_to(ROOT, target_is_directory=True)
    script = authored(name)["with"]["script"]
    runner = """
const fs = require('fs'); const input=JSON.parse(fs.readFileSync(0,'utf8'));
const comments=[],outputs={};
const github={rest:{issues:{createComment:async row=>comments.push(row)}}};
const context={repo:{owner:'stranske',repo:'example'},runId:20};
const core={setOutput:(key,value)=>{outputs[key]=value;}};
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
new AsyncFunction('require','github','context','core',input.script)(require,github,context,core)
 .then(()=>process.stdout.write(JSON.stringify({comments,outputs})))
 .catch(error=>{process.stderr.write(error.stack);process.exitCode=1;});
"""
    result = subprocess.run(
        ["node", "-e", runner],
        input=json.dumps({"script": script}),
        text=True,
        capture_output=True,
        cwd=tmp_path,
        check=True,
        env={
            **os.environ,
            "GITHUB_RUN_ATTEMPT": "1",
            "PRODUCTION_REPORT_POSTED": str(posted).lower(),
            "EVALUATOR_STEP_OUTCOME": outcome,
        },
    )
    return json.loads(result.stdout)


def manifest(tmp_path):
    data = json.loads(FIXTURE.read_text())
    data["assessment_identity"] = ASSESSMENT
    data["execution_binding"] = {
        "schema": "verifier-execution-binding/v1",
        "workflow_path": ".github/workflows/agents-verifier.yml",
        "job_name": "Run post-merge verifier",
        "pending_step": "Record verification event pending",
        "evaluator_step": "Run LLM evaluation",
    }
    (tmp_path / "verification-event-manifest.json").write_text(json.dumps(data))
    return data


def annotate(tmp_path, *, used_llm, verdict="PASS"):
    (tmp_path / "evaluation.json").write_text(
        json.dumps({"used_llm": used_llm, "verdict": verdict})
    )
    (tmp_path / "evaluation-comment.md").write_text("Retained actual model result.\n")
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/verifier_corpus_evidence.py"),
            "--evaluation",
            "evaluation.json",
            "--comment",
            "evaluation-comment.md",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "GITHUB_REPOSITORY": "stranske/example",
            "PR_NUMBER": "7",
            "PR_HEAD_SHA": "a" * 40,
            "EVALUATED_SHA": "b" * 40,
            "GITHUB_RUN_ID": "20",
            "GITHUB_RUN_ATTEMPT": "1",
            "CI_FAILED": "false",
        },
    )


@pytest.mark.parametrize("verdict", ["PASS", "CONCERNS"])
def test_actual_pending_annotation_and_terminal_steps_share_exact_event(tmp_path, verdict):
    data = manifest(tmp_path)
    pending = run_state_step(tmp_path, "Record verification event pending")
    assert '"status":"pending"' in pending["comments"][0]["body"]
    assert data["verification_event"]["event_id"] in pending["comments"][0]["body"]
    assert "execution_binding" in pending["comments"][0]["body"]
    result = annotate(tmp_path, used_llm=True, verdict=verdict)
    assert result.returncode == 0, result.stderr
    text = (tmp_path / "evaluation-comment.md").read_text()
    assert "verifier-corpus-decision/v1" in text
    assert data["verification_event"]["event_id"] in text
    assert ('"verdict": "PASS"' if verdict == "PASS" else '"verdict": "NON_PASS"') in text
    terminal = run_state_step(tmp_path, "Record verification event terminal", posted=True)
    assert terminal["outputs"]["complete"] == "true"
    assert terminal["comments"] == []


@pytest.mark.parametrize("used_llm", [False, "false", 1, None])
def test_missing_model_result_finishes_incomplete_never_reuses_prior_pass(tmp_path, used_llm):
    manifest(tmp_path)
    assert annotate(tmp_path, used_llm=used_llm).returncode == 0
    assert "verifier-corpus-decision/v1" not in (tmp_path / "evaluation-comment.md").read_text()
    terminal = run_state_step(tmp_path, "Record verification event terminal", posted=True)
    assert terminal["outputs"]["complete"] == "false"
    assert '"status":"incomplete"' in terminal["comments"][0]["body"]


def test_manifest_identity_mismatch_never_publishes_a_legacy_pass(tmp_path):
    data = manifest(tmp_path)
    event = data["verification_event"]
    event["pr"] = "8"
    core = {key: value for key, value in event.items() if key != "event_id"}
    event["event_id"] = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (tmp_path / "verification-event-manifest.json").write_text(json.dumps(data))
    assert annotate(tmp_path, used_llm=True).returncode != 0
    assert "verifier-corpus-decision/v1" not in (tmp_path / "evaluation-comment.md").read_text()


def test_errored_true_result_is_retained_for_recovery_without_terminal_pass(tmp_path):
    manifest(tmp_path)
    (tmp_path / "evaluation.json").write_text(
        json.dumps({"used_llm": True, "verdict": "PASS", "error": "response incomplete"})
    )
    (tmp_path / "evaluation-comment.md").write_text("Original retained response.\n")
    env = {
        **os.environ,
        "GITHUB_REPOSITORY": "stranske/example",
        "PR_NUMBER": "7",
        "PR_HEAD_SHA": "a" * 40,
        "EVALUATED_SHA": "b" * 40,
        "GITHUB_RUN_ID": "20",
        "GITHUB_RUN_ATTEMPT": "1",
        "CI_FAILED": "false",
    }
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/verifier_corpus_evidence.py"),
            "--evaluation",
            "evaluation.json",
            "--comment",
            "evaluation-comment.md",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "verifier-corpus-decision/v1" not in (tmp_path / "evaluation-comment.md").read_text()
    state = incomplete_state(
        run_state_step(tmp_path, "Record verification event terminal", posted=True)
    )
    assert state["retry_kind"] == "recover_existing_evaluation"
    assert state["retryable"] is False


def test_template_repeat_bypasses_only_coarse_fingerprint_and_threads_all_inputs():
    template = yaml.load(
        (ROOT / "templates/consumer-repo/.github/workflows/agents-verifier.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    reusable = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    for key in ("verification_event", "verification_material", "verification_predecessor"):
        assert key in template["on"]["workflow_dispatch"]["inputs"]
        assert key in reusable["on"]["workflow_call"]["inputs"]
        assert key in template["jobs"]["verifier"]["with"]
    assert (
        "steps.check.outputs.mode != 'checkbox'"
        in template["jobs"]["check"]["outputs"]["fingerprint_should_run"]
    )
    assert "event_complete" in template["jobs"]["persist-fingerprint"]["if"]
    assert reusable["concurrency"]["cancel-in-progress"] == "false"
    assert (ROOT / ".github/scripts/verification_event.js").read_bytes() == (
        ROOT / "templates/consumer-repo/.github/scripts/verification_event.js"
    ).read_bytes()


def incomplete_state(result):
    body = result["comments"][0]["body"]
    return json.loads(body.split("verifier-event-state/v1 ", 1)[1].rsplit(" -->", 1)[0])


@pytest.mark.parametrize(
    "case,expected",
    [
        ("no_llm", "known_no_evaluation"),
        ("review_unpublished", "recover_existing_evaluation"),
        ("missing", "uncertain_execution"),
        ("skipped", "known_no_evaluation"),
        ("provider_error", "uncertain_execution"),
        ("malformed", "uncertain_execution"),
        ("contradictory_skipped", "uncertain_execution"),
    ],
)
def test_authored_incomplete_state_preserves_execution_cause(tmp_path, case, expected):
    manifest(tmp_path)
    if case in {"no_llm", "provider_error"}:
        payload = {"used_llm": False, "verdict": "UNVERIFIABLE_INPUT"}
        if case == "provider_error":
            payload["error"] = "Chunk review failed after invocation; response unavailable"
        (tmp_path / "evaluation.json").write_text(json.dumps(payload))
    elif case in {"review_unpublished", "contradictory_skipped"}:
        (tmp_path / "evaluation.json").write_text(json.dumps({"used_llm": True, "verdict": "PASS"}))
    elif case == "malformed":
        (tmp_path / "evaluation.json").write_text(
            json.dumps({"used_llm": "false", "verdict": "UNVERIFIABLE_INPUT"})
        )
    result = run_state_step(
        tmp_path,
        "Record verification event terminal",
        posted=False,
        outcome="skipped" if case in {"skipped", "contradictory_skipped"} else "success",
    )
    state = incomplete_state(result)
    assert state["retry_kind"] == expected
    assert state["retryable"] == (expected == "known_no_evaluation")
    assert state["failure_cause"]
    assert state["status"] == "incomplete"


def test_comparison_no_evaluation_requires_all_configured_slots(tmp_path):
    from tools.llm_registry import resolve_slots

    data = manifest(tmp_path)
    data["assessment_identity"] = {**ASSESSMENT, "mode": "compare"}
    (tmp_path / "verification-event-manifest.json").write_text(json.dumps(data))
    slots = resolve_slots()[:2]
    assert len(slots) == 2
    rows = [
        {
            "used_llm": False,
            "verdict": "UNVERIFIABLE_INPUT",
            "provider_used": slot.provider,
            "model": slot.model,
        }
        for slot in slots
    ]
    (tmp_path / "comparison.json").write_text(json.dumps({"results": rows[:1]}))
    state = incomplete_state(run_state_step(tmp_path, "Record verification event terminal"))
    assert state["retry_kind"] == "uncertain_execution"
    assert state["failure_cause"] == "configured_result_slots_incomplete"
    (tmp_path / "comparison.json").write_text(json.dumps({"results": rows}))
    state = incomplete_state(run_state_step(tmp_path, "Record verification event terminal"))
    assert state["retry_kind"] == "known_no_evaluation"
    assert state["retryable"] is True


def test_root_and_consumer_share_event_semantics_despite_reviewed_ci_fingerprint_roles():
    source = yaml.load(
        (ROOT / ".github/workflows/agents-verifier.yml").read_text(), Loader=yaml.BaseLoader
    )
    consumer = yaml.load(
        (ROOT / "templates/consumer-repo/.github/workflows/agents-verifier.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    for key in ("verification_event", "verification_material", "verification_predecessor"):
        assert (
            source["on"]["workflow_dispatch"]["inputs"][key]
            == consumer["on"]["workflow_dispatch"]["inputs"][key]
        )
    source_with = source["jobs"]["verifier"]["with"]
    consumer_with = consumer["jobs"]["verifier"]["with"]
    assert {key: value for key, value in source_with.items() if key != "ci_workflows"} == {
        key: value for key, value in consumer_with.items() if key != "ci_workflows"
    }
    assert source["jobs"]["acceptance-gates"] == consumer["jobs"]["acceptance-gates"]
    assert json.loads(source_with["ci_workflows"]) == ["pr-11-ci-smoke.yml", "selftest-ci.yml"]
    assert json.loads(consumer_with["ci_workflows"]) == ["ci.yml"]
    assert "persist-fingerprint" not in source["jobs"]
    assert "persist-fingerprint" in consumer["jobs"]


@pytest.mark.parametrize("ignored_provider", ["openai", "anthropic", "auto", "github-models"])
def test_authored_compare_command_and_assessment_ignore_unused_provider(tmp_path, ignored_provider):
    (tmp_path / ".workflows-lib").symlink_to(ROOT, target_is_directory=True)
    fake_python = tmp_path / "python"
    fake_python.write_text(
        f"#!{sys.executable}\n"
        + """import json,sys
from pathlib import Path
Path('invocation.json').write_text(json.dumps(sys.argv[1:]))
print(json.dumps({'results':[{'used_llm':False,'verdict':'UNVERIFIABLE_INPUT'}],'report':'Offline contract proof; no provider invoked.'}))
"""
    )
    fake_python.chmod(0o755)
    context = tmp_path / "context.md"
    context.write_text("Authentic collected input.")
    result = subprocess.run(
        ["bash", "-c", authored("Run multi-provider comparison")["run"]],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
            "VERIFIER_CONTEXT_PATH": str(context),
            "VERIFIER_DIFF_PATH": "",
            "VERIFIER_MODEL": "selected-primary",
            "VERIFIER_MODEL2": "",
            "VERIFIER_PROVIDER": ignored_provider,
            "VERIFIER_SEMANTIC_MODE": "0",
            "VERIFIER_EVIDENCE_PROFILE": "standard",
            "GITHUB_OUTPUT": str(tmp_path / "outputs"),
        },
    )
    assert result.returncode == 0, result.stderr
    invocation = json.loads((tmp_path / "invocation.json").read_text())
    assert invocation[-2:] == ["--model", "selected-primary"]
    assert "--provider" not in invocation
    assert ignored_provider not in invocation
    code = "const {assessmentIdentity}=require('./.github/scripts/verification_event.js');process.stdout.write(JSON.stringify(assessmentIdentity(JSON.parse(process.argv[1]))));"
    normalized = subprocess.run(
        [
            "node",
            "-e",
            code,
            json.dumps(
                {
                    "mode": "compare",
                    "provider": ignored_provider,
                    "model": "selected-primary",
                    "model2": "",
                    "canonical": True,
                }
            ),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    identity = json.loads(normalized.stdout)
    assert identity["provider"] == ""
    assert identity["model2"] == "selected-primary"
