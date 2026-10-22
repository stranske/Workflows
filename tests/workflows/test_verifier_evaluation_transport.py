"""Execute the authored evaluate shell with an inert provider-command boundary."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/reusable-agents-verifier.yml"


def _run(tmp_path, *, raw="", exit_code=0, stderr="", secret=""):
    workflow = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    steps = workflow["jobs"]["verifier"]["steps"]
    step = next(s for s in steps if s.get("id") == "llm_evaluate")
    identity = next(
        s for s in steps if s.get("name") == "Record verifier input identity for model evaluation"
    )
    values = {
        "inputs.model": "claude-sonnet-5-5",
        "inputs.provider": "anthropic",
        "inputs.mode": "evaluate",
        "steps.agent.outputs.agent_label || ''": "agent:codex",
        "steps.agent.outputs.from_label || ''": "from:codex",
        "steps.context.outputs.context_path": "verifier-context.md",
        "steps.context.outputs.diff_path": "verifier-pr-diff.patch",
        "steps.context.outputs.chain_depth": "0",
        "steps.context.outputs.chain_depth || '0'": "0",
        "steps.context.outputs.target_sha": "b" * 40,
        "steps.context.outputs.pr_number": "4175",
        "inputs.ci_workflows": '["ci.yml"]',
        "inputs.evidence_profile": "expanded",
    }

    def render(text):
        return re.sub(r"\$\{\{\s*(.*?)\s*\}\}", lambda m: values[m[1]], text)

    (tmp_path / ".workflows-lib").symlink_to(ROOT, target_is_directory=True)
    (tmp_path / "verifier-context.md").write_text("# PR 4175\nOriginal request.")
    (tmp_path / "verifier-pr-diff.patch").write_text("+exact changed code\n")
    (tmp_path / "verifier-diff-summary.md").write_text("source.py | 1 +\n")
    output = tmp_path / "provider-stdout"
    output.write_text(raw)
    err = tmp_path / "provider-stderr"
    err.write_text(stderr)
    bin_path = tmp_path / "bin"
    bin_path.mkdir()
    python = bin_path / "python"
    python.write_text(
        f"#!/bin/sh\ncat {shlex.quote(str(output))}\ncat {shlex.quote(str(err))} >&2\nexit {exit_code}\n"
    )
    python.chmod(0o755)
    python3 = bin_path / "python3"
    python3.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n')
    python3.chmod(0o755)
    # No real credentials or tracing configuration reaches the subprocess.
    env = {
        "PATH": str(bin_path) + os.pathsep + os.defpath,
        "PYTHONPATH": ".workflows-lib",
        "PYTHONDONTWRITEBYTECODE": "1",
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_RUN_ID": "1234",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_OUTPUT": str(tmp_path / "outputs"),
        "OPENAI_API_KEY": secret,
        "VERIFIER_EVIDENCE_PROFILE": "expanded",
    }
    identity_result = subprocess.run(
        ["bash", "-c", identity["run"]],
        cwd=tmp_path,
        env={**env, **{k: render(v) for k, v in identity["env"].items()}},
        text=True,
        capture_output=True,
    )
    assert identity_result.returncode == 0, identity_result.stderr
    result = subprocess.run(
        ["bash", "-c", render(step["run"])],
        cwd=tmp_path,
        env={
            **env,
            **{
                k: render(v)
                for k, v in step["env"].items()
                if k
                not in {
                    "GITHUB_TOKEN",
                    "OPENAI_API_KEY",
                    "CLAUDE_API_STRANSKE",
                    "LANGSMITH_API_KEY",
                }
            },
        },
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    outputs = dict(
        line.split("=", 1) for line in Path(env["GITHUB_OUTPUT"]).read_text().splitlines()
    )
    return result, outputs, steps


def _payload(**changes):
    return json.dumps(
        {
            "verdict": "PASS",
            "used_llm": True,
            "provider_used": "anthropic/claude-sonnet-5-5",
            "model": "claude-sonnet-5-5",
            "summary": "Exact source reviewed.",
            **changes,
        }
    )


@pytest.mark.parametrize(
    "raw,exit_code,status",
    [
        ("", 2, "process_failed"),
        ("", 127, "process_failed"),
        (_payload(), 9, "process_failed"),
        ("{invalid", 0, "invalid_output"),
        ("null", 0, "invalid_output"),
        (_payload(confidence=3), 0, "invalid_output"),
        (_payload(used_llm=False), 0, "result_unavailable"),
    ],
)
def test_evaluate_transport_failure_is_unverifiable_with_retained_unknown_effects(
    tmp_path, raw, exit_code, status
):
    result, outputs, _ = _run(
        tmp_path, raw=raw, exit_code=exit_code, stderr="inert evaluator diagnostic"
    )
    receipt = json.loads((tmp_path / "evaluation-execution.json").read_text())
    assert receipt["status"] == status and receipt["exit_code"] == exit_code
    assert receipt["decision_available"] is False and receipt["recoverable"] is True
    assert receipt["model_execution"] == receipt["remote_effects"] == "unconfirmed"
    assert receipt["retry_authority"] is False
    assert outputs["verdict"] == "UNVERIFIABLE_INPUT"
    assert "**Verdict:** UNVERIFIABLE_INPUT" in result.stdout
    assert "**Verdict:** CONCERNS" not in result.stdout
    assert (tmp_path / "evaluation.json").read_text() == raw
    for name, ref in receipt["outputs"].items():
        retained = (tmp_path / name).read_bytes()
        assert (
            ref["bytes"] == len(retained) and ref["sha256"] == hashlib.sha256(retained).hexdigest()
        )
    manifest = (tmp_path / "verifier-input-manifest.json").read_bytes()
    assert receipt["input_manifest"]["sha256"] == hashlib.sha256(manifest).hexdigest()
    identity = json.loads(manifest)
    assert identity["repository"] == "owner/repo" and identity["pr"] == 4175
    assert (
        identity["mode"] == receipt["mode"] == "evaluate"
        and identity["provider_requested"] == "anthropic"
    )
    assert receipt["acceptance_authority"] is False
    assert identity["merge_sha"] == "b" * 40 and identity["source_run_id"] == "1234"
    assert receipt["source_run_attempt"] == "2"


def test_usable_evaluation_keeps_actual_verdict_and_redacts_secret_values_before_retention(
    tmp_path,
):
    secret = "inert-secret-must-not-escape"
    result, outputs, _ = _run(
        tmp_path,
        raw=_payload(summary="Source reviewed. " + secret),
        stderr="diagnostic " + secret,
        secret=secret,
    )
    assert outputs["verdict"] == "PASS" and outputs["execution_status"] == "completed"
    receipt = json.loads((tmp_path / "evaluation-execution.json").read_text())
    assert receipt["decision_available"] is True and receipt["exit_code"] == 0
    for name in (
        "evaluation.json",
        "evaluation-stderr.log",
        "evaluation-execution.json",
        "evaluation-comment.md",
    ):
        assert secret not in (tmp_path / name).read_text()
    assert secret not in result.stdout + result.stderr
    assert "*" * len(secret) in (tmp_path / "evaluation-stderr.log").read_text()


def test_evaluation_upload_and_identity_cover_the_authored_evaluate_mode():
    steps = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)["jobs"]["verifier"]["steps"]
    identity = next(
        s for s in steps if s.get("name") == "Record verifier input identity for model evaluation"
    )
    assert "inputs.mode == 'evaluate'" in identity["if"]
    upload = next(s for s in steps if s.get("name") == "Retain evaluation execution evidence")
    assert "always()" in upload["if"] and "inputs.mode == 'evaluate'" in upload["if"]
    assert set(upload["with"]["path"].splitlines()) >= {
        "evaluation.json",
        "evaluation-stderr.log",
        "evaluation-execution.json",
        "verifier-input-manifest.json",
        "verifier-context.md",
        "verifier-pr-diff.patch",
    }
    assert upload["with"]["retention-days"] == "7"


def test_oversized_streams_remain_bounded_and_stdout_cannot_decide(tmp_path):
    secret = "boundary-inert-secret-must-not-escape"
    stdout_limit = 8 * 1024 * 1024
    stderr_limit = 1024 * 1024
    raw = "x" * (stdout_limit - 10) + secret + "after"
    stderr = "y" * (stderr_limit // 2 - 10) + secret + "z" * stderr_limit + "last diagnostic"
    result, outputs, _ = _run(tmp_path, raw=raw, stderr=stderr, secret=secret)
    receipt = json.loads((tmp_path / "evaluation-execution.json").read_text())
    assert receipt["status"] == "output_truncated"
    assert outputs["verdict"] == "UNVERIFIABLE_INPUT"
    assert receipt["decision_available"] is False and receipt["retry_authority"] is False
    assert receipt["model_execution"] == receipt["remote_effects"] == "unconfirmed"
    for name, original, limit in (
        ("evaluation.json", raw, stdout_limit),
        ("evaluation-stderr.log", stderr, stderr_limit),
    ):
        ref = receipt["outputs"][name]
        assert ref["original_bytes"] == len(original.encode())
        assert ref["original_sha256"] == hashlib.sha256(original.encode()).hexdigest()
        assert ref["original_complete"] and ref["truncated"]
        retained = (tmp_path / name).read_text()
        assert len(retained.encode()) <= limit
        assert secret not in retained and secret[:10] not in retained
    assert "last diagnostic" in (tmp_path / "evaluation-stderr.log").read_text()
    assert secret not in result.stdout + result.stderr
    assert not list(tmp_path.glob("evaluation-raw*"))


def test_retention_read_failure_is_typed_and_does_not_authorize_decision(tmp_path, monkeypatch):
    workflow = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    step = next(s for s in workflow["jobs"]["verifier"]["steps"] if s.get("id") == "llm_evaluate")
    receipt_code = (
        step["run"].split("<<'PYRECEIPT'", 1)[1].split("\n", 1)[1].split("\nPYRECEIPT", 1)[0]
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EVALUATION_EXIT_CODE", "0")
    (tmp_path / "evaluation-raw.json").write_text(_payload())
    (tmp_path / "evaluation-raw-stderr.log").write_text("private inert diagnostic")
    original_open = Path.open

    def fail_read(path, *args, **kwargs):
        if path.name == "evaluation-raw-stderr.log" and args == ("rb",):
            raise OSError("inert read failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_read)
    exec(compile(receipt_code, "authored-evaluation-receipt", "exec"), {})
    receipt = json.loads((tmp_path / "evaluation-execution.json").read_text())
    assert receipt["status"] == "retention_failed" and not receipt["decision_available"]
    assert receipt["outputs"]["evaluation-stderr.log"]["retention_error_type"] == "OSError"
    assert not receipt["outputs"]["evaluation-stderr.log"]["original_complete"]
    assert receipt["model_execution"] == receipt["remote_effects"] == "unconfirmed"
    assert not receipt["retry_authority"]
    assert (tmp_path / "evaluation-stderr.log").read_text() == ""
    assert not list(tmp_path.glob("evaluation-raw*"))


def test_tail_redaction_does_not_expose_partial_credential_after_later_replacement(tmp_path):
    secret = "sensitive-fragment-" + "private-value-" * 6
    secret = secret[:100].ljust(100, "K")
    limit = 1024 * 1024
    overlap = len(secret)
    tail_buffer = limit // 2 + overlap
    # The retained working tail starts one byte into the first secret. Replacing
    # a later full occurrence must not shift that initial fragment into output.
    filler = tail_buffer - (len(secret) - 1) - len(secret) - len("last")
    stderr = "q" * limit + secret + "q" * filler + secret + "last"
    result, _, _ = _run(tmp_path, raw=_payload(), stderr=stderr, secret=secret)
    retained = (tmp_path / "evaluation-stderr.log").read_text()
    assert secret[25:70] not in retained
    assert secret[25:70] not in result.stdout + result.stderr
    assert len(retained.encode()) <= limit and retained.endswith("last")
