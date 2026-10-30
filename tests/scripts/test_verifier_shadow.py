from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

from scripts.langchain import verifier_shadow as shadow

CONFIG = {
    "enabled": True,
    "candidates": [{"provider": "openai", "model": "cand-model"}],
}
COMPARISON = {
    "results": [
        {"provider_used": "openai", "model": "prod-a", "verdict": "PASS", "used_llm": True},
        {"provider_used": "anthropic", "model": "prod-b", "verdict": "CONCERNS", "used_llm": True},
    ]
}


def _result(verdict="PASS", error=None):
    return SimpleNamespace(
        verdict=verdict, used_llm=error is None, error=error, confidence=0.8, concerns=["a", "b"]
    )


def _run(evaluator, config=CONFIG, comparison=COMPARISON):
    return shadow.run_shadow(
        "ctx", "diff", comparison, config, production_verdict="CONCERNS", evaluator=evaluator
    )


def test_a_candidate_is_judged_on_the_same_context_and_diff_and_recorded_next_to_production():
    seen = {}

    def evaluator(context, diff=None, model=None, provider=None):
        seen.update(context=context, diff=diff, model=model, provider=provider)
        return _result("PASS")

    record = _run(evaluator)
    assert seen == {"context": "ctx", "diff": "diff", "model": "cand-model", "provider": "openai"}
    assert record["production_verdict"] == "CONCERNS"
    assert [s["verdict"] for s in record["production_slots"]] == ["PASS", "CONCERNS"]
    (candidate,) = record["candidates"]
    assert candidate["verdict"] == "PASS" and candidate["used_llm"] and candidate["error"] is None
    assert candidate["concerns"] == 2 and candidate["latency_s"] is not None


def test_a_failing_candidate_becomes_an_error_field_never_an_exception():
    def boom(*args, **kwargs):
        raise RuntimeError("provider down")

    (candidate,) = _run(boom)["candidates"]
    assert candidate["verdict"] is None and "provider down" in candidate["error"]


def test_a_slow_candidate_times_out_without_blocking_the_run(monkeypatch):
    monkeypatch.setattr(shadow, "CANDIDATE_TIMEOUT_SECONDS", 0.2)

    def slow(*args, **kwargs):
        time.sleep(2)
        return _result()

    started = time.perf_counter()
    entry = shadow.run_candidate(CONFIG["candidates"][0], "c", None, slow, timeout=0.2)
    assert time.perf_counter() - started < 1.5 and "timed out" in entry["error"]


def test_a_model_that_is_already_a_production_judge_on_the_run_is_not_shadowed():
    config = {"enabled": True, "candidates": [{"provider": "openai", "model": "prod-a"}]}
    assert _run(lambda *a, **k: _result(), config)["candidates"] == []


def test_disabled_config_records_production_only_and_calls_nothing():
    called = []
    record = _run(
        lambda *a, **k: called.append(1) or _result(),
        {"enabled": False, "candidates": CONFIG["candidates"]},
    )
    assert called == [] and record["candidates"] == [] and record["production_slots"]


def test_main_writes_an_error_record_and_exits_zero_when_inputs_are_missing(tmp_path, monkeypatch):
    out = tmp_path / "shadow.json"
    code = shadow.main(
        [
            "--context-file",
            str(tmp_path / "nope.md"),
            "--config",
            str(tmp_path / "nope.json"),
            "--output",
            str(out),
        ]
    )
    data = json.loads(out.read_text())
    assert code == 0 and data["candidates"] == [] and data["error"]


def test_the_shipped_config_names_a_candidate_and_preregistered_criteria():
    from pathlib import Path

    config = json.loads(
        (Path(__file__).resolve().parents[2] / "config/verifier_shadow.json").read_text()
    )
    assert config["candidates"] and config["window"]["min_runs"] >= 10
    for key in (
        "usable_min",
        "inaccurate_share_max_excess",
        "coverage_max_shortfall",
        "usefulness_max_shortfall",
    ):
        assert key in config["criteria"]
    # graded on the work, never on agreement with one production judge
    assert not {"class_agreement_min", "candidate_miss_max_absolute"} & set(config["criteria"])
    judged = {(c["provider"], c["model"]) for c in config["candidates"]}
    assert (config["adjudicator"]["provider"], config["adjudicator"]["model"]) not in judged


