"""CI failure triage helpers.

Ported from the keepalive triage prototype to provide deterministic failure
classification and fix suggestions without an LLM dependency.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class TriagePattern:
    error_type: str
    regexes: tuple[re.Pattern[str], ...]
    root_cause: str
    suggested_fix: str
    file_regexes: tuple[re.Pattern[str], ...] = ()
    playbook_url: str | None = None


@dataclass(frozen=True)
class TriageFinding:
    error_type: str
    root_cause: str
    suggested_fix: str
    relevant_files: list[str]
    playbook_url: str | None = None
    evidence: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TriageReport:
    findings: list[TriageFinding]
    summary: str
    failed_tests: list[str] = field(default_factory=list)


_DEFAULT_FILE_REGEX = re.compile(r"(?P<path>[A-Za-z0-9_./-]+\.(?:py|js|ts|tsx|json|ya?ml))")


def _compile(patterns: list[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pat, re.IGNORECASE) for pat in patterns)


SUGGESTED_FIX_TEMPLATES: dict[str, str] = {
    "mypy": "Fix the reported type errors in {files} or update typing stubs to satisfy mypy.",
    "pytest": "Inspect failing tests in {files} and fix the regression or update expectations.",
    "coverage": "Add or expand tests covering {files} to meet the coverage threshold.",
    "import_error": "Ensure imports in {files} resolve by fixing module paths or packaging.",
    "syntax_error": "Fix the syntax error in {files} and rerun the formatter or linter if needed.",
}


DEFAULT_TRIAGE_PATTERNS: tuple[TriagePattern, ...] = (
    TriagePattern(
        error_type="mypy",
        regexes=_compile(
            [
                r"\bmypy\b",
                r"\berror:\s+.*\[(attr-defined|assignment|arg-type|return-value)\]",
                r"Found \d+ errors? in \d+ files?",
            ]
        ),
        root_cause="Type checking failed during mypy.",
        suggested_fix=SUGGESTED_FIX_TEMPLATES["mypy"],
        file_regexes=_compile([r"(?P<path>[A-Za-z0-9_./-]+\.py):\d+:"]),
        playbook_url="docs/INTEGRATION_GUIDE.md#scenario-2-mypy-errors",
    ),
    TriagePattern(
        error_type="pytest",
        regexes=_compile(
            [
                r"=+ FAILURES =+",
                r"E\s+AssertionError",
                r"FAILED\s+[A-Za-z0-9_./-]+::",
            ]
        ),
        root_cause="Pytest reported failing tests.",
        suggested_fix=SUGGESTED_FIX_TEMPLATES["pytest"],
        file_regexes=_compile([r"(?P<path>[A-Za-z0-9_./-]+\.py):\d+:"]),
        playbook_url="docs/INTEGRATION_GUIDE.md#scenario-1-tests-failing",
    ),
    TriagePattern(
        error_type="coverage",
        regexes=_compile(
            [
                r"coverage\s+failure",
                r"TOTAL\s+\d+\s+\d+\s+\d+%",
                r"required test coverage of \d+% not reached",
            ]
        ),
        root_cause="Coverage enforcement failed.",
        suggested_fix=SUGGESTED_FIX_TEMPLATES["coverage"],
        playbook_url="docs/INTEGRATION_GUIDE.md#consumer-repo-setup-coverage-soft-gate",
    ),
    TriagePattern(
        error_type="import_error",
        regexes=_compile(
            [
                r"ModuleNotFoundError",
                r"ImportError",
                r"No module named",
            ]
        ),
        root_cause="Python import failed during test or runtime.",
        suggested_fix=SUGGESTED_FIX_TEMPLATES["import_error"],
        file_regexes=_compile([r"File \"(?P<path>[A-Za-z0-9_./-]+\.py)\""]),
        playbook_url="docs/llm-task-analysis.md#import-errors",
    ),
    TriagePattern(
        error_type="syntax_error",
        regexes=_compile(
            [
                r"SyntaxError",
                r"IndentationError",
                r"unexpected EOF while parsing",
            ]
        ),
        root_cause="Python parser raised a syntax error.",
        suggested_fix=SUGGESTED_FIX_TEMPLATES["syntax_error"],
        file_regexes=_compile([r"File \"(?P<path>[A-Za-z0-9_./-]+\.py)\""]),
        playbook_url="docs/fast-validation-ecosystem.md#error-handling",
    ),
)


def triage_ci_failure(
    log_text: str,
    patterns: tuple[TriagePattern, ...] = DEFAULT_TRIAGE_PATTERNS,
    use_llm: bool | None = None,
) -> TriageReport:
    lines = [line.rstrip() for line in log_text.splitlines() if line.strip()]
    findings: list[TriageFinding] = []
    failed_tests = extract_pytest_failures(log_text)

    for pattern in patterns:
        evidence = _collect_evidence(lines, pattern.regexes)
        if not evidence:
            continue
        relevant_files = _extract_relevant_files(evidence, pattern.file_regexes)
        suggested_fix = _format_suggested_fix(pattern.suggested_fix, relevant_files)
        findings.append(
            TriageFinding(
                error_type=pattern.error_type,
                root_cause=pattern.root_cause,
                suggested_fix=suggested_fix,
                relevant_files=relevant_files,
                playbook_url=pattern.playbook_url,
                evidence=evidence,
            )
        )

    summary = _build_summary(findings, failed_tests)
    report = TriageReport(findings=findings, summary=summary, failed_tests=failed_tests)
    return _maybe_enhance_with_llm(report, log_text, use_llm)


def _collect_evidence(lines: list[str], regexes: tuple[re.Pattern[str], ...]) -> list[str]:
    evidence: list[str] = []
    for line in lines:
        if any(regex.search(line) for regex in regexes):
            evidence.append(line)
    return evidence


def _extract_relevant_files(
    evidence: list[str], file_regexes: tuple[re.Pattern[str], ...]
) -> list[str]:
    paths: list[str] = []

    for line in evidence:
        for regex in file_regexes:
            match = regex.search(line)
            if match:
                path = match.groupdict().get("path")
                if path:
                    paths.append(path)
        match = _DEFAULT_FILE_REGEX.search(line)
        if match:
            path = match.groupdict().get("path")
            if path:
                paths.append(path)

    seen: set[str] = set()
    unique_paths = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        unique_paths.append(path)
    return unique_paths


def _format_suggested_fix(template: str, relevant_files: list[str]) -> str:
    if "{files}" not in template:
        return template
    files = ", ".join(relevant_files) if relevant_files else "the reported files"
    return template.format(files=files)


def _build_summary(findings: list[TriageFinding], failed_tests: list[str] | None = None) -> str:
    if not findings:
        if failed_tests:
            return "Detected failing tests without a known failure pattern."
        return "No known failure patterns detected."
    types = ", ".join(finding.error_type for finding in findings)
    if failed_tests:
        return f"Detected failure types: {types}. Pytest failures: {len(failed_tests)}."
    return f"Detected failure types: {types}."


def extract_pytest_failures(log_text: str) -> list[str]:
    failures: list[str] = []
    for line in log_text.splitlines():
        line = line.strip()
        if not line.startswith("FAILED "):
            continue
        payload = line[len("FAILED ") :].strip()
        if not payload:
            continue
        test_id = payload.split(" - ", 1)[0].strip()
        if test_id and test_id not in failures:
            failures.append(test_id)
    return failures


def _maybe_enhance_with_llm(
    report: TriageReport, log_text: str, use_llm: bool | None
) -> TriageReport:
    if use_llm is None:
        use_llm = _bool_env(os.environ.get("KEEPALIVE_USE_LLM_TRIAGE"))
    if not use_llm:
        return report

    llm_findings = _run_llm_triage(log_text)
    if not llm_findings:
        return report

    existing_types = {finding.error_type for finding in report.findings}
    merged = list(report.findings)
    for finding in llm_findings:
        if finding.error_type in existing_types:
            continue
        merged.append(finding)
        existing_types.add(finding.error_type)

    summary = _build_summary(merged, report.failed_tests)
    return TriageReport(findings=merged, summary=summary, failed_tests=report.failed_tests)


def _bool_env(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _run_llm_triage(log_text: str) -> list[TriageFinding]:
    client_info = _get_llm_client()
    if not client_info:
        return []
    client, _ = client_info
    prompt = _build_llm_prompt(log_text)
    try:
        response = client.invoke(prompt)
    except Exception:
        return []
    content = getattr(response, "content", None) or str(response)
    return _parse_llm_findings(content)


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


def _build_llm_prompt(log_text: str) -> str:
    trimmed = log_text.strip()
    if len(trimmed) > 8000:
        trimmed = trimmed[:8000]
    schema = {
        "findings": [
            {
                "error_type": "string",
                "root_cause": "string",
                "suggested_fix": "string",
                "relevant_files": ["string"],
                "playbook_url": "string or null",
            }
        ]
    }
    return (
        "You are a CI failure triage assistant. "
        "Read the log snippet and return JSON only, matching this schema:\n"
        f"{json.dumps(schema)}\n"
        "Return an empty findings list if nothing is clear.\n"
        "Log snippet:\n"
        f"{trimmed}"
    )


def _parse_llm_findings(text: str) -> list[TriageFinding]:
    payload = _extract_json_payload(text)
    if not payload:
        return []
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    findings_data = data.get("findings")
    if not isinstance(findings_data, list):
        return []
    findings: list[TriageFinding] = []
    for raw in findings_data:
        if not isinstance(raw, dict):
            continue
        error_type = str(raw.get("error_type") or "").strip()
        root_cause = str(raw.get("root_cause") or "").strip()
        suggested_fix = str(raw.get("suggested_fix") or "").strip()
        if not (error_type and root_cause and suggested_fix):
            continue
        relevant_files = [
            str(item).strip()
            for item in raw.get("relevant_files", [])
            if isinstance(item, str) and item.strip()
        ]
        playbook_url = raw.get("playbook_url")
        if playbook_url is not None:
            playbook_url = str(playbook_url).strip() or None
        findings.append(
            TriageFinding(
                error_type=error_type,
                root_cause=root_cause,
                suggested_fix=suggested_fix,
                relevant_files=relevant_files,
                playbook_url=playbook_url,
            )
        )
    return findings


def _extract_json_payload(text: str) -> str | None:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return stripped[start : end + 1]


def _report_to_dict(report: TriageReport) -> dict[str, object]:
    return {
        "summary": report.summary,
        "failed_tests": report.failed_tests,
        "findings": [
            {
                "error_type": finding.error_type,
                "root_cause": finding.root_cause,
                "suggested_fix": finding.suggested_fix,
                "relevant_files": finding.relevant_files,
                "playbook_url": finding.playbook_url,
                "evidence": finding.evidence,
            }
            for finding in report.findings
        ],
    }


def _format_text_report(report: TriageReport) -> str:
    if not report.findings:
        if report.failed_tests:
            failures = "\n".join(f"- {test_id}" for test_id in report.failed_tests)
            return f"{report.summary}\nFailing tests:\n{failures}"
        return report.summary

    lines = [report.summary]
    if report.failed_tests:
        lines.append("Failing tests:")
        lines.extend(f"- {test_id}" for test_id in report.failed_tests)
    for finding in report.findings:
        lines.append(f"- error_type: {finding.error_type}")
        lines.append(f"  root_cause: {finding.root_cause}")
        lines.append(f"  suggested_fix: {finding.suggested_fix}")
        if finding.relevant_files:
            files = ", ".join(finding.relevant_files)
            lines.append(f"  relevant_files: {files}")
        if finding.playbook_url:
            lines.append(f"  playbook_url: {finding.playbook_url}")
    return "\n".join(lines)


def _read_log_text(path: str | None) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8")
    return sys.stdin.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CI failure triage helper.")
    parser.add_argument("--log-file", help="Path to a log file; defaults to stdin.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(argv)

    log_text = _read_log_text(args.log_file)
    report = triage_ci_failure(log_text)

    if args.json:
        payload = _report_to_dict(report)
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_format_text_report(report))

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
