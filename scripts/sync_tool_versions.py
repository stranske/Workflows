"""Keep pyproject.toml tool pins aligned with the automation pin file."""

from __future__ import annotations

import argparse
import dataclasses
import re
import sys
from pathlib import Path

# Removed: typing.Dict, typing.Tuple - use builtin dict, tuple
from re import Pattern
from collections.abc import Iterable

PIN_FILE = Path(".github/workflows/autofix-versions.env")
PYPROJECT_FILE = Path("pyproject.toml")


@dataclasses.dataclass(frozen=True)
class ToolConfig:
    """Metadata describing how to align a tool's version pins."""

    env_key: str
    package_name: str
    pyproject_pattern: Pattern[str]
    pyproject_format: str


def _compile(pattern: str) -> Pattern[str]:
    return re.compile(pattern, flags=re.MULTILINE)


def _format_entry(pattern: str, version: str) -> str:
    return pattern.format(version=version)


TOOL_CONFIGS: tuple[ToolConfig, ...] = (
    ToolConfig(
        env_key="BLACK_VERSION",
        package_name="black",
        pyproject_pattern=_compile(r'"black==(?P<version>[^"]+)"'),
        pyproject_format='"black=={version}",',
    ),
    ToolConfig(
        env_key="RUFF_VERSION",
        package_name="ruff",
        pyproject_pattern=_compile(r'"ruff==(?P<version>[^"]+)"'),
        pyproject_format='"ruff=={version}",',
    ),
    ToolConfig(
        env_key="ISORT_VERSION",
        package_name="isort",
        pyproject_pattern=_compile(r'"isort==(?P<version>[^"]+)"'),
        pyproject_format='"isort=={version}",',
    ),
    ToolConfig(
        env_key="DOCFORMATTER_VERSION",
        package_name="docformatter",
        pyproject_pattern=_compile(r'"docformatter==(?P<version>[^"]+)"'),
        pyproject_format='"docformatter=={version}",',
    ),
    ToolConfig(
        env_key="MYPY_VERSION",
        package_name="mypy",
        pyproject_pattern=_compile(r'"mypy(?:==|>=)(?P<version>[^"]+)"'),
        pyproject_format='"mypy=={version}",',
    ),
    ToolConfig(
        env_key="PYTEST_VERSION",
        package_name="pytest",
        pyproject_pattern=_compile(r'"pytest==(?P<version>[^"]+)"'),
        pyproject_format='"pytest=={version}",',
    ),
    ToolConfig(
        env_key="PYTEST_COV_VERSION",
        package_name="pytest-cov",
        pyproject_pattern=_compile(r'"pytest-cov==(?P<version>[^"]+)"'),
        pyproject_format='"pytest-cov=={version}",',
    ),
    ToolConfig(
        env_key="COVERAGE_VERSION",
        package_name="coverage",
        pyproject_pattern=_compile(r'"coverage==(?P<version>[^"]+)"'),
        pyproject_format='"coverage=={version}",',
    ),
)


class SyncError(RuntimeError):
    """Raised when the repository is misconfigured or a sync fails."""


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        raise SyncError(f"Pin file '{path}' does not exist")

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#"):
            continue
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        values[key.strip()] = raw_value.strip()

    missing = [cfg.env_key for cfg in TOOL_CONFIGS if cfg.env_key not in values]
    if missing:
        raise SyncError(f"Pin file '{path}' is missing keys: {', '.join(missing)}")
    return values


def ensure_pyproject(
    content: str, configs: Iterable[ToolConfig], env: dict[str, str], apply: bool
) -> tuple[str, dict[str, str]]:
    mismatches: dict[str, str] = {}
    updated_content = content

    for cfg in configs:
        expected = env[cfg.env_key]
        match = cfg.pyproject_pattern.search(updated_content)
        if not match:
            raise SyncError(
                f"pyproject.toml is missing an entry for {cfg.package_name}; "
                f"expected pattern '{cfg.pyproject_pattern.pattern}'"
            )
        current = match.group("version")
        if current != expected:
            mismatches[cfg.package_name] = f"pyproject has {current}, pin file requires {expected}"
            if apply:
                # Bind cfg and expected in closure to avoid B023
                replacement = _format_entry(cfg.pyproject_format, expected)
                updated_content = cfg.pyproject_pattern.sub(
                    lambda m, repl=replacement: repl,
                    updated_content,
                    count=1,
                )
    return updated_content, mismatches


def main(argv: Iterable[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Synchronise tool version pins with pyproject.toml",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Rewrite pyproject.toml to match pinned versions instead of only checking",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Explicitly run in verification-only mode (default)",
    )
    args = parser.parse_args(list(argv))
    apply_changes = args.apply

    if args.check and args.apply:
        parser.error("--apply and --check are mutually exclusive")
    if not args.apply:
        apply_changes = False

    env_values = parse_env_file(PIN_FILE)

    pyproject_content = PYPROJECT_FILE.read_text(encoding="utf-8")

    pyproject_updated, project_mismatches = ensure_pyproject(
        pyproject_content, TOOL_CONFIGS, env_values, apply_changes
    )

    if project_mismatches and not apply_changes:
        for package, message in project_mismatches.items():
            print(f"✗ {package}: {message}", file=sys.stderr)
        print(
            "Use --apply to rewrite pyproject.toml with the pinned versions.",
            file=sys.stderr,
        )
        return 1

    if apply_changes and pyproject_updated != pyproject_content:
        PYPROJECT_FILE.write_text(pyproject_updated, encoding="utf-8")
        print("✓ tool pins synced to pyproject.toml")

    return 0


if __name__ == "__main__":
    # TODO Phase 4: Remove trend_analysis.script_logging dependency when available
    # For now, use simple logging setup
    try:
        from trend_analysis.script_logging import setup_script_logging

        setup_script_logging(module_file=__file__)
    except ImportError:
        # Fallback for workflow repo without trend_analysis package
        import logging

        logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        sys.exit(main(sys.argv[1:]))
    except SyncError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)
