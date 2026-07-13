from types import SimpleNamespace

from tools.run_model_eval_pilot import run_pilot


def test_run_pilot_records_paired_verdicts() -> None:
    corpus = {
        "corpus_version": "v1",
        "cases": [
            {
                "case_id": "a",
                "repo": "o/r",
                "pr": 1,
                "category": "clean-pass",
                "expected_verdict": "PASS",
            },
            {
                "case_id": "b",
                "repo": "o/r",
                "pr": 2,
                "category": "follow-up-required",
                "expected_verdict": "NON_PASS",
            },
        ],
    }
    candidates = {"candidates": [{"provider": "openai", "model_id": "model-a"}]}

    def evaluator(context, *, diff, model, provider):
        verdict = "PASS" if "#1" in context else "CONCERNS"
        return SimpleNamespace(verdict=verdict, confidence=0.9, error=None)

    report = run_pilot(
        corpus,
        candidates,
        token="token",
        fetcher=lambda repo, pr, token: (f"PR #{pr}", "diff"),
        evaluator=evaluator,
    )

    assert [row["actual_verdict"] for row in report["results"]] == ["PASS", "NON_PASS"]
    assert all(row["schema_valid"] for row in report["results"])


def test_run_pilot_captures_failure_with_case_and_candidate_metadata() -> None:
    corpus = {
        "corpus_version": "v1",
        "cases": [
            {
                "case_id": "broken",
                "repo": "o/r",
                "pr": 3,
                "category": "follow-up-required",
                "expected_verdict": "NON_PASS",
            }
        ],
    }
    candidates = {"candidates": [{"provider": "openai", "model_id": "model-a"}]}

    report = run_pilot(
        corpus,
        candidates,
        token="token",
        fetcher=lambda *_: (_ for _ in ()).throw(RuntimeError("fetch failed")),
    )

    assert report["results"] == [
        {
            "case_id": "broken",
            "category": "follow-up-required",
            "expected_verdict": "NON_PASS",
            "actual_verdict": "NON_PASS",
            "schema_valid": False,
            "provider": "openai",
            "model_id": "model-a",
            "confidence": 0,
            "latency_ms": report["results"][0]["latency_ms"],
            "error": "fetch failed",
        }
    ]
