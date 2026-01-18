#!/usr/bin/env python3
"""
Integration helpers for applying semantic labels to issues.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

try:
    from scripts.langchain import label_matcher
except ModuleNotFoundError:
    import label_matcher


@dataclass
class IssueData:
    title: str
    body: str | None = None
    labels: list[str] = field(default_factory=list)

    def apply_labels(self, new_labels: Iterable[str]) -> None:
        self.labels = merge_labels(self.labels, new_labels)


def merge_labels(existing: Iterable[str], incoming: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for label in list(existing) + list(incoming):
        normalized = _normalize_label(label)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(label)
    return merged


def label_issue(
    issue: IssueData,
    available_labels: Iterable[Any],
    *,
    threshold: float | None = None,
    k: int | None = None,
    max_labels: int | None = None,
) -> list[str]:
    issue_text = _build_issue_text(issue)
    label_store = _build_label_store(available_labels)
    if label_store is None:
        return []

    matches = label_matcher.find_similar_labels(label_store, issue_text, threshold=threshold, k=k)
    names = _select_label_names(matches, max_labels=max_labels)
    issue.apply_labels(names)
    return names


def _build_issue_text(issue: IssueData) -> str:
    if not isinstance(issue.title, str) or not issue.title.strip():
        raise ValueError("issue title must be a non-empty string.")
    parts = [issue.title.strip()]
    if issue.body and issue.body.strip():
        parts.append(issue.body.strip())
    return "\n\n".join(parts)


def _build_label_store(labels: Iterable[Any]) -> label_matcher.LabelVectorStore | None:
    label_records = _collect_label_records(labels)
    if not label_records:
        return None

    vector_store = label_matcher.build_label_vector_store(label_records)
    if vector_store is not None:
        return vector_store

    return label_matcher.LabelVectorStore(
        store=object(),
        provider="keyword",
        model="keyword",
        labels=label_records,
    )


def _collect_label_records(labels: Iterable[Any]) -> list[label_matcher.LabelRecord]:
    if labels is None:
        raise ValueError("labels must be an iterable of label records, not None.")
    if isinstance(labels, (str, bytes)):
        raise ValueError("labels must be an iterable of label records, not a string.")
    if not isinstance(labels, Iterable):
        raise ValueError("labels must be an iterable of label records.")

    records: list[label_matcher.LabelRecord] = []
    for index, item in enumerate(labels):
        record = _coerce_label_record(item)
        if record is not None:
            records.append(record)
        else:
            if isinstance(item, Mapping):
                raise ValueError(f"Label entry at index {index} is missing a name.")
            if getattr(item, "name", None) is not None or getattr(item, "label", None) is not None:
                raise ValueError(f"Label entry at index {index} has an empty name.")
            raise ValueError(f"Unsupported label entry at index {index}: {type(item).__name__}.")
    return records


def _coerce_label_record(item: Any) -> label_matcher.LabelRecord | None:
    if isinstance(item, label_matcher.LabelRecord):
        return item
    if isinstance(item, (str, bytes)):
        name = item.decode("utf-8", errors="replace") if isinstance(item, bytes) else item
        name = name.strip()
        if not name:
            return None
        return label_matcher.LabelRecord(name=name)
    if isinstance(item, Mapping):
        name = str(item.get("name") or item.get("label") or "").strip()
        if not name:
            return None
        description = item.get("description")
        return label_matcher.LabelRecord(
            name=name,
            description=str(description) if description is not None else None,
        )
    name = str(getattr(item, "name", "") or "").strip()
    if not name:
        return None
    description = getattr(item, "description", None)
    return label_matcher.LabelRecord(
        name=name,
        description=str(description) if description is not None else None,
    )


def _select_label_names(
    matches: Sequence[label_matcher.LabelMatch],
    *,
    max_labels: int | None = None,
) -> list[str]:
    if not matches:
        return []
    names: list[str] = []
    seen: set[str] = set()
    for match in matches:
        normalized = _normalize_label(match.label.name)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        names.append(match.label.name)
        if max_labels is not None and len(names) >= max_labels:
            break
    return names


def _normalize_label(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(label or "").lower())
