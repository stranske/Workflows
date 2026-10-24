"""Classify retained execution evidence; never invoke or retry an evaluator."""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import os
import re
import zipfile
from pathlib import Path
from typing import Any


def incomplete_cause(
    manifest: dict[str, Any],
    *,
    directory: Path,
    step_outcome: str,
    publication_outcome: str = "",
    publication_effect: str = "",
) -> dict[str, Any]:
    """Permit retry only on positive no-evaluation evidence, never absent output.

    The evaluator's exception path can return used_llm=False after attempting a
    provider call. Such errored payloads are therefore deliberately uncertain.
    """
    retained = manifest.get("retained_revalidation")
    if isinstance(retained, dict):
        if retained.get("schema") != "retained-revalidation/v1" or not re.fullmatch(
            r"[0-9a-f]{64}", str(retained.get("recovery_key", ""))
        ):
            return _cause("uncertain_execution", "retained_revalidation_identity_unavailable")
        # No provider step runs for this mode. That does NOT prove a report POST
        # had no effect: only a skipped publisher or its pre-POST flag does so.
        no_publication = (
            publication_outcome in {"failure", "cancelled", "skipped"}
            and publication_effect == "none"
        ) or (publication_outcome == "skipped" and publication_effect == "")
        effect = "none" if no_publication else "uncertain"
        return {
            **_cause(
                "known_no_evaluation" if no_publication else "uncertain_execution",
                (
                    "retained_revalidation_before_publication"
                    if no_publication
                    else "retained_revalidation_publication_uncertain"
                ),
            ),
            "retained_revalidation": {
                **retained,
                "provider_generation_performed": False,
                "publication_effect": effect,
            },
        }
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


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def revalidate_retained(*, directory: Path) -> dict[str, Any]:
    """Revalidate authenticated retained bytes without executing any evaluator.

    The origin file is written by the trusted Actions API collector in this
    same job, never accepted as a workflow input. Originals remain immutable.
    A new execution receipt describes revalidation, not a second provider call.
    """
    from tools.verifier_corpus_evidence import (
        authoritative_verifier,
        event_metadata,
        validated_payload,
    )

    origin_raw = (directory / "verification-recovery-origin.json").read_bytes()
    origin = json.loads(origin_raw)
    selector = json.loads(os.environ["VERIFICATION_RECOVERY"])
    if (
        origin.get("schema") != "workflows-retained-origin/v1"
        or origin.get("repository", "").lower() != os.environ["GITHUB_REPOSITORY"].lower()
        or origin.get("current_run_id") != os.environ["GITHUB_RUN_ID"]
        or set(selector) != {"run_id", "run_attempt", "artifact_id"}
        or any(type(value) is not int or value < 1 for value in selector.values())
        or str(selector["run_id"]) != origin.get("source_run_id")
        or str(selector["run_attempt"]) != origin.get("source_run_attempt")
        or selector["artifact_id"] != origin.get("artifact_id")
        or int(origin["source_run_id"]) >= int(origin["current_run_id"])
    ):
        raise ValueError("Authenticated recovery origin/current job mismatch")
    archive = (directory / "verification-recovery-source.zip").read_bytes()
    if (
        len(archive) > 8388608
        or len(archive) != origin["archive_bytes"]
        or _sha(archive) != origin["archive_sha256"]
    ):
        raise ValueError("Authenticated retained archive changed")
    with zipfile.ZipFile(io.BytesIO(archive)) as opened:
        entries = opened.infolist()
        names = [entry.filename for entry in entries]
        if (
            len(entries) > 80
            or len(set(names)) != len(names)
            or sum(entry.file_size for entry in entries) > 33554432
            or any(
                entry.flag_bits & 1
                or entry.is_dir()
                or "/" in entry.filename
                or "\\" in entry.filename
                or entry.filename in {".", ".."}
                or ((entry.external_attr >> 16) & 0o170000) == 0o120000
                for entry in entries
            )
        ):
            raise ValueError("Unsafe or incomplete retained archive inventory")
        blobs = {entry.filename: opened.read(entry) for entry in entries}
    current = event_metadata(directory / "verification-event-manifest.json")
    event = current["verification_event"]
    assessment = current["assessment_identity"]
    mode = assessment["mode"]
    if mode not in {"evaluate", "compare"}:
        raise ValueError("Unsupported retained assessment mode")
    stem = "evaluation" if mode == "evaluate" else "comparison"
    required = {
        f"{stem}.json",
        f"{stem}-execution.json",
        "verifier-input-manifest.json",
        "verification-event-manifest.json",
        "verifier-context.md",
        "verifier-pr-diff.patch",
        "verifier-diff-summary.md",
    }
    if not required.issubset(blobs):
        raise ValueError("Mandatory retained source members missing")
    original_event = json.loads(blobs["verification-event-manifest.json"])
    if (
        original_event.get("verification_event") != event
        or original_event.get("assessment_identity") != assessment
        or original_event.get("predecessor_event_id") != current.get("predecessor_event_id")
        or origin.get("verification_event") != event
        or origin.get("assessment_identity") != assessment
        or _sha(_canonical(original_event["request"])) != event["request_sha256"]
        or _sha(_canonical(original_event["material"])) != event["material_sha256"]
    ):
        raise ValueError("Retained assessment is not applicable to current immutable request")
    snapshot = json.loads(blobs["verifier-input-manifest.json"])
    old_receipt = json.loads(blobs[f"{stem}-execution.json"])
    raw = blobs[f"{stem}.json"]
    output = old_receipt.get("outputs", {}).get(f"{stem}.json", {})
    if (
        snapshot.get("schema") != "workflows-verifier-input-snapshot/v1"
        or snapshot.get("capture_kind") != "production"
        or snapshot.get("repository", "").lower() != event["repo"]
        or str(snapshot.get("pr")) != event["pr"]
        or snapshot.get("merge_sha") != event["evaluated_sha"]
        or snapshot.get("mode") != mode
        or str(snapshot.get("source_run_id")) != origin["source_run_id"]
        or old_receipt.get("repository", "").lower() != event["repo"]
        or str(old_receipt.get("source_run_id")) != origin["source_run_id"]
        or str(old_receipt.get("source_run_attempt")) != origin["source_run_attempt"]
        or old_receipt.get("schema") != f"workflows-verifier-{stem}-execution/v1"
        or old_receipt.get("mode") != mode
        or type(old_receipt.get("exit_code")) is not int
        or old_receipt["exit_code"] != 0
        or (
            old_receipt.get("input_manifest", {}).get("sha256")
            != _sha(blobs["verifier-input-manifest.json"])
            and not (mode == "compare" and "input_manifest" not in old_receipt)
        )
        or output.get("sha256") != _sha(raw)
        or output.get("bytes") != len(raw)
        or output.get("original_sha256", _sha(raw)) != _sha(raw)
        or output.get("original_bytes", len(raw)) != len(raw)
        or output.get("original_complete", mode == "compare") is not True
        or output.get("truncated", False if mode == "compare" else None) is not False
        or output.get("redacted", False) is not False
        or output.get("retention_error_type")
    ):
        raise ValueError("Retained result execution/input join incomplete")
    for key, name in [
        ("context_sha256", "verifier-context.md"),
        ("diff_sha256", "verifier-pr-diff.patch"),
        ("diff_summary_sha256", "verifier-diff-summary.md"),
    ]:
        if snapshot.get(key) != _sha(blobs[name]):
            raise ValueError("Retained original input hash mismatch")
    if snapshot["diff_sha256"] != original_event["material"]["code"]["diff_sha256"]:
        raise ValueError("Retained diff differs from authenticated event")
    payload = json.loads(raw)
    rows, verdict, available = validated_payload(payload, mode=mode)
    if mode == "evaluate":
        requested_provider = assessment.get("provider")
        requested_model = assessment.get("model")
        provider_label = rows[0].get("provider_used") or ""
        actual_provider = authoritative_verifier()._provider_family(provider_label)
        actual_model = rows[0].get("model") or (
            provider_label.split("/", 1)[1] if "/" in provider_label else None
        )
        if (requested_provider and actual_provider != requested_provider) or (
            requested_model and actual_model != requested_model
        ):
            raise ValueError("Retained served reviewer differs from requested assessment")
    if not available or verdict not in {"PASS", "CONCERNS", "FAIL"}:
        raise ValueError("Retained output does not contain a complete usable evaluation")
    retained = directory / "retained-source" / origin["archive_sha256"]
    if (directory / "retained-source").is_symlink() or retained.is_symlink():
        raise ValueError("Retained source path is not owned")
    retained.mkdir(parents=True, exist_ok=True)
    if not retained.resolve().is_relative_to(directory.resolve()):
        raise ValueError("Retained source path escapes recovery workspace")
    for name, content in blobs.items():
        target = retained / name
        if target.is_symlink() or (target.exists() and target.read_bytes() != content):
            raise ValueError("Immutable retained source collision")
        if not target.exists():
            target.write_bytes(content)
    provenance = {
        "schema": "retained-revalidation/v1",
        "recovery_key": origin["recovery_key"],
        "provider_generation_performed": False,
        "source_run_id": origin["source_run_id"],
        "source_run_attempt": origin["source_run_attempt"],
        "artifact_id": origin["artifact_id"],
        "archive_sha256": origin["archive_sha256"],
        "origin_sha256": _sha(origin_raw),
        "original_receipt_sha256": _sha(blobs[f"{stem}-execution.json"]),
        "original_status": old_receipt.get("status"),
        "helper_sha": origin["helper_sha"],
        "validator_sha256": origin["validator_sha256"],
        "revalidator_sha256": _sha(Path(__file__).read_bytes()),
        "current_validator_sha256": _sha(
            (Path(__file__).resolve().parents[1] / "scripts/langchain/pr_verifier.py").read_bytes()
        ),
    }
    receipt = {
        "schema": f"workflows-verifier-{stem}-execution/v1",
        "mode": mode,
        "status": "completed",
        "exit_code": 0,
        "decision_available": True,
        "repository": event["repo"],
        "source_run_id": os.environ["GITHUB_RUN_ID"],
        "source_run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "verdict": verdict,
        "execution_kind": "authenticated_retained_revalidation",
        "retained_revalidation": provenance,
        "outputs": {
            f"{stem}.json": {
                "sha256": _sha(raw),
                "bytes": len(raw),
                "original_complete": True,
                "truncated": False,
            }
        },
    }
    (directory / f"{stem}.json").write_bytes(raw)
    (directory / f"{stem}-execution.json").write_text(json.dumps(receipt, indent=2) + "\n")
    # Rebuild the outgoing report from admitted data. Never republish an old
    # marker or model-authored top-level claim as current authority.
    report = f"## Retained {stem} revalidation\n\n**Verdict:** {verdict}\n\n"
    report += "Authenticated retained output revalidated; no provider was invoked again.\n\n"
    for row in rows:
        if len(rows) > 1:
            report += f"### {html.escape(str(row.get('provider_used') or 'Reviewer'))}\n\n"
        verifier = authoritative_verifier()
        reviewed = verifier.EvaluationResult.model_validate(row, strict=True)
        report += html.escape(verifier._review_count(reviewed)) + "\n\n"
        if row.get("summary"):
            report += html.escape(str(row["summary"])) + "\n\n"
        if row.get("concerns"):
            report += "### Concerns\n\n"
            report += "\n".join(
                f"- {html.escape(str(concern))}" for concern in row["concerns"] if concern
            )
            report += "\n\n"
    (directory / f"{stem}-comment.md").write_text(report + "\n")
    (directory / "verification-revalidation-receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )
    return receipt


def verify_revalidation_admission(receipt: dict[str, Any], *, directory: Path) -> bool:
    """Reject copied recovery receipts outside their collector-owned job/input."""
    from tools.verifier_corpus_evidence import event_metadata

    try:
        origin_raw = (directory / "verification-recovery-origin.json").read_bytes()
        origin = json.loads(origin_raw)
        selected = json.loads(os.environ["VERIFICATION_RECOVERY"])
        proof = receipt["retained_revalidation"]
        metadata = event_metadata(directory / "verification-event-manifest.json")
        stem = "evaluation" if receipt["mode"] == "evaluate" else "comparison"
        source = directory / "retained-source" / origin["archive_sha256"]
        return (
            proof["schema"] == "retained-revalidation/v1"
            and proof["provider_generation_performed"] is False
            and proof["origin_sha256"] == _sha(origin_raw)
            and proof["recovery_key"] == origin["recovery_key"]
            and origin["schema"] == "workflows-retained-origin/v1"
            and origin["repository"] == os.environ["GITHUB_REPOSITORY"].lower()
            and origin["current_run_id"] == os.environ["GITHUB_RUN_ID"]
            and receipt["source_run_id"] == os.environ["GITHUB_RUN_ID"]
            and receipt["source_run_attempt"] == os.environ["GITHUB_RUN_ATTEMPT"]
            and set(selected) == {"run_id", "run_attempt", "artifact_id"}
            and all(type(value) is int and value > 0 for value in selected.values())
            and selected
            == {
                "run_id": int(origin["source_run_id"]),
                "run_attempt": int(origin["source_run_attempt"]),
                "artifact_id": origin["artifact_id"],
            }
            and all(
                proof[key] == origin[key]
                for key in (
                    "source_run_id",
                    "source_run_attempt",
                    "artifact_id",
                    "helper_sha",
                    "validator_sha256",
                )
            )
            and proof["revalidator_sha256"] == _sha(Path(__file__).read_bytes())
            and proof["current_validator_sha256"]
            == _sha(
                (
                    Path(__file__).resolve().parents[1] / "scripts/langchain/pr_verifier.py"
                ).read_bytes()
            )
            and proof["archive_sha256"] == origin["archive_sha256"]
            and proof["original_receipt_sha256"]
            == _sha((source / f"{stem}-execution.json").read_bytes())
            and (source / f"{stem}.json").read_bytes() == (directory / f"{stem}.json").read_bytes()
            and origin["verification_event"] == metadata["verification_event"]
            and origin["assessment_identity"] == metadata["assessment_identity"]
        )
    except (OSError, ValueError, TypeError, KeyError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--revalidate-retained", action="store_true")
    parser.add_argument("--step-outcome", default="")
    parser.add_argument("--publication-outcome", default="")
    parser.add_argument("--publication-effect", default="")
    args = parser.parse_args()
    if args.revalidate_retained:
        result = revalidate_retained(directory=Path.cwd())
        if os.environ.get("GITHUB_OUTPUT"):
            with Path(os.environ["GITHUB_OUTPUT"]).open("a") as stream:
                stream.write(f"verdict={result['verdict']}\n")
        print(json.dumps(result, sort_keys=True))
        return 0
    if not args.manifest:
        parser.error("--manifest or --revalidate-retained is required")
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        result = incomplete_cause(
            manifest,
            directory=Path.cwd(),
            step_outcome=args.step_outcome,
            publication_outcome=args.publication_outcome,
            publication_effect=args.publication_effect,
        )
    except (OSError, ValueError, TypeError):
        result = _cause("uncertain_execution", "execution_manifest_invalid_or_unavailable")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    import sys

    # The reusable's authoritative checkout, not a caller-local scripts package.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    raise SystemExit(main())
