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

Anthropic embeddings are gated by `ANTHROPIC_EMBEDDINGS_ENABLED` (true/1/on/yes)
plus `CLAUDE_API_STRANSKE`.
"""

from __future__ import annotations

import hashlib
import importlib.util
import math
import os
import re
import sys
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field

from tools.llm_provider import GITHUB_MODELS_BASE_URL


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ValueError:
        return name in sys.modules and sys.modules[name] is not None


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

    def resolve_model(self, model: str | None) -> str:
        """Resolve the model name for this provider."""
        return model or self.default_model

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
        model = selected.resolve_model(criteria.model)
        return EmbeddingProviderSelection(provider=selected, model=model)

    def ranked_candidates(self, criteria: EmbeddingSelectionCriteria) -> list[EmbeddingProvider]:
        """Return eligible providers sorted by deterministic ranking rules."""
        candidates = self._eligible_providers(criteria)
        candidates.sort(key=lambda provider: self._sort_key(provider, criteria))
        return candidates


ENV_OPENAI_API_KEY = "OPENAI_API_KEY"
ENV_GITHUB_TOKEN = "GITHUB_TOKEN"
ENV_ANTHROPIC_API_KEY = "CLAUDE_API_STRANSKE"
ENV_ANTHROPIC_EMBEDDINGS_ENABLED = "ANTHROPIC_EMBEDDINGS_ENABLED"

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_GITHUB_EMBEDDING_MODEL = DEFAULT_EMBEDDING_MODEL
DEFAULT_ANTHROPIC_EMBEDDING_MODEL = "claude-embedding-1"
FALLBACK_DIMENSIONS = 256

TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


class HashedEmbeddingClient:
    """Simple hashing-based embedding client for offline fallback."""

    def __init__(self, *, dimensions: int = FALLBACK_DIMENSIONS) -> None:
        self.dimensions = dimensions

    def embed_documents(self, texts: Iterable[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = TOKEN_RE.findall(text.lower()) if text else []
        if not tokens:
            return vector
        for token in tokens:
            idx = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % self.dimensions
            vector[idx] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm > 0.0:
            vector = [value / norm for value in vector]
        return vector


class OpenAIEmbeddingProvider(EmbeddingProvider):
    name = "openai"
    cost_tier = 2
    latency_tier = 2
    priority = 30
    capabilities = {"embeddings"}

    @property
    def default_model(self) -> str:
        return DEFAULT_EMBEDDING_MODEL

    def credentials_configured(self) -> bool:
        return bool(os.environ.get(ENV_OPENAI_API_KEY))

    def is_available(self) -> bool:
        if not self.credentials_configured():
            return False
        return _module_available("langchain_openai")

    def supports_model(self, model: str | None) -> bool:
        return bool(model)

    def build_client(self, *, model: str | None = None) -> object | None:
        try:
            from langchain_openai import OpenAIEmbeddings
        except ImportError:
            return None
        return OpenAIEmbeddings(
            model=model or self.default_model,
            api_key=os.environ.get(ENV_OPENAI_API_KEY),
        )

    def embed(self, texts: Iterable[str], *, model: str | None = None) -> EmbeddingResponse:
        client = self.build_client(model=model)
        if client is None:
            raise RuntimeError("OpenAI embeddings client unavailable")
        vectors = client.embed_documents(list(texts))
        return EmbeddingResponse(
            vectors=vectors,
            metadata=EmbeddingMetadata(
                provider=self.name,
                model=model or self.default_model,
                dimensions=len(vectors[0]) if vectors else None,
                is_fallback=False,
            ),
        )


class GitHubEmbeddingProvider(EmbeddingProvider):
    name = "github-models"
    cost_tier = 1
    latency_tier = 2
    priority = 20
    capabilities = {"embeddings"}

    @property
    def default_model(self) -> str:
        return DEFAULT_GITHUB_EMBEDDING_MODEL

    def credentials_configured(self) -> bool:
        return bool(os.environ.get(ENV_GITHUB_TOKEN))

    def is_available(self) -> bool:
        if not self.credentials_configured():
            return False
        return _module_available("langchain_openai")

    def supports_model(self, model: str | None) -> bool:
        return bool(model)

    def build_client(self, *, model: str | None = None) -> object | None:
        try:
            from langchain_openai import OpenAIEmbeddings
        except ImportError:
            return None
        return OpenAIEmbeddings(
            model=model or self.default_model,
            base_url=GITHUB_MODELS_BASE_URL,
            api_key=os.environ.get(ENV_GITHUB_TOKEN),
        )

    def embed(self, texts: Iterable[str], *, model: str | None = None) -> EmbeddingResponse:
        client = self.build_client(model=model)
        if client is None:
            raise RuntimeError("GitHub Models embeddings client unavailable")
        vectors = client.embed_documents(list(texts))
        return EmbeddingResponse(
            vectors=vectors,
            metadata=EmbeddingMetadata(
                provider=self.name,
                model=model or self.default_model,
                dimensions=len(vectors[0]) if vectors else None,
                is_fallback=False,
            ),
        )


class AnthropicEmbeddingProvider(EmbeddingProvider):
    name = "anthropic"
    cost_tier = 3
    latency_tier = 3
    priority = 10
    capabilities = {"embeddings"}

    @property
    def default_model(self) -> str:
        return DEFAULT_ANTHROPIC_EMBEDDING_MODEL

    def credentials_configured(self) -> bool:
        enabled = os.environ.get(ENV_ANTHROPIC_EMBEDDINGS_ENABLED)
        return bool(enabled and enabled.lower() in {"1", "true", "yes", "on"}) and bool(
            os.environ.get(ENV_ANTHROPIC_API_KEY)
        )

    def is_available(self) -> bool:
        if not self.credentials_configured():
            return False
        if _module_available("langchain_anthropic"):
            return True
        return _module_available("langchain_community")

    def supports_model(self, model: str | None) -> bool:
        return bool(model)

    def _resolve_embeddings_class(self):
        try:
            from langchain_anthropic import AnthropicEmbeddings
        except ImportError:
            try:
                from langchain_community.embeddings import AnthropicEmbeddings
            except ImportError:
                return None
        return AnthropicEmbeddings

    def build_client(self, *, model: str | None = None) -> object | None:
        embeddings_class = self._resolve_embeddings_class()
        if embeddings_class is None:
            return None
        return embeddings_class(
            model=model or self.default_model,
            anthropic_api_key=os.environ.get(ENV_ANTHROPIC_API_KEY),
        )

    def embed(self, texts: Iterable[str], *, model: str | None = None) -> EmbeddingResponse:
        client = self.build_client(model=model)
        if client is None:
            raise RuntimeError("Anthropic embeddings client unavailable")
        vectors = client.embed_documents(list(texts))
        return EmbeddingResponse(
            vectors=vectors,
            metadata=EmbeddingMetadata(
                provider=self.name,
                model=model or self.default_model,
                dimensions=len(vectors[0]) if vectors else None,
                is_fallback=False,
            ),
        )


class FallbackEmbeddingProvider(EmbeddingProvider):
    name = "fallback"
    cost_tier = 0
    latency_tier = 0
    priority = 1
    capabilities = {"embeddings", "fallback"}

    @property
    def default_model(self) -> str:
        return "hashing"

    def credentials_configured(self) -> bool:
        return True

    def is_available(self) -> bool:
        return True

    def build_client(self, *, model: str | None = None) -> object | None:
        return HashedEmbeddingClient()

    def resolve_model(self, model: str | None) -> str:
        return self.default_model

    def embed(self, texts: Iterable[str], *, model: str | None = None) -> EmbeddingResponse:
        client = self.build_client(model=model)
        if client is None:
            raise RuntimeError("Fallback embeddings client unavailable")
        vectors = client.embed_documents(list(texts))
        return EmbeddingResponse(
            vectors=vectors,
            metadata=EmbeddingMetadata(
                provider=self.name,
                model=self.default_model,
                dimensions=FALLBACK_DIMENSIONS,
                is_fallback=True,
            ),
        )


_DEFAULT_REGISTRY: EmbeddingProviderRegistry | None = None


def default_embedding_registry() -> EmbeddingProviderRegistry:
    """Return a registry with the standard embedding providers registered."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        registry = EmbeddingProviderRegistry()
        registry.register(OpenAIEmbeddingProvider())
        registry.register(GitHubEmbeddingProvider())
        registry.register(AnthropicEmbeddingProvider())
        registry.register(FallbackEmbeddingProvider())
        _DEFAULT_REGISTRY = registry
    return _DEFAULT_REGISTRY
