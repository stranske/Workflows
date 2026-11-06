from __future__ import annotations

import json
from datetime import UTC, datetime

from tools import generate_mutation_cases as g
from tools import stable_pass_cases as s
from tools.plan_model_eval import ROOT, build_plan

NOW = datetime(2026, 10, 18, tzinfo=UTC)


def _source(case_id="src-1", pr=5, source_only=True):
    return {
        "case_id": case_id,
        "repo": "o/r",
        "pr": pr,
        "source_only": source_only,
        "production_snapshot": {"context": "c"},
    }


def _facts(merged="2026-08-01T00:00:00Z", labels=(), state="MERGED"):
    return {"merged_at": merged, "labels": set(labels), "state": state}


def _run(sources, facts, reverted=frozenset(), sufficient=True, days=30):
    return s.stable_pass_cases(
        sources,
        minimum_age_days=days,
        coverage_sufficient=lambda snapshot: sufficient,
        facts_fn=lambda repo, pr: facts,
        reverted_fn=lambda repo: set(reverted),
        now=NOW,
    )


def test_an_old_clean_merge_with_a_sufficient_input_becomes_a_stable_merge_pass():
    (case,) = _run({"src-1": _source()}, _facts())
    assert case["expected_verdict"] == "PASS" and case["provenance"] == "stable-merge"
    assert case["category"] == "clean-pass" and case["stable_age_days_at_label"] >= 30


def test_each_disqualifier_removes_the_case():
    sources = {"src-1": _source()}
    assert _run(sources, _facts(merged="2026-10-10T00:00:00Z")) == []  # too recent
    assert _run(sources, _facts(), reverted={5}) == []  # reverted
    assert _run(sources, _facts(labels={"verifier-followup"})) == []  # verifier follow-up
    assert _run(sources, _facts(labels={"verify:create-issue"})) == []
    assert _run(sources, _facts(state="CLOSED")) == [] and _run(sources, None) == []
    assert _run(sources, _facts(), sufficient=False) == []  # insufficient input


def test_a_corpus_case_keeps_its_own_label_and_is_never_relabelled():
    assert _run({"x": _source(source_only=False)}, _facts()) == []


def test_policy_switch_controls_whether_stable_cases_count():
    corpus, registry, policy = (
        json.loads((ROOT / path).read_text())
        for path in (
            "config/model_eval_pilot.json",
            "config/model_registry.json",
            "config/model_selection_policy.json",
        )
    )
    extra = [
        {
            "case_id": f"stable-{i}",
            "repo": "stranske/Workflows",
            "pr": 9000 + i,
            "expected_verdict": "PASS",
            "category": "clean-pass",
            "provenance": "stable-merge",
            "snapshot_ref": "x",
            "coverage_sufficient": True,
        }
        for i in range(5)
    ]
    corpus = {
        **corpus,
        "cases": [c for c in corpus["cases"] if c.get("provenance") != "stable-merge"] + extra,
    }
    on = build_plan(corpus, registry, policy)
    off_policy = json.loads(json.dumps(policy))
    off_policy["profiles"]["verifier-balanced"]["approval_stage"]["stable_merge_pass"][
        "enabled"
    ] = False
    off = build_plan(corpus, registry, off_policy)
    assert on["stable_merge_pass_cases"] == 5 and off["stable_merge_pass_cases"] == 0
    assert on["expected_pass_cases"] - off["expected_pass_cases"] == 5
    assert on["evaluable_pass_cases"] - off["evaluable_pass_cases"] == 5


def test_stable_cases_are_written_as_listed_corpus_cases_and_rebuild_replaces_them(tmp_path):
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(json.dumps({"cases": [], "screen_cases": []}))
    source = {
        "case_id": "src-1",
        "repo": "o/r",
        "pr": 5,
        "expected_verdict": "PASS",
        "production_snapshot": {"context": "c", "diff": ""},
    }
    stable = _run({"src-1": _source()}, _facts())
    snaps = tmp_path / "snaps"
    g.write_corpus(corpus_path, snaps, {"src-1": source}, [], extra_cases=stable)
    written = json.loads(corpus_path.read_text())["cases"]
    assert [c["case_id"] for c in written] == ["src-1"] and written[0][
        "provenance"
    ] == "stable-merge"
    assert (
        written[0]["snapshot_ref"].endswith("src-1.json.gz") and (snaps / "src-1.json.gz").exists()
    )
    g.write_corpus(corpus_path, snaps, {}, [], rebuild=True)
    assert json.loads(corpus_path.read_text())["cases"] == []


def test_diagnostic_only_cases_never_count_toward_any_floor():
    corpus, registry, policy = (
        json.loads((ROOT / path).read_text())
        for path in (
            "config/model_eval_pilot.json",
            "config/model_registry.json",
            "config/model_selection_policy.json",
        )
    )
    base = build_plan(corpus, registry, policy)
    extra = [
        {
            "case_id": f"diag-{i}",
            "repo": "stranske/Workflows",
            "pr": 9500 + i,
            "expected_verdict": "NON_PASS",
            "category": "ci-failure-disqualifier",
            "provenance": "controlled-mutation",
            "diagnostic_only": True,
            "mutation_recipe": {"mutation": "fail-ci-row"},
            "coverage_sufficient": True,
        }
        for i in range(10)
    ]
    plan = build_plan({**corpus, "cases": [*corpus["cases"], *extra]}, registry, policy)
    for key in (
        "expected_non_pass_cases",
        "evaluable_non_pass_cases",
        "controlled_mutation_non_pass_cases",
    ):
        assert plan[key] == base[key], key
    assert plan["diagnostic_only_cases"] == base["diagnostic_only_cases"] + 10
    assert base["diagnostic_only_cases"] == 22  # the failed-CI mutants already in the corpus
