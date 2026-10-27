"""Publish and validate the exact verifier decision used by corpus harvesting."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

MARKER = "verifier-corpus-decision/v1"


def event_metadata(path: Path) -> dict[str, Any]:
    """Read only the collector's exact event, never a caller-provided digest."""
    manifest = json.loads(path.read_text(encoding="utf-8"))
    event = manifest["verification_event"]
    fields = (
        "schema",
        "repo",
        "pr",
        "head_sha",
        "evaluated_sha",
        "request_sha256",
        "material_sha256",
    )
    core = {key: event[key] for key in fields}
    actual = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if (
        event.get("schema") != "verification-event/v1"
        or actual != event.get("event_id")
        or not re.fullmatch(r"[0-9a-f]{40}", str(event.get("head_sha")))
        or not re.fullmatch(r"[0-9a-f]{40}", str(event.get("evaluated_sha")))
        or any(
            not re.fullmatch(r"[0-9a-f]{64}", str(event.get(key)))
            for key in ("request_sha256", "material_sha256")
        )
    ):
        raise ValueError("Invalid collector verification event")
    metadata = {"verification_event": event, "assessment_identity": manifest["assessment_identity"]}

    def content_hash(value: Any) -> str:
        return hashlib.sha256(
            json.dumps(
                value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            ).encode("utf-8")
        ).hexdigest()

    request = manifest.get("request")
    material = manifest.get("material")
    if ("request" in manifest or "material" in manifest) and (
        not isinstance(request, dict)
        or not isinstance(material, dict)
        or request.get("schema") != "verification-request/v1"
        or material.get("schema") != "verification-material/v1"
        or content_hash(request) != event["request_sha256"]
        or content_hash(material) != event["material_sha256"]
    ):
        raise ValueError("Collected inputs do not match event hashes")
    rows = material.get("required_evidence", []) if isinstance(material, dict) else []
    corrective = (
        [
            row
            for row in rows
            if isinstance(row, dict) and row.get("kind") == "corrective_instruction"
        ]
        if isinstance(rows, list)
        else []
    )
    selected = json.loads(os.environ.get("VERIFICATION_MATERIAL") or "[]")
    if (
        isinstance(selected, list)
        and any(
            isinstance(row, dict) and row.get("kind") == "corrective_instruction"
            for row in selected
        )
        and not corrective
    ):
        raise ValueError("Selected corrective input missing from collector manifest")
    if corrective:
        if (
            len(corrective) != 1
            or not isinstance(request, dict)
            or request.get("schema") != "verification-request/v1"
            or material.get("schema") != "verification-material/v1"
            or content_hash(request) != event["request_sha256"]
            or content_hash(material) != event["material_sha256"]
        ):
            raise ValueError("Corrective input does not match collected event hashes")
        row = corrective[0]
        if (
            row.get("authority") != "native_same_principal_dispatch"
            or row.get("owner_instruction", {}).get("repository") != event["repo"]
            or row.get("corrective_pr", {}).get("number") != event["pr"]
            or row.get("corrective_pr", {}).get("head_sha") != event["head_sha"]
        ):
            raise ValueError("Corrective input native subject differs")
        # The existing authenticated result artifact retains the COMPLETE
        # request/material. A consumer must fetch that exact native artifact and
        # recompute both event hashes: this compact row alone is not scope proof.
        metadata["corrective_verification_input"] = {
            "schema": "closer-corrective-verification-input/v1",
            "verification_event": event,
            "corrective_instruction": row,
        }
    basis = manifest.get("verification_request_basis")
    if "verification_request_basis" in manifest:
        if not isinstance(basis, str) or not re.fullmatch(r"[0-9a-f]{64}", basis):
            raise ValueError("Invalid verification request basis")
        metadata["verification_request_basis"] = basis
    predecessor = manifest.get("predecessor_event_id")
    if predecessor:
        if not re.fullmatch(r"[0-9a-f]{64}", str(predecessor)):
            raise ValueError("Invalid verification predecessor")
        metadata["predecessor_event_id"] = predecessor
    return metadata


