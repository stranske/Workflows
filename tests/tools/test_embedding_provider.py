"""Behavioral coverage for the highest-ranked unclaimed low-blast-radius provider surface.

``tools/embedding_provider.py`` ranks next after previously covered or control-plane targets: ten
fix commits, eleven total touches, and sixteen unexercised statements in the fresh Linux report.
The gaps below are provider-boundary decisions, not SDK implementation details: credential and
dependency availability, empty-batch behavior, finite fallback output, registry encapsulation,
and fail-closed eligibility filters.
"""

import hashlib
import sys
import types
from collections.abc import Iterable

import pytest
from tools import embedding_provider


class StubEmbeddings:
    last_instance = None

    def __init__(self, model, api_key=None):
        self.model = model
        self.api_key = api_key
        StubEmbeddings.last_instance = self

    def embed_documents(self, texts):
        return [[float(len(text))] for text in texts]


def _install_stub_langchain(monkeypatch):
    monkeypatch.setitem(sys.modules, "langchain_openai", types.SimpleNamespace())


def _install_stub_openai_embeddings(monkeypatch):
    module = types.SimpleNamespace(OpenAIEmbeddings=StubEmbeddings)
    monkeypatch.setitem(sys.modules, "langchain_openai", module)


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


def test_base_provider_supports_model_accepts_keyword_argument():
    provider = embedding_provider.LocalFallbackEmbeddingProvider()

    assert provider.supports_model(model="custom-embedding-model") is True


def test_openai_provider_passes_api_key(monkeypatch):
    _install_stub_openai_embeddings(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "token")

    provider = embedding_provider.OpenAIEmbeddingProvider()
    response = provider.embed(["alpha"])

    assert response.vectors == [[5.0]]
    assert response.metadata.provider == "openai"
    assert response.metadata.dimensions == 1
    assert StubEmbeddings.last_instance.api_key == "token"


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


def test_openai_availability_requires_credentials_and_dependency(monkeypatch):
    provider = embedding_provider.OpenAIEmbeddingProvider()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    _install_stub_langchain(monkeypatch)

    assert provider.is_available() is False

    monkeypatch.setenv("OPENAI_API_KEY", "token")
    monkeypatch.setitem(sys.modules, "langchain_openai", None)

    assert provider.is_available() is False


def test_openai_empty_batch_is_a_metadata_only_noop(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "langchain_openai", None)

    response = embedding_provider.OpenAIEmbeddingProvider().embed(
        ["", "  ", "\n\t"], model="requested-model"
    )

    assert response == embedding_provider.EmbeddingResponse(
        vectors=[],
        metadata=embedding_provider.EmbeddingMetadata(
            provider="openai",
            model="requested-model",
            dimensions=None,
            is_fallback=False,
        ),
    )


def test_openai_nonempty_batch_requires_credentials(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "langchain_openai", None)

    with pytest.raises(RuntimeError, match="without OPENAI_API_KEY configured"):
        embedding_provider.OpenAIEmbeddingProvider().embed(["alpha"])


def test_openai_nonempty_batch_reports_missing_optional_dependency(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "token")
    monkeypatch.setitem(sys.modules, "langchain_openai", None)

    with pytest.raises(
        RuntimeError,
        match="langchain_openai and its dependencies are required",
    ) as raised:
        embedding_provider.OpenAIEmbeddingProvider().embed(["alpha"])

    assert isinstance(raised.value.__cause__, ImportError)


def test_fallback_empty_batch_preserves_local_metadata():
    response = embedding_provider.LocalFallbackEmbeddingProvider().embed(
        ["", "  "], model="explicit-local-model"
    )

    assert response == embedding_provider.EmbeddingResponse(
        vectors=[],
        metadata=embedding_provider.EmbeddingMetadata(
            provider="fallback",
            model="explicit-local-model",
            dimensions=embedding_provider.FALLBACK_DIMENSIONS,
            is_fallback=True,
        ),
    )


def test_fallback_punctuation_only_text_produces_a_finite_zero_vector():
    response = embedding_provider.LocalFallbackEmbeddingProvider().embed(["!!!"])

    assert response.metadata.dimensions == embedding_provider.FALLBACK_DIMENSIONS
    assert response.vectors == [[0.0] * embedding_provider.FALLBACK_DIMENSIONS]


def test_registry_list_is_a_snapshot_not_mutable_registry_state():
    registry = embedding_provider.bootstrap_registry()

    snapshot = registry.list()
    snapshot.clear()

    registered = registry.list()
    assert len(registered) == 2
    assert {provider.provider_id for provider in registered} == {"openai", "fallback"}


class _ControlledProvider(embedding_provider.EmbeddingProvider):
    def __init__(
        self,
        name: str,
        *,
        capabilities: set[str],
        supports_requested_model: bool = True,
        available: bool = True,
        priority: int = 0,
    ) -> None:
        self.name = name
        self.capabilities = frozenset(capabilities)
        self._supports_requested_model = supports_requested_model
        self._available = available
        self.priority = priority

    def supports_model(self, model: str | None) -> bool:
        return self._supports_requested_model and model == "requested-model"

    def is_available(self) -> bool:
        return self._available

    def embed(
        self, texts: Iterable[str], *, model: str | None = None
    ) -> embedding_provider.EmbeddingResponse:
        raise AssertionError("selection tests do not invoke providers")


def test_registry_rejects_capability_model_and_runtime_mismatches():
    registry = embedding_provider.EmbeddingProviderRegistry()
    registry.register(_ControlledProvider("missing-capability", capabilities=set(), priority=103))
    registry.register(
        _ControlledProvider(
            "wrong-model",
            capabilities={"embeddings"},
            supports_requested_model=False,
            priority=102,
        )
    )
    registry.register(
        _ControlledProvider(
            "unavailable",
            capabilities={"embeddings"},
            available=False,
            priority=101,
        )
    )
    registry.register(_ControlledProvider("eligible", capabilities={"embeddings"}))

    selection = registry.select(
        embedding_provider.EmbeddingSelectionCriteria(
            model="requested-model",
            required_capabilities={"embeddings"},
        )
    )

    assert selection is not None
    assert selection.provider.provider_id == "eligible"
    assert selection.model == "requested-model"
