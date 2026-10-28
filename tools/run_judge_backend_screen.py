#!/usr/bin/env python3
"""Screen additional verifier-judge backends on the frozen verifier corpus.

The existing MAINT-78 CLI screen (``tools/run_model_eval_cli_screen.py``) measures Codex models
only. This tool applies the SAME cases, the SAME production prompt and the SAME provisional
thresholds to other backends so a candidate judge can be compared with the incumbent before it is
given any PASS authority:

* ``muse-cli``   - the Muse CLI on the owner's subscription login (no API-key spend).
* ``cursor-cli`` - the Cursor CLI in read-only ``ask`` mode.
* ``agy-cli``    - the Antigravity CLI, local use only, with its silent-success guards.
* ``claude-cli`` - the Claude Code CLI with every tool disabled (the Anthropic baseline).
* ``muse-api``   - the Meta Model API with its OWN pay-as-you-go key (``MUSE_API_KEY``). This is a
  different credential from the subscription key stored as ``META_API_KEY``.

Evidence classes are recorded per judge and are never mixed: CLI results are exploratory (a CLI is
a different harness from the production LangChain verifier); only an API backend yields observed
token usage. Nothing here changes production behaviour or promotes a model. A judge that passes the
screen is a *candidate* for the existing capped API confirmation and approval stages.

Never prints a credential. Backends receive only the environment variables they need.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from scripts.langchain import pr_verifier
from tools.model_eval_snapshots import screen_cases, verifier_prompt
from tools.plan_model_eval import ROOT, build_plan

SCHEMA = "workflows-judge-backend-screen/v1"
MUSE_API_DEFAULT_BASE_URL = "https://api.meta.ai/v1"
MUSE_API_DEFAULT_MODEL = "muse-spark-1.2"
# Meta's contributor tier is discounted in exchange for using prompts and completions for training.
# Verifier prompts contain PR diffs, so that tier is refused outright.
CONTRIBUTOR_MARKER = "contributor"
SECRET_ENV_NAMES = {"GH_TOKEN", "GITHUB_TOKEN", "META_API_KEY", "MUSE_API_KEY", "OPENAI_API_KEY"}


@dataclass(frozen=True)
class JudgeOutcome:
    payload: dict[str, Any] | None
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    served_model: str | None = None
    error: str | None = None
    stop: bool = False  # stop screening THIS judge (auth failure, rate limit, unreachable)
    tool_activity: bool = False  # the judge reached for a tool on untrusted PR content
    text: str | None = None  # the model's raw answer, for callers that parse it themselves


class Judge(Protocol):
    name: str
    evidence_class: str
    api_key_calls: bool

    def invoke(self, prompt: str) -> JudgeOutcome: ...


def extract_payload(text: str) -> dict[str, Any] | None:
    """Return the first JSON object in ``text`` that validates as the verifier payload."""
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(text[index:])
        except ValueError:
            continue
        if isinstance(candidate, dict):
            try:
                return pr_verifier.EvaluationPayload.model_validate(candidate).model_dump()
            except ValueError:
                continue
    return None


def _clean_env(keep: set[str] | None = None) -> dict[str, str]:
    """Environment for a judge subprocess: no GitHub or unrelated credentials."""
    keep = keep or set()
    return {
        key: value
        for key, value in os.environ.items()
        if key in keep or (key not in SECRET_ENV_NAMES and not key.endswith(("_TOKEN", "_KEY")))
    }


def _redact(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "<redacted>")
    return text


class MuseCliJudge:
    """Muse CLI headless judge on the subscription login (``META_API_KEY`` is never passed)."""

    name = "muse-cli"
    evidence_class = "exploratory-cli"
    api_key_calls = False

    def __init__(
        self,
        *,
        model: str | None = None,
        effort: str = "medium",
        muse: str = "muse",
        timeout: int = 420,
    ) -> None:
        self.model, self.effort, self.muse, self.timeout = model, effort, muse, timeout

    def invoke(self, prompt: str) -> JudgeOutcome:
        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="judge-muse-") as scratch:
            prompt_file = Path(scratch) / "prompt.md"
            prompt_file.write_text(prompt, encoding="utf-8")
            command = [
                self.muse,
                "exec",
                "--json",
                "--preset",
                "empty",
                "--contributor-mode",
                "off",
                "--no-session-log",
                "--no-foreign-personal-context",
                "--reasoning-effort",
                self.effort,
                "--max-model-steps",
                "4",
                "--prompt-file",
                str(prompt_file),
            ]
            if self.model:
                command += ["--model", self.model]
            try:
                response = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    cwd=scratch,
                    timeout=self.timeout,
                    check=False,
                    env=_clean_env(),
                )
            except subprocess.TimeoutExpired:
                return JudgeOutcome(None, _ms(started), error="Muse CLI timed out", stop=True)
        latency = _ms(started)
        events = []
        for line in response.stdout.splitlines():
            if line.startswith("{"):
                try:
                    events.append(json.loads(line))
                except ValueError:
                    continue
        types = [str(event.get("payload_type", "")) for event in events]
        served = next(
            (
                event["payload"].get("model_id")
                for event in events
                if event.get("payload_type") == "run.model.configured"
            ),
            None,
        )
        if any("tool" in kind for kind in types):
            return JudgeOutcome(
                None,
                latency,
                served_model=served,
                error="Muse CLI emitted a tool event; judge stopped",
                stop=True,
                tool_activity=True,
            )
        terminal = next(
            (
                event["payload"]
                for event in events
                if event.get("payload_type") == "run.terminal.completed"
            ),
            None,
        )
        if response.returncode or terminal is None or terminal.get("terminal") != "completed":
            return JudgeOutcome(
                None, latency, served_model=served, error=f"Muse CLI exited {response.returncode}"
            )
        payload = extract_payload(str(terminal.get("text") or ""))
        error = None if payload else "Invalid verifier JSON"
        return JudgeOutcome(payload, latency, served_model=served, error=error)


class CursorCliJudge:
    """Cursor CLI in read-only ``ask`` mode; ``CURSOR_API_KEY`` comes from the environment."""

    name = "cursor-cli"
    evidence_class = "exploratory-cli"
    api_key_calls = False  # the CLI bills the Cursor account, not an API key meter we can read

    def __init__(
        self, *, model: str | None = None, cursor: str = "cursor-agent", timeout: int = 420
    ) -> None:
        self.model, self.cursor, self.timeout = model, cursor, timeout

    def invoke(self, prompt: str) -> JudgeOutcome:
        started = time.perf_counter()
        command = [self.cursor, "-p", "--output-format", "json", "--mode", "ask", "--trust"]
        if self.model:
            command += ["--model", self.model]
        key = os.environ.get("CURSOR_API_KEY", "")
        if not key:
            return JudgeOutcome(None, 0.0, error="CURSOR_API_KEY is not set", stop=True)
        with tempfile.TemporaryDirectory(prefix="judge-cursor-") as scratch:
            try:
                response = subprocess.run(
                    command,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    cwd=scratch,
                    timeout=self.timeout,
                    check=False,
                    env=_clean_env({"CURSOR_API_KEY"}),
                )
            except subprocess.TimeoutExpired:
                return JudgeOutcome(None, _ms(started), error="Cursor CLI timed out", stop=True)
        latency = _ms(started)
        try:
            envelope = json.loads(response.stdout)
        except ValueError:
            return JudgeOutcome(
                None,
                latency,
                error=_redact(f"Cursor CLI output was not JSON (rc {response.returncode})", [key]),
            )
        usage = envelope.get("usage") or {}
        tokens_in = _int(usage.get("inputTokens"))
        tokens_out = _int(usage.get("outputTokens"))
        if response.returncode or envelope.get("is_error"):
            return JudgeOutcome(
                None,
                latency,
                tokens_in,
                tokens_out,
                error=_redact(f"Cursor CLI error (rc {response.returncode})", [key]),
            )
        payload = extract_payload(str(envelope.get("result") or ""))
        return JudgeOutcome(
            payload,
            latency,
            tokens_in,
            tokens_out,
            served_model=self.model,
            error=None if payload else "Invalid verifier JSON",
            text=str(envelope.get("result") or ""),
        )


class ClaudeCliJudge:
    """Claude Code CLI with every tool disabled, on its own login (the Anthropic baseline)."""

    name = "claude-cli"
    evidence_class = "exploratory-cli"
    api_key_calls = False

    def __init__(
        self, *, model: str | None = None, claude: str = "claude", timeout: int = 420
    ) -> None:
        self.model, self.claude, self.timeout = model, claude, timeout

    def invoke(self, prompt: str) -> JudgeOutcome:
        started = time.perf_counter()
        command = [
            self.claude,
            "-p",
            "--output-format",
            "json",
            "--tools",
            "",
            "--no-session-persistence",
            "--disable-slash-commands",
            "--setting-sources",
            "",
        ]
        if self.model:
            command += ["--model", self.model]
        with tempfile.TemporaryDirectory(prefix="judge-claude-") as scratch:
            try:
                response = subprocess.run(
                    command,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    cwd=scratch,
                    timeout=self.timeout,
                    check=False,
                    env=_clean_env({"CLAUDE_CODE_OAUTH_TOKEN"}),
                )
            except subprocess.TimeoutExpired:
                return JudgeOutcome(None, _ms(started), error="Claude CLI timed out", stop=True)
        latency = _ms(started)
        try:
            envelope = json.loads(response.stdout)
        except ValueError:
            return JudgeOutcome(
                None, latency, error=f"Claude CLI output was not JSON (rc {response.returncode})"
            )
        usage = envelope.get("usage") or {}
        tokens_in = sum(
            _int(usage.get(key)) or 0
            for key in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
        )
        tokens_out = _int(usage.get("output_tokens"))
        served = next(iter(envelope.get("modelUsage") or {}), None)
        if response.returncode or envelope.get("is_error"):
            return JudgeOutcome(
                None,
                latency,
                tokens_in or None,
                tokens_out,
                served,
                f"Claude CLI error (rc {response.returncode})",
            )
        payload = extract_payload(str(envelope.get("result") or ""))
        return JudgeOutcome(
            payload,
            latency,
            tokens_in or None,
            tokens_out,
            served,
            None if payload else "Invalid verifier JSON",
        )


def _contains_tool_event(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("type") in {"tool_use", "tool_result", "tool_call"}:
            return True
        return any(_contains_tool_event(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_tool_event(child) for child in value)
    return False


class CodexCliJudge:
    """The incumbent family: the Codex CLI exactly as the MAINT-78 screen drives it (tools off,
    read-only, ephemeral, strict config). Usage is the CLI's own count."""

    evidence_class = "exploratory-cli"
    api_key_calls = False

    def __init__(self, *, model: str = "gpt-5.6-terra", codex: str = "codex") -> None:
        self.model, self.codex = model, codex
        self.name = model

    def invoke(self, prompt: str) -> JudgeOutcome:
        from tools.run_model_eval_cli_screen import invoke_cli

        result = invoke_cli(self.codex, self.model, prompt)
        return JudgeOutcome(
            result.payload,
            result.latency_ms,
            result.input_tokens or None,
            result.output_tokens or None,
            self.model,
            result.error,
            stop=result.stop_screen,
        )


