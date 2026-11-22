#!/usr/bin/env python3
"""Restore and verify the original module-identity evidence paths offline."""

import argparse
import hashlib
import json
import re
import sys
import tarfile
from pathlib import Path

PHASE = "module-identity-validation"
ARCHIVE = "module-identity-metadata.tar.gz"
GUIDE = "ARCHIVED-RECORDS.md"


def verify(name, data, digest, child):
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"SHA-256 mismatch: {name}")
    if name in child and (len(data), digest) != (child[name]["bytes"], child[name]["sha256"]):
        raise ValueError(f"Child manifest mismatch: {name}")
    return data


def restore(source, destination):
    parent = json.loads((source / "manifest.json").read_bytes())
    prefix = f"{PHASE}/"
    expected = {
        name.removeprefix(prefix): digest for name, digest in parent.items() if name.startswith(prefix)
    }
    if len(expected) != 70 or any(
        name in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9_.-]+", name) for name in expected
    ):
        raise ValueError("Unexpected parent manifest inventory")

    loose = source / PHASE
    manifest = loose / "manifest.json"
    if manifest.is_symlink():
        raise ValueError("Child manifest must be a regular file")
    manifest_data = verify(manifest.name, manifest.read_bytes(), expected[manifest.name], {})
    child = json.loads(manifest_data)
    if len(expected.keys() & child.keys()) != 68:
        raise ValueError("Unexpected child manifest inventory")

    files = {}
    for path in loose.iterdir():
        if path.name == GUIDE:
            continue
        if path.is_symlink() or not path.is_file() or path.name not in expected:
            raise ValueError(f"Unexpected loose path: {path.name}")
        data = manifest_data if path == manifest else path.read_bytes()
        files[path.name] = verify(path.name, data, expected[path.name], child)

    archived = 0
    with tarfile.open(source / ARCHIVE, "r:gz") as archive:
        for member in archive:
            name = member.name
            if not member.isfile() or name not in expected or name not in child or name in files:
                raise ValueError(f"Unexpected or duplicate archive member: {name}")
            if member.size != child[name]["bytes"]:
                raise ValueError(f"Archive size mismatch: {name}")
            with archive.extractfile(member) as handle:
                files[name] = verify(name, handle.read(), expected[name], child)
            archived += 1

    missing = expected.keys() - files.keys()
    if missing:
        raise ValueError(f"Missing original paths: {', '.join(sorted(missing))}")
    if archived != 29:
        raise ValueError(f"Expected 29 archived records, found {archived}")

    destination.mkdir()
    for name, data in files.items():
        (destination / name).write_bytes(data)
    print("Restored 70 original paths and SHA-256 digests (68 also checked against sizes and digests in the child manifest).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="new output directory with an existing parent")
    args = parser.parse_args()
    try:
        restore(Path(__file__).resolve().parent, args.destination)
    except (OSError, EOFError, ValueError, KeyError, TypeError, tarfile.TarError) as error:
        print(f"Recovery failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
