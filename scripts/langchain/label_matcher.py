#!/usr/bin/env python3
"""
Semantic label matching helpers for issue intake.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from scripts.langchain import semantic_matcher


@dataclass(frozen=True)
class LabelRecord:
    name: str
    description: str | None = None


@dataclass
class LabelVectorStore:
    store: object
    provider: str
    model: str
    labels: list[LabelRecord]


@dataclass(frozen=True)
class LabelMatch:
    label: LabelRecord
    score: float
    raw_score: float
    score_type: str


DEFAULT_LABEL_SIMILARITY_THRESHOLD = 0.8
DEFAULT_LABEL_SIMILARITY_K = 5
SHORT_LABEL_LENGTH = 4


def _normalize_label(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _coerce_label(item: Any) -> LabelRecord | None:
    if isinstance(item, LabelRecord):
        return item
    if isinstance(item, Mapping):
        name = str(item.get("name") or item.get("label") or "").strip()
        if not name:
            return None
        description = item.get("description")
        return LabelRecord(
            name=name,
            description=str(description) if description is not None else None,
        )
    name = str(getattr(item, "name", "") or "").strip()
    if not name:
        return None
    description = getattr(item, "description", None)
    return LabelRecord(
        name=name,
        description=str(description) if description is not None else None,
    )


def _label_text(label: LabelRecord) -> str:
    description = (label.description or "").strip()
    if description:
        return f"{label.name}\n{description}"
    return label.name


def build_label_vector_store(
    labels: Iterable[Any],
    *,
    client_info: semantic_matcher.EmbeddingClientInfo | None = None,
    model: str | None = None,
) -> LabelVectorStore | None:
    label_records: list[LabelRecord] = []
    for item in labels:
        record = _coerce_label(item)
        if record is not None:
            label_records.append(record)

    if not label_records:
        return None

    resolved = client_info or semantic_matcher.get_embedding_client(model=model)
    if resolved is None:
        return None

    try:
        from langchain_community.vectorstores import FAISS
    except ImportError:
        return None

    texts = [_label_text(label) for label in label_records]
    metadatas = [{"name": label.name, "description": label.description} for label in label_records]
    store = FAISS.from_texts(texts, resolved.client, metadatas=metadatas)
    return LabelVectorStore(
        store=store,
        provider=resolved.provider,
        model=resolved.model,
        labels=label_records,
    )


def _resolve_threshold(explicit: float | None) -> float:
    if explicit is not None:
        return explicit
    env_value = os.environ.get("LABEL_MATCH_THRESHOLD")
    if env_value:
        try:
            return float(env_value)
        except ValueError:
            return DEFAULT_LABEL_SIMILARITY_THRESHOLD
    return DEFAULT_LABEL_SIMILARITY_THRESHOLD


def _similarity_from_score(score: float, score_type: str) -> float:
    if score_type == "distance":
        if score < 0:
            return 0.0
        return 1.0 / (1.0 + score)
    if score < 0:
        return 0.0
    if score > 1:
        return 1.0
    return score


def _label_from_metadata(metadata: Mapping[str, Any], fallback_name: str | None) -> LabelRecord:
    name = str(metadata.get("name") or fallback_name or "").strip()
    description = metadata.get("description")
    return LabelRecord(
        name=name or "unlabeled",
        description=str(description) if description is not None else None,
    )


def _exact_short_label_match(label_store: LabelVectorStore, query: str) -> LabelMatch | None:
    normalized = _normalize_label(query)
    if not normalized or len(normalized) > SHORT_LABEL_LENGTH:
        return None
    for label in label_store.labels:
        if _normalize_label(label.name) == normalized:
            return LabelMatch(label=label, score=1.0, raw_score=1.0, score_type="exact")
    return None


def find_similar_labels(
    label_store: LabelVectorStore,
    query: str,
    *,
    threshold: float | None = None,
    k: int | None = None,
) -> list[LabelMatch]:
    if not query or not query.strip():
        return []

    store = label_store.store
    if hasattr(store, "similarity_search_with_relevance_scores"):
        search_fn = store.similarity_search_with_relevance_scores
        score_type = "relevance"
    elif hasattr(store, "similarity_search_with_score"):
        search_fn = store.similarity_search_with_score
        score_type = "distance"
    else:
        return []

    limit = k or DEFAULT_LABEL_SIMILARITY_K
    try:
        results = search_fn(query, k=limit)
    except TypeError:
        results = search_fn(query, limit)

    min_score = _resolve_threshold(threshold)
    matches: list[LabelMatch] = []
    for doc, raw_score in results:
        metadata = getattr(doc, "metadata", {}) or {}
        fallback_name = getattr(doc, "page_content", None)
        label = _label_from_metadata(metadata, fallback_name)
        similarity = _similarity_from_score(float(raw_score), score_type)
        if similarity >= min_score:
            matches.append(
                LabelMatch(
                    label=label,
                    score=similarity,
                    raw_score=float(raw_score),
                    score_type=score_type,
                )
            )

    matches.sort(key=lambda match: match.score, reverse=True)
    return matches


def resolve_label_match(
    label_store: LabelVectorStore,
    query: str,
    *,
    threshold: float | None = None,
    k: int | None = None,
) -> LabelMatch | None:
    exact = _exact_short_label_match(label_store, query)
    if exact is not None:
        return exact
    matches = find_similar_labels(label_store, query, threshold=threshold, k=k)
    if matches:
        return matches[0]
    return None
