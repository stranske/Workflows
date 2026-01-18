#!/usr/bin/env python
"""Aggregate per-repo metrics NDJSON into org-level data."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from src import aggregator, cli_parser, ndjson_parser, percentile_calculator


def _read_ndjson(path: Path) -> tuple[list[dict[str, Any]], int]:
    entries, errors = ndjson_parser.read_ndjson_file(path)
    return entries, len(errors)


def read_repo_metrics(path: Path, repo: str) -> tuple[list[dict[str, Any]], int]:
    """Load a per-repo metrics log and tag entries with the repo name."""
    entries, errors = _read_ndjson(path)
    tagged: list[dict[str, Any]] = []
    for entry in entries:
        tagged_entry = dict(entry)
        tagged_entry["repo"] = repo
        tagged.append(tagged_entry)
    return tagged, errors


def _as_number(value: Any) -> float | None:
    return aggregator.as_number(value)


def _percentile(sorted_values: list[float], percentile: float) -> float | None:
    return percentile_calculator.percentile(sorted_values, percentile)


def summarize_values(values: list[float]) -> dict[str, float | None]:
    return percentile_calculator.summarize_values(values)


def aggregate_numeric_fields(
    entries: list[dict[str, Any]],
    fields: list[str],
) -> dict[str, dict[str, float | None]]:
    return aggregator.aggregate_numeric_fields(entries, fields)


def _infer_numeric_fields(entries: Iterable[dict[str, Any]]) -> list[str]:
    return aggregator.infer_numeric_fields(entries)


def _repo_slug(repo: str) -> str:
    return repo.replace("/", "__")


def _parse_repo_specs(
    repo_specs: Iterable[str],
    repos_csv: str | None,
    repos_file: Path | None,
    metrics_dir: Path,
) -> list[tuple[str, Path]]:
    repo_map: dict[str, Path] = {}

    for spec in repo_specs:
        if not spec:
            continue
        trimmed = spec.strip()
        if not trimmed:
            continue
        if "=" in trimmed:
            repo, path_text = trimmed.split("=", 1)
            repo = repo.strip()
            path_text = path_text.strip()
            if repo and path_text:
                repo_map.setdefault(repo, Path(path_text))
        else:
            repo = trimmed
            repo_map.setdefault(repo, metrics_dir / f"{_repo_slug(repo)}.ndjson")

    if repos_csv:
        for raw in repos_csv.split(","):
            repo = raw.strip()
            if repo:
                repo_map.setdefault(repo, metrics_dir / f"{_repo_slug(repo)}.ndjson")

    if repos_file:
        try:
            lines = repos_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for line in lines:
            repo = line.partition("#")[0].strip()
            if repo and not repo.startswith("#"):
                repo_map.setdefault(repo, metrics_dir / f"{_repo_slug(repo)}.ndjson")

    return list(repo_map.items())


def read_repo_metrics_files(
    repo_specs: Iterable[tuple[str, Path]],
) -> tuple[list[dict[str, Any]], int]:
    all_entries: list[dict[str, Any]] = []
    errors = 0
    for repo, path in repo_specs:
        entries, read_errors = read_repo_metrics(path, repo)
        all_entries.extend(entries)
        errors += read_errors
    return all_entries, errors


def _group_by_repo(
    entries: Iterable[dict[str, Any]],
    repo_names: Iterable[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    if repo_names:
        for repo in repo_names:
            grouped[str(repo)] = []
    for entry in entries:
        repo = entry.get("repo") or "unknown"
        repo_key = str(repo)
        grouped.setdefault(repo_key, []).append(entry)
    return grouped


def build_summary(
    entries: list[dict[str, Any]],
    errors: int,
    numeric_fields: list[str] | None = None,
    repo_names: Iterable[str] | None = None,
) -> dict[str, Any]:
    fields = numeric_fields or _infer_numeric_fields(entries)
    overall = aggregate_numeric_fields(entries, fields)
    comparisons = build_comparison_groups(entries, fields, repo_names=repo_names)
    repos_summary: dict[str, Any] = {}
    for repo, repo_entries in _group_by_repo(entries, repo_names=repo_names).items():
        repos_summary[repo] = {
            "count": len(repo_entries),
            "aggregates": aggregate_numeric_fields(repo_entries, fields),
        }
    return {
        "total_entries": len(entries),
        "parse_errors": errors,
        "numeric_fields": fields,
        "overall": {"count": len(entries), "aggregates": overall},
        "comparisons": comparisons,
        "repos": repos_summary,
    }


def build_comparison_groups(
    entries: list[dict[str, Any]],
    fields: list[str],
    repo_names: Iterable[str] | None = None,
) -> dict[str, Any]:
    grouped = _group_by_repo(entries, repo_names=repo_names)
    comparisons: dict[str, Any] = {}
    for field in fields:
        overall_values: list[float] = []
        per_repo: dict[str, Any] = {}
        for repo, repo_entries in grouped.items():
            values: list[float] = []
            for entry in repo_entries:
                value = _as_number(entry.get(field))
                if value is not None:
                    values.append(value)
            overall_values.extend(values)
            per_repo[repo] = {
                "count": len(values),
                "summary": summarize_values(values),
            }
        comparisons[field] = {
            "overall": summarize_values(overall_values),
            "repos": per_repo,
        }
    return comparisons


def write_combined_ndjson(path: Path, entries: Iterable[dict[str, Any]]) -> None:
    lines = [json.dumps(entry, sort_keys=True) for entry in entries]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    return cli_parser.build_parser()


def main(argv: list[str] | None = None) -> int:
    try:
        args = cli_parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    repo_specs = _parse_repo_specs(
        args.repo,
        args.repos,
        args.repos_file,
        args.metrics_dir,
    )
    if not repo_specs:
        print("aggregate_repo_metrics: no repos specified.", file=sys.stderr)
        return 1

    entries, errors = read_repo_metrics_files(repo_specs)
    numeric_fields = args.numeric_field or _infer_numeric_fields(entries)
    aggregated_entries = aggregator.build_grouped_aggregates(
        entries,
        numeric_fields,
        args.group_key,
    )
    write_combined_ndjson(args.output, [*entries, *aggregated_entries])
    repo_names = [repo for repo, _ in repo_specs]
    summary = build_summary(entries, errors, numeric_fields, repo_names=repo_names)
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote combined metrics to {args.output}")
    print(f"Wrote summary to {args.summary_output}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
