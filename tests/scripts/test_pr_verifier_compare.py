import json
import runpy
from pathlib import Path

import pytest
import scripts.langchain.pr_verifier as pr_verifier

from tests.scripts.verifier_capacity_fakes import with_capacity


def _valid_response(summary: str = "ok") -> str:
    return json.dumps(
        {
            "verdict": "PASS",
            "scores": {
                "correctness": 8,
                "completeness": 7,
                "quality": 7,
                "testing": 6,
                "risks": 5,
            },
            "concerns": [],
            "summary": summary,
        }
    )


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeClient:
    def __init__(self, name: str, calls: list[str], responses: list[str] | None = None) -> None:
        with_capacity(self)
        self.name = name
        self.calls = calls
        self.responses = list(responses or [_valid_response()])

    def invoke(self, prompt: str, **_kwargs: object) -> FakeResponse:
        self.calls.append(self.name)
        if self.responses:
            return FakeResponse(self.responses.pop(0))
        return FakeResponse(_valid_response())


def test_evaluate_pr_multiple_runs_sequentially(monkeypatch) -> None:
    calls: list[str] = []
    clients = [
        (FakeClient("first", calls), "provider-a", "model-a"),
        (FakeClient("second", calls), "provider-b", "model-b"),
    ]
    runner = pr_verifier.ComparisonRunner(
        context="context",
        diff=None,
        prompt="prompt",
        clients=clients,
    )
    monkeypatch.setattr(
        pr_verifier.ComparisonRunner,
        "from_environment",
        lambda context, diff, model1=None, model2=None: runner,
    )

    results = pr_verifier.evaluate_pr_multiple("context")

    assert calls == ["first", "second"]
    assert [
        (result.verdict, result.used_llm, result.provider_used, result.model, result.error)
        for result in results
    ] == [
        ("PASS", True, "provider-a", "model-a", None),
        ("PASS", True, "provider-b", "model-b", None),
    ]


def test_evaluate_pr_multiple_preserves_success_metadata(monkeypatch) -> None:
    calls: list[str] = []
    clients = [
        (
            FakeClient("github", calls, [_valid_response("github ok")]),
            "github-models/gpt-5.4",
            "gpt-5.4",
        ),
        (
            FakeClient("openai", calls, [_valid_response("openai ok")]),
            "openai/gpt-5.5",
            "gpt-5.5",
        ),
    ]
    runner = pr_verifier.ComparisonRunner(
        context="context",
        diff=None,
        prompt="prompt",
        clients=clients,
    )
    monkeypatch.setattr(
        pr_verifier.ComparisonRunner,
        "from_environment",
        lambda context, diff, model1=None, model2=None: runner,
    )

    results = pr_verifier.evaluate_pr_multiple("context")

    assert calls == ["github", "openai"]
    assert [
        (result.verdict, result.used_llm, result.provider_used, result.model, result.error)
        for result in results
    ] == [
        ("PASS", True, "github-models/gpt-5.4", "gpt-5.4", None),
        ("PASS", True, "openai/gpt-5.5", "gpt-5.5", None),
    ]


def test_evaluate_pr_multiple_keeps_error_shape_for_missing_json(monkeypatch) -> None:
    calls: list[str] = []
    clients = [
        (
            FakeClient("github", calls, ["No JSON here.", "Still no JSON."]),
            "github-models/gpt-5.4",
            "gpt-5.4",
        ),
        (
            FakeClient("openai", calls, [_valid_response("fallback judge ok")]),
            "openai/gpt-5.5",
            "gpt-5.5",
        ),
    ]
    runner = pr_verifier.ComparisonRunner(
        context="context",
        diff=None,
        prompt="prompt",
        clients=clients,
    )
    monkeypatch.setattr(
        pr_verifier.ComparisonRunner,
        "from_environment",
        lambda context, diff, model1=None, model2=None: runner,
    )

    results = pr_verifier.evaluate_pr_multiple("context")

    assert calls == ["github", "github", "openai"]
    failed, passed = results
    assert failed.verdict == "CONCERNS"
    assert failed.used_llm is True
    assert failed.provider_used == "github-models/gpt-5.4"
    assert failed.model == "gpt-5.4"
    assert failed.error is not None
    assert "Failed to parse JSON response" in failed.error
    assert passed.verdict == "PASS"
    assert passed.used_llm is True
    assert passed.provider_used == "openai/gpt-5.5"
    assert passed.model == "gpt-5.5"
    assert passed.error is None