def decision_from_results(
    results: list[dict[str, Any]], identity: dict[str, str], *, ci_failed: str | None = None
) -> dict[str, Any] | None:
    """Retain usable decisions with the workflow's trusted merge-CI hard gate."""
    verdicts = [str(result.get("verdict", "")).upper() for result in results]
    if not results or not all(
        result.get("used_llm") is True and not result.get("error") for result in results
    ):
        return None
    if any(verdict not in {"PASS", "CONCERNS", "FAIL", "NON_PASS"} for verdict in verdicts):
        return None
    # The context step emits exactly true/false. Missing or malformed context
    # cannot establish an authoritative disposition for corpus harvesting.
    if ci_failed not in {"true", "false"}:
        return None
    return {
        "schema": MARKER,
        **identity,
        "verdict": (
            "PASS" if ci_failed == "false" and all(v == "PASS" for v in verdicts) else "NON_PASS"
        ),
        "ci_failed": ci_failed == "true",
        "provider_verdicts": verdicts,
    }


def authoritative_verifier():
    """Import only the validator shipped beside this checked-out helper."""
    root = Path(__file__).resolve().parents[1]
    source = root / "scripts/langchain/pr_verifier.py"
    if not source.is_file():
        raise ImportError("Authoritative Workflows verifier checkout unavailable")
    sys.path.insert(0, str(root))
    from scripts.langchain import pr_verifier

    if Path(pr_verifier.__file__).resolve() != source.resolve():
        raise ImportError("Verifier validator resolved outside authoritative checkout")
    return pr_verifier


def _semantic_rows_complete(payload, results, configured, verifier) -> bool:
    """Join flat report rows to the authenticated source-owned cell matrix."""
    from tools.verifier_semantic_acceptance import freeze_judge_slots, plan_request_matrix

    try:
        if len(configured) != 2 or len(set(configured)) != 2:
            return False
        envelope = payload["semantic_acceptance"]
        unsigned = {key: value for key, value in envelope.items() if key != "signature"}
        if envelope.get("schema") != verifier.SEMANTIC_ENVELOPE_SCHEMA or not hmac.compare_digest(
            envelope.get("signature", ""), verifier._semantic_envelope_signature(unsigned)
        ):
            return False
        execution = envelope["execution"]
        slots = freeze_judge_slots(execution["slots"])
        if sorted((slot["provider"], slot["model"]) for slot in slots) != sorted(configured):
            return False
        expected = plan_request_matrix(execution["plan"], list(slots))
        admitted = envelope["admission"]
        cells = admitted["results"]
        identities = [(cell["slot_id"], cell["package_id"]) for cell in cells]
        if (
            not expected
            or len(results) != len(cells)
            or len(cells) != len(expected)
            or len(set(identities)) != len(identities)
            or set(identities) != expected
            or admitted.get("expected_cells") != [list(cell) for cell in sorted(expected)]
            or admitted.get("missing_cells") != []
            or admitted.get("errors") != []
        ):
            return False
        by_slot = {slot["slot_id"]: slot for slot in slots}
        for row, cell in zip(results, cells, strict=True):
            slot = by_slot[cell["slot_id"]]
            evaluation = cell.get("evaluation") or {}
            projected = verifier.EvaluationResult(
                verdict=cell["verdict"],
                concerns=list(cell.get("findings", [])),
                scores=evaluation.get("scores"),
                confidence=evaluation.get("confidence"),
                summary=evaluation.get("summary"),
                raw_content=cell.get("raw_content"),
                provider_used=slot["provider"],
                model=slot["model"],
                used_llm=cell.get("execution_error") is None,
                error=cell.get("execution_error"),
            )
            if row.model_dump() != projected.model_dump():
                return False
        return True
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return False


