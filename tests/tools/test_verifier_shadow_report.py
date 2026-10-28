from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

from tools import verifier_shadow_report as rep

ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "config/verifier_shadow.json").read_text())
CAND = CONFIG["candidates"][0]  # the first candidate; others are exercised below
START = datetime(2026, 10, 22, tzinfo=UTC)


def _record(i, cand="PASS", slot="PASS", day=0.0, cand_ok=True, run=None):
    return {
        "repository": "o/r",
        "run_id": str(run or i),
        "pr_number": str(i),
        "recorded_at": (START + timedelta(days=day)).isoformat(),
        "production_slots": [
            {"provider": "openai", "model": "inc", "verdict": slot, "used_llm": True},
            {"provider": "anthropic", "model": "b", "verdict": "PASS", "used_llm": True},
        ],
        "candidates": [
            {
                "provider": CAND["provider"],
                "model": CAND["model"],
                "verdict": cand if cand_ok else None,
                "used_llm": cand_ok,
                "pipeline": "compare-slot/v2",
            }
        ],
    }


def _eval(records, days):
    return rep.evaluate(records, CONFIG, now=START + timedelta(days=days))["candidates"][0]


def test_meets_after_the_window_with_enough_agreeing_runs():
    records = [_record(i, day=i * 0.5) for i in range(12)]
    out = _eval(records, 8)
    assert out["status"] == "MEETS" and out["paired_runs"] == 12 and out["failed_criteria"] == []


def test_insufficient_reports_exactly_what_is_still_needed():
    out = _eval([_record(i, day=i * 0.2) for i in range(7)], 3)
    assert out["status"] == "INSUFFICIENT"
    assert out["runs_still_needed"] == 3 and out["days_still_needed"] == 4.0


def test_a_run_count_without_the_days_is_still_insufficient():
    out = _eval([_record(i, day=0.1 * i) for i in range(12)], 2)
    assert out["status"] == "INSUFFICIENT" and out["runs_still_needed"] == 0


def test_the_cap_is_reported_as_insufficient_not_as_a_pass():
    out = _eval([_record(i, day=i) for i in range(3)], 25)
    assert out["status"] == "INSUFFICIENT AT CAP"


def test_a_candidate_miss_beyond_the_allowance_does_not_meet_and_is_listed():
    records = [_record(i, day=i * 0.5) for i in range(10)]
    records += [_record(20 + k, cand="PASS", slot="CONCERNS", day=5) for k in range(2)]
    out = _eval(records, 9)
    assert out["status"] == "DOES NOT MEET" and "candidate_misses" in out["failed_criteria"]
    assert len(out["candidate_misses"]) == 2 and "o/r#20" in out["candidate_misses"][0]


def test_one_miss_is_within_the_allowance():
    records = [_record(i, day=i * 0.5) for i in range(11)]
    records.append(_record(30, cand="PASS", slot="CONCERNS", day=5))
    assert _eval(records, 8)["status"] == "MEETS"


def test_too_many_extra_flags_do_not_meet():
    records = [_record(i, day=i * 0.5) for i in range(8)]
    records += [_record(40 + k, cand="CONCERNS", slot="PASS", day=5) for k in range(5)]
    out = _eval(records, 9)
    assert out["status"] == "DOES NOT MEET" and "extra_flags" in out["failed_criteria"]


def test_low_coverage_does_not_meet():
    records = [_record(i, day=i * 0.5) for i in range(10)]
    records += [_record(50 + k, cand_ok=False, day=5) for k in range(5)]
    out = _eval(records, 9)
    assert "coverage" in out["failed_criteria"] and out["status"] == "DOES NOT MEET"


def test_runs_without_a_usable_production_slot_are_not_paired():
    bad = _record(1)
    bad["production_slots"][0]["used_llm"] = False
    assert _eval([bad], 1)["paired_runs"] == 0


