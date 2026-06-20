#!/usr/bin/env python3
"""Extract an unspoofable verifier verdict from structured agent output."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

VERDICT_RE = re.compile(
    r"\b[\"']?verdict[\"']?\s*:\s*[\"']?(pass|fail)[\"']?\b",
    re.IGNORECASE,
)
FENCED_BLOCK_RE = re.compile(
    r"^[ \t]*```(?P<lang>[^\n`]*)\n(?P<body>.*?)^[ \t]*```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)

VALID_VERDICTS = {"pass", "concerns", "fail", "error"}


def _normalize_verdict(value: object) -> str:
    verdict = str(value or "").strip().lower().replace("_", "-")
    if verdict in {"passed", "success"}:
        return "pass"
    if verdict in {"needs-review", "needs review", "review", "concern", "concerns"}:
        return "concerns"
    if verdict in {"failed", "failure"}:
        return "fail"
    return verdict if verdict in VALID_VERDICTS else ""


def _diff_regions(markdown: str) -> list[str]:
    regions: list[str] = []
    for match in FENCED_BLOCK_RE.finditer(markdown):
        lang = match.group("lang").strip().lower()
        if lang in {"diff", "patch"}:
            regions.append(match.group("body"))
    return regions


def _without_diff_regions(markdown: str) -> str:
    def replace(match: re.Match[str]) -> str:
        lang = match.group("lang").strip().lower()
        return "\n" if lang in {"diff", "patch"} else match.group(0)

    return FENCED_BLOCK_RE.sub(replace, markdown)


def _json_candidates(markdown: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for match in FENCED_BLOCK_RE.finditer(markdown):
        if match.group("lang").strip().lower() != "json":
            continue
        try:
            parsed = json.loads(match.group("body"))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            candidates.append(parsed)

    return candidates


def build_verdict(output: str) -> dict[str, Any]:
    for region in _diff_regions(output):
        if VERDICT_RE.search(region):
            return {
                "verdict": "fail",
                "source": "diff-tamper",
                "needs_attention": True,
                "reason": "verdict marker appeared inside a diff/patch region",
            }

    output_without_diff = _without_diff_regions(output)
    for candidate in _json_candidates(output_without_diff):
        verdict = _normalize_verdict(candidate.get("verdict"))
        if not verdict:
            continue
        return {
            **candidate,
            "verdict": verdict,
            "source": "structured-json",
            "needs_attention": bool(candidate.get("needs_attention", verdict != "pass")),
        }

    return {
        "verdict": "error",
        "source": "missing-structured-json",
        "needs_attention": True,
        "reason": "no structured verifier JSON verdict found outside diff regions",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, help="Verifier agent output markdown")
    parser.add_argument("--json", required=True, help="Destination verdict JSON path")
    args = parser.parse_args()

    output = Path(args.output).read_text(encoding="utf-8") if Path(args.output).is_file() else ""
    verdict = build_verdict(output)
    destination = Path(args.json)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(verdict, sort_keys=True) + "\n", encoding="utf-8")
    print(f"verdict={verdict['verdict']}")
    print(f"source={verdict['source']}")
    if verdict.get("reason"):
        print(f"reason={verdict['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
