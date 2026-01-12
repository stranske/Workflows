#!/usr/bin/env python3
"""Collect keepalive metrics logs and emit combined NDJSON + dashboard."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from scripts import keepalive_metrics_collector as collector
from scripts import keepalive_metrics_dashboard as dashboard

DEFAULT_METRICS_DIR = "keepalive-metrics"
DEFAULT_FILENAME = "keepalive-metrics.ndjson"
DEFAULT_OUTPUT_NDJSON = "keepalive-metrics.ndjson"
DEFAULT_OUTPUT_DASHBOARD = "keepalive-metrics-dashboard.md"
ENV_METRICS_DIR = "KEEPALIVE_METRICS_DIR"
ENV_REPOS = "KEEPALIVE_METRICS_REPOS"


def _parse_repo_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    text = raw.strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return [item.strip() for item in text.split(",") if item.strip()]
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


def _normalize_repo_slug(repo: str) -> str:
    return repo.strip().lower()


def _repo_aliases(repo: str) -> set[str]:
    normalized = _normalize_repo_slug(repo)
    if not normalized:
        return set()
    aliases = {normalized}
    if "/" in normalized:
        aliases.add(normalized.replace("/", "_"))
        aliases.add(normalized.replace("/", "-"))
        owner, name = normalized.split("/", 1)
        if owner and name:
            aliases.update({name, f"{owner}_{name}", f"{owner}-{name}"})
    return aliases


def _infer_repo_from_path(
    path: Path,
    metrics_dir: Path,
    repos: list[str],
) -> str | None:
    try:
        rel = path.relative_to(metrics_dir)
    except ValueError:
        rel = path
    parts = [part.lower() for part in rel.parts]
    if repos:
        for repo in repos:
            for alias in _repo_aliases(repo):
                if alias in parts:
                    return repo
    if parts:
        return parts[0]
    return None


def _read_ndjson(path: Path) -> tuple[list[dict[str, Any]], int]:
    entries: list[dict[str, Any]] = []
    errors = 0
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return entries, 1
    for line in content.splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            errors += 1
            continue
        if isinstance(parsed, dict):
            entries.append(parsed)
        else:
            errors += 1
    return entries, errors


def _load_records(
    files: list[Path],
    metrics_dir: Path,
    repos: list[str],
) -> tuple[list[dict[str, Any]], int, set[str]]:
    records: list[dict[str, Any]] = []
    errors = 0
    seen_repos: set[str] = set()
    for path in files:
        repo = _infer_repo_from_path(path, metrics_dir, repos)
        if repo:
            seen_repos.add(repo)
        entries, parse_errors = _read_ndjson(path)
        errors += parse_errors
        for entry in entries:
            if repo and "source_repo" not in entry:
                entry["source_repo"] = repo
            try:
                collector.validate_record(entry)
            except collector.ValidationError:
                errors += 1
                continue
            records.append(entry)
    return records, errors, seen_repos


def _write_ndjson(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            payload = json.dumps(record, separators=(",", ":"), sort_keys=True)
            handle.write(payload + "\n")


def _resolve_metrics_files(
    metrics_paths: list[str],
    metrics_dir: Path,
    filename: str,
) -> list[Path]:
    if metrics_paths:
        return [Path(path) for path in metrics_paths if path]
    if not metrics_dir.exists():
        return []
    return sorted(path for path in metrics_dir.rglob(filename) if path.is_file())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggregate keepalive metrics logs into NDJSON and markdown."
    )
    parser.add_argument(
        "--metrics-dir",
        default=None,
        help=(
            "Directory containing downloaded metrics logs "
            f"(default: {DEFAULT_METRICS_DIR} or ${ENV_METRICS_DIR})"
        ),
    )
    parser.add_argument(
        "--metrics-path",
        action="append",
        default=[],
        help="Explicit metrics NDJSON path (repeatable)",
    )
    parser.add_argument(
        "--filename",
        default=DEFAULT_FILENAME,
        help="Metrics filename to search for under metrics-dir",
    )
    parser.add_argument(
        "--repos",
        help=(
            "Comma-separated or JSON list of expected repos (enforced if provided; "
            f"default: ${ENV_REPOS})"
        ),
    )
    parser.add_argument(
        "--output-ndjson",
        default=DEFAULT_OUTPUT_NDJSON,
        help="Combined NDJSON output path",
    )
    parser.add_argument(
        "--output-dashboard",
        default=DEFAULT_OUTPUT_DASHBOARD,
        help="Markdown dashboard output path",
    )
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    raw_repos = args.repos or os.getenv(ENV_REPOS)
    repos = _parse_repo_list(raw_repos)
    metrics_dir_raw = args.metrics_dir or os.getenv(ENV_METRICS_DIR) or DEFAULT_METRICS_DIR
    metrics_dir = Path(metrics_dir_raw)
    files = _resolve_metrics_files(args.metrics_path, metrics_dir, args.filename)
    if not files:
        print("keepalive_metrics_report: no metrics files found", file=sys.stderr)
        return 1

    records, errors, seen_repos = _load_records(files, metrics_dir, repos)
    missing_repos = [repo for repo in repos if repo not in seen_repos]
    if missing_repos:
        errors += len(missing_repos)
        print(
            f"keepalive_metrics_report: missing repos: {', '.join(missing_repos)}",
            file=sys.stderr,
        )

    output_ndjson = Path(args.output_ndjson)
    _write_ndjson(output_ndjson, records)

    dashboard_output = dashboard.build_dashboard(records, errors)
    output_dashboard = Path(args.output_dashboard)
    output_dashboard.parent.mkdir(parents=True, exist_ok=True)
    output_dashboard.write_text(dashboard_output, encoding="utf-8")

    print(f"Wrote combined metrics to {output_ndjson}")
    print(f"Wrote keepalive dashboard to {output_dashboard}")
    if errors:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main(sys.argv[1:]))
