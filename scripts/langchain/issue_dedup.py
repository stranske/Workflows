#!/usr/bin/env python3
"""
Build FAISS vector stores for issue deduplication.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from scripts.langchain import semantic_matcher


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
        return None

    try:
        from langchain_community.vectorstores import FAISS
    except ImportError:
        return None

    texts = [_issue_text(issue) for issue in issue_records]
    metadatas = [
        {"number": issue.number, "title": issue.title, "url": issue.url}
        for issue in issue_records
    ]
    store = FAISS.from_texts(texts, resolved.client, metadatas=metadatas)
    return IssueVectorStore(
        store=store,
        provider=resolved.provider,
        model=resolved.model,
        issues=issue_records,
    )
