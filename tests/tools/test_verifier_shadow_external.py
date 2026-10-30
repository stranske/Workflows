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
# the daily mechanism under test, whatever the committed on/off switch says
CONFIG = {**json.loads((ROOT / "config/verifier_shadow.json").read_text()), "enabled": True}
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
        list_artifacts=lambda repo, run_ids: lister(repo),
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
    assert entry["pipeline"] == "compare-slot/v3" and entry["capacity_preflight"] == "skipped"
    assert entry["review"]["verdict"] == "PASS" and entry["review"]["summary"] == "ok"
    assert (
        pv._preflight_input_capacity is before
    ), "the capacity pre-check patch leaked out of the job"


def _record(run_id, pr, *, external=False):
    cands = [{"provider": "openai", "model": "m"}]
    if external:
        cands.append({"provider": "muse-api", "model": "muse-spark-1.3", "external": True})
    return {"repository": "o/r", "run_id": run_id, "pr_number": pr, "candidates": cands}


def _artifacts(*run_ids):
    return [
        {"id": int(r), "name": f"comparison-results-{r}", "created_at": NOW.isoformat()}
        for r in run_ids
    ]


def test_each_pull_request_is_judged_once_on_its_newest_run():
    ledger = [_record("70", "5"), _record("80", "5"), _record("75", "6")]
    judge = FakeJudge()
    counts = _collect(
        ledger,
        lambda repo: _artifacts("70", "80", "75"),
        lambda repo, i: _zip(),
        lambda c: judge,
        max_runs=10,
    )
    judged = {r["run_id"] for r in ledger if len(r["candidates"]) > 1}
    assert judged == {"80", "75"} and counts["judged"] == 2
    assert len(judge.calls) == 2 * len(EXTERNAL)


def test_the_judged_run_stays_the_choice_when_a_newer_run_appears_later():
    ledger = [_record("70", "5", external=True), _record("80", "5")]
    assert ext.chosen_runs(ledger) == {("o/r", "70")}
    judge = FakeJudge()
    _collect(ledger, lambda repo: _artifacts("70", "80"), lambda repo, i: _zip(), lambda c: judge)
    assert len(ledger[1]["candidates"]) == 1, "the PR was judged again on a later run"


def test_records_without_a_pr_number_stand_for_themselves():
    ledger = [_record("1", None), _record("2", None), _record("3", "")]
    assert ext.chosen_runs(ledger) == {("o/r", "1"), ("o/r", "2"), ("o/r", "3")}


def test_no_run_starts_when_a_whole_judge_timeout_no_longer_fits(monkeypatch):
    ledger = [_record("1", "1"), _record("2", "2")]
    now = [1000.0]
    monkeypatch.setattr(ext.time, "monotonic", lambda: now[0])
    seen = []

    def factory(c):
        now[0] += 400  # each judged run burns 400s of the budget
        return FakeJudge()

    counts = ext.collect_external(
        ledger,
        CONFIG,
        ["o/r"],
        since=NOW - timedelta(days=7),
        max_runs=10,
        list_artifacts=lambda repo, run_ids: _artifacts("1", "2"),
        download=lambda repo, i: _zip(),
        is_public=lambda r: True,
        judge_factory=factory,
        deadline=1000.0 + ext.RUN_RESERVE_SECONDS + 100,
        checkpoint=lambda: seen.append(sum(len(r["candidates"]) > 1 for r in ledger)),
    )
    assert counts["judged"] == 1 and counts["out_of_time"] == 1
    assert seen == [1], "the ledger is saved after each judged run, before the next one starts"


def test_reserve_is_derived_from_the_judge_timeout_not_a_second_literal():
    from tools.run_judge_backend_screen import JUDGE_TIMEOUT_SECONDS

    assert ext.RUN_RESERVE_SECONDS > JUDGE_TIMEOUT_SECONDS


def test_main_checkpoints_the_ledger_atomically_and_honours_the_budget(tmp_path, monkeypatch):
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(json.dumps([_record("1", "1")]))
    config_path = tmp_path / "shadow.json"
    config_path.write_text(json.dumps(CONFIG))  # the daily path switched on
    monkeypatch.setattr(ext, "gh_artifacts_for_runs", lambda repo, run_ids: _artifacts("1"))
    monkeypatch.setattr(ext, "gh_download", lambda repo, i: _zip())
    monkeypatch.setattr(ext, "gh_is_public", lambda repo: True)
    monkeypatch.setattr(ext, "make_judge", lambda c: FakeJudge())
    assert (
        ext.main(
            [
                "--ledger",
                str(ledger_path),
                "--repos",
                "o/r",
                "--budget-seconds",
                "5000",
                "--config",
                str(config_path),
            ]
        )
        == 0
    )
    saved = json.loads(ledger_path.read_text())
    assert len(saved[0]["candidates"]) == 1 + len(EXTERNAL) and not list(tmp_path.glob("*.tmp"))
    ledger_path.write_text(json.dumps([_record("1", "1")]))
    ext.main(
        [
            "--ledger",
            str(ledger_path),
            "--repos",
            "o/r",
            "--budget-seconds",
            "1",
            "--config",
            str(config_path),
        ]
    )
    assert len(json.loads(ledger_path.read_text())[0]["candidates"]) == 1, "no budget, no spend"


