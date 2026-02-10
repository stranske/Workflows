#!/usr/bin/env python3
"""
Build FAISS vector stores for issue deduplication.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

try:
    from scripts.langchain import semantic_matcher
except ModuleNotFoundError:
    import semantic_matcher


@dataclass(frozen=True)
class IssueRecord:
    number: int | None
    title: str
    body: str | None = None
    url: str | None = None


@dataclass
class IssueVectorStore:
    store: object
    provider: str
    model: str
    issues: list[IssueRecord]
    is_fallback: bool = False


@dataclass(frozen=True)
class IssueMatch:
    issue: IssueRecord
    score: float
    raw_score: float
    score_type: str


DEFAULT_SIMILARITY_THRESHOLD = 0.8
DEFAULT_SIMILARITY_K = 5
SIMILAR_ISSUES_MARKER = "<!-- issue-dedup:similar-issues -->"

logger = logging.getLogger(__name__)


def _coerce_issue(item: Any) -> IssueRecord | None:
    if isinstance(item, IssueRecord):
        return item
    if isinstance(item, Mapping):
        title = str(item.get("title") or "").strip()
        if not title:
            return None
        number = item.get("number")
        body = item.get("body")
        url = item.get("html_url") or item.get("url")
        return IssueRecord(
            number=int(number) if isinstance(number, int) else None,
            title=title,
            body=str(body) if body is not None else None,
            url=str(url) if url is not None else None,
        )
    title = str(getattr(item, "title", "") or "").strip()
    if not title:
        return None
    number = getattr(item, "number", None)
    body = getattr(item, "body", None)
    url = getattr(item, "html_url", None) or getattr(item, "url", None)
    return IssueRecord(
        number=int(number) if isinstance(number, int) else None,
        title=title,
        body=str(body) if body is not None else None,
        url=str(url) if url is not None else None,
    )


def _issue_text(issue: IssueRecord) -> str:
    title = issue.title.strip()
    body = (issue.body or "").strip()
    if body:
        return f"{title}\n{body}"
    return title


def build_issue_vector_store(
    issues: Iterable[Any],
    *,
    client_info: semantic_matcher.EmbeddingClientInfo | None = None,
    model: str | None = None,
) -> IssueVectorStore | None:
    issue_records: list[IssueRecord] = []
    for item in issues:
        record = _coerce_issue(item)
        if record is not None:
            issue_records.append(record)

    if not issue_records:
        return None

    resolved = client_info or semantic_matcher.get_embedding_client(model=model)
    if resolved is None:
        logger.info("No embedding provider available for issue deduplication.")
        return None

    try:
        from langchain_community.vectorstores import FAISS
    except ImportError:
        return None

    texts = [_issue_text(issue) for issue in issue_records]
    metadatas = [
        {"number": issue.number, "title": issue.title, "url": issue.url} for issue in issue_records
    ]
    store = FAISS.from_texts(texts, resolved.client, metadatas=metadatas)
    logger.info(
        "Issue dedup embedding provider=%s model=%s is_fallback=%s",
        resolved.provider,
        resolved.model,
        resolved.is_fallback,
    )
    return IssueVectorStore(
        store=store,
        provider=resolved.provider,
        model=resolved.model,
        is_fallback=resolved.is_fallback,
        issues=issue_records,
    )


def _resolve_threshold(explicit: float | None) -> float:
    if explicit is not None:
        return explicit
    env_value = os.environ.get("ISSUE_DEDUP_THRESHOLD")
    if env_value:
        try:
            return float(env_value)
        except ValueError:
            return DEFAULT_SIMILARITY_THRESHOLD
    return DEFAULT_SIMILARITY_THRESHOLD


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


def _issue_from_metadata(metadata: Mapping[str, Any], fallback_title: str | None) -> IssueRecord:
    title = str(metadata.get("title") or fallback_title or "").strip()
    number = metadata.get("number")
    url = metadata.get("url")
    return IssueRecord(
        number=int(number) if isinstance(number, int) else None,
        title=title or "Untitled",
        body=None,
        url=str(url) if url is not None else None,
    )


def find_similar_issues(
    issue_store: IssueVectorStore,
    query: str,
    *,
    threshold: float | None = None,
    k: int | None = None,
) -> list[IssueMatch]:
    """Return issues similar to query text using the vector store."""
    if not query or not query.strip():
        return []

    store = issue_store.store
    if hasattr(store, "similarity_search_with_relevance_scores"):
        search_fn = store.similarity_search_with_relevance_scores
        score_type = "relevance"
    elif hasattr(store, "similarity_search_with_score"):
        search_fn = store.similarity_search_with_score
        score_type = "distance"
    else:
        return []

    limit = k or DEFAULT_SIMILARITY_K
    try:
        results = search_fn(query, k=limit)
    except TypeError:
        results = search_fn(query, limit)

    min_score = _resolve_threshold(threshold)
    matches: list[IssueMatch] = []
    for doc, raw_score in results:
        metadata = getattr(doc, "metadata", {}) or {}
        fallback_title = getattr(doc, "page_content", None)
        issue = _issue_from_metadata(metadata, fallback_title)
        similarity = _similarity_from_score(float(raw_score), score_type)
        if similarity >= min_score:
            matches.append(
                IssueMatch(
                    issue=issue,
                    score=similarity,
                    raw_score=float(raw_score),
                    score_type=score_type,
                )
            )

    matches.sort(key=lambda match: match.score, reverse=True)
    return matches


def _format_similarity(score: float) -> str:
    clamped = min(max(score, 0.0), 1.0)
    return f"{round(clamped * 100):d}%"


def format_similar_issues_comment(
    matches: Iterable[IssueMatch],
    *,
    max_items: int = DEFAULT_SIMILARITY_K,
) -> str | None:
    match_list = list(matches)
    if not match_list:
        return None

    lines = [
        SIMILAR_ISSUES_MARKER,
        "### ⚠️ Potential Duplicate Detected",
        "",
        "This issue appears similar to existing open issues:",
        "",
    ]

    for match in match_list[: max(1, max_items)]:
        issue = match.issue
        title = issue.title.strip() or "Untitled"
        score = _format_similarity(match.score)
        reference = f"#{issue.number}" if issue.number is not None else "Issue"
        if issue.url:
            title = f"[{title}]({issue.url})"
        lines.append(f"- **{reference}** - {title} ({score} similarity)")

    lines += [
        "",
        "<details>",
        "<summary>Next steps for maintainers</summary>",
        "",
        "Review the linked issues to see if they address the same problem.",
        "If this is a duplicate, close this issue and add your context to the existing one.",
        "If this is different, add a comment explaining how this issue is distinct.",
        "If this is related but separate, link the issues and keep both open.",
        "</details>",
        "",
        "---",
        "*Auto-generated by duplicate detection. False positive? Just ignore this comment.*",
    ]

    return "\n".join(lines)
