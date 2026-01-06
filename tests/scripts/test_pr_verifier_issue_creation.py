import json

import scripts.langchain.pr_verifier as pr_verifier


def test_extract_pr_metadata() -> None:
    context = (
        "# Verifier context\n" "- Pull request: [#123](https://github.com/org/repo/pull/123)\n"
    )
    pr_number, pr_url = pr_verifier._extract_pr_metadata(context)
    assert pr_number == 123
    assert pr_url == "https://github.com/org/repo/pull/123"


def test_format_followup_issue_body_includes_concerns() -> None:
    result = pr_verifier.EvaluationResult(
        verdict="CONCERNS",
        scores=pr_verifier.EvaluationScores(
            correctness=6,
            completeness=7,
            quality=5,
            testing=4,
            risks=3,
        ),
        concerns=["Missing regression test coverage."],
        summary="Evaluation flagged testing gaps.",
    )
    body = pr_verifier._format_followup_issue_body(
        result,
        pr_number=12,
        pr_url="https://example.com/pr/12",
        run_url="https://example.com/run/99",
    )
    assert "## LLM Evaluation Follow-up" in body
    assert "- Verdict: CONCERNS" in body
    assert "- Missing regression test coverage." in body
    assert "- PR: https://example.com/pr/12" in body


def test_create_followup_issue_skips_without_token(monkeypatch) -> None:
    result = pr_verifier.EvaluationResult(verdict="CONCERNS")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    issue_number = pr_verifier._create_followup_issue(
        result,
        "Pull request: #5",
        labels=["agent:codex"],
        run_url=None,
    )
    assert issue_number is None


def test_create_followup_issue_posts(monkeypatch) -> None:
    result = pr_verifier.EvaluationResult(verdict="FAIL", concerns=["Issue found."])
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "org/repo")

    captured = {}

    class FakeResponse:
        def __init__(self):
            self._data = json.dumps({"number": 99}).encode("utf-8")

        def read(self):
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request):
        captured["url"] = request.full_url
        captured["body"] = request.data
        return FakeResponse()

    monkeypatch.setattr(pr_verifier.urllib.request, "urlopen", fake_urlopen)

    issue_number = pr_verifier._create_followup_issue(
        result,
        "- Pull request: [#99](https://example.com/pr/99)",
        labels=["agent:codex"],
        run_url="https://example.com/run/99",
    )

    assert issue_number == 99
    assert captured["url"] == "https://api.github.com/repos/org/repo/issues"
    payload = json.loads(captured["body"].decode("utf-8"))
    assert payload["title"] == "LLM evaluation concerns for PR #99"
    assert payload["labels"] == ["agent:codex"]
