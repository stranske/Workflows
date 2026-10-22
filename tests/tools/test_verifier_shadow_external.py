"""External shadow candidates: replay saved verifier inputs through Muse/Cursor-style judges."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from tools import verifier_shadow_external as ext

ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "config/verifier_shadow.json").read_text())
EXTERNAL = ext.external_candidates(CONFIG)
NOW = datetime.now(UTC)


class FakeJudge:
    def __init__(self, verdict="PASS", error=None):
        self.verdict, self.error, self.calls = verdict, error, []

    def invoke(self, prompt):
        self.calls.append(prompt)
        payload = (
            {"verdict": self.verdict, "confidence": 0.9, "concerns": []} if not self.error else None
        )
        return SimpleNamespace(payload=payload, latency_ms=1500.0, error=self.error)


def _zip(context="ctx", with_shadow=True):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        if context is not None:
            z.writestr("verifier-context.md", context)
        z.writestr("verifier-pr-diff.patch", "diff --git a/x b/x\n")
        if with_shadow:
            z.writestr("verifier-shadow.json", json.dumps({"run_id": "77"}))
    return buf.getvalue()


def _setup(blob):
    ledger = [
        {"repository": "o/r", "run_id": "77", "candidates": [{"provider": "openai", "model": "m"}]}
    ]
    artifacts = [
        {"id": 1, "name": "comparison-results-77", "created_at": NOW.isoformat(), "expired": False}
    ]
    return ledger, artifacts, (lambda repo: artifacts), (lambda repo, i: blob)


def _collect(ledger, lister, downloader, factory, **kw):
    return ext.collect_external(
        ledger,
        CONFIG,
        ["o/r"],
        since=NOW - timedelta(days=7),
        max_runs=kw.pop("max_runs", 5),
        list_artifacts=lister,
        download=downloader,
        is_public=kw.pop("is_public", lambda r: True),
        judge_factory=factory,
    )


def test_config_has_muse_and_cursor_as_external_candidates():
    assert {c["provider"] for c in EXTERNAL} == {"muse-api", "cursor-cli"}
    assert all(c["replaces_provider"] == "openai" for c in EXTERNAL)
    names = {c["model"] for c in CONFIG["candidates"]}
    assert not names & {
        "gpt-5.6-luna",
        "gpt-6-sol",
        "claude-sonnet-5",
    }, "an older model is shadowed while a newer one exists"


def test_replay_adds_verdicts_for_every_external_candidate_once(monkeypatch):
    monkeypatch.setattr(ext, "build_prompt", lambda c, d: f"PROMPT:{c}")
    ledger, _, lister, downloader = _setup(_zip())
    judges = {c["provider"]: FakeJudge("CONCERNS") for c in EXTERNAL}
    counts = _collect(ledger, lister, downloader, lambda c: judges[c["provider"]])
    assert counts["judged"] == 1
    added = {(e["provider"], e["verdict"]) for e in ledger[0]["candidates"][1:]}
    assert added == {("muse-api", "CONCERNS"), ("cursor-cli", "CONCERNS")}
    assert all(j.calls == ["PROMPT:ctx"] for j in judges.values())
    again = _collect(ledger, lister, downloader, lambda c: judges[c["provider"]])
    assert again["judged"] == 0 and all(
        len(j.calls) == 1 for j in judges.values()
    )  # never repeated


def test_one_failing_judge_is_recorded_without_stopping_the_other(monkeypatch):
    monkeypatch.setattr(ext, "build_prompt", lambda c, d: "p")
    ledger, _, lister, downloader = _setup(_zip())
    judges = {"muse-api": FakeJudge(error="HTTP 429"), "cursor-cli": FakeJudge("PASS")}
    _collect(ledger, lister, downloader, lambda c: judges[c["provider"]])
    by = {e["provider"]: e for e in ledger[0]["candidates"][1:]}
    assert by["muse-api"]["verdict"] is None and by["muse-api"]["error"] == "HTTP 429"
    assert by["cursor-cli"]["verdict"] == "PASS" and by["cursor-cli"]["used_llm"]


def test_private_repositories_are_never_sent(monkeypatch):
    monkeypatch.setattr(ext, "build_prompt", lambda c, d: "p")
    ledger, _, lister, downloader = _setup(_zip())
    judge = FakeJudge()
    counts = _collect(ledger, lister, downloader, lambda c: judge, is_public=lambda r: False)
    assert counts["skipped_private"] == 1 and not judge.calls and len(ledger[0]["candidates"]) == 1


def test_run_cap_bounds_spend_and_unusable_archives_are_counted(monkeypatch):
    monkeypatch.setattr(ext, "build_prompt", lambda c, d: "p")
    ledger, _, lister, downloader = _setup(_zip())
    capped = _collect(ledger, lister, downloader, lambda c: FakeJudge(), max_runs=0)
    assert capped["capped"] == 1 and len(ledger[0]["candidates"]) == 1
    ledger2, _, lister2, bad = _setup(_zip(context=None))
    assert _collect(ledger2, lister2, bad, lambda c: FakeJudge())["unusable"] == 1


def test_in_workflow_runner_leaves_external_candidates_to_the_report_job():
    from scripts.langchain import verifier_shadow as vs

    calls = []
    record = vs.run_shadow(
        "ctx",
        None,
        {"results": []},
        CONFIG,
        production_verdict="PASS",
        evaluator=lambda *a, **k: calls.append(k["provider"])
        or SimpleNamespace(verdict="PASS", used_llm=True, error=None),
    )
    assert "muse-api" not in calls and "cursor-cli" not in calls
    assert not any(c["provider"] in ("muse-api", "cursor-cli") for c in record["candidates"])
