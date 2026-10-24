"""Authenticate bounded gzip-text evidence views without rewriting Git patches."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import zlib
from pathlib import Path
from typing import Any

SCHEMA = "verifier-gzip-text-asset/v1"
CODEC = "gzip-single-member-utf8/v1"
MAX_RAW = 4 * 1024 * 1024
MAX_TEXT = 4 * 1024 * 1024
MAX_TOTAL_RAW = 32 * 1024 * 1024
MAX_TOTAL_TEXT = 64 * 1024 * 1024
PATH = re.compile(r"^docs/verification/(?:[^/]+/)*[^/]+\.(?:log|txt|xml)\.gz$")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def evidence_path(path: Any) -> bool:
    return (
        isinstance(path, str)
        and bool(PATH.fullmatch(path))
        and all(part not in {"", ".", ".."} for part in path.split("/"))
        and not any(ord(char) < 32 or char in "\\\x7f" for char in path)
    )


def decode_gzip_text(raw: bytes, *, max_raw: int = MAX_RAW, max_text: int = MAX_TEXT) -> bytes:
    """Validate CRC/EOF, reject concatenation/trailing data and bound allocation."""
    if not raw or len(raw) > min(max_raw, MAX_RAW) or max_text < 0:
        raise ValueError("gzip_raw_byte_bound")
    try:
        inflater = zlib.decompressobj(31)
        text = inflater.decompress(raw, min(max_text, MAX_TEXT) + 1)
    except zlib.error as exc:
        raise ValueError("gzip_crc_or_format_invalid") from exc
    if len(text) > min(max_text, MAX_TEXT) or inflater.unconsumed_tail:
        raise ValueError("gzip_decoded_byte_bound")
    if not inflater.eof:
        raise ValueError("gzip_truncated")
    if inflater.unused_data:
        raise ValueError("gzip_multimember_or_trailing_data")
    try:
        text.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise ValueError("gzip_text_encoding_invalid") from exc
    if b"\0" in text:
        raise ValueError("gzip_text_nul")
    return text


def verified_assets(coverage: dict[str, Any], directory: Path, full_diff: bytes) -> dict[str, dict]:
    """Recompute representations and bind each to its real, added Git file span.

    Recognized proof assets are not executable/binary-code exemptions. V1 only
    represents added regular evidence files; modified/deleted/renamed inputs stay
    unsupported until all their required sides can be authenticated.
    """
    from tools.verifier_capture_obligation_manifest import _full_patch_file_records

    records = coverage.get("gzip_asset_sources", [])
    if (
        not isinstance(records, list)
        or sum(isinstance(row, dict) and row.get("status") == "captured" for row in records) > 80
    ):
        raise ValueError("gzip_asset_inventory_invalid")
    if not records:
        return {}
    patch_records = _full_patch_file_records(full_diff)
    if patch_records is None:
        raise ValueError("gzip_asset_patch_inventory_invalid")
    spans = {row["source"]: row for row in patch_records}
    if len(spans) != len(patch_records):
        raise ValueError("gzip_asset_duplicate_patch_path")
    binding = coverage.get("gzip_asset_binding") or {}
    if not isinstance(binding, dict):
        raise ValueError("gzip_asset_binding_invalid")
    repo, commit = binding.get("repository"), binding.get("evaluated_sha")
    if (
        not isinstance(repo, str)
        or not re.fullmatch(r"[\w.-]+/[\w.-]+", repo)
        or not re.fullmatch(r"[0-9a-f]{40}", str(commit))
    ):
        raise ValueError("gzip_asset_binding_invalid")
    result: dict[str, dict] = {}
    seen: set[str] = set()
    raw_total = text_total = 0
    for record in records:
        if (
            not isinstance(record, dict)
            or not evidence_path(record.get("source"))
            or record["source"] in seen
        ):
            raise ValueError("gzip_asset_path_invalid_or_duplicate")
        path = record["source"]
        seen.add(path)
        if record.get("status") != "captured":
            result[path] = {**record, "verified": False}
            continue
        span = spans.get(path)
        if not span:
            continue  # A whole-file chunk validates only its assigned real patch spans.
        if not span["binary"]:
            raise ValueError("gzip_asset_not_binary_patch_identity")
        patch = full_diff[span["start"] : span["end"]]
        index = re.search(rb"(?m)^index 0{7,40}\.\.([0-9a-f]{7,40})(?: 100644)?$", patch)
        if (
            record.get("schema") != SCHEMA
            or record.get("codec") != CODEC
            or record.get("input_id") != "gzip_asset:" + digest(path.encode("utf-8"))
            or record.get("repository") != repo
            or record.get("evaluated_sha") != commit
            or record.get("change_kind") != "added"
            or b"\nnew file mode 100644\n" not in patch
            or record.get("patch_sha256") != digest(patch.removesuffix(b"\n"))
            or record.get("necessity") not in {"required", "unknown"}
            or any(type(record.get(key)) is not int for key in ("raw_bytes", "text_bytes"))
            or record.get("mode") != "100644"
            or index is None
            or not str(record.get("git_blob_sha")).startswith(index[1].decode())
            or not re.fullmatch(r"[0-9a-f]{40}", str(record.get("git_blob_sha")))
            or not all(
                re.fullmatch(r"[0-9a-f]{64}", str(record.get(key)))
                for key in ("raw_sha256", "text_sha256")
            )
        ):
            raise ValueError("gzip_asset_provenance_invalid")
        raw_path = directory / f"{record['raw_sha256']}.gz"
        text_path = directory / f"{record['text_sha256']}.txt"
        if raw_path.is_symlink() or text_path.is_symlink() or raw_path.stat().st_size > MAX_RAW:
            raise ValueError("gzip_asset_sidecar_invalid")
        raw = raw_path.read_bytes()
        raw_total += len(raw)
        if raw_total > MAX_TOTAL_RAW:
            raise ValueError("gzip_asset_total_raw_bound")
        text = decode_gzip_text(raw, max_text=MAX_TOTAL_TEXT - text_total)
        text_total += len(text)
        if (
            text_total > MAX_TOTAL_TEXT
            or text_path.stat().st_size != len(text)
            or text_path.read_bytes() != text
            or digest(raw) != record["raw_sha256"]
            or digest(text) != record["text_sha256"]
            or record.get("raw_bytes") != len(raw)
            or record.get("text_bytes") != len(text)
            or hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            != record["git_blob_sha"]
        ):
            raise ValueError("gzip_asset_content_identity_mismatch")
        result[path] = {**record, "verified": True, "text": text}
    return result


def render_asset(record: dict) -> str:
    """A derived evidence view, explicitly not a fabricated Git text patch."""
    return (
        f"\nVerified gzip-text evidence view (not a Git patch): {json.dumps(record['source'], ensure_ascii=True)}\n"
        f"Git blob: {record['git_blob_sha']}; raw SHA256: {record['raw_sha256']}; "
        f"decoded SHA256: {record['text_sha256']}; codec: {CODEC}\n"
        + record["text"].decode("utf-8")
        + "\n[End of derived evidence view]\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-text", type=int, default=MAX_TEXT)
    args = parser.parse_args()
    import sys

    raw = sys.stdin.buffer.read(MAX_RAW + 1)
    text = decode_gzip_text(raw, max_text=args.max_text)
    print(
        json.dumps(
            {
                "codec": CODEC,
                "raw_sha256": digest(raw),
                "raw_bytes": len(raw),
                "text_sha256": digest(text),
                "text_bytes": len(text),
                "text_base64": base64.b64encode(text).decode("ascii"),
            }
        )
    )
    return 0


def validate_context_binding(coverage: dict, context: str) -> None:
    """Join derived inventory to the builder's outer immutable target metadata.

    This checks internal capture consistency; authenticity still comes from the
    source-owned collector and normal context/input/event receipt bindings.
    """
    if not coverage.get("gzip_asset_sources"):
        return
    preamble = context.split("## Context source coverage", 1)[0]
    repos = re.findall(r"(?m)^- Repository: ([^\s`]+/[^\s`]+)$", preamble)
    commits = re.findall(r"(?m)^- Target commit: `([0-9a-f]{40})`$", preamble)
    binding = coverage.get("gzip_asset_binding") or {}
    if not isinstance(binding, dict):
        raise ValueError("gzip_asset_binding_invalid")
    if (
        len(repos) != 1
        or len(commits) != 1
        or repos[0].lower() != binding.get("repository")
        or commits[0] != binding.get("evaluated_sha")
    ):
        raise ValueError("gzip_asset_outer_target_identity_mismatch")


def review_assets(
    coverage: dict, full_diff: bytes, *, context: str | None = None
) -> dict[str, str]:
    """Only locally revalidated, complete views may discharge a binary omission."""
    import os

    if context is not None:
        validate_context_binding(coverage, context)
    directory = Path(os.environ.get("VERIFIER_EVIDENCE_CAPTURE_DIR", "verifier-evidence"))
    return {
        path: render_asset(record)
        for path, record in verified_assets(coverage, directory, full_diff).items()
        if record.get("verified")
    }


def captured_inputs(
    coverage: dict, directory: Path, full_diff: bytes, *, context: str | None = None
) -> dict[str, bytes]:
    """Decoded views participate in the existing complete UTF-8 byte inventory.

    Compressed originals stay digest-addressed retained sidecars; their Git and
    SHA identities and codec are bound in context, not fed as arbitrary text.
    """
    if context is not None:
        validate_context_binding(coverage, context)
    return {
        "gzip_asset:" + digest(path.encode("utf-8")): record["text"]
        for path, record in verified_assets(coverage, directory, full_diff).items()
        if record.get("verified")
    }


if __name__ == "__main__":
    raise SystemExit(main())
