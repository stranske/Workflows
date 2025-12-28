#!/usr/bin/env python3
"""Parse ChatGPT topics from input.txt and produce topics.json."""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from pathlib import Path

INPUT_PATH = Path("input.txt")
OUTPUT_PATH = Path("topics.json")

# Exit code conventions (documented for the workflow & tests):
# 1 = generic failure / missing file (legacy paths kept)
# 2 = empty input file
# 3 = no numbered topics detected (and fallback disabled)
# 4 = parsed produced zero topic objects (should not normally occur)

ALLOW_FALLBACK = os.environ.get("ALLOW_SINGLE_TOPIC", "0") in {"1", "true", "True"}


def _load_text() -> str:
    try:
        text = INPUT_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:  # pragma: no cover - guardrail for workflow execution
        raise SystemExit("No input.txt found to parse.") from exc
    if not text:
        raise SystemExit("No topic content provided.")
    return text


def _split_numbered_items(text: str) -> list[dict[str, str | list[str] | bool]]:
    """Split raw text into enumerated topic blocks.

    Supports enumeration tokens:
      Numeric: 1. 1) 1: 1-
      Alpha:   A. A) A: A-
      Alphanum: A1. A1) (letter followed by digits)

    Adds continuity detection for numeric and alpha sequences; alphanum is left as-is.
    Each returned item dict includes:
      title, lines, enumerator, continuity_break (bool)
    """
    pattern = re.compile(r"^\s*(?P<enum>(?:\d+|[A-Za-z]\d+|[A-Za-z]))[\).:\-]\s+(?P<title>.+)$")
    items: list[dict[str, str | list[str] | bool]] = []
    current: dict[str, str | list[str] | bool] | None = None
    style: str | None = None  # 'numeric' | 'alpha' | 'alphanum'
    last_enum_value: str | None = None

    def detect_style(token: str) -> str:
        if token.isdigit():
            return "numeric"
        if re.fullmatch(r"[A-Za-z]", token):
            return "alpha"
        if re.fullmatch(r"[A-Za-z]\d+", token):
            return "alphanum"
        return "unknown"

    def continuity_ok(prev: str | None, current_token: str, current_style: str) -> bool:
        if prev is None:
            return True
        if current_style == "numeric" and prev.isdigit() and current_token.isdigit():
            try:
                return int(current_token) == int(prev) + 1
            except ValueError:  # pragma: no cover - defensive
                return True
        if (
            current_style == "alpha"
            and re.fullmatch(r"[A-Za-z]", prev)
            and re.fullmatch(r"[A-Za-z]", current_token)
        ):
            return ord(current_token.upper()) == ord(prev.upper()) + 1
        # For alphanum or unknown styles skip continuity enforcement
        return True

    for raw_line in text.splitlines():
        m = pattern.match(raw_line)
        if m:
            token = m.group("enum")
            title = m.group("title").strip()
            # Clean markdown emphasis and trailing punctuation for GUID stability
            title = re.sub(r"^[*_`]+|[*_`]+$", "", title).strip()
            title = title.rstrip(". ")
            if current:
                items.append(current)
            if style is None:
                style = detect_style(token)
            is_cont_ok = continuity_ok(last_enum_value, token, style)
            current = {
                "title": title,
                "lines": [],
                "enumerator": token,
                "continuity_break": not is_cont_ok,
            }
            last_enum_value = token
        else:
            if current is None:
                continue
            lines_field = current.setdefault("lines", [])
            if isinstance(lines_field, list):
                lines_field.append(raw_line.rstrip("\n"))
    if current:
        items.append(current)
    if not items:
        raise SystemExit("No numbered topics were found in the provided text.")
    return items


