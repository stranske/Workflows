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