def test_evaluate_pr_multiple_keeps_error_shape_for_malformed_json(monkeypatch) -> None:
    calls: list[str] = []
    clients = [
        (
            FakeClient(
                "github",
                calls,
                [
                    '{"verdict":"MAYBE","scores":{},"concerns":[],"summary":"bad"}',
                    '{"verdict":"PASS","scores":{},"concerns":[],"summary":"still bad"}',
                ],
            ),
            "github-models/gpt-5.4",
            "gpt-5.4",
        ),
        (
            FakeClient("openai", calls, [_valid_response("fallback judge ok")]),
            "openai/gpt-5.5",
            "gpt-5.5",
        ),
    ]
    runner = pr_verifier.ComparisonRunner(
        context="context",
        diff=None,
        prompt="prompt",
        clients=clients,
    )
    monkeypatch.setattr(
        pr_verifier.ComparisonRunner,
        "from_environment",
        lambda context, diff, model1=None, model2=None: runner,
    )

    results = pr_verifier.evaluate_pr_multiple("context")

    assert calls == ["github", "github", "openai"]
    failed, passed = results
    assert failed.verdict == "CONCERNS"
    assert failed.used_llm is True
    assert failed.provider_used == "github-models/gpt-5.4"
    assert failed.model == "gpt-5.4"
    assert failed.error is not None
    assert "Failed to parse JSON response after repair" in failed.error
    assert passed.verdict == "PASS"
    assert passed.used_llm is True
    assert passed.provider_used == "openai/gpt-5.5"
    assert passed.model == "gpt-5.5"
    assert passed.error is None


def test_evaluate_pr_multiple_falls_back_when_no_clients(monkeypatch) -> None:
    runner = pr_verifier.ComparisonRunner(
        context="context",
        diff=None,
        prompt="prompt",
        clients=[],
    )
    monkeypatch.setattr(
        pr_verifier.ComparisonRunner,
        "from_environment",
        lambda context, diff, model1=None, model2=None: runner,
    )

    results = pr_verifier.evaluate_pr_multiple("context")

    assert len(results) == 1
    assert results[0].used_llm is False
    assert results[0].verdict == "CONCERNS"
    assert results[0].scores is None
    error = results[0].error or ""
    assert "unverified" in error
    assert "cross-family" in error
    assert "available families: none" in error


def _assert_same_family_compare_blocked(
    results: list[pr_verifier.EvaluationResult],
    calls: list[str],
    *,
    family_label: str,
) -> None:
    assert calls == []
    assert len(results) == 1
    assert results[0].used_llm is False
    assert results[0].verdict == "CONCERNS"
    assert results[0].scores is None
    error = results[0].error or ""
    assert "unverified" in error
    assert "cross-family" in error
    assert f"available families: {family_label}" in error


def _run_compare_with_clients(
    monkeypatch,
    clients: list[tuple[str, str, str]],
) -> tuple[list[pr_verifier.EvaluationResult], list[str]]:
    calls: list[str] = []
    wired_clients = [
        (FakeClient(name, calls), provider, model) for name, provider, model in clients
    ]
    runner = pr_verifier.ComparisonRunner(
        context="context",
        diff=None,
        prompt="prompt",
        clients=wired_clients,
    )
    monkeypatch.setattr(
        pr_verifier.ComparisonRunner,
        "from_environment",
        lambda context, diff, model1=None, model2=None: runner,
    )
    results = pr_verifier.evaluate_pr_multiple("context")
    return results, calls


