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


def test_records_are_read_from_the_named_comparison_artifact(monkeypatch):
    import io
    import json
    import zipfile

    record = rec("gemini-api", "PASS", "PASS")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("comparison.json", json.dumps({"results": [], "third_reviewer": record}))
    calls = []

    def fake_gh(args, *, binary=False):
        calls.append(args)
        if args[0] == "run":
            return [{"databaseId": 7}]
        if binary:
            return buffer.getvalue()
        return {"artifacts": [{"id": 9, "name": "comparison-results-7", "expired": False}]}

    monkeypatch.setattr(readout, "_gh", fake_gh)
    found = readout.records_for_repo("stranske/Workflows", "2026-11-12", 10)
    assert [r["provider"] for r in found] == ["gemini-api"]
    assert found[0]["run_id"] == 7
    assert any("artifacts?name=comparison-results-7" in " ".join(a) for a in calls)


def test_an_unreadable_repository_fails_the_readout(monkeypatch, capsys):
    import subprocess

    def boom(*a):
        raise subprocess.CalledProcessError(1, "gh")

    monkeypatch.setattr(readout, "records_for_repo", boom)
    assert readout.main(["--repos", "stranske/Workflows", "--since", "2026-11-12"]) == 1
    assert "readout incomplete" in capsys.readouterr().err
