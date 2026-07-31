"""Tests for tools/langchain_client.py."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest
from tools import langchain_client, llm_registry


def _reviewed_model(provider: str) -> str:
    """Return the registry's reviewed selection for ``provider``.

    Tests assert the resolver serves the *reviewed selection*, not a hardcoded
    model id. Pinning literals here made every selection change — including an
    auto-prepared maint-86 promotion PR — fail CI for no real defect.
    """
    model = llm_registry.select_model_for_profile(provider=provider)
    assert model, f"no reviewed selection for {provider}; registry/policy is misconfigured"
    return model


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
    assert resolved.model == _reviewed_model(langchain_client.PROVIDER_OPENAI)


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
    assert resolved.model == _reviewed_model(langchain_client.PROVIDER_ANTHROPIC)


def test_build_chat_client_anthropic_without_openai_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Claude can run in Anthropic-only environments without langchain_openai."""
    monkeypatch.setitem(sys.modules, "langchain_openai", None)
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


def test_explicit_github_provider_uses_reviewed_model_when_model_is_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.delenv(langchain_client.ENV_MODEL, raising=False)
    monkeypatch.setattr(
        langchain_client,
        "configured_model_for_provider",
        lambda provider: "github-reviewed" if provider == "github-models" else "",
    )

    resolved = langchain_client.build_chat_client(provider="github-models")

    assert resolved is not None
    assert resolved.provider == langchain_client.PROVIDER_GITHUB
    assert resolved.model == "github-reviewed"
    assert isinstance(resolved.client, FakeChatOpenAI)
    # github-models GA namespaces bare ids with the openai/ publisher
    assert resolved.client.kwargs["model"] == "openai/github-reviewed"


def test_build_chat_client_env_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Model override env var should update the constructed model."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv(langchain_client.ENV_MODEL_REGISTRY_CONFIG, "/tmp/missing-registry.json")
    monkeypatch.setenv(langchain_client.ENV_MODEL, "gpt-4o-mini")
    monkeypatch.delenv(langchain_client.ENV_PROVIDER, raising=False)

    resolved = langchain_client.build_chat_client()

    assert resolved is not None
    assert resolved.model == "gpt-4o-mini"
    assert isinstance(resolved.client, FakeChatOpenAI)
    assert resolved.client.kwargs["model"] == "openai/gpt-4o-mini"


