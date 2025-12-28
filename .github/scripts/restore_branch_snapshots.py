from __future__ import annotations

import os
import sys
import tempfile
import zipfile
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import requests


@dataclass(slots=True)
class Artifact:
    id: int
    name: str
    created_at: str
    expired: bool
    workflow_run_id: int | None


class RestoreError(RuntimeError):
    pass


def _iter_artifacts(response: dict) -> Iterator[Artifact]:
    artifacts = response.get("artifacts")
    if not isinstance(artifacts, Sequence):
        return iter(())
    converted: list[Artifact] = []
    for entry in artifacts:
        if not isinstance(entry, dict):
            continue
        try:
            art_id = int(entry.get("id"))
        except (TypeError, ValueError):
            continue
        name = str(entry.get("name", ""))
        created_at = str(entry.get("created_at", ""))
        expired = bool(entry.get("expired"))
        workflow_run = entry.get("workflow_run")
        if isinstance(workflow_run, dict):
            run_id_raw = workflow_run.get("id")
            try:
                workflow_run_id = int(run_id_raw) if run_id_raw is not None else None
            except (TypeError, ValueError):
                workflow_run_id = None
        else:
            workflow_run_id = None
        converted.append(
            Artifact(
                id=art_id,
                name=name,
                created_at=created_at,
                expired=expired,
                workflow_run_id=workflow_run_id,
            )
        )
    return iter(converted)


def _collect_artifacts(session: requests.Session, repo: str, token: str) -> list[Artifact]:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "trend-model-scripts",
    }
    url = f"https://api.github.com/repos/{repo}/actions/artifacts?per_page=100"
    results: list[Artifact] = []

    while url:
        response = session.get(url, headers=headers, timeout=30)
        if response.status_code != 200:
            raise RestoreError(
                f"Failed to list artifacts (status {response.status_code}): {response.text[:200]}"
            )
        data = response.json()
        results.extend(list(_iter_artifacts(data)))
        next_link = response.links.get("next", {}).get("url")
        url = next_link

    return results


def _select_latest(
    artifacts: Iterable[Artifact], prefix: str, current_run_id: str | None
) -> Artifact | None:
    cleaned_run = str(current_run_id) if current_run_id else ""
    filtered = [
        art
        for art in artifacts
        if not art.expired
        and art.name.startswith(prefix)
        and (not cleaned_run or str(art.workflow_run_id) != cleaned_run)
    ]
    if not filtered:
        return None
    return max(filtered, key=lambda item: item.created_at)


def _download_artifact(
    session: requests.Session,
    repo: str,
    token: str,
    artifact_id: int,
    destination: Path,
) -> None:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "trend-model-scripts",
    }
    url = f"https://api.github.com/repos/{repo}/actions/artifacts/{artifact_id}/zip"
    response = session.get(url, headers=headers, timeout=60, stream=True)
    if response.status_code != 200:
        raise RestoreError(
            f"Failed to download artifact {artifact_id} (status {response.status_code})"
        )
    with destination.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=65536):
            if chunk:
                handle.write(chunk)


def _extract_zip(archive: Path, target_dir: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(target_dir)


def _copy_json(source_dir: Path, destination_dir: Path) -> None:
    destination_dir.mkdir(parents=True, exist_ok=True)
    copied = False
    for path in source_dir.glob("*.json"):
        if path.is_file():
            target = destination_dir / path.name
            target.write_bytes(path.read_bytes())
            copied = True
    if not copied:
        raise RestoreError(f"Artifact directory {source_dir} did not contain JSON snapshots")


def restore_previous_snapshots(
    *,
    repo: str,
    token: str,
    snapshot_dir: Path,
    run_id: str | None,
) -> bool:
    session = requests.Session()
    artifacts = _collect_artifacts(session, repo, token)
    prefix = f"{snapshot_dir.name}-"
    candidate = _select_latest(artifacts, prefix, run_id)
    if candidate is None:
        return False

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        archive = tmpdir / "artifact.zip"
        _download_artifact(session, repo, token, candidate.id, archive)
        unpacked = tmpdir / "unpacked"
        unpacked.mkdir(parents=True, exist_ok=True)
        _extract_zip(archive, unpacked)
        source_dir = unpacked / snapshot_dir.name
        if not source_dir.exists():
            raise RestoreError(f"Artifact did not contain {snapshot_dir.name}")
        previous_dir = snapshot_dir / "previous"
        for old in previous_dir.glob("*.json"):
            old.unlink(missing_ok=True)
        _copy_json(source_dir, previous_dir)
    return True


def main() -> int:
    snapshot_dir = Path(os.environ.get("SNAPSHOT_DIR", "gate-branch-protection"))
    repo = os.environ.get("TARGET_REPO") or os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    run_id = os.environ.get("TARGET_RUN_ID") or os.environ.get("GITHUB_RUN_ID")

    if not repo or not token:
        print("[summary] Missing repository or token; skipping restore", flush=True)
        return 0

    try:
        restored = restore_previous_snapshots(
            repo=repo,
            token=token,
            snapshot_dir=snapshot_dir,
            run_id=run_id,
        )
    except RestoreError as exc:
        print(f"[summary] Snapshot restore failed: {exc}", flush=True)
        return 0
    except requests.RequestException as exc:
        print(f"[summary] Snapshot restore request error: {exc}", flush=True)
        return 0

    if restored:
        print(
            f"[summary] Restored previous snapshots into {snapshot_dir / 'previous'}",
            flush=True,
        )
    else:
        print("[summary] No previous artifact found", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
