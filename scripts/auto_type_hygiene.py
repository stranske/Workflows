#!/usr/bin/env python
"""Automatically apply lightweight type-hygiene adjustments.

Goals (automation-safe):
  * Install missing type stubs (handled by workflow separately) – this script only mutates source files.
    * Optionally inject `# type: ignore[import-untyped, unused-ignore]` comments for a curated allowlist of known untyped
        imports.  If a stub file or `py.typed` marker is present, the script leaves the import unchanged.
  * Idempotent: never duplicate ignore comments.
  * Skip legacy / excluded paths (archives/legacy_assets/, Old/, notebooks/old/).
  * Avoid masking *semantic* errors – we only touch import lines that succeed at runtime but lack stubs.

Non-goals:
  * Do not auto-ignore undefined names, return type mismatches, or attr errors.
  * Do not blanket `type: ignore` whole files.

Invocation: safe to run multiple times; exits 0 even if no changes.

Config via environment variables:
  AUTO_TYPE_ALLOWLIST   Comma-separated module base names to treat as untyped (default: "yaml")
  AUTO_TYPE_DRY_RUN     If set to '1' print planned changes but do not write.

This script intentionally uses only the standard library.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_DIRS = [ROOT / "src", ROOT / "tests"]
EXCLUDE_PATTERNS = [
    re.compile(r"(^|/)archives/legacy_assets(/|$)"),
    re.compile(r"(^|/)Old(/|$)"),
    re.compile(r"(^|/)notebooks/old(/|$)"),
]
DEFAULT_ALLOWLIST = ["yaml"]
TYPED_FALLBACK = {"yaml"}


def _load_allowlist() -> list[str]:
    raw = os.environ.get("AUTO_TYPE_ALLOWLIST")
    if raw is None:
        return DEFAULT_ALLOWLIST.copy()

    parsed = [segment.strip() for segment in raw.split(",") if segment.strip()]
    if not parsed:
        return DEFAULT_ALLOWLIST.copy()
    return parsed


ALLOWLIST = _load_allowlist()
DRY_RUN = os.environ.get("AUTO_TYPE_DRY_RUN") == "1"

IMPORT_PATTERN = re.compile(
    r"^(?P<indent>\s*)(import|from)\s+(?P<module>[a-zA-Z0-9_\.]+)(?P<rest>.*)$"
)
IGNORE_CODES: tuple[str, ...] = ("import-untyped", "unused-ignore")
IGNORE_TOKEN = f"# type: ignore[{', '.join(IGNORE_CODES)}]"


def should_exclude(path: Path) -> bool:
    rel = str(path.as_posix())
    return any(p.search(rel) for p in EXCLUDE_PATTERNS)


def _has_stub_package(module: str) -> bool:
    base = module.split(".")[0]
    stub_dirname = f"{base}-stubs"
    for entry in sys.path:
        try:
            path = Path(entry)
        except TypeError:
            continue
        if not path.exists():
            continue
        candidate = path / stub_dirname
        if not candidate.is_dir():
            continue
        if (candidate / "py.typed").exists():
            return True
    return False


def module_has_types(module: str) -> bool:
    """Return ``True`` if ``module`` has typing support available."""

    if module.split(".")[0] in TYPED_FALLBACK:
        return True

    parts = module.split(".")
    for base in SRC_DIRS:
        package_path = base.joinpath(*parts)
        stub = package_path.with_suffix(".pyi")
        if stub.exists():
            return True
        if (package_path / "__init__.pyi").exists():
            return True

    try:
        spec = importlib.util.find_spec(module)
    except (ImportError, AttributeError, ValueError):
        return False

    if spec is None:
        return False

    origin = getattr(spec, "origin", None)
    if isinstance(origin, str) and origin.endswith(".pyi"):
        return True

    submodules = getattr(spec, "submodule_search_locations", None)
    if submodules:
        for location in submodules:
            if location and Path(location).joinpath("py.typed").exists():
                return True

    return _has_stub_package(module)


def needs_ignore(module: str) -> bool:
    base = module.split(".")[0]
    return base in ALLOWLIST and not module_has_types(module)


def process_file(path: Path) -> tuple[bool, list[str]]:
    """Return (changed, new_lines)."""
    try:
        original = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return False, []

    changed = False
    new_lines: list[str] = []

    for line in original:
        m = IMPORT_PATTERN.match(line)
        if not m:
            new_lines.append(line)
            continue
        module = m.group("module")
        if needs_ignore(module):
            target_codes = set(IGNORE_CODES)
            if IGNORE_TOKEN in line:
                new_lines.append(line)
                continue

            ignore_match = re.search(r"#\s*type:\s*ignore(?P<bracket>\[[^\]]*\])?", line)
            if ignore_match:
                bracket = ignore_match.group("bracket")
                if bracket is None:
                    replacement = IGNORE_TOKEN
                else:
                    bracket_content = bracket[1:-1].strip()
                    if bracket_content:
                        codes = [
                            code.strip() for code in bracket_content.split(",") if code.strip()
                        ]
                    else:
                        codes = []
                    codes_set = set(codes)
                    if target_codes.issubset(codes_set):
                        new_lines.append(line)
                        continue
                    merged = list(codes)
                    for code in IGNORE_CODES:
                        if code not in codes_set:
                            merged.append(code)
                    replacement = f"# type: ignore[{', '.join(merged)}]"

                start, end = ignore_match.span()
                line = f"{line[:start]}{replacement}{line[end:]}"
                changed = True
            else:
                line = f"{line.rstrip()}  {IGNORE_TOKEN}"
                changed = True
        new_lines.append(line)

    return changed, new_lines


def iter_python_files() -> Iterator[Path]:
    for base in SRC_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if should_exclude(path):
                continue
            yield path


def main() -> int:
    modified: list[Path] = []
    for py_file in iter_python_files():
        changed, new_lines = process_file(py_file)
        if changed:
            modified.append(py_file)
            if not DRY_RUN:
                py_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    if modified:
        rels = [str(p.relative_to(ROOT)) for p in modified]
        print(f"[auto_type_hygiene] Added import-untyped ignores to {len(modified)} file(s):")
        for r in rels:
            print(f"  - {r}")
    else:
        print("[auto_type_hygiene] No changes needed.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    try:
        from trend_analysis.script_logging import setup_script_logging

        setup_script_logging(module_file=__file__)
    except ImportError:
        pass
    raise SystemExit(main())
