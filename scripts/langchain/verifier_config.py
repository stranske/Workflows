"""Shared verifier prompt budgets, repair policy, and terminal checks."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from scripts.langchain.issue_pr_context import DEFAULT_TOKEN_BUDGET
from scripts.langchain.structured_output import MAX_REPAIR_ATTEMPTS, clamp_repair_attempts

EVAL_PAIR_BUDGET_TOKENS = DEFAULT_TOKEN_BUDGET
EVAL_SCHEMA_REPAIR_BUDGET_TOKENS = DEFAULT_TOKEN_BUDGET
EVAL_FOLLOW_UP_BUDGET_TOKENS = DEFAULT_TOKEN_BUDGET

# Prompt-coverage budgets (#3701). The context block carries CI, plan sources and
# the diff summary; changed code is reviewed as whole files across bounded chunks.
# A prefix cap of EVAL_PAIR_BUDGET_TOKENS // 2 per block silently dropped all or
# most code on complex PRs, so code gets its own bounded budget. Override with the
# VERIFIER_CONTEXT_BUDGET_TOKENS / VERIFIER_DIFF_BUDGET_TOKENS environment variables.
VERIFIER_CONTEXT_BUDGET_TOKENS = 4000
VERIFIER_DIFF_BUDGET_TOKENS = 16000
# Bound provider calls per review alongside the per-call changed-code budget.
# Exhausting either limit leaves files explicitly UNVERIFIABLE_INPUT.
MAX_REVIEW_CHUNKS = 64
# A PASS needs at least this share of changed-code characters in the prompt.
MIN_CODE_COVERAGE_RATIO = 0.5

RepairDecision = Literal["retry", "terminal", "escalate"]

_TERMINAL_VERDICTS = {"pass", "concerns", "fail", "error", "unverifiable-input"}
_TERMINAL_DISPOSITIONS = {
    "follow-up-created",
    "needs-human-depth-limit",
    "needs-human-verdict-policy",
    "no-follow-up-created",
    "verifier-error",
    "verifier-pass",
    "verifier-non-pass",
}
_PENDING_STAGES = {
    "pending",
    "repair-pending",
    "repair",
    "schema-repair",
    "validation-retry",
}
_FAILED_REPAIR_STAGES = {
    "repair-unavailable",
    "repair-validation",
    "validation",
    "schema-validation",
}


@dataclass(frozen=True)
class SchemaRepairPolicy:
    """Policy for structured-output schema repair in verifier flows."""

    max_attempts: int = MAX_REPAIR_ATTEMPTS
    escalation_threshold: int = MAX_REPAIR_ATTEMPTS

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_attempts", clamp_repair_attempts(self.max_attempts))
        object.__setattr__(
            self,
            "escalation_threshold",
            clamp_repair_attempts(self.escalation_threshold),
        )

    def terminal_decision(
        self,
        *,
        repair_attempts_used: int = 0,
        error_stage: str | None = None,
        has_payload: bool = False,
    ) -> RepairDecision:
        """Return the next repair disposition for a parser result."""

        attempts = max(0, int(repair_attempts_used or 0))
        max_attempts = max(0, int(self.max_attempts))
        threshold = max(0, int(self.escalation_threshold))
        stage = _normalize(error_stage)

        if has_payload or not stage:
            return "terminal"
        if attempts < max_attempts:
            return "retry"
        if stage in _FAILED_REPAIR_STAGES and attempts >= threshold:
            return "escalate"
        return "terminal"


def is_terminal_artifact(verifier_run: Any) -> bool:
    """Return True when verifier output is complete enough for downstream work."""

    data = _coerce_artifact(verifier_run)
    if data is None:
        return False
    if isinstance(data, list):
        return bool(data) and all(is_terminal_artifact(item) for item in data)
    if not isinstance(data, dict):
        return False

    if _has_pending_repair(data):
        return False

    verdict = _normalize(data.get("verdict"))
    if verdict in _TERMINAL_VERDICTS:
        return True

    disposition = _normalize(data.get("disposition") or data.get("terminal_state"))
    if disposition in _TERMINAL_DISPOSITIONS and not _requires_verdict(data):
        return True

    results = data.get("results")
    if isinstance(results, list):
        usable = [item for item in results if isinstance(item, dict)]
        return bool(usable) and all(is_terminal_artifact(item) for item in usable)

    payload = data.get("payload")
    if isinstance(payload, dict):
        return is_terminal_artifact(payload)

    return False


def artifact_from_verification_text(text: str) -> dict[str, Any]:
    """Build a verifier artifact candidate from a posted verifier report."""

    raw = latest_verifier_report(text)
    artifact: dict[str, Any] = {"raw_present": bool(raw)}
    if not raw:
        return artifact

    parsed = _coerce_artifact(raw)
    if isinstance(parsed, dict):
        return {**parsed, **artifact}
    if isinstance(parsed, list):
        return {**artifact, "artifact_family": "verifier-report", "results": parsed}

    verdicts = _extract_verdicts(raw)
    if verdicts:
        severity = {"PASS": 0, "CONCERNS": 1, "FAIL": 2, "ERROR": 3, "UNVERIFIABLE_INPUT": 0.5}
        artifact["verdict"] = max(verdicts, key=lambda verdict: severity.get(verdict, -1))

    lowered = raw.lower()
    repair_pending = any(
        phrase in lowered
        for phrase in (
            "repair pending",
            "schema repair pending",
            "validation retry",
            "pending repair",
            "partial verifier output",
        )
    )
    if (
        "## pr verification" in lowered
        or "## llm evaluation report" in lowered
        or "## provider comparison report" in lowered
        or "verdict:" in lowered
    ):
        artifact["artifact_family"] = "verifier-report"
    if repair_pending:
        artifact["repair_pending"] = True
    return artifact


def latest_verifier_report(text: str) -> str:
    """Select the last posted verifier report before interpreting any verdict.

    A single structured JSON artifact or marker-less report is returned intact.
    Historical reports remain available in comments, never as current evidence.
    """

    raw = (text or "").strip()
    parsed = _coerce_artifact(raw)
    if isinstance(parsed, dict) and parsed.get("schema") == "verifier-comment-history/v1":
        comments = parsed.get("comments")
        if not isinstance(comments, list) or not all(isinstance(body, str) for body in comments):
            return ""
        return comments[-1].strip() if comments else ""
    if isinstance(parsed, (dict, list)):
        return raw
    # Legacy concatenated histories use this explicit comment separator. A
    # heading inside one current report is content, never another report.
    if "\n\n---\n\n" in raw:
        candidate = raw.rsplit("\n\n---\n\n", 1)[-1].strip()
        if re.match(
            r"##[ \t]+(?:PR Verification|LLM Evaluation Report|Provider Comparison Report)\b",
            candidate,
            re.I,
        ):
            raw = candidate
    heading = re.search(
        r"^##[ \t]+(?:PR Verification(?: Report| Comparison)?|LLM Evaluation Report|Provider Comparison Report)\b",
        raw,
        re.I | re.M,
    )
    return raw[heading.start() :] if heading else raw


def _coerce_artifact(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    if isinstance(value, (dict, list)):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return vars(value)
    return value


def _extract_verdicts(text: str) -> list[str]:
    verdicts: list[str] = []
    for match in re.finditer(
        r"verdict:\s*\*?\*?\s*(pass|concerns|fail|error|unverifiable_input)\b", text, re.I
    ):
        verdicts.append(match.group(1).upper())

    for match in re.finditer(
        r"\|\s*[^|\n]+\s*\|\s*[^|\n]*\|\s*(pass|concerns|fail|error|unverifiable_input)\s*\|",
        text,
        re.I,
    ):
        verdicts.append(match.group(1).upper())

    seen: list[str] = []
    for verdict in verdicts:
        if verdict not in seen:
            seen.append(verdict)
    return seen


def _has_pending_repair(data: dict[str, Any]) -> bool:
    if data.get("repair_pending") is True or data.get("pending_repair") is True:
        return True
    stage = _normalize(
        data.get("error_stage") or data.get("stage") or data.get("status") or data.get("state")
    )
    if stage in _PENDING_STAGES:
        return True

    attempts_remaining = data.get("repair_attempts_remaining")
    if isinstance(attempts_remaining, int) and attempts_remaining > 0:
        return True

    policy = SchemaRepairPolicy()
    return (
        bool(stage)
        and policy.terminal_decision(
            repair_attempts_used=int(data.get("repair_attempts_used") or 0),
            error_stage=stage,
            has_payload=data.get("payload") is not None,
        )
        == "retry"
    )


def _requires_verdict(data: dict[str, Any]) -> bool:
    disposition = _normalize(data.get("disposition") or data.get("terminal_state"))
    return disposition in {"follow-up-created", "verifier-non-pass"} and not data.get("verdict")


def _normalize(value: Any) -> str:
    return str(value or "").strip().replace("_", "-").lower()
