"""Tests for the judge-backend screen: fakes only, no network and no model calls."""

from __future__ import annotations

import json
import stat
import urllib.error
from pathlib import Path
from typing import Any

import pytest
from tools import run_judge_backend_screen as screen

VERDICT = {
    "verdict": "PASS",
    "confidence": 0.9,
    "scores": {"correctness": 9, "completeness": 9, "quality": 9, "testing": 9, "risks": 9},
    "concerns": [],
    "summary": "ok",
}
THRESHOLDS = {
    "maximum_false_passes": 0,
    "maximum_schema_errors": 0,
    "minimum_pass_recall": 0.5,
    "minimum_accuracy_delta_vs_incumbent": 0,
}


def _row(
    expected: str, actual: str, *, schema_valid: bool = True, latency: float = 10.0
) -> dict[str, Any]:
    return {
        "expected_verdict": expected,
        "actual_verdict": actual,
        "schema_valid": schema_valid,
        "latency_ms": latency,
        "input_tokens": 100,
        "output_tokens": 10,
    }


def _script(path: Path, body: str) -> str:
    path.write_text("#!/bin/bash\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def test_extract_payload_finds_the_verdict_object_in_surrounding_prose():
    text = "Here is my review:\n```json\n" + json.dumps(VERDICT) + "\n```\nThanks."
    assert screen.extract_payload(text)["verdict"] == "PASS"
    assert screen.extract_payload("no json here") is None
    assert screen.extract_payload('{"verdict": "MAYBE"}') is None


def test_wilson_bound_shows_how_little_a_tiny_screen_proves():
    assert screen.wilson_upper(0, 4) == pytest.approx(0.4899, abs=1e-4)
    assert screen.wilson_upper(0, 75) < 0.05
    assert screen.wilson_upper(0, 0) == 1.0


def test_metrics_apply_the_provisional_gate():
    rows = [
        _row("PASS", "PASS"),
        _row("PASS", "PASS"),
        _row("NON_PASS", "NON_PASS"),
        _row("NON_PASS", "NON_PASS"),
    ]
    ok = screen.judge_metrics(rows, expected_pass=2, expected_non_pass=2, thresholds=THRESHOLDS)
    assert ok["accepted"] == 4 and ok["false_pass"] == 0 and ok["meets_provisional_screen"] is True

    false_pass = [*rows[:3], _row("NON_PASS", "PASS")]
    bad = screen.judge_metrics(
        false_pass, expected_pass=2, expected_non_pass=2, thresholds=THRESHOLDS
    )
    assert bad["false_pass"] == 1 and bad["meets_provisional_screen"] is False
    assert any("false PASS" in reason for reason in bad["provisional_screen_reasons"])

    schema = [*rows[:3], _row("NON_PASS", "NON_PASS", schema_valid=False)]
    bad_schema = screen.judge_metrics(
        schema, expected_pass=2, expected_non_pass=2, thresholds=THRESHOLDS
    )
    assert bad_schema["schema_errors"] == 1 and bad_schema["meets_provisional_screen"] is False

    incomplete = screen.judge_metrics(
        rows[:3], expected_pass=2, expected_non_pass=2, thresholds=THRESHOLDS
    )
    assert incomplete["meets_provisional_screen"] is False


def test_metrics_compare_against_the_incumbent_in_both_verdict_classes():
    incumbent = screen.judge_metrics(
        [
            _row("PASS", "PASS"),
            _row("PASS", "PASS"),
            _row("NON_PASS", "NON_PASS"),
            _row("NON_PASS", "NON_PASS"),
        ],
        expected_pass=2,
        expected_non_pass=2,
        thresholds=THRESHOLDS,
    )
    weaker = screen.judge_metrics(
        [
            _row("PASS", "NON_PASS"),
            _row("PASS", "PASS"),
            _row("NON_PASS", "NON_PASS"),
            _row("NON_PASS", "NON_PASS"),
        ],
        expected_pass=2,
        expected_non_pass=2,
        thresholds=THRESHOLDS,
        baseline=incumbent,
    )
    assert weaker["meets_provisional_screen"] is False
    assert any("incumbent" in reason for reason in weaker["provisional_screen_reasons"])


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._raw = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_muse_api_refuses_the_contributor_tier():
    with pytest.raises(ValueError, match="contributor"):
        screen.MuseApiJudge(model="muse-spark-1.3-contributor")


def test_muse_api_request_shape_usage_and_key_handling(monkeypatch):
    monkeypatch.setenv("MUSE_API_KEY", "fixture-not-a-credential")
    seen = {}

    def opener(request, timeout):
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        seen["body"] = json.loads(request.data)
        return _Response(
            {
                "model": "muse-spark-1.2",
                "choices": [{"message": {"content": json.dumps(VERDICT)}}],
                "usage": {"prompt_tokens": 1234, "completion_tokens": 56},
            }
        )

    outcome = screen.MuseApiJudge(opener=opener).invoke("PROMPT")
    assert seen["url"] == "https://api.meta.ai/v1/chat/completions"
    assert seen["auth"] == "Bearer fixture-not-a-credential"
    assert seen["body"]["model"] == "muse-spark-1.2"
    assert seen["body"]["messages"] == [{"role": "user", "content": "PROMPT"}]
    assert (outcome.input_tokens, outcome.output_tokens) == (1234, 56)
    assert outcome.payload["verdict"] == "PASS" and outcome.served_model == "muse-spark-1.2"


def test_muse_api_rate_limit_stops_the_judge_without_leaking_the_key(monkeypatch):
    key = "fixture-not-a-credential"
    monkeypatch.setenv("MUSE_API_KEY", key)

    def opener(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url, 429, "Too Many Requests", {}, _Body(f"rate limited for {key}")
        )

    outcome = screen.MuseApiJudge(opener=opener).invoke("PROMPT")
    assert outcome.stop is True and outcome.payload is None
    assert key not in (outcome.error or "") and "429" in (outcome.error or "")


class _Body:
    def __init__(self, text: str) -> None:
        self._text = text.encode()

    def read(self) -> bytes:
        return self._text

    def close(self) -> None:
        return None


def test_muse_api_missing_key_stops_before_any_request(monkeypatch):
    monkeypatch.delenv("MUSE_API_KEY", raising=False)

    def opener(*_a, **_k):
        raise AssertionError("no request may be made without a key")

    outcome = screen.MuseApiJudge(opener=opener).invoke("PROMPT")
    assert outcome.stop is True and "MUSE_API_KEY" in outcome.error


def _muse_events(*kinds: str, text: str = "", terminal: str = "completed") -> str:
    events = [
        {"payload_type": "run.model.configured", "payload": {"model_id": "muse-wonder-1.0"}},
        *({"payload_type": kind, "payload": {}} for kind in kinds),
        {"payload_type": "run.terminal.completed", "payload": {"terminal": terminal, "text": text}},
    ]
    return "".join(json.dumps(e) + "\n" for e in events)


def test_muse_cli_parses_the_terminal_answer_and_records_the_serving_model(tmp_path, monkeypatch):
    monkeypatch.setenv("META_API_KEY", "must-not-reach-the-child")
    monkeypatch.setenv("GITHUB_TOKEN", "must-not-reach-the-child")
    env_dump = tmp_path / "env.txt"
    out = tmp_path / "events.jsonl"
    out.write_text(_muse_events("run.output.delta", text=json.dumps(VERDICT)))
    fake = _script(tmp_path / "muse", f"env > {env_dump}\ncat {out}\n")
    outcome = screen.MuseCliJudge(muse=fake).invoke("PROMPT")
    assert outcome.payload["verdict"] == "PASS"
    assert outcome.served_model == "muse-wonder-1.0"
    assert outcome.input_tokens is None  # the CLI reports no usage; never invent it
    leaked = env_dump.read_text()
    assert "META_API_KEY" not in leaked and "GITHUB_TOKEN" not in leaked


def test_muse_cli_tool_activity_invalidates_the_judge(tmp_path):
    out = tmp_path / "events.jsonl"
    out.write_text(_muse_events("tool.call.started", text=json.dumps(VERDICT)))
    outcome = screen.MuseCliJudge(muse=_script(tmp_path / "muse", f"cat {out}\n")).invoke("PROMPT")
    # Tool activity stops this judge before another untrusted case is sent.
    assert outcome.stop is True and outcome.tool_activity is True
    assert outcome.payload is None and "tool event" in outcome.error


def test_muse_cli_nonzero_exit_is_an_error_not_a_verdict(tmp_path):
    outcome = screen.MuseCliJudge(muse=_script(tmp_path / "muse", "exit 3\n")).invoke("PROMPT")
    assert outcome.payload is None and "exited 3" in outcome.error


def test_cursor_cli_reads_result_and_usage_and_keeps_only_its_own_key(tmp_path, monkeypatch):
    monkeypatch.setenv("CURSOR_API_KEY", "cur-test-key-not-real")
    monkeypatch.setenv("GITHUB_TOKEN", "must-not-reach-the-child")
    env_dump = tmp_path / "env.txt"
    envelope = {
        "type": "result",
        "is_error": False,
        "result": json.dumps(VERDICT),
        "usage": {"inputTokens": 8716, "outputTokens": 33},
    }
    fake = _script(
        tmp_path / "cursor-agent", f"env > {env_dump}\ncat <<'EOF'\n{json.dumps(envelope)}\nEOF\n"
    )
    outcome = screen.CursorCliJudge(cursor=fake).invoke("PROMPT")
    assert outcome.payload["verdict"] == "PASS"
    assert (outcome.input_tokens, outcome.output_tokens) == (8716, 33)
    dumped = env_dump.read_text()
    assert "CURSOR_API_KEY=cur-test-key-not-real" in dumped and "GITHUB_TOKEN" not in dumped


def test_cursor_cli_error_envelope_and_missing_key(tmp_path, monkeypatch):
    monkeypatch.setenv("CURSOR_API_KEY", "cur-test-key-not-real")
    fake = _script(
        tmp_path / "cursor-agent", 'echo \'{"is_error": true, "result": "boom"}\'\nexit 1\n'
    )
    outcome = screen.CursorCliJudge(cursor=fake).invoke("PROMPT")
    assert outcome.payload is None and "error" in outcome.error.lower()
    monkeypatch.delenv("CURSOR_API_KEY")
    assert screen.CursorCliJudge(cursor=fake).invoke("PROMPT").stop is True


class _FakeJudge:
    api_key_calls = False

    def __init__(self, name: str, verdicts: dict[str, str]) -> None:
        self.name = name
        self.evidence_class = "exploratory-cli"
        self._verdicts = verdicts
        self._cases: list[str] = []

    def bind(self, order: list[str]) -> _FakeJudge:
        self._cases = list(order)
        return self

    def invoke(self, prompt: str) -> screen.JudgeOutcome:
        case_id = self._cases.pop(0)
        payload = {**VERDICT, "verdict": self._verdicts[case_id]}
        return screen.JudgeOutcome(payload, 5.0)


def _frozen():
    root = screen.ROOT
    return (
        json.loads((root / "config/model_eval_pilot.json").read_text()),
        json.loads((root / "config/model_registry.json").read_text()),
        json.loads((root / "config/model_selection_policy.json").read_text()),
    )


def test_screen_runs_the_frozen_corpus_end_to_end_with_fake_judges():
    corpus, registry, policy = _frozen()
    cases, _ = screen.screen_cases(
        corpus, policy["profiles"]["verifier-balanced"]["provisional_stage"]
    )
    order = [c["case_id"] for c in cases]
    truth = {c["case_id"]: ("PASS" if c["expected_verdict"] == "PASS" else "FAIL") for c in cases}
    perfect = _FakeJudge("perfect", truth).bind(order)
    lenient = _FakeJudge("lenient", dict.fromkeys(truth, "PASS")).bind(order)
    result = screen.run_screen([perfect, lenient], corpus=corpus, registry=registry, policy=policy)
    by_name = {j["judge"]: j for j in result["judges"]}
    assert by_name["perfect"]["meets_provisional_screen"] is True
    assert by_name["perfect"]["false_pass"] == 0
    assert by_name["lenient"]["false_pass"] == by_name["lenient"]["expected_non_pass"] > 0
    assert by_name["lenient"]["meets_provisional_screen"] is False
    assert result["approval_ready"] is False
    assert result["schema"] == screen.SCHEMA and len(result["rows"]) == 2 * len(order)


def test_claude_cli_reads_result_usage_and_serving_model_with_tools_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "must-not-reach-the-child")
    args_dump = tmp_path / "args.txt"
    envelope = {
        "type": "result",
        "is_error": False,
        "result": json.dumps(VERDICT),
        "usage": {
            "input_tokens": 2,
            "cache_creation_input_tokens": 2266,
            "cache_read_input_tokens": 535,
            "output_tokens": 4,
        },
        "modelUsage": {"claude-sonnet-5-5": {}},
    }
    fake = _script(
        tmp_path / "claude",
        f"echo \"$@\" > {args_dump}\ncat > /dev/null\ncat <<'EOF'\n{json.dumps(envelope)}\nEOF\n",
    )
    outcome = screen.ClaudeCliJudge(claude=fake, model="sonnet").invoke("PROMPT")
    assert outcome.payload["verdict"] == "PASS" and outcome.served_model == "claude-sonnet-5-5"
    assert (outcome.input_tokens, outcome.output_tokens) == (2 + 2266 + 535, 4)
    called = args_dump.read_text()
    assert (
        "--tools" in called and "--no-session-persistence" in called and "--model sonnet" in called
    )


