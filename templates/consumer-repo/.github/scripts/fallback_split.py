#!/usr/bin/env python3
"""Fallback enumerator-based topic splitter.

Used when the structured parser fails with exit code 3 but enumerators
were detected during decoding. Produces a minimal topics.json so the
workflow can still sync issues instead of hard-failing.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

INPUT_FILE = Path("input.txt")
OUTPUT_FILE = Path("topics.json")


def main() -> int:
    if not INPUT_FILE.exists():
        print("fallback_split: input.txt missing", flush=True)
        return 1
    text = INPUT_FILE.read_text(encoding="utf-8", errors="ignore")
    # Pattern captures enumerators like 1) 2. 3- A) A. etc.
    pattern = re.compile(r"(^|\n)\s*(([0-9]{1,3}|[A-Za-z][0-9]*))[\)\.:\-]\s+")
    matches = list(pattern.finditer(text))
    if not matches:
        print("fallback_split: no enumerators found", flush=True)
        return 2
    topics = []
    for idx, m in enumerate(matches):
        start_token = m.start(2)
        block_start = m.end(0)
        block_end = matches[idx + 1].start(2) if idx + 1 < len(matches) else len(text)
        segment = text[block_start:block_end].strip()
        title_line = (segment.splitlines() or [f"Topic {idx + 1}"])[0][:120]
        norm = re.sub(r"\s+", " ", title_line.lower())
        topics.append(
            {
                "title": title_line,
                "labels": [],
                "sections": {},
                "extras": segment,
                "enumerator": text[start_token : m.end(0)].strip().split()[0],
                "continuity_break": False,
                "guid": str(uuid.uuid5(uuid.NAMESPACE_DNS, norm)),
                "fallback": True,
            }
        )
    OUTPUT_FILE.write_text(json.dumps(topics, indent=2), encoding="utf-8")
    print(f"fallback_split: generated {len(topics)} topic(s)")
    return 0


if __name__ == "__main__":  # pragma: no cover - trivial wrapper
    raise SystemExit(main())
