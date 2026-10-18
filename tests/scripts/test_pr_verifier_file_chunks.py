"""Whole changed-file review and honest incomplete-input disposition (#4036)."""

import json
from types import SimpleNamespace

import pytest
from scripts.langchain import pr_verifier as verifier


def patch(name, size=20000):
    return (
        f"diff --git a/{name} b/{name}\n--- a/{name}\n+++ b/{name}\n@@ -1 +1 @@\n-old\n"
        + "+"
        + "x" * size
        + "\n"
    )


class Client:
    def __init__(self, verdicts=()):
        self.prompts = []
        self.verdicts = iter(verdicts)

    def invoke(self, prompt, **kwargs):
        self.prompts.append(prompt)
        verdict = next(self.verdicts, "PASS")
        return SimpleNamespace(
            content=json.dumps(
                {
                    "verdict": verdict,
                    "summary": "File reviewed.",
                    "concerns": ["Real code defect"] if verdict in {"CONCERNS", "FAIL"} else [],
                }
            )
        )


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.delenv("VERIFIER_SEMANTIC_MODE", raising=False)
    monkeypatch.delenv("VERIFIER_EVIDENCE_PROFILE", raising=False)
    monkeypatch.setenv("VERIFIER_DIFF_BUDGET_TOKENS", "16000")
    monkeypatch.setattr(verifier, "_get_llm_clients", lambda *args: [])


def evaluate(monkeypatch, client, diff):
    monkeypatch.setattr(verifier, "_get_llm_client", lambda **kwargs: (client, "openai"))
    return verifier.evaluate_pr("Review the supplied changed files.", diff=diff)


def test_nine_file_diff_reviewed_fully_without_truncated_input(setup, monkeypatch):
    client = Client()
    patches = [patch(f"file_{i}.py") for i in range(9)]
    result = evaluate(monkeypatch, client, "".join(patches))
    for prompt in client.prompts:
        assert "truncated" not in prompt, "truncated provider input"
    assert len(client.prompts) > 1, "single-shot truncated review: expected multiple chunks"
    for item in patches:
        assert sum(item.strip() in prompt for prompt in client.prompts) == 1, "truncated file patch"
    assert result.verdict == "PASS"
    assert result.files_not_reviewed == []
    assert result.input_coverage["files_complete"] == 9
    assert "files reviewed 9 of 9" in verifier.format_comparison_report([result])
    assert "truncated" not in verifier.format_comparison_report([result])


def test_oversized_file_is_explicitly_unreviewed(setup, monkeypatch):
    client = Client()
    result = evaluate(monkeypatch, client, patch("small.py") + patch("huge.py", 65000))
    assert result.verdict == "UNVERIFIABLE_INPUT"
    assert result.files_not_reviewed == ["huge.py"]
    assert "files reviewed 1 of 2" in verifier.format_comparison_report([result])
    assert not any("diff --git a/huge.py" in prompt for prompt in client.prompts)


def test_request_limit_preserves_exact_unreviewed_file_list(setup, monkeypatch):
    monkeypatch.setattr(verifier, "MAX_REVIEW_CHUNKS", 2)
    result = evaluate(monkeypatch, Client(), "".join(patch(f"{i}.py", 40000) for i in range(4)))
    assert result.verdict == "UNVERIFIABLE_INPUT"
    assert result.files_not_reviewed == ["2.py", "3.py"]


@pytest.mark.parametrize("finding", ["CONCERNS", "FAIL"])
def test_real_finding_dominates_incomplete_input(setup, monkeypatch, finding):
    result = evaluate(monkeypatch, Client([finding]), patch("small.py") + patch("huge.py", 65000))
    assert result.verdict == finding
    assert result.concerns == ["Real code defect"]
    assert (
        verifier.comparison_verdict(
            [result, verifier.EvaluationResult(verdict="UNVERIFIABLE_INPUT")]
        )
        == finding
    )


def test_comparison_uses_same_chunk_review(setup):
    client = Client()
    diff = "".join(patch(f"{i}.py") for i in range(9))
    runner = verifier.ComparisonRunner("context", diff, "unused single prompt", [])
    result = runner.run_single(client, "openai", "model")
    assert result.verdict == "PASS"
    assert len(client.prompts) == 4  # Three file chunks plus global acceptance reconciliation.


def test_incomplete_coverage_does_not_relabel_real_finding(setup):
    coverage = verifier.prompt_coverage("context", None)
    for verdict in ["PASS", "CONCERNS", "FAIL"]:
        result = verifier._apply_coverage_floor(
            verifier.EvaluationResult(verdict=verdict, used_llm=True), coverage
        )
        assert result.verdict == ("UNVERIFIABLE_INPUT" if verdict == "PASS" else verdict)


def test_incomplete_context_is_not_sent_as_a_finding_request(setup, monkeypatch):
    from tests.scripts.test_pr_verifier_prompt_coverage import _context

    context, _ = _context(1, 1000, 1000)
    monkeypatch.setenv("VERIFIER_CONTEXT_BUDGET_TOKENS", "1")
    client = Client(["CONCERNS"])
    monkeypatch.setattr(verifier, "_get_llm_client", lambda **kwargs: (client, "openai"))
    result = verifier.evaluate_pr(context)
    assert result.verdict == "UNVERIFIABLE_INPUT"
    assert not client.prompts


