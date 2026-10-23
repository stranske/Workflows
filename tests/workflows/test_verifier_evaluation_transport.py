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


def _run(tmp_path, *, raw="", exit_code=0, stderr="", secret="", fault="", expect_success=True):
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
    python3.write_text(
        f"#!{sys.executable}\n"
        "import contextlib, io, os, sys\n"
        f"fault = {fault!r}\n"
        "if sys.argv[1:] != ['-']:\n"
        "    os.execv(sys.executable, [sys.executable, *sys.argv[1:]])\n"
        "code = sys.stdin.read()\n"
        "generator = 'secret_names = (' in code\n"
        "checker = \"status = receipt['status']\" in code\n"
        "fallback = 'fallback_reason = ' in code\n"
        "if (generator and fault in {'generator', 'fallback'}) or (checker and fault == 'extractor') or (fallback and fault == 'fallback'):\n"
        "    sys.stderr.write(os.environ.get('OPENAI_API_KEY', '') + '\\n')\n"
        "    sys.exit(23)\n"
        "if generator and fault == 'missing_status':\n"
        "    with contextlib.redirect_stdout(io.StringIO()): exec(compile(code, '<stdin>', 'exec'), {'__name__': '__main__'})\n"
        "else:\n"
        "    exec(compile(code, '<stdin>', 'exec'), {'__name__': '__main__'})\n"
        "if generator and fault == 'bad_authority':\n"
        "    import json\n"
        "    from pathlib import Path\n"
        "    target = Path('evaluation-execution.json')\n"
        "    receipt = json.loads(target.read_text())\n"
        "    receipt['acceptance_authority'] = True\n"
        "    target.write_text(json.dumps(receipt))\n"
        "if generator and fault == 'malformed':\n"
        "    from pathlib import Path\n"
        "    Path('evaluation-execution.json').write_text('{invalid')\n"
    )
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
    if fault == "publish":
        output_directory = tmp_path / "not-an-output-file"
        output_directory.mkdir()
        env["GITHUB_OUTPUT"] = str(output_directory)
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
    if expect_success:
        assert result.returncode == 0, result.stderr
    outputs = (
        dict(line.split("=", 1) for line in Path(env["GITHUB_OUTPUT"]).read_text().splitlines())
        if Path(env["GITHUB_OUTPUT"]).is_file()
        else {}
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


def test_redaction_metadata_observes_secret_only_in_discarded_middle(tmp_path):
    secret = "synthetic-middle-only-secret"
    limit = 1024 * 1024
    result, _, _ = _run(
        tmp_path, raw=_payload(), stderr="x" * limit + secret + "y" * limit, secret=secret
    )
    receipt = json.loads((tmp_path / "evaluation-execution.json").read_text())
    ref = receipt["outputs"]["evaluation-stderr.log"]
    assert ref["redacted"] is True
    assert ref["original_redacted"] is True
    assert ref["retained_redacted"] is False
    assert secret not in (tmp_path / "evaluation-stderr.log").read_text()
    assert secret not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "fault", ["generator", "malformed", "bad_authority", "extractor", "missing_status"]
)
def test_receipt_or_extraction_failure_emits_truthful_typed_fallback(tmp_path, fault):
    secret = "synthetic-receipt-error-secret"
    result, outputs, _ = _run(tmp_path, raw=_payload(), secret=secret, fault=fault)
    receipt = json.loads((tmp_path / "evaluation-execution.json").read_text())
    assert receipt["schema"] == "workflows-verifier-evaluation-execution/v1"
    assert receipt["status"] in {"receipt_generation_failed", "receipt_validation_failed"}
    assert (
        receipt["acceptance_authority"]
        is receipt["retry_authority"]
        is receipt["decision_available"]
        is False
    )
    assert receipt["model_execution"] == receipt["remote_effects"] == "unconfirmed"
    assert outputs["verdict"] == "UNVERIFIABLE_INPUT"
    assert outputs["execution_status"] == receipt["status"]
    manifest = (tmp_path / "verifier-input-manifest.json").read_bytes()
    assert receipt["input_manifest"]["sha256"] == hashlib.sha256(manifest).hexdigest()
    assert receipt["repository"] == "owner/repo" and receipt["source_run_id"] == "1234"
    for name, ref in receipt["outputs"].items():
        assert ref["original_complete"] is False
        assert ref["original_sha256"] is ref["original_bytes"] is None
        assert ref["bytes"] == len((tmp_path / name).read_bytes())
        assert ref["sha256"] == hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
    assert len((tmp_path / "evaluation-execution.json").read_bytes()) < 16 * 1024
    from scripts.langchain.pr_verifier import EvaluationResult

    fallback = EvaluationResult.model_validate_json(
        (tmp_path / "evaluation.json").read_text(), strict=True
    )
    assert fallback.verdict == "UNVERIFIABLE_INPUT" and fallback.used_llm is False
    for name in (
        "evaluation.json",
        "evaluation-stderr.log",
        "evaluation-execution.json",
        "evaluation-comment.md",
    ):
        assert secret not in (tmp_path / name).read_text()
    assert secret not in result.stdout + result.stderr


