#!/usr/bin/env python3
"""Helpers for maint-50 tool version reporting."""

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


TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "black",
        "black",
        "black_current",
        "black_latest",
        "BLACK_CURRENT",
        "BLACK_LATEST",
    ),
    ToolSpec(
        "coverage",
        "coverage",
        "coverage_current",
        "coverage_latest",
        "COVERAGE_CURRENT",
        "COVERAGE_LATEST",
    ),
    ToolSpec(
        "docformatter",
        "docformatter",
        "docformatter_current",
        "docformatter_latest",
        "DOCFORMATTER_CURRENT",
        "DOCFORMATTER_LATEST",
    ),
    ToolSpec(
        "isort",
        "isort",
        "isort_current",
        "isort_latest",
        "ISORT_CURRENT",
        "ISORT_LATEST",
    ),
    ToolSpec(
        "mypy",
        "mypy",
        "mypy_current",
        "mypy_latest",
        "MYPY_CURRENT",
        "MYPY_LATEST",
    ),
    ToolSpec(
        "pytest",
        "pytest",
        "pytest_current",
        "pytest_latest",
        "PYTEST_CURRENT",
        "PYTEST_LATEST",
    ),
    ToolSpec(
        "pytest-cov",
        "pytest-cov",
        "pytest_cov_current",
        "pytest_cov_latest",
        "PYTEST_COV_CURRENT",
        "PYTEST_COV_LATEST",
    ),
    ToolSpec(
        "ruff",
        "ruff",
        "ruff_current",
        "ruff_latest",
        "RUFF_CURRENT",
        "RUFF_LATEST",
    ),
)

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
            'pip install "black==$BLACK_VERSION" "ruff==$RUFF_VERSION" '
            '"isort==$ISORT_VERSION" "docformatter==$DOCFORMATTER_VERSION" '
            '"mypy==$MYPY_VERSION" "pytest==$PYTEST_VERSION" '
            '"pytest-cov==$PYTEST_COV_VERSION" "coverage==$COVERAGE_VERSION"',
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
    current = {spec.name: os.getenv(spec.current_env, "") for spec in TOOLS}
    latest = {spec.name: os.getenv(spec.latest_env, "") for spec in TOOLS}
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("latest")
    subcommands.add_parser("compare")
    args = parser.parse_args(argv)
    if args.command == "latest":
        return command_latest()
    if args.command == "compare":
        return command_compare()
    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