def test_evaluate_pr_multiple_blocks_same_family_only(monkeypatch) -> None:
    results, calls = _run_compare_with_clients(
        monkeypatch,
        [
            ("first", "openai/gpt-5.4", "gpt-5.4"),
            ("second", "openai/gpt-5.5", "gpt-5.5"),
        ],
    )

    _assert_same_family_compare_blocked(results, calls, family_label="openai")


def test_evaluate_pr_multiple_blocks_anthropic_same_family(monkeypatch) -> None:
    results, calls = _run_compare_with_clients(
        monkeypatch,
        [
            ("first", "anthropic/claude-3-5-sonnet", "claude-3-5-sonnet"),
            ("second", "claude/claude-3-opus", "claude-3-opus"),
        ],
    )

    _assert_same_family_compare_blocked(results, calls, family_label="anthropic")


def test_evaluate_pr_multiple_blocks_github_models_same_family(monkeypatch) -> None:
    results, calls = _run_compare_with_clients(
        monkeypatch,
        [
            ("first", "github-models/gpt-4o", "gpt-4o"),
            ("second", "github-models/azure-openai", "azure-openai"),
        ],
    )

    _assert_same_family_compare_blocked(results, calls, family_label="github-models")


# Tests for refactored client selection helpers


def test_get_provider_families_returns_unique_families() -> None:
    clients = [
        (object(), "openai/gpt-4", "gpt-4"),
        (object(), "anthropic/claude-3", "claude-3"),
        (object(), "openai/gpt-5", "gpt-5"),
    ]
    families = pr_verifier._get_provider_families(clients)
    assert families == {"openai", "anthropic"}


def test_get_provider_families_handles_empty_list() -> None:
    families = pr_verifier._get_provider_families([])
    assert families == set()


def test_get_provider_families_handles_github_models() -> None:
    clients = [
        (object(), "GitHub-Models/gpt-4o", "gpt-4o"),
        (object(), "openai/gpt-4", "gpt-4"),
    ]
    families = pr_verifier._get_provider_families(clients)
    assert families == {"github-models", "openai"}


def test_validate_comparison_clients_valid_cross_family() -> None:
    clients = [
        (object(), "openai/gpt-4", "gpt-4"),
        (object(), "anthropic/claude-3", "claude-3"),
    ]
    is_valid, error = pr_verifier._validate_comparison_clients(clients)
    assert is_valid is True
    assert error == ""


def test_validate_comparison_clients_invalid_single_client() -> None:
    clients = [(object(), "openai/gpt-4", "gpt-4")]
    is_valid, error = pr_verifier._validate_comparison_clients(clients)
    assert is_valid is False
    assert "unverified" in error
    assert "available families: openai" in error


def test_validate_comparison_clients_invalid_empty_clients() -> None:
    clients: list[tuple[object, str, str]] = []
    is_valid, error = pr_verifier._validate_comparison_clients(clients)
    assert is_valid is False
    assert "unverified" in error
    assert "available families: none" in error


def test_validate_comparison_clients_invalid_same_family() -> None:
    clients = [
        (object(), "openai/gpt-4", "gpt-4"),
        (object(), "openai/gpt-5", "gpt-5"),
    ]
    is_valid, error = pr_verifier._validate_comparison_clients(clients)
    assert is_valid is False
    assert "unverified" in error
    assert "available families: openai" in error


def test_validate_comparison_clients_valid_multiple_same_family_with_third() -> None:
    clients = [
        (object(), "openai/gpt-4", "gpt-4"),
        (object(), "openai/gpt-5", "gpt-5"),
        (object(), "anthropic/claude-3", "claude-3"),
    ]
    is_valid, error = pr_verifier._validate_comparison_clients(clients)
    assert is_valid is True
    assert error == ""


