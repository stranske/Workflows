#!/usr/bin/env python3
"""Build a reviewable MAINT-78 case from a production verifier artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from tools.model_eval_snapshots import snapshot_digest


def create_case(
    artifact: Path,
    *,
    case_id: str,
    expected_verdict: str,
    category: str,
    adjudication_evidence: str,
    adjudicated_by: str,
    adjudication_rationale: str,
    context_override: Path | None = None,
    diff_summary_override: Path | None = None,
    mutation_note: str = "",
) -> dict:
    manifest = json.loads((artifact / "verifier-input-manifest.json").read_text())
    if manifest.get("schema") != "workflows-verifier-input-snapshot/v1":
        raise ValueError("production input manifest is absent or has the wrong schema")
    context = (artifact / "verifier-context.md").read_text()
    diff_summary = (artifact / "verifier-diff-summary.md").read_text()
    if hashlib.sha256(context.encode()).hexdigest() != manifest["context_sha256"]:
        raise ValueError("production context does not match the captured manifest")
    if hashlib.sha256(diff_summary.encode()).hexdigest() != manifest["diff_summary_sha256"]:
        raise ValueError("production diff summary does not match the captured manifest")
    if expected_verdict not in {"PASS", "NON_PASS"}:
        raise ValueError("expected verdict must be PASS or NON_PASS")
    if not all((case_id, category, adjudication_evidence, adjudicated_by, adjudication_rationale)):
        raise ValueError("case identity and independent adjudication fields are required")
    is_mutation = context_override is not None or diff_summary_override is not None
    if is_mutation and (context_override is None or diff_summary_override is None):
        raise ValueError(
            "controlled defect must replace both context and diff summary consistently"
        )
    if is_mutation and not mutation_note:
        raise ValueError("controlled defect requires a mutation note")
    if not is_mutation and mutation_note:
        raise ValueError("mutation note requires a controlled defect override")
    if context_override:
        context = context_override.read_text()
    if diff_summary_override:
        diff_summary = diff_summary_override.read_text()
    snapshot = {
        "context": context,
        "diff_summary": diff_summary,
        "chain_depth": int(manifest["chain_depth"]),
        "merge_sha": manifest["merge_sha"],
        "source_run_id": str(manifest["source_run_id"]),
        "adjudication_evidence": adjudication_evidence,
        "adjudicated_by": adjudicated_by,
        "adjudication_rationale": adjudication_rationale,
        "input_kind": "controlled_defect" if is_mutation else "production_capture",
    }
    if is_mutation:
        snapshot["mutation_note"] = mutation_note
        snapshot["source_context_sha256"] = manifest["context_sha256"]
        snapshot["source_diff_summary_sha256"] = manifest["diff_summary_sha256"]
    snapshot["sha256"] = snapshot_digest(snapshot)
    return {
        "case_id": case_id,
        "repo": manifest["repository"],
        "pr": int(manifest["pr"]),
        "expected_verdict": expected_verdict,
        "category": category,
        "production_snapshot": snapshot,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--expected-verdict", choices=("PASS", "NON_PASS"), required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--adjudication-evidence", required=True)
    parser.add_argument("--adjudicated-by", required=True)
    parser.add_argument("--adjudication-rationale", required=True)
    parser.add_argument("--context-override", type=Path)
    parser.add_argument("--diff-summary-override", type=Path)
    parser.add_argument("--mutation-note", default="")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    case = create_case(
        args.artifact,
        case_id=args.case_id,
        expected_verdict=args.expected_verdict,
        category=args.category,
        adjudication_evidence=args.adjudication_evidence,
        adjudicated_by=args.adjudicated_by,
        adjudication_rationale=args.adjudication_rationale,
        context_override=args.context_override,
        diff_summary_override=args.diff_summary_override,
        mutation_note=args.mutation_note,
    )
    args.output.write_text(json.dumps(case, indent=2) + "\n")


if __name__ == "__main__":
    main()
