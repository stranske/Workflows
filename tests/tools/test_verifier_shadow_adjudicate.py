"""Blind, evidence-bound adjudication of every evaluation of a verified PR."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from tools import verifier_shadow_adjudicate as adj

ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "config/verifier_shadow.json").read_text())
NOW = datetime(2026, 10, 28, tzinfo=UTC)
CONTEXT = (
    "## Tasks\n- [ ] add the /health route\n## Acceptance Criteria\n"
    "- test_health_route asserts a 200 response\n"
)
DIFF = "+++ b/app.py\n+@app.get('/health')\n+def health(): return {'ok': True}\n"
COMPARISON = {
    "results": [
        {
            "provider_used": "openai",
            "model": "gpt-5.6-terra",
            "used_llm": True,
            "verdict": "CONCERNS",
            "summary": "Route added but test_health_route is not in the diff.",
            "concerns": ["test_health_route is missing"],
        },
        {
            "provider_used": "anthropic",
            "model": "claude-sonnet-5-5",
            "used_llm": True,
            "verdict": "PASS",
            "summary": "The route and its test were added.",
            "concerns": [],
        },
        {"provider_used": "github", "model": "x", "used_llm": False, "verdict": None},
    ]
}
CAND_REVIEW = {
    "verdict": "PASS",
    "summary": "All criteria met; test_health_route covers the 200 response.",
    "concerns": [],
}


def _record(run="7", reviewed=True, day=0.0, all_candidates=True, **extra):
    entries = []
    for c in CONFIG["candidates"] if all_candidates else CONFIG["candidates"][:1]:
        entry = {"provider": c["provider"], "model": c["model"], "pipeline": "compare-slot/v3"}
        entry.update({"verdict": "PASS", "used_llm": True, "error": None})
        if reviewed:
            entry["review"] = dict(CAND_REVIEW)
        entries.append(entry)
    return {
        "repository": "o/r",
        "run_id": run,
        "pr_number": run,
        "recorded_at": (NOW - timedelta(days=day)).isoformat(),
        "candidates": entries,
        **extra,
    }


class FakeClient:
    def __init__(self, answer):
        self.answer, self.prompts = answer, []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        if isinstance(self.answer, Exception):
            raise self.answer
        return SimpleNamespace(content=self.answer)


def _answer(labelled, inaccurate_label=None, quote=True):
    evaluations = []
    for label, _key, _review in labelled:
        bad = label == inaccurate_label
        errors = []
        if bad:
            errors = [
                {
                    "claim": "test_health_route covers the 200 response" if quote else "made up",
                    "evidence": "test_health_route asserts a 200 response",
                    "why": "the diff adds no test",
                }
            ]
        evaluations.append(
            {
                "label": label,
                "accuracy": "inaccurate" if bad else "accurate",
                "verdict_supported": not bad,
                "errors": errors,
                "coverage": [
                    {"id": "C1", "status": "checked"},
                    {"id": "C2", "status": "asserted" if bad else "checked"},
                ],
                "usefulness": 2 if bad else 4,
                "usefulness_reason": "r",
            }
        )
    return json.dumps(
        {
            "criteria": [{"id": "C1", "text": "route"}, {"id": "C2", "text": "test"}],
            "reference_verdict": "CONCERNS",
            "reference_reasoning": "the acceptance test is missing",
            "evaluations": evaluations,
        }
    )


def _labelled(record=None):
    evaluators = adj.evaluators_for(record or _record(), COMPARISON)
    return adj.blind(evaluators, "o/r:7")


def test_every_usable_evaluation_is_included_and_unusable_ones_are_not():
    keys = set(adj.evaluators_for(_record(), COMPARISON))
    assert (
        "production:openai:gpt-5.6-terra" in keys
        and "production:anthropic:claude-sonnet-5-5" in keys
    )
    assert not any(k.startswith("production:github") for k in keys)
    assert sum(k.startswith("candidate:") for k in keys) == len(CONFIG["candidates"])
    old = _record(reviewed=False)
    assert not any(k.startswith("candidate:") for k in adj.evaluators_for(old, COMPARISON))


def test_the_adjudicator_never_sees_which_model_wrote_which_evaluation():
    labelled = _labelled()
    prompt = adj.build_prompt(CONTEXT, DIFF, labelled)
    for name in ("gpt-5.6-terra", "claude-sonnet-5-5", "production", "candidate"):
        assert name not in prompt.split("=== EVALUATIONS ===")[1]
    assert [label for label, _, _ in labelled] == [chr(65 + i) for i in range(len(labelled))]


def test_the_shuffle_is_stable_per_run_and_differs_between_runs():
    first, again = _labelled(), _labelled()
    assert [k for _, k, _ in first] == [k for _, k, _ in again]
    other = adj.blind(adj.evaluators_for(_record(), COMPARISON), "o/r:8")
    orders = {
        tuple(k for _, k, _ in adj.blind(dict.fromkeys("abcdefgh", {}), f"s{i}")) for i in range(5)
    }
    assert len(orders) > 1 and {k for _, k, _ in other} == {k for _, k, _ in first}


def test_a_quoted_error_counts_and_the_ratings_are_keyed_back_to_each_evaluator():
    labelled = _labelled()
    target = next(label for label, key, _ in labelled if key.startswith("candidate:"))
    out = adj.validate(json.loads(_answer(labelled, target)), labelled, CONTEXT, DIFF)
    key = next(k for label, k, _ in labelled if label == target)
    rating = out["ratings"][key]
    assert (
        rating["accuracy"] == "inaccurate" and rating["errors"][0]["why"] == "the diff adds no test"
    )
    assert rating["coverage"] == 0.75 and rating["usefulness"] == 2 and out["discarded_errors"] == 0
    assert out["reference_verdict"] == "CONCERNS" and len(out["criteria"]) == 2


def test_an_error_whose_quotes_cannot_be_found_is_discarded_and_cannot_mark_anyone_down():
    labelled = _labelled()
    target = labelled[0][0]
    out = adj.validate(json.loads(_answer(labelled, target, quote=False)), labelled, CONTEXT, DIFF)
    rating = out["ratings"][labelled[0][1]]
    assert rating["errors"] == [] and rating["accuracy"] == "unsupported"
    assert out["discarded_errors"] == 1


def test_an_evaluation_the_adjudicator_skipped_is_marked_unrated():
    labelled = _labelled()
    answer = json.loads(_answer(labelled))
    answer["evaluations"] = answer["evaluations"][1:]
    out = adj.validate(answer, labelled, CONTEXT, DIFF)
    assert out["ratings"][labelled[0][1]] == {"label": labelled[0][0], "rated": False}


def test_out_of_range_usefulness_and_unknown_labels_are_ignored():
    labelled = _labelled()
    answer = json.loads(_answer(labelled))
    answer["evaluations"][0]["usefulness"] = 9
    answer["evaluations"][0]["accuracy"] = "great"
    rating = adj.validate(answer, labelled, CONTEXT, DIFF)["ratings"][labelled[0][1]]
    assert rating["usefulness"] is None and rating["accuracy"] is None


def test_adjudicate_reads_thinking_blocks_and_records_failures_without_raising():
    record = _record()
    labelled = adj.blind(adj.evaluators_for(record, COMPARISON), "o/r:7")
    blocks = [
        {"type": "thinking", "thinking": "{not json}"},
        {"type": "text", "text": _answer(labelled)},
    ]
    judge = CONFIG["adjudicator"]
    out = adj.adjudicate(record, CONTEXT, DIFF, COMPARISON, FakeClient(blocks), judge)
    assert out["error"] is None and out["model"] == judge["model"] and out["ratings"]
    broken = adj.adjudicate(
        record, CONTEXT, DIFF, COMPARISON, FakeClient(RuntimeError("429")), judge
    )
    assert "429" in broken["error"]
    prose = adj.adjudicate(record, CONTEXT, DIFF, COMPARISON, FakeClient("no json"), judge)
    assert prose["error"] == "adjudicator answer was not a JSON object"
    none = adj.adjudicate(
        _record(reviewed=False), CONTEXT, DIFF, COMPARISON, FakeClient("{}"), judge
    )
    assert none["error"] == "no candidate review to adjudicate"


def test_a_run_waits_for_every_candidate_but_not_past_the_artifact_life():
    wanted = CONFIG["candidates"]
    assert adj.needs_adjudication(_record(), wanted, NOW)
    partial = _record(all_candidates=False, day=1)
    assert not adj.needs_adjudication(partial, wanted, NOW)
    settled = _record(all_candidates=False, day=adj.SETTLE_DAYS)
    assert adj.needs_adjudication(
        settled, wanted, NOW
    ), "a candidate that never answers cannot hold a run"


def test_done_semantic_and_exhausted_runs_are_left_alone_but_a_failure_is_retried():
    wanted = CONFIG["candidates"]
    assert not adj.needs_adjudication(_record(adjudication={"error": None}), wanted, NOW)
    assert not adj.needs_adjudication(_record(semantic_mode=True), wanted, NOW)
    failed = _record(adjudication={"error": "429"}, adjudication_attempts=1)
    assert adj.needs_adjudication(failed, wanted, NOW)
    failed["adjudication_attempts"] = adj.MAX_ATTEMPTS
    assert not adj.needs_adjudication(failed, wanted, NOW)


def _zip(context=CONTEXT, comparison=COMPARISON):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("verifier-context.md", context)
        z.writestr("verifier-pr-diff.patch", DIFF)
        if comparison is not None:
            z.writestr("comparison.json", json.dumps(comparison))
    return buf.getvalue()


def _artifacts(*runs):
    return [
        {"id": int(r), "name": f"comparison-results-{r}", "created_at": NOW.isoformat()}
        for r in runs
    ]


def _run_ledger(ledger, client, **kw):
    seen = []
    counts = adj.adjudicate_ledger(
        ledger,
        CONFIG,
        ["o/r"],
        since=NOW - timedelta(days=7),
        max_runs=kw.pop("max_runs", 10),
        now=NOW,
        list_artifacts=kw.pop("list_artifacts", lambda repo: _artifacts("7", "8")),
        download=kw.pop("download", lambda repo, i: _zip()),
        is_public=kw.pop("is_public", lambda repo: True),
        client_factory=lambda judge: seen.append(judge) or client,
        **kw,
    )
    return counts, seen


def test_the_ledger_pass_adjudicates_each_settled_run_once_with_the_configured_model():
    ledger = [_record("7"), _record("8")]
    labelled = adj.blind(adj.evaluators_for(ledger[0], COMPARISON), "o/r:7")
    client = FakeClient(_answer(labelled))
    saved = []
    counts, seen = _run_ledger(ledger, client, checkpoint=lambda: saved.append(1))
    assert counts["adjudicated"] == 2 and len(client.prompts) == 2 and saved == [1, 1]
    assert seen == [CONFIG["adjudicator"]], "the adjudicator comes from the config, built once"
    assert all(r["adjudication_attempts"] == 1 and not r["adjudication"]["error"] for r in ledger)
    again, _ = _run_ledger(ledger, client)
    assert again["adjudicated"] == 0 and len(client.prompts) == 2


def test_spend_is_bounded_by_the_cap_the_budget_and_public_repositories(monkeypatch):
    client = FakeClient("{}")
    capped, _ = _run_ledger([_record("7"), _record("8")], client, max_runs=1)
    assert capped["capped"] == 1
    private, _ = _run_ledger([_record("7")], client, is_public=lambda repo: False)
    assert private["skipped_private"] == 1
    monkeypatch.setattr(adj.time, "monotonic", lambda: 0.0)
    late, _ = _run_ledger([_record("7")], client, deadline=adj.RUN_RESERVE_SECONDS - 1)
    assert late["out_of_time"] == 1
    unusable, _ = _run_ledger([_record("7")], client, download=lambda r, i: _zip(comparison=None))
    assert unusable["unusable"] == 1


def test_the_run_reserve_is_derived_from_the_call_timeout():
    assert adj.RUN_RESERVE_SECONDS > adj.CALL_TIMEOUT_SECONDS


def test_a_wrong_shaped_answer_is_recorded_as_an_error_never_raised():
    record = _record()
    labelled = adj.blind(adj.evaluators_for(record, COMPARISON), "o/r:7")
    answer = json.loads(_answer(labelled))
    answer["evaluations"][0]["coverage"] = [{"id": "C1", "status": ["checked"]}]
    answer["evaluations"][1]["errors"] = 5
    answer["evaluations"][2]["coverage"] = 3
    out = adj.adjudicate(
        record, CONTEXT, DIFF, COMPARISON, FakeClient(json.dumps(answer)), CONFIG["adjudicator"]
    )
    assert out["error"].startswith("malformed adjudicator answer")


def test_a_wrong_shaped_answer_still_counts_an_attempt_so_retries_stop():
    ledger = [_record("7")]
    client = FakeClient(json.dumps({"criteria": [], "evaluations": [{"label": "A", "errors": 5}]}))
    for _ in range(adj.MAX_ATTEMPTS + 1):
        _run_ledger(ledger, client, list_artifacts=lambda repo: _artifacts("7"))
    assert ledger[0]["adjudication_attempts"] == adj.MAX_ATTEMPTS
    assert len(client.prompts) == adj.MAX_ATTEMPTS


def test_a_corrupt_archive_is_unusable_not_a_crash():
    counts, _ = _run_ledger([_record("7")], FakeClient("{}"), download=lambda r, i: b"not a zip")
    assert counts["unusable"] >= 1


def test_placeholders_inside_the_pr_text_are_not_expanded():
    labelled = _labelled()
    prompt = adj.build_prompt("context mentions {diff} and {evaluations}", DIFF, labelled)
    assert "context mentions {diff} and {evaluations}" in prompt
    assert prompt.count(DIFF.strip()) == 1


def test_an_unsupported_coverage_status_is_a_malformed_answer_and_is_retried():
    record = _record()
    labelled = adj.blind(adj.evaluators_for(record, COMPARISON), "o/r:7")
    for bad in (["checked"], "verified"):
        answer = json.loads(_answer(labelled))
        answer["evaluations"][0]["coverage"] = [{"id": "C1", "status": bad}]
        out = adj.adjudicate(
            record, CONTEXT, DIFF, COMPARISON, FakeClient(json.dumps(answer)), CONFIG["adjudicator"]
        )
        assert out["error"].startswith("malformed adjudicator answer"), bad
        record["adjudication"], record["adjudication_attempts"] = out, 1
        assert adj.needs_adjudication(record, CONFIG["candidates"], NOW)


def test_a_corrupt_compressed_member_is_unusable_and_later_runs_still_go():
    good = _zip()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("verifier-context.md", CONTEXT * 50)
        z.writestr("comparison.json", json.dumps(COMPARISON))
    raw = bytearray(buf.getvalue())
    start = raw.find(b"verifier-context.md") + len("verifier-context.md")
    for i in range(start + 4, start + 40):
        raw[i] ^= 0xFF  # damage the deflated data, not the directory
    ledger = [_record("7"), _record("8")]
    labelled = adj.blind(adj.evaluators_for(ledger[1], COMPARISON), "o/r:8")
    counts, _ = _run_ledger(
        ledger,
        FakeClient(_answer(labelled)),
        download=lambda r, i: bytes(raw) if i == 7 else good,
    )
    assert counts["unusable"] == 1 and counts["adjudicated"] == 1
