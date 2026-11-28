"""Keep pyproject.toml tool pins aligned with the automation pin file."""

from __future__ import annotations

import argparse
import dataclasses
import re
import sys
from collections.abc import Iterable
from pathlib import Path

# Removed: typing.Dict, typing.Tuple - use builtin dict, tuple
from re import Pattern

try:
    from scripts.sync_dev_dependencies import pinned_dev_tools
except ModuleNotFoundError:  # direct script execution
    from sync_dev_dependencies import pinned_dev_tools  # type: ignore[no-redef]

PIN_FILE = Path(".github/workflows/autofix-versions.env")
PYPROJECT_FILE = Path("pyproject.toml")
TEMPLATE_FILE = Path("templates/consumer-repo/.github/workflows/autofix-versions.env")
INTEGRATION_TEMPLATE_FILE = Path(
    "templates/integration-repo/.github/workflows/autofix-versions.env"
)
LOCKFILE_FILE = Path("requirements.lock")
LOCKFILE_PATTERN = re.compile(
    r"^(?P<lead>\s*)(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[^\s#]+)(?P<trail>\s*(?:#.*)?)$"
)


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


# pyproject may express these tools as a floor (">=") as well as an exact pin.
FLOOR_ALLOWED_PACKAGES = frozenset({"mypy"})


def _tool_config(env_key: str, package: str) -> ToolConfig:
    operator = "(?:==|>=)" if package in FLOOR_ALLOWED_PACKAGES else "=="
    return ToolConfig(
        env_key=env_key,
        package_name=package,
        pyproject_pattern=_compile(rf'"{re.escape(package)}{operator}(?P<version>[^"]+)"'),
        pyproject_format=f'"{package}=={{version}}"',
    )


def _canonical_pins() -> dict[str, str]:
    path = Path(__file__).resolve().parents[1] / PIN_FILE
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.lstrip().startswith("#") and "=" in line:
            key, raw_value = line.split("=", 1)
            values[key.strip()] = raw_value.strip()
    return values


# One config per tool pinned in autofix-versions.env, named through the single package map.
TOOL_CONFIGS: tuple[ToolConfig, ...] = tuple(
    _tool_config(env_key, package)
    for env_key, package in pinned_dev_tools(_canonical_pins()).items()
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


def ensure_template(
    source_content: str, template_file: Path, apply: bool
) -> tuple[dict[str, str], bool]:
    """Ensure a template env file mirrors the canonical pin file."""
    if not template_file.exists():
        return {}, False

    template_content = template_file.read_text(encoding="utf-8")
    if template_content == source_content:
        return {}, False

    if apply:
        template_file.write_text(source_content, encoding="utf-8")
    return {str(template_file): f"{template_file} differs from source pin file"}, True


def ensure_lockfile(
    lockfile_file: Path,
    configs: Iterable[ToolConfig],
    env: dict[str, str],
    apply: bool,
) -> dict[str, str]:
    """Ensure direct tool pins in requirements.lock match the canonical pin file."""
    if not lockfile_file.exists():
        return {}

    targets = {cfg.package_name.lower(): env[cfg.env_key] for cfg in configs}
    content = lockfile_file.read_text(encoding="utf-8")
    lines = content.splitlines()
    mismatches: dict[str, str] = {}
    updated_lines: list[str] = []

    for line in lines:
        match = LOCKFILE_PATTERN.match(line)
        if not match:
            updated_lines.append(line)
            continue

        name = match.group("name")
        current = match.group("version")
        expected = targets.get(name.lower())
        if expected and current != expected:
            mismatches[f"requirements.lock:{name}"] = (
                f"requirements.lock has {current}, pin file requires {expected}"
            )
            if apply:
                updated_lines.append(
                    f"{match.group('lead')}{name}=={expected}{match.group('trail')}"
                )
            else:
                updated_lines.append(line)
        else:
            updated_lines.append(line)

    if apply and mismatches:
        updated_content = "\n".join(updated_lines)
        if content.endswith("\n"):
            updated_content += "\n"
        lockfile_file.write_text(updated_content, encoding="utf-8")

    return mismatches


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

    source_content = PIN_FILE.read_text(encoding="utf-8")
    template_mismatches: dict[str, str] = {}
    template_updates = False
    for template_file in (TEMPLATE_FILE, INTEGRATION_TEMPLATE_FILE):
        mismatches, updated = ensure_template(source_content, template_file, apply_changes)
        template_mismatches.update(mismatches)
        template_updates = template_updates or updated

    lockfile_mismatches = ensure_lockfile(LOCKFILE_FILE, TOOL_CONFIGS, env_values, apply_changes)

    all_mismatches = {**project_mismatches, **template_mismatches, **lockfile_mismatches}
    if all_mismatches and not apply_changes:
        for package, message in all_mismatches.items():
            print(f"✗ {package}: {message}", file=sys.stderr)
        print(
            "Use --apply to sync tool versions to pyproject.toml and template.",
            file=sys.stderr,
        )
        return 1

    if apply_changes:
        if pyproject_updated != pyproject_content:
            PYPROJECT_FILE.write_text(pyproject_updated, encoding="utf-8")
            print("✓ tool pins synced to pyproject.toml")
        if template_updates:
            print("✓ template autofix-versions.env files synced from source")
        if lockfile_mismatches:
            print("✓ requirements.lock direct tool pins synced from source")

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        sys.exit(main(sys.argv[1:]))
    except SyncError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)
