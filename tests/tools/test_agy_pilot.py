import json
import subprocess
import sys

import pytest
from tools import agy_pilot
from tools.agy_pilot import ModelCall, Target

SOURCE = "def gap(a, b):\n" "    if a == b:\n" "        return 0\n" "    return a - b\n"
TESTS = (
    "from tools import clamp_mod\n"
    "def test_gap():\n"
    "    assert clamp_mod.gap(2, 2) == 0\n"
    "    assert clamp_mod.gap(5, 3) == 2\n"
    "    assert clamp_mod.gap(3, 5) == -2\n"
)


def _target():
    mutants = agy_pilot.validated_mutants("clamp_mod", SOURCE, TESTS, 3, seed=1)
    return Target("clamp_mod", SOURCE, None, mutants)


def test_candidates_skip_strings_headers_and_comments():
    src = 'def f(a, b):\n    # a < b\n    s = "a == b"\n    return a < b\n'
    lines = {m.line for m in agy_pilot.candidate_mutants(src)}
    assert lines == {4}


def test_only_mutants_the_modules_own_tests_fail_on_are_kept():
    target = _target()
    assert target.mutants, "gap has behavioural mutants"
    for m in target.mutants:
        assert not agy_pilot._run_pytest("clamp_mod", m.source, TESTS)
    assert (
        agy_pilot.validated_mutants("clamp_mod", SOURCE, "def test_x():\n    assert False\n", 3, 1)
        == []
    )


def test_audit_scores_recall_precision_and_resolving_citations():
    target = _target()
    seeded = [m.line for m in target.mutants]
    findings = [
        {"module": "clamp_mod", "line": seeded[0], "issue": "x"},
        {"module": "clamp_mod", "line": 999, "issue": "bogus"},
    ]
    row = agy_pilot.score_audit(findings, target)
    assert (
        row["found"] == 1 and row["reported"] == 2 and row["useful"] == 1 and row["resolving"] == 1
    )
    assert agy_pilot.score_audit([{"module": "other", "line": seeded[0]}], target)["found"] == 0


def test_testgen_requires_clean_pass_then_counts_kills(monkeypatch):
    # Execute only these repository-owned fixture strings in this scoring test.
    trusted_run = agy_pilot._run_pytest
    monkeypatch.setattr(agy_pilot, "_run_pytest", lambda *args, **kwargs: trusted_run(*args))
    target = _target()
    good = agy_pilot.score_testgen(TESTS, target)
    assert good["clean_pass"] and good["killed"] == len(target.mutants)
    failing = agy_pilot.score_testgen(
        "from tools import clamp_mod\ndef test_x():\n    assert clamp_mod.gap(5, 3) == 99\n", target
    )
    assert failing == {"mutants": len(target.mutants), "killed": 0, "clean_pass": False}
    assert agy_pilot.score_testgen("", target)["killed"] == 0


def test_single_and_batched_modes_make_the_expected_number_of_calls_and_empty_is_unusable():
    targets = [_target(), Target("clamp_two", SOURCE, None, _target().mutants)]
    prompts = []

    def backend(prompt):
        prompts.append(prompt)
        return ModelCall(text=json.dumps({"findings": []}), tokens_in=100, tokens_out=10)

    single = agy_pilot.run_pilot(backend, targets, "audit", "single", 4)
    batched = agy_pilot.run_pilot(backend, targets, "audit", "batched", 4)
    assert (single["calls"], batched["calls"]) == (2, 1)
    assert single["tokens_per_item"] == 110 and batched["tokens_per_item"] == 55
    assert single["totals"]["recall"] == 0.0

    empty = agy_pilot.run_pilot(
        lambda p: ModelCall(text="", error="agy returned an empty response"),
        targets,
        "testgen",
        "batched",
        4,
    )
    assert empty["empty_or_unusable"] == 2 and empty["totals"]["kill_rate"] == 0.0


def test_unreported_tokens_stay_none_not_zero():
    result = agy_pilot.run_pilot(lambda p: ModelCall(text="{}"), [_target()], "audit", "single", 1)
    assert result["tokens_per_item"] is None and result["tokens_in"] is None


