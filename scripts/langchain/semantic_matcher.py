#!/usr/bin/env python3
"""
Shared embedding utilities for semantic matching.

Selects embedding providers via the registry and uses a deterministic fallback
when external credentials are not configured.
"""

from __future__ import annotations

import math
import os
from collections.abc import Iterable
from dataclasses import dataclass

from tools.embedding_provider import (
    EmbeddingProvider,
    EmbeddingProviderRegistry,
    EmbeddingProviderSelection,
    EmbeddingSelectionCriteria,
    bootstrap_registry,
)

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


@dataclass
class EmbeddingClientInfo:
    client: object
    provider: str
    model: str
    is_fallback: bool


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    provider: str
    model: str
    is_fallback: bool
    dimensions: int | None


class EmbeddingAdapter:
    """Adapter exposing a LangChain embeddings interface for providers."""

    def __init__(self, provider: EmbeddingProvider, model: str) -> None:
        self._provider = provider
        self._model = model

    @property
    def provider(self) -> EmbeddingProvider:
        return self._provider

    @property
    def model(self) -> str:
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._provider.embed(texts, model=self._model).vectors

    def embed_query(self, text: str) -> list[float]:
        response = self._provider.embed([text], model=self._model)
        return response.vectors[0] if response.vectors else []

    def __call__(self, text: str) -> list[float]:
        return self.embed_query(text)


def _parse_provider_list(value: str | None) -> set[str] | None:
    if not value:
        return None
    items = {item.strip() for item in value.split(",") if item.strip()}
    return items or None


def _parse_bool(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _criteria_from_env(model: str | None) -> EmbeddingSelectionCriteria:
    resolved_model = model or os.environ.get("EMBEDDING_MODEL") or None
    return EmbeddingSelectionCriteria(
        model=resolved_model,
        preferred_provider=os.environ.get("EMBEDDING_PROVIDER_PREFERRED") or None,
        provider_allowlist=_parse_provider_list(os.environ.get("EMBEDDING_PROVIDER_ALLOWLIST")),
        provider_denylist=_parse_provider_list(os.environ.get("EMBEDDING_PROVIDER_DENYLIST")),
        prefer_low_cost=_parse_bool(os.environ.get("EMBEDDING_PREFER_LOW_COST")),
        prefer_low_latency=_parse_bool(os.environ.get("EMBEDDING_PREFER_LOW_LATENCY")),
    )


def _select_provider(
    registry: EmbeddingProviderRegistry, criteria: EmbeddingSelectionCriteria
) -> EmbeddingProviderSelection | None:
    return registry.select(criteria)


def get_embedding_client(model: str | None = None) -> EmbeddingClientInfo | None:
    registry = bootstrap_registry()
    criteria = _criteria_from_env(model or None)
    selection = _select_provider(registry, criteria)
    if selection is None:
        return None
    adapter = EmbeddingAdapter(selection.provider, selection.model)
    return EmbeddingClientInfo(
        client=adapter,
        provider=selection.provider.provider_id,
        model=selection.model,
        is_fallback=selection.provider.is_fallback(),
    )


def generate_embeddings(
    texts: Iterable[str],
    *,
    client_info: EmbeddingClientInfo | None = None,
    model: str | None = None,
) -> EmbeddingResult | None:
    items = [text.strip() for text in texts if text and text.strip()]
    if not items:
        return EmbeddingResult(
            vectors=[],
            provider="none",
            model=model or DEFAULT_EMBEDDING_MODEL,
            is_fallback=False,
            dimensions=None,
        )

    resolved = client_info or get_embedding_client(model=model)
    if resolved is None:
        return None

    vectors = resolved.client.embed_documents(items)
    dimensions = len(vectors[0]) if vectors else None
    return EmbeddingResult(
        vectors=vectors,
        provider=resolved.provider,
        model=resolved.model,
        is_fallback=resolved.is_fallback,
        dimensions=dimensions,
    )


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for l_val, r_val in zip(left, right, strict=False):
        dot += float(l_val) * float(r_val)
        left_norm += float(l_val) * float(l_val)
        right_norm += float(r_val) * float(r_val)
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return dot / (math.sqrt(left_norm) * math.sqrt(right_norm))


def best_cosine_matches(
    query: list[float],
    candidates: list[list[float]],
    *,
    top_k: int = 5,
) -> list[tuple[int, float]]:
    scored: list[tuple[int, float]] = []
    for idx, vector in enumerate(candidates):
        scored.append((idx, cosine_similarity(query, vector)))
    scored.sort(key=lambda item: item[1], reverse=True)
    if top_k <= 0:
        return []
    return scored[:top_k]
