#!/usr/bin/env python3
"""Stage the fleet artifacts maint-80 already downloaded for the conformance report.

maint-80 (LangSmith Metrics Dashboard) extracts each registered repo's fleet
artifact under ``<extracted-root>/<owner>_<repo>/``. The conformance report
(``scripts/langsmith_fleet_conformance.py``) reads
``<records-root>/<owner>__<repo>/<artifact_name>``. This copies the first file
named ``artifact_name`` (top level first, then the shallowest match) into that
layout, which is what the retired maint-81 did after its own second download.
Folding the step into maint-80 means the fleet artifacts are fetched once a
week instead of twice (cohesion review B14).

Prints one line per artifact-backed registry entry: ``staged`` or ``missing``.
A missing entry is left absent so the conformance report marks it missing.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def extracted_dir_name(repo: str) -> str:
    """maint-80's download directory name for a repo (``owner/repo`` -> ``owner_repo``)."""
    return repo.replace("/", "_")


def records_dir_name(repo: str) -> str:
    """The conformance report's directory name for a repo (``owner/repo`` -> ``owner__repo``)."""
    owner, name = repo.split("/", 1)
    return f"{owner}__{name}"


def find_artifact_file(repo_dir: Path, artifact_name: str) -> Path | None:
    if not repo_dir.is_dir():
        return None
    direct = repo_dir / artifact_name
    if direct.is_file():
        return direct
    matches = sorted(
        (path for path in repo_dir.rglob(artifact_name) if path.is_file()),
        key=lambda path: (len(path.relative_to(repo_dir).parts), str(path)),
    )
    return matches[0] if matches else None


def stage_records(registry: dict, extracted_root: Path, records_root: Path) -> dict[str, str]:
    outcome: dict[str, str] = {}
    for entry in registry.get("repos", []):
        if not isinstance(entry, dict):
            continue
        if (entry.get("evidence_mode") or "artifact") != "artifact":
            continue
        repo = str(entry.get("repo") or "")
        artifact_name = str(entry.get("artifact_name") or "langsmith-fleet.ndjson")
        if "/" not in repo:
            continue
        source = find_artifact_file(extracted_root / extracted_dir_name(repo), artifact_name)
        if source is None:
            outcome[repo] = "missing"
            continue
        target = records_root / records_dir_name(repo) / artifact_name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        outcome[repo] = "staged"
    return outcome


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry", type=Path, default=Path("config/langsmith_fleet_registry.json")
    )
    parser.add_argument("--extracted-root", type=Path, required=True)
    parser.add_argument("--records-root", type=Path, required=True)
    args = parser.parse_args(argv)
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    args.records_root.mkdir(parents=True, exist_ok=True)
    for repo, state in stage_records(registry, args.extracted_root, args.records_root).items():
        print(f"{state}\t{repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
