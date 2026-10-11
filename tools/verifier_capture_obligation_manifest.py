"""Derive a lossless capture obligation manifest from generated verifier context.

Source issue #3820 requires an auditable contract for which evidence must be
present before expanded native provider invocation. This module reads the
builder-emitted context source coverage inventory and names per-source
obligations without mutating captured artifacts. This helper validates generated
capture coverage only; snapshot emission, downstream prompt retention, native
capacity checks and lossless partitioning remain separate integration obligations.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
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
        if isinstance(discovery, dict) and type(discovery.get("required")) is not bool:
            gaps.append("acceptance_source_discovery_required_malformed")
        if isinstance(discovery, dict) and discovery.get("required"):
            status = str(discovery.get("status") or "unavailable")
            obligations.append(
                SourceObligation(
                    source="acceptance_source_discovery",
                    kind="discovery",
                    status=status,
                    included_chars=None,
                    total_chars=None,
                    reason=discovery.get("reason"),
                )
            )
            if status != "included":
                gaps.append(f"acceptance_source_discovery:{status}")

        elif discovery is not None and not isinstance(discovery, dict):
            gaps.append("acceptance_source_discovery_malformed")

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
