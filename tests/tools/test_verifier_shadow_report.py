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
KEY = f"candidate:{CAND['provider']}:{CAND['model']}"
PIPE = "compare-slot/v3"
START = datetime(2026, 10, 22, tzinfo=UTC)


def _rating(accuracy="accurate", coverage=0.9, usefulness=4):
    return {
        "rated": True,
        "accuracy": accuracy,
        "coverage": coverage,
        "usefulness": usefulness,
        "errors": (
            [{"why": "claims the test exists; the diff adds none"}]
            if accuracy == "inaccurate"
            else []
        ),
    }


def _record(
    i,
    cand="PASS",
    slots=("PASS", "PASS"),
    day=0.0,
    cand_ok=True,
    mine=None,
    incumbents=None,
    adjudicated=True,
):
    record = {
        "repository": "o/r",
        "run_id": str(i),
        "pr_number": str(i),
        "recorded_at": (START + timedelta(days=day)).isoformat(),
        "production_slots": [
            {"provider": "openai", "model": "inc", "verdict": slots[0], "used_llm": True},
            {"provider": "anthropic", "model": "b", "verdict": slots[1], "used_llm": True},
        ],
        "candidates": [
            {
                "provider": CAND["provider"],
                "model": CAND["model"],
                "verdict": cand if cand_ok else None,
                "used_llm": cand_ok,
                "pipeline": PIPE,
            }
        ],
    }
    if adjudicated and cand_ok:
        theirs = incumbents or [_rating(), _rating()]
        record["adjudication"] = {
            "error": None,
            "reference_verdict": "PASS",
            "ratings": {
                KEY: mine or _rating(),
                "production:openai:inc": theirs[0],
                "production:anthropic:b": theirs[1],
            },
        }
    return record


def _eval(records, days):
    return rep.evaluate(records, CONFIG, now=START + timedelta(days=days))["candidates"][0]


def test_meets_after_the_window_when_its_work_matches_the_incumbents():
    out = _eval([_record(i, day=i * 0.5) for i in range(12)], 8)
    assert out["status"] == "MEETS" and out["adjudicated_runs"] == 12
    assert out["failed_criteria"] == []


def test_disagreeing_with_a_production_judge_is_not_itself_a_failure():
    """The verifier runs two families on purpose; a split is information, not an error."""
    records = [
        _record(i, cand="PASS", slots=("UNVERIFIABLE_INPUT", "PASS"), day=i * 0.5)
        for i in range(12)
    ]
    records += [
        _record(20 + i, cand="CONCERNS", slots=("PASS", "CONCERNS"), day=6) for i in range(4)
    ]
    out = _eval(records, 8)
    assert out["status"] == "MEETS" and out["warnings"] == []


def test_a_much_higher_inaccurate_share_than_the_incumbents_does_not_meet():
    records = [_record(i, day=i * 0.5) for i in range(8)]
    records += [_record(30 + i, day=5, mine=_rating("inaccurate")) for i in range(4)]
    out = _eval(records, 8)
    assert out["status"] == "DOES NOT MEET" and "inaccuracy" in out["failed_criteria"]
    assert out["inaccurate_share"] == round(4 / 12, 3) and out["incumbent_inaccurate_share"] == 0.0
    assert (
        len(out["inaccurate_runs"]) == 4
        and "diff adds none" in out["inaccurate_runs"][0]["errors"][0]
    )


def test_inaccuracy_is_judged_against_the_incumbents_on_the_same_runs():
    shaky = [_rating("inaccurate"), _rating()]
    records = [
        _record(i, day=i * 0.5, mine=_rating("inaccurate") if i < 3 else None, incumbents=shaky)
        for i in range(12)
    ]
    out = _eval(records, 8)
    assert out["incumbent_inaccurate_share"] == 0.5 and out["inaccurate_share"] == 0.25
    assert "inaccuracy" not in out["failed_criteria"]