def test_provider_unreviewed_file_list_survives_parsing_and_rendering(setup):
    response = json.dumps({"verdict": "UNVERIFIABLE_INPUT", "files_not_reviewed": ["a.py"]})
    result = verifier._parse_llm_response(response, "openai")
    result = verifier._apply_coverage_floor(
        result, verifier.prompt_coverage("context", patch("a.py"))
    )
    assert result.files_not_reviewed == ["a.py"]
    assert "files reviewed 0 of 1" in verifier.format_comparison_report([result])


@pytest.mark.parametrize(
    "error", [RuntimeError("provider unavailable"), verifier.InputCapacityError("limit")]
)
def test_chunk_exception_is_unverifiable_with_exact_unreviewed_files(setup, monkeypatch, error):
    def invoke(*args, **kwargs):
        raise error

    monkeypatch.setattr(verifier, "_invoke_llm", invoke)
    result = evaluate(monkeypatch, Client(), patch("a.py", 40000) + patch("b.py", 40000))
    assert result.verdict == "UNVERIFIABLE_INPUT"
    assert result.files_not_reviewed == ["a.py", "b.py"]
    assert result.input_coverage["files_complete"] == 0
    assert verifier.comparison_verdict([result]) == "UNVERIFIABLE_INPUT"


def test_local_passes_cannot_hide_unimplemented_global_criterion(setup, monkeypatch):
    client = Client(["PASS", "PASS", "PASS", "CONCERNS"])
    monkeypatch.setattr(verifier, "_get_llm_client", lambda **kwargs: (client, "openai"))
    result = verifier.evaluate_pr(
        "Acceptance: implement a cache invalidation function named invalidate_cache.",
        diff="".join(patch(f"{i}.py") for i in range(9)),
    )
    assert result.files_not_reviewed == []
    assert result.verdict == "CONCERNS"
    assert "criterion that no chunk implements" in client.prompts[-1]
    assert "invalidate_cache" in client.prompts[-1]
    assert all(f"{i}.py" in client.prompts[-1] for i in range(9))


def test_chunk_preflight_receives_the_exact_local_prompt(setup, monkeypatch):
    invoke = verifier._invoke_llm

    def checked(client, prompt, *, operation, context=None, diff=None):
        if operation == "evaluate_pr_chunk":
            assert prompt == verifier._prepare_prompt(context, diff)
            assert verifier.prompt_coverage(context, diff).sufficient
        return invoke(client, prompt, operation=operation, context=context, diff=diff)

    monkeypatch.setattr(verifier, "_invoke_llm", checked)
    result = evaluate(monkeypatch, Client(), "".join(patch(f"{i}.py") for i in range(9)))
    assert result.verdict == "PASS"


@pytest.mark.parametrize("reject", [False, True])
def test_expanded_chunks_run_preflight_and_preserve_capacity_failure(setup, monkeypatch, reject):
    from tests.scripts.verifier_capacity_fakes import complete_capture_context, with_capacity

    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    client = with_capacity(Client())
    if reject:
        client.root_client.responses.input_tokens.count.side_effect = RuntimeError(
            "counter unavailable"
        )
    context = complete_capture_context()
    first, second = patch("a.py", 40000), patch("b.py", 40000)
    old = verifier._strip_diff_fence(dict(verifier._split_verifier_context(context))["full_diff"])
    context = (
        context.replace(old, first + second)
        .replace("- Files changed: 1", "- Files changed: 2")
        .replace("- a.py (+1/-1)", "- a.py (+1/-1)\n- b.py (+1/-1)")
    )
    monkeypatch.setattr(verifier, "_get_llm_client", lambda **kwargs: (client, "openai"))
    result = verifier.evaluate_pr(context, diff=first + second)
    if reject:
        assert result.verdict == "UNVERIFIABLE_INPUT"
        assert result.files_not_reviewed == ["a.py", "b.py"]
        assert "counter unavailable" in result.summary
        assert "counter unavailable" in result.error
        assert not client.prompts
    else:
        assert result.verdict == "PASS", result.summary
        assert result.files_not_reviewed == []
        assert len(client.prompts) == 3
        assert client.root_client.responses.input_tokens.count.call_count == 3


def test_chunk_aggregate_preserves_provider_unreviewed_files(setup, monkeypatch):
    class PartialClient(Client):
        def invoke(self, prompt, **kwargs):
            response = super().invoke(prompt, **kwargs)
            response.content = json.dumps(
                {
                    "verdict": "PASS",
                    "files_not_reviewed": ["a.py"] if "diff --git a/a.py" in prompt else [],
                }
            )
            return response

    result = evaluate(monkeypatch, PartialClient(), patch("a.py", 40000) + patch("b.py", 40000))
    assert result.verdict == "UNVERIFIABLE_INPUT"
    assert result.files_not_reviewed == ["a.py"]
    assert result.input_coverage["files_complete"] == 1


@pytest.mark.parametrize("verdict", ["PASS", "CONCERNS", "FAIL"])
def test_provider_omission_withholds_single_review_pass_but_preserves_findings(setup, verdict):
    result = verifier._apply_coverage_floor(
        verifier.EvaluationResult(verdict=verdict, used_llm=True, files_not_reviewed=["a.py"]),
        verifier.prompt_coverage("context", patch("a.py")),
    )
    assert result.verdict == ("UNVERIFIABLE_INPUT" if verdict == "PASS" else verdict)
    assert result.files_not_reviewed == ["a.py"]