def test_the_ledger_never_double_counts_a_run_and_collect_reads_artifact_archives():
    record = _record(1)
    assert len(rep.merge_ledger([record], [dict(record), _record(2)])) == 2

    def archive(rec):
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            z.writestr("verifier-shadow.json", json.dumps(rec))
            z.writestr("comparison.json", "{}")
        return buffer.getvalue()

    now = datetime.now(UTC)
    artifacts = [
        {"id": 1, "name": "comparison-results-1", "created_at": now.isoformat(), "expired": False},
        {"id": 2, "name": "comparison-results-2", "created_at": now.isoformat(), "expired": True},
        {"id": 3, "name": "other", "created_at": now.isoformat(), "expired": False},
        {
            "id": 4,
            "name": "comparison-results-4",
            "created_at": (now - timedelta(days=30)).isoformat(),
            "expired": False,
        },
    ]
    got = rep.collect(
        ["o/r"],
        since=now - timedelta(days=8),
        list_artifacts=lambda repo: artifacts,
        download=lambda repo, i: archive(_record(i)),
    )
    assert [r["run_id"] for r in got] == [
        "1"
    ]  # expired, wrong-name and too-old artifacts are skipped


def test_markdown_states_the_status_the_needs_and_that_nothing_is_promoted():
    text = rep.markdown(rep.evaluate([_record(1)], CONFIG, now=START + timedelta(days=1)))
    assert "INSUFFICIENT" in text and "still needed" in text and "Nothing here promotes" in text


def test_a_met_window_prints_zero_still_needed_not_silence():
    text = rep.markdown(
        rep.evaluate(
            [_record(i, day=i * 0.5) for i in range(12)], CONFIG, now=START + timedelta(days=8)
        )
    )
    assert "**MEETS**" in text and "still needed: 0 paired run(s), 0.0 day(s)" in text
    assert "failed criteria: none" in text


def test_each_candidate_is_judged_on_its_own_window_and_own_baseline():
    other = CONFIG["candidates"][-1]  # an anthropic candidate, baseline = the anthropic slot
    records = []
    for i in range(12):
        record = _record(i, day=i * 0.5)
        record["candidates"].append(
            {
                "provider": other["provider"],
                "model": other["model"],
                "verdict": "PASS",
                "used_llm": True,
                "pipeline": "compare-slot/v2",
            }
        )
        records.append(record)
    result = rep.evaluate(records, CONFIG, now=START + timedelta(days=8))
    by_name = {c["candidate"]: c for c in result["candidates"]}
    first = by_name[f"{CAND['provider']}:{CAND['model']}"]
    second = by_name[f"{other['provider']}:{other['model']}"]
    assert first["status"] == "MEETS" and second["status"] == "MEETS"
    untouched = [c for c in result["candidates"] if c["paired_runs"] == 0]
    assert untouched and all(
        c["status"] == "INSUFFICIENT" for c in untouched
    )  # no data, no verdict


def test_a_late_candidate_starts_its_own_clock():
    late = CONFIG["candidates"][-1]
    records = [_record(i, day=i * 0.5) for i in range(12)]
    records[-1]["candidates"].append(
        {
            "provider": late["provider"],
            "model": late["model"],
            "verdict": "PASS",
            "used_llm": True,
            "pipeline": "compare-slot/v2",
        }
    )
    result = rep.evaluate(records, CONFIG, now=START + timedelta(days=8))
    late_result = next(c for c in result["candidates"] if c["candidate"].endswith(late["model"]))
    assert late_result["days_observed"] < 3  # started at the last record, not at day 0


def test_markdown_opens_with_one_row_per_candidate():
    text = rep.markdown(rep.evaluate([_record(1)], CONFIG, now=START + timedelta(days=1)))
    assert "| Candidate | Status |" in text
    for candidate in CONFIG["candidates"]:
        assert f"| {candidate['provider']}:{candidate['model']} |" in text


def test_entries_from_the_earlier_lenient_pipeline_are_not_evidence():
    old = _record(1)
    del old["candidates"][0]["pipeline"]
    result = _eval([old], 1)
    assert result["paired_runs"] == 0 and result["attempts"] == 0


def test_a_harness_error_is_not_a_verdict():
    """Haiku/opus returned 'Failed to parse JSON' as CONCERNS with used_llm true; that is not a measurement."""
    record = _record(1, cand="CONCERNS")
    record["candidates"][0]["error"] = "Schema repair policy escalated verifier output"
    result = _eval([record], 1)
    assert result["paired_runs"] == 0 and result["attempts"] == 1 and result["coverage"] == 0.0
