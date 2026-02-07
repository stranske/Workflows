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


def _install_fake_langchain_anthropic(monkeypatch: pytest.MonkeyPatch):
    fake_module = types.ModuleType("langchain_anthropic")

    class FakeChatAnthropic:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_module.ChatAnthropic = FakeChatAnthropic
    monkeypatch.setitem(sys.modules, "langchain_anthropic", fake_module)
    return FakeChatAnthropic


def test_build_chat_client_prefers_openai_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Slot 1 (OpenAI) should be preferred when both tokens are set."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.delenv(langchain_client.ENV_PROVIDER, raising=False)
    monkeypatch.delenv(langchain_client.ENV_MODEL, raising=False)

    resolved = langchain_client.build_chat_client()

    assert resolved is not None
    assert resolved.provider == langchain_client.PROVIDER_OPENAI
    assert isinstance(resolved.client, FakeChatOpenAI)
    assert resolved.client.kwargs["api_key"] == "oa-token"
    assert "base_url" not in resolved.client.kwargs


def test_build_chat_client_github_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """GitHub Models is used when OpenAI and Claude are unavailable."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv(langchain_client.ENV_ANTHROPIC_KEY, raising=False)
    monkeypatch.delenv(langchain_client.ENV_PROVIDER, raising=False)

    resolved = langchain_client.build_chat_client()

    assert resolved is not None
    assert resolved.provider == langchain_client.PROVIDER_GITHUB
    assert isinstance(resolved.client, FakeChatOpenAI)
    assert resolved.client.kwargs["api_key"] == "gh-token"
    assert resolved.client.kwargs["base_url"] == langchain_client.GITHUB_MODELS_BASE_URL


def test_build_chat_client_anthropic_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Claude is used when OpenAI is unavailable and Claude is configured."""
    _install_fake_langchain_openai(monkeypatch)
    FakeChatAnthropic = _install_fake_langchain_anthropic(monkeypatch)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv(langchain_client.ENV_ANTHROPIC_KEY, "claude-token")
    monkeypatch.delenv(langchain_client.ENV_PROVIDER, raising=False)

    resolved = langchain_client.build_chat_client()

    assert resolved is not None
    assert resolved.provider == langchain_client.PROVIDER_ANTHROPIC
    assert isinstance(resolved.client, FakeChatAnthropic)
    assert resolved.client.kwargs["anthropic_api_key"] == "claude-token"


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
) -> None:
    """Invalid provider overrides should fall back to auto-selection."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.setenv(langchain_client.ENV_PROVIDER, "not-a-provider")

    resolved = langchain_client.build_chat_client()

    assert resolved is not None
    assert resolved.provider == langchain_client.PROVIDER_OPENAI
    assert isinstance(resolved.client, FakeChatOpenAI)


def test_build_chat_clients_auto_selects_openai_then_claude(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auto selection returns OpenAI then Claude when configured."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    FakeChatAnthropic = _install_fake_langchain_anthropic(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.setenv(langchain_client.ENV_ANTHROPIC_KEY, "claude-token")
    monkeypatch.delenv(langchain_client.ENV_PROVIDER, raising=False)
    monkeypatch.delenv(langchain_client.ENV_MODEL, raising=False)

    clients = langchain_client.build_chat_clients()

    assert [client.provider for client in clients] == [
        langchain_client.PROVIDER_OPENAI,
        langchain_client.PROVIDER_ANTHROPIC,
    ]
    assert isinstance(clients[0].client, FakeChatOpenAI)
    assert isinstance(clients[1].client, FakeChatAnthropic)


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
    """Model override env var should set the primary model when not provided."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.setenv(langchain_client.ENV_MODEL, "gpt-4o-mini")
    monkeypatch.delenv(langchain_client.ENV_PROVIDER, raising=False)

    clients = langchain_client.build_chat_clients()

    assert [client.model for client in clients] == [
        "gpt-4o-mini",
        langchain_client.DEFAULT_MODEL,
    ]
    assert isinstance(clients[0].client, FakeChatOpenAI)


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
    fake_openai = types.ModuleType("langchain_openai")
    fake_anthropic = types.ModuleType("langchain_anthropic")

    call_count = {"openai": 0, "anthropic": 0}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            call_count["openai"] += 1
            raise RuntimeError("OpenAI API error")

    class FakeChatAnthropic:
        def __init__(self, **kwargs):
            call_count["anthropic"] += 1
            self.kwargs = kwargs

    fake_openai.ChatOpenAI = FakeChatOpenAI
    fake_anthropic.ChatAnthropic = FakeChatAnthropic
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_openai)
    monkeypatch.setitem(sys.modules, "langchain_anthropic", fake_anthropic)
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.setenv(langchain_client.ENV_ANTHROPIC_KEY, "claude-token")
    monkeypatch.delenv(langchain_client.ENV_PROVIDER, raising=False)

    resolved = langchain_client.build_chat_client()

    assert resolved is not None
    assert resolved.provider == langchain_client.PROVIDER_ANTHROPIC
    assert isinstance(resolved.client, FakeChatAnthropic)
    assert resolved.client.kwargs["anthropic_api_key"] == "claude-token"
    assert call_count["openai"] == 1
    assert call_count["anthropic"] == 1


