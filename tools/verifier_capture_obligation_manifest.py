"""Derive a lossless capture obligation manifest from generated verifier context.

Source issue #3820 requires an auditable contract for which evidence must be
present before expanded native provider invocation. This module reads the
builder-emitted context source coverage inventory and names per-source
obligations without mutating captured artifacts.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

SCHEMA = "workflows-verifier-capture-obligation-manifest/v1"
_COVERAGE_BLOCK_RE = re.compile(
    r"## Context source coverage\s+```json\s*(\{.*?\})\s*```",
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


def parse_context_source_coverage(context_text: str) -> dict[str, Any] | None:
    match = _COVERAGE_BLOCK_RE.search(context_text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


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
        for record in coverage.get("changed_code_sources") or []:
            if not isinstance(record, dict):
                gaps.append("changed_code_sources_malformed")
                continue
            obligation = _obligation_from_record("changed_code", record)
            obligations.append(obligation)
            if require_full_changed_code and obligation.status != "included":
                gaps.append(f"changed_code:{obligation.source}:{obligation.status}")

        for record in coverage.get("acceptance_evidence_sources") or []:
            if not isinstance(record, dict):
                gaps.append("acceptance_evidence_sources_malformed")
                continue
            obligation = _obligation_from_record("acceptance_evidence", record)
            obligations.append(obligation)
            if obligation.status in {"truncated", "omitted", "unavailable"}:
                gaps.append(f"acceptance_evidence:{obligation.source}:{obligation.status}")

        discovery = coverage.get("acceptance_source_discovery")
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

        artifact = coverage.get("full_diff_artifact")
        if isinstance(artifact, dict):
            status = str(artifact.get("status") or "unavailable")
            obligations.append(
                SourceObligation(
                    source=str(artifact.get("source") or "verifier-pr-diff.patch"),
                    kind="full_diff_artifact",
                    status=status,
                    included_chars=artifact.get("chars"),
                    total_chars=artifact.get("chars"),
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
