"""Quality checks for weekly repo-review issue bodies."""

from __future__ import annotations

import re

ISSUE_BODY_REQUIRED_SECTIONS = (
    "## Why",
    "## Scope",
    "## Non-Goals",
    "## Tasks",
    "## Acceptance Criteria",
    "## Implementation Notes",
)

GENERIC_PHRASES = (
    "approved weekly-review candidate",
    "candidate source:",
    "weekly priority:",
    "implement the approved review gap",
    "add or update repo-local tests",
    "the reviewed design/readiness gap",
    "implemented in repo-local code, docs, tests, or workflows as appropriate",
    "no unrelated workflows/template-sync",
    "use the file paths named in the scope/tasks as the starting point",
    "ready to upload if approved",
)

FRAGMENT_TASKS = {
    "strip leading/trailing whitespace",
    "collapse repeated spaces",
    "normalize apostrophes/hyphens where appropriate",
}


def list_value(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def markdown_section(body: str, heading: str) -> str:
    match = re.search(rf"(?ms)^{re.escape(heading)}\s*\n(.*?)(?=^## |\Z)", body)
    return match.group(1).strip() if match else ""


def checklist_items(section_text: str) -> list[str]:
    return [
        match.group(1).strip() for match in re.finditer(r"(?m)^- \[[ xX]\]\s+(.+)$", section_text)
    ]


def issue_body_quality_errors(body: str) -> list[str]:
    errors: list[str] = []
    normalized = body.lower()

    for section in ISSUE_BODY_REQUIRED_SECTIONS:
        if not re.search(rf"(?m)^{re.escape(section)}\s*$", body):
            errors.append(f"missing required section {section}")

    for phrase in GENERIC_PHRASES:
        if phrase in normalized:
            errors.append(f"generic placeholder phrase: {phrase}")

    tasks = checklist_items(markdown_section(body, "## Tasks"))
    acceptance = checklist_items(markdown_section(body, "## Acceptance Criteria"))
    if len(tasks) < 4:
        errors.append("fewer than 4 task checkboxes")
    if len(acceptance) < 3:
        errors.append("fewer than 3 acceptance-criteria checkboxes")

    for item in tasks:
        lowered = item.lower().strip()
        if item.endswith(":"):
            errors.append(f"task checkbox is a fragment ending with colon: {item}")
        if lowered in FRAGMENT_TASKS:
            errors.append(f"task checkbox is a fragment: {item}")
        if len(item.split()) < 4:
            errors.append(f"task checkbox is too terse: {item}")

    for item in acceptance:
        if item.endswith(":"):
            errors.append(f"acceptance checkbox is a fragment ending with colon: {item}")
        if len(item.split()) < 6:
            errors.append(f"acceptance checkbox is too terse: {item}")

    implementation_notes = markdown_section(body, "## Implementation Notes")
    if implementation_notes:
        if "relevant areas:" in implementation_notes.lower():
            errors.append("implementation notes use broad 'Relevant areas' wording")
        if not re.search(r"`[^`]+`", implementation_notes):
            errors.append("implementation notes do not include concrete path/code references")

    return errors


def issue_body_is_agent_ready(body: str) -> bool:
    return not issue_body_quality_errors(body)


def review_evidence_trace_errors(trace: object) -> list[str]:
    if not isinstance(trace, dict):
        return ["review evidence trace is missing or not an object"]

    errors: list[str] = []
    gap = str(trace.get("gap") or "").strip()
    current_state = str(trace.get("current_state") or "").strip()
    required_change = str(trace.get("required_change") or "").strip()
    if not gap:
        errors.append("review evidence trace is missing a verified gap")
    if not current_state:
        errors.append("review evidence trace is missing current_state")
    if not required_change:
        errors.append("review evidence trace is missing required_change")

    design_refs = [
        str(item).strip() for item in list_value(trace.get("design_refs")) if str(item).strip()
    ]
    implementation_refs = [
        str(item).strip()
        for item in list_value(trace.get("implementation_refs"))
        if str(item).strip()
    ]
    readiness_refs = [
        str(item).strip()
        for item in [
            *list_value(trace.get("test_refs")),
            *list_value(trace.get("readiness_refs")),
        ]
        if str(item).strip()
    ]
    if not design_refs:
        errors.append("review evidence trace is missing design_refs")
    if not implementation_refs:
        errors.append("review evidence trace is missing implementation_refs")
    if not readiness_refs:
        errors.append("review evidence trace is missing test_refs/readiness_refs")

    title_patterns = [
        str(item).strip()
        for item in [
            *list_value(trace.get("issue_title_pattern")),
            *list_value(trace.get("issue_title_patterns")),
            *list_value(trace.get("candidate_title_pattern")),
            *list_value(trace.get("candidate_title_patterns")),
        ]
        if str(item).strip()
    ]
    candidate_indexes = list_value(trace.get("candidate_indexes"))
    candidate_titles = [
        str(item).strip() for item in list_value(trace.get("candidate_titles")) if str(item).strip()
    ]
    if not title_patterns and not candidate_indexes and not candidate_titles:
        errors.append("review evidence trace is not tied to candidate indexes or title patterns")

    for label, refs in (
        ("design_refs", design_refs),
        ("implementation_refs", implementation_refs),
        ("test_refs/readiness_refs", readiness_refs),
    ):
        for ref in refs:
            if "`" in ref:
                errors.append(
                    f"{label} entry should be a raw path or note without backticks: {ref}"
                )
            if len(ref.split()) > 12 and "/" not in ref and "." not in ref:
                errors.append(f"{label} entry is too broad to be traceable: {ref}")

    return errors
