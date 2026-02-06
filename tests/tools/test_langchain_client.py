"""Tests for tools/langchain_client.py."""

from __future__ import annotations

import sys
import types

import pytest

from tools import langchain_client


def _install_fake_langchain_openai(monkeypatch: pytest.MonkeyPatch):
    fake_module = types.ModuleType("langchain_openai")

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_module.ChatOpenAI = FakeChatOpenAI
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)
    return FakeChatOpenAI


def test_build_chat_client_prefers_github_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """GitHub Models should be preferred when both tokens are set."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.delenv(langchain_client.ENV_PROVIDER, raising=False)
    monkeypatch.delenv(langchain_client.ENV_MODEL, raising=False)

    resolved = langchain_client.build_chat_client()

    assert resolved is not None
    assert resolved.provider == langchain_client.PROVIDER_GITHUB
    assert isinstance(resolved.client, FakeChatOpenAI)
    assert resolved.client.kwargs["api_key"] == "gh-token"
    assert resolved.client.kwargs["base_url"] == langchain_client.GITHUB_MODELS_BASE_URL


def test_build_chat_client_openai_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenAI is used when GitHub token is missing."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.delenv(langchain_client.ENV_PROVIDER, raising=False)

    resolved = langchain_client.build_chat_client()

    assert resolved is not None
    assert resolved.provider == langchain_client.PROVIDER_OPENAI
    assert isinstance(resolved.client, FakeChatOpenAI)
    assert resolved.client.kwargs["api_key"] == "oa-token"
    assert "base_url" not in resolved.client.kwargs


def test_build_chat_client_env_provider_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider override env var should force OpenAI when set."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.setenv(langchain_client.ENV_PROVIDER, "openai")

    resolved = langchain_client.build_chat_client()

    assert resolved is not None
    assert resolved.provider == langchain_client.PROVIDER_OPENAI
    assert isinstance(resolved.client, FakeChatOpenAI)
    assert resolved.client.kwargs["api_key"] == "oa-token"


def test_build_chat_client_env_provider_override_github(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider override env var should force GitHub Models when set."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.setenv(langchain_client.ENV_PROVIDER, "github-models")

    resolved = langchain_client.build_chat_client()

    assert resolved is not None
    assert resolved.provider == langchain_client.PROVIDER_GITHUB
    assert isinstance(resolved.client, FakeChatOpenAI)
    assert resolved.client.kwargs["api_key"] == "gh-token"
    assert resolved.client.kwargs["base_url"] == langchain_client.GITHUB_MODELS_BASE_URL


def test_build_chat_client_env_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Model override env var should update the constructed model."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv(langchain_client.ENV_MODEL, "gpt-4o-mini")
    monkeypatch.delenv(langchain_client.ENV_PROVIDER, raising=False)

    resolved = langchain_client.build_chat_client()

    assert resolved is not None
    assert resolved.model == "gpt-4o-mini"
    assert isinstance(resolved.client, FakeChatOpenAI)
    assert resolved.client.kwargs["model"] == "gpt-4o-mini"


def test_build_chat_client_env_overrides_provider_and_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider+model env overrides should be honored together."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.setenv(langchain_client.ENV_PROVIDER, "github-models")
    monkeypatch.setenv(langchain_client.ENV_MODEL, "gpt-4o-mini")

    resolved = langchain_client.build_chat_client()

    assert resolved is not None
    assert resolved.provider == langchain_client.PROVIDER_GITHUB
    assert resolved.model == "gpt-4o-mini"
    assert isinstance(resolved.client, FakeChatOpenAI)
    assert resolved.client.kwargs["base_url"] == langchain_client.GITHUB_MODELS_BASE_URL


def test_build_chat_client_invalid_env_provider_falls_back(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Invalid provider overrides should fall back to auto-selection."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.setenv(langchain_client.ENV_PROVIDER, "not-a-provider")

    with caplog.at_level("WARNING"):
        resolved = langchain_client.build_chat_client()

    assert resolved is not None
    assert resolved.provider == langchain_client.PROVIDER_GITHUB
    assert isinstance(resolved.client, FakeChatOpenAI)
    assert "Invalid provider" in caplog.text


def test_build_chat_client_invalid_provider_argument_falls_back(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Invalid provider argument should fall back to auto-selection."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")

    with caplog.at_level("WARNING"):
        resolved = langchain_client.build_chat_client(provider="not-a-provider")

    assert resolved is not None
    assert resolved.provider == langchain_client.PROVIDER_GITHUB
    assert isinstance(resolved.client, FakeChatOpenAI)
    assert "Invalid provider" in caplog.text


def test_build_chat_client_force_openai_falls_back_to_github(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """force_openai should fall back to GitHub Models when OpenAI key is missing."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with caplog.at_level("WARNING"):
        resolved = langchain_client.build_chat_client(force_openai=True)

    assert resolved is not None
    assert resolved.provider == langchain_client.PROVIDER_GITHUB
    assert isinstance(resolved.client, FakeChatOpenAI)
    assert resolved.client.kwargs["api_key"] == "gh-token"
    assert resolved.client.kwargs["base_url"] == langchain_client.GITHUB_MODELS_BASE_URL
    assert "falling back to GitHub Models" in caplog.text


