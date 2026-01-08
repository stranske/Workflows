"""Tests for PR verifier auth error fallback."""

import scripts.langchain.pr_verifier as pr_verifier


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeClient:
    def __init__(self, name: str, succeed: bool = True) -> None:
        self.name = name
        self.succeed = succeed
        self.invoked = False

    def invoke(self, prompt: str) -> FakeResponse:
        self.invoked = True
        if not self.succeed:
            raise Exception("401 Unauthorized: models permission required")
        return FakeResponse(
            '{"verdict":"PASS","scores":{"correctness":8,"completeness":7,'
            '"quality":7,"testing":6,"risks":5},"concerns":[],"summary":"ok"}'
        )


def test_is_auth_error_detects_401() -> None:
    exc = Exception("401 Unauthorized: models permission required")
    assert pr_verifier._is_auth_error(exc) is True


def test_is_auth_error_detects_forbidden() -> None:
    exc = Exception("403 Forbidden: access denied")
    assert pr_verifier._is_auth_error(exc) is True


def test_is_auth_error_detects_permission() -> None:
    exc = Exception("Error: permission denied for models API")
    assert pr_verifier._is_auth_error(exc) is True


def test_is_auth_error_rejects_other_errors() -> None:
    exc = Exception("Rate limit exceeded")
    assert pr_verifier._is_auth_error(exc) is False


def test_evaluate_pr_falls_back_on_auth_error(monkeypatch) -> None:
    """When primary provider fails with auth error, fallback to alternate provider."""
    primary_client = FakeClient("github-models", succeed=False)
    fallback_client = FakeClient("openai", succeed=True)

    call_count = [0]

    def mock_get_client(model=None, provider=None):
        call_count[0] += 1
        if call_count[0] == 1:
            # First call: return failing github-models client
            return (primary_client, "github-models/gpt-4o")
        else:
            # Second call: return working openai client
            return (fallback_client, "openai/gpt-4o")

    monkeypatch.setattr(pr_verifier, "_get_llm_client", mock_get_client)
    monkeypatch.setattr(pr_verifier, "_prepare_prompt", lambda ctx, diff: "test prompt")

    result = pr_verifier.evaluate_pr("test context")

    assert primary_client.invoked is True
    assert fallback_client.invoked is True
    assert result.verdict == "PASS"
    assert result.provider_used == "openai/gpt-4o"
    assert "fallback" in (result.error or "").lower()


def test_evaluate_pr_no_fallback_when_provider_explicit(monkeypatch) -> None:
    """When provider is explicitly specified, don't fallback on auth error."""
    primary_client = FakeClient("github-models", succeed=False)

    def mock_get_client(model=None, provider=None):
        return (primary_client, "github-models/gpt-4o")

    monkeypatch.setattr(pr_verifier, "_get_llm_client", mock_get_client)
    monkeypatch.setattr(pr_verifier, "_prepare_prompt", lambda ctx, diff: "test prompt")

    # Explicitly request github-models - should NOT fallback
    result = pr_verifier.evaluate_pr("test context", provider="github-models")

    assert primary_client.invoked is True
    assert result.used_llm is False  # Fallback evaluation
    assert "401" in (result.error or "")


def test_evaluate_pr_no_fallback_on_non_auth_error(monkeypatch) -> None:
    """When error is not auth-related, don't attempt fallback."""

    class RateLimitClient:
        def invoke(self, prompt: str):
            raise Exception("Rate limit exceeded")

    def mock_get_client(model=None, provider=None):
        return (RateLimitClient(), "github-models/gpt-4o")

    monkeypatch.setattr(pr_verifier, "_get_llm_client", mock_get_client)
    monkeypatch.setattr(pr_verifier, "_prepare_prompt", lambda ctx, diff: "test prompt")

    result = pr_verifier.evaluate_pr("test context")

    assert result.used_llm is False
    assert "Rate limit" in (result.error or "")
