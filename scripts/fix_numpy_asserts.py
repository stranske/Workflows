"""Stub implementation that rewrites common NumPy equality assertions."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(".")
TEST_ROOT = Path("tests")
TARGET_FILES: set[Path] = set()


def _tracked_arrays(lines: list[str]) -> set[str]:
    names: set[str] = set()
    pattern = re.compile(r"^\s*(\w+)\s*=\s*np\.array")
    for line in lines:
        match = pattern.match(line)
        if match:
            names.add(match.group(1))
    return names


def process_file(path: Path) -> bool:
    lines = path.read_text(encoding="utf-8").splitlines()
    array_vars = _tracked_arrays(lines)
    changed = False
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("assert ") and "==" in stripped and ".tolist()" not in stripped:
            match = re.match(r"\s*assert\s+(\w+)\s*==\s*(\[.*\])", stripped)
            if match:
                var_name = match.group(1)
                if var_name in array_vars:
                    prefix = line.split("assert", 1)[0]
                    line = f"{prefix}assert {var_name}.tolist() == {match.group(2)}"
                    changed = True
        new_lines.append(line)

    if changed:
        path.write_text("\n".join(new_lines), encoding="utf-8")
    return changed


def main() -> int:
    targets = TARGET_FILES or {p.relative_to(ROOT) for p in (ROOT / TEST_ROOT).rglob("*.py")}
    for rel_path in targets:
        process_file(ROOT / rel_path)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