def test_shallow_coverage_or_unhelpful_reviews_do_not_meet():
    records = [_record(i, day=i * 0.5, mine=_rating(coverage=0.5, usefulness=2)) for i in range(12)]
    out = _eval(records, 8)
    assert {"rigor", "usefulness"} <= set(out["failed_criteria"])
    assert out["status"] == "DOES NOT MEET"


def test_an_inaccurate_pass_over_two_production_findings_is_decisive_even_early():
    records = [
        _record(1, cand="PASS", slots=("CONCERNS", "FAIL"), mine=_rating("inaccurate")),
    ]
    out = _eval(records, 1)
    assert out["status"] == "DOES NOT MEET" and out["decisive"] == ["o/r#1 (run 1)"]
    assert out["warnings"][0]["kind"] == "pass_against_both_findings"


def test_an_adjudicated_correct_pass_over_two_findings_is_a_warning_not_a_failure():
    records = [_record(i, day=i * 0.5) for i in range(11)]
    records.append(_record(40, cand="PASS", slots=("CONCERNS", "CONCERNS"), day=6))
    out = _eval(records, 8)
    assert out["status"] == "MEETS" and out["decisive"] == []
    assert [w["kind"] for w in out["warnings"]] == ["pass_against_both_findings"]


def test_a_finding_against_two_passes_is_listed_as_a_warning():
    out = _eval([_record(1, cand="CONCERNS", slots=("PASS", "PASS"))], 1)
    assert [w["kind"] for w in out["warnings"]] == ["finding_against_both_passes"]


def test_unverifiable_input_is_not_a_finding_for_the_warnings():
    out = _eval([_record(1, cand="PASS", slots=("UNVERIFIABLE_INPUT", "UNVERIFIABLE_INPUT"))], 1)
    assert out["warnings"] == []


def test_insufficient_reports_exactly_what_is_still_needed():
    out = _eval([_record(i, day=i * 0.2) for i in range(7)], 3)
    assert out["status"] == "INSUFFICIENT"
    assert out["runs_still_needed"] == 3 and out["days_still_needed"] == 4.0


def test_only_adjudicated_runs_count_toward_the_window():
    records = [_record(i, day=i * 0.5, adjudicated=i < 4) for i in range(12)]
    out = _eval(records, 8)
    assert out["adjudicated_runs"] == 4 and out["runs_still_needed"] == 6
    assert out["status"] == "INSUFFICIENT"


def test_a_failed_adjudication_is_not_evidence():
    record = _record(1)
    record["adjudication"]["error"] = "adjudicator answer was not a JSON object"
    assert _eval([record], 1)["adjudicated_runs"] == 0


def test_a_run_count_without_the_days_is_still_insufficient():
    out = _eval([_record(i, day=0.1 * i) for i in range(12)], 2)
    assert out["status"] == "INSUFFICIENT" and out["runs_still_needed"] == 0


def test_the_cap_is_reported_as_insufficient_not_as_a_pass():
    out = _eval([_record(i, day=i) for i in range(3)], 25)
    assert out["status"] == "INSUFFICIENT AT CAP"


def test_unusable_evaluations_do_not_meet():
    records = [_record(i, day=i * 0.5) for i in range(10)]
    records += [_record(50 + k, cand_ok=False, day=5) for k in range(5)]
    out = _eval(records, 9)
    assert "usable_evaluations" in out["failed_criteria"] and out["status"] == "DOES NOT MEET"


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
    assert [r["run_id"] for r in got] == ["1"]  # expired, wrong-name and too-old are skipped


def test_markdown_states_the_status_the_needs_and_that_nothing_is_promoted():
    text = rep.markdown(rep.evaluate([_record(1)], CONFIG, now=START + timedelta(days=1)))
    assert "INSUFFICIENT" in text and "still needed" in text and "Nothing here promotes" in text
    assert "blind adjudicator" in text


def test_a_met_window_prints_zero_still_needed_not_silence():
    text = rep.markdown(
        rep.evaluate(
            [_record(i, day=i * 0.5) for i in range(12)], CONFIG, now=START + timedelta(days=8)
        )
    )
    assert "**MEETS**" in text and "still needed: 0 adjudicated run(s), 0.0 day(s)" in text
    assert "failed criteria: none" in text


