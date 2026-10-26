"""Derive a lossless capture obligation manifest from generated verifier context.

The capture contract requires an auditable inventory of which evidence must be
present before expanded native provider invocation. This module reads the
builder-emitted context source coverage inventory and names per-source
obligations without mutating captured artifacts. This helper validates generated
capture coverage and records it in input snapshots. Expanded native preflight
consumes the same manifest; lossless partitioning remains a separate obligation.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.verifier_artifact_capture import load_artifact_capture

SCHEMA = "workflows-verifier-capture-obligation-manifest/v1"
_COVERAGE_BLOCK_RE = re.compile(
    r"^## Context source coverage[ \t]*\n(?:(?!^## |^```)[^\n]*\n)*"
    r"^```json[ \t]*\n(.*?)\n```[ \t]*(?:\n|$)",
    re.MULTILINE | re.DOTALL,
)


@dataclass(frozen=True)
class SourceObligation:
    source: str
    kind: str
    status: str
    included_chars: int | None
    total_chars: int | None
    reason: str | None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source": self.source,
            "kind": self.kind,
            "status": self.status,
        }
        if self.included_chars is not None:
            payload["included_chars"] = self.included_chars
        if self.total_chars is not None:
            payload["total_chars"] = self.total_chars
        if self.reason:
            payload["reason"] = self.reason
        return payload


def _obligation_from_record(kind: str, record: dict[str, Any]) -> SourceObligation:
    return SourceObligation(
        source=str(record.get("source") or kind),
        kind=kind,
        status=str(record.get("status") or "unavailable"),
        included_chars=record.get("included_chars"),
        total_chars=record.get("total_chars"),
        reason=record.get("reason"),
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject ambiguous duplicate JSON keys rather than choosing a winner."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate coverage key")
        result[key] = value
    return result


def parse_context_source_coverage(context_text: str) -> dict[str, Any] | None:
    """Read only the anchored builder inventory before untrusted CI material."""
    sections = re.split(r"^## CI Information[ \t]*$", context_text, maxsplit=1, flags=re.M)
    if len(sections) != 2:
        return None
    preamble = sections[0]
    matches = list(_COVERAGE_BLOCK_RE.finditer(preamble))
    if len(matches) != 1:
        return None
    try:
        payload = json.loads(matches[0].group(1), object_pairs_hook=_unique_object)
    except (ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _valid_count(value: Any) -> bool:
    """Counts are nonnegative integers; booleans are not character counts."""
    return type(value) is int and value >= 0


def _record_gaps(kind: str, record: dict[str, Any]) -> list[str]:
    """Validate identity, closed status vocabulary, and retained byte accounting."""
    gaps: list[str] = []
    source = record.get("source")
    if not isinstance(source, str) or not source.strip():
        gaps.append(f"{kind}:source_missing_or_malformed")
    status = record.get("status")
    if not isinstance(status, str) or status not in {
        "included",
        "truncated",
        "omitted",
        "unavailable",
    }:
        gaps.append(f"{kind}:{source}:status_missing_or_unknown")
    if (
        kind == "acceptance_evidence"
        and "failure_kinds" in record
        and not _evidence_availability_only(record)
    ):
        gaps.append(f"{kind}:{source}:integrity_failure_or_unknown_kind")
    included, total = record.get("included_chars"), record.get("total_chars")
    # Unavailable aggregate retrievals have no known counts. Preserve that gap;
    # do not manufacture a total for records whose original size is unknown.
    if status == "included" or "included_chars" in record or "total_chars" in record:
        if not _valid_count(included) or (total is not None and not _valid_count(total)):
            gaps.append(f"{kind}:{source}:counts_malformed")
        elif status == "included" and (total is None or included != total):
            gaps.append(f"{kind}:{source}:included_count_mismatch")
        elif total is not None and included > total:
            gaps.append(f"{kind}:{source}:included_exceeds_total")
    return gaps


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _decode_git_quoted_path(value: bytes) -> tuple[bytes, bytes] | None:
    """Decode Git's C-style quoted path form without guessing ambiguous headers."""
    if not value.startswith(b'"'):
        return None
    chunks: list[bytes] = []
    index = 1
    simple = {
        ord("a"): b"\a",
        ord("b"): b"\b",
        ord("f"): b"\f",
        ord("n"): b"\n",
        ord("r"): b"\r",
        ord("t"): b"\t",
        ord("v"): b"\v",
        ord("\\"): b"\\",
        ord('"'): b'"',
    }
    while index < len(value):
        byte = value[index]
        if byte == ord('"'):
            decoded = b"".join(chunks)
            try:
                decoded.decode("utf-8")
            except UnicodeDecodeError:
                return None
            return decoded, value[index + 1 :]
        if byte != ord("\\"):
            chunks.append(bytes([byte]))
            index += 1
            continue
        if index + 1 >= len(value):
            return None
        escaped = value[index + 1]
        if ord("0") <= escaped <= ord("7"):
            octal = value[index + 1 : index + 4]
            if len(octal) != 3 or any(char < ord("0") or char > ord("7") for char in octal):
                return None
            chunks.append(bytes([int(octal, 8)]))
            index += 4
            continue
        replacement = simple.get(escaped)
        if replacement is None:
            return None
        chunks.append(replacement)
        index += 2
    return None


