"""Every verifier judge on the labelled corpus at once, rated by the shadow's blind adjudicator."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

from tools import verifier_shadow_corpus as corpus

ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "config/verifier_shadow.json").read_text())
PRODUCTION = [
    {"provider": "openai", "model": "prod-openai"},
    {"provider": "anthropic", "model": "prod-anthropic"},
]


def _case(case_id="c1", expected="PASS", repo="o/public", depth=2):
    return {
        "case_id": case_id,
        "repo": repo,
        "pr": 5,
        "expected_verdict": expected,
        "category": "clean-pass",
        "evaluable": True,
        "production_snapshot": {
            "context": "## Acceptance Criteria\n- test_x passes\n",
            "diff": "+def test_x(): pass\n",
            "chain_depth": depth,
            "input_kind": "retrospective_capture",
        },
    }


def _evaluator(verdicts=None, seen=None):
    verdicts = verdicts or {}

    def evaluate(context, diff=None, model=None, provider=None):
        if seen is not None:
            seen.append((model, os.environ.get("CHAIN_DEPTH")))
        return SimpleNamespace(
            verdict=verdicts.get(model, "PASS"),
            used_llm=True,
            error=None,
            confidence=0.9,
            concerns=[],
            summary=f"{model} checked test_x",
            scores=None,
            files_not_reviewed=[],
        )

    return evaluate


def _externals(candidates, context, diff):
    return [
        {
            "provider": c["provider"],
            "model": c["model"],
            "verdict": "PASS",
            "used_llm": True,
            "error": None,
            "external": True,
            "pipeline": "compare-slot/v3",
            "review": {"verdict": "PASS", "summary": "ok", "concerns": []},
        }
        for c in candidates
    ]


class Adjudicator:
    """Rates every label accurate with full coverage, or fails while ``broken``."""

    def __init__(self, broken=False):
        self.broken, self.calls = broken, 0

    def invoke(self, prompt):
        self.calls += 1
        if self.broken:
            raise RuntimeError("adjudicator down")
        return SimpleNamespace(
            content=json.dumps(
                {
                    "criteria": [{"id": "AC1", "text": "test_x passes"}],
                    "reference_verdict": "PASS",
                    "evaluations": [
                        {
                            "label": chr(ord("A") + i),
                            "accuracy": "accurate",
                            "verdict_supported": True,
                            "errors": [],
                            "coverage": [{"id": "AC1", "status": "checked"}],
                            "usefulness": 4,
                        }
                        for i in range(20)
                    ],
                }
            )
        )


def test_judge_case_runs_production_and_every_candidate_on_the_case_prompt():
    seen: list = []
    previous = os.environ.get("CHAIN_DEPTH")
    record = corpus.judge_case(
        _case(depth=2),
        PRODUCTION,
        CONFIG,
        evaluator=_evaluator(seen=seen),
        externals=_externals,
        is_public=lambda repo: True,
    )
    inside = [c for c in CONFIG["candidates"] if c.get("runner") != "external"]
    assert [e["model"] for e in record["production_slots"]] == ["prod-openai", "prod-anthropic"]
    assert [(e["provider"], e["model"]) for e in record["candidates"]] == [
        (c["provider"], c["model"]) for c in CONFIG["candidates"]
    ]
    assert len(seen) == len(PRODUCTION) + len(inside)
    assert {depth for _, depth in seen} == {"2"}  # the case's own chain depth reaches the prompt
    assert os.environ.get("CHAIN_DEPTH") == previous  # and is restored afterwards
    assert record["corpus"]["expected_verdict"] == "PASS"
    assert all(e.get("review") for e in record["production_slots"] + record["candidates"])


def test_external_judges_never_see_a_private_repository():
    called = []
    record = corpus.judge_case(
        _case(repo="o/private"),
        PRODUCTION,
        CONFIG,
        evaluator=_evaluator(),
        externals=lambda *a: called.append(a) or [],
        is_public=lambda repo: False,
    )
    assert called == []
    external = [e for e in record["candidates"] if e.get("external")]
    assert external and all(e["error"] == "skipped: private repository" for e in external)


def test_a_production_model_is_never_also_run_as_a_candidate():
    config = {**CONFIG, "candidates": [{"provider": "openai", "model": "prod-openai"}]}
    record = corpus.judge_case(
        _case(),
        PRODUCTION,
        config,
        evaluator=_evaluator(),
        externals=_externals,
        is_public=lambda repo: True,
    )
    assert record["candidates"] == []


def _judge(calls):
    def judge(case, production, config):
        calls.append(case["case_id"])
        return corpus.judge_case(
            case,
            production,
            config,
            evaluator=_evaluator(),
            externals=_externals,
            is_public=lambda repo: True,
        )

    return judge


def test_run_corpus_judges_then_adjudicates_each_case_once():
    records: list = []
    calls: list = []
    client = Adjudicator()
    counts = corpus.run_corpus(
        [_case("a"), _case("b")],
        records,
        CONFIG,
        production=PRODUCTION,
        judge=_judge(calls),
        client_factory=lambda adjudicator: client,
    )
    assert counts["judged"] == 2 and counts["adjudicated"] == 2 and counts["failed"] == 0
    assert calls == ["a", "b"]
    ratings = records[0]["adjudication"]["ratings"]
    assert "production:openai:prod-openai" in ratings
    assert all(r["accuracy"] == "accurate" for r in ratings.values())
    again = corpus.run_corpus(
        [_case("a"), _case("b")],
        records,
        CONFIG,
        production=PRODUCTION,
        judge=_judge(calls),
        client_factory=lambda adjudicator: client,
    )
    assert again["already_done"] == 2 and calls == ["a", "b"] and client.calls == 2


def test_a_judged_but_unadjudicated_case_is_adjudicated_without_paying_the_judges_again():
    records: list = []
    calls: list = []
    corpus.run_corpus(
        [_case("a")],
        records,
        CONFIG,
        production=PRODUCTION,
        judge=_judge(calls),
        client_factory=lambda adjudicator: Adjudicator(broken=True),
    )
    assert records[0]["adjudication"]["error"]
    del records[0]["adjudication"]  # e.g. the job stopped between judging and adjudicating
    counts = corpus.run_corpus(
        [_case("a")],
        records,
        CONFIG,
        production=PRODUCTION,
        judge=_judge(calls),
        client_factory=lambda adjudicator: Adjudicator(),
    )
    assert counts == {**counts, "judged": 0, "adjudicated": 1, "already_done": 0}
    assert calls == ["a"]
    assert not records[0]["adjudication"]["error"]


def test_no_case_starts_when_the_budget_cannot_fit_it():
    records: list = []
    counts = corpus.run_corpus(
        [_case("a")],
        records,
        CONFIG,
        production=PRODUCTION,
        judge=_judge([]),
        client_factory=lambda adjudicator: Adjudicator(),
        deadline=0.0,
    )
    assert counts["out_of_time"] == 1 and records == []


def test_report_counts_label_agreement_and_holds_a_small_sample_insufficient():
    records: list = []
    cases = [_case("pass"), _case("bad", expected="NON_PASS")]

    def judge(case, production, config):
        return corpus.judge_case(
            case,
            production,
            config,
            evaluator=_evaluator({"prod-anthropic": "CONCERNS", "gpt-6-luna": "PASS"}),
            externals=_externals,
            is_public=lambda repo: True,
        )

    corpus.run_corpus(
        cases,
        records,
        CONFIG,
        production=PRODUCTION,
        judge=judge,
        client_factory=lambda adjudicator: Adjudicator(),
    )
    result = corpus.report(records, CONFIG)
    luna = result["labels"]["candidate:openai:gpt-6-luna"]
    assert luna == {
        "usable": 2,
        "label_pass": 1,
        "label_non_pass": 1,
        "false_pass": 1,
        "finding_on_pass_label": 0,
        "unverifiable": 0,
    }
    sonnet = result["labels"]["production:anthropic:prod-anthropic"]
    assert sonnet["false_pass"] == 0 and sonnet["finding_on_pass_label"] == 1
    assert result["adjudicated"] == 2
    assert {c["status"] for c in result["candidates"]} == {"INSUFFICIENT"}  # 2 < min_runs
    assert "Agreement with the corpus labels" in corpus.markdown(result)


def test_report_grades_once_the_sample_reaches_the_minimum():
    records: list = []
    cases = [_case(f"c{i}") for i in range(CONFIG["window"]["min_runs"])]
    corpus.run_corpus(
        cases,
        records,
        CONFIG,
        production=PRODUCTION,
        judge=_judge([]),
        client_factory=lambda adjudicator: Adjudicator(),
    )
    statuses = {c["status"] for c in corpus.report(records, CONFIG)["candidates"]}
    assert statuses == {"MEETS"}


def test_the_real_corpus_loads_with_production_inputs():
    cases = corpus.corpus_cases()
    assert len(cases) >= 50
    assert {c["expected_verdict"] for c in cases} == {"PASS", "NON_PASS"}
    assert len({c["repo"] for c in cases}) > 1
    assert all(corpus.case_inputs(c)[0] for c in cases)
