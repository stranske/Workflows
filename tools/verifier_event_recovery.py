"""Classify retained execution evidence; never invoke or retry an evaluator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def incomplete_cause(
    manifest: dict[str, Any], *, directory: Path, step_outcome: str
) -> dict[str, Any]:
    """Permit retry only on positive no-evaluation evidence, never absent output.

    The evaluator's exception path can return used_llm=False after attempting a
    provider call. Such errored payloads are therefore deliberately uncertain.
    """
    assessment = manifest.get("assessment_identity") or {}
    mode = assessment.get("mode")
    if mode not in {"evaluate", "compare"}:
        return _cause("uncertain_execution", "unsupported_assessment")
    payload_path = directory / ("evaluation.json" if mode == "evaluate" else "comparison.json")
    if not payload_path.exists():
        if step_outcome == "skipped":
            return _cause("known_no_evaluation", "evaluator_step_not_invoked")
        return _cause("uncertain_execution", "execution_payload_missing")
    try:
        from scripts.langchain.pr_verifier import EvaluationResult

        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        rows = [payload] if mode == "evaluate" else payload["results"]
        if not isinstance(rows, list) or not rows:
            raise ValueError("No result slots")
        # Do not coerce strings, integers, missing flags or unknown fields into
        # claims about invocation. Use the existing evaluator's result schema.
        if any(not isinstance(row, dict) or type(row.get("used_llm")) is not bool for row in rows):
            raise ValueError("Invocation evidence unavailable")
        results = [
            EvaluationResult.model_validate(row, strict=True, extra="forbid") for row in rows
        ]
        if step_outcome == "skipped" and any(result.used_llm for result in results):
            return _cause("uncertain_execution", "contradictory_execution_evidence")
        if any(result.used_llm for result in results):
            return _cause("recover_existing_evaluation", "retained_provider_evaluation")
        if any(result.error or result.verdict != "UNVERIFIABLE_INPUT" for result in results):
            return _cause("uncertain_execution", "errored_or_contradictory_no_evaluation_payload")
        if mode == "compare":
            from tools.llm_registry import resolve_slots

            overrides = [
                assessment.get("model") or None,
                assessment.get("model2") or assessment.get("model") or None,
            ]
            slots = resolve_slots()[:2]
            expected = [
                (slot.provider, override or slot.model)
                for slot, override in zip(slots, overrides, strict=True)
            ]
            actual = [(result.provider_used, result.model) for result in results]
            if len(expected) != 2 or len(set(expected)) != 2 or sorted(actual) != sorted(expected):
                return _cause("uncertain_execution", "configured_result_slots_incomplete")
        receipt_path = directory / "evaluation-execution.json"
        if mode == "evaluate" and receipt_path.exists():
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if receipt.get("exit_code") != 0 or receipt.get("status") in {
                "process_failed",
                "retention_failed",
                "output_truncated",
                "invalid_output",
            }:
                return _cause(
                    "uncertain_execution", "execution_receipt_does_not_establish_no_evaluation"
                )
        return _cause("known_no_evaluation", "validated_no_evaluation")
    except (ImportError, OSError, ValueError, KeyError, TypeError):
        return _cause("uncertain_execution", "execution_payload_invalid_or_unavailable")


def _cause(cause: str, reason: str) -> dict[str, Any]:
    return {
        "retry_kind": cause,
        "retryable": cause == "known_no_evaluation",
        "failure_cause": reason,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--step-outcome", default="")
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        result = incomplete_cause(manifest, directory=Path.cwd(), step_outcome=args.step_outcome)
    except (OSError, ValueError, TypeError):
        result = _cause("uncertain_execution", "execution_manifest_invalid_or_unavailable")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    import sys

    # The reusable's authoritative checkout, not a caller-local scripts package.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    raise SystemExit(main())