def test_markdown_opens_with_one_row_per_candidate():
    text = rep.markdown(rep.evaluate([_record(1)], CONFIG, now=START + timedelta(days=1)))
    assert "| Candidate | Status |" in text
    for candidate in CONFIG["candidates"]:
        assert f"| {candidate['provider']}:{candidate['model']} |" in text


def test_candidates_without_data_have_no_verdict():
    result = rep.evaluate(
        [_record(i, day=i * 0.5) for i in range(12)], CONFIG, now=START + timedelta(days=8)
    )
    untouched = [c for c in result["candidates"] if c["adjudicated_runs"] == 0]
    assert untouched and all(c["status"] == "INSUFFICIENT" for c in untouched)


def test_a_late_candidate_starts_its_own_clock():
    late = CONFIG["candidates"][-1]
    records = [_record(i, day=i * 0.5) for i in range(12)]
    records[-1]["candidates"].append(
        {
            "provider": late["provider"],
            "model": late["model"],
            "verdict": "PASS",
            "used_llm": True,
            "pipeline": PIPE,
        }
    )
    result = rep.evaluate(records, CONFIG, now=START + timedelta(days=8))
    late_result = next(c for c in result["candidates"] if c["candidate"].endswith(late["model"]))
    assert late_result["days_observed"] < 3  # started at the last record, not at day 0


def test_entries_from_an_earlier_pipeline_are_not_evidence():
    old = _record(1)
    old["candidates"][0]["pipeline"] = "compare-slot/v2"
    assert _eval([old], 1)["attempts"] == 0


def test_a_harness_error_is_not_a_usable_evaluation():
    record = _record(1, cand="CONCERNS", adjudicated=False)
    record["candidates"][0]["error"] = "Schema repair policy escalated verifier output"
    result = _eval([record], 1)
    assert result["attempts"] == 1 and result["usable_share"] == 0.0


def test_semantic_mode_runs_are_not_graded_or_attempted():
    plain = [_record(i, day=i * 0.5) for i in range(12)]
    semantic = [
        dict(_record(100 + i, day=i * 0.5, mine=_rating("inaccurate")), semantic_mode=True)
        for i in range(5)
    ]
    out = _eval(plain + semantic, 8)
    assert out["adjudicated_runs"] == 12 and out["status"] == "MEETS"
    assert rep.adjudicated_runs(semantic, CAND) == [] and rep.attempted(semantic, CAND) == []
    assert len(rep.adjudicated_runs([_record(1)], CAND)) == 1, "no flag is not semantic mode"


def test_workflow_installs_requirements_and_bounds_the_paid_steps():
    import yaml

    wf = yaml.safe_load(
        (ROOT / ".github/workflows/maint-89-verifier-shadow-report.yml").read_text()
    )
    job = wf["jobs"]["report"]
    steps = job["steps"]
    names = [s.get("name", "") for s in steps]

    def at(prefix):
        return next(i for i, n in enumerate(names) if n.startswith(prefix))

    install, replay = at("Install the verifier's Python"), at("Judge the external candidates")
    adjudicate, report = at("Adjudicate every evaluation"), at("Re-evaluate the criteria")
    assert "tools/requirements-llm.txt" in steps[install]["run"]
    assert install < replay < adjudicate < report
    total = 0
    for index in (replay, adjudicate):
        step = steps[index]
        assert step["continue-on-error"] is True and "--budget-seconds" in step["run"]
        budget = int(step["run"].split("--budget-seconds")[1].split()[0])
        assert budget < step["timeout-minutes"] * 60
        total += step["timeout-minutes"]
    assert total * 60 < job["timeout-minutes"] * 60, "the report must still fit after both steps"
    assert "CLAUDE_API_STRANSKE" in steps[adjudicate]["env"]
    assert "cancelled" in steps[report]["if"], "the report must still be written after a failure"
