"""Tests for tools/harvest_verifier_corpus.py (realized-outcome corpus growth)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from tools import harvest_verifier_corpus as hv

NOW = datetime(2026, 7, 25, tzinfo=UTC)


def _rec(pr, *, merged=True, days_ago=40, reverted=False, followup=False, resolved=False):
    merged_at = None
    if merged:
        merged_at = datetime(2026, 7, 25, tzinfo=UTC).fromordinal(NOW.toordinal() - days_ago)
        merged_at = merged_at.replace(tzinfo=UTC).isoformat()
    return {
        "repo": "stranske/Demo",
        "pr": pr,
        "merged": merged,
        "merged_at": merged_at,
        "reverted": reverted,
        "verifier_followup": followup,
        "followup_resolved": resolved,
    }


def test_stable_merge_is_high_confidence_pass():
    label = hv.classify(_rec(1, days_ago=40), now=NOW, stability_days=30)
    assert label == {"expected_verdict": "PASS", "category": "clean-pass", "confidence": "high"}


def test_recent_merge_is_low_confidence_pass():
    label = hv.classify(_rec(2, days_ago=5), now=NOW, stability_days=30)
    assert label["expected_verdict"] == "PASS"
    assert label["confidence"] == "low"  # not yet stable -> staging


def test_reverted_is_high_confidence_non_pass():
    label = hv.classify(_rec(3, days_ago=10, reverted=True), now=NOW, stability_days=30)
    assert label == {
        "expected_verdict": "NON_PASS",
        "category": "regression-after-merge",
        "confidence": "high",
    }


def test_resolved_followup_is_high_confidence_non_pass():
    label = hv.classify(_rec(4, followup=True, resolved=True), now=NOW, stability_days=30)
    assert label["category"] == "follow-up-required"
    assert label["confidence"] == "high"


def test_unresolved_followup_stages():
    label = hv.classify(_rec(5, followup=True, resolved=False), now=NOW, stability_days=30)
    assert label["expected_verdict"] == "NON_PASS"
    assert label["confidence"] == "low"


def test_unmerged_pr_yields_no_signal():
    assert hv.classify(_rec(6, merged=False), now=NOW, stability_days=30) is None


def test_partition_splits_promote_and_stage():
    recs = [_rec(1, days_ago=40), _rec(2, days_ago=3), _rec(3, reverted=True)]
    promote, stage = hv.partition(recs, now=NOW, stability_days=30)
    assert {c["pr"] for c in promote} == {1, 3}
    assert {c["pr"] for c in stage} == {2}


def test_grow_corpus_dedups_and_caps_and_bumps_version():
    corpus = {"corpus_version": "v2026-07-12", "cases": [{"repo": "stranske/Demo", "pr": 1}]}
    promote = [
        hv.to_case(
            _rec(1, days_ago=40), {"expected_verdict": "PASS", "category": "clean-pass"}, now=NOW
        ),
        hv.to_case(
            _rec(9, days_ago=40), {"expected_verdict": "PASS", "category": "clean-pass"}, now=NOW
        ),
    ]
    grown, added = hv.grow_corpus(corpus, promote, max_size=150)
    assert [c["pr"] for c in added] == [9]  # pr 1 already present -> deduped
    assert grown["corpus_version"] == "v2026-07-12+harvest1"

    capped, added2 = hv.grow_corpus(corpus, promote, max_size=1)  # already 1 case -> cap hit
    assert added2 == [] and capped is corpus


def test_grow_corpus_respects_per_category_caps():
    corpus = {"cases": []}
    promote = [
        hv.to_case(
            _rec(n, days_ago=40), {"expected_verdict": "PASS", "category": "clean-pass"}, now=NOW
        )
        for n in range(10)
    ]
    grown, added = hv.grow_corpus(corpus, promote, max_size=150, category_caps={"clean-pass": 3})
    assert len(added) == 3  # capped at 3 clean-pass despite 10 offered
    assert len(grown["cases"]) == 3


def test_grow_corpus_noop_returns_original():
    corpus = {"cases": [{"repo": "stranske/Demo", "pr": 1}]}
    grown, added = hv.grow_corpus(corpus, [], max_size=150)
    assert added == [] and grown is corpus


def test_staging_auto_expires_old_cases():
    old = {"repo": "stranske/Demo", "pr": 100, "harvested_at": "2026-01-01"}  # >60d ago
    fresh = {"repo": "stranske/Demo", "pr": 101, "harvested_at": NOW.date().isoformat()}
    out = hv.prune_staging({"cases": [old]}, [fresh], now=NOW, expiry_days=60)
    prs = {c["pr"] for c in out["cases"]}
    assert prs == {101}  # old one expired out, fresh retained


def test_main_dry_run_and_write(tmp_path, capsys):
    policy = {
        "profiles": {
            "verifier-balanced": {
                "corpus_growth": {
                    "enabled": True,
                    "stability_days": 30,
                    "staging_expiry_days": 60,
                    "max_corpus_size": 150,
                    "source_repos": [],
                }
            }
        }
    }
    corpus = {"corpus_version": "v1", "cases": []}
    records = [_rec(1, days_ago=40), _rec(2, days_ago=2)]
    pol_p = tmp_path / "policy.json"
    cor_p = tmp_path / "corpus.json"
    stg_p = tmp_path / "staging.json"
    rec_p = tmp_path / "records.json"
    pol_p.write_text(json.dumps(policy))
    cor_p.write_text(json.dumps(corpus))
    rec_p.write_text(json.dumps(records))

    argv = [
        "--policy",
        str(pol_p),
        "--corpus",
        str(cor_p),
        "--staging",
        str(stg_p),
        "--from-json",
        str(rec_p),
        "--write",
    ]
    assert hv.main(argv) == 0
    grown = json.loads(cor_p.read_text())
    assert [c["pr"] for c in grown["cases"]] == [1]  # only the stable merge promoted
    staged = json.loads(stg_p.read_text())
    assert [c["pr"] for c in staged["cases"]] == [2]  # recent merge staged


def test_main_respects_disabled_flag(tmp_path):
    pol_p = tmp_path / "policy.json"
    pol_p.write_text(
        json.dumps({"profiles": {"verifier-balanced": {"corpus_growth": {"enabled": False}}}})
    )
    assert hv.main(["--policy", str(pol_p), "--from-json", str(tmp_path / "none.json")]) == 0