@pytest.mark.parametrize("fault", ["fallback", "publish"])
def test_failed_fallback_or_output_publication_is_workflow_failure(tmp_path, fault):
    result, _, steps = _run(tmp_path, raw=_payload(), fault=fault, expect_success=False)
    assert result.returncode != 0
    job = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)["jobs"]["verifier"]
    evaluate = next(s for s in steps if s.get("id") == "llm_evaluate")
    # Actions computes a failed conclusion from this real nonzero command; neither
    # step nor job may convert it to success. Retention must still run afterward.
    assert evaluate.get("continue-on-error", "false") == "false"
    assert job.get("continue-on-error", "false") == "false"
    retain = next(s for s in steps if s.get("name") == "Retain evaluation execution evidence")
    assert "always()" in retain["if"]
    assert steps.index(retain) > steps.index(evaluate)


@pytest.mark.parametrize("failure", ["api_failure", "missing_payload", "missing_target"])
def test_failed_evaluation_comment_publication_is_not_a_success(tmp_path, failure):
    steps = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)["jobs"]["verifier"]["steps"]
    step = next(s for s in steps if s.get("name") == "Post LLM evaluation comment")
    if failure != "missing_payload":
        (tmp_path / "evaluation-comment.md").write_text("**Verdict:** UNVERIFIABLE_INPUT")
    binary = tmp_path / "bin"
    binary.mkdir()
    (binary / "gh").write_text("#!/bin/sh\nexit 42\n")
    (binary / "gh").chmod(0o755)
    result = subprocess.run(
        [
            "bash",
            "-c",
            step["run"].replace(
                "${{ steps.context.outputs.pr_number }}",
                "" if failure == "missing_target" else "4175",
            ),
        ],
        cwd=tmp_path,
        env={"PATH": str(binary) + os.pathsep + os.defpath},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    upload = next(s for s in steps if s.get("name") == "Retain evaluation execution evidence")
    assert upload.get("continue-on-error", "false") == "false"
    assert upload["with"]["if-no-files-found"] == "error"


@pytest.mark.parametrize("location", ["none", "retained_tail", "chunk_boundary"])
def test_original_and_retained_redaction_metadata_stay_distinct(tmp_path, location):
    secret = "synthetic-metadata-only-secret"
    diagnostic = {
        "none": "Plain non-sensitive diagnostic.",
        "retained_tail": "x" * (1024 * 1024) + secret + "last",
        "chunk_boundary": "x" * (64 * 1024 - 10) + secret + "last",
    }[location]
    result, _, _ = _run(tmp_path, raw=_payload(), stderr=diagnostic, secret=secret)
    ref = json.loads((tmp_path / "evaluation-execution.json").read_text())["outputs"][
        "evaluation-stderr.log"
    ]
    assert ref["original_redacted"] is (location != "none")
    assert ref["retained_redacted"] is (location != "none")
    assert ref["redacted"] == ref["original_redacted"]
    assert secret not in result.stdout + result.stderr
    assert len((tmp_path / "evaluation-stderr.log").read_bytes()) <= 1024 * 1024


def test_multibyte_optional_diagnostic_cannot_discard_a_valid_decision(tmp_path):
    result, outputs, _ = _run(tmp_path, raw=_payload(), stderr="€" * 400000)
    receipt = json.loads((tmp_path / "evaluation-execution.json").read_text())
    assert receipt["status"] == "completed" and receipt["decision_available"] is True
    assert outputs["verdict"] == "PASS"
    retained = (tmp_path / "evaluation-stderr.log").read_bytes()
    assert len(retained) <= 1024 * 1024
    assert retained.decode("utf-8").endswith("€")
    assert "**Verdict:** PASS" in result.stdout
    assert receipt["outputs"]["evaluation-stderr.log"]["bytes"] == len(retained)
