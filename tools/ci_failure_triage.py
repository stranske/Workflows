"""CI failure triage helpers.

Ported from the keepalive triage prototype to provide deterministic failure
classification and fix suggestions without an LLM dependency.
"""

from __future__ import annotations

import argparse
import json
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


_DEFAULT_FILE_REGEX = re.compile(r"(?P<path>[A-Za-z0-9_./-]+\.(?:py|js|ts|tsx|json|ya?ml))")


def _compile(patterns: list[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pat, re.IGNORECASE) for pat in patterns)


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
        suggested_fix="Fix the reported type errors or update the typing stubs to satisfy mypy.",
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
        suggested_fix="Inspect the failing tests and fix the regression or update expectations.",
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
        suggested_fix="Add or expand tests to raise coverage for the targeted module.",
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
        suggested_fix="Ensure the module exists, is in the correct path, and is declared in packaging.",
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
        suggested_fix="Fix the syntax error and rerun the formatter or linter if needed.",
        file_regexes=_compile([r"File \"(?P<path>[A-Za-z0-9_./-]+\.py)\""]),
        playbook_url="docs/fast-validation-ecosystem.md#error-handling",
    ),
)


def triage_ci_failure(
    log_text: str, patterns: tuple[TriagePattern, ...] = DEFAULT_TRIAGE_PATTERNS
) -> TriageReport:
    lines = [line.rstrip() for line in log_text.splitlines() if line.strip()]
    findings: list[TriageFinding] = []

    for pattern in patterns:
        evidence = _collect_evidence(lines, pattern.regexes)
        if not evidence:
            continue
        relevant_files = _extract_relevant_files(evidence, pattern.file_regexes)
        findings.append(
            TriageFinding(
                error_type=pattern.error_type,
                root_cause=pattern.root_cause,
                suggested_fix=pattern.suggested_fix,
                relevant_files=relevant_files,
                playbook_url=pattern.playbook_url,
                evidence=evidence,
            )
        )

    summary = _build_summary(findings)
    return TriageReport(findings=findings, summary=summary)


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


def _build_summary(findings: list[TriageFinding]) -> str:
    if not findings:
        return "No known failure patterns detected."
    types = ", ".join(finding.error_type for finding in findings)
    return f"Detected failure types: {types}."


def _report_to_dict(report: TriageReport) -> dict[str, object]:
    return {
        "summary": report.summary,
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
        return report.summary

    lines = [report.summary]
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
