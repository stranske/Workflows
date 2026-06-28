from types import SimpleNamespace
from unittest.mock import Mock

import scripts.test_openai_provider as smoke


def test_test_openai_provider_returns_one_when_openai_unavailable(
    monkeypatch,
    capsys,
) -> None:
    get_provider = Mock()
    monkeypatch.setattr(
        smoke,
        "check_providers",
        Mock(
            return_value={
                "github-models": True,
                "openai": False,
                "anthropic": False,
                "regex-fallback": True,
            }
        ),
    )
    monkeypatch.setattr(smoke, "get_llm_provider", get_provider)

    exit_code = smoke.test_openai_provider()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Provider availability:" in captured.out
    assert "openai" in captured.out
    assert "OPENAI_API_KEY not set - cannot test OpenAI provider" in captured.out
    assert captured.err == ""
    get_provider.assert_not_called()


def test_test_openai_provider_returns_zero_and_prints_analysis_summary(
    monkeypatch,
    capsys,
) -> None:
    provider = Mock()
    provider.name = "openai"
    provider.analyze_completion.return_value = SimpleNamespace(
        provider_used="openai",
        confidence=0.75,
        completed_tasks=["Fix login bug"],
        in_progress_tasks=["Add unit tests"],
        reasoning="Mocked analysis completed without a provider call.",
    )
    get_provider = Mock(return_value=provider)
    monkeypatch.setattr(
        smoke,
        "check_providers",
        Mock(
            return_value={
                "github-models": False,
                "openai": True,
                "anthropic": False,
                "regex-fallback": True,
            }
        ),
    )
    monkeypatch.setattr(smoke, "get_llm_provider", get_provider)

    exit_code = smoke.test_openai_provider()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Testing OpenAI provider directly..." in captured.out
    assert "Provider: openai" in captured.out
    assert "OpenAI provider working!" in captured.out
    assert "Confidence: 75%" in captured.out
    assert "Completed: ['Fix login bug']" in captured.out
    assert "In progress: ['Add unit tests']" in captured.out
    assert "Reasoning: Mocked analysis completed without a provider call...." in captured.out
    assert captured.err == ""
    get_provider.assert_called_once_with(force_provider="openai")
    provider.analyze_completion.assert_called_once()


def test_test_openai_provider_returns_one_and_redacts_provider_exception_secret(
    monkeypatch,
    capsys,
) -> None:
    secret = "sk-testsecretvalue1234567890"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    provider = Mock()
    provider.name = "openai"
    provider.analyze_completion.side_effect = RuntimeError(f"authentication failed for {secret}")
    monkeypatch.setattr(
        smoke,
        "check_providers",
        Mock(
            return_value={
                "github-models": False,
                "openai": True,
                "anthropic": False,
                "regex-fallback": True,
            }
        ),
    )
    monkeypatch.setattr(smoke, "get_llm_provider", Mock(return_value=provider))

    exit_code = smoke.test_openai_provider()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "OpenAI provider failed:" in captured.out
    assert "<redacted>" in captured.out
    assert secret not in captured.out
    assert secret not in captured.err
