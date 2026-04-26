#!/usr/bin/env python3
"""Emit a machine-readable freshness report for the pinned Codex CLI."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SCHEMA = "workflows-codex-cli-freshness/v1"
DEFAULT_PACKAGE = "@openai/codex"
DEFAULT_WORKFLOW_PATH = ".github/workflows/reusable-agents-verifier.yml"
DEFAULT_OUTPUT_JSON = "codex-cli-freshness.json"
DEFAULT_OUTPUT_MD = "codex-cli-freshness.md"
DEFAULT_OUTPUT_NDJSON = "codex-cli-freshness.ndjson"


def _utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_semver(value: str) -> tuple[int, int, int] | None:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", value.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def _version_text(value: str) -> str:
    match = re.search(r"(\d+\.\d+\.\d+(?:[-+][A-Za-z0-9._-]+)?)", value.strip())
    return match.group(1) if match else value.strip()


def extract_pinned_cli_version(workflow_path: Path, package: str = DEFAULT_PACKAGE) -> str:
    content = workflow_path.read_text(encoding="utf-8")
    escaped = re.escape(package)
    match = re.search(rf"{escaped}@([0-9]+\.[0-9]+\.[0-9]+)", content)
    if not match:
        raise ValueError(f"Could not find an explicit {package} version pin in {workflow_path}")
    return match.group(1)


def query_latest_npm_version(package: str = DEFAULT_PACKAGE, timeout: int = 30) -> tuple[str, str]:
    command = ["npm", "view", package, "version", "--silent"]
    try:
        with tempfile.TemporaryDirectory(prefix="codex-cli-freshness-npm-") as cache_dir:
            env = os.environ.copy()
            env["NPM_CONFIG_CACHE"] = cache_dir
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
    except (OSError, subprocess.SubprocessError) as exc:
        return "", f"npm-query-failed: {exc}"
    latest = _version_text(completed.stdout)
    if not latest:
        return "", "npm-query-empty"
    return latest, ""


def _version_delta(
    pinned: tuple[int, int, int] | None, latest: tuple[int, int, int] | None
) -> dict[str, int] | None:
    if pinned is None or latest is None:
        return None
    return {
        "major": max(0, latest[0] - pinned[0]),
        "minor": max(0, latest[1] - pinned[1]) if latest[0] == pinned[0] else latest[1],
        "patch": max(0, latest[2] - pinned[2]) if latest[:2] == pinned[:2] else latest[2],
    }


def build_contract(
    *,
    pinned_version: str,
    latest_version: str,
    workflow_path: str = DEFAULT_WORKFLOW_PATH,
    package: str = DEFAULT_PACKAGE,
    query_error: str = "",
    generated_at: str | None = None,
) -> dict[str, Any]:
    pinned_version = _version_text(pinned_version)
    latest_version = _version_text(latest_version) if latest_version else ""
    pinned_tuple = parse_semver(pinned_version)
    latest_tuple = parse_semver(latest_version) if latest_version else None
    status = "unknown"
    if pinned_tuple is None:
        status = "invalid-pinned-version"
    elif query_error or latest_tuple is None:
        status = "latest-unavailable"
    elif latest_tuple > pinned_tuple:
        status = "outdated"
    else:
        status = "current"

    return {
        "schema": SCHEMA,
        "generated_at": generated_at or _utc_now(),
        "package": package,
        "component": "agents-verifier",
        "status": status,
        "pinned_version": pinned_version,
        "latest_version": latest_version,
        "query_error": query_error,
        "version_delta": _version_delta(pinned_tuple, latest_tuple),
        "source": {
            "workflow": workflow_path,
            "install_step": "Install Codex CLI",
        },
        "update_targets": [
            {
                "path": workflow_path,
                "reason": "Advance the pinned verifier Codex CLI install.",
            },
            {
                "path": "tests/workflows/test_verifier_terminal_disposition.py",
                "reason": "Keep model-to-minimum-CLI compatibility reviewed.",
            },
        ],
    }


def format_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Codex CLI Freshness",
        "",
        f"- Schema: {report['schema']}",
        f"- Component: {report['component']}",
        f"- Package: `{report['package']}`",
        f"- Status: {report['status']}",
        f"- Pinned version: {report['pinned_version'] or 'unknown'}",
        f"- Latest version: {report['latest_version'] or 'unknown'}",
    ]
    if report.get("query_error"):
        lines.append(f"- Query error: {report['query_error']}")
    delta = report.get("version_delta")
    if isinstance(delta, dict):
        lines.append(
            "- Version delta: "
            f"major {delta['major']}, minor {delta['minor']}, patch {delta['patch']}"
        )
    lines.extend(
        [
            "",
            "## Update Path",
            f"- Update `{report['source']['workflow']}` in the Install Codex CLI step.",
            "- Re-run the verifier terminal disposition contract tests.",
        ]
    )
    latest = report.get("latest_version")
    if latest:
        lines.append(f"- Target install pin: `{report['package']}@{latest}`")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-path", default=DEFAULT_WORKFLOW_PATH)
    parser.add_argument("--package", default=DEFAULT_PACKAGE)
    parser.add_argument("--latest-version", default="")
    parser.add_argument("--output-json", default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--output-ndjson", default=DEFAULT_OUTPUT_NDJSON)
    parser.add_argument("--fail-when-outdated", action="store_true")
    parser.add_argument("--npm-timeout", type=int, default=30)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    workflow_path = Path(args.workflow_path)
    try:
        pinned_version = extract_pinned_cli_version(workflow_path, args.package)
    except (OSError, ValueError) as exc:
        pinned_version = ""
        latest_version = args.latest_version.strip()
        query_error = f"pin-read-failed: {exc}"
    else:
        latest_version = args.latest_version.strip()
        query_error = ""
        if not latest_version:
            latest_version, query_error = query_latest_npm_version(args.package, args.npm_timeout)

    report = build_contract(
        pinned_version=pinned_version,
        latest_version=latest_version,
        workflow_path=args.workflow_path,
        package=args.package,
        query_error=query_error,
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_ndjson = Path(args.output_ndjson)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_ndjson.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output_md.write_text(format_markdown(report), encoding="utf-8")
    output_ndjson.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.fail_when_outdated and report["status"] == "outdated":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
