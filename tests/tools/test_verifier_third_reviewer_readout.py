"""Readout of the verifier third-reviewer experiment."""

from tools import verifier_third_reviewer_readout as readout


def rec(provider, verdict, pair, usable=True, changes=False):
    return {
        "schema": readout.SCHEMA,
        "provider": provider,
        "model": "m",
        "usable": usable,
        "verdict": verdict,
        "pair_verdict": pair,
        "changes_conclusion": changes,
    }


def test_summary_counts_agreement_and_conclusion_changes():
    rows = readout.summarise(
        [
            rec("gemini-api", "PASS", "PASS"),
            rec("gemini-api", "CONCERNS", "PASS", changes=True),
            rec("gemini-api", "PASS", "FAIL"),
            rec("gemini-api", None, "PASS", usable=False),
            rec("cursor-cli", "FAIL", "CONCERNS"),
        ]
    )
    by = {row["backup"]: row for row in rows}
    gemini = by["gemini-api/m"]
    assert gemini["sampled"] == 4 and gemini["usable"] == 3 and gemini["unusable"] == 1
    assert gemini["agrees_with_pair"] == 1
    assert gemini["changes_conclusion"] == 1
    assert gemini["finding_where_pair_passed"] == 1
    assert gemini["pass_where_pair_found"] == 1
    assert by["cursor-cli/m"]["agrees_with_pair"] == 1


def test_an_empty_sample_prints_a_count_of_zero(capsys, monkeypatch):
    monkeypatch.setattr(readout, "records_for_repo", lambda *a: [])
    assert readout.main(["--repos", "stranske/Workflows", "--since", "2026-11-12"]) == 0
    out = capsys.readouterr().out
    assert "third-reviewer records since 2026-11-12: 0" in out
