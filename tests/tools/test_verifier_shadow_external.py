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
    """Answers with the raw JSON text the production parser reads."""

    def __init__(self, verdict="PASS", error=None):
        self.verdict, self.error, self.calls = verdict, error, []

    def invoke(self, prompt):
        self.calls.append(prompt)
        if self.error:
            return SimpleNamespace(payload=None, latency_ms=10.0, error=self.error, text=None)
        text = json.dumps(
            {
                "verdict": self.verdict,
                "confidence": 0.9,
                "concerns": [],
                "summary": "ok",
            }
        )
        return SimpleNamespace(payload=json.loads(text), latency_ms=10.0, error=None, text=text)


CONTEXT = "## Tasks\n- [ ] add foo\n## Acceptance Criteria\n- foo exists\n"
DIFF = "diff --git a/foo.py b/foo.py\n--- a/foo.py\n+++ b/foo.py\n@@ -0,0 +1 @@\n+def foo(): pass\n"


def _zip(context=CONTEXT, with_shadow=True):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        if context is not None:
            z.writestr("verifier-context.md", context)
        z.writestr("verifier-pr-diff.patch", DIFF)
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
    ledger, _, lister, downloader = _setup(_zip())
    judges = {c["provider"]: FakeJudge("CONCERNS") for c in EXTERNAL}
    counts = _collect(ledger, lister, downloader, lambda c: judges[c["provider"]])
    assert counts["judged"] == 1
    assert all(e["error"] is None for e in ledger[0]["candidates"][1:]), ledger[0]["candidates"]
    added = {(e["provider"], e["verdict"]) for e in ledger[0]["candidates"][1:]}
    assert added == {("muse-api", "CONCERNS"), ("cursor-cli", "CONCERNS")}
    assert all(len(j.calls) == 1 and "foo exists" in j.calls[0] for j in judges.values())
    again = _collect(ledger, lister, downloader, lambda c: judges[c["provider"]])
    assert again["judged"] == 0 and all(
        len(j.calls) == 1 for j in judges.values()
    )  # never repeated


def test_one_failing_judge_is_recorded_without_stopping_the_other(monkeypatch):
    ledger, _, lister, downloader = _setup(_zip())
    judges = {"muse-api": FakeJudge(error="HTTP 429"), "cursor-cli": FakeJudge("PASS")}
    _collect(ledger, lister, downloader, lambda c: judges[c["provider"]])
    by = {e["provider"]: e for e in ledger[0]["candidates"][1:]}
    assert by["muse-api"]["verdict"] != "PASS" and "HTTP 429" in (by["muse-api"]["error"] or "")
    assert by["cursor-cli"]["verdict"] == "PASS" and by["cursor-cli"]["used_llm"]
    assert by["cursor-cli"]["error"] is None


def test_private_repositories_are_never_sent(monkeypatch):
    ledger, _, lister, downloader = _setup(_zip())
    judge = FakeJudge()
    counts = _collect(ledger, lister, downloader, lambda c: judge, is_public=lambda r: False)
    assert counts["skipped_private"] == 1 and not judge.calls and len(ledger[0]["candidates"]) == 1


def test_run_cap_bounds_spend_and_unusable_archives_are_counted(monkeypatch):
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


def test_external_judges_run_the_production_slot_path_and_leave_production_untouched():
    from scripts.langchain import pr_verifier as pv

    before = pv._preflight_input_capacity
    ledger, _, lister, downloader = _setup(_zip())
    judge = FakeJudge("PASS")
    _collect(ledger, lister, downloader, lambda c: judge)
    entry = ledger[0]["candidates"][1]
    assert entry["pipeline"] == "compare-slot/v2" and entry["capacity_preflight"] == "skipped"
    assert (
        pv._preflight_input_capacity is before
    ), "the capacity pre-check patch leaked out of the job"
