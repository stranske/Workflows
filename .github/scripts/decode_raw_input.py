#!/usr/bin/env python3
"""Decode JSON-encoded raw_input passed via workflow dispatch and write input.txt

Reads raw_input.json (single JSON string) -> writes decoded text to input.txt if non-empty.
Falls back to treating file contents as plain text if JSON parse fails.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

RAW_FILE = Path("raw_input.json")
OUT_FILE = Path("input.txt")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Decode or normalize topic input")
    parser.add_argument("--passthrough", action="store_true", help="Read plain text from --in file")
    parser.add_argument("--in", dest="in_file", help="Input file for passthrough mode")
    parser.add_argument(
        "--source",
        dest="source_tag",
        help="Source tag (repo_file|source_url|raw_input)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    text: str = ""
    source_used = args.source_tag or ("passthrough" if args.passthrough else "raw_input")
    if args.passthrough:
        if not args.in_file:
            return
        src_path = Path(args.in_file)
        if not src_path.exists():
            return
        text = src_path.read_text(encoding="utf-8", errors="ignore")
    else:
        if not RAW_FILE.exists():
            return
        raw = RAW_FILE.read_text(encoding="utf-8")
        try:
            text = json.loads(raw) if raw not in ("", "null") else ""
        except json.JSONDecodeError:
            text = raw
    original = text or ""
    # Normalize CR-only to LF and remove BOM if present
    normalization_counts = {
        "carriage_returns": original.count("\r") - original.count("\r\n"),
        "crlf_pairs": original.count("\r\n"),
        "bom": 1 if original.startswith("\ufeff") else 0,
        "nbsp": original.count("\u00a0"),
        "zws": original.count("\u200b"),
        "tabs": original.count("\t"),
        "other_zero_width": sum(
            original.count(ch) for ch in ("\u200c", "\u200d", "\u2060", "\ufeff")
        ),
    }
    # Remove BOM
    if original.startswith("\ufeff"):
        original = original[1:]
    # Replace CRLF and CR
    original = original.replace("\r\n", "\n").replace("\r", "\n")
    # Replace NBSP with normal space
    if "\u00a0" in original:
        original = original.replace("\u00a0", " ")
    # Remove zero-width spaces
    if "\u200b" in original:
        original = original.replace("\u200b", "")
    # Remove other zero-width characters
    for ch in ("\u200c", "\u200d", "\u2060", "\ufeff"):
        if ch in original:
            original = original.replace(ch, "")
    # Convert tabs to single space (avoid accidental code block breaks)
    if "\t" in original:
        original = original.replace("\t", " ")
    text = original.rstrip("\n")

    # Heuristic: if the input lost original line breaks (appears mostly as one very long line)
    # reconstruct newlines before common enumeration patterns so the parser can split topics.
    applied: list[str] = []

    def apply_enumerator_newlines(s: str) -> str:
        pattern = re.compile(
            r"(?<!\n)(?:(?<=\s)|^)(?P<enum>([0-9]{1,3}|[A-Za-z][0-9]*))[\)\.:\-]\s+"
        )
        parts: list[str] = []
        last = 0
        for m in pattern.finditer(s):
            start = m.start()
            if start > last:
                parts.append(s[last:start])
            parts.append("\n" + s[m.start() : m.end()])
            last = m.end()
        parts.append(s[last:])
        rebuilt = "".join(parts)
        if rebuilt.count("\n") > s.count("\n"):
            applied.append("enumerators")
            return rebuilt.lstrip("\n")
        return s

    def apply_section_headers(s: str) -> str:
        # Insert newlines before key section markers if they appear in the middle of a long line
        markers = [
            " Why ",
            " Tasks ",
            " Acceptance criteria ",
            " Implementation notes ",
        ]
        rebuilt = s
        for m in markers:
            # replace occurrences not already preceded by newline
            rebuilt = re.sub(rf"(?<!\n){re.escape(m)}", "\n" + m.strip() + "\n", rebuilt)
        if rebuilt != s:
            applied.append("sections")
        return rebuilt

    # Removed unused variable (was: text_before) to satisfy flake8 F841
    if text and ("\n" not in text or text.count("\n") < 2):
        text = apply_enumerator_newlines(text)
        text = apply_section_headers(text)

    # Fallback: if still almost no newlines but multiple enumerators exist, force split
    if text.count("\n") < 2 and len(re.findall(r"[0-9]{1,3}[)\.:\-]", text)) >= 2:
        forced = re.sub(r"\s+([0-9]{1,3}[)\.:\-])\s+", r"\n\1 ", text)
        if forced != text:
            applied.append("forced_split")
            text = forced

    def extract_enumerators(s: str) -> tuple[list[str], list[str]]:
        # Enumerators followed by punctuation ) . : - then space
        enum_pattern = re.compile(r"(^|\s)(([0-9]{1,3}|[A-Za-z][0-9]*))[\)\.:\-](?=\s)")
        tokens: list[str] = []
        for m in enum_pattern.finditer(s):
            token = m.group(2)
            tokens.append(token)
        distinct = []
        for t in tokens:
            if t not in distinct:
                distinct.append(t)
        return tokens, distinct

    raw_tokens, raw_distinct = extract_enumerators(original)
    reb_tokens, reb_distinct = extract_enumerators(text)

    diagnostics: dict[str, Any] = {
        "raw_len": len(original),
        "raw_newlines": original.count("\n"),
        "rebuilt_len": len(text),
        "rebuilt_newlines": text.count("\n"),
        "applied": applied,
        "raw_enum_count": len(raw_tokens),
        "raw_enum_distinct": raw_distinct[:50],
        "rebuilt_enum_count": len(reb_tokens),
        "rebuilt_enum_distinct": reb_distinct[:50],
        "whitespace_normalization": normalization_counts,
        "source_used": source_used,
    }

    if text.strip():
        OUT_FILE.write_text(text + "\n", encoding="utf-8")
    # Always write diagnostics when debug artifact collection might happen
    Path("decode_debug.json").write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
