#!/usr/bin/env python3
"""
Shared embedding utilities for semantic matching.

Use GitHub Models (preferred) or OpenAI embeddings when credentials are available.
"""

from __future__ import annotations

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

    if openai_token:
        return EmbeddingClientInfo(
            client=OpenAIEmbeddings(
                model=embedding_model,
                api_key=openai_token,
            ),
            provider="openai",
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