def validated_payload(payload: Any, *, mode: str) -> tuple[list[dict[str, Any]], str, bool]:
    """Use the checked-out Workflows validator, never caller-local Python code.

    This validates retained output only; importing the schema/classifiers does
    not construct clients or invoke providers. Expanded comparison retains its
    existing conservative classifier, including a configured FAIL with a missing
    sibling, while incomplete slots cannot publish a terminal corpus decision.
    """
    pr_verifier = authoritative_verifier()
    if mode == "evaluate":
        result = pr_verifier.EvaluationResult.model_validate(payload, strict=True)
        rows = [result.model_dump()]
        return rows, result.verdict, result.used_llm is True and not result.error
    if mode != "compare":
        raise ValueError("Unsupported verifier mode")
    expanded = os.environ.get("VERIFIER_EVIDENCE_PROFILE") == "expanded"
    if expanded:
        verdict = pr_verifier.expanded_comparison_verdict(
            payload,
            model1=os.environ.get("VERIFIER_MODEL") or None,
            model2=os.environ.get("VERIFIER_MODEL2") or None,
        )
    raw = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        if expanded:
            return [], verdict, False
        raise ValueError("Comparison results must be an array")
    try:
        results = [pr_verifier.EvaluationResult.model_validate(row, strict=True) for row in raw]
    except ValueError:
        if expanded:
            return [], verdict, False
        raise
    if not expanded:
        verdict = pr_verifier.comparison_verdict(results)
    available = bool(results) and all(row.used_llm is True and not row.error for row in results)
    if expanded:
        from tools.llm_registry import resolve_slots

        slots = resolve_slots()[:2]
        model1 = os.environ.get("VERIFIER_MODEL") or os.environ.get("LANGCHAIN_MODEL")
        model2 = os.environ.get("VERIFIER_MODEL2") or os.environ.get("VERIFIER_MODEL") or None
        expected = [
            (slot.provider, override or slot.model)
            for slot, override in zip(slots, [model1, model2], strict=False)
        ]
        if pr_verifier._semantic_mode():
            available = available and _semantic_rows_complete(
                payload, results, expected, pr_verifier
            )
        else:
            actual = [(row.provider_used, row.model) for row in results]
            available = (
                available
                and len(expected) == len(actual) == 2
                and len(set(expected)) == 2
                and all(
                    isinstance(provider, str) and isinstance(model, str)
                    for provider, model in actual
                )
                and sorted(actual) == sorted(expected)
            )
    return [row.model_dump() for row in results], verdict, available