def test_build_chat_client_force_openai_missing_key_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """force_openai should raise a controlled exception when no fallback exists."""
    _install_fake_langchain_openai(monkeypatch)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(langchain_client.MissingOpenAIAPIKeyError):
        langchain_client.build_chat_client(force_openai=True)


def test_build_chat_client_env_timeout_and_retries_are_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timeout and retry defaults should be read from env at call time."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    monkeypatch.setenv(langchain_client.ENV_TIMEOUT, "25")
    monkeypatch.setenv(langchain_client.ENV_MAX_RETRIES, "7")
    resolved = langchain_client.build_chat_client()
    assert resolved is not None
    assert isinstance(resolved.client, FakeChatOpenAI)
    assert resolved.client.kwargs["timeout"] == 25
    assert resolved.client.kwargs["max_retries"] == 7

    monkeypatch.setenv(langchain_client.ENV_TIMEOUT, "42")
    monkeypatch.setenv(langchain_client.ENV_MAX_RETRIES, "3")
    resolved = langchain_client.build_chat_client()
    assert resolved is not None
    assert resolved.client.kwargs["timeout"] == 42
    assert resolved.client.kwargs["max_retries"] == 3


def test_build_chat_clients_env_timeout_and_retries_are_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timeout and retry env overrides should be honored per call for client lists."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.delenv(langchain_client.ENV_PROVIDER, raising=False)

    monkeypatch.setenv(langchain_client.ENV_TIMEOUT, "15")
    monkeypatch.setenv(langchain_client.ENV_MAX_RETRIES, "5")
    clients = langchain_client.build_chat_clients()
    assert all(isinstance(client.client, FakeChatOpenAI) for client in clients)
    assert [client.client.kwargs["timeout"] for client in clients] == [15, 15]
    assert [client.client.kwargs["max_retries"] for client in clients] == [5, 5]

    monkeypatch.setenv(langchain_client.ENV_TIMEOUT, "33")
    monkeypatch.setenv(langchain_client.ENV_MAX_RETRIES, "2")
    clients = langchain_client.build_chat_clients()
    assert [client.client.kwargs["timeout"] for client in clients] == [33, 33]
    assert [client.client.kwargs["max_retries"] for client in clients] == [2, 2]


def test_build_chat_clients_auto_selects_github_then_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auto selection returns GitHub then OpenAI when both tokens exist."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.delenv(langchain_client.ENV_PROVIDER, raising=False)
    monkeypatch.delenv(langchain_client.ENV_MODEL, raising=False)

    clients = langchain_client.build_chat_clients()

    assert [client.provider for client in clients] == [
        langchain_client.PROVIDER_GITHUB,
        langchain_client.PROVIDER_OPENAI,
    ]
    assert all(isinstance(client.client, FakeChatOpenAI) for client in clients)


def test_build_chat_clients_env_provider_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider override env var should force OpenAI for both models."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.setenv(langchain_client.ENV_PROVIDER, "openai")

    clients = langchain_client.build_chat_clients(model1="gpt-4o-mini", model2="gpt-4o")

    assert [client.provider for client in clients] == [
        langchain_client.PROVIDER_OPENAI,
        langchain_client.PROVIDER_OPENAI,
    ]
    assert [client.model for client in clients] == ["gpt-4o-mini", "gpt-4o"]
    assert all(isinstance(client.client, FakeChatOpenAI) for client in clients)