def _parse_git_path(value: bytes) -> bytes | None:
    """Parse exactly one Git header path, preserving its decoded raw identity."""
    if not value:
        return None
    if not value.startswith(b'"'):
        return value if b'"' not in value else None
    parsed = _decode_git_quoted_path(value)
    if parsed is None or parsed[1].strip():
        return None
    return parsed[0]


def _parse_git_diff_header_candidates(line: bytes) -> list[tuple[bytes, bytes]] | None:
    """Return every syntactically plausible Git header identity without guessing."""
    prefix = b"diff --git "
    if not line.startswith(prefix):
        return None
    payload = line[len(prefix) :]

    def pair(source: bytes, destination: bytes | None) -> tuple[bytes, bytes] | None:
        if destination is None or not source.startswith(b"a/") or not destination.startswith(b"b/"):
            return None
        return source[2:], destination[2:]

    if payload.startswith(b'"'):
        decoded = _decode_git_quoted_path(payload)
        if decoded is None or not decoded[1].startswith(b" "):
            return None
        candidate = pair(decoded[0], _parse_git_path(decoded[1].lstrip(b" ")))
        return [candidate] if candidate is not None else None

    candidates: list[tuple[bytes, bytes]] = []
    for index in range(len(payload) - 2):
        if payload[index : index + 1] != b" ":
            continue
        remainder = payload[index + 1 :]
        if not (remainder.startswith(b"b/") or remainder.startswith(b'"b/')):
            continue
        source = payload[:index]
        if b'"' in source:
            continue
        candidate = pair(source, _parse_git_path(remainder))
        if candidate is not None and candidate not in candidates:
            candidates.append(candidate)
    return candidates or None


def _resolve_git_header_identity(
    candidates: list[tuple[bytes, bytes]], metadata: list[tuple[bytes, bytes]]
) -> tuple[bytes, bytes] | None:
    """Bind all path metadata to one header candidate before any default choice."""
    if metadata:
        identity = metadata[0]
        if any(pair != identity for pair in metadata[1:]):
            return None
        matches = [candidate for candidate in candidates if candidate == identity]
        return identity if len(matches) == 1 else None
    identical = [candidate for candidate in candidates if candidate[0] == candidate[1]]
    if len(identical) == 1:
        return identical[0]
    return candidates[0] if len(candidates) == 1 else None


def _metadata_git_path(value: bytes) -> bytes | None:
    """Read the path portion of a ---/+++ metadata line using Git path grammar."""
    return _parse_git_path(value.split(b"\t", 1)[0])


def _raw_patch_has_binary_section(raw: bytes) -> bool:
    """Binary patch syntax is unavailable evidence even when its payload is malformed."""
    return any(
        line == b"GIT binary patch" or line.startswith(b"Binary files ")
        for line in raw.splitlines()
    )