def admitted_decision(
    payload_path: Path,
    receipt_path: Path,
    identity: dict[str, str],
    *,
    mode: str,
    ci_failed: str | None,
) -> dict[str, Any] | None:
    """Join one validated retained result to its exact execution receipt."""
    raw = payload_path.read_bytes()
    receipt_raw = receipt_path.read_bytes()
    receipt = json.loads(receipt_raw)
    if not isinstance(receipt, dict) or not isinstance(receipt.get("outputs"), dict):
        return None
    ref = receipt["outputs"].get(payload_path.name, {})
    if not isinstance(ref, dict):
        return None
    schema_name = {"evaluate": "evaluation", "compare": "comparison"}[mode]
    if (
        receipt.get("schema") != f"workflows-verifier-{schema_name}-execution/v1"
        or receipt.get("mode") != mode
        or receipt.get("status") != "completed"
        or receipt.get("decision_available") is not True
        or type(receipt.get("exit_code")) is not int
        or receipt["exit_code"] != 0
        or not isinstance(receipt.get("repository"), str)
        or receipt["repository"].lower() != identity["repo"].lower()
        or str(receipt.get("source_run_id")) != identity["run_id"]
        or str(receipt.get("source_run_attempt")) != identity["run_attempt"]
        or ref.get("sha256") != hashlib.sha256(raw).hexdigest()
        or type(ref.get("bytes")) is not int
        or ref["bytes"] != len(raw)
        or ref.get("truncated", False) is not False
        or ref.get("original_complete", True) is not True
        or ref.get("retention_error_type")
    ):
        return None
    validator = authoritative_verifier()
    revalidation = receipt.get("retained_revalidation")
    if receipt.get("execution_kind") == "authenticated_retained_revalidation":
        # Authority comes from this job's authenticated Actions collector, not
        # an input digest or a user-supplied replacement execution receipt.
        from tools.verifier_event_recovery import verify_revalidation_admission

        if not verify_revalidation_admission(receipt, directory=payload_path.parent):
            return None
    elif revalidation is not None:
        return None
    payload = json.loads(raw)
    raw_rows = [payload] if mode == "evaluate" else payload["results"]
    if not isinstance(raw_rows, list) or not raw_rows:
        return None
    rows = [
        validator.EvaluationResult.model_validate(row, strict=True).model_dump() for row in raw_rows
    ]
    verdict = receipt.get("verdict", rows[0]["verdict"] if mode == "evaluate" else None)
    if (
        verdict not in {"PASS", "CONCERNS", "FAIL"}
        or (mode == "evaluate" and verdict != rows[0]["verdict"])
        or (verdict == "PASS" and any(row["verdict"] != "PASS" for row in rows))
    ):
        return None
    # The producer computed the authoritative classifier while its invocation
    # context (including an ephemeral semantic envelope key) was available.
    # Retained exact hashes bind that admitted classification; do not rerun a
    # different classifier later or require keeping private ephemeral keys.
    decision = decision_from_results(rows, identity, ci_failed=ci_failed)
    if decision is not None:
        # The authoritative comparison classifier may conservatively reject
        # PASS despite individual PASS strings (e.g. missing configured slots).
        if verdict != "PASS" and decision["verdict"] == "PASS":
            # Existing native consumers derive this schema's decision from
            # provider verdicts and the CI floor. Do not invent a provider
            # NON_PASS or publish an aggregate floor they cannot represent.
            return None
        if revalidation:
            decision["retained_revalidation"] = revalidation
        decision["result_admission"] = {
            "schema": "verifier-result-admission/v1",
            "mode": mode,
            "payload_sha256": hashlib.sha256(raw).hexdigest(),
            "execution_receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
        }
    return decision


def joined_decision(record: dict[str, Any]) -> dict[str, Any] | None:
    """Require a decision tied to this repository, PR, head and evaluated merge."""
    decision = record.get("verifier_decision")
    if not isinstance(decision, dict) or decision.get("schema") != MARKER:
        return None
    repo = str(record.get("repo", "")).strip().lower()
    pr = str(record.get("pr", ""))
    head = str(record.get("head_sha", ""))
    evaluated = str(record.get("merge_sha") or head)
    run = str(decision.get("run_id", ""))
    attempt = str(decision.get("run_attempt", ""))
    if (
        not re.fullmatch(r"[^/\s]+/[^/\s]+", repo)
        or not pr.isdigit()
        or not re.fullmatch(r"[0-9a-f]{40}", head)
        or not re.fullmatch(r"[0-9a-f]{40}", evaluated)
        or not run.isdigit()
        or not attempt.isdigit()
        or int(run) < 1
        or int(attempt) < 1
        or str(decision.get("repo", "")).lower() != repo
        or str(decision.get("pr", "")) != pr
        or decision.get("head_sha") != head
        or decision.get("evaluated_sha") != evaluated
        or decision.get("verdict") not in {"PASS", "NON_PASS"}
        or (decision.get("ci_failed") is True and decision.get("verdict") == "PASS")
        or not str(decision.get("source_url", ""))
        .lower()
        .startswith(f"https://github.com/{repo}/pull/{pr}#issuecomment-")
    ):
        return None
    return decision


