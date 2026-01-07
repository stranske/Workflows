import scripts.langchain.pr_verifier as pr_verifier


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeClient:
    def __init__(self, name: str, calls: list[str]) -> None:
        self.name = name
        self.calls = calls

    def invoke(self, prompt: str) -> FakeResponse:
        self.calls.append(self.name)
        return FakeResponse(
            '{"verdict":"PASS","scores":{"correctness":8,"completeness":7,'
            '"quality":7,"testing":6,"risks":5},"concerns":[],"summary":"ok"}'
        )


def test_evaluate_pr_multiple_runs_sequentially(monkeypatch) -> None:
    calls: list[str] = []
    clients = [
        (FakeClient("first", calls), "provider-a"),
        (FakeClient("second", calls), "provider-b"),
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
    assert [result.provider_used for result in results] == ["provider-a", "provider-b"]


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
