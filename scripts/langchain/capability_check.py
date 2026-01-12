#!/usr/bin/env python3
"""
Capability classification for agent issue intake.

Run with:
    python scripts/langchain/capability_check.py \
        --tasks-file tasks.md --acceptance-file acceptance.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

AGENT_CAPABILITY_CHECK_PROMPT = """
Analyze these tasks and acceptance criteria for agent compatibility.

Tasks:
{tasks}

Acceptance Criteria:
{acceptance}

For each item, classify as:
- ACTIONABLE: Agent can directly complete this
- PARTIAL: Agent can contribute but may not fully satisfy
- BLOCKED: Agent cannot complete this (explain why)

Known agent limitations:
- Cannot modify protected workflow files (.github/workflows/*.yml)
- Cannot change repository settings (branch protection, secrets, etc.)
- Cannot interact with external services requiring credentials
- Cannot make subjective design decisions requiring human input
- Cannot guarantee specific coverage percentages (can add tests, coverage varies)
- Cannot retry CI/CD pipelines - only fix code and push

Output JSON:
{{
  "actionable_tasks": [...],
  "partial_tasks": [{{"task": "...", "limitation": "..."}}],
  "blocked_tasks": [{{"task": "...", "reason": "...", "suggested_action": "..."}}],
  "recommendation": "PROCEED|REVIEW_NEEDED|BLOCKED",
  "human_actions_needed": [...]
}}
""".strip()


@dataclass
class CapabilityCheckResult:
    """Normalized result for capability classification."""

    actionable_tasks: list[str]
    partial_tasks: list[dict[str, str]]
    blocked_tasks: list[dict[str, str]]
    recommendation: str
    human_actions_needed: list[str]
    provider_used: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "actionable_tasks": self.actionable_tasks,
            "partial_tasks": self.partial_tasks,
            "blocked_tasks": self.blocked_tasks,
            "recommendation": self.recommendation,
            "human_actions_needed": self.human_actions_needed,
            "provider_used": self.provider_used,
        }


def _get_llm_client() -> tuple[object, str] | None:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        return None

    github_token = os.environ.get("GITHUB_TOKEN")
    openai_token = os.environ.get("OPENAI_API_KEY")
    if not github_token and not openai_token:
        return None

    from tools.llm_provider import DEFAULT_MODEL, GITHUB_MODELS_BASE_URL

    if github_token:
        return (
            ChatOpenAI(
                model=DEFAULT_MODEL,
                base_url=GITHUB_MODELS_BASE_URL,
                api_key=github_token,
                temperature=0.1,
            ),
            "github-models",
        )
    return (
        ChatOpenAI(
            model=DEFAULT_MODEL,
            api_key=openai_token,
            temperature=0.1,
        ),
        "openai",
    )


def _prepare_prompt_values(tasks: list[str], acceptance: str) -> dict[str, str]:
    task_lines = "\n".join(f"- {task}" for task in tasks) if tasks else "- (none)"
    acceptance_block = acceptance.strip() or "(none)"
    return {"tasks": task_lines, "acceptance": acceptance_block}


def _extract_json_payload(text: str) -> str | None:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return stripped[start : end + 1]


def _coerce_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, str) and item.strip()]


def _coerce_dict_list(value: Any, required_keys: set[str]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        entry: dict[str, str] = {}
        for key in required_keys:
            raw = item.get(key)
            if isinstance(raw, str) and raw.strip():
                entry[key] = raw.strip()
        if len(entry) == len(required_keys):
            normalized.append(entry)
    return normalized


def _normalize_result(payload: dict[str, Any], provider_used: str | None) -> CapabilityCheckResult:
    actionable = _coerce_list(payload.get("actionable_tasks"))
    partial = _coerce_dict_list(payload.get("partial_tasks"), {"task", "limitation"})
    blocked = _coerce_dict_list(
        payload.get("blocked_tasks"), {"task", "reason", "suggested_action"}
    )
    recommendation = str(payload.get("recommendation") or "REVIEW_NEEDED").strip().upper()
    if recommendation not in {"PROCEED", "REVIEW_NEEDED", "BLOCKED"}:
        recommendation = "REVIEW_NEEDED"
    human_actions = _coerce_list(payload.get("human_actions_needed"))

    return CapabilityCheckResult(
        actionable_tasks=actionable,
        partial_tasks=partial,
        blocked_tasks=blocked,
        recommendation=recommendation,
        human_actions_needed=human_actions,
        provider_used=provider_used,
    )


def _matches_any(patterns: list[str], text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _is_multi_action_task(task: str) -> bool:
    lowered = task.lower()
    if len(task.split()) >= 14:
        return True
    if any(sep in lowered for sep in (" and ", " + ", " & ", " then ", "; ")):
        return True
    return bool("," in task or " / " in task or re.search(r"\s\+\s", lowered))


def _requires_admin_access(task: str) -> bool:
    patterns = [
        r"\bgithub\s+secrets?\b",
        r"\bsecrets?\b",
        r"\brepository\s+settings\b",
        r"\brepo\s+settings\b",
        r"\bbranch\s+protection\b",
        r"\badmin\s+access\b",
        r"\badmin\b.*\bpermission\b",
        r"\borganization\s+settings\b",
        r"\borg\s+settings\b",
        r"\bbilling\b",
        r"\baccess\s+control\b",
    ]
    return _matches_any(patterns, task)


def _requires_external_dependency(task: str) -> bool:
    patterns = [
        r"\bstripe\b",
        r"\bpaypal\b",
        r"\bbraintree\b",
        r"\btwilio\b",
        r"\bslack\b",
        r"\bsentry\b",
        r"\bwebhook\b",
        r"\boauth\b",
        r"\bapi\s+key\b",
        r"\bclient\s+secret\b",
        r"\bclient\s+id\b",
        r"\bexternal\s+api\b",
        r"\bthird-?party\b",
        r"\bintegrat(e|ion)\b.*\bapi\b",
    ]
    return _matches_any(patterns, task)


def _fallback_classify(
    tasks: list[str], _acceptance: str, reason: str | None
) -> CapabilityCheckResult:
    actionable: list[str] = []
    partial: list[dict[str, str]] = []
    blocked: list[dict[str, str]] = []
    human_actions: list[str] = []

    for task in tasks:
        if _requires_admin_access(task):
            blocked.append(
                {
                    "task": task,
                    "reason": "Requires admin or repository settings access",
                    "suggested_action": "Have a repo admin apply the change or grant access.",
                }
            )
            human_actions.append(f"Admin access needed: {task}")
            continue
        if _requires_external_dependency(task):
            blocked.append(
                {
                    "task": task,
                    "reason": "Requires external service credentials or configuration",
                    "suggested_action": (
                        "Provide credentials or have a human set up " "the external service."
                    ),
                }
            )
            human_actions.append(f"External dependency setup required: {task}")
            continue
        if _is_multi_action_task(task):
            partial.append(
                {
                    "task": task,
                    "limitation": "Task bundles multiple actions; split into smaller tasks.",
                }
            )
            human_actions.append(f"Split task into smaller steps: {task}")
            continue
        actionable.append(task)

    if reason:
        human_actions.append(reason)

    if blocked:
        recommendation = "BLOCKED"
    elif partial or not tasks:
        recommendation = "REVIEW_NEEDED"
    else:
        recommendation = "PROCEED"

    return CapabilityCheckResult(
        actionable_tasks=actionable,
        partial_tasks=partial,
        blocked_tasks=blocked,
        recommendation=recommendation,
        human_actions_needed=human_actions,
        provider_used=None,
    )


def classify_capabilities(tasks: list[str], acceptance: str) -> CapabilityCheckResult:
    client_info = _get_llm_client()
    if not client_info:
        return _fallback_classify(tasks, acceptance, "LLM provider unavailable")

    client, provider_name = client_info
    try:
        from langchain_core.prompts import ChatPromptTemplate
    except ImportError:
        result = _fallback_classify(tasks, acceptance, "langchain-core not installed")
        result.provider_used = provider_name
        return result

    template = ChatPromptTemplate.from_template(AGENT_CAPABILITY_CHECK_PROMPT)
    chain = template | client
    response = chain.invoke(_prepare_prompt_values(tasks, acceptance))
    content = getattr(response, "content", None) or str(response)
    payload = _extract_json_payload(content)
    if not payload:
        result = _fallback_classify(tasks, acceptance, "LLM response missing JSON payload")
        result.provider_used = provider_name
        return result
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        result = _fallback_classify(tasks, acceptance, "LLM response JSON parse failed")
        result.provider_used = provider_name
        return result

    return _normalize_result(data, provider_name)


def _strip_checkbox(line: str) -> str:
    cleaned = re.sub(r"^\s*[-*+]\s*\[[ xX]\]\s*", "", line)
    cleaned = re.sub(r"^\s*[-*+]\s*", "", cleaned)
    return cleaned.strip()


def _parse_tasks_from_text(text: str) -> list[str]:
    tasks: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("-", "*", "+")):
            task = _strip_checkbox(stripped)
            if task:
                tasks.append(task)
    return tasks


def _load_text(path: str | None) -> str:
    if not path:
        return ""
    return Path(path).read_text(encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify agent capability for tasks.")
    parser.add_argument("--tasks-file", help="Path to tasks markdown/text file.")
    parser.add_argument("--acceptance-file", help="Path to acceptance criteria text file.")
    parser.add_argument("--tasks-json", help="JSON array of task strings.")
    parser.add_argument("--acceptance", help="Acceptance criteria text.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    tasks: list[str] = []
    if args.tasks_json:
        try:
            tasks_payload = json.loads(args.tasks_json)
        except json.JSONDecodeError:
            print("Invalid --tasks-json payload", file=sys.stderr)
            return 2
        if isinstance(tasks_payload, list):
            tasks = [str(item).strip() for item in tasks_payload if str(item).strip()]
    if not tasks and args.tasks_file:
        tasks_text = _load_text(args.tasks_file)
        tasks = _parse_tasks_from_text(tasks_text)
    acceptance_text = args.acceptance or _load_text(args.acceptance_file)

    result = classify_capabilities(tasks, acceptance_text)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


# Alias for backward compatibility with workflow
check_capability = classify_capabilities


if __name__ == "__main__":
    raise SystemExit(main())
