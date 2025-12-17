"""Insert missing typing imports detected during mypy runs."""

from __future__ import annotations

import argparse
from pathlib import Path
import re

ROOT = Path(".")
DEFAULT_TARGETS: list[Path] = []


def _ensure_typing_imports(path: Path, names: set[str]) -> bool:
    text = path.read_text(encoding="utf-8")
    needed = {name for name in names if re.search(rf"\b{name}\b", text)}
    if not needed:
        return False

    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if line.startswith("from typing import"):
            existing = [segment.strip() for segment in line.split("import", 1)[1].split(",")]
            present = {name for name in existing if name}
            missing = needed - present
            if not missing:
                return False
            merged = sorted(present | needed)
            lines[idx] = f"from typing import {', '.join(merged)}"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True

    insert_at = 0
    for idx, line in enumerate(lines):
        insert_at = idx + 1
        if not line.startswith("from __future__"):
            break
    lines.insert(insert_at, f"from typing import {', '.join(sorted(needed))}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def main(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--paths", nargs="*", default=[])
    parsed, _unknown = parser.parse_known_args(args)

    targets = parsed.paths or [str(p) for p in DEFAULT_TARGETS]
    for target in targets:
        target_path = Path(target if isinstance(target, str) else str(target))
        full_path = target_path if target_path.is_absolute() else ROOT / target_path
        if full_path.is_file():
            _ensure_typing_imports(full_path, {"Optional", "Iterable"})
        elif full_path.is_dir():
            for file_path in full_path.rglob("*.py"):
                _ensure_typing_imports(file_path, {"Optional", "Iterable"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
