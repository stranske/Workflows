"""Normalize aggregation formatting in automation modules."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(".")
TARGET = ROOT / "automation_multifailure.py"


def _rewrite(text: str) -> tuple[str, bool]:
    if '" | ".join' in text or "' | '.join" in text:
        return text, False
    replaced = text.replace('",".join', '" | ".join').replace("',' .join", '" | ".join')
    changed = replaced != text
    return replaced, changed


def main() -> int:
    target = TARGET if TARGET.is_absolute() else ROOT / TARGET
    if not target.exists():
        return 0

    original = target.read_text(encoding="utf-8")
    updated, changed = _rewrite(original)
    if changed:
        target.write_text(updated, encoding="utf-8")
    else:
        print("Target already uses pipe separator")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