def test_build_chat_clients_handles_partial_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When one provider fails, others should still work."""
    fake_openai = types.ModuleType("langchain_openai")
    fake_anthropic = types.ModuleType("langchain_anthropic")

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeChatAnthropic:
        def __init__(self, **kwargs):
            raise RuntimeError("Anthropic API error")

    fake_openai.ChatOpenAI = FakeChatOpenAI
    fake_anthropic.ChatAnthropic = FakeChatAnthropic
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_openai)
    monkeypatch.setitem(sys.modules, "langchain_anthropic", fake_anthropic)
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.setenv(langchain_client.ENV_ANTHROPIC_KEY, "claude-token")
    monkeypatch.delenv(langchain_client.ENV_PROVIDER, raising=False)

    clients = langchain_client.build_chat_clients()

    assert len(clients) == 1
    assert clients[0].provider == langchain_client.PROVIDER_OPENAI
    assert isinstance(clients[0].client, FakeChatOpenAI)


# --- Reasoning model temperature handling ---


@pytest.mark.parametrize(
    "model,expected",
    [
        ("o1", True),
        ("o1-mini", True),
        ("o1-preview", True),
        ("o1-preview-2024-09-12", True),
        ("o3", True),
        ("o3-2025-04-16", True),
        ("o3-mini", True),
        ("o3-pro", True),
        ("o4-mini", True),
        ("o4-mini-deep-research", True),
        ("gpt-5.2", False),
        ("gpt-4o", False),
        ("gpt-4.1", False),
        ("claude-sonnet-4-5-20250929", False),
        ("mixtral-8x7b", False),
        ("o", False),
        ("o-1", False),
        ("openai-o1", False),
        ("oasis-1", False),
    ],
)
def test_is_reasoning_model(model: str, expected: bool) -> None:
    assert langchain_client._is_reasoning_model(model) is expected


def test_build_openai_client_reasoning_model_no_temperature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reasoning models (o3-mini, etc.) must NOT receive temperature."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.delenv(langchain_client.ENV_ANTHROPIC_KEY, raising=False)
    monkeypatch.setenv(langchain_client.ENV_PROVIDER, "openai")
    monkeypatch.setenv(langchain_client.ENV_MODEL, "o3-mini")

    resolved = langchain_client.build_chat_client(model="o3-mini")

    assert resolved is not None
    assert isinstance(resolved.client, FakeChatOpenAI)
    assert "temperature" not in resolved.client.kwargs


def test_build_openai_client_normal_model_has_temperature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Normal models must receive temperature=0.1."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.delenv(langchain_client.ENV_ANTHROPIC_KEY, raising=False)
    monkeypatch.setenv(langchain_client.ENV_PROVIDER, "openai")
    monkeypatch.setenv(langchain_client.ENV_MODEL, "gpt-5.2")

    resolved = langchain_client.build_chat_client(model="gpt-5.2")

    assert resolved is not None
    assert isinstance(resolved.client, FakeChatOpenAI)
    assert resolved.client.kwargs["temperature"] == 0.1
