#!/usr/bin/env python3
"""Proposal policy and PyPI freshness report for the dev-tool source lane.

Used by maint-auto-update-pypi-versions.yml to check the UTC proposal window
and report freshness of the autofix-versions.env pins.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

if __package__:
    from scripts.sync_dev_dependencies import pinned_dev_tools
else:  # direct script execution
    from sync_dev_dependencies import pinned_dev_tools  # type: ignore[no-redef]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    package: str
    current_output: str
    latest_output: str
    current_env: str
    latest_env: str


@dataclass(frozen=True)
class ToolStatus:
    tool: str
    current: str
    latest: str
    status: str
    has_update: bool


PIN_FILE = Path(__file__).resolve().parents[1] / ".github/workflows/autofix-versions.env"


def read_pins(path: Path = PIN_FILE) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def _tool_spec(package: str) -> ToolSpec:
    slug = package.replace("-", "_")
    return ToolSpec(
        package,
        package,
        f"{slug}_current",
        f"{slug}_latest",
        f"{slug.upper()}_CURRENT",
        f"{slug.upper()}_LATEST",
    )


# Every tool autofix-versions.env pins, named through the one package map
# (sync_dev_dependencies.DEV_TOOL_PACKAGES). Before 2026-11-28 this was a hand-kept
# list that never checked pytest-xdist.
_PINS = read_pins()
PINNED_TOOLS: dict[str, str] = pinned_dev_tools(_PINS)
TOOLS: tuple[ToolSpec, ...] = tuple(
    _tool_spec(package) for package in sorted(PINNED_TOOLS.values())
)
CURRENT_BY_PACKAGE: dict[str, str] = {
    package: _PINS[env_key] for env_key, package in PINNED_TOOLS.items()
}

VERSION_RE = re.compile(
    r"(?P<version>\d+(?:\.\d+)+(?:[-_.]?(?:a|b|rc|post|dev)\d*)?)",
    re.IGNORECASE,
)


def parse_tool_version_output(tool: str, output: str) -> str | None:
    """Extract a version from common CLI or API output without raising."""
    text = (output or "").strip()
    if not text or text.lower() == "unknown":
        return None
    match = VERSION_RE.search(text)
    if not match:
        return None
    return match.group("version")


def latest_pypi_version(package: str) -> str | None:
    """Fetch the latest PyPI version for *package*, returning None on failure."""
    url = f"https://pypi.org/pypi/{package}/json"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read())
    except Exception as exc:
        print(f"Warning: Could not fetch {package}: {exc}", file=sys.stderr)
        return None
    version = data.get("info", {}).get("version")
    return str(version) if version else None


def compare_versions(current: dict[str, str], latest: dict[str, str]) -> list[ToolStatus]:
    statuses: list[ToolStatus] = []
    for spec in sorted(TOOLS, key=lambda item: item.name):
        current_raw = current.get(spec.name, "")
        latest_raw = latest.get(spec.name, "")
        current_version = parse_tool_version_output(spec.name, current_raw)
        latest_version = parse_tool_version_output(spec.name, latest_raw)
        if not latest_version:
            status = "Check failed"
            has_update = False
            latest_label = latest_raw or "unknown"
        elif not current_version:
            status = "Current version invalid"
            has_update = False
            latest_label = latest_version
        elif current_version != latest_version:
            status = "Update available"
            has_update = True
            latest_label = latest_version
        else:
            status = "Current"
            has_update = False
            latest_label = latest_version
        statuses.append(
            ToolStatus(
                tool=spec.name,
                current=current_version or current_raw or "unknown",
                latest=latest_label,
                status=status,
                has_update=has_update,
            )
        )
    return statuses


def render_report(statuses: list[ToolStatus]) -> str:
    lines = [
        "## Tool Version Status",
        "",
        "| Tool | Current | Latest | Status |",
        "|------|---------|--------|--------|",
    ]
    for item in statuses:
        lines.append(f"| {item.tool} | {item.current} | {item.latest} | {item.status} |")
    return "\n".join(lines)


def render_updates(statuses: list[ToolStatus]) -> str:
    updates = [
        f"- **{item.tool}**: {item.current} -> {item.latest}"
        for item in statuses
        if item.has_update
    ]
    return "\n".join(updates)


def render_issue_body(
    *,
    report: str,
    updates: str,
    workflow_url: str,
    timestamp: str,
) -> str:
    instructions = "\n".join(
        [
            "source .github/workflows/autofix-versions.env",
            "pip install "
            + " ".join(f'"{package}==${env_key}"' for env_key, package in PINNED_TOOLS.items()),
            "black --check --line-length 100 .",
            "ruff check .",
            "mypy src tests",
        ]
    )
    updates_block = updates or "No tool updates were detected."
    return (
        f"{report}\n\n"
        "### Updates Available\n\n"
        f"{updates_block}\n\n"
        "### Update Instructions\n\n"
        "1. Update `.github/workflows/autofix-versions.env` with the new versions\n"
        "2. Test locally:\n"
        "```bash\n"
        f"{instructions}\n"
        "```\n"
        "3. Create a PR with the version updates\n"
        "4. Ensure all CI checks pass before merging\n\n"
        "### Documentation\n\n"
        "See `.github/workflows/autofix-versions.env` for the version file.\n\n"
        "---\n"
        "*This issue was automatically generated by the "
        f"[Tool Version Check workflow]({workflow_url}).*\n"
        f"*Last checked: {timestamp}*"
    )


def write_multiline_output(path: Path, name: str, value: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{name}<<{name.upper()}_EOF\n")
        handle.write(value)
        handle.write(f"\n{name.upper()}_EOF\n")


def command_latest() -> int:
    output = Path(os.environ["GITHUB_OUTPUT"])
    with output.open("a", encoding="utf-8") as handle:
        for spec in TOOLS:
            version = latest_pypi_version(spec.package)
            value = version or "unknown"
            handle.write(f"{spec.latest_output}={value}\n")
            print(f"{spec.package}: {value}")
    return 0


def command_compare() -> int:
    # Current comes from the pin file unless a caller overrides it; latest comes from the
    # environment when the `latest` step exported it, otherwise straight from PyPI.
    current = {
        spec.name: os.getenv(spec.current_env) or CURRENT_BY_PACKAGE.get(spec.name, "")
        for spec in TOOLS
    }
    latest = {
        spec.name: os.getenv(spec.latest_env) or latest_pypi_version(spec.package) or "unknown"
        for spec in TOOLS
    }
    statuses = compare_versions(current, latest)
    report = render_report(statuses)
    updates = render_updates(statuses)
    has_updates = bool(updates)

    workflow_url = os.getenv("WORKFLOW_URL", "")
    timestamp = os.getenv("CHECK_TIMESTAMP", "")
    if not timestamp:
        timestamp = dt.datetime.now(tz=dt.UTC).isoformat()
    issue_body = render_issue_body(
        report=report,
        updates=updates,
        workflow_url=workflow_url,
        timestamp=timestamp,
    )

    Path("tool-version-report.md").write_text(report, encoding="utf-8")
    Path("tool-version-updates.md").write_text(updates, encoding="utf-8")
    Path("tool-version-issue-body.md").write_text(issue_body, encoding="utf-8")

    output = Path(os.environ["GITHUB_OUTPUT"])
    write_multiline_output(output, "report", report)
    if updates:
        write_multiline_output(output, "updates", updates)
    else:
        with output.open("a", encoding="utf-8") as handle:
            handle.write("updates=\n")
    with output.open("a", encoding="utf-8") as handle:
        handle.write(f"has_updates={'true' if has_updates else 'false'}\n")
    print(report)
    return 0


ROUTINE_WINDOW_WEEKDAY = 0  # Monday in ``datetime.weekday`` notation.


def should_propose_update(now: dt.datetime, *, security_override: bool) -> bool:
    """Return whether the canonical source lane may open or refresh its PR."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return security_override or now.astimezone(dt.UTC).weekday() == ROUTINE_WINDOW_WEEKDAY


def command_proposal_policy(at: str | None, *, security_override: bool) -> int:
    now = dt.datetime.fromisoformat(at.replace("Z", "+00:00")) if at else dt.datetime.now(dt.UTC)
    allowed = should_propose_update(now, security_override=security_override)
    if security_override:
        reason = "security_override"
    elif allowed:
        reason = "weekly_window"
    else:
        reason = "outside_weekly_window"
    print(f"should_propose={'true' if allowed else 'false'}")
    print(f"reason={reason}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("latest")
    subcommands.add_parser("compare")
    proposal_policy = subcommands.add_parser("proposal-policy")
    proposal_policy.add_argument("--security-override", action="store_true")
    proposal_policy.add_argument("--at", help="UTC ISO-8601 timestamp for deterministic checks")
    args = parser.parse_args(argv)
    if args.command == "proposal-policy":
        return command_proposal_policy(args.at, security_override=args.security_override)
    if args.command == "latest":
        return command_latest()
    if args.command == "compare":
        return command_compare()
    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
