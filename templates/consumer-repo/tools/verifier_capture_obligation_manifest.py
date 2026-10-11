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


def build_capture_obligation_manifest(
    context_text: str,
    *,
    require_full_changed_code: bool = True,
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
                    kind != "changed_code" or require_full_changed_code
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
    # Path.read_text normalizes line endings. Compare that same view to the
    # already loaded evaluation input, while binding snapshots to raw bytes.
    if context_text is not None and context_text != captured_text.replace("\r\n", "\n").replace(
        "\r", "\n"
    ):
        raise ValueError("loaded context changed before snapshot recording")
    diff_bytes = diff_path.read_bytes() if diff_path is not None else None
    if diff_bytes is not None:
        captured_diff = diff_bytes.decode("utf-8")
        if diff_text is not None and diff_text != captured_diff.replace("\r\n", "\n").replace(
            "\r", "\n"
        ):
            raise ValueError("loaded diff changed before snapshot recording")
    manifest = build_capture_obligation_manifest(captured_text)
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
