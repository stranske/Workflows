#!/usr/bin/env python3
"""Download keepalive metrics artifacts from consumer repositories."""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path
from typing import Any

from scripts import api_client

DEFAULT_ARTIFACT_NAME = "keepalive-metrics"
DEFAULT_FILENAME = "keepalive-metrics.ndjson"
DEFAULT_METRICS_DIR = "keepalive-metrics"


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


def _apply_repo_filter(repos: list[str], raw_filter: str | None) -> list[str]:
    filters = _parse_repo_list(raw_filter)
    if not filters:
        return repos
    normalized = {_normalize_repo_slug(repo) for repo in filters}
    return [repo for repo in repos if _normalize_repo_slug(repo) in normalized]


def _artifact_sort_key(artifact: dict[str, Any]) -> str:
    return str(artifact.get("created_at") or artifact.get("updated_at") or "")


def _select_artifacts(
    artifacts: list[dict[str, Any]],
    artifact_name: str,
    max_per_repo: int,
) -> list[dict[str, Any]]:
    if max_per_repo <= 0:
        return []
    filtered = [
        artifact
        for artifact in artifacts
        if not artifact.get("expired") and str(artifact.get("name") or "") == artifact_name
    ]
    filtered.sort(key=_artifact_sort_key, reverse=True)
    return filtered[:max_per_repo]


def _list_artifacts(
    repo: str,
    token: str,
    *,
    per_page: int,
    max_pages: int,
    retry_attempts: int,
    retry_backoff: float,
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    page = 1
    while page <= max_pages:
        payload = api_client.fetch_artifacts_page(
            repo,
            token,
            page=page,
            per_page=per_page,
            retry_attempts=retry_attempts,
            retry_backoff=retry_backoff,
        )
        items = payload.get("artifacts")
        if not isinstance(items, list):
            break
        artifacts.extend(item for item in items if isinstance(item, dict))
        if len(items) < per_page:
            break
        page += 1
    return artifacts


def _extract_metrics_zip(zip_path: Path, output_dir: Path, filename: str) -> bool:
    if not zip_path.exists():
        return False
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if Path(info.filename).name != filename:
                continue
            output_dir.mkdir(parents=True, exist_ok=True)
            destination = output_dir / filename
            with archive.open(info) as source, destination.open("wb") as target:
                target.write(source.read())
            return True
    return False


def _download_metrics_artifact(
    repo: str,
    token: str,
    artifact: dict[str, Any],
    *,
    output_dir: Path,
    filename: str,
    retry_attempts: int,
    retry_backoff: float,
) -> bool:
    artifact_id = artifact.get("id")
    if not isinstance(artifact_id, int):
        return False
    zip_path = output_dir / f"{artifact_id}.zip"
    api_client.download_artifact_zip(
        repo,
        artifact_id,
        token,
        zip_path,
        retry_attempts=retry_attempts,
        retry_backoff=retry_backoff,
    )
    extracted = _extract_metrics_zip(zip_path, output_dir, filename)
    return extracted


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download keepalive metrics artifacts from consumer repositories."
    )
    parser.add_argument(
        "--repos",
        help="Comma-separated or JSON list of repos to collect.",
    )
    parser.add_argument(
        "--repo-filter",
        help="Optional comma-separated or JSON list to limit repos.",
    )
    parser.add_argument(
        "--artifact-name",
        default=DEFAULT_ARTIFACT_NAME,
        help="Artifact name to download.",
    )
    parser.add_argument(
        "--filename",
        default=DEFAULT_FILENAME,
        help="Metrics filename expected inside the artifact.",
    )
    parser.add_argument(
        "--metrics-dir",
        default=DEFAULT_METRICS_DIR,
        help="Root directory for downloaded metrics.",
    )
    parser.add_argument(
        "--max-per-repo",
        type=int,
        default=1,
        help="Maximum artifacts to download per repo.",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=100,
        help="Artifacts page size when querying GitHub.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Maximum pages to query per repo.",
    )
    parser.add_argument(
        "--retry-attempts",
        type=int,
        default=5,
        help="Maximum API retry attempts.",
    )
    parser.add_argument(
        "--retry-backoff",
        type=float,
        default=1.0,
        help="Base backoff seconds for API retries.",
    )
    parser.add_argument(
        "--token-env",
        default="GITHUB_TOKEN",
        help="Environment variable containing the GitHub token.",
    )
    parser.add_argument(
        "--token",
        help="GitHub token override (discouraged; prefer token-env).",
    )
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    raw_repos = args.repos or os.getenv("KEEPALIVE_METRICS_REPOS")
    repos = _parse_repo_list(raw_repos)
    if not repos:
        print("keepalive_metrics_fetch: no repos provided", file=sys.stderr)
        return 1

    repo_filter = args.repo_filter or os.getenv("KEEPALIVE_METRICS_REPO_FILTER")
    repos = _apply_repo_filter(repos, repo_filter)
    if not repos:
        print("keepalive_metrics_fetch: repo filter matched no repos", file=sys.stderr)
        return 1

    token = args.token or os.getenv(args.token_env)
    if not token:
        print(
            f"keepalive_metrics_fetch: missing token in {args.token_env}",
            file=sys.stderr,
        )
        return 1

    metrics_root = Path(args.metrics_dir)
    errors = 0
    for repo in repos:
        artifacts = _list_artifacts(
            repo,
            token,
            per_page=args.per_page,
            max_pages=args.max_pages,
            retry_attempts=args.retry_attempts,
            retry_backoff=args.retry_backoff,
        )
        selected = _select_artifacts(artifacts, args.artifact_name, args.max_per_repo)
        if not selected:
            errors += 1
            print(f"keepalive_metrics_fetch: no artifacts found for {repo}", file=sys.stderr)
            continue

        for artifact in selected:
            artifact_id = artifact.get("id")
            repo_dir = metrics_root / _normalize_repo_slug(repo) / str(artifact_id)
            try:
                extracted = _download_metrics_artifact(
                    repo,
                    token,
                    artifact,
                    output_dir=repo_dir,
                    filename=args.filename,
                    retry_attempts=args.retry_attempts,
                    retry_backoff=args.retry_backoff,
                )
            except RuntimeError as exc:
                errors += 1
                print(
                    f"keepalive_metrics_fetch: failed to download {repo} artifact: {exc}",
                    file=sys.stderr,
                )
                continue
            if not extracted:
                errors += 1
                print(
                    f"keepalive_metrics_fetch: missing {args.filename} in {repo}",
                    file=sys.stderr,
                )
                continue
            print(f"Fetched {repo} artifact {artifact_id} into {repo_dir}")

    return 1 if errors else 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main(sys.argv[1:]))