def decision_from_comments(
    record: dict[str, Any], comments: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Read only the verifier bot's structured evidence, newest usable record first."""
    for comment in reversed(comments):
        if (comment.get("author") or {}).get("login") not in {
            "github-actions",
            "github-actions[bot]",
        }:
            continue
        matches = re.findall(
            r"<!-- verifier-corpus-decision/v1 (\{[^\n]+\}) -->", comment.get("body", "")
        )
        for match in reversed(matches):
            try:
                decision = json.loads(match)
            except json.JSONDecodeError:
                continue
            if not isinstance(decision, dict):
                continue
            decision["source_url"] = comment.get("url", "")
            if joined_decision({**record, "verifier_decision": decision}):
                return decision
    return None


def settled_verdict(decision: dict[str, Any] | None) -> str:
    """Use the same admitted verdict for human reports and workflow outputs."""
    if decision is None:
        return "UNVERIFIABLE_INPUT"
    if decision["verdict"] == "PASS":
        return "PASS"
    return "FAIL" if "FAIL" in decision["provider_verdicts"] else "CONCERNS"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--comparison", type=Path)
    inputs.add_argument("--evaluation", type=Path)
    parser.add_argument("--comment", type=Path)
    parser.add_argument("--execution-receipt", type=Path, required=True)
    parser.add_argument("--print-decision", action="store_true")
    parser.add_argument("--print-verdict", action="store_true")
    args = parser.parse_args(argv)
    if not args.comment and not args.print_decision and not args.print_verdict:
        parser.error("--comment or --print-decision is required")
    # Model-provided report text cannot supply an authenticated marker. Build
    # one settled outgoing report; never mutate retained inputs or public history.
    text = args.comment.read_text(encoding="utf-8") if args.comment else ""
    text = re.sub(r"<!-- verifier-corpus-decision/v1 (\{[^\n]+\}) -->", "", text)
    refusal = None
    identity = {
        key: os.environ.get(env, "")
        for key, env in {
            "repo": "GITHUB_REPOSITORY",
            "pr": "PR_NUMBER",
            "head_sha": "PR_HEAD_SHA",
            "evaluated_sha": "EVALUATED_SHA",
            "run_id": "GITHUB_RUN_ID",
            "run_attempt": "GITHUB_RUN_ATTEMPT",
        }.items()
    }
    try:
        decision = admitted_decision(
            args.comparison or args.evaluation,
            args.execution_receipt,
            identity,
            mode="compare" if args.comparison else "evaluate",
            ci_failed=os.environ.get("CI_FAILED"),
        )
        if decision:
            manifest = Path("verification-event-manifest.json")
            if manifest.exists():
                metadata = event_metadata(manifest)
                event = metadata["verification_event"]
                if any(
                    str(event[key]).lower() != str(identity[key]).lower()
                    for key in ("repo", "pr", "head_sha", "evaluated_sha")
                ):
                    raise ValueError("Collector event differs from terminal result identity")
                decision.update(metadata)
    except (OSError, ValueError, TypeError, KeyError, ImportError, AttributeError) as exc:
        decision = None
        # A bounded type identifies the recoverable refusal without exposing
        # manifest contents, local paths or exception text in the public report.
        refusal = f"result_or_event_admission_failed/{type(exc).__name__}"
    if args.comment:
        settled = settled_verdict(decision)
        # Provider detail remains in the report and exact retained JSON. The
        # top-level publication verdict must reflect admission and the CI floor.
        text, count = re.subn(
            r"^\*\*Verdict:\*\*.*$", f"**Verdict:** {settled}", text, count=1, flags=re.MULTILINE
        )
        if not count:
            text = f"**Verdict:** {settled}\n\n" + text
        if refusal:
            text += f"\nResult admission refused: `{refusal}`. Retained output requires recovery; no provider retry is authorized.\n"
        if decision is not None:
            text += f"\n<!-- {MARKER} {json.dumps(decision, sort_keys=True)} -->\n"
        args.comment.write_text(text, encoding="utf-8")
    if args.print_decision:
        print(json.dumps(decision, sort_keys=True))
    if args.print_verdict:
        print(settled_verdict(decision))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
