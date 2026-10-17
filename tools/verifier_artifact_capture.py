"""Verify retained raw artifact members before admitting them as native inputs.

Rendering limits do not establish raw capture. Every archive and occurrence is
verified independently; identical content never erases extraction accounting.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from pathlib import Path
from typing import Any

MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024
MAX_EXTRACT_BYTES = 64 * 1024 * 1024


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_artifact_capture(
    coverage: dict[str, Any], directory: Path
) -> tuple[dict[str, bytes], set[str]]:
    """Return complete raw inputs and exactly the artifact sources they recover.

    Digest-only filenames are source-owned; archive member names are never paths.
    Unknown/legacy inventories do not upgrade truncated capture.
    """
    inputs: dict[str, bytes] = {}
    recovered: set[str] = set()
    archives = coverage.get("artifact_capture_inventory", [])
    if not isinstance(archives, list) or len(archives) > 400:
        raise ValueError("artifact capture inventory malformed or over bound")
    seen: set[int] = set()
    downloaded = extracted = 0
    for archive in archives:
        if not isinstance(archive, dict):
            raise ValueError("artifact capture record malformed")
        if archive.get("status") != "captured":
            continue
        artifact = archive.get("artifact_id")
        run = archive.get("run_id")
        digest = archive.get("archive_sha256")
        if (
            type(artifact) is not int
            or artifact <= 0
            or artifact in seen
            or type(run) is not int
            or run <= 0
            or not isinstance(archive.get("name"), str)
            or not archive["name"].strip()
            or not isinstance(digest, str)
            or not re.fullmatch(r"[a-f0-9]{64}", digest)
            or not re.fullmatch(r"[a-f0-9]{40}", str(archive.get("head_sha", "")))
            or not re.fullmatch(r"[\w.-]+/[\w.-]+", str(archive.get("repository", "")))
        ):
            raise ValueError("artifact capture identity malformed or duplicate")
        seen.add(artifact)
        path = directory / f"{digest}.zip"
        if path.is_symlink() or path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("retained archive path or byte bound invalid")
        raw = path.read_bytes()
        downloaded += len(raw)
        if (
            type(archive.get("archive_bytes")) is not int
            or len(raw) != archive["archive_bytes"]
            or _digest(raw) != digest
            or downloaded > MAX_DOWNLOAD_BYTES
        ):
            raise ValueError("retained archive bytes do not match complete capture")
        members = archive.get("members")
        with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
            listed = [item for item in zipped.infolist() if not item.is_dir()]
            if (
                not isinstance(members, list)
                or not listed
                or len(listed) > 80
                or len(listed) != len(members)
                or archive.get("member_count") != len(listed)
                or archive.get("member_inventory_complete") is not True
            ):
                raise ValueError("retained member inventory incomplete")
            names = [item.filename for item in listed]
            if len(names) != len(set(names)):
                raise ValueError("retained archive has ambiguous duplicate members")
            for index, (item, member) in enumerate(zip(listed, members, strict=True)):
                if (
                    not isinstance(member, dict)
                    or member.get("name") != item.filename
                    or type(member.get("occurrence")) is not int
                    or member["occurrence"] != index
                    or member.get("status") not in {"included", "captured"}
                    or member.get("encoding") != "utf-8"
                    or type(member.get("raw_bytes")) is not int
                    or member["raw_bytes"] != item.file_size
                    or not re.fullmatch(r"[a-f0-9]{64}", str(member.get("raw_sha256", "")))
                ):
                    raise ValueError("retained member identity incomplete")
                extracted += item.file_size
                if extracted > MAX_EXTRACT_BYTES:
                    raise ValueError("retained extraction exceeds cumulative byte bound")
                value = zipped.read(item)  # CRC/read failure is fatal before providers.
                member_path = directory / f"{member['raw_sha256']}.txt"
                if member_path.is_symlink() or member_path.stat().st_size != len(value):
                    raise ValueError("retained member sidecar length differs")
                if (
                    member_path.read_bytes() != value
                    or _digest(value) != member["raw_sha256"]
                    or b"\0" in value
                ):
                    raise ValueError("retained member bytes differ")
                value.decode("utf-8", errors="strict")
                inputs[f"artifact:{run}:{artifact}:{index}"] = value
        recovered.add(f"Run {run}: {archive['name']}")
    return inputs, recovered


def load_artifact_capture(
    coverage: dict[str, Any], directory: Path
) -> tuple[dict[str, bytes], set[str]]:
    """Normalize malformed ZIP/encoding failures into a closed capture failure."""
    try:
        return _load_artifact_capture(coverage, directory)
    except (zipfile.BadZipFile, UnicodeError, KeyError) as exc:
        raise ValueError("retained artifact capture is malformed") from exc
