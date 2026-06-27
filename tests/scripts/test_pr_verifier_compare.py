import json

import scripts.langchain.pr_verifier as pr_verifier


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
    assert "unverified" in (results[0].error or "")


def test_evaluate_pr_multiple_blocks_same_family_only(monkeypatch) -> None:
    calls: list[str] = []
    clients = [
        (FakeClient("first", calls), "openai/gpt-5.4", "gpt-5.4"),
        (FakeClient("second", calls), "openai/gpt-5.5", "gpt-5.5"),
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

    assert calls == []
    assert len(results) == 1
    assert results[0].used_llm is False
    assert results[0].verdict == "CONCERNS"
    assert "unverified" in (results[0].error or "")
