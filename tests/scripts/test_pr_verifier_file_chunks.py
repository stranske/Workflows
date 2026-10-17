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
    assert len(client.prompts) == 3


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
