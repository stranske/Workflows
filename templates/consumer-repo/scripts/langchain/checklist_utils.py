"""Shared helpers for checklist parsing and normalization."""

from __future__ import annotations


def is_placeholder_checklist_text(text: str) -> bool:
    """Return true for standard placeholder checklist text."""

    stripped = text.strip()
    normalized = stripped.strip("_").strip()
    return normalized in {
        "",
        "---",
        "Not provided.",
    } or (
        stripped.startswith("_")
        and stripped.endswith("_")
        and normalized.startswith("Filed from ")
        and " review" in normalized
    )