class AgyCliJudge:
    """Antigravity CLI (``agy``): local use only. Guards against its documented silent-success modes.

    ``--model`` is always explicit (an unmodelled run can exit 0 with no output), the workspace is
    an absolute scratch directory (otherwise it falls back to an internal one), runtime state is
    redirected with ``--gemini_dir``, ``--mode plan`` keeps it read-only, and an empty response is
    an error, never a verdict.
    """

    name = "agy-cli"
    evidence_class = "exploratory-cli"
    api_key_calls = False

    def __init__(
        self, *, model: str = "gemini-4-argon-medium", agy: str = "agy", timeout: int = 480
    ) -> None:
        self.model, self.agy, self.timeout = model, agy, timeout

    def invoke(self, prompt: str) -> JudgeOutcome:
        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="judge-agy-") as scratch:
            command = [
                self.agy,
                "--gemini_dir",
                str(Path(scratch) / ".gemini"),
                "-p",
                "",
                "--input-format",
                "stream-json",
                "--output-format",
                "stream-json",
                "--model",
                self.model,
                "--mode",
                "plan",
                "--add-dir",
                scratch,
                "--print-timeout",
                f"{self.timeout // 60}m",
            ]
            try:
                response = subprocess.run(
                    command,
                    input=json.dumps(
                        {"type": "user", "message": {"role": "user", "content": prompt}}
                    )
                    + "\n",
                    capture_output=True,
                    text=True,
                    cwd=scratch,
                    timeout=self.timeout + 60,
                    check=False,
                    env=_clean_env(),
                )
            except subprocess.TimeoutExpired:
                return JudgeOutcome(None, _ms(started), error="agy timed out", stop=True)
        latency = _ms(started)
        try:
            events = [json.loads(line) for line in response.stdout.splitlines() if line.strip()]
            if any(not isinstance(event, dict) for event in events):
                raise ValueError("invalid stream event")
            if any(_contains_tool_event(event) for event in events):
                return JudgeOutcome(
                    None,
                    latency,
                    error="agy emitted a tool event; judge stopped",
                    stop=True,
                    tool_activity=True,
                )
            envelope = next(
                (
                    event
                    for event in reversed(events)
                    if event.get("type") == "result" or "status" in event
                ),
                {},
            )
            if envelope.get("type") == "result":
                envelope = {
                    **envelope,
                    "status": (
                        "ERROR"
                        if envelope.get("is_error")
                        or envelope.get("subtype") not in {None, "success"}
                        else "SUCCESS"
                    ),
                    "response": envelope.get("result", ""),
                }
        except ValueError:
            return JudgeOutcome(
                None, latency, error=f"agy output was not JSON (rc {response.returncode})"
            )
        usage = envelope.get("usage") or {}
        tokens_in = _int(usage.get("input_tokens"))
        tokens_out = _int(usage.get("output_tokens"))
        text = str(envelope.get("response") or "")
        if response.returncode or envelope.get("status") != "SUCCESS":
            return JudgeOutcome(
                None,
                latency,
                tokens_in,
                tokens_out,
                self.model,
                f"agy status {envelope.get('status')}",
            )
        if not text.strip():
            return JudgeOutcome(
                None, latency, tokens_in, tokens_out, self.model, "agy returned an empty response"
            )
        payload = extract_payload(text)
        return JudgeOutcome(
            payload,
            latency,
            tokens_in,
            tokens_out,
            self.model,
            None if payload else "Invalid verifier JSON",
        )


