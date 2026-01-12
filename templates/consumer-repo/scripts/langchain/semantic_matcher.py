#!/usr/bin/env python3
"""
Shared embedding utilities for semantic matching.

Use GitHub Models (preferred) or OpenAI embeddings when credentials are available.
"""

from __future__ import annotations

import math
import os
from collections.abc import Iterable
from dataclasses import dataclass

from tools.llm_provider import GITHUB_MODELS_BASE_URL

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


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


def get_embedding_client(model: str | None = None) -> EmbeddingClientInfo | None:
    try:
        from langchain_openai import OpenAIEmbeddings
    except ImportError:
        return None

    github_token = os.environ.get("GITHUB_TOKEN")
    openai_token = os.environ.get("OPENAI_API_KEY")
    embedding_model = model or os.environ.get("EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL

    # Prefer OpenAI for embeddings - GitHub Models doesn't support the embeddings endpoint
    if openai_token:
        return EmbeddingClientInfo(
            client=OpenAIEmbeddings(
                model=embedding_model,
                api_key=openai_token,
            ),
            provider="openai",
            model=embedding_model,
        )

    # Fall back to GitHub Models (may not work for embeddings)
    if github_token:
        return EmbeddingClientInfo(
            client=OpenAIEmbeddings(
                model=embedding_model,
                base_url=GITHUB_MODELS_BASE_URL,
                api_key=github_token,
            ),
            provider="github-models",
            model=embedding_model,
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