def test_agy_cli_is_read_only_explicit_about_model_and_rejects_empty_output(tmp_path):
    args_dump = tmp_path / "args.txt"
    ok = {
        "status": "SUCCESS",
        "response": json.dumps(VERDICT),
        "usage": {"input_tokens": 12844, "output_tokens": 55},
    }
    fake = _script(
        tmp_path / "agy",
        f"echo \"$@\" > {args_dump}\ncat <<'EOF'\n{json.dumps(ok)}\nEOF\n",
    )
    outcome = screen.AgyCliJudge(agy=fake, model="gemini-3.8-flash-high").invoke("PROMPT")
    assert outcome.payload["verdict"] == "PASS" and (
        outcome.input_tokens,
        outcome.output_tokens,
    ) == (12844, 55)
    called = args_dump.read_text()
    for needle in ("--mode plan", "--model gemini-3.8-flash-high", "--add-dir", "--gemini_dir"):
        assert needle in called, needle

    empty = {
        "status": "SUCCESS",
        "response": "  \n",
        "usage": {"input_tokens": 12844, "output_tokens": 0},
    }
    silent = _script(tmp_path / "agy2", f"cat <<'EOF'\n{json.dumps(empty)}\nEOF\n")
    result = screen.AgyCliJudge(agy=silent).invoke("PROMPT")
    assert result.payload is None and "empty response" in result.error


