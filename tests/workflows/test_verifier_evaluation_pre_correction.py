"""Replay the six evaluation-receipt failures on the shell from before the correction.

The frozen ``llm_evaluate`` script is the step at
``9d88a0f572d5a9bd1bba62de9a0f926ed037df6f``, the parent of
``7d37a60ea5dbe59a52d9da91a31af283376df7e2``. Each case is the behavior that
shell produced with an inert evaluator. The subprocess PATH contains only
that evaluator and cat, grep, and cut. The authored shell is run immediately
afterward so a regression that brings one of those failures back fails here.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/reusable-agents-verifier.yml"
LOCAL_UTILITIES = ("cat", "grep", "cut")


def _bash() -> str:
    """Resolve bash from the parent environment before the closed PATH is installed."""
    bash = shutil.which("bash")
    if bash is None:
        raise AssertionError("bash is unavailable")
    return bash


def _local_command_path(bin_path: Path) -> str:
    """Keep the replay on the inert stubs and the utilities the frozen shell calls."""
    for name in LOCAL_UTILITIES:
        source = shutil.which(name)
        if source is None:
            raise AssertionError(f"local utility unavailable: {name}")
        destination = bin_path / name
        if not destination.exists():
            destination.symlink_to(source)
    return str(bin_path)


PRE_CORRECTION_SHELL = (
    ROOT / "tests/fixtures/verifier_evaluation_transport/pre_correction_llm_evaluate.sh"
)
PRE_CORRECTION_SHA256 = "0f30c765f1f295573edfe184a3c753a5181ace62daece522d7c1aacaa220b630"
ORIGINAL_FAILURES = (
    "generator",
    "missing_status",
    "malformed",
    "bad_authority",
    "extractor",
    "discarded_middle",
)
SECRET = "synthetic-middle-only-secret"
EXPRESSIONS = {
    "steps.agent.outputs.agent_label || ''": "",
    "steps.agent.outputs.from_label || ''": "",
}


def _render(text):
    def replace(match):
        key = match.group(1).strip()
        if key not in EXPRESSIONS:
            raise AssertionError(f"unexpected workflow expression: {key}")
        return EXPRESSIONS[key]

    return re.sub(r"\$\{\{\s*(.*?)\s*\}\}", replace, text)


def _pre_correction_step():
    script = PRE_CORRECTION_SHELL.read_bytes()
    assert hashlib.sha256(script).hexdigest() == PRE_CORRECTION_SHA256
    return {"continue-on-error": "true", "run": script.decode()}


def _authored_step():
    workflow = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    return next(
        step for step in workflow["jobs"]["verifier"]["steps"] if step.get("id") == "llm_evaluate"
    )


def _diagnostic(failure):
    if failure != "discarded_middle":
        return "inert evaluator diagnostic"
    # The pre-correction scan only inspected the retained prefix and tail.
    # Place the secret strictly outside both windows, using the same overlap
    # the shell derives from this single unescaped secret value.
    assert json.dumps(SECRET)[1:-1] == SECRET
    limit = 1024 * 1024
    overlap = len(SECRET)
    return "x" * (limit + overlap + 32) + SECRET + "y" * (limit + overlap + 32)


def _payload():
    return json.dumps(
        {
            "verdict": "PASS",
            "used_llm": True,
            "provider_used": "anthropic/claude-sonnet-5-5",
            "model": "claude-sonnet-5-5",
            "summary": "Exact source reviewed.",
        }
    )


def _python_wrapper(failure):
    return "\n".join(
        [
            f"#!{sys.executable}",
            "import contextlib, io, json, os, sys",
            f"fault = {failure!r}",
            "if sys.argv[1:] != ['-']:",
            "    sys.stderr.write('refusing non-stdin python3: %s\\n' % sys.argv[1:])",
            "    sys.exit(98)",
            "code = sys.stdin.read()",
            "generator = 'secret_names = (' in code",
            "checker = \"status = receipt['status']\" in code",
            "if (generator and fault == 'generator') or (checker and fault == 'extractor'):",
            "    sys.stderr.write(os.environ.get('OPENAI_API_KEY', '') + '\\n')",
            "    sys.exit(23)",
            "if generator and fault == 'missing_status':",
            "    with contextlib.redirect_stdout(io.StringIO()):",
            "        exec(compile(code, '<stdin>', 'exec'), {'__name__': '__main__'})",
            "else:",
            "    exec(compile(code, '<stdin>', 'exec'), {'__name__': '__main__'})",
            "if generator and fault == 'bad_authority':",
            "    target = __import__('pathlib').Path('evaluation-execution.json')",
            "    receipt = json.loads(target.read_text())",
            "    receipt['acceptance_authority'] = True",
            "    target.write_text(json.dumps(receipt))",
            "if generator and fault == 'malformed':",
            "    __import__('pathlib').Path('evaluation-execution.json').write_text('{invalid')",
            "",
        ]
    )


def _leaked(work, stdout, stderr):
    """Secret presence in published output, not in the injected provider stream."""
    published = [stdout, stderr]
    for name in (
        "evaluation.json",
        "evaluation-stderr.log",
        "evaluation-execution.json",
        "evaluation-comment.md",
        "evaluation-transport-outputs.env",
        "evaluation-raw.json",
        "evaluation-raw-stderr.log",
        "evaluation-receipt-raw-stderr.log",
        "evaluation-receipt-check-raw-stderr.log",
        "evaluation-fallback-raw-stderr.log",
        "outputs",
    ):
        path = work / name
        if path.is_file():
            published.append(path.read_text(errors="replace"))
    return any(SECRET in text for text in published)


def _first_verdict(outputs):
    for line in outputs.splitlines():
        if line.startswith("verdict="):
            return line.split("=", 1)[1]
    return ""


def _execute(work, step, failure):
    work.mkdir()
    (work / ".workflows-lib").symlink_to(ROOT, target_is_directory=True)
    (work / "verifier-context.md").write_text("# PR 4175\nOriginal request.\n")
    (work / "verifier-pr-diff.patch").write_text("+exact changed code\n")
    stdout_file = work / "provider-stdout"
    stderr_file = work / "provider-stderr"
    stdout_file.write_text(_payload())
    stderr_file.write_text(_diagnostic(failure))
    binaries = work / "bin"
    binaries.mkdir()
    python = binaries / "python"
    python.write_text(
        "#!/bin/sh\n"
        f"cat {shlex.quote(str(stdout_file))}\n"
        f"cat {shlex.quote(str(stderr_file))} >&2\n"
        "exit 0\n"
    )
    python.chmod(0o755)
    python3 = binaries / "python3"
    python3.write_text(_python_wrapper(failure))
    python3.chmod(0o755)
    output = work / "outputs"
    env = {
        "PATH": _local_command_path(binaries),
        "PYTHONPATH": ".workflows-lib",
        "PYTHONDONTWRITEBYTECODE": "1",
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_RUN_ID": "1234",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_OUTPUT": str(output),
        "OPENAI_API_KEY": SECRET,
        "VERIFIER_CONTEXT_PATH": "verifier-context.md",
        "VERIFIER_DIFF_PATH": "verifier-pr-diff.patch",
        "VERIFIER_MODEL": "claude-sonnet-5-5",
        "VERIFIER_PROVIDER": "anthropic",
        "VERIFIER_EVIDENCE_PROFILE": "expanded",
        "HOME": str(work),
    }
    result = subprocess.run(
        [_bash(), "-c", _render(step["run"])],
        cwd=work,
        env=env,
        text=True,
        capture_output=True,
    )
    receipt_path = work / "evaluation-execution.json"
    receipt_text = receipt_path.read_text() if receipt_path.is_file() else None
    receipt = None
    if receipt_text is not None:
        try:
            receipt = json.loads(receipt_text)
        except json.JSONDecodeError:
            receipt = None
    retained_path = work / "evaluation-stderr.log"
    return {
        "rc": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "outputs": output.read_text() if output.is_file() else "",
        "receipt_text": receipt_text,
        "receipt": receipt,
        "retained_stderr": retained_path.read_text() if retained_path.is_file() else "",
        "leaked": _leaked(work, result.stdout, result.stderr),
    }


def _assert_reproduced(failure, step, observed):
    assert step["continue-on-error"] == "true"
    verdict = _first_verdict(observed["outputs"])
    if failure == "generator":
        assert observed["rc"] != 0
        assert observed["receipt_text"] is None
        assert verdict == ""
        assert observed["leaked"] is True
        return
    if failure == "missing_status":
        assert observed["rc"] != 0
        assert verdict == ""
        assert observed["receipt"]["status"] == "completed"
        assert observed["leaked"] is False
        return
    if failure == "malformed":
        assert observed["rc"] == 0
        assert observed["receipt_text"].startswith("{invalid")
        assert verdict == "PASS"
        assert observed["leaked"] is False
        return
    if failure == "bad_authority":
        assert observed["rc"] == 0
        assert observed["receipt"]["acceptance_authority"] is True
        assert verdict == "PASS"
        assert observed["leaked"] is False
        return
    if failure == "extractor":
        assert observed["rc"] == 0
        assert observed["receipt"]["status"] == "completed"
        assert verdict == "PASS"
        assert observed["leaked"] is False
        return
    if failure == "discarded_middle":
        reference = observed["receipt"]["outputs"]["evaluation-stderr.log"]
        assert observed["rc"] == 0
        assert reference["redacted"] is False
        assert "original_redacted" not in reference
        assert SECRET not in observed["retained_stderr"]
        assert observed["leaked"] is False
        return
    raise AssertionError(failure)


def _assert_closed(failure, step, observed):
    assert step.get("continue-on-error", "false") == "false"
    assert observed["rc"] == 0, observed["stderr"][-400:]
    assert observed["leaked"] is False
    verdict = _first_verdict(observed["outputs"])
    if failure == "discarded_middle":
        reference = observed["receipt"]["outputs"]["evaluation-stderr.log"]
        assert observed["receipt"]["status"] == "completed"
        assert verdict == "PASS"
        assert reference["original_redacted"] is True
        assert reference["retained_redacted"] is False
        assert reference["redacted"] is True
        assert SECRET not in observed["retained_stderr"]
        return
    expected = (
        "receipt_generation_failed" if failure == "generator" else "receipt_validation_failed"
    )
    receipt = observed["receipt"]
    assert verdict == "UNVERIFIABLE_INPUT"
    assert receipt["status"] == expected
    assert receipt["acceptance_authority"] is False
    assert receipt["decision_available"] is False
    assert receipt["retry_authority"] is False
    assert receipt["model_execution"] == receipt["remote_effects"] == "unconfirmed"


def test_original_failure_regressions_are_the_six_pre_correction_cases():
    assert len(ORIGINAL_FAILURES) == 6
    assert len(set(ORIGINAL_FAILURES)) == 6


def test_pre_correction_shell_reproduces_six_original_failures(tmp_path):
    """The historical shell shows each failure; the authored shell does not."""
    pre_step = _pre_correction_step()
    authored_step = _authored_step()
    for failure in ORIGINAL_FAILURES:
        reproduced = _execute(tmp_path / f"pre-{failure}", pre_step, failure)
        try:
            _assert_reproduced(failure, pre_step, reproduced)
        except AssertionError as exc:
            raise AssertionError(f"pre-correction {failure} was not reproduced") from exc
        closed = _execute(tmp_path / f"current-{failure}", authored_step, failure)
        try:
            _assert_closed(failure, authored_step, closed)
        except AssertionError as exc:
            raise AssertionError(f"authored shell still shows {failure}") from exc
