import hashlib
import sys
import types

from tools import embedding_provider


def _install_stub_langchain(monkeypatch):
    monkeypatch.setitem(sys.modules, "langchain_openai", types.SimpleNamespace())


def test_registry_selects_openai_with_credentials(monkeypatch):
    _install_stub_langchain(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "token")

    registry = embedding_provider.bootstrap_registry()
    selection = registry.select(embedding_provider.EmbeddingSelectionCriteria())

    assert selection is not None
    assert selection.provider.provider_id == "openai"


def test_registry_applies_allowlist_and_denylist(monkeypatch):
    _install_stub_langchain(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "token")

    registry = embedding_provider.bootstrap_registry()
    allowlist = embedding_provider.EmbeddingSelectionCriteria(provider_allowlist={"fallback"})
    denylist = embedding_provider.EmbeddingSelectionCriteria(provider_denylist={"openai"})

    selection_allow = registry.select(allowlist)
    selection_deny = registry.select(denylist)

    assert selection_allow is not None
    assert selection_allow.provider.provider_id == "fallback"
    assert selection_deny is not None
    assert selection_deny.provider.provider_id == "fallback"


def test_registry_selects_fallback_without_credentials(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "langchain_openai", None)

    registry = embedding_provider.bootstrap_registry()
    selection = registry.select(embedding_provider.EmbeddingSelectionCriteria())

    assert selection is not None
    assert selection.provider.provider_id == "fallback"
    assert selection.provider.is_fallback() is True


def test_provider_capabilities_are_immutable_and_fallback_hash_uses_sha256():
    assert embedding_provider.EmbeddingProvider.capabilities == frozenset()
    assert embedding_provider.OpenAIEmbeddingProvider.capabilities == frozenset({"embeddings"})
    assert embedding_provider.LocalFallbackEmbeddingProvider.capabilities == frozenset(
        {"embeddings", "local"}
    )

    digest = hashlib.sha256(b"example").digest()
    expected = int.from_bytes(digest[:8], "little")
    assert embedding_provider._hash_token("example") == expected


def test_registry_selection_is_deterministic(monkeypatch):
    _install_stub_langchain(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "token")

    registry = embedding_provider.bootstrap_registry()
    criteria = embedding_provider.EmbeddingSelectionCriteria()

    first = registry.select(criteria)
    second = registry.select(criteria)

    assert first is not None
    assert second is not None
    assert first.provider.provider_id == second.provider.provider_id
    assert first.model == second.model