def test_tool_activity_is_counted_and_blocks_the_screen():
    rows = [
        _row("PASS", "PASS"),
        _row("PASS", "PASS"),
        _row("NON_PASS", "NON_PASS"),
        _row("NON_PASS", "NON_PASS"),
    ]
    rows[0] = {**rows[0], "schema_valid": False, "tool_activity": True}
    metrics = screen.judge_metrics(
        rows, expected_pass=2, expected_non_pass=2, thresholds=THRESHOLDS
    )
    assert metrics["tool_activity_cases"] == 1 and metrics["meets_provisional_screen"] is False
    assert any("tool activity" in reason for reason in metrics["provisional_screen_reasons"])


@pytest.mark.parametrize("error", [FileNotFoundError, OSError, RuntimeError])
def test_backend_failure_retains_prior_rows_and_runs_other_judges(error):
    corpus, registry, policy = _frozen()
    cases, _ = screen.screen_cases(
        corpus, policy["profiles"]["verifier-balanced"]["provisional_stage"]
    )
    order = [c["case_id"] for c in cases]
    truth = {c["case_id"]: "PASS" if c["expected_verdict"] == "PASS" else "FAIL" for c in cases}

    class Broken:
        name = "broken"
        evidence_class = "exploratory-cli"
        api_key_calls = False

        def invoke(self, prompt):
            raise error("sensitive detail must never be reported")

    result = screen.run_screen(
        [_FakeJudge("first", truth).bind(order), Broken(), _FakeJudge("last", truth).bind(order)],
        corpus=corpus,
        registry=registry,
        policy=policy,
    )
    assert len(result["rows"]) == len(order) * 2 + 1
    failed = next(j for j in result["judges"] if j["judge"] == "broken")
    assert failed["stopped"] == f"broken failed: {error.__name__}"
    assert "sensitive detail" not in json.dumps(result)