def muse_api_name(model: str) -> str:
    """The judge name in a screen: the default model keeps the historical name, others are tagged."""
    return "muse-api" if model == MUSE_API_DEFAULT_MODEL else f"muse-api:{model}"


def repo_visibility(repo: str) -> str:
    """GitHub's visibility for ``owner/name`` ("public", "private", "internal"); "unknown" on failure."""
    try:
        run = subprocess.run(
            ["gh", "api", f"repos/{repo}", "--jq", ".visibility"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return run.stdout.strip() or "unknown"


def require_public_sources(repos: set[str], lookup: Callable[[str], str] | None = None) -> None:
    """Contributor tier trains on what it is sent. Allow it only when EVERY prompt is built from
    content already published in a public repository; anything else (private, internal, unknown,
    unpublished local work) refuses, and a lookup failure counts as not public."""
    lookup = lookup or repo_visibility
    not_public = sorted(r for r in repos if lookup(r) != "public")
    if not repos or not_public:
        raise SystemExit(
            "refusing contributor-tier models: prompts must come only from public repositories; "
            f"not confirmed public: {not_public or 'no repositories named'}"
        )


class MuseApiJudge:
    """Meta Model API (OpenAI-compatible chat completions) with its own pay-as-you-go key."""

    name = "muse-api"
    evidence_class = "api-observed"
    api_key_calls = True

    def __init__(
        self,
        *,
        model: str = MUSE_API_DEFAULT_MODEL,
        base_url: str = MUSE_API_DEFAULT_BASE_URL,
        key_env: str = "MUSE_API_KEY",
        timeout: int = 420,
        allow_contributor_tier: bool = False,
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        if CONTRIBUTOR_MARKER in model.lower() and not allow_contributor_tier:
            raise ValueError(
                "refusing a contributor-tier model: it may train on prompts, and verifier "
                "prompts contain PR diffs"
            )
        self.name = muse_api_name(model)
        self.model, self.base_url, self.key_env = model, base_url.rstrip("/"), key_env
        self.timeout, self._open = timeout, opener

    def invoke(self, prompt: str) -> JudgeOutcome:
        key = os.environ.get(self.key_env, "")
        if not key:
            return JudgeOutcome(None, 0.0, error=f"{self.key_env} is not set", stop=True)
        body = json.dumps(
            {"model": self.model, "messages": [{"role": "user", "content": prompt}]}
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        started = time.perf_counter()
        try:
            with self._open(request, timeout=self.timeout) as handle:
                raw = handle.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:300]
            finally:
                exc.close()
            return JudgeOutcome(
                None,
                _ms(started),
                error=_redact(f"Muse API HTTP {exc.code}: {detail}", [key]),
                stop=exc.code in {401, 402, 403, 429},
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return JudgeOutcome(
                None, _ms(started), error=_redact(f"Muse API unreachable: {exc}", [key]), stop=True
            )
        latency = _ms(started)
        try:
            data = json.loads(raw)
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            return JudgeOutcome(None, latency, error="Muse API returned an unexpected body")
        usage = data.get("usage") or {}
        payload = extract_payload(str(content or ""))
        return JudgeOutcome(
            payload,
            latency,
            _int(usage.get("prompt_tokens")),
            _int(usage.get("completion_tokens")),
            served_model=str(data.get("model") or self.model),
            error=None if payload else "Invalid verifier JSON",
            text=str(content or ""),
        )


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def wilson_upper(failures: int, total: int, z: float = 1.96) -> float:
    """Wilson upper bound on a failure rate; 1.0 when nothing was observed."""
    if total <= 0:
        return 1.0
    p = failures / total
    denom = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return round(min(1.0, (centre + margin) / denom), 4)


def judge_metrics(
    rows: list[dict[str, Any]],
    *,
    expected_pass: int,
    expected_non_pass: int,
    thresholds: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    prices: tuple[float, float] | None = None,
) -> dict[str, Any]:
    """Per-judge counts plus the provisional-stage verdict (same arithmetic as the Codex screen)."""
    accepted = sum(r["schema_valid"] and r["actual_verdict"] == r["expected_verdict"] for r in rows)
    pass_correct = sum(
        r["schema_valid"] and r["expected_verdict"] == "PASS" and r["actual_verdict"] == "PASS"
        for r in rows
    )
    non_pass_correct = sum(
        r["schema_valid"]
        and r["expected_verdict"] == "NON_PASS"
        and r["actual_verdict"] == "NON_PASS"
        for r in rows
    )
    false_pass = sum(
        r["expected_verdict"] == "NON_PASS" and r["actual_verdict"] == "PASS" for r in rows
    )
    false_fail = sum(
        r["schema_valid"] and r["expected_verdict"] == "PASS" and r["actual_verdict"] == "NON_PASS"
        for r in rows
    )
    schema_errors = sum(not r["schema_valid"] for r in rows)
    tool_activity = sum(bool(r.get("tool_activity")) for r in rows)
    latencies = sorted(r["latency_ms"] for r in rows if r.get("latency_ms") is not None)
    tokens_in = [r["input_tokens"] for r in rows if r.get("input_tokens") is not None]
    tokens_out = [r["output_tokens"] for r in rows if r.get("output_tokens") is not None]
    cost = None
    if prices and tokens_in and tokens_out:
        cost = round((sum(tokens_in) * prices[0] + sum(tokens_out) * prices[1]) / 1_000_000, 6)
    complete = len(rows) == expected_pass + expected_non_pass
    reasons: list[str] = []
    if not complete:
        reasons.append("incomplete: not every case produced a row")
    if false_pass > int(thresholds["maximum_false_passes"]):
        reasons.append(f"false PASS {false_pass} > {thresholds['maximum_false_passes']}")
    if tool_activity:
        reasons.append(f"tool activity on {tool_activity} case(s): result excluded")
    if schema_errors > int(thresholds["maximum_schema_errors"]):
        reasons.append(f"schema errors {schema_errors} > {thresholds['maximum_schema_errors']}")
    recall = pass_correct / expected_pass if expected_pass else 0.0
    if recall < float(thresholds["minimum_pass_recall"]):
        reasons.append(f"PASS recall {recall:.2f} < {thresholds['minimum_pass_recall']}")
    if baseline is not None:
        delta = accepted - baseline["accepted"]
        if delta < int(thresholds["minimum_accuracy_delta_vs_incumbent"]):
            reasons.append(f"accuracy delta {delta} vs incumbent below the minimum")
        if (
            pass_correct < baseline["pass_correct"]
            or non_pass_correct < baseline["non_pass_correct"]
        ):
            reasons.append("regresses a verdict class relative to the incumbent")
    return {
        "rows": len(rows),
        "accepted": accepted,
        "pass_correct": pass_correct,
        "expected_pass": expected_pass,
        "non_pass_correct": non_pass_correct,
        "expected_non_pass": expected_non_pass,
        "false_pass": false_pass,
        "false_fail": false_fail,
        "schema_errors": schema_errors,
        "tool_activity_cases": tool_activity,
        "false_pass_wilson_upper_bound": wilson_upper(false_pass, expected_non_pass),
        "latency_p50_ms": round(statistics.median(latencies), 1) if latencies else None,
        "latency_p95_ms": (
            latencies[min(len(latencies) - 1, math.ceil(0.95 * len(latencies)) - 1)]
            if latencies
            else None
        ),
        "input_tokens": sum(tokens_in) if tokens_in else None,
        "output_tokens": sum(tokens_out) if tokens_out else None,
        "modeled_cost_usd": cost,
        "meets_provisional_screen": complete and not reasons,
        "provisional_screen_reasons": reasons,
    }


def load_baseline_rows(path: Path, model_id: str | None) -> tuple[str, list[dict[str, Any]]]:
    """Rows of the incumbent from a prior Codex CLI screen or from this tool's own output."""
    data = json.loads(path.read_text())
    rows = data.get("rows") or []
    if data.get("schema") == SCHEMA:
        judge = model_id or (data.get("baseline") or {}).get("judge")
        if not judge:
            raise ValueError("baseline model is required when no incumbent is recorded")
        if not any(r["judge"] == judge for r in rows):
            raise ValueError("recorded baseline has no rows")
        return judge, [r for r in rows if r["judge"] == judge]
    judge = model_id or data.get("models", [{}])[0].get("model_id")
    return str(judge), [r for r in rows if r.get("model_id") == judge]


def case_group(case: dict[str, Any]) -> str:
    """real, or the mutation type of a controlled-mutation case, for per-group reporting."""
    snapshot = case.get("production_snapshot") or {}
    if case.get("provenance") == "controlled-mutation":
        return str(snapshot.get("mutation") or "controlled-mutation")
    return "real"


def corpus_cases_with_snapshots(
    corpus: dict[str, Any],
    root: Path,
    *,
    limit_per_group: int | None = None,
    evaluable_only: bool = False,
    include_diagnostic: bool = False,
) -> list[dict[str, Any]]:
    """Every corpus case a prompt can be built for: the screen cases plus cases with a snapshot
    reference or mutation recipe (loaded through ``generate_mutation_cases.load_case``).

    ``limit_per_group`` keeps the first N per (expected verdict, group, category) in corpus order,
    so a bounded pilot is deterministic and still spans every kind of case.
    """
    from tools.generate_mutation_cases import load_case

    seen: set[str] = set()
    cases: list[dict[str, Any]] = []
    for case in corpus.get("screen_cases", []):
        seen.add(case["case_id"])
        cases.append(case)
    for case in corpus.get("cases", []):
        if case["case_id"] in seen or not (case.get("snapshot_ref") or case.get("mutation_recipe")):
            continue
        cases.append(load_case(case, root))
    if not include_diagnostic:
        cases = [c for c in cases if not c.get("diagnostic_only")]
    if evaluable_only:
        # the production prompt's own sufficiency check: an insufficient input measures the capture
        from tools.generate_mutation_cases import coverage_sufficient

        cases = [c for c in cases if coverage_sufficient(c["production_snapshot"])]
    if limit_per_group is None:
        return cases
    kept: dict[tuple[str, str, str], int] = {}
    out = []
    for case in cases:
        key = (case["expected_verdict"], case_group(case), case["category"])
        if kept.get(key, 0) < limit_per_group:
            kept[key] = kept.get(key, 0) + 1
            out.append(case)
    return out


def run_screen(
    judges: list[Judge],
    *,
    corpus: dict[str, Any],
    registry: dict[str, Any],
    policy: dict[str, Any],
    baseline: tuple[str, list[dict[str, Any]]] | None = None,
    baseline_prompt_sha256_by_case: dict[str, str] | None = None,
    prices: dict[str, tuple[float, float]] | None = None,
    cases_override: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    plan = build_plan(corpus, registry, policy)
    if not plan["screen_ready"]:
        raise ValueError(f"candidate screen is not ready: {plan['screen_blockers']}")
    stage = policy["profiles"]["verifier-balanced"]["provisional_stage"]
    cases, blockers = screen_cases(corpus, stage)
    if blockers:
        raise ValueError(f"production-context inputs are invalid: {blockers}")
    if cases_override is not None:
        cases = cases_override
    prompts = {c["case_id"]: verifier_prompt(c["production_snapshot"]) for c in cases}
    prompt_hashes = {
        case_id: hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        for case_id, prompt in prompts.items()
    }
    if baseline is not None:
        expected = {case["case_id"]: case["expected_verdict"] for case in cases}
        base_rows = baseline[1]
        if (
            len(base_rows) != len(expected)
            or {row.get("case_id") for row in base_rows} != expected.keys()
            or any(
                row.get("expected_verdict") != expected.get(row.get("case_id")) for row in base_rows
            )
            or baseline_prompt_sha256_by_case != prompt_hashes
        ):
            raise ValueError("baseline case IDs, truth or prompt hashes differ; rerun the baseline")
    scoring_ids = {c["case_id"] for c in cases if not c.get("diagnostic_only")}
    expected_pass = sum(
        c["expected_verdict"] == "PASS" for c in cases if c["case_id"] in scoring_ids
    )
    expected_non_pass = len(scoring_ids) - expected_pass
    rows: list[dict[str, Any]] = []
    stopped: dict[str, str] = {}
    for judge in judges:
        for case in cases:
            try:
                outcome = judge.invoke(prompts[case["case_id"]])
            except Exception as exc:  # isolate one backend without logging sensitive messages
                outcome = JudgeOutcome(
                    None, 0.0, error=f"{judge.name} failed: {type(exc).__name__}", stop=True
                )
            rows.append(
                {
                    "judge": judge.name,
                    "evidence_class": judge.evidence_class,
                    "case_id": case["case_id"],
                    "category": case["category"],
                    "group": case_group(case),
                    "diagnostic_only": bool(case.get("diagnostic_only")),
                    "expected_verdict": case["expected_verdict"],
                    "actual_verdict": (
                        "PASS"
                        if outcome.payload and outcome.payload["verdict"] == "PASS"
                        else "NON_PASS"
                    ),
                    "raw_verdict": outcome.payload["verdict"] if outcome.payload else None,
                    "schema_valid": outcome.payload is not None,
                    "latency_ms": outcome.latency_ms,
                    "input_tokens": outcome.input_tokens,
                    "output_tokens": outcome.output_tokens,
                    "served_model": outcome.served_model,
                    "tool_activity": outcome.tool_activity,
                    **({"error": outcome.error} if outcome.error else {}),
                }
            )
            if outcome.stop:
                stopped[judge.name] = outcome.error or "stopped"
                break
    base_metrics = None
    retained_baseline = []
    if baseline is not None:
        case_metadata = {c["case_id"]: c for c in cases}
        retained_baseline = [
            {
                **r,
                "judge": baseline[0],
                "group": case_group(case_metadata[r["case_id"]]),
                "diagnostic_only": bool(case_metadata[r["case_id"]].get("diagnostic_only")),
            }
            for r in baseline[1]
        ]
        base_rows = [
            {**r, "schema_valid": r.get("schema_valid", True)}
            for r in retained_baseline
            if r["case_id"] in scoring_ids
        ]
        base_metrics = judge_metrics(
            base_rows,
            expected_pass=expected_pass,
            expected_non_pass=expected_non_pass,
            thresholds=stage,
        )
        base_metrics["judge"] = baseline[0]
    metrics = []
    for judge in judges:
        all_rows = [r for r in rows if r["judge"] == judge.name]
        subset = [r for r in all_rows if r["case_id"] in scoring_ids]
        entry = judge_metrics(
            subset,
            expected_pass=expected_pass,
            expected_non_pass=expected_non_pass,
            thresholds=stage,
            baseline=base_metrics,
            prices=(prices or {}).get(judge.name),
        )
        execution = judge_metrics(
            all_rows,
            expected_pass=sum(c["expected_verdict"] == "PASS" for c in cases),
            expected_non_pass=sum(c["expected_verdict"] != "PASS" for c in cases),
            thresholds=stage,
            prices=(prices or {}).get(judge.name),
        )
        for key in (
            "latency_p50_ms",
            "latency_p95_ms",
            "input_tokens",
            "output_tokens",
            "modeled_cost_usd",
        ):
            entry[key] = execution[key]
        entry.update(
            {
                "judge": judge.name,
                "evidence_class": judge.evidence_class,
                "api_key_calls": len(all_rows) if judge.api_key_calls else 0,
                "stopped": stopped.get(judge.name),
            }
        )
        metrics.append(entry)
    return {
        "schema": SCHEMA,
        "input_fingerprint": plan["input_fingerprint"],
        "scope": (
            "exploratory screen on the frozen verifier corpus; CLI judges are a different harness "
            "from the production verifier; a pass is a reason to run the capped API confirmation, "
            "never a promotion"
        ),
        "case_ids": [c["case_id"] for c in cases],
        "prompt_sha256_by_case": prompt_hashes,
        "provisional_thresholds": {
            k: v for k, v in stage.items() if k.startswith(("maximum_", "minimum_"))
        },
        "baseline": base_metrics,
        "judges": metrics,
        "rows": rows + retained_baseline,
        "approval_ready": False,
    }


def build_judges(args: argparse.Namespace) -> list[Judge]:
    judges: list[Judge] = []
    for name in [item.strip() for item in args.judges.split(",") if item.strip()]:
        if name == "muse-cli":
            judges.append(MuseCliJudge(model=args.muse_model, effort=args.muse_effort))
        elif name == "cursor-cli":
            judges.append(CursorCliJudge(model=args.cursor_model))
        elif name == "agy-cli":
            judges.append(AgyCliJudge(model=args.agy_model))
        elif name == "codex-cli":
            judges.append(CodexCliJudge(model=args.codex_model))
        elif name == "claude-cli":
            judges.append(ClaudeCliJudge(model=args.claude_model))
        elif name == "muse-api":
            judges.append(
                MuseApiJudge(
                    model=args.muse_api_model,
                    base_url=args.muse_api_base_url,
                    allow_contributor_tier=bool(getattr(args, "allow_contributor_tier", False)),
                )
            )
        else:
            raise SystemExit(f"unknown judge: {name}")
    return judges


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=ROOT / "config/model_eval_pilot.json")
    parser.add_argument("--registry", type=Path, default=ROOT / "config/model_registry.json")
    parser.add_argument("--policy", type=Path, default=ROOT / "config/model_selection_policy.json")
    parser.add_argument("--judges", default="muse-cli,cursor-cli")
    parser.add_argument("--muse-model")
    parser.add_argument("--muse-effort", default="medium")
    parser.add_argument("--cursor-model")
    parser.add_argument("--claude-model")
    parser.add_argument("--codex-model", default="gpt-5.6-terra")
    parser.add_argument("--agy-model", default="gemini-4-argon-medium")
    parser.add_argument("--muse-api-model", default=MUSE_API_DEFAULT_MODEL)
    parser.add_argument("--muse-api-base-url", default=MUSE_API_DEFAULT_BASE_URL)
    parser.add_argument(
        "--muse-api-price-in", type=float, help="USD per million input tokens (unverified)"
    )
    parser.add_argument(
        "--muse-api-price-out", type=float, help="USD per million output tokens (unverified)"
    )
    parser.add_argument(
        "--baseline", type=Path, help="prior Codex CLI screen or this tool's output"
    )
    parser.add_argument("--baseline-model")
    parser.add_argument(
        "--cases",
        choices=("screen", "all", "evaluable"),
        default="screen",
        help="screen: the 8 captured screen cases; all: every case with a snapshot or recipe; "
        "evaluable: those whose production prompt is sufficient (the approval set)",
    )
    parser.add_argument(
        "--include-diagnostic",
        action="store_true",
        help="with --cases all/evaluable: also run diagnostic-only cases (the failed-CI mutants)",
    )
    parser.add_argument(
        "--limit-per-group",
        type=int,
        help="with --cases all: keep the first N per verdict, group and category",
    )
    parser.add_argument(
        "--allow-contributor-tier",
        action="store_true",
        help="allow *-contributor models, which may train on prompts; refused unless every case "
        "repository is confirmed public",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    prices = {}
    if args.muse_api_price_in is not None and args.muse_api_price_out is not None:
        prices[muse_api_name(args.muse_api_model)] = (
            args.muse_api_price_in,
            args.muse_api_price_out,
        )
    baseline = load_baseline_rows(args.baseline, args.baseline_model) if args.baseline else None
    baseline_hashes = (
        json.loads(args.baseline.read_text()).get("prompt_sha256_by_case")
        if args.baseline
        else None
    )
    corpus = json.loads(args.corpus.read_text())
    if args.allow_contributor_tier:
        require_public_sources(
            {str(c["repo"]) for c in corpus.get("screen_cases", []) + corpus.get("cases", [])}
        )
    override = (
        corpus_cases_with_snapshots(
            corpus,
            ROOT,
            limit_per_group=args.limit_per_group,
            evaluable_only=args.cases == "evaluable",
            include_diagnostic=args.include_diagnostic,
        )
        if args.cases in ("all", "evaluable")
        else None
    )
    payload = run_screen(
        build_judges(args),
        cases_override=override,
        corpus=corpus,
        registry=json.loads(args.registry.read_text()),
        policy=json.loads(args.policy.read_text()),
        baseline=baseline,
        baseline_prompt_sha256_by_case=baseline_hashes,
        prices=prices,
    )
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    for judge in payload["judges"]:
        print(
            f"{judge['judge']}: {judge['accepted']}/{judge['rows']} correct, "
            f"false PASS {judge['false_pass']}, schema errors {judge['schema_errors']}, "
            f"screen {'MEETS' if judge['meets_provisional_screen'] else 'does not meet'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
