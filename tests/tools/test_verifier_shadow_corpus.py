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
    outside = [c for c in CONFIG["candidates"] if c.get("runner") == "external"]
    assert [(e["provider"], e["model"]) for e in record["candidates"]] == [
        (c["provider"], c["model"]) for c in inside + outside
    ]  # corpus-only candidates included: the corpus trial is where they run
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
    assert len(cases) >= 15
    assert all(c["evaluable"] for c in cases)  # a case no judge can answer is never dispatched
    assert {c["expected_verdict"] for c in cases} == {"PASS", "NON_PASS"}
    assert len({c["repo"] for c in cases}) > 1
    assert all(corpus.case_inputs(c)[0] for c in cases)


def test_each_shard_resumes_from_its_checkpoint_unless_a_fresh_start_is_asked():
    import yaml

    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/maint-89-verifier-shadow-report.yml").read_text()
    )
    steps = workflow["jobs"]["corpus"]["steps"]
    names = [s.get("name", "") for s in steps]
    restore = names.index("Restore this shard's newest checkpoint")
    assert restore < names.index("Judge and adjudicate this shard of the corpus")
    step = steps[restore]
    assert step["if"] == "${{ !inputs.corpus_fresh }}"
    assert "verifier-shadow-corpus-$SHARD" in step["run"] and "$GITHUB_RUN_ID" in step["run"]


def test_a_verdict_reached_without_a_model_is_never_reviewed_or_rated():
    """2026-10-29: the coverage floor answered 44 corpus cases without calling any model; candidate
    entries kept a review while production ones did not, so the adjudicator rated the candidates
    alone and their inaccurate share read 0.6 against production's 0.03."""

    def floor(context, diff=None, model=None, provider=None):
        return SimpleNamespace(
            verdict="UNVERIFIABLE_INPUT",
            used_llm=False,
            error=None,
            confidence=0.0,
            concerns=[],
            summary="insufficient input",
            scores=None,
            files_not_reviewed=[],
        )

    record = corpus.judge_case(
        _case(),
        PRODUCTION,
        CONFIG,
        evaluator=floor,
        externals=lambda *a: [],
        is_public=lambda repo: True,
    )
    assert not any(e.get("review") for e in record["production_slots"] + record["candidates"])
    from tools.verifier_shadow_adjudicate import evaluators_for

    stale = {
        **record,
        "candidates": [
            {**e, "review": {"verdict": "UNVERIFIABLE_INPUT"}} for e in record["candidates"]
        ],
    }
    assert evaluators_for(stale, corpus.comparison_of(record["production_slots"])) == {}


def test_a_checkpoint_from_another_selection_never_reaches_the_report(tmp_path, monkeypatch):
    kept, moved, dropped = _case("kept"), _case("moved"), _case("dropped")
    monkeypatch.setattr(corpus, "corpus_cases", lambda path=corpus.CORPUS: [kept, moved])
    records: list = []
    corpus.run_corpus(
        [kept, moved, dropped],
        records,
        CONFIG,
        production=PRODUCTION,
        judge=_judge([]),
        client_factory=lambda adjudicator: Adjudicator(),
    )
    old = tmp_path / "corpus-0.json"
    old.write_text(json.dumps(records))
    calls: list = []
    monkeypatch.setattr(corpus, "judge_case", _judge(calls))
    monkeypatch.setattr(corpus, "make_client", lambda adjudicator: Adjudicator())
    monkeypatch.setattr(corpus, "production_judges", lambda: PRODUCTION)
    # shard 0 of 2 now holds only "kept"; its checkpoint still carries "moved" and "dropped"
    corpus.main(["run", "--records", str(old), "--shard", "0", "--shards", "2"])
    assert [r["corpus"]["case_id"] for r in json.loads(old.read_text())] == ["kept"]
    assert calls == []
    other = tmp_path / "corpus-1.json"
    other.write_text(json.dumps(records))  # a stale copy of "moved" (and "dropped") elsewhere
    md, js = tmp_path / "r.md", tmp_path / "r.json"
    corpus.main(["report", str(old), str(other), "--markdown", str(md), "--json", str(js)])
    assert json.loads(js.read_text())["cases"] == 2  # kept + moved once; dropped never counts