def test_baseline_loader_uses_recorded_incumbent_not_alphabetical_candidate(tmp_path):
    path = tmp_path / "screen.json"
    rows = [{"judge": name, "case_id": "c"} for name in ["aaa-candidate", "incumbent"]]
    path.write_text(
        json.dumps({"schema": screen.SCHEMA, "baseline": {"judge": "incumbent"}, "rows": rows})
    )
    assert screen.load_baseline_rows(path, None) == ("incumbent", [rows[1]])
    path.write_text(json.dumps({"schema": screen.SCHEMA, "rows": rows}))
    with pytest.raises(ValueError, match="baseline model"):
        screen.load_baseline_rows(path, None)
    assert screen.load_baseline_rows(path, "aaa-candidate")[1] == [rows[0]]
    path.write_text(
        json.dumps(
            {
                "models": [{"model_id": "incumbent"}],
                "rows": [{"model_id": "incumbent", "case_id": "c"}],
            }
        )
    )
    assert screen.load_baseline_rows(path, None)[0] == "incumbent"


@pytest.mark.parametrize(
    "cls", [screen.MuseCliJudge, screen.CursorCliJudge, screen.ClaudeCliJudge, screen.AgyCliJudge]
)
def test_cli_timeout_stops_only_that_judge(monkeypatch, cls):
    monkeypatch.setenv("CURSOR_API_KEY", "fixture-cursor")

    def timed_out(*args, **kwargs):
        raise screen.subprocess.TimeoutExpired("fixture", 1)

    monkeypatch.setattr(screen.subprocess, "run", timed_out)
    result = cls().invoke("fixture prompt")
    assert result.stop is True and result.payload is None


