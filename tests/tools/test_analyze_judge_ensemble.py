"""Tests for the judge-ensemble analyzer on synthetic verdicts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools import analyze_judge_ensemble as ens


def _truth(pass_cases: int, non_pass_cases: int) -> dict[str, str]:
    truth = {f"p{i}": "PASS" for i in range(pass_cases)}
    truth.update({f"n{i}": "NON_PASS" for i in range(non_pass_cases)})
    return truth


def _perfect(truth: dict[str, str]) -> dict[str, str | None]:
    return dict(truth)


def _wrong_on(truth: dict[str, str], cases: set[str]) -> dict[str, str | None]:
    flip = {"PASS": "NON_PASS", "NON_PASS": "PASS"}
    return {c: (flip[v] if c in cases else v) for c, v in truth.items()}


def test_strict_and_is_the_production_contract():
    a = {"c1": "PASS", "c2": "PASS", "c3": "NON_PASS", "c4": None}
    b = {"c1": "PASS", "c2": "NON_PASS", "c3": "PASS", "c4": "PASS"}
    assert ens.strict_and(a, b, ["c1", "c2", "c3", "c4"]) == {
        "c1": "PASS",
        "c2": "NON_PASS",
        "c3": "NON_PASS",
        "c4": "NON_PASS",
    }


def test_an_invalid_result_can_never_count_as_a_pass():
    truth = {"c1": "NON_PASS"}
    authority = ens.judge_authority("x", {"c1": None}, truth, bound=0.05)
    assert authority["false_pass"] == 0 and authority["invalid"] == 1
    assert authority["may_hold_pass_authority"] is False


def test_a_tiny_sample_cannot_confer_authority_even_with_zero_errors():
    truth = _truth(4, 4)
    authority = ens.judge_authority("x", _perfect(truth), truth, bound=0.05)
    assert authority["false_pass"] == 0
    assert authority["may_hold_pass_authority"] is False
    assert any("needed with zero errors" in b for b in authority["authority_blockers"])
    assert ens.cases_needed_for_bound(0.05) > 60


def test_a_large_clean_sample_confers_authority_and_one_false_pass_removes_it():
    truth = _truth(80, 80)
    categories = _categories(truth)
    assert ens.judge_authority(
        "x", _perfect(truth), truth, bound=0.05, categories=categories, baseline=_perfect(truth)
    )["may_hold_pass_authority"]
    bad = ens.judge_authority("x", _wrong_on(truth, {"n0"}), truth, bound=0.05)
    assert bad["false_pass"] == 1 and not bad["may_hold_pass_authority"]


def test_tie_break_value_counts_how_often_the_third_judge_is_right_on_disagreements():
    truth = _truth(40, 40)
    disputed = {f"n{i}" for i in range(6)}
    decisions = {
        "a": _perfect(truth),
        "b": _wrong_on(truth, disputed),  # disagrees with a on exactly six cases
        "c": _perfect(truth),
    }
    decisions = {
        n: {c: "CONCERNS" if v == "NON_PASS" else v for c, v in rows.items()}
        for n, rows in decisions.items()
    }
    result = ens.analyze(decisions, truth)
    trio = next(
        t for t in result["tie_breaks"] if t["pair"] == ["a", "b"] and t["tie_breaker"] == "c"
    )
    assert trio["disagreements"] == 6 and trio["tie_breaker_right_on_disagreements"] == 6
    assert trio["estimable"] is True
    assert trio["majority_of_three"]["false_pass"] == 0  # 2-of-3 outvotes b's false PASS


def test_too_few_disagreements_means_insufficient_evidence():
    truth = _truth(80, 80)
    decisions = {n: _perfect(truth) for n in ("a", "b", "c")}
    result = ens.analyze(decisions, truth, categories=_categories(truth), baseline_model="a")
    assert "insufficient evidence" in result["recommendation"]["tie_break"]
    assert result["enables_anything"] is False


def test_nothing_is_enabled_when_fewer_than_three_judges_hold_authority():
    truth = _truth(4, 4)  # too small for anyone to earn authority
    decisions = {n: _perfect(truth) for n in ("a", "b", "c")}
    result = ens.analyze(decisions, truth)
    assert result["recommendation"]["tie_break"].startswith("not enabled")
    assert result["recommendation"]["failover"].startswith("not enabled")
    assert "NON_PASS case(s) observed" in result["recommendation"]["sample_note"]


def test_failover_reports_the_backup_standing_alone():
    truth = _truth(40, 40)
    decisions = {"primary": _perfect(truth), "backup": _wrong_on(truth, {"n0", "n1"})}
    result = ens.analyze(decisions, truth)
    entry = next(f for f in result["failovers"] if f["unavailable"] == "primary")
    assert entry["backup"] == "backup" and entry["backup_alone"]["false_pass"] == 2
    assert entry["backup_may_hold_pass_authority"] is False


def test_load_judgments_reads_both_screen_formats_and_rejects_inconsistent_truth(tmp_path):
    codex = tmp_path / "codex.json"
    codex.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "model_id": "gpt-x",
                        "case_id": "c1",
                        "expected_verdict": "PASS",
                        "actual_verdict": "PASS",
                        "schema_valid": True,
                    }
                ]
            }
        )
    )
    new = tmp_path / "new.json"
    new.write_text(
        json.dumps(
            {
                "schema": "workflows-judge-backend-screen/v1",
                "rows": [
                    {
                        "judge": "muse-cli",
                        "case_id": "c1",
                        "expected_verdict": "PASS",
                        "actual_verdict": "NON_PASS",
                        "schema_valid": False,
                    }
                ],
            }
        )
    )
    decisions, truth = ens.load_judgments([codex, new])
    assert decisions == {"gpt-x": {"c1": "PASS"}, "muse-cli": {"c1": None}} and truth == {
        "c1": "PASS"
    }
    clash = tmp_path / "clash.json"
    clash.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "judge": "z",
                        "case_id": "c1",
                        "expected_verdict": "NON_PASS",
                        "actual_verdict": "PASS",
                    }
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="inconsistent"):
        ens.load_judgments([codex, clash])


def test_cli_writes_json_and_markdown(tmp_path: Path):
    truth = _truth(2, 2)
    rows = []
    for judge in ("a", "b"):
        for case, expected in truth.items():
            rows.append(
                {
                    "judge": judge,
                    "case_id": case,
                    "expected_verdict": expected,
                    "actual_verdict": expected,
                    "schema_valid": True,
                }
            )
    source = tmp_path / "in.json"
    source.write_text(json.dumps({"rows": rows}))
    out, md = tmp_path / "out.json", tmp_path / "out.md"
    assert ens.main(["--inputs", str(source), "--output", str(out), "--markdown", str(md)]) == 0
    assert json.loads(out.read_text())["schema"] == ens.SCHEMA
    assert "Nothing is enabled by this report" in md.read_text()


def _categories(truth):
    names = [
        "clean-pass",
        "missing-acceptance-criterion",
        "stale-verifier-claim",
        "review-thread-debt",
        "follow-up-required",
    ]
    return {case: names[i % len(names)] for i, case in enumerate(truth)}


def test_reject_all_judge_cannot_earn_authority_on_a_large_sample():
    truth = _truth(80, 80)
    report = ens.judge_authority(
        "reject-all",
        dict.fromkeys(truth, "FAIL"),
        truth,
        bound=0.05,
        categories=_categories(truth),
        baseline=truth,
    )
    assert report["false_pass"] == 0 and report["false_fail"] == 80
    assert report["may_hold_pass_authority"] is False
    assert report["approval_gates"]["false_fail_rate_wilson_upper_bound"] is False
    assert report["approval_gates"]["paired_success_noninferiority"] is False


def test_authority_requires_category_and_paired_incumbent_evidence():
    truth = _truth(80, 80)
    for kwargs in ({}, {"categories": _categories(truth)}, {"baseline": truth}):
        report = ens.judge_authority("perfect", truth, truth, bound=0.05, **kwargs)
        assert report["may_hold_pass_authority"] is False


@pytest.mark.parametrize("veto", ["FAIL", None, "NON_PASS"])
def test_hard_fail_or_unknown_cannot_be_outvoted(veto):
    assert ens.majority([{"c": "PASS"}, {"c": veto}, {"c": "PASS"}], ["c"]) == {"c": "NON_PASS"}
    report = ens.analyze(
        {"a": {"c": "PASS"}, "b": {"c": veto}, "c": {"c": "PASS"}}, {"c": "NON_PASS"}
    )
    assert all(t["disagreements"] == 0 for t in report["tie_breaks"])


def test_unapproved_judge_is_excluded_from_tie_break_recommendation():
    trio = {
        "pair": ["a", "b"],
        "tie_breaker": "unapproved",
        "estimable": True,
        "disagreements": 5,
        "tie_breaker_right_on_disagreements": 5,
    }
    assert "insufficient evidence" in ens._tie_break_verdict([trio], ["a", "b", "c"])


@pytest.mark.parametrize("field", ["input_fingerprint", "prompt_sha256_by_case"])
def test_loader_rejects_different_corpora_or_prompts(tmp_path, field):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps({field: "first", "rows": []}))
    b.write_text(json.dumps({field: "second", "rows": []}))
    with pytest.raises(ValueError, match="fingerprint"):
        ens.load_judgments([a, b])


def test_loader_preserves_hard_fail_and_rejects_conflicting_repeats(tmp_path):
    path = tmp_path / "in.json"
    row = {
        "judge": "a",
        "case_id": "c",
        "expected_verdict": "NON_PASS",
        "actual_verdict": "NON_PASS",
        "raw_verdict": "FAIL",
        "schema_valid": True,
    }
    path.write_text(json.dumps({"rows": [row, row]}))
    decisions, _ = ens.load_judgments([path])
    assert decisions == {"a": {"c": "FAIL"}}
    path.write_text(json.dumps({"rows": [row, {**row, "raw_verdict": "CONCERNS"}]}))
    with pytest.raises(ValueError, match="conflicting"):
        ens.load_judgments([path])
