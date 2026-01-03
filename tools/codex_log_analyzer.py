"""
Codex Log Analyzer

Analyze Codex JSONL logs to infer likely task completions based on file changes
and command evidence. Intended as a lightweight, non-LLM heuristic analyzer.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from tools.codex_jsonl_parser import CodexSession, parse_codex_jsonl


@dataclass
class TaskMatch:
    task: str
    confidence: str  # high, medium, low
    reason: str
    evidence_files: list[str]


@dataclass
class LogAnalysisResult:
    matches: list[TaskMatch]
    summary: str
    session: CodexSession | None = None


SYNONYMS = {
    "add": ["create", "implement", "introduce", "build"],
    "create": ["add", "implement", "introduce", "build"],
    "implement": ["add", "create", "build"],
    "fix": ["repair", "resolve", "correct", "patch"],
    "update": ["modify", "change", "revise", "edit"],
    "remove": ["delete", "drop", "eliminate"],
    "test": ["tests", "testing", "spec", "specs"],
    "config": ["configuration", "settings", "configure"],
    "doc": ["docs", "documentation", "document"],
}


def analyze_codex_log(
    content: str,
    tasks: Iterable[str] | str,
    *,
    include_checked: bool = False,
) -> LogAnalysisResult:
    """
    Analyze Codex JSONL log content for likely task completion matches.

    Args:
        content: JSONL log content from `codex exec --json`.
        tasks: Iterable of task strings or raw checkbox markdown block.
        include_checked: If tasks is markdown, include checked tasks as candidates.

    Returns:
        LogAnalysisResult with matches and summary.
    """
    session = parse_codex_jsonl(content)
    file_paths = [fc.path for fc in session.file_changes if fc.path]
    commands = [cmd.command for cmd in session.commands if cmd.command]

    if isinstance(tasks, str):
        task_lines = _extract_tasks_from_markdown(tasks, include_checked=include_checked)
    else:
        task_lines = [t.strip() for t in tasks if t and t.strip()]

    matches = _match_tasks_to_evidence(task_lines, file_paths, commands)
    summary = _build_summary(matches, file_paths)
    return LogAnalysisResult(matches=matches, summary=summary, session=session)


def _extract_tasks_from_markdown(markdown: str, *, include_checked: bool) -> list[str]:
    checkbox_pattern = re.compile(r"^[\s]*[-*+]\s*\[([ xX])\]\s*(.+)$", re.MULTILINE)
    tasks = []
    for match in checkbox_pattern.finditer(markdown):
        checked = match.group(1).lower() == "x"
        task_text = match.group(2).strip()
        if not task_text:
            continue
        if include_checked or not checked:
            tasks.append(task_text)
    return tasks


def _match_tasks_to_evidence(
    tasks: list[str],
    files_changed: list[str],
    commands: list[str],
) -> list[TaskMatch]:
    matches: list[TaskMatch] = []

    keywords = _build_keyword_set(files_changed, commands)
    expanded_keywords = _expand_synonyms(keywords)
    test_file_modules = _build_test_module_map(files_changed)

    for task in tasks:
        task_lower = task.lower()
        task_words = re.findall(r"\b[a-z0-9_-]{3,}\b", task_lower)
        is_test_task = bool(re.search(r"\b(test|tests|unit\s*test|coverage)\b", task_lower))

        matching_words = [w for w in task_words if w in expanded_keywords]
        score = len(matching_words) / len(task_words) if task_words else 0.0

        file_refs = _extract_file_refs(task_lower)
        exact_file_match = _has_exact_file_match(file_refs, files_changed)
        file_match = _has_file_keyword_match(task_words, files_changed)
        command_match = _has_command_keyword_match(task_words, commands)
        test_module_match = _has_test_module_match(task_lower, test_file_modules) if is_test_task else False

        confidence = "low"
        reason = "No strong evidence"
        evidence_files = []

        if exact_file_match:
            confidence = "high"
            matched_file = _first_matching_file(file_refs, files_changed)
            reason = f"Exact file created/modified: {matched_file}"
            evidence_files = [matched_file] if matched_file else []
        elif is_test_task and test_module_match:
            confidence = "high"
            reason = "Test file created matching module reference"
            evidence_files = files_changed
        elif score >= 0.35 and (file_match or command_match):
            confidence = "high"
            reason = f"{round(score * 100)}% keyword match, evidence in files/commands"
            evidence_files = files_changed
        elif score >= 0.25 and file_match:
            confidence = "high"
            reason = f"{round(score * 100)}% keyword match with file match"
            evidence_files = files_changed
        elif score >= 0.2 or file_match:
            confidence = "medium"
            reason = f"{round(score * 100)}% keyword match" + (", file touched" if file_match else "")
            evidence_files = files_changed

        if confidence != "low":
            matches.append(
                TaskMatch(
                    task=task,
                    confidence=confidence,
                    reason=reason,
                    evidence_files=evidence_files,
                )
            )

    return matches


def _build_keyword_set(files_changed: list[str], commands: list[str]) -> set[str]:
    keywords: set[str] = set()

    for file_path in files_changed:
        parts = re.split(r"[\s/]+", re.sub(r"[^a-zA-Z0-9_/-]", " ", file_path.lower()))
        for part in parts:
            if len(part) > 2:
                keywords.add(part)
        file_name = file_path.split("/")[-1]
        for part in _split_camel_case(re.sub(r"\.[^.]+$", "", file_name)):
            keywords.add(part)

    for command in commands:
        for word in re.findall(r"\b[a-z0-9_-]{3,}\b", command.lower()):
            keywords.add(word)
        for part in _split_camel_case(command):
            keywords.add(part)

    return keywords


def _expand_synonyms(keywords: set[str]) -> set[str]:
    expanded = set(keywords)
    for keyword in list(keywords):
        synonyms = SYNONYMS.get(keyword, [])
        expanded.update(synonyms)
    return expanded


def _split_camel_case(text: str) -> list[str]:
    split_text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    split_text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", split_text)
    return [w.lower() for w in re.split(r"[\s_-]+", split_text) if len(w) > 2]


def _build_test_module_map(files_changed: list[str]) -> dict[str, list[str]]:
    test_file_modules: dict[str, list[str]] = {}
    for file_path in files_changed:
        match = re.search(r"tests?/test_([a-z0-9_]+)\.(?:py|js|ts)$", file_path, re.I)
        if not match:
            continue
        module_parts = match.group(1).lower().split("_")
        modules = list(module_parts)
        for part in module_parts:
            if not part.endswith("s"):
                modules.append(part + "s")
            if part.endswith("s"):
                modules.append(part[:-1])
        modules.append(match.group(1).lower())
        test_file_modules[file_path] = modules
    return test_file_modules


def _extract_file_refs(task_lower: str) -> list[str]:
    refs = re.findall(
        r"`([^`]+\.[a-z0-9]+)`|([a-z0-9_./-]+(?:\.test)?\.(?:js|ts|py|yml|yaml|md))",
        task_lower,
    )
    return [ref for pair in refs for ref in pair if ref]


def _has_exact_file_match(file_refs: list[str], files_changed: list[str]) -> bool:
    for ref in file_refs:
        ref_lower = ref.lower()
        ref_base = ref_lower.split("/")[-1]
        for changed in files_changed:
            changed_lower = changed.lower()
            changed_base = changed_lower.split("/")[-1]
            if changed_base == ref_base or changed_lower.endswith(ref_lower):
                return True
    return False


def _first_matching_file(file_refs: list[str], files_changed: list[str]) -> str | None:
    for ref in file_refs:
        ref_lower = ref.lower()
        ref_base = ref_lower.split("/")[-1]
        for changed in files_changed:
            changed_lower = changed.lower()
            changed_base = changed_lower.split("/")[-1]
            if changed_base == ref_base or changed_lower.endswith(ref_lower):
                return changed
    return None


def _has_file_keyword_match(task_words: list[str], files_changed: list[str]) -> bool:
    for changed in files_changed:
        changed_lower = changed.lower()
        if any(word in changed_lower for word in task_words):
            return True
    return False


def _has_command_keyword_match(task_words: list[str], commands: list[str]) -> bool:
    for command in commands:
        command_lower = command.lower()
        if any(word in command_lower and len(word) > 4 for word in task_words):
            return True
    return False


def _has_test_module_match(task_lower: str, test_file_modules: dict[str, list[str]]) -> bool:
    module_refs = re.findall(r"`([a-z0-9_\/]+)`|for\s+([a-z0-9_]+)\s+module", task_lower)
    clean_refs = []
    for pair in module_refs:
        ref = next((p for p in pair if p), "")
        ref = ref.replace("/", "").strip()
        if not ref:
            continue
        clean_refs.extend({ref, ref.rstrip("s"), f"{ref}s"})

    for modules in test_file_modules.values():
        for ref in clean_refs:
            if any(ref in module or module in ref for module in modules):
                return True
    return False


def _build_summary(matches: list[TaskMatch], files_changed: list[str]) -> str:
    if not matches:
        if files_changed:
            return "No clear task matches found in codex log changes"
        return "No changes detected in codex log"
    high = sum(1 for match in matches if match.confidence == "high")
    medium = sum(1 for match in matches if match.confidence == "medium")
    return (
        f"Found {len(matches)} potential task completion(s): "
        f"{high} high, {medium} medium confidence"
    )