def test_build_chat_clients_env_provider_override_github(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider override env var should force GitHub Models when set."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.setenv(langchain_client.ENV_PROVIDER, "github-models")

    clients = langchain_client.build_chat_clients(model1="gpt-4o-mini", model2="gpt-4o")

    assert [client.provider for client in clients] == [
        langchain_client.PROVIDER_GITHUB,
        langchain_client.PROVIDER_GITHUB,
    ]
    assert [client.model for client in clients] == ["gpt-4o-mini", "gpt-4o"]
    assert all(isinstance(client.client, FakeChatOpenAI) for client in clients)


def test_build_chat_clients_env_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Model override env var should set both models when not provided."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.setenv(langchain_client.ENV_MODEL, "gpt-4o-mini")
    monkeypatch.delenv(langchain_client.ENV_PROVIDER, raising=False)

    clients = langchain_client.build_chat_clients()

    assert [client.model for client in clients] == ["gpt-4o-mini", "gpt-4o-mini"]
    assert all(isinstance(client.client, FakeChatOpenAI) for client in clients)


def test_build_chat_clients_env_model_with_provider_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Model env override should apply when provider is explicitly set."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.setenv(langchain_client.ENV_PROVIDER, "openai")
    monkeypatch.setenv(langchain_client.ENV_MODEL, "gpt-4o-mini")

    clients = langchain_client.build_chat_clients()

    assert [client.provider for client in clients] == [langchain_client.PROVIDER_OPENAI]
    assert [client.model for client in clients] == ["gpt-4o-mini"]
    assert all(isinstance(client.client, FakeChatOpenAI) for client in clients)


def test_build_chat_clients_github_models_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """GitHub Models path should be used when only GitHub token is set."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv(langchain_client.ENV_PROVIDER, raising=False)

    clients = langchain_client.build_chat_clients()

    assert [client.provider for client in clients] == [langchain_client.PROVIDER_GITHUB]
    assert isinstance(clients[0].client, FakeChatOpenAI)
    assert clients[0].client.kwargs["base_url"] == langchain_client.GITHUB_MODELS_BASE_URL


def test_build_chat_clients_openai_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenAI fallback should be used when GitHub token is missing."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.delenv(langchain_client.ENV_PROVIDER, raising=False)

    clients = langchain_client.build_chat_clients()

    assert [client.provider for client in clients] == [langchain_client.PROVIDER_OPENAI]
    assert isinstance(clients[0].client, FakeChatOpenAI)
    assert "base_url" not in clients[0].client.kwargs


def test_build_chat_client_handles_initialization_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When client initialization fails, fallback to other provider."""
    fake_module = types.ModuleType("langchain_openai")

    call_count = {"github": 0, "openai": 0}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            if "base_url" in kwargs:
                call_count["github"] += 1
                raise RuntimeError("GitHub Models API error")
            call_count["openai"] += 1
            self.kwargs = kwargs

    fake_module.ChatOpenAI = FakeChatOpenAI
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.delenv(langchain_client.ENV_PROVIDER, raising=False)

    # Should fallback to OpenAI when GitHub Models fails
    resolved = langchain_client.build_chat_client()

    assert resolved is not None
    assert resolved.provider == langchain_client.PROVIDER_OPENAI
    assert isinstance(resolved.client, FakeChatOpenAI)
    assert resolved.client.kwargs["api_key"] == "oa-token"
    assert call_count["github"] == 1  # Tried GitHub first
    assert call_count["openai"] == 1  # Fell back to OpenAI


def test_build_chat_clients_handles_partial_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When one provider fails, others should still work."""
    fake_module = types.ModuleType("langchain_openai")

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            if "base_url" in kwargs:
                raise RuntimeError("GitHub Models API error")
            self.kwargs = kwargs

    fake_module.ChatOpenAI = FakeChatOpenAI
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.delenv(langchain_client.ENV_PROVIDER, raising=False)

    clients = langchain_client.build_chat_clients()

    # Should only return OpenAI client since GitHub failed
    assert len(clients) == 1
    assert clients[0].provider == langchain_client.PROVIDER_OPENAI
    assert isinstance(clients[0].client, FakeChatOpenAI)
