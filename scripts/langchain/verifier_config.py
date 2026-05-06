"""Shared verifier prompt budgets, repair policy, and terminal checks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from scripts.langchain.issue_pr_context import DEFAULT_TOKEN_BUDGET
from scripts.langchain.structured_output import MAX_REPAIR_ATTEMPTS

EVAL_PAIR_BUDGET_TOKENS = DEFAULT_TOKEN_BUDGET
EVAL_SCHEMA_REPAIR_BUDGET_TOKENS = DEFAULT_TOKEN_BUDGET
EVAL_FOLLOW_UP_BUDGET_TOKENS = DEFAULT_TOKEN_BUDGET

RepairDecision = Literal["retry", "terminal", "escalate"]

_TERMINAL_VERDICTS = {"pass", "concerns", "fail", "error"}
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
    if isinstance(value, dict | list):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return vars(value)
    return value


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
