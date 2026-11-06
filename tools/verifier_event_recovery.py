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
        if (
            retained.get("schema") not in {"retained-revalidation/v1", "retained-revalidation/v2"}
            or not re.fullmatch(r"[0-9a-f]{64}", str(retained.get("recovery_key", "")))
            or (
                retained.get("schema") == "retained-revalidation/v2"
                and not _retained_v2_identity(retained, manifest)
            )
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
            cause = _cause("recover_existing_evaluation", "retained_provider_evaluation")
            repair = _input_repair(mode, directory, payload_path, results, step_outcome)
            # Provenance only: retryable stays false and no verdict is rewritten.
            return {**cause, "input_repair": repair} if repair else cause
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


def _input_repair(
    mode: str, directory: Path, payload_path: Path, results: list[Any], step_outcome: str
) -> dict[str, Any] | None:
    """Bind a completed-but-input-unverifiable result to its retained bytes.

    Returns None unless every provider slot actually ran, at least one reported
    UNVERIFIABLE_INPUT, and the retained receipt joins the result bytes exactly.
    The verdicts are copied, never interpreted; UNVERIFIABLE_INPUT is not accepted.
    """
    stem = payload_path.stem
    receipt_path = directory / f"{stem}-execution.json"
    if (
        step_outcome == "skipped"
        or not receipt_path.exists()
        or any(not result.used_llm or result.error for result in results)
        or not any(result.verdict == "UNVERIFIABLE_INPUT" for result in results)
    ):
        return None
    try:
        raw = payload_path.read_bytes()
        receipt_raw = receipt_path.read_bytes()
        receipt = json.loads(receipt_raw)
        output = receipt.get("outputs", {}).get(payload_path.name, {})
        if not isinstance(output, dict):
            return None
    except (OSError, ValueError, AttributeError):
        return None
    if (
        receipt.get("exit_code") != 0
        or receipt.get("mode") != mode
        or receipt.get("status")
        in {"process_failed", "retention_failed", "output_truncated", "invalid_output"}
        or output.get("sha256") != _sha(raw)
        or output.get("bytes") != len(raw)
        or output.get("truncated", False) is not False
    ):
        return None
    return {
        "result": {"path": payload_path.name, "raw_sha256": _sha(raw), "bytes": len(raw)},
        "receipt": {"path": receipt_path.name, "raw_sha256": _sha(receipt_raw)},
        "provider_verdicts": sorted(
            (
                {
                    "provider": result.provider_used or "",
                    "model": result.model or "",
                    "verdict": result.verdict,
                }
                for result in results
            ),
            key=lambda row: json.dumps(row, sort_keys=True),
        ),
    }


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


def _retained_v2_identity(retained: dict[str, Any], manifest: dict[str, Any]) -> bool:
    """Bind V2 lifecycle identity; this is not projection/result admission."""
    try:
        if retained.get("provider_generation_performed") is not False:
            return False
        selected = {
            "run_id": int(retained["source_run_id"]),
            "run_attempt": int(retained["source_run_attempt"]),
            "artifact_id": retained["artifact_id"],
        }
        if (
            any(type(value) is not int or value < 1 for value in selected.values())
            or str(selected["run_id"]) != retained["source_run_id"]
            or str(selected["run_attempt"]) != retained["source_run_attempt"]
        ):
            return False
        expected = {
            "schema": "retained-revalidation-key/v1",
            "event_id": manifest["verification_event"]["event_id"],
            "assessment": manifest["assessment_identity"],
            "selector": selected,
        }
        return retained["recovery_key"] == _sha(_canonical(expected))
    except (KeyError, TypeError, ValueError):
        return False


def _projection_compare_slots(payload: dict[str, Any], assessment: dict[str, Any]) -> None:
    """Require the exact existing configured native pair, retaining row order."""
    from tools.llm_registry import resolve_slots

    if not isinstance(assessment, dict) or assessment.get("mode") != "compare":
        raise ValueError("Original comparison assessment unavailable")
    slots = resolve_slots()[:2]
    overrides = [
        assessment.get("model") or None,
        assessment.get("model2") or assessment.get("model") or None,
    ]
    expected = [
        (slot.provider, override or slot.model)
        for slot, override in zip(slots, overrides, strict=True)
    ]
    rows = payload.get("results")
    if (
        len(slots) != 2
        or len(set(expected)) != 2
        or {provider for provider, _ in expected} != {"openai", "anthropic"}
        or not isinstance(rows, list)
        or len(rows) != 2
        or any(not isinstance(row, dict) for row in rows)
    ):
        raise ValueError("Original comparison requires the configured two native slots")
    actual = [(row.get("provider_used"), row.get("model")) for row in rows]
    if any(
        not isinstance(provider, str) or not isinstance(model, str) for provider, model in actual
    ) or sorted(actual) != sorted(expected):
        raise ValueError("Original comparison slot identity differs from configured pair")


# Audited complete original producer: _parse_llm_response preserves the first
# content_text on schema/repair failure. This is a source compatibility fact,
# never a caller-supplied claim about native execution or provider completion.
_ORIGINAL_FENCED_FINAL_PRODUCERS = frozenset(
    {"5e8f7a842231f16d8f5ba3ae1a48ed7625afa2feafe774963cdba066196fd0b8"}
)
_ORIGINAL_PARSE_ERROR = (
    "Schema repair policy escalated verifier output: " "Failed to parse JSON response after repair:"
)


def original_final_projection(
    payload: dict[str, Any],
    *,
    mode: str,
    validator_sha256: str,
    assessment: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Derive data from an audited original final; this grants no admission.

    Native acquisition, immutable archive/input/event joins and current-job
    admission are mandatory in the caller. No client is constructed here.
    """
    from tools.verifier_corpus_evidence import authoritative_verifier

    if validator_sha256 not in _ORIGINAL_FENCED_FINAL_PRODUCERS:
        raise ValueError("Original final producer provenance is not audited")
    verifier = authoritative_verifier()
    if mode == "compare":
        _projection_compare_slots(payload, assessment)
        if set(payload) != {"results", "report"} or not isinstance(payload["report"], str):
            raise ValueError("Original comparison projection shape unavailable")
        originals = payload["results"]
    elif mode == "evaluate":
        originals = [payload]
    else:
        raise ValueError("Unsupported original final projection mode")
    if not isinstance(originals, list) or not originals:
        raise ValueError("Original final result slots unavailable")
    projected, changes = [], []
    for index, original in enumerate(originals):
        row = verifier.EvaluationResult.model_validate(original, strict=True, extra="forbid")
        if not row.error:
            projected.append(original)
            continue
        coverage = row.input_coverage
        if (
            row.used_llm is not True
            or row.verdict != "CONCERNS"
            or not row.error.startswith(_ORIGINAL_PARSE_ERROR)
            or row.scores is not None
            or row.confidence is not None
            or row.concerns != []
            or row.summary is not None
            or row.files_not_reviewed != []
            or row.files_reviewed is not None
            or row.deferred_concerns != []
            or row.resolved_chunk_concerns != []
            or row.chunk_reviews != []
            or row.partition_recovery is not None
            or not isinstance(coverage, dict)
            or coverage.get("sufficient") is not True
            or not isinstance(row.raw_content, str)
            or not row.raw_content.strip().startswith("```")
        ):
            raise ValueError("Original row is not the audited final parse failure")
        parsed = verifier._parse_semantic_evaluation_payload(row.raw_content)
        if parsed.files_not_reviewed:
            raise ValueError("Original final requires coverage postprocessing, not raw projection")
        # Closed transition: payload fields come only from strict parsing of
        # the unchanged raw final. Only the DERIVED parse-error status clears;
        # the complete original row/error/refusal remains immutable history.
        derived = {**original, **parsed.model_dump(mode="json"), "error": None}
        verifier.EvaluationResult.model_validate(derived, strict=True, extra="forbid")
        projected.append(derived)
        changes.append(
            {
                "slot_index": index,
                "original_row_sha256": _sha(_canonical(original)),
                "original_error_sha256": _sha(row.error.encode()),
                "original_final_sha256": _sha(row.raw_content.encode()),
                "original_final_bytes": len(row.raw_content.encode()),
                "parsed_payload_sha256": _sha(_canonical(parsed.model_dump(mode="json"))),
                "derived_row_sha256": _sha(_canonical(derived)),
            }
        )
    if not changes:
        raise ValueError("No audited original parse failure to project")
    result = {**payload, "results": projected} if mode == "compare" else projected[0]
    proof = {
        "schema": "retained-original-final-projection/v1",
        "original_payload_sha256": _sha(_canonical(payload)),
        "derived_payload_sha256": _sha(_canonical(result)),
        "original_validator_sha256": validator_sha256,
        "slots": changes,
    }
    return result, proof


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
    projection = None
    if not available:
        payload, projection = original_final_projection(
            payload, mode=mode, validator_sha256=origin["validator_sha256"], assessment=assessment
        )
        raw = _canonical(payload)
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
        "schema": "retained-revalidation/v2" if projection else "retained-revalidation/v1",
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
    if projection is not None:
        provenance["original_final_projection"] = projection
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


def _verify_original_projection(proof, origin, source, directory, stem):
    """Recompute from immutable originals; never trust a supplied projection."""
    if set(proof) != {
        "schema",
        "recovery_key",
        "provider_generation_performed",
        "source_run_id",
        "source_run_attempt",
        "artifact_id",
        "archive_sha256",
        "origin_sha256",
        "original_receipt_sha256",
        "original_status",
        "helper_sha",
        "validator_sha256",
        "revalidator_sha256",
        "current_validator_sha256",
        "original_final_projection",
    }:
        return False
    original_bytes = (source / f"{stem}.json").read_bytes()
    archive = (directory / "verification-recovery-source.zip").read_bytes()
    if _sha(archive) != origin["archive_sha256"] or len(archive) != origin["archive_bytes"]:
        return False
    with zipfile.ZipFile(io.BytesIO(archive)) as opened:
        if opened.namelist().count(f"{stem}.json") != 1:
            return False
        if opened.read(f"{stem}.json") != original_bytes:
            return False
        if (
            opened.read(f"{stem}-execution.json")
            != (source / f"{stem}-execution.json").read_bytes()
        ):
            return False
    original = json.loads(original_bytes)
    derived, expected = original_final_projection(
        original,
        mode="evaluate" if stem == "evaluation" else "compare",
        validator_sha256=origin["validator_sha256"],
        assessment=origin["assessment_identity"],
    )
    return proof.get("original_final_projection") == expected and (
        directory / f"{stem}.json"
    ).read_bytes() == _canonical(derived)


# Published digests for the #4231/#4235 comparison archives. A digest is a claim.
# It does not authenticate archive bytes that GitHub no longer serves.
KNOWN_RETAINED_ARTIFACTS = {
    6390994169: {
        "pr": 4231,
        "run_id": 40143755394,
        "artifact_id": 12579928048,
        "published_archive_sha256": "c432b89fca7af092f08bc6cddf032b62b2f15ac0c727e75b9fcb30b9695e9d58",
    },
    6392557346: {
        "pr": 4235,
        "run_id": 40155311407,
        "artifact_id": 12584318436,
        "published_archive_sha256": "526dcef67f26160ece176b800e7a4d18a2e6d6883d7a2e4294b07570570486ab",
    },
}
EXPLICIT_EXPIRED_ARTIFACT_REJECTION = "explicit expired-artifact rejection"
AUTHENTICATED_RETAINED_READBACK = "authenticated retained readback"
IDENTITY_MISMATCH = "identity mismatch"
MISSING_STATUS = "missing status evidence"
INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE = "incomplete evidence"
INCOMPLETE_OBSERVATION_SET = "incomplete observation set"
OWNER_EXPIRY_DECISION = {
    "date": "2026-11-06",
    "fresh_provider_evaluation": False,
    "statement": "no fresh provider evaluation",
}
_ARCHIVE_BYTE_BOUND = 8388608


def _exact_int(value: Any, *, minimum: int = 1) -> int | None:
    if type(value) is not int or value < minimum:
        return None
    return value


def _archive_entry_unsafe(entry: zipfile.ZipInfo) -> bool:
    """Same archive rejection the retained revalidator uses for a source zip."""
    return bool(
        entry.flag_bits & 1
        or entry.is_dir()
        or "/" in entry.filename
        or "\\" in entry.filename
        or entry.filename in {".", ".."}
        or ((entry.external_attr >> 16) & 0o170000) == 0o120000
    )


def inspect_digest_bound_archive(
    raw: bytes | None,
    published_sha256: str | None,
    member_claims: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Apply archive-digest and optional member-hash rules to bytes already in hand.

    Absence is recorded. This does not fetch an artifact or invent a path.
    """
    if raw is None:
        return {"available": False, "authenticated": False, "sha256": None, "reason": "absent"}
    if len(raw) > _ARCHIVE_BYTE_BOUND:
        return {
            "available": False,
            "authenticated": False,
            "sha256": None,
            "reason": "archive_byte_bound",
        }
    digest = _sha(raw)
    published = (
        published_sha256
        if isinstance(published_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", published_sha256)
        else ""
    )
    if digest != published:
        return {
            "available": True,
            "authenticated": False,
            "sha256": digest,
            "reason": "digest_mismatch" if published else "published_digest_unavailable",
        }
    if member_claims is None:
        return {
            "available": True,
            "authenticated": True,
            "sha256": digest,
            "members": [],
            "reason": "digest_match",
        }
    if not isinstance(member_claims, list):
        return {
            "available": True,
            "authenticated": False,
            "sha256": digest,
            "reason": "member_authentication_failed",
        }
    member_results: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as opened:
            names = opened.namelist()
            infos = opened.infolist()
            if (
                len(names) != len(set(names))
                or len(infos) > 80
                or sum(info.file_size for info in infos) > 33554432
                or any(_archive_entry_unsafe(info) for info in infos)
            ):
                raise ValueError("unsafe archive")
            for claim in member_claims:
                if not isinstance(claim, dict):
                    raise ValueError("unsafe archive")
                path = claim.get("path")
                expect = claim.get("raw_sha256")
                matched = (
                    isinstance(path, str)
                    and names.count(path) == 1
                    and isinstance(expect, str)
                    and re.fullmatch(r"[0-9a-f]{64}", expect) is not None
                    and _sha(opened.read(path)) == expect
                )
                member_results.append({"path": path, "match": matched})
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        return {
            "available": True,
            "authenticated": False,
            "sha256": digest,
            "reason": "member_authentication_failed",
        }
    if any(row["match"] is False for row in member_results):
        return {
            "available": True,
            "authenticated": False,
            "sha256": digest,
            "members": member_results,
            "reason": "member_digest_mismatch",
        }
    return {
        "available": True,
        "authenticated": True,
        "sha256": digest,
        "members": member_results,
        "reason": "digest_match",
    }


def _read_local_archive(path_value: Any) -> tuple[bytes | None, dict[str, Any]]:
    """Read an optional local archive. A missing path is absence, not success."""
    absent = {"available": False, "authenticated": False, "sha256": None, "reason": "absent"}
    if path_value in (None, ""):
        return None, absent
    path = Path(str(path_value))
    try:
        if path.is_symlink() or not path.is_file():
            return None, absent
        return path.read_bytes(), {}
    except OSError:
        return None, {**absent, "reason": "unreadable"}


def _known_identity(observation: dict[str, Any], comment_id: int) -> tuple[bool, str | None]:
    known = KNOWN_RETAINED_ARTIFACTS.get(comment_id)
    if known is None:
        return False, None
    published = observation.get("published_archive_sha256")
    identity_ok = (
        _exact_int(observation.get("pr")) == known["pr"]
        and _exact_int(observation.get("run_id")) == known["run_id"]
        and _exact_int(observation.get("artifact_id")) == known["artifact_id"]
        and published in (None, "", known["published_archive_sha256"])
    )
    return identity_ok, known["published_archive_sha256"]


def classify_retained_artifact_outcome(observation: dict[str, Any]) -> dict[str, Any]:
    """Classify one retained artifact without calling a provider.

    A published provenance marker is not authentication of unavailable bytes.
    Local bytes are inspected only when a path is supplied.
    """
    comment_id = _exact_int(observation.get("comment_id"))
    if comment_id is None:
        return {
            "schema": "retained-artifact-outcome/v1",
            "comment_id": None,
            "outcome": INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE,
            "artifact_outcome": INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE,
            "reason": "comment_id_missing",
            "authenticated_readback": False,
            "native_admission_succeeded": False,
            "original_event_accepting": None,
            "provider_calls": None,
            "provider_generation_performed": False,
            "marker_published": False,
            "marker_authenticates_archive": False,
            "evidence_complete": False,
        }
    identity_ok, known_digest = _known_identity(observation, comment_id)
    published = observation.get("published_archive_sha256") or known_digest
    http_status = observation.get("artifact_http_status")
    if type(http_status) is not int:
        http_status = None
    expired = observation.get("artifact_expired")
    if expired is not None and type(expired) is not bool:
        expired = None
    member_claims = observation.get("member_claims")
    local_raw, local_report = _read_local_archive(observation.get("local_archive_path"))
    if local_raw is not None:
        local_report = inspect_digest_bound_archive(local_raw, published, member_claims)
    actions_raw = observation.get("actions_archive_bytes")
    actions_report = inspect_digest_bound_archive(
        actions_raw if isinstance(actions_raw, bytes) else None,
        published,
        member_claims,
    )
    actions_authenticated = (
        identity_ok
        and http_status == 200
        and expired is False
        and actions_report["authenticated"] is True
    )
    if not identity_ok:
        artifact_outcome = IDENTITY_MISMATCH
        reason = "known_subject_identity_mismatch"
    elif expired is True or (http_status == 404 and expired is None):
        artifact_outcome = EXPLICIT_EXPIRED_ARTIFACT_REJECTION
        reason = "artifact_expired_or_unavailable"
    elif http_status == 404 and expired is False:
        artifact_outcome = "contradictory artifact status"
        reason = "expired_flag_contradicts_http_status"
    elif http_status is None and actions_raw is None and expired is None:
        artifact_outcome = MISSING_STATUS
        reason = "artifact_status_missing"
    elif actions_authenticated:
        artifact_outcome = AUTHENTICATED_RETAINED_READBACK
        reason = "actions_archive_digest_match"
    else:
        artifact_outcome = "unauthenticated retained evidence"
        reason = str(actions_report.get("reason") or "unauthenticated")

    provider_calls = _exact_int(observation.get("provider_calls"), minimum=0)
    original_raw = observation.get("original_event_accepting")
    original_accepting = original_raw if type(original_raw) is bool else None
    outcome = artifact_outcome
    if provider_calls not in (None, 0):
        outcome = "provider call observed"
        reason = "provider_call_forbidden"
    elif original_accepting is True:
        outcome = "original event accepting"
        reason = "original_event_must_stay_nonaccepting"
    evidence_complete = provider_calls is not None and original_accepting is not None
    if not evidence_complete and outcome == artifact_outcome:
        reason = (
            "missing_original_event_acceptance"
            if original_accepting is None
            else "missing_or_invalid_provider_calls"
        )
    authenticated = artifact_outcome == AUTHENTICATED_RETAINED_READBACK
    admission = observation.get("admission_result")
    native_admission = False
    if authenticated and isinstance(admission, dict):
        event_id = admission.get("event_id")
        predecessor = admission.get("predecessor_event_id")
        native_admission = (
            admission.get("succeeded") is True
            and admission.get("evidence_source") == "native_admission"
            and isinstance(event_id, str)
            and re.fullmatch(r"[0-9a-f]{64}", event_id) is not None
            and isinstance(predecessor, str)
            and re.fullmatch(r"[0-9a-f]{64}", predecessor) is not None
            and event_id != predecessor
            and admission.get("original_event_accepting") is False
        )
    return {
        "schema": "retained-artifact-outcome/v1",
        "pr": observation.get("pr"),
        "comment_id": comment_id,
        "run_id": observation.get("run_id"),
        "artifact_id": observation.get("artifact_id"),
        "outcome": outcome,
        "artifact_outcome": artifact_outcome,
        "reason": reason,
        "authenticated_readback": authenticated,
        "native_admission_succeeded": native_admission,
        "original_event_accepting": original_accepting,
        "provider_calls": provider_calls,
        "provider_generation_performed": False,
        "marker_published": observation.get("marker_published") is True,
        "marker_authenticates_archive": False,
        "evidence_complete": evidence_complete,
        "collected_subject": (
            observation.get("subject") if isinstance(observation.get("subject"), dict) else None
        ),
        "comment_readback": {
            "status": observation.get("proof_status"),
            "body_sha256": observation.get("proof_body_sha256"),
        },
        "published_archive_sha256": published,
        "actions_archive": {"http_status": http_status, "expired": expired, **actions_report},
        "local_archive": local_report,
        "owner_decision": (
            OWNER_EXPIRY_DECISION
            if identity_ok and artifact_outcome == EXPLICIT_EXPIRED_ARTIFACT_REJECTION
            else None
        ),
    }


def _observation_from_collector_receipt(row: dict[str, Any]) -> dict[str, Any]:
    """Map a collector receipt onto classifier input without inventing counts."""
    if not isinstance(row, dict):
        return {}
    retained = (
        row.get("retained_artifact") if isinstance(row.get("retained_artifact"), dict) else {}
    )
    http_status = row.get("artifact_http_status", retained.get("status"))
    failures = (
        row.get("artifact_failures") if isinstance(row.get("artifact_failures"), list) else []
    )
    expired = row.get("artifact_expired")
    if expired is None and any(
        isinstance(item, dict) and item.get("kind") == "expired" for item in failures
    ):
        expired = True
    if type(http_status) is not int:
        details = " ".join(
            str(item.get("detail") or "") for item in failures if isinstance(item, dict)
        )
        artifact_id = row.get("artifact_id")
        if artifact_id is not None and str(artifact_id) in details and "Not Found" in details:
            http_status = 404
        else:
            http_status = None
    comment_id = row.get("comment_id", row.get("comment"))
    if comment_id is None and isinstance(row.get("proof"), list) and row["proof"]:
        proof = row["proof"][0] if isinstance(row["proof"][0], dict) else {}
        url = str(proof.get("url") or "")
        if "issuecomment-" in url and url.rsplit("issuecomment-", 1)[1].isdigit():
            comment_id = int(url.rsplit("issuecomment-", 1)[1])
    inventory = (
        row.get("archive_inventory") if isinstance(row.get("archive_inventory"), list) else []
    )
    first = inventory[0] if inventory and isinstance(inventory[0], dict) else {}
    return {
        "pr": row.get("pr"),
        "comment_id": comment_id,
        "run_id": row.get("run_id", first.get("run_id")),
        "artifact_id": row.get("artifact_id", first.get("artifact_id")),
        "subject": row.get("subject"),
        "proof_status": row.get("proof_status"),
        "proof_body_sha256": row.get("proof_body_sha256"),
        "marker_published": row.get("marker_published", False),
        "artifact_http_status": http_status,
        "artifact_expired": expired,
        "published_archive_sha256": row.get("published_archive_sha256"),
        "local_archive_path": row.get("local_archive_path"),
        "member_claims": row.get("member_claims"),
        "actions_archive_bytes": row.get("actions_archive_bytes"),
        "original_event_accepting": row.get("original_event_accepting"),
        "provider_calls": row.get("provider_calls"),
        "admission_result": row.get("admission_result"),
    }


def classify_retained_artifact_report(payload: dict[str, Any]) -> dict[str, Any]:
    """Classify both known #4231/#4235 comments and choose one operational phrase.

    The expiry phrase requires both comment ids once, explicit expiry for each,
    original events nonaccepting, and zero provider calls. Anything short of
    that stays a different phrase. Marker publication cannot authenticate bytes.
    """
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    if "observations" in payload and isinstance(payload.get("observations"), list):
        rows: list[Any] = payload["observations"]
    else:
        receipts = payload.get("receipts") if isinstance(payload.get("receipts"), list) else []
        rows = [_observation_from_collector_receipt(row) for row in receipts]
    classified = [
        (
            classify_retained_artifact_outcome(row)
            if isinstance(row, dict)
            else classify_retained_artifact_outcome({})
        )
        for row in rows
    ]
    comment_ids = [row.get("comment_id") for row in classified]
    known_ids = set(KNOWN_RETAINED_ARTIFACTS)
    pair_complete = len(classified) == 2 and set(comment_ids) == known_ids
    evidence_ready = all(row.get("evidence_complete") is True for row in classified)
    outcomes = {row.get("outcome") for row in classified}
    if not classified or not evidence_ready:
        phrase = INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE
        total_provider_calls = None
    elif not pair_complete:
        phrase = INCOMPLETE_OBSERVATION_SET
        total_provider_calls = sum(row.get("provider_calls") or 0 for row in classified)
    elif outcomes == {EXPLICIT_EXPIRED_ARTIFACT_REJECTION} and all(
        row.get("authenticated_readback") is False
        and row.get("native_admission_succeeded") is False
        and row.get("original_event_accepting") is False
        and row.get("provider_calls") == 0
        for row in classified
    ):
        phrase = EXPLICIT_EXPIRED_ARTIFACT_REJECTION
        total_provider_calls = 0
    elif outcomes == {AUTHENTICATED_RETAINED_READBACK}:
        phrase = AUTHENTICATED_RETAINED_READBACK
        total_provider_calls = 0
    elif len(outcomes) == 1:
        phrase = next(iter(outcomes))
        total_provider_calls = sum(row.get("provider_calls") or 0 for row in classified)
    else:
        phrase = "mixed retained-artifact outcomes"
        total_provider_calls = sum(row.get("provider_calls") or 0 for row in classified)
    return {
        "schema": "retained-artifact-report/v1",
        "operational_outcome": phrase,
        "provider_calls": total_provider_calls,
        "provider_generation_performed": False,
        "context": context,
        "results": classified,
    }


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
            proof["schema"] in {"retained-revalidation/v1", "retained-revalidation/v2"}
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
            and (
                (
                    proof["schema"] == "retained-revalidation/v1"
                    and "original_final_projection" not in proof
                    and (source / f"{stem}.json").read_bytes()
                    == (directory / f"{stem}.json").read_bytes()
                )
                or (
                    proof["schema"] == "retained-revalidation/v2"
                    and _verify_original_projection(proof, origin, source, directory, stem)
                )
            )
            and origin["verification_event"] == metadata["verification_event"]
            and origin["assessment_identity"] == metadata["assessment_identity"]
        )
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--revalidate-retained", action="store_true")
    parser.add_argument("--classify-retained-artifact", type=Path)
    parser.add_argument("--step-outcome", default="")
    parser.add_argument("--publication-outcome", default="")
    parser.add_argument("--publication-effect", default="")
    args = parser.parse_args()
    modes = sum(
        [
            bool(args.manifest),
            bool(args.revalidate_retained),
            bool(args.classify_retained_artifact),
        ]
    )
    if modes != 1:
        parser.error(
            "exactly one of --manifest, --revalidate-retained, "
            "or --classify-retained-artifact is required"
        )
    if args.classify_retained_artifact:
        try:
            payload = json.loads(args.classify_retained_artifact.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("retained artifact payload must be an object")
            result = classify_retained_artifact_report(payload)
        except (OSError, ValueError, TypeError, KeyError):
            result = {
                "schema": "retained-artifact-report/v1",
                "operational_outcome": INCOMPLETE_RETAINED_ARTIFACT_EVIDENCE,
                "provider_calls": None,
                "provider_generation_performed": False,
                "results": [],
            }
        print(json.dumps(result, sort_keys=True))
        return 0
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