def test_a_missing_context_calls_no_candidate(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(
        "scripts.langchain.pr_verifier.evaluate_pr", lambda *a, **k: called.append(1)
    )
    out = tmp_path / "shadow.json"
    shadow.main(["--context-file", str(tmp_path / "missing.md"), "--output", str(out)])
    assert called == [] and "context" in json.loads(out.read_text())["error"]


def test_all_candidates_judge_in_parallel_and_keep_config_order():
    config = {
        "enabled": True,
        "candidates": [{"provider": "openai", "model": f"m{i}"} for i in range(4)],
    }

    def slow(context, diff=None, model=None, provider=None):
        time.sleep(0.4)
        return _result("PASS" if model in ("m0", "m2") else "CONCERNS")

    started = time.perf_counter()
    record = _run(slow, config)
    elapsed = time.perf_counter() - started
    assert elapsed < 1.2, f"candidates ran one after another ({elapsed:.1f}s)"
    assert [c["model"] for c in record["candidates"]] == ["m0", "m1", "m2", "m3"]
    assert [c["verdict"] for c in record["candidates"]] == ["PASS", "CONCERNS", "PASS", "CONCERNS"]


def test_one_failing_candidate_does_not_disturb_the_others():
    config = {
        "enabled": True,
        "candidates": [
            {"provider": "openai", "model": "ok"},
            {"provider": "openai", "model": "bad"},
        ],
    }

    def evaluator(context, diff=None, model=None, provider=None):
        if model == "bad":
            raise RuntimeError("quota")
        return _result("PASS")

    ok, bad = _run(evaluator, config)["candidates"]
    assert ok["verdict"] == "PASS" and bad["verdict"] is None and "quota" in bad["error"]


def test_the_shipped_config_shadows_several_candidates_across_all_four_providers():
    from pathlib import Path

    config = json.loads(
        (Path(__file__).resolve().parents[2] / "config/verifier_shadow.json").read_text()
    )
    providers = {c["provider"] for c in config["candidates"]}
    assert len(config["candidates"]) >= 6 and providers == {
        "openai",
        "anthropic",
        "muse-api",
        "cursor-cli",
    }
    assert len({(c["provider"], c["model"]) for c in config["candidates"]}) == len(
        config["candidates"]
    )


def test_candidates_run_the_production_slot_path_not_the_lenient_evaluator(monkeypatch):
    """evaluate_pr uses evaluate_minimum=True; production compare uses ComparisonRunner.run_single."""
    from scripts.langchain import pr_verifier as pv

    seen = {}

    class Runner:
        def __init__(self, **kw):
            seen["init"] = kw

        def run_single(self, client, provider, model):
            seen["run"] = (client, provider, model)
            return SimpleNamespace(
                verdict="PASS", used_llm=True, error=None, confidence=0.9, concerns=[]
            )

    monkeypatch.setattr(
        pv, "_get_llm_client", lambda model=None, provider=None: ("client", "openai")
    )
    monkeypatch.setattr(pv, "ComparisonRunner", Runner)
    monkeypatch.setattr(
        pv, "_prepare_prompt", lambda c, d, **kw: seen.setdefault("min", kw) and "p" or "p"
    )
    result = shadow.evaluate_like_production("ctx", "diff", model="m", provider="openai")
    assert result.verdict == "PASS" and seen["run"] == ("client", "openai", "m")
    assert "evaluate_minimum" not in seen.get("min", {})


def test_every_candidate_entry_names_its_pipeline():
    entry = shadow.run_candidate(
        {"provider": "openai", "model": "m"}, "ctx", None, lambda *a, **k: _result("PASS")
    )
    assert entry["pipeline"] == shadow.PIPELINE == "compare-slot/v3"


def test_a_candidate_entry_keeps_the_review_the_adjudicator_reads():
    result = _result("CONCERNS")
    result.summary = "Route added; the acceptance test is missing."
    result.concerns = ["tests/test_route.py is not in the diff"]
    result.files_not_reviewed = []
    entry = shadow.run_candidate(
        {"provider": "openai", "model": "m"}, "ctx", None, lambda *a, **k: result
    )
    review = entry["review"]
    assert review["verdict"] == "CONCERNS" and review["concerns"] == [
        "tests/test_route.py is not in the diff"
    ]
    assert review["summary"].startswith("Route added")
    failed = _result("CONCERNS")
    failed.error = "Failed to parse JSON response"
    assert "review" not in shadow.run_candidate(
        {"provider": "openai", "model": "m"}, "ctx", None, lambda *a, **k: failed
    ), "an errored entry carries no review to grade"


def test_reviews_are_bounded_so_records_stay_small():
    from types import SimpleNamespace

    huge = SimpleNamespace(
        verdict="CONCERNS",
        confidence=0.5,
        scores=None,
        summary="s" * 10_000,
        concerns=["c" * 5_000] * 100,
        files_not_reviewed=["f"] * 500,
    )
    review = shadow.review_of(huge)
    limits = shadow.REVIEW_LIMITS
    assert (
        len(review["summary"]) == limits["summary"]
        and len(review["concerns"]) == limits["concerns"]
    )
    assert (
        len(review["concerns"][0]) == limits["concern"]
        and len(review["files_not_reviewed"]) == limits["files"]
    )


def test_main_records_whether_production_ran_the_semantic_matrix(tmp_path, monkeypatch):
    context = tmp_path / "context.md"
    context.write_text("## Tasks\n- [ ] x\n")
    seen = []

    def fake_run_shadow(context, diff, comparison, config, **kwargs):
        seen.append(kwargs["meta"])
        return {"candidates": [], **kwargs["meta"]}

    monkeypatch.setattr(shadow, "run_shadow", fake_run_shadow)
    for value, expected in (("1", True), ("0", False), (None, False)):
        if value is None:
            monkeypatch.delenv("VERIFIER_SEMANTIC_MODE", raising=False)
        else:
            monkeypatch.setenv("VERIFIER_SEMANTIC_MODE", value)
        out = tmp_path / f"out-{value}.json"
        shadow.main(["--context-file", str(context), "--output", str(out)])
        assert json.loads(out.read_text())["semantic_mode"] is expected
    assert len(seen) == 3


def test_a_reasoning_effort_variant_runs_the_same_model_at_that_effort(monkeypatch):
    import pytest

    chat_openai = pytest.importorskip("langchain_openai").ChatOpenAI
    from scripts.langchain import pr_verifier as pv

    seen = {}
    client = chat_openai(model="gpt-6.1-terra", api_key="offline", use_responses_api=True)

    def get_client(model=None, provider=None):
        seen["model"] = model
        return client, "openai"

    def run_single(self, used, provider, model):
        seen["payload"] = used._get_request_payload("prompt")
        return SimpleNamespace(verdict="PASS")

    monkeypatch.setattr(pv, "_get_llm_client", get_client)
    monkeypatch.setattr(pv.ComparisonRunner, "run_single", run_single)
    shadow.evaluate_like_production("ctx", None, model="gpt-6.1-terra#high", provider="openai")
    assert seen["model"] == "gpt-6.1-terra"
    assert seen["payload"]["model"] == "gpt-6.1-terra"
    assert seen["payload"]["reasoning"]["effort"] == "high"
    shadow.evaluate_like_production("ctx", None, model="gpt-6.1-terra", provider="openai")
    assert "reasoning" not in seen["payload"]  # the plain model keeps the provider default


def test_corpus_only_candidates_never_run_or_grade_in_the_daily_shadow():
    from tools.verifier_shadow_external import external_candidates
    from tools.verifier_shadow_report import evaluate

    config = {
        "enabled": True,
        "criteria": json.loads(Path("config/verifier_shadow.json").read_text())["criteria"],
        "window": {"min_runs": 10, "min_days": 7, "max_days": 21},
        "candidates": [
            {"provider": "openai", "model": "daily"},
            {"provider": "openai", "model": "corpus", "corpus_only": True},
            {"provider": "muse-api", "model": "ext", "runner": "external", "corpus_only": True},
        ],
    }
    calls = []

    def evaluator(context, diff=None, model=None, provider=None):
        calls.append(model)
        return SimpleNamespace(verdict="PASS", used_llm=True, error=None, concerns=[])

    shadow.run_shadow(
        "ctx", None, {"results": []}, config, production_verdict="PASS", evaluator=evaluator
    )
    assert calls == ["daily"]
    assert external_candidates(config) == []
    assert [c["model"] for c in external_candidates(config, corpus=True)] == ["ext"]
    assert [c["candidate"] for c in evaluate([], config)["candidates"]] == ["openai:daily"]
