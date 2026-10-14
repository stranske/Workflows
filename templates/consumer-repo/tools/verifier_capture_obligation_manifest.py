"""Derive a lossless capture obligation manifest from generated verifier context.

Source issue #3820 requires an auditable contract for which evidence must be
present before expanded native provider invocation. This module reads the
builder-emitted context source coverage inventory and names per-source
obligations without mutating captured artifacts. This helper validates generated
capture coverage and records it in input snapshots. Expanded native preflight
consumes the same manifest; lossless partitioning remains a separate obligation.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


def _full_patch_file_records(raw: bytes) -> list[dict[str, Any]] | None:
    """Parse only complete, unambiguous raw Git file spans for recovery binding."""
    starts = [match.start() for match in re.finditer(rb"(?m)^diff --git ", raw)]
    if not starts:
        return None
    records: list[dict[str, Any]] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(raw)
        span = raw[start:end]
        lines = span.splitlines()
        if not lines or not lines[0].startswith(b"diff --git "):
            return None
        from_path = to_path = None
        for line in lines[1:]:
            if line.startswith(b"@@"):
                break
            if line.startswith(b"--- "):
                from_path = line[4:].split(b"\t", 1)[0]
            elif line.startswith(b"+++ "):
                to_path = line[4:].split(b"\t", 1)[0]
        if from_path is not None or to_path is not None:
            if from_path is None or to_path is None:
                return None
            if from_path == b"/dev/null":
                source_bytes = to_path
            elif to_path == b"/dev/null":
                source_bytes = from_path
            else:
                source_bytes = to_path
            if source_bytes.startswith(b"a/") or source_bytes.startswith(b"b/"):
                source_bytes = source_bytes[2:]
            if from_path == b"/dev/null":
                declared_from = source_bytes
            else:
                declared_from = from_path[2:] if from_path.startswith(b"a/") else from_path
            # Metadata cannot rename a file independently of the authoritative
            # diff header. Ordinary unquoted paths, including spaces, compare as
            # raw bytes; quoted/ambiguous headers fail closed below.
            if lines[0][len(b"diff --git ") :] != b"a/" + declared_from + b" b/" + source_bytes:
                return None
        else:
            # A header-only parse is accepted only for ordinary unquoted paths.
            header = lines[0][len(b"diff --git ") :]
            match = re.fullmatch(rb"a/([^ ]+) b/([^ ]+)", header)
            if match is None:
                return None
            declared_from, source_bytes = match.group(1), match.group(2)
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
    canonical_bytes = full_diff_bytes[:-1] if full_diff_bytes.endswith(b"\n") else full_diff_bytes
    expected_records = _full_patch_file_records(canonical_bytes)
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


def build_capture_obligation_manifest(
    context_text: str,
    *,
    require_full_changed_code: bool = True,
    full_diff_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Build obligation manifest and overall sufficiency for native preflight."""
    coverage = parse_context_source_coverage(context_text)
    obligations: list[SourceObligation] = []
    gaps: list[str] = []

    if not coverage:
        gaps.append("context_source_coverage_missing_or_malformed")
    else:
        if coverage.get("schema") != "verifier-context-source-coverage/v1":
            gaps.append("context_source_coverage_schema_unknown")
        if coverage.get("stage") != "generated-context":
            gaps.append("context_source_coverage_stage_unknown")
        changed_records = coverage.get("changed_code_sources")
        full_patch_covers_changed_code = False
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
                if obligation.status != "included" and (
                    kind != "changed_code"
                    or require_full_changed_code
                    and not (
                        full_patch_covers_changed_code
                        and obligation.status in {"truncated", "omitted"}
                    )
                ):
                    gaps.append(f"{kind}:{obligation.source}:{obligation.status}")

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
