from types import SimpleNamespace

from tools import run_model_eval_pilot as pilot
from tools.run_model_eval_pilot import (
    run_pilot,
    run_preflight,
    summarize_results,
    unusable_candidates,
)


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


def test_unusable_candidates_requires_valid_evidence_per_candidate() -> None:
    report = {
        "results": [
            {"provider": "openai", "model_id": "working", "schema_valid": True},
            {"provider": "openai", "model_id": "working", "schema_valid": False},
            {"provider": "anthropic", "model_id": "broken", "schema_valid": False},
        ]
    }

    assert unusable_candidates(report) == ["anthropic/broken"]
    assert unusable_candidates({"results": []}) == ["<no-results>"]


def test_fetch_pr_includes_linked_source_issue_context(monkeypatch) -> None:
    monkeypatch.setattr(
        pilot.api_client,
        "fetch_pull_request",
        lambda *_: {"title": "PR", "body": "Closes #12"},
    )
    monkeypatch.setattr(pilot.api_client, "fetch_pull_request_diff", lambda *_: "diff")
    monkeypatch.setattr(
        pilot.api_client,
        "fetch_issue",
        lambda *_: {"title": "Source", "body": "- [ ] acceptance context"},
    )
    monkeypatch.setattr(
        pilot.api_client,
        "fetch_issue_comments",
        lambda *_: [{"body": "Verifier disposition: PASS after comparison."}],
    )

    context, diff = pilot.fetch_pr("owner/repo", 13, "token")

    assert "Source issue: #12 — Source" in context
    assert "acceptance context" in context
    assert "Verifier disposition: PASS after comparison." in context
    assert diff == "diff"


def test_preflight_uses_one_case_per_candidate_and_stops_unusable_candidate() -> None:
    corpus = {
        "corpus_version": "v1",
        "cases": [
            {
                "case_id": "representative",
                "repo": "o/r",
                "pr": 1,
                "category": "clean",
                "expected_verdict": "PASS",
            },
            {
                "case_id": "later",
                "repo": "o/r",
                "pr": 2,
                "category": "clean",
                "expected_verdict": "PASS",
            },
        ],
    }
    candidates = {"candidates": [{"provider": "openai", "model_id": "model-a"}]}
    report = run_preflight(
        corpus,
        candidates,
        token="token",
        fetcher=lambda *_: ("PR #1", "diff"),
        evaluator=lambda *_args, **_kwargs: SimpleNamespace(
            verdict="PASS", confidence=1, error=None
        ),
    )

    assert report["stage"] == "candidate-preflight"
    assert [row["case_id"] for row in report["results"]] == ["representative"]
    assert unusable_candidates(report) == []


def test_run_pilot_fetches_each_case_once_for_all_candidates() -> None:
    corpus = {
        "corpus_version": "v1",
        "cases": [
            {
                "case_id": "one",
                "repo": "o/r",
                "pr": 1,
                "category": "clean",
                "expected_verdict": "PASS",
            }
        ],
    }
    candidates = {
        "candidates": [
            {"provider": "openai", "model_id": "model-a"},
            {"provider": "openai", "model_id": "model-b"},
        ]
    }
    calls = []

    report = run_pilot(
        corpus,
        candidates,
        token="token",
        fetcher=lambda *args: (calls.append(args), ("PR #1", "diff"))[1],
        evaluator=lambda *_args, **_kwargs: SimpleNamespace(
            verdict="PASS", confidence=1, error=None
        ),
    )

    assert len(calls) == 1
    assert len(report["results"]) == 2


def test_summary_reports_category_agreement_errors_and_latency() -> None:
    summary = summarize_results(
        [
            {
                "provider": "openai",
                "model_id": "model-a",
                "category": "clean",
                "expected_verdict": "PASS",
                "actual_verdict": "PASS",
                "schema_valid": True,
                "latency_ms": 2,
            },
            {
                "provider": "openai",
                "model_id": "model-a",
                "category": "clean",
                "expected_verdict": "NON_PASS",
                "actual_verdict": "PASS",
                "schema_valid": False,
                "latency_ms": 3,
            },
        ]
    )

    candidate = summary["candidates"][0]
    assert candidate["latency_ms"] == 5.0
    assert candidate["schema_errors"] == 1
    assert candidate["categories"]["clean"] == {
        "rows": 2,
        "agreement": 1,
        "false_pass": 1,
        "false_fail": 0,
        "schema_errors": 1,
    }
