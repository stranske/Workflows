"""Tests for tools/embedding_provider.py."""

from __future__ import annotations

from tools import embedding_provider as ep


class StubProvider(ep.EmbeddingProvider):
    def __init__(
        self,
        *,
        name: str,
        cost_tier: int = 1,
        latency_tier: int = 1,
        priority: int = 0,
        creds: bool = True,
        available: bool = True,
    ) -> None:
        self.name = name
        self.cost_tier = cost_tier
        self.latency_tier = latency_tier
        self.priority = priority
        self._creds = creds
        self._available = available
        self.capabilities = {"embeddings"}

    @property
    def default_model(self) -> str:  # pragma: no cover - not used here
        return "stub-model"

    def credentials_configured(self) -> bool:
        return self._creds

    def is_available(self) -> bool:
        return self._available and self._creds

    def embed(self, texts, *, model=None):
        return ep.EmbeddingResponse(
            vectors=[[0.0] for _ in texts],
            metadata=ep.EmbeddingMetadata(
                provider=self.name,
                model=model or "stub-model",
                dimensions=1,
                is_fallback=False,
            ),
        )


def test_registry_selects_preferred_provider() -> None:
    registry = ep.EmbeddingProviderRegistry()
    registry.register(StubProvider(name="alpha", priority=1))
    registry.register(StubProvider(name="beta", priority=2))

    selection = registry.select(
        ep.EmbeddingSelectionCriteria(preferred_provider="beta", required_capabilities={"embeddings"})
    )

    assert selection is not None
    assert selection.provider.name == "beta"


def test_registry_respects_cost_preferences() -> None:
    registry = ep.EmbeddingProviderRegistry()
    registry.register(StubProvider(name="cheap", cost_tier=0, priority=1))
    registry.register(StubProvider(name="expensive", cost_tier=2, priority=10))

    selection = registry.select(
        ep.EmbeddingSelectionCriteria(prefer_low_cost=True, required_capabilities={"embeddings"})
    )

    assert selection is not None
    assert selection.provider.name == "cheap"


def test_default_registry_falls_back_without_credentials(monkeypatch) -> None:
    monkeypatch.delenv(ep.ENV_OPENAI_API_KEY, raising=False)
    monkeypatch.delenv(ep.ENV_GITHUB_TOKEN, raising=False)
    monkeypatch.delenv(ep.ENV_ANTHROPIC_API_KEY, raising=False)
    monkeypatch.delenv(ep.ENV_ANTHROPIC_EMBEDDINGS_ENABLED, raising=False)

    registry = ep.default_embedding_registry()
    selection = registry.select(ep.EmbeddingSelectionCriteria(required_capabilities={"embeddings"}))

    assert selection is not None
    assert selection.provider.name == "fallback"