def test_build_chat_client_blocked_model_override_does_not_shift_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A blocked global override must not be retried against later providers."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    FakeChatAnthropic = _install_fake_langchain_anthropic(monkeypatch)
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "provider": "openai",
                        "model_id": "gpt-blocked",
                        "blocked": True,
                        "lifecycle": "current",
                    },
                    {
                        "provider": "openai",
                        "model_id": "gpt-safe",
                        "lifecycle": "current",
                    },
                    {
                        "provider": "anthropic",
                        "model_id": "claude-safe",
                        "lifecycle": "current",
                    },
                ],
                "selections": [
                    {
                        "profile": "verifier-balanced",
                        "provider": "openai",
                        "model_id": "gpt-safe",
                        "status": "approved",
                        "review_by": "2026-12-31",
                        "evidence_ids": ["test"],
                    },
                    {
                        "profile": "verifier-balanced",
                        "provider": "anthropic",
                        "model_id": "claude-safe",
                        "status": "approved",
                        "review_by": "2026-12-31",
                        "evidence_ids": ["test"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(langchain_client.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))
    monkeypatch.setenv("OPENAI_API_KEY", "oa-token")
    monkeypatch.setenv(langchain_client.ENV_ANTHROPIC_KEY, "claude-token")
    monkeypatch.setenv(langchain_client.ENV_MODEL, "gpt-blocked")
    monkeypatch.delenv(langchain_client.ENV_PROVIDER, raising=False)

    resolved = langchain_client.build_chat_client()

    assert resolved is not None
    assert resolved.provider == langchain_client.PROVIDER_OPENAI
    assert resolved.model == "gpt-safe"
    assert isinstance(resolved.client, FakeChatOpenAI)
    assert not isinstance(resolved.client, FakeChatAnthropic)


def test_build_chat_client_blocked_override_consumed_when_first_provider_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A blocked first-slot override must not shift to the next available provider."""
    _install_fake_langchain_openai(monkeypatch)
    FakeChatAnthropic = _install_fake_langchain_anthropic(monkeypatch)
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "provider": "openai",
                        "model_id": "gpt-blocked",
                        "blocked": True,
                        "lifecycle": "current",
                    },
                    {
                        "provider": "openai",
                        "model_id": "gpt-safe",
                        "lifecycle": "current",
                    },
                    {
                        "provider": "anthropic",
                        "model_id": "claude-safe",
                        "lifecycle": "current",
                    },
                ],
                "selections": [
                    {
                        "profile": "verifier-balanced",
                        "provider": "openai",
                        "model_id": "gpt-safe",
                        "status": "approved",
                        "review_by": "2026-12-31",
                        "evidence_ids": ["test"],
                    },
                    {
                        "profile": "verifier-balanced",
                        "provider": "anthropic",
                        "model_id": "claude-safe",
                        "status": "approved",
                        "review_by": "2026-12-31",
                        "evidence_ids": ["test"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(langchain_client.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv(langchain_client.ENV_ANTHROPIC_KEY, "claude-token")
    monkeypatch.setenv(langchain_client.ENV_MODEL, "gpt-blocked")
    monkeypatch.delenv(langchain_client.ENV_PROVIDER, raising=False)

    resolved = langchain_client.build_chat_client()

    assert resolved is not None
    assert resolved.provider == langchain_client.PROVIDER_ANTHROPIC
    assert resolved.model == "claude-safe"
    assert isinstance(resolved.client, FakeChatAnthropic)
    assert resolved.client.kwargs["model"] == "claude-safe"


def test_load_model_registry_ignores_malformed_nested_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "provider": "openai",
                        "model_id": "gpt-safe",
                        "quality": None,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(langchain_client.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))

    entries = llm_registry.load_model_registry()

    assert len(entries) == 1
    assert entries[0].quality is None


def test_load_model_registry_rejects_non_list_models(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"models": None}), encoding="utf-8")
    monkeypatch.setenv(langchain_client.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))

    assert llm_registry.load_model_registry() == []


def test_load_model_registry_ignores_v1_quality_scores(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "provider": "anthropic",
                        "model_id": "claude-sonnet-4-6",
                        "quality": {"T1": True, "T2": 0.8},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(langchain_client.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))

    [entry] = llm_registry.load_model_registry()

    assert entry.quality is None


def test_load_slot_config_ignores_tier_slot_when_registry_invalid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    slot_path = tmp_path / "slots.json"
    slot_path.write_text(
        json.dumps({"slots": [{"name": "primary", "provider": "openai", "quality_tier": "T3"}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv(langchain_client.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))
    monkeypatch.setenv(langchain_client.ENV_SLOT_CONFIG, str(slot_path))

    slots = llm_registry.load_slot_config(github_default_model=langchain_client.DEFAULT_MODEL)

    assert slots == []


def test_load_slot_config_uses_provider_fallback_after_position_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        llm_registry,
        "default_slots",
        lambda *, github_default_model: [
            llm_registry.SlotDefinition(
                name="slot1",
                provider=langchain_client.PROVIDER_OPENAI,
                model="gpt-default",
            ),
            llm_registry.SlotDefinition(
                name="slot2",
                provider=langchain_client.PROVIDER_ANTHROPIC,
                model="claude-sonnet-4-6",
            ),
        ],
    )
    slot_path = tmp_path / "slots.json"
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(["invalid"]), encoding="utf-8")
    slot_path.write_text(
        json.dumps({"slots": [{"name": "primary-claude", "provider": "anthropic"}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv(langchain_client.ENV_SLOT_CONFIG, str(slot_path))
    monkeypatch.setenv(langchain_client.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))

    slots = llm_registry.load_slot_config(github_default_model="github-default")

    assert slots == [
        llm_registry.SlotDefinition(
            name="primary-claude",
            provider=langchain_client.PROVIDER_ANTHROPIC,
            model="claude-sonnet-4-6",
        )
    ]


def test_slot_env_override_reverts_to_original_when_override_blocked(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "provider": "openai",
                        "model_id": "gpt-blocked",
                        "blocked": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(langchain_client.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))
    monkeypatch.setenv(langchain_client.ENV_MODEL, "gpt-blocked")

    slots = llm_registry.apply_slot_env_overrides(
        [
            llm_registry.SlotDefinition(
                name="slot1",
                provider=langchain_client.PROVIDER_OPENAI,
                model="gpt-safe",
            ),
            llm_registry.SlotDefinition(
                name="slot2",
                provider=langchain_client.PROVIDER_ANTHROPIC,
                model="claude-safe",
            ),
        ]
    )

    assert slots == [
        llm_registry.SlotDefinition(
            name="slot1",
            provider=langchain_client.PROVIDER_OPENAI,
            model="gpt-safe",
        ),
        llm_registry.SlotDefinition(
            name="slot2",
            provider=langchain_client.PROVIDER_ANTHROPIC,
            model="claude-safe",
        ),
    ]


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

    clients = langchain_client.build_chat_clients(model1="gpt-4.1-mini", model2="gpt-4o")

    assert [client.provider for client in clients] == [
        langchain_client.PROVIDER_OPENAI,
        langchain_client.PROVIDER_OPENAI,
    ]
    assert [client.model for client in clients] == ["gpt-4.1-mini", "gpt-4o"]
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
    monkeypatch.setenv(langchain_client.ENV_MODEL, "gpt-4.1-mini")
    monkeypatch.delenv(langchain_client.ENV_PROVIDER, raising=False)

    clients = langchain_client.build_chat_clients()

    assert [client.model for client in clients] == [
        "gpt-4.1-mini",
        _reviewed_model(langchain_client.PROVIDER_GITHUB),
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
    monkeypatch.setenv(langchain_client.ENV_MODEL, "gpt-4.1-mini")

    clients = langchain_client.build_chat_clients()

    assert [client.provider for client in clients] == [langchain_client.PROVIDER_OPENAI]
    assert [client.model for client in clients] == ["gpt-4.1-mini"]
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


def test_build_chat_clients_anthropic_without_openai_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multi-client resolution should not make Anthropic depend on OpenAI imports."""
    monkeypatch.setitem(sys.modules, "langchain_openai", None)
    FakeChatAnthropic = _install_fake_langchain_anthropic(monkeypatch)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv(langchain_client.ENV_ANTHROPIC_KEY, "claude-token")
    monkeypatch.delenv(langchain_client.ENV_PROVIDER, raising=False)

    clients = langchain_client.build_chat_clients()

    assert len(clients) == 1
    assert clients[0].provider == langchain_client.PROVIDER_ANTHROPIC
    assert isinstance(clients[0].client, FakeChatAnthropic)


# --- Reasoning model temperature handling ---


@pytest.mark.parametrize(
    "model,expected",
    [
        ("o1", True),
        ("o10", True),
        ("o1-mini", True),
        ("o1-preview", True),
        ("o1-preview-2024-09-12", True),
        ("o3", True),
        ("o4", True),
        ("o3-2025-04-16", True),
        ("o3-mini", True),
        ("o3-pro", True),
        ("o4-mini", True),
        ("o4-mini-deep-research", True),
        ("o1-2025-01-01", True),
        ("O3-MINI", True),
        ("o3-mini-deep-research-v2", True),
        ("gpt-5.2", False),
        ("gpt-4o", False),
        ("gpt-4.1", False),
        ("claude-sonnet-4-5-20250929", False),
        ("mixtral-8x7b", False),
        ("o1x", False),
        ("o1_preview", False),
        ("o1-preview-", False),
        ("o1.2", False),
        ("o1--mini", False),
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


class _CaptureChatOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _CaptureChatAnthropic:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_github_model_id_namespaces_bare_ids():
    assert langchain_client._github_model_id("codex-mini-latest") == "openai/codex-mini-latest"
    assert langchain_client._github_model_id("gpt-5") == "openai/gpt-5"


def test_github_model_id_leaves_namespaced_ids_unchanged():
    assert langchain_client._github_model_id("openai/gpt-5") == "openai/gpt-5"
    assert (
        langchain_client._github_model_id("mistral-ai/mistral-large") == "mistral-ai/mistral-large"
    )


def test_build_github_client_sends_namespaced_model():
    client = langchain_client._build_github_client(
        _CaptureChatOpenAI, model="codex-mini-latest", token="t", timeout=30, max_retries=2
    )
    assert client.kwargs["model"] == "openai/codex-mini-latest"
    assert client.kwargs["base_url"] == langchain_client.GITHUB_MODELS_BASE_URL


def test_build_github_client_preserves_already_namespaced():
    client = langchain_client._build_github_client(
        _CaptureChatOpenAI, model="openai/gpt-5", token="t", timeout=30, max_retries=2
    )
    assert client.kwargs["model"] == "openai/gpt-5"


def _build_anthropic(model: str):
    return langchain_client._build_anthropic_client(
        _CaptureChatAnthropic, model=model, token="t", timeout=30, max_retries=2
    )


def test_anthropic_rejects_temperature_matches_newer_generation():
    # Confirmed-rejecting (maint-78 pilot 2026-07-24) + Claude 5 family.
    assert langchain_client._anthropic_rejects_temperature("claude-opus-4-8")
    assert langchain_client._anthropic_rejects_temperature("claude-sonnet-5")
    assert langchain_client._anthropic_rejects_temperature("claude-fable-5")
    assert langchain_client._anthropic_rejects_temperature("claude-opus-5")


def test_anthropic_incumbent_and_minor5_still_accept_temperature():
    # Incumbent opus-4-6 and minor-version -5 suffixes must NOT be treated as rejecting.
    assert not langchain_client._anthropic_rejects_temperature("claude-opus-4-6")
    assert not langchain_client._anthropic_rejects_temperature("claude-haiku-4-5-20251001")
    assert not langchain_client._anthropic_rejects_temperature("claude-sonnet-4-6")


def test_build_anthropic_omits_temperature_for_newer_models():
    # These previously 400'd on `temperature`; now the param must be omitted.
    for model in ("claude-opus-4-8", "claude-sonnet-5"):
        client = _build_anthropic(model)
        assert "temperature" not in client.kwargs, model
        assert client.kwargs["model"] == model


def test_build_anthropic_keeps_temperature_for_incumbent():
    client = _build_anthropic("claude-opus-4-6")
    assert client.kwargs["temperature"] == 0.1
