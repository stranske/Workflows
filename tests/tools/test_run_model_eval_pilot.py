import json
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
            {"case_id": "one", "provider": "openai", "model_id": "working", "schema_valid": True},
            {"case_id": "two", "provider": "openai", "model_id": "working", "schema_valid": True},
            {"case_id": "one", "provider": "anthropic", "model_id": "broken", "schema_valid": True},
            {
                "case_id": "two",
                "provider": "anthropic",
                "model_id": "broken",
                "schema_valid": False,
            },
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


def test_fetch_pr_skips_inaccessible_linked_issue(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        pilot.api_client,
        "fetch_pull_request",
        lambda *_: {"title": "PR", "body": "Closes #12"},
    )
    monkeypatch.setattr(pilot.api_client, "fetch_pull_request_diff", lambda *_: "diff")
    monkeypatch.setattr(
        pilot.api_client,
        "fetch_issue",
        lambda *_: (_ for _ in ()).throw(RuntimeError("forbidden")),
    )

    context, _ = pilot.fetch_pr("owner/repo", 13, "token")

    assert "Repository: owner/repo" in context
    assert "Linked source issues" not in context
    assert "pilot: skipping linked issue #12: forbidden" in capsys.readouterr().err


def test_linked_issue_numbers_accepts_inline_references_and_deduplicates() -> None:
    assert pilot._linked_issue_numbers(
        "This closes #12; related to: #12 and fixes #13. Resolves #99.", pr_number=99
    ) == [12, 13]


def test_fetch_pr_bounds_and_guards_linked_issue_text(monkeypatch) -> None:
    monkeypatch.setattr(
        pilot.api_client,
        "fetch_pull_request",
        lambda *_: {"title": "PR", "body": "Closes #12"},
    )
    monkeypatch.setattr(pilot.api_client, "fetch_pull_request_diff", lambda *_: "diff")
    monkeypatch.setattr(
        pilot.api_client,
        "fetch_issue",
        lambda *_: {"title": "Source", "body": "unsafe body"},
    )
    monkeypatch.setattr(pilot.api_client, "fetch_issue_comments", lambda *_: [])
    monkeypatch.setattr(
        pilot,
        "check_prompt_injection",
        lambda text: {"blocked": text == "unsafe body", "code": "INSTRUCTION_OVERRIDE"},
    )

    context, _ = pilot.fetch_pr("owner/repo", 13, "token")

    assert "unsafe body" not in context
    assert "INSTRUCTION_OVERRIDE" in context


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
        "latency_ms": 5.0,
    }


def test_main_reports_malformed_corpus_without_traceback(monkeypatch, tmp_path, capsys) -> None:
    corpus = tmp_path / "corpus.json"
    candidates = tmp_path / "candidates.json"
    output = tmp_path / "report.json"
    corpus.write_text(json.dumps({"corpus_version": "v1", "cases": []}))
    candidates.write_text(json.dumps({"candidates": []}))
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(
        pilot.sys,
        "argv",
        [
            "run_model_eval_pilot.py",
            "--corpus",
            str(corpus),
            "--candidates",
            str(candidates),
            "--output",
            str(output),
        ],
    )

    assert pilot.main() == 1
    assert (
        "pilot preflight error: pilot corpus requires at least one case" in capsys.readouterr().err
    )
