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

try:
    import semantic_matcher
except ModuleNotFoundError:
    from . import semantic_matcher


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
KEYWORD_BUG_SCORE = 0.91
KEYWORD_FEATURE_SCORE = 0.9
KEYWORD_DOCS_SCORE = 0.9
_IGNORED_LABEL_TOKENS = {"type", "kind"}
# Common words that appear in label descriptions but shouldn't trigger keyword matching
_COMMON_STOPWORDS = {
    "this",
    "that",
    "the",
    "a",
    "an",
    "is",
    "are",
    "or",
    "and",
    "for",
    "to",
    "of",
    "in",
    "on",
    "with",
    "be",
    "it",
    "not",
    "if",
    "by",
    "as",
    "at",
    "from",
    "has",
    "have",
    "can",
    "will",
    "would",
    "should",
    "may",
    "might",
    "must",
    "need",
    "issue",
    "issues",
    "pull",
    "request",
    "requests",
    "information",
    "further",
    "already",
    "exists",
    "changes",
    "additions",
    "improvements",
    "triggers",
    "analysis",
    "suggestions",
    "formatted",
    "template",
    "format",
    "optimize",
    "optimization",
    "new",
    "code",
    "clean",
    "only",
    "create",
    "follow",
    "up",
    "verification",
    "acceptance",
    "criteria",
    "checkbox",
    "evaluate",
    "evaluation",
    "compare",
    "comparison",
    "multiple",
    "models",
    "providers",
    "decompose",
    "break",
    "down",
    "large",
    "tasks",
    "smaller",
    "maintainable",
    "requires",
    "human",
    "intervention",
    "attention",
    "help",
    "wanted",
    "good",
    "first",
}
_BUG_KEYWORDS = {
    "bug",
    "bugs",
    "buggy",
    "crash",
    "crashes",
    "crashed",
    "error",
    "errors",
    "failure",
    "failures",
    "broken",
    "regression",
    "defect",
}
_FEATURE_KEYWORDS = {
    "feature",
    "features",
    "enhancement",
    "enhancements",
    "request",
    "requests",
    "improvement",
    "improvements",
    "support",
    "add",
    "enable",
}
_FEATURE_PHRASES = {
    "dark mode",
    "light mode",
}
_DOCS_KEYWORDS = {
    "doc",
    "docs",
    "documentation",
    "readme",
    "guide",
    "guides",
    "example",
    "examples",
    "tutorial",
    "tutorials",
}