def _full_patch_file_records(raw: bytes) -> list[dict[str, Any]] | None:
    """Parse only complete, unambiguous raw Git file spans for recovery binding."""
    starts = [match.start() for match in re.finditer(rb"(?m)^diff --git ", raw)]
    if not starts:
        return None
    try:
        syntax = subprocess.run(
            ["git", "apply", "--numstat", "-"],
            input=raw,
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if syntax.returncode != 0:
        return None
    raw = raw[:-1] if raw.endswith(b"\n") else raw
    starts = [match.start() for match in re.finditer(rb"(?m)^diff --git ", raw)]
    if not starts:
        return None
    records: list[dict[str, Any]] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(raw)
        span = raw[start:end]
        lines = span.splitlines()
        if not lines:
            return None
        header_candidates = _parse_git_diff_header_candidates(lines[0])
        if header_candidates is None:
            return None
        payload = lines[1:]
        hunk_indexes = [
            position for position, line in enumerate(payload) if line.startswith(b"@@ ")
        ]
        has_hunk = any(
            any(line.startswith((b"+", b"-", b" ")) for line in payload[position + 1 :])
            for position in hunk_indexes
        )
        has_binary = any(
            line == b"GIT binary patch" or line.startswith(b"Binary files ") for line in payload
        )
        has_mode_change = any(line.startswith(b"old mode ") for line in payload) and any(
            line.startswith(b"new mode ") for line in payload
        )
        has_rename = any(line.startswith(b"rename from ") for line in payload) and any(
            line.startswith(b"rename to ") for line in payload
        )
        has_copy = any(line.startswith(b"copy from ") for line in payload) and any(
            line.startswith(b"copy to ") for line in payload
        )
        has_empty_file = any(
            line.startswith((b"new file mode ", b"deleted file mode ")) for line in payload
        ) and any(line.startswith(b"index ") for line in payload)
        if not (
            has_hunk or has_binary or has_mode_change or has_rename or has_copy or has_empty_file
        ):
            return None
        metadata_pairs: list[tuple[bytes, bytes]] = []
        from_paths: list[bytes | None] = []
        to_paths: list[bytes | None] = []
        rename_from_paths: list[bytes | None] = []
        rename_to_paths: list[bytes | None] = []
        copy_from_paths: list[bytes | None] = []
        copy_to_paths: list[bytes | None] = []
        for line in lines[1:]:
            if line.startswith(b"@@"):
                break
            if line.startswith(b"--- "):
                from_paths.append(_metadata_git_path(line[4:]))
            elif line.startswith(b"+++ "):
                to_paths.append(_metadata_git_path(line[4:]))
            elif line.startswith(b"rename from "):
                rename_from_paths.append(_parse_git_path(line[len(b"rename from ") :]))
            elif line.startswith(b"rename to "):
                rename_to_paths.append(_parse_git_path(line[len(b"rename to ") :]))
            elif line.startswith(b"copy from "):
                copy_from_paths.append(_parse_git_path(line[len(b"copy from ") :]))
            elif line.startswith(b"copy to "):
                copy_to_paths.append(_parse_git_path(line[len(b"copy to ") :]))

        def add_pairs(
            left: list[bytes | None],
            right: list[bytes | None],
            collected: list[tuple[bytes, bytes]],
            *,
            diff_metadata: bool = False,
        ) -> bool:
            if len(left) != len(right) or any(value is None for value in left + right):
                return False
            for pair_from, pair_to in zip(left, right, strict=True):
                assert pair_from is not None and pair_to is not None
                if diff_metadata:
                    pair_from = pair_from[2:] if pair_from.startswith(b"a/") else pair_from
                    pair_to = pair_to[2:] if pair_to.startswith(b"b/") else pair_to
                    if pair_from == b"/dev/null":
                        pair_from = pair_to
                    elif pair_to == b"/dev/null":
                        pair_to = pair_from
                collected.append((pair_from, pair_to))
            return True

        if (from_paths or to_paths) and not add_pairs(
            from_paths, to_paths, metadata_pairs, diff_metadata=True
        ):
            return None
        if (rename_from_paths or rename_to_paths) and not add_pairs(
            rename_from_paths, rename_to_paths, metadata_pairs
        ):
            return None
        if (copy_from_paths or copy_to_paths) and not add_pairs(
            copy_from_paths, copy_to_paths, metadata_pairs
        ):
            return None
        header_paths = _resolve_git_header_identity(header_candidates, metadata_pairs)
        if header_paths is None:
            return None
        declared_from, source_bytes = header_paths
        try:
            source = source_bytes.decode("utf-8")
            from_source = declared_from.decode("utf-8")
        except UnicodeDecodeError:
            return None
        if not source or not from_source:
            return None
        records.append(
            {
                "source": source,
                "from_path": from_source,
                "start": start,
                "end": end,
                "sha256": hashlib.sha256(span).hexdigest(),
                "binary": has_binary,
            }
        )
    return records


def _verified_full_diff_changed_code(
    artifact: dict[str, Any],
    changed_records: list[dict[str, Any]],
    full_diff_bytes: bytes | None,
) -> tuple[bool, list[str]]:
    """Bind omitted embedded code to exact raw full-patch spans, never metadata alone."""
    if full_diff_bytes is None:
        return False, ["full_diff_artifact:raw_bytes_unavailable"]
    if artifact.get("status") != "included":
        return False, [f"full_diff_artifact:{artifact.get('status')}"]
    if artifact.get("source") != "verifier-pr-diff.patch":
        return False, ["full_diff_artifact:source_unrecognized"]
    if artifact.get("encoding") != "utf-8":
        return False, ["full_diff_artifact:encoding_unrecognized"]
    if artifact.get("bytes") != len(full_diff_bytes):
        return False, ["full_diff_artifact:byte_count_mismatch"]
    if (
        not _valid_sha256(artifact.get("sha256"))
        or artifact["sha256"] != hashlib.sha256(full_diff_bytes).hexdigest()
    ):
        return False, ["full_diff_artifact:sha256_mismatch"]
    try:
        artifact_text = full_diff_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return False, ["full_diff_artifact:utf8_decode_failed"]
    # The builder stores one canonical trailing LF. Retain every earlier CR/LF byte.
    canonical = artifact_text[:-1] if artifact_text.endswith("\n") else artifact_text
    if artifact.get("chars") != len(canonical) or not canonical:
        return False, ["full_diff_artifact:character_count_mismatch"]
    gaps: list[str] = []
    expected_records = _full_patch_file_records(full_diff_bytes)
    if expected_records is None:
        return False, ["full_diff_artifact:file_inventory_malformed"]
    if len(changed_records) != len(expected_records):
        return False, ["changed_code:full_patch_record_count_mismatch"]
    expected_by_span = {(item["start"], item["end"]): item for item in expected_records}
    if len(expected_by_span) != len(expected_records):
        return False, ["full_diff_artifact:file_inventory_malformed"]
    assigned: set[tuple[int, int]] = set()
    for record in changed_records:
        if not isinstance(record, dict):
            gaps.append("changed_code:record_malformed")
            continue
        start, end, digest = record.get("start"), record.get("end"), record.get("sha256")
        source = str(record.get("source") or "changed_code")
        if type(start) is not int or type(end) is not int:
            gaps.append(f"changed_code:{source}:full_patch_span_malformed")
            continue
        expected = expected_by_span.get((start, end))
        if expected is None or (start, end) in assigned:
            gaps.append(f"changed_code:{source}:full_patch_span_identity_mismatch")
            continue
        assigned.add((start, end))
        if (
            record.get("source") != expected["source"]
            or record.get("from_path") != expected["from_path"]
            or digest != expected["sha256"]
        ):
            gaps.append(f"changed_code:{source}:full_patch_span_identity_mismatch")
    if len(assigned) != len(expected_records):
        gaps.append("changed_code:full_patch_record_coverage_mismatch")
    return not gaps, gaps


# Collector-owned failure kinds that describe retrieval/bounds only. Unknown
# kinds, provenance, decoding and archive-integrity failures remain blocking.
_AVAILABILITY_FAILURE_KINDS = frozenset(
    {
        "record",
        "character",
        "page",
        "transport",
        "clause_length",
        "reference_record",
        "reference_source",
        "workflow_listing",
        "run_record",
        "run_page",
        "run_transport",
        "artifact_page",
        "artifact_transport",
        "artifact_record",
        "expired",
        "archive_byte",
        "global_archive_byte",
        "global_extraction_byte",
        "global_character",
        "entry",
        "extraction_byte",
        "extraction_incomplete",
        "unselected_member",
        # A supported archive can contain unrenderable media (for example PNG).
        # This is unavailable evidence, not corruption; only optional channels
        # can be omitted, and required media remains a capture gap.
        "unrenderable_media",
    }
)


def _evidence_availability_only(record: dict[str, Any]) -> bool:
    """Accept only typed availability failures, never inferred reason prose."""
    kinds = record.get("failure_kinds")
    if "failure_kinds" not in record:
        # Individual bounded records have no retrieval failure. Unavailable
        # aggregate inventories require explicit collector classification.
        return record.get("status") in {"truncated", "omitted"} and not record.get("reason")
    return (
        isinstance(kinds, list)
        and bool(kinds)
        and all(isinstance(kind, str) and kind in _AVAILABILITY_FAILURE_KINDS for kind in kinds)
    )


def build_capture_obligation_manifest(
    context_text: str,
    *,
    require_full_changed_code: bool = True,
    full_diff_bytes: bytes | None = None,
    optional_evidence_channels: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Build obligation manifest and overall sufficiency for native preflight."""
    coverage = parse_context_source_coverage(context_text)
    obligations: list[SourceObligation] = []
    gaps: list[str] = []
    optional_gaps: list[str] = []
    optional_sources: list[dict[str, str]] = []
    if not optional_evidence_channels <= {"comments", "artifacts"}:
        raise ValueError("unknown optional evidence channel")
    recovered_artifacts: set[str] = set()
    if (
        coverage
        and os.environ.get("VERIFIER_EVIDENCE_CAPTURE_DIR")
        and os.environ.get("VERIFIER_SEMANTIC_MODE") == "1"
    ):
        try:
            _, recovered_artifacts = load_artifact_capture(
                coverage, Path(os.environ["VERIFIER_EVIDENCE_CAPTURE_DIR"])
            )
        except (OSError, ValueError) as exc:
            gaps.append(f"artifact_raw_capture:{exc}")

    asset_views = {}
    if coverage and coverage.get("gzip_asset_sources") and full_diff_bytes is not None:
        try:
            from tools.verifier_gzip_assets import review_assets

            asset_views = review_assets(coverage, full_diff_bytes, context=context_text)
        except (OSError, ValueError, TypeError) as exc:
            gaps.append(f"gzip_asset_capture:{exc}")
    if not coverage:
        gaps.append("context_source_coverage_missing_or_malformed")
    else:
        if coverage.get("schema") != "verifier-context-source-coverage/v1":
            gaps.append("context_source_coverage_schema_unknown")
        if coverage.get("stage") != "generated-context":
            gaps.append("context_source_coverage_stage_unknown")
        changed_records = coverage.get("changed_code_sources")
        full_patch_covers_changed_code = False
        binary_sources: set[str] = set()
        artifact_for_binary = coverage.get("full_diff_artifact")
        if (
            isinstance(artifact_for_binary, dict)
            and full_diff_bytes is not None
            and _raw_patch_has_binary_section(full_diff_bytes)
        ):
            binary_records = _full_patch_file_records(full_diff_bytes)
            if binary_records is not None:
                binary_sources = {row["source"] for row in binary_records if row["binary"]}
            if binary_records is None or any(
                row["binary"] and row["source"] not in asset_views for row in binary_records
            ):
                gaps.append("changed_code:full_patch_binary_unavailable")
        if isinstance(changed_records, list) and any(
            isinstance(record, dict)
            and isinstance(record.get("status"), str)
            and record.get("status") in {"truncated", "omitted"}
            for record in changed_records
        ):
            artifact_for_recovery = coverage.get("full_diff_artifact")
            if isinstance(artifact_for_recovery, dict):
                full_patch_covers_changed_code, artifact_gaps = _verified_full_diff_changed_code(
                    artifact_for_recovery, changed_records, full_diff_bytes
                )
                gaps.extend(artifact_gaps)
            else:
                gaps.append("full_diff_artifact_missing_or_malformed")
        for field, kind in (
            ("changed_code_sources", "changed_code"),
            ("acceptance_sources", "acceptance_source"),
            ("acceptance_evidence_sources", "acceptance_evidence"),
        ):
            records = coverage.get(field)
            if not isinstance(records, list):
                gaps.append(f"{field}_missing_or_malformed")
                continue
            if field != "acceptance_evidence_sources" and not records:
                gaps.append(f"{field}_empty")
            seen: set[str] = set()
            for record in records:
                if not isinstance(record, dict):
                    gaps.append(f"{field}_malformed")
                    continue
                gaps.extend(_record_gaps(kind, record))
                obligation = _obligation_from_record(kind, record)
                obligations.append(obligation)
                if obligation.source in seen:
                    gaps.append(f"{kind}:{obligation.source}:duplicate_source")
                seen.add(obligation.source)
                if (
                    kind == "acceptance_evidence"
                    and obligation.source in recovered_artifacts
                    and obligation.status in {"truncated", "omitted"}
                ):
                    continue
                if kind == "changed_code" and obligation.source in asset_views:
                    continue
                if obligation.status != "included" and (
                    kind != "changed_code"
                    or require_full_changed_code
                    and not (
                        full_patch_covers_changed_code
                        and obligation.source not in binary_sources
                        and obligation.status in {"truncated", "omitted"}
                    )
                ):
                    gap = f"{kind}:{obligation.source}:{obligation.status}"
                    # Only source-owned channel metadata can classify an
                    # availability omission. Identity/accounting errors above
                    # remain hard gaps, even for useful enrichment.
                    if (
                        kind == "acceptance_evidence"
                        and isinstance(record.get("channel"), str)
                        and record.get("channel") in optional_evidence_channels
                        and record.get("required_material") is not True
                        and _evidence_availability_only(record)
                    ):
                        optional_gaps.append(gap)
                        optional_sources.append(
                            {
                                "source": obligation.source,
                                "channel": record["channel"],
                                "necessity": "useful",
                                "status": obligation.status,
                            }
                        )
                    else:
                        gaps.append(gap)

        discovery = coverage.get("acceptance_source_discovery")
        # The builder always emits this record. Absence cannot establish that
        # linked acceptance sources were unnecessary or fully discovered.
        if not isinstance(discovery, dict):
            gaps.append("acceptance_source_discovery_missing_or_malformed")
        else:
            if type(discovery.get("required")) is not bool:
                gaps.append("acceptance_source_discovery_required_malformed")
            status = discovery.get("status")
            if status != "included":
                gaps.append(f"acceptance_source_discovery:{status}")
            if discovery.get("required") is True:
                obligations.append(
                    SourceObligation(
                        source="acceptance_source_discovery",
                        kind="discovery",
                        status=str(status or "unavailable"),
                        included_chars=None,
                        total_chars=None,
                        reason=discovery.get("reason"),
                    )
                )

        artifact = coverage.get("full_diff_artifact")
        if not isinstance(artifact, dict):
            gaps.append("full_diff_artifact_missing_or_malformed")
        else:
            status = artifact.get("status")
            source = artifact.get("source")
            chars = artifact.get("chars")
            if not isinstance(source, str) or not source.strip():
                gaps.append("full_diff_artifact_source_missing_or_malformed")
            if not _valid_count(chars) or chars == 0:
                gaps.append("full_diff_artifact_chars_missing_or_malformed")
            obligations.append(
                SourceObligation(
                    source=str(source or "verifier-pr-diff.patch"),
                    kind="full_diff_artifact",
                    status=str(status or "unavailable"),
                    included_chars=chars if _valid_count(chars) else None,
                    total_chars=chars if _valid_count(chars) else None,
                    reason=None,
                )
            )
            if status != "included":
                gaps.append(f"full_diff_artifact:{status}")

    sufficient = not gaps
    return {
        "schema": SCHEMA,
        "sufficient": sufficient,
        "gaps": gaps,
        "obligations": [item.to_dict() for item in obligations],
        **({"binary_evidence_representations": sorted(asset_views)} if asset_views else {}),
        **(
            {
                "screening_policy": "action-minimum-evaluate/v1",
                "capture_complete": not gaps and not optional_gaps,
                "capture_gaps": [*gaps, *optional_gaps],
                "optional_evidence": optional_sources,
            }
            if optional_evidence_channels
            else {}
        ),
    }


BYTE_INVENTORY_SCHEMA = "workflows-verifier-capture-byte-inventory/v1"
BYTE_RANGE_SIZE = 65536


def build_capture_byte_inventory(inputs: dict[str, bytes]) -> dict[str, Any]:
    """Index every raw byte without interpreting ranges as semantic partitions.

    Half-open offsets and hashes permit later planners to prove reassembly. A
    range may bisect a UTF-8 character: consumers must reassemble raw bytes before
    decoding. This inventory never certifies evidence sufficiency or native fit.
    """
    items: list[dict[str, Any]] = []
    for name, raw in sorted(inputs.items()):
        if not isinstance(name, str) or not name or not isinstance(raw, bytes):
            raise ValueError("capture byte inventory input is malformed")
        digest = hashlib.sha256(raw).hexdigest()
        ranges = []
        for start in range(0, len(raw), BYTE_RANGE_SIZE):
            end = min(start + BYTE_RANGE_SIZE, len(raw))
            ranges.append(
                {
                    "id": f"{name}:{digest}:{start}:{end}",
                    "start": start,
                    "end": end,
                    "sha256": hashlib.sha256(raw[start:end]).hexdigest(),
                }
            )
        items.append({"input": name, "bytes": len(raw), "sha256": digest, "ranges": ranges})
    return {"schema": BYTE_INVENTORY_SCHEMA, "range_bytes": BYTE_RANGE_SIZE, "inputs": items}


def validate_capture_byte_inventory(inventory: Any, inputs: dict[str, bytes]) -> None:
    """Require exact coverage, identities, bounds and hashes of supplied bytes."""
    expected = build_capture_byte_inventory(inputs)
    # Canonical JSON also distinguishes bool from integer offsets/counts.
    if json.dumps(inventory, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError("capture byte inventory does not match the captured inputs")


REASSEMBLY_CONTRACT_SCHEMA = "workflows-verifier-capture-reassembly-contract/v1"


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def build_capture_reassembly_contract(
    manifest: dict[str, Any], byte_inventory: dict[str, Any]
) -> dict[str, Any]:
    """Freeze the global evidence floor; never infer semantic independence.

    Every obligation and gap depends on ALL captured ranges. A later semantic
    planner must explicitly prove any narrower package, including governing
    sources, RED/restoration/GREEN evidence and cross-proof findings. This
    conservative contract is not a partition plan or a sufficiency upgrade.
    """
    binding = {
        "obligation_manifest_sha256": _canonical_digest(manifest),
        "byte_inventory_sha256": _canonical_digest(byte_inventory),
    }
    contract_id = _canonical_digest(binding)
    entries = {}
    for field in ("obligations", "gaps"):
        entries[field] = [
            {
                "id": f"{contract_id}:{field}:{index}:{_canonical_digest(value)}",
                "value": value,
            }
            for index, value in enumerate(manifest[field])
        ]
    return {
        "schema": REASSEMBLY_CONTRACT_SCHEMA,
        "id": contract_id,
        **binding,
        "dependency_policy": "all-captured-inputs",
        "required_range_ids": [
            item["id"] for source in byte_inventory["inputs"] for item in source["ranges"]
        ],
        "sufficient": manifest["sufficient"],
        **entries,
    }


def record_capture_obligations(
    context_path: Path,
    *,
    context_text: str | None = None,
    diff_path: Path | None = None,
    diff_text: str | None = None,
) -> dict[str, Any]:
    """Enrich a local input snapshot without rewriting any captured source bytes.

    Existing snapshots must bind the exact context. Never repair a stale identity
    or replace an already recorded, conflicting inventory. A standalone manifest
    is also emitted for evaluate runs that do not create comparison snapshots.
    """
    context_bytes = context_path.read_bytes()
    captured_text = context_bytes.decode("utf-8")
    if context_text is not None and context_text != captured_text:
        raise ValueError("loaded context changed before snapshot recording")
    diff_bytes = diff_path.read_bytes() if diff_path is not None else None
    if diff_bytes is not None:
        captured_diff = diff_bytes.decode("utf-8")
        if diff_text is not None and diff_text != captured_diff:
            raise ValueError("loaded diff changed before snapshot recording")
    manifest = build_capture_obligation_manifest(captured_text, full_diff_bytes=diff_bytes)
    raw_inputs = {"context": context_bytes}
    if diff_bytes is not None:
        raw_inputs["diff"] = diff_bytes
    capture_dir = os.environ.get("VERIFIER_EVIDENCE_CAPTURE_DIR")
    if capture_dir:
        try:
            artifact_inputs, _ = load_artifact_capture(
                parse_context_source_coverage(captured_text) or {}, Path(capture_dir)
            )
        except (OSError, ValueError) as exc:
            gap = f"artifact_raw_capture:{exc}"
            if gap not in manifest["gaps"]:
                manifest["gaps"].append(gap)
            manifest["sufficient"] = False
        else:
            raw_inputs.update(artifact_inputs)
    if diff_bytes is not None:
        try:
            from tools.verifier_gzip_assets import captured_inputs

            raw_inputs.update(
                captured_inputs(
                    parse_context_source_coverage(captured_text) or {},
                    Path(capture_dir or "verifier-evidence"),
                    diff_bytes,
                    context=captured_text,
                )
            )
        except (OSError, ValueError, TypeError) as exc:
            manifest["gaps"].append(f"gzip_asset_capture:{exc}")
            manifest["sufficient"] = False
    byte_inventory = build_capture_byte_inventory(raw_inputs)
    reassembly_contract = build_capture_reassembly_contract(manifest, byte_inventory)
    snapshot_path = context_path.with_name("verifier-input-manifest.json")
    if snapshot_path.exists():
        snapshot = json.loads(
            snapshot_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
        )
        if (
            not isinstance(snapshot, dict)
            or snapshot.get("schema") != "workflows-verifier-input-snapshot/v1"
            or snapshot.get("context_sha256") != hashlib.sha256(context_bytes).hexdigest()
        ):
            raise ValueError("context does not match the verifier input snapshot")
        if (
            diff_bytes is not None
            and snapshot.get("diff_sha256") != hashlib.sha256(diff_bytes).hexdigest()
        ):
            raise ValueError("diff does not match the verifier input snapshot")
        if "capture_obligations" in snapshot and snapshot["capture_obligations"] != manifest:
            raise ValueError("capture obligations do not match the verifier input snapshot")
        if "capture_byte_inventory" in snapshot:
            validate_capture_byte_inventory(snapshot["capture_byte_inventory"], raw_inputs)
        if "capture_reassembly_contract" in snapshot and json.dumps(
            snapshot["capture_reassembly_contract"], sort_keys=True
        ) != json.dumps(reassembly_contract, sort_keys=True):
            raise ValueError("capture reassembly contract does not match the captured inputs")
        snapshot["capture_reassembly_contract"] = reassembly_contract
        snapshot["capture_obligations"] = manifest
        snapshot["capture_byte_inventory"] = byte_inventory
        snapshot_path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    context_path.with_name("verifier-capture-obligation-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    context_path.with_name("verifier-capture-byte-inventory.json").write_text(
        json.dumps(byte_inventory, indent=2) + "\n", encoding="utf-8"
    )
    context_path.with_name("verifier-capture-reassembly-contract.json").write_text(
        json.dumps(reassembly_contract, indent=2) + "\n", encoding="utf-8"
    )
    return manifest
