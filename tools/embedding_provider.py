"""
Embedding provider abstraction and deterministic registry selection.

Providers are responsible for:
- Checking their own availability, including dependency imports and credentials.
- Returning embeddings with provider/model metadata via EmbeddingResponse.

Expected configuration sources:
- Environment variables (e.g., OPENAI_API_KEY, GITHUB_TOKEN, ANTHROPIC_API_KEY)
- Optional config files loaded by callers (not enforced here).

Selection semantics:
- Only providers that report configured credentials and required capabilities are eligible.
- If a preferred provider name is supplied, it is selected when eligible.
- Otherwise, selection is deterministic and respects cost/latency preferences.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EmbeddingMetadata:
    """Metadata returned with embedding vectors.

    Contract:
    - provider: stable provider identifier (e.g., "openai", "anthropic", "fallback")
    - model: resolved model name used for embeddings
    - dimensions: embedding dimensionality when known, else None
    - is_fallback: True when a non-LLM fallback provider was used
    """

    provider: str
    model: str
    dimensions: int | None
    is_fallback: bool = False
    provider_info: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EmbeddingResponse:
    """Embedding vectors with metadata."""

    vectors: list[list[float]]
    metadata: EmbeddingMetadata


@dataclass(frozen=True)
class EmbeddingSelectionCriteria:
    """Criteria for selecting an embedding provider."""

    model: str | None = None
    required_capabilities: set[str] = field(default_factory=set)
    preferred_provider: str | None = None
    provider_allowlist: set[str] | None = None
    provider_denylist: set[str] | None = None
    prefer_low_cost: bool = False
    prefer_low_latency: bool = False


@dataclass(frozen=True)
class EmbeddingProviderSelection:
    """Resolved provider and model selection."""

    provider: EmbeddingProvider
    model: str


class EmbeddingProvider(ABC):
    """Abstract embedding provider interface."""

    name: str = ""
    cost_tier: int = 1
    latency_tier: int = 1
    priority: int = 0
    capabilities: set[str] = set()

    @property
    def default_model(self) -> str:
        """Return the provider's default embedding model name."""
        return ""

    def supports_model(self, model: str | None) -> bool:
        """Return True if the provider can serve the requested model."""
        return True

    def supports_capabilities(self, required: set[str]) -> bool:
        """Return True if the provider supports all required capabilities."""
        return required.issubset(self.capabilities)

    def credentials_configured(self) -> bool:
        """Return True if required credentials are configured via env/config."""
        return True

    def is_available(self) -> bool:
        """Return True if provider is usable (credentials + dependencies)."""
        return self.credentials_configured()

    @abstractmethod
    def embed(self, texts: Iterable[str], *, model: str | None = None) -> EmbeddingResponse:
        """Generate embeddings for the provided texts."""
        raise NotImplementedError


class EmbeddingProviderRegistry:
    """Registry for embedding providers with deterministic selection."""

    def __init__(self) -> None:
        self._providers: list[EmbeddingProvider] = []

    def register(self, provider: EmbeddingProvider) -> None:
        """Register a provider instance."""
        self._providers.append(provider)

    def list(self) -> list[EmbeddingProvider]:
        """Return a copy of registered providers."""
        return list(self._providers)

    def _eligible_providers(self, criteria: EmbeddingSelectionCriteria) -> list[EmbeddingProvider]:
        candidates: list[EmbeddingProvider] = []
        for provider in self._providers:
            if criteria.provider_allowlist and provider.name not in criteria.provider_allowlist:
                continue
            if criteria.provider_denylist and provider.name in criteria.provider_denylist:
                continue
            if not provider.credentials_configured():
                continue
            if not provider.supports_capabilities(criteria.required_capabilities):
                continue
            if criteria.model and not provider.supports_model(criteria.model):
                continue
            if not provider.is_available():
                continue
            candidates.append(provider)
        return candidates

    def _sort_key(self, provider: EmbeddingProvider, criteria: EmbeddingSelectionCriteria) -> tuple:
        preferred_rank = 0 if criteria.preferred_provider == provider.name else 1
        cost_rank = provider.cost_tier if criteria.prefer_low_cost else 0
        latency_rank = provider.latency_tier if criteria.prefer_low_latency else 0
        priority_rank = -int(provider.priority)
        return (
            preferred_rank,
            cost_rank,
            latency_rank,
            priority_rank,
            provider.name,
        )

    def select(self, criteria: EmbeddingSelectionCriteria) -> EmbeddingProviderSelection | None:
        """Select a provider deterministically based on the supplied criteria.

        Precedence:
        1. Eligibility (credentials/configured, capabilities, availability)
        2. Preferred provider name when specified
        3. Cost tier when prefer_low_cost is True
        4. Latency tier when prefer_low_latency is True
        5. Provider priority (higher is better)
        6. Provider name (deterministic tie-breaker)
        """

        candidates = self._eligible_providers(criteria)
        if not candidates:
            return None
        candidates.sort(key=lambda provider: self._sort_key(provider, criteria))
        selected = candidates[0]
        model = criteria.model or selected.default_model
        return EmbeddingProviderSelection(provider=selected, model=model)
