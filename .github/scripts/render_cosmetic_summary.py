"""Render the cosmetic repair summary for GitHub Actions.

This script reads the JSON payload produced by the cosmetic repair job and
prints a markdown summary suitable for appending to the GitHub step summary.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_summary_lines(data: dict) -> list[str]:
    """Convert the cosmetic repair metadata into human readable lines."""

    lines: list[str] = []
    status = data.get("status", "unknown")
    lines.append(f"- Status: **{status}**")

    changed = data.get("changed_files") or []
    if changed:
        lines.append(f"- Changed files ({len(changed)}):")
        lines.extend(f"  - `{path}`" for path in changed)
    else:
        lines.append("- No file changes detected.")

    pr_url = data.get("pr_url")
    if pr_url:
        lines.append(f"- PR: {pr_url}")

    instructions = data.get("instructions") or []
    if instructions:
        lines.append("- Instructions processed:")
        for entry in instructions:
            kind = entry.get("kind", "unknown")
            path = entry.get("path", "?")
            guard = entry.get("guard", "")
            extra = f" ({guard})" if guard else ""
            lines.append(f"  - `{kind}` → `{path}`{extra}")

    return lines


def read_summary(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Failed to parse {path}: {exc}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render cosmetic repair summary")
    parser.add_argument("summary_path", type=Path, help="Path to the summary JSON file")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = read_summary(args.summary_path)
    for line in build_summary_lines(data):
        print(line)


if __name__ == "__main__":
    main()