def _normalize_label(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


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


def _ensure_label_iterable(labels: Iterable[Any]) -> Iterable[Any]:
    if labels is None:
        raise ValueError("labels must be an iterable of label records, not None.")
    if isinstance(labels, (str, bytes)):
        raise ValueError("labels must be an iterable of label records, not a string.")
    if not isinstance(labels, Iterable):
        raise ValueError("labels must be an iterable of label records.")
    return labels


def _ensure_label_store(label_store: LabelVectorStore) -> LabelVectorStore:
    if not isinstance(label_store, LabelVectorStore):
        raise ValueError("label_store must be a LabelVectorStore instance.")
    return label_store


def _ensure_query_text(query: Any) -> str:
    if query is None or not isinstance(query, str):
        raise ValueError("query must be a string.")
    return query


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
    for index, item in enumerate(_ensure_label_iterable(labels)):
        record = _coerce_label(item)
        if record is not None:
            label_records.append(record)
        else:
            if isinstance(item, Mapping):
                raise ValueError(f"Label entry at index {index} is missing a name.")
            if getattr(item, "name", None) is not None or getattr(item, "label", None) is not None:
                raise ValueError(f"Label entry at index {index} has an empty name.")
            raise ValueError(f"Unsupported label entry at index {index}: {type(item).__name__}.")

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


def _token_matches_keyword(token: str, keyword: str) -> bool:
    if token == keyword:
        return True
    # Only allow prefix matching for tokens >= 4 chars to avoid false positives
    # from short tokens like "d" matching "defect" or "a" matching "add"
    if len(token) >= 4 and token.startswith(keyword):
        return True
    # Check if keyword starts with token (both must be >= 4 chars)
    return len(token) >= 4 and len(keyword) >= 4 and keyword.startswith(token)


def _keyword_match_score(label: LabelRecord, query: str) -> float | None:
    tokens = _tokenize(query)
    if not tokens:
        return None

    query_lower = query.lower()
    # Only match on significant tokens, excluding common stopwords
    significant_tokens = tokens - _COMMON_STOPWORDS

    # Require label NAME to appear in query for high-confidence keyword match
    # (not just overlapping description tokens)
    label_name_tokens = _tokenize(label.name) - _IGNORED_LABEL_TOKENS
    if label_name_tokens and label_name_tokens.intersection(significant_tokens):
        return 0.95

    # Use label NAME only (not description) for category matching to avoid false positives
    # e.g., "duplicate" description contains "request" but shouldn't match feature keywords
    label_name_normalized = _normalize_label(label.name)
    score = 0.0

    if "bug" in label_name_normalized and any(
        _token_matches_keyword(token, keyword) for token in tokens for keyword in _BUG_KEYWORDS
    ):
        score = max(score, KEYWORD_BUG_SCORE)
    if any(tag in label_name_normalized for tag in ("feature", "enhancement", "request")) and (
        any(
            _token_matches_keyword(token, keyword)
            for token in tokens
            for keyword in _FEATURE_KEYWORDS
        )
        or any(phrase in query_lower for phrase in _FEATURE_PHRASES)
    ):
        score = max(score, KEYWORD_FEATURE_SCORE)
    if "doc" in label_name_normalized and any(
        _token_matches_keyword(token, keyword) for token in tokens for keyword in _DOCS_KEYWORDS
    ):
        score = max(score, KEYWORD_DOCS_SCORE)

    return score or None


def _keyword_matches(
    labels: Iterable[LabelRecord],
    query: str,
    *,
    threshold: float | None = None,
) -> list[LabelMatch]:
    min_score = _resolve_threshold(threshold)
    matches: list[LabelMatch] = []
    for label in labels:
        score = _keyword_match_score(label, query)
        if score is None or score < min_score:
            continue
        matches.append(
            LabelMatch(
                label=label,
                score=score,
                raw_score=score,
                score_type="keyword",
            )
        )
    return matches


def find_similar_labels(
    label_store: LabelVectorStore,
    query: str,
    *,
    threshold: float | None = None,
    k: int | None = None,
) -> list[LabelMatch]:
    label_store = _ensure_label_store(label_store)
    query = _ensure_query_text(query)
    if not query.strip():
        return []

    store = label_store.store
    if hasattr(store, "similarity_search_with_relevance_scores"):
        search_fn = store.similarity_search_with_relevance_scores
        score_type = "relevance"
    elif hasattr(store, "similarity_search_with_score"):
        search_fn = store.similarity_search_with_score
        score_type = "distance"
    else:
        matches = _keyword_matches(label_store.labels, query, threshold=threshold)
        matches.sort(key=lambda match: match.score, reverse=True)
        return matches

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

    keyword_matches = _keyword_matches(label_store.labels, query, threshold=threshold)
    if keyword_matches:
        seen = {_normalize_label(match.label.name) for match in matches}
        for match in keyword_matches:
            normalized = _normalize_label(match.label.name)
            if normalized and normalized not in seen:
                matches.append(match)
                seen.add(normalized)

    matches.sort(key=lambda match: match.score, reverse=True)
    return matches


def resolve_label_match(
    label_store: LabelVectorStore,
    query: str,
    *,
    threshold: float | None = None,
    k: int | None = None,
) -> LabelMatch | None:
    label_store = _ensure_label_store(label_store)
    query = _ensure_query_text(query)
    exact = _exact_short_label_match(label_store, query)
    if exact is not None:
        return exact
    matches = find_similar_labels(label_store, query, threshold=threshold, k=k)
    if matches:
        return matches[0]
    return None