def test_adjacent_defects_require_distinct_citations():
    mutants = [agy_pilot.Mutant(line, "==", "!=", SOURCE) for line in (2, 3)]
    target = Target("clamp_mod", SOURCE, None, mutants)
    row = agy_pilot.score_audit([{"module": target.name, "line": 2}], target)
    assert row["found"] == row["useful"] == 1
    row = agy_pilot.score_audit([{"module": target.name, "line": 2}] * 2, target)
    assert row["found"] == row["useful"] == 1
    row = agy_pilot.score_audit([{"module": target.name, "line": n} for n in (2, 3)], target)
    assert row["found"] == row["useful"] == 2


@pytest.mark.parametrize("payload", [{"tests": ["bad"]}, {"tests": {}}, {"tests": "bad"}])
def test_malformed_test_batch_is_unusable(payload):
    targets = [Target("one", SOURCE, None), Target("two", SOURCE, None)]
    result = agy_pilot.run_pilot(
        lambda _: ModelCall(text=json.dumps(payload)), targets, "testgen", "batched", 2
    )
    assert result["empty_or_unusable"] == 2


def test_partial_batch_counts_missing_module(monkeypatch):
    monkeypatch.setattr(agy_pilot, "_run_pytest", lambda *a, **k: True)
    targets = [Target("one", SOURCE, None), Target("two", SOURCE, None)]
    result = agy_pilot.run_pilot(
        lambda _: ModelCall(text=json.dumps({"tests": {"one": "def test_ok(): pass"}})),
        targets,
        "testgen",
        "batched",
        2,
    )
    assert [s["usable"] for s in result["scores"]] == [True, False]
    result = agy_pilot.run_pilot(lambda _: ModelCall(text="{}"), targets, "audit", "batched", 2)
    assert result["empty_or_unusable"] == 2


@pytest.mark.parametrize("backend", [agy_pilot.agy_backend, agy_pilot.claude_backend])
@pytest.mark.parametrize(
    "failure", [FileNotFoundError(), subprocess.CompletedProcess([], 1, "{}", "failed")]
)
def test_backend_process_failures_are_recorded(monkeypatch, backend, failure):
    def run(*a, **k):
        if isinstance(failure, Exception):
            raise failure
        return failure

    monkeypatch.setattr(agy_pilot.subprocess, "run", run)
    assert backend("model")("prompt").error


def test_agy_stdin_stream_and_tool_rejection(monkeypatch):
    prompt = "private source-bearing prompt"

    def run(argv, **kw):
        assert all(prompt not in arg for arg in argv)
        assert json.loads(kw["input"])["message"]["content"] == prompt
        assert argv[argv.index("--input-format") + 1] == "stream-json"
        events = [
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "name": "read_file"}]},
            },
            {"type": "result", "subtype": "success", "result": "{}"},
        ]
        return subprocess.CompletedProcess(argv, 0, "\n".join(map(json.dumps, events)), "")

    monkeypatch.setattr(agy_pilot.subprocess, "run", run)
    assert "tool event" in agy_pilot.agy_backend("model")(prompt).error


def test_agy_successful_result_event(monkeypatch):
    # the shape agy 1.4.0 really emits (captured live 2026-10-17); an invented shape passed here
    # while every real call came back empty
    event = {
        "event": "result",
        "result": {
            "status": "SUCCESS",
            "response": '{"findings":[]}',
            "usage": {"input_tokens": 7, "output_tokens": 3},
        },
    }
    monkeypatch.setattr(
        agy_pilot.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess([], 0, json.dumps(event), ""),
    )
    result = agy_pilot.agy_backend("model")("prompt")
    assert not result.error and result.tokens_in == 7 and result.tokens_out == 3
    assert json.loads(result.text) == {"findings": []}


def test_missing_isolation_never_executes_generated_code(monkeypatch):
    monkeypatch.setattr(agy_pilot, "_sandbox_command", lambda *a: None)

    def unexpected(*a, **k):
        raise AssertionError("unconfined subprocess launched")

    monkeypatch.setattr(agy_pilot.subprocess, "run", unexpected)
    assert not agy_pilot._run_pytest("test_mod", "x=1", "def test_x(): pass", isolated=True)


