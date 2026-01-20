#!/usr/bin/env python3
"""Update README badge blocks with metrics badge endpoints."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import quote

from scripts.metrics_badges_config import BADGE_TYPES

START_MARKER = "<!-- METRICS_BADGES_START -->"
END_MARKER = "<!-- METRICS_BADGES_END -->"


@dataclass(frozen=True)
class BadgeLink:
    label: str
    url: str

    def to_markdown(self) -> str:
        return f"![{self.label}]({self.url})"


def _build_badge_links(endpoint_base: str) -> list[BadgeLink]:
    base = endpoint_base.rstrip("/")
    links: list[BadgeLink] = []
    for badge in BADGE_TYPES:
        endpoint = f"{base}/{badge.name}.json"
        url = f"https://img.shields.io/endpoint?url={quote(endpoint, safe='')}"
        links.append(BadgeLink(label=badge.label, url=url))
    return links


def _render_badge_block(links: Iterable[BadgeLink]) -> str:
    lines = [link.to_markdown() for link in links]
    return "\n".join(lines)


def _replace_badge_block(content: str, block: str) -> tuple[str, bool]:
    start = content.find(START_MARKER)
    end = content.find(END_MARKER)
    if start == -1 or end == -1 or end < start:
        raise ValueError("badge markers not found")
    end += len(END_MARKER)
    replacement = f"{START_MARKER}\n{block}\n{END_MARKER}"
    updated = f"{content[:start]}{replacement}{content[end:]}"
    return updated, updated != content


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replace README badge markers with metrics badge links."
    )
    parser.add_argument(
        "--readme-path",
        default="README.md",
        help="Path to the README file to update.",
    )
    parser.add_argument(
        "--badge-endpoint-base",
        required=True,
        help="Base URL hosting the badge endpoint JSON files.",
    )
    return parser


def main(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    readme_path = Path(args.readme_path)
    if not readme_path.exists():
        print(f"README not found: {readme_path}", file=sys.stderr)
        return 1

    try:
        content = readme_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"failed to read README: {exc}", file=sys.stderr)
        return 1

    badge_links = _build_badge_links(args.badge_endpoint_base)
    badge_block = _render_badge_block(badge_links)

    try:
        updated, changed = _replace_badge_block(content, badge_block)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not changed:
        print("README badges already up to date.")
        return 0

    try:
        readme_path.write_text(updated, encoding="utf-8")
    except OSError as exc:
        print(f"failed to write README: {exc}", file=sys.stderr)
        return 1

    print(f"Updated badges in {readme_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main(sys.argv[1:]))