@pytest.mark.parametrize("omission", ["drop_acceptance", "drop_diff", "drop_file"])
def test_comparison_withholds_pass_for_late_required_omission(monkeypatch, omission) -> None:
    """The #3701 acceptance command must exercise the post-8k comparison floor.

    Reuse the production-shaped context generator from the extended coverage suite;
    these are deterministic controls, not historical production capture transcripts.
    """
    fixtures = runpy.run_path(str(Path(__file__).with_name("test_pr_verifier_prompt_coverage.py")))
    make_context = fixtures["_context"]
    complete, _ = make_context(4, 6000, 1200, ci_chars=9000)
    assert complete.index(fixtures["ACCEPTANCE_SENTINEL"]) > 8000
    assert pr_verifier.prompt_coverage(complete, None).sufficient
    options = {omission: 3 if omission == "drop_file" else True}
    incomplete, _ = make_context(4, 6000, 1200, ci_chars=9000, **options)
    calls = []
    clients = [
        (FakeClient("first", calls), "openai", "first-model"),
        (FakeClient("second", calls), "anthropic", "second-model"),
    ]
    monkeypatch.setattr(pr_verifier, "_get_llm_clients", lambda m1=None, m2=None: clients)
    results = pr_verifier.evaluate_pr_multiple(incomplete)
    assert len(results) == 2
    assert calls == ["first", "second"]
    assert all(result.verdict == "CONCERNS" for result in results)
    assert all(not result.input_coverage["sufficient"] for result in results)


@pytest.mark.parametrize("status", ["included", "truncated", "unavailable"])
@pytest.mark.parametrize("required", [True, False])
def test_comparison_consumes_linked_issue_discovery(monkeypatch, status, required) -> None:
    fixtures = runpy.run_path(str(Path(__file__).with_name("test_pr_verifier_prompt_coverage.py")))
    context, _ = fixtures["_context"](1, 1000, 500)
    inventory = {
        "schema": "verifier-context-source-coverage/v1",
        "acceptance_source_discovery": {"status": status, "required": required},
    }
    block = "## Context source coverage\n\n```json\n" + json.dumps(inventory) + "\n```\n\n"
    context = context.replace("## CI Information", block + "## CI Information", 1)
    calls = []
    clients = [
        (FakeClient("first", calls), "openai", "first-model"),
        (FakeClient("second", calls), "anthropic", "second-model"),
    ]
    monkeypatch.setattr(pr_verifier, "_get_llm_clients", lambda m1=None, m2=None: clients)
    results = pr_verifier.evaluate_pr_multiple(context)
    assert calls == ["first", "second"]
    blocked = required and status != "included"
    assert [result.verdict for result in results] == ["CONCERNS" if blocked else "PASS"] * 2
    assert all(result.input_coverage["sufficient"] is not blocked for result in results)
    assert all(
        result.input_coverage["acceptance_source_discovery"]
        == ({"included": "complete"}.get(status, status) if required else "not_declared")
        for result in results
    )


@pytest.mark.parametrize(
    "files,code_chars,acceptance_chars,sufficient",
    [(30, 159700, 9000, False), (11, 75300, 3200, False), (9, 27600, 1500, True)],
    ids=["workflows-3601-shape", "manager-database-1703-shape", "pension-data-912-shape"],
)
def test_named_comparison_command_covers_three_maint78_shapes(
    monkeypatch, files, code_chars, acceptance_chars, sufficient
) -> None:
    """Exercise the production comparison factory with recorded capture dimensions."""
    fixtures = runpy.run_path(str(Path(__file__).with_name("test_pr_verifier_prompt_coverage.py")))
    context, paths = fixtures["_context"](files, code_chars, acceptance_chars)
    monkeypatch.setattr(pr_verifier, "_get_llm_clients", lambda m1=None, m2=None: [])
    runner = pr_verifier.ComparisonRunner.from_environment(context, None)
    assert runner.coverage.sufficient is sufficient
    assert runner.coverage.to_dict()["files_omitted"] == 0
    assert fixtures["ACCEPTANCE_SENTINEL"] in runner.prompt
    assert all(f"diff --git a/{path} b/{path}" in runner.prompt for path in paths)