def test_generated_tests_always_request_isolation(monkeypatch):
    def run(*a, **kw):
        assert kw.get("isolated") is True
        return True

    monkeypatch.setattr(agy_pilot, "_run_pytest", run)
    assert agy_pilot.score_testgen("def test_x(): pass", Target("one", SOURCE, None))["clean_pass"]


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS sandbox integration")
def test_generated_test_sandbox_denies_host_files_network_and_secrets(tmp_path, monkeypatch):
    canary = tmp_path / "host-only.txt"
    canary.write_text("private canary")
    monkeypatch.setenv("UNCONVENTIONAL_SECRET", "not-for-generated-code")
    tests = f"""import os, socket
from pathlib import Path
def test_confinement():
    assert "UNCONVENTIONAL_SECRET" not in os.environ
    try:
        Path({str(canary)!r}).read_text()
    except PermissionError:
        pass
    else:
        raise AssertionError("host file read allowed")
    try:
        Path({str(canary)!r}).write_text("changed")
    except PermissionError:
        pass
    else:
        raise AssertionError("host file write allowed")
    with socket.socket() as connection:
        try:
            connection.bind(("127.0.0.1", 0))
        except PermissionError:
            pass
        else:
            raise AssertionError("network access allowed")
"""
    assert agy_pilot._run_pytest("clamp_mod", SOURCE, tests, isolated=True)
    assert canary.read_text() == "private canary"


def test_agy_backend_speaks_agys_real_stream_shape(tmp_path):
    """agy's stream input is {"event":"user","message":{"content":...}} and its answer arrives as
    {"event":"result","result":{...}}; the first version of this backend used another shape and
    every call came back empty."""
    fake = tmp_path / "agy"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "msg = json.loads(sys.stdin.readline())\n"
        "assert msg['event'] == 'user' and msg['message']['content'] == 'hello', msg\n"
        "print(json.dumps({'event': 'init'}))\n"
        "print(json.dumps({'event': 'step_update', 'status': 'done'}))\n"
        "print(json.dumps({'event': 'result', 'result': {'status': 'SUCCESS', 'response': '{\"ok\": 1}',"
        " 'usage': {'input_tokens': 7, 'output_tokens': 3}}}))\n"
    )
    fake.chmod(0o755)
    call = agy_pilot.agy_backend("m", agy=str(fake))("hello")
    assert call.error is None and call.text == '{"ok": 1}'
    assert (call.tokens_in, call.tokens_out) == (7, 3)


def test_agy_backend_treats_a_denied_tool_action_as_an_error_not_an_answer(tmp_path):
    fake = tmp_path / "agy"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "sys.stdin.readline()\n"
        "print(json.dumps({'event': 'result', 'result': {'status': 'SUCCESS', 'response': '',"
        " 'denied_actions': [{'action': 'write_file'}]}}))\n"
    )
    fake.chmod(0o755)
    call = agy_pilot.agy_backend("m", agy=str(fake))("hello")
    assert call.error and call.text == ""


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS sandbox integration")
def test_sibling_imports_work_for_generated_tests_without_host_paths():
    """Modules that import sibling tools must be scoreable in the sandbox: siblings are copied in."""
    tests = (
        "from tools import resolve_mypy_pin\n"
        "import tools\n"
        "def test_sibling_is_a_scratch_copy():\n"
        "    assert 'agy-pilot-' in tools.__file__\n"
        "    assert 'agy-pilot-' in resolve_mypy_pin.__file__\n"
    )
    assert agy_pilot._run_pytest("clamp_mod", SOURCE, tests, isolated=True)


def test_a_quota_error_is_reported_as_such_and_stops_further_calls(tmp_path):
    fake = tmp_path / "agy"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "sys.stdin.readline()\n"
        "print(json.dumps({'event': 'result', 'result': {'status': 'ERROR', 'response': '',"
        " 'error': 'Individual quota reached. Resets in 132h25m10s.'}}))\n"
    )
    fake.chmod(0o755)
    backend = agy_pilot.agy_backend("m", agy=str(fake))
    call = backend("hello")
    assert call.error.startswith(agy_pilot.QUOTA_ERROR) and "132h" in call.error

    calls = []

    def counting(prompt):
        calls.append(prompt)
        return call

    targets = [_target(), Target("two", SOURCE, None, _target().mutants)]
    result = agy_pilot.run_pilot(counting, targets, "audit", "single", 1)
    assert len(calls) == 1 and result["empty_or_unusable"] == 2
    assert any(agy_pilot.QUOTA_ERROR in e for e in result["errors"])
