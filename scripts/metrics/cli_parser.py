"""CLI parser for repository metrics aggregation."""

from __future__ import annotations

import argparse
from pathlib import Path


def _existing_file(value: str) -> Path:
    path = Path(value)
    if not path.exists():
        raise argparse.ArgumentTypeError(f"File not found: {path}")
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"Not a file: {path}")
    return path


def _existing_dir(value: str) -> Path:
    path = Path(value)
    if not path.exists():
        raise argparse.ArgumentTypeError(f"Directory not found: {path}")
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"Not a directory: {path}")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate per-repo metrics NDJSON into org-level data and "
            "emit combined NDJSON plus summary JSON."
        )
    )
    parser.add_argument(
        "--repo",
        action="append",
        default=[],
        help="Repo spec owner/name=path or owner/name (uses --metrics-dir).",
    )
    parser.add_argument("--repos", help="Comma-separated list of repos (owner/name).")
    parser.add_argument(
        "--repos-file",
        type=_existing_file,
        help="Path to a file listing repos (one per line, # comments allowed).",
    )
    parser.add_argument(
        "--metrics-dir",
        type=_existing_dir,
        default=Path("repo-metrics"),
        help="Directory containing per-repo NDJSON named owner__repo.ndjson.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("combined-repo-metrics.ndjson"),
        help="Combined NDJSON output path.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path("repo-metrics-summary.json"),
        help="Summary JSON output path.",
    )
    parser.add_argument(
        "--numeric-field",
        action="append",
        default=[],
        help="Numeric field to aggregate (repeatable).",
    )
    parser.add_argument(
        "--group-key",
        action="append",
        default=["metric_name", "workflow", "dimension"],
        help="Entry field to group on for aggregated output (repeatable).",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not (args.repo or args.repos or args.repos_file):
        parser.error("At least one of --repo, --repos, or --repos-file is required.")

    return args