def _parse_sections(
    raw_lines: list[str],
) -> tuple[list[str], dict[str, list[str]], list[str]]:
    section_aliases: dict[str, set[str]] = {
        "why": {"why"},
        "tasks": {"tasks"},
        "acceptance_criteria": {"acceptance criteria", "acceptance criteria."},
        "implementation_notes": {
            "implementation notes",
            "implementation note",
            "notes",
        },
    }

    labels: list[str] = []
    remaining: list[str] = []
    label_found = False
    for line in raw_lines:
        stripped = line.strip()
        lowered = stripped.lower()
        if not label_found and lowered.startswith("labels"):
            label_found = True
            _, _, remainder = stripped.partition(":")
            if remainder:
                parts = re.split(r"[;,]", remainder)
                labels.extend([part.strip() for part in parts if part.strip()])
            continue
        remaining.append(line)

    sections: dict[str, list[str]] = {key: [] for key in section_aliases}
    extras: list[str] = []
    current_section: str | None = None

    for line in remaining:
        stripped = line.strip()
        if stripped == "":
            if current_section:
                sections[current_section].append("")
            continue
        normalized = re.sub(r"[^a-z0-9 ]+", " ", stripped.lower()).strip()
        normalized = normalized.rstrip(":").strip()
        matched_section = None
        for key, aliases in section_aliases.items():
            if normalized in aliases:
                matched_section = key
                break
        if matched_section:
            current_section = matched_section
            continue
        if current_section:
            sections[current_section].append(line)
        else:
            extras.append(line)

    return labels, sections, extras


def _join_section(lines: list[str]) -> str:
    return "\n".join(lines).strip()


def parse_text(text: str, *, allow_single_fallback: bool = False) -> list[dict[str, object]]:
    """Parse raw *text* into topic dictionaries.

    Parameters
    ----------
    text : str
        The raw input content.
    allow_single_fallback : bool, default False
        When True and no numbered topics are found, treat entire *text* as one topic.
    """
    try:
        items = _split_numbered_items(text)
    except SystemExit as exc:
        if allow_single_fallback and "No numbered topics" in str(exc):
            cleaned = text.strip()
            if not cleaned:
                raise SystemExit(2) from None
            items = [
                {
                    "title": cleaned.splitlines()[0][:120].strip(),
                    "lines": cleaned.splitlines()[1:],
                }
            ]
        else:
            # Re-raise original (will map to code 3 upstream if message matches)
            raise

    parsed: list[dict[str, object]] = []
    for item in items:
        raw_lines_field = item.get("lines", [])
        if isinstance(raw_lines_field, list):
            raw_lines = [str(line) for line in raw_lines_field if line is not None]
        elif isinstance(raw_lines_field, str):
            raw_lines = [raw_lines_field]
        else:
            raw_lines = []
        labels, sections, extras = _parse_sections(raw_lines)
        data: dict[str, object] = {
            "title": str(item.get("title", "")).strip(),
            "labels": labels,
            "sections": {key: _join_section(value) for key, value in sections.items()},
            "extras": _join_section(extras),
            "enumerator": item.get("enumerator"),
            "continuity_break": bool(item.get("continuity_break", False)),
        }
        normalized_title = re.sub(r"\s+", " ", str(data["title"]).strip().lower())
        data["guid"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, normalized_title))
        parsed.append(data)
    return parsed


def parse_topics() -> list[dict[str, object]]:
    text = _load_text()
    return parse_text(text, allow_single_fallback=ALLOW_FALLBACK)


def main() -> None:
    try:
        parsed = parse_topics()
    except SystemExit as exc:
        msg = str(exc)
        # Map specific messages to distinct exit codes for CI diagnostics
        if msg.startswith("No input.txt"):
            raise  # keep exit 1
        if msg == "No topic content provided.":
            raise SystemExit(2) from None
        if msg.startswith("No numbered topics"):
            raise SystemExit(3) from None
        raise
    if not parsed:
        raise SystemExit(4)
    preview = str(parsed[0].get("title", "")) if parsed else ""
    OUTPUT_PATH.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
    print(f"Parsed {len(parsed)} topic(s). First title: {preview[:80]}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        raise
