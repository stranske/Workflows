"""Offline full-capture resource accounting; never authorizes provider execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

from tools.verifier_capture_obligation_manifest import (
    _unique_object,
    build_capture_byte_inventory,
    build_capture_obligation_manifest,
    build_capture_reassembly_contract,
)

SCHEMA = "workflows-verifier-proof-resource-plan/v1"
# Same cumulative default as agents_verifier_context.js, across ALL archives.
TOTAL_EXTRACT_BYTES = 64 * 1024 * 1024
MAX_ARCHIVES = 100
MAX_MEMBERS = 4096


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_resource_plan(
    inputs: dict[str, bytes],
    expected_archives: list[dict[str, Any]],
    archive_paths: dict[int, Path],
    metadata_paths: dict[int, Path],
) -> dict[str, Any]:
    """Bind a complete frozen archive inventory before any member extraction.

    Expected records come from the caller's retained authenticated inventory;
    this offline function checks bindings, not GitHub authentication. Each record
    names artifact_id, repository, run_id, head_sha, metadata_sha256,
    archive_sha256 and archive_bytes. Retained metadata must match both its hash
    and those identities. These checks do not replace authenticated collection.
    No subset selection or per-package extraction counter exists. ZIP metadata
    supplies required raw bytes, not evidence of successful extraction/CRC checks.
    Even a small, gap-free capture stays diagnostic until semantic closure and
    exact native request/result admission are implemented independently.
    """
    if set(inputs) not in ({"context"}, {"context", "diff"}):
        raise ValueError("resource plan requires the complete context/diff input set")
    if not isinstance(expected_archives, list) or len(expected_archives) > MAX_ARCHIVES:
        raise ValueError("archive inventory exceeds finite bound or is malformed")
    records: dict[int, dict[str, Any]] = {}
    for record in expected_archives:
        if not isinstance(record, dict):
            raise ValueError("malformed archive identity")
        artifact = record.get("artifact_id")
        if type(artifact) is not int or artifact <= 0 or artifact in records:
            raise ValueError("duplicate or malformed artifact identity")
        if type(record.get("run_id")) is not int or record["run_id"] <= 0:
            raise ValueError("malformed run identity")
        repository = record.get("repository")
        if (
            not isinstance(repository, str)
            or len(repository.split("/")) != 2
            or not all(repository.split("/"))
        ):
            raise ValueError("malformed repository identity")
        for field, size in (("head_sha", 40), ("archive_sha256", 64), ("metadata_sha256", 64)):
            value = record.get(field)
            if (
                not isinstance(value, str)
                or len(value) != size
                or any(c not in "0123456789abcdef" for c in value)
            ):
                raise ValueError(f"malformed {field}")
        if type(record.get("archive_bytes")) is not int or record["archive_bytes"] < 0:
            raise ValueError("malformed archive byte count")
        records[artifact] = record
    if any(type(key) is not int for key in archive_paths) or set(archive_paths) != set(records):
        raise ValueError("archive paths do not cover the exact expected inventory")
    if any(type(key) is not int for key in metadata_paths) or set(metadata_paths) != set(records):
        raise ValueError("metadata paths do not cover the exact expected inventory")
    inventory = build_capture_byte_inventory(inputs)
    manifest = build_capture_obligation_manifest(
        inputs["context"].decode("utf-8"), full_diff_bytes=inputs.get("diff")
    )
    contract = build_capture_reassembly_contract(manifest, inventory)
    archives = []
    occurrences: list[dict[str, Any]] = []
    required_bytes = 0
    for artifact, record in sorted(records.items()):
        path = Path(archive_paths[artifact])
        metadata_bytes = Path(metadata_paths[artifact]).read_bytes()
        if hashlib.sha256(metadata_bytes).hexdigest() != record["metadata_sha256"]:
            raise ValueError(f"archive {artifact} metadata differs from frozen inventory")
        metadata = json.loads(metadata_bytes, object_pairs_hook=_unique_object)
        if (
            not isinstance(metadata, dict)
            or type(metadata.get("id")) is not int
            or metadata.get("id") != artifact
            or metadata.get("url")
            != f"https://api.github.com/repos/{record['repository']}/actions/artifacts/{artifact}"
            or not isinstance(metadata.get("workflow_run"), dict)
            or type(metadata["workflow_run"].get("id")) is not int
            or metadata["workflow_run"].get("id") != record["run_id"]
            or metadata["workflow_run"].get("head_sha") != record["head_sha"]
            or metadata.get("digest") != f"sha256:{record['archive_sha256']}"
            or metadata.get("size_in_bytes") != record["archive_bytes"]
            or type(metadata.get("size_in_bytes")) is not int
        ):
            raise ValueError(f"archive {artifact} provenance does not match frozen identities")
        if (
            path.stat().st_size != record["archive_bytes"]
            or _sha256(path) != record["archive_sha256"]
        ):
            raise ValueError(f"archive {artifact} bytes differ from frozen inventory")
        # Reading the central directory does not decompress or render any member.
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len(occurrences) + len(members) > MAX_MEMBERS:
                raise ValueError("complete member inventory exceeds finite metadata bound")
            for index, member in enumerate(members):
                identity = {"artifact": record, "listing_index": index, "name": member.filename}
                required_bytes += member.file_size
                occurrences.append(
                    {
                        "id": _digest(identity),
                        "artifact_id": artifact,
                        "listing_index": index,
                        "name": member.filename,
                        "raw_bytes": member.file_size,
                        "compressed_bytes": member.compress_size,
                        "crc32": member.CRC,
                        "directory": member.is_dir(),
                        "content_sha256": None,
                        "content_status": "not-extracted",
                    }
                )
        archives.append(dict(record))
    blockers = [
        "semantic-dependency-closure-unproven",
        "native-capacity-and-result-matrix-unproven",
    ]
    if required_bytes > TOTAL_EXTRACT_BYTES:
        blockers.insert(0, "global-extraction-bound")
    if not manifest["sufficient"]:
        blockers.append("original-capture-insufficient")
    plan = {
        "schema": SCHEMA,
        "capture_reassembly_contract": contract,
        "expected_archives_sha256": _digest(expected_archives),
        "archives": archives,
        "member_occurrences": occurrences,
        "required_extraction_bytes": required_bytes,
        "global_extraction_limit_bytes": TOTAL_EXTRACT_BYTES,
        "extracted_bytes": 0,
        "rendered_bytes": 0,
        "provider_calls": 0,
        "dependency_policy": "all-captured-inputs-and-all-archive-occurrences",
        "semantic_packages": [],
        "admitted": False,
        "blockers": blockers,
    }
    return {"id": _digest(plan), **plan}


def validate_resource_plan(
    plan: Any,
    inputs: dict[str, bytes],
    expected_archives: list[dict[str, Any]],
    archive_paths: dict[int, Path],
    metadata_paths: dict[int, Path],
) -> None:
    """Reject omitted occurrences, modified provenance/gaps, or promoted admission."""
    expected = build_resource_plan(inputs, expected_archives, archive_paths, metadata_paths)
    if json.dumps(plan, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError("resource plan differs from the full frozen capture")


def main() -> int:
    """Write a diagnostic plan without altering capture or invoking a provider."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--diff", type=Path)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    packet = json.loads(args.inventory.read_bytes(), object_pairs_hook=_unique_object)
    inputs = {"context": args.context.read_bytes()}
    if args.diff is not None:
        inputs["diff"] = args.diff.read_bytes()
    plan = build_resource_plan(
        inputs,
        packet["expected_archives"],
        {int(key): Path(value) for key, value in packet["archive_paths"].items()},
        {int(key): Path(value) for key, value in packet["metadata_paths"].items()},
    )
    # Refuse replacement of an input or an existing historical receipt.
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(plan, indent=2) + "\n")
    print(json.dumps({"id": plan["id"], "admitted": False, "blockers": plan["blockers"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