@pytest.mark.parametrize(
    "cls,envelope",
    [
        (screen.ClaudeCliJudge, "not JSON"),
        (screen.ClaudeCliJudge, json.dumps({"is_error": True, "result": "failure"})),
        (screen.AgyCliJudge, json.dumps({"status": "ERROR", "response": "failure"})),
    ],
)
def test_cli_error_responses_and_credential_filtering(monkeypatch, cls, envelope):
    seen = {}
    monkeypatch.setenv("MUSE_API_KEY", "fixture-muse")
    monkeypatch.setenv("GITHUB_TOKEN", "fixture-github")

    def fake_run(*args, **kwargs):
        seen.update(kwargs)
        return screen.subprocess.CompletedProcess(args[0], 0, envelope, "")

    monkeypatch.setattr(screen.subprocess, "run", fake_run)
    result = cls().invoke("fixture prompt")
    assert result.payload is None and result.error
    assert "MUSE_API_KEY" not in seen["env"] and "GITHUB_TOKEN" not in seen["env"]


def test_http_error_response_body_is_closed(monkeypatch):
    monkeypatch.setenv("MUSE_API_KEY", "fixture-muse")

    class Body(_Body):
        closed = False

        def close(self):
            self.closed = True

    body = Body("rate limit")

    def opener(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 429, "rate limit", {}, body)

    assert screen.MuseApiJudge(opener=opener).invoke("fixture prompt").stop is True
    assert body.closed is True


@pytest.mark.parametrize("cls", [screen.CursorCliJudge, screen.AgyCliJudge])
def test_cli_prompt_is_sent_only_over_stdin(monkeypatch, cls):
    prompt = "private verifier prompt " * 1000
    seen = {}
    monkeypatch.setenv("CURSOR_API_KEY", "fixture-cursor")

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen.update(kwargs)
        event = {"type": "result", "is_error": False, "result": json.dumps(VERDICT)}
        return screen.subprocess.CompletedProcess(command, 0, json.dumps(event), "")

    monkeypatch.setattr(screen.subprocess, "run", fake_run)
    result = cls().invoke(prompt)
    assert result.payload["verdict"] == "PASS"
    assert all(prompt not in argument for argument in seen["command"])
    if cls is screen.AgyCliJudge:
        assert json.loads(seen["input"]) == {
            "type": "user",
            "message": {"role": "user", "content": prompt},
        }
        assert "--input-format" in seen["command"]
    else:
        assert seen["input"] == prompt


def test_agy_stream_tool_activity_stops_the_judge(monkeypatch):
    events = [
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "shell"}]}},
        {"type": "result", "result": json.dumps(VERDICT)},
    ]

    def fake_run(command, **kwargs):
        return screen.subprocess.CompletedProcess(
            command, 0, "\n".join(json.dumps(event) for event in events), ""
        )

    monkeypatch.setattr(screen.subprocess, "run", fake_run)
    result = screen.AgyCliJudge().invoke("fixture prompt")
    assert result.stop is True and result.tool_activity is True and result.payload is None


@pytest.mark.parametrize(
    "output", ["[]", '{"type":"result","subtype":"error_during_execution","result":""}']
)
def test_agy_invalid_or_error_stream_does_not_produce_a_verdict(monkeypatch, output):
    def fake_run(command, **kwargs):
        return screen.subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(screen.subprocess, "run", fake_run)
    result = screen.AgyCliJudge().invoke("fixture prompt")
    assert result.payload is None and result.error
