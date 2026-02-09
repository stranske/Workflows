#!/usr/bin/env python3
"""
Shared embedding utilities for semantic matching.

Uses the embedding provider registry for deterministic selection with safe fallbacks.
"""

from __future__ import annotations

import math
import os
from collections.abc import Iterable
from dataclasses import dataclass

from tools import embedding_provider

DEFAULT_EMBEDDING_MODEL = embedding_provider.DEFAULT_EMBEDDING_MODEL
EMBEDDING_PROVIDER_ENV = "EMBEDDING_PROVIDER"
EMBEDDING_MODEL_ENV = "EMBEDDING_MODEL"


@dataclass
class EmbeddingClientInfo:
    client: object
    provider: str
    model: str


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    provider: str
    model: str


def get_embedding_client(
    model: str | None = None,
    *,
    provider: str | None = None,
) -> EmbeddingClientInfo | None:
    requested_model = model or os.environ.get(EMBEDDING_MODEL_ENV) or DEFAULT_EMBEDDING_MODEL
    preferred_provider = provider or os.environ.get(EMBEDDING_PROVIDER_ENV)

    criteria = embedding_provider.EmbeddingSelectionCriteria(
        model=requested_model,
        preferred_provider=preferred_provider,
        required_capabilities={"embeddings"},
    )
    registry = embedding_provider.default_embedding_registry()
    for candidate in registry.ranked_candidates(criteria):
        client = None
        if hasattr(candidate, "build_client"):
            resolved_model = candidate.resolve_model(requested_model)
            client = candidate.build_client(model=resolved_model)
        if client is None:
            continue
        return EmbeddingClientInfo(
            client=client,
            provider=candidate.name,
            model=resolved_model,
        )
    return None


def generate_embeddings(
    texts: Iterable[str],
    *,
    client_info: EmbeddingClientInfo | None = None,
    model: str | None = None,
) -> EmbeddingResult | None:
    items = [text.strip() for text in texts if text and text.strip()]
    if not items:
        return EmbeddingResult(vectors=[], provider="none", model=model or DEFAULT_EMBEDDING_MODEL)

    resolved = client_info or get_embedding_client(model=model)
    if resolved is None:
        return None

    vectors = resolved.client.embed_documents(items)
    return EmbeddingResult(vectors=vectors, provider=resolved.provider, model=resolved.model)


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