def test_semantic_mode_runs_are_not_replayed_through_the_legacy_slot_path():
    blob = _zip()
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        files = {n: z.read(n) for n in z.namelist()}
    files["verifier-shadow.json"] = json.dumps({"run_id": "77", "semantic_mode": True}).encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    ledger, _, lister, downloader = _setup(buf.getvalue())
    judge = FakeJudge()
    counts = _collect(ledger, lister, downloader, lambda c: judge)
    assert counts["semantic"] == 1 and counts["judged"] == 0 and not judge.calls


def test_a_run_cannot_make_a_judge_call_that_would_outlive_its_time_budget(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(ext.time, "monotonic", lambda: now[0])
    judge = FakeJudge()
    client = ext.JudgeChatClient(judge, run_deadline=ext.RUN_BUDGET_SECONDS)
    assert client.invoke("first").content  # fits: a whole judge timeout remains
    now[0] = ext.RUN_BUDGET_SECONDS - ext.JUDGE_TIMEOUT_SECONDS + 1  # chunk 2 could overrun
    try:
        client.invoke("second")
    except RuntimeError as exc:
        assert "time budget" in str(exc)
    else:
        raise AssertionError("a call that cannot finish inside the run budget was started")
    assert len(judge.calls) == 1


def test_the_run_budget_covers_more_than_one_sequential_judge_call():
    from tools.run_judge_backend_screen import JUDGE_TIMEOUT_SECONDS

    assert ext.RUN_BUDGET_SECONDS >= 2 * JUDGE_TIMEOUT_SECONDS
    assert ext.RUN_RESERVE_SECONDS == ext.RUN_BUDGET_SECONDS


def test_error_excerpt_keeps_the_tail_where_an_agent_judge_puts_its_json():
    narration = "I will inspect the workspace. " * 40
    answer = narration + '{"verdict": "PASS", "confidence": 0.9}'
    kept = ext.excerpt(answer)
    middle = len(answer) - 600
    assert kept == f"{answer[:300]} [... {middle} chars ...] {answer[-300:]}"
    assert kept.endswith('"confidence": 0.9}') and len(kept) < 700
    assert ext.excerpt("short answer") == "short answer"


def test_an_errored_judge_entry_stores_head_and_tail_of_the_answer(monkeypatch):
    raw = "Narration. " * 100 + '{"verdict": "PASS"}'
    failed = SimpleNamespace(
        verdict="CONCERNS", used_llm=True, error="Failed to parse JSON response", raw_content=raw
    )
    monkeypatch.setattr(ext, "evaluate_like_production", lambda *a, **k: failed)
    entry = ext.entry_for(EXTERNAL[0], FakeJudge(), CONTEXT, DIFF)
    assert entry["error"] == "Failed to parse JSON response"
    assert entry["raw_excerpt"] == ext.excerpt(raw) and entry["raw_excerpt"].endswith('"PASS"}')


def test_an_external_verdict_reached_without_a_model_gets_no_review(monkeypatch):
    floor = SimpleNamespace(
        verdict="UNVERIFIABLE_INPUT", used_llm=False, error=None, confidence=0.0, concerns=[]
    )
    monkeypatch.setattr(ext, "evaluate_like_production", lambda *a, **k: floor)
    entry = ext.entry_for(EXTERNAL[0], FakeJudge(), CONTEXT, DIFF)
    assert entry["verdict"] == "UNVERIFIABLE_INPUT" and "review" not in entry


def test_an_entry_from_an_earlier_pipeline_is_judged_again():
    ledger, _, lister, downloader = _setup(_zip())
    ledger[0]["candidates"] += [
        {
            "provider": c["provider"],
            "model": c["model"],
            "pipeline": "compare-slot/v2",
            "external": True,
        }
        for c in EXTERNAL
    ]
    judge = FakeJudge()
    counts = _collect(ledger, lister, downloader, lambda c: judge)
    assert counts["judged"] == 1 and len(judge.calls) == len(EXTERNAL)
    current = [c for c in ledger[0]["candidates"] if c.get("pipeline") == "compare-slot/v3"]
    assert len(current) == len(EXTERNAL) and all(c.get("review") for c in current)


def test_the_excerpt_cutoff_is_exactly_twice_the_edge():
    at_limit, over = "x" * 600, "y" * 601
    assert ext.excerpt(at_limit) == at_limit
    assert ext.excerpt(over) == f"{'y' * 300} [... 1 chars ...] {'y' * 300}"


def test_the_counts_say_how_many_comparison_artifacts_were_seen():
    ledger, _, lister, downloader = _setup(_zip())
    counts = _collect(ledger, lister, downloader, lambda c: FakeJudge())
    assert counts["artifacts_seen"] == 1


def test_a_failed_listing_is_counted_not_read_as_no_artifacts():
    from tools.verifier_shadow_report import ListingError

    ledger, _, _, downloader = _setup(_zip())

    def lister(repo):
        raise ListingError("o/r page 1: HTTP 500")

    counts = _collect(ledger, lister, downloader, lambda c: FakeJudge())
    assert counts["listing_failed"] == 1 and counts["artifacts_seen"] == 0
