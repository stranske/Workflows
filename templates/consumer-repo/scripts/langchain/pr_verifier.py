#!/usr/bin/env python3
"""
Evaluate pull requests with an LLM-backed rubric.

Run with:
    python scripts/langchain/pr_verifier.py --context-file verifier-context.md --json
"""

# ruff: noqa: I001

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from scripts import api_client
from scripts.langchain._llm_client import get_llm_client, get_llm_clients
from scripts.langchain.structured_output import (
    build_repair_callback,
    parse_structured_output,
)
from scripts.langchain.verifier_config import (
    EVAL_PAIR_BUDGET_TOKENS,
    EVAL_SCHEMA_REPAIR_BUDGET_TOKENS,
    MIN_CODE_COVERAGE_RATIO,
    VERIFIER_CONTEXT_BUDGET_TOKENS,
    VERIFIER_DIFF_BUDGET_TOKENS,
    SchemaRepairPolicy,
)

# The shared client builder returns the ClientInfo ``provider_label`` for the
# verifier (the historical ``_get_llm_client`` returned that field). Bound under
# the module name so existing tests can monkeypatch ``pr_verifier._get_llm_client``.
_get_llm_client = partial(get_llm_client, return_field="provider_label")
_get_llm_clients = get_llm_clients

LOGGER = logging.getLogger(__name__)
SCHEMA_REPAIR_POLICY = SchemaRepairPolicy()
TOKEN_CHARS = 4

PR_EVALUATION_PROMPT = """
You are reviewing a **merged** pull request to evaluate whether the code
changes meet the documented acceptance criteria.

**IMPORTANT: This verification runs AFTER the PR has been merged.** Therefore:
- Do NOT evaluate CI status, workflow runs, or pending checks - these are irrelevant post-merge
- Do NOT raise concerns about CI workflows being "in progress" or "queued"
- Focus ONLY on the actual code changes and whether they fulfill the requirements

PR Context:
{context}

PR Diff (summary or full):
{diff}

Evaluate the **code changes** against the acceptance criteria:
- correctness (does the implementation behave as intended based on the code)
- completeness (are all requirements addressed in the code changes)
- quality (code readability, maintainability, style)
- testing (are tests present and adequate for the acceptance criteria)
- risks (security, performance, compatibility concerns in the code)

An artifact explicitly required by acceptance criteria (such as a failing and
restored passing test transcript) is a completeness deliverable. If absent
from the supplied PR evidence, flag it even if implementation and ordinary
tests are otherwise correct. Do not confuse this with optional test coverage.

Ignore CI workflow status - focus on code quality and acceptance criteria fulfillment.

**Verdict guidelines:**
- **PASS**: correctness and completeness are satisfied.  Testing gaps alone
  should NOT prevent a PASS if the implementation is functionally correct,
  unless a test or evidence artifact is explicitly required for acceptance.
- **CONCERNS**: significant correctness or completeness issues exist, OR the
  implementation introduces meaningful risks.
- **FAIL**: the changes do not address the acceptance criteria or introduce
  breaking problems.

Respond in JSON with:
{{
  "verdict": "PASS | CONCERNS | FAIL",
  "confidence": 0.0-1.0,
  "scores": {{
    "correctness": 0-10,
    "completeness": 0-10,
    "quality": 0-10,
    "testing": 0-10,
    "risks": 0-10
  }},
  "concerns": ["..."],
  "summary": "concise report"
}}
""".strip()

# Relaxed prompt for infrastructure/platform changes (.github/, scripts/,
# docs/, templates/, config files).  Focuses on functional correctness and
# de-emphasizes comprehensive test coverage which is often impractical for
# workflow YAML, shell scripts, and documentation.
PR_EVALUATION_PROMPT_INFRA = """
You are reviewing a **merged** pull request that primarily modifies
**infrastructure and platform files** (GitHub Actions workflows, CI scripts,
documentation, configuration, or templates).

**IMPORTANT: This verification runs AFTER the PR has been merged.** Therefore:
- Do NOT evaluate CI status, workflow runs, or pending checks
- Focus on the actual changes and whether they fulfill the requirements

PR Context:
{context}

PR Diff (summary or full):
{diff}

Evaluate the **infrastructure changes** against the acceptance criteria.
Because these are infrastructure/platform changes rather than application code:
- **testing**: Only flag missing tests if the change breaks existing test suites
  or introduces testable logic (e.g., a new Python utility). Do NOT flag missing
  tests for workflow YAML, documentation, shell scripts, or config file changes.
- **correctness**: Does the implementation do what the issue asked for?
- **completeness**: Are all acceptance criteria addressed?
- **required evidence**: An artifact explicitly named in acceptance criteria
  is a deliverable; its absence is a completeness gap, not an optional test gap.
- **quality**: Is the code/config readable and maintainable?
- **risks**: Could this break CI, consumer repos, or existing automation?

Be LENIENT on test coverage for infrastructure work. Be STRICT on correctness
and risks (broken CI or consumer repos is a critical failure).

Respond in JSON with:
{{
  "verdict": "PASS | CONCERNS | FAIL",
  "confidence": 0.0-1.0,
  "scores": {{
    "correctness": 0-10,
    "completeness": 0-10,
    "quality": 0-10,
    "testing": 0-10,
    "risks": 0-10
  }},
  "concerns": ["..."],
  "summary": "concise report"
}}
""".strip()

# Addendum appended to any prompt (including custom) when infrastructure-
# dominant changes are detected.  This is lighter than the full INFRA prompt
# and avoids overriding a custom prompt file.
INFRA_PROMPT_ADDENDUM = """

## Infrastructure Change Guidance

This PR primarily modifies infrastructure/platform files (workflows, scripts,
docs, templates, or config).  Apply the following adjustments:
- **testing**: Do NOT penalise missing tests for workflow YAML, documentation,
  shell scripts, or config file changes.  Only flag missing tests when the PR
  introduces testable application logic (e.g. a new Python module).
- **required evidence**: If acceptance explicitly requires a transcript or
  other artifact in the PR evidence, treat its absence as a completeness gap.
- **risks**: Pay extra attention to CI breakage and consumer-repo impact.
- Be LENIENT on test coverage for infrastructure work.
""".strip()

# Addendum for follow-up PRs (chain depth > 0).  These are fix iterations
# addressing prior verifier feedback — testing gaps should NOT perpetuate
# the chain when the functional fix is correct.
CHAIN_DEPTH_ADDENDUM = """

## Follow-up Iteration Context

This PR is **follow-up iteration {depth}** in a verification chain.  It was
created specifically to address concerns raised by a previous verification.
Apply the following adjustments:
- **testing**: Do NOT raise CONCERNS solely for missing or incomplete tests
  unless the PR introduces new testable logic that is completely untested.
  Test coverage gaps alone should NOT prevent a PASS verdict when the
  functional implementation is correct.
- **required evidence**: If this follow-up explicitly requires a transcript
  or other artifact in the PR evidence, its absence is a completeness gap;
  it is not merely a test coverage concern.
- **correctness**: This is the primary criterion — does the fix address the
  original concerns?  Weight correctness heavily.
- **completeness**: Evaluate whether the specific concerns from the prior
  verification have been addressed.  Do not expand scope beyond what was asked.
- At chain depth {depth}, focus strictly on whether THIS iteration resolves
  its targeted concerns.  Avoid raising new concerns that were not part of
  the original feedback.
- Treat the original source issue/PR scope as baseline context that may
  already be satisfied by earlier merged work. Do NOT re-grade the full
  original issue checklist unless this iteration explicitly reopens it.
- If acceptance criteria require out-of-band GitHub metadata actions
  (for example: comments/labels/body updates on already merged PRs/issues),
  do not treat missing evidence in THIS diff as a hard completeness failure.
  Call these out as "external evidence required" and keep verdict focused on
  whether code/disposition artifacts in this iteration address the targeted
  verifier concerns.
""".strip()

# File path patterns considered infrastructure/platform rather than application
INFRA_PATH_PATTERNS: tuple[str, ...] = (
    ".github/",
    "scripts/",
    "docs/",
    "templates/",
    ".eslintrc",
    ".prettierrc",
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    "Makefile",
    "Dockerfile",
    "docker-compose",
    ".gitignore",
    ".pre-commit-config",
    "requirements",
    "CLAUDE.md",
    "README.md",
    "CHANGELOG.md",
    "LICENSE",
)

# Fraction of changed files that must be infrastructure to trigger relaxed mode
INFRA_THRESHOLD = 0.6

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "pr_evaluation.md"
REQUIRED_EVALUATION_AREAS = (
    "correctness",
    "completeness",
    "quality",
    "testing",
    "risks",
)
SCORE_KEYS = ("correctness", "completeness", "quality", "testing", "risks")


class EvaluationScores(BaseModel):
    correctness: float = Field(ge=0, le=10)
    completeness: float = Field(ge=0, le=10)
    quality: float = Field(ge=0, le=10)
    testing: float = Field(ge=0, le=10)
    risks: float = Field(ge=0, le=10)


class EvaluationResult(BaseModel):
    verdict: Literal["PASS", "CONCERNS", "FAIL"]
    scores: EvaluationScores | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    concerns: list[str] = Field(default_factory=list)
    summary: str | None = None
    provider_used: str | None = None
    model: str | None = None
    used_llm: bool = False
    raw_content: str | None = None
    error: str | None = None
    change_type: Literal["infrastructure", "application", "mixed"] | None = None
    langsmith_trace_id: str | None = None
    langsmith_trace_url: str | None = None
    input_coverage: dict[str, object] | None = None


class EvaluationPayload(BaseModel):
    model_config = {"extra": "ignore"}
    verdict: Literal["PASS", "CONCERNS", "FAIL"]
    scores: EvaluationScores | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    concerns: list[str] = Field(default_factory=list)
    summary: str | None = None


def _ensure_prompt_rubric(prompt: str) -> str:
    lowered = prompt.lower()
    if all(area in lowered for area in REQUIRED_EVALUATION_AREAS):
        return prompt

    rubric_lines = [
        "",
        "Provide an evaluation that covers:",
        "- correctness",
        "- completeness",
        "- quality",
        "- testing",
        "- risks",
    ]
    return prompt.rstrip() + "\n" + "\n".join(rubric_lines) + "\n"


def _load_prompt() -> str:
    if PROMPT_PATH.is_file():
        prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()
        return _ensure_prompt_rubric(prompt)
    return _ensure_prompt_rubric(PR_EVALUATION_PROMPT)


@dataclass(frozen=True)
class ComparisonRunner:
    context: str
    diff: str | None
    prompt: str
    clients: list[tuple[object, str, str]]  # (client, provider, model)
    coverage: PromptCoverage | None = None

    @classmethod
    def from_environment(
        cls, context: str, diff: str | None, model1: str | None = None, model2: str | None = None
    ) -> ComparisonRunner:
        return cls(
            context=context,
            diff=diff,
            prompt=_prepare_prompt(context, diff),
            clients=_get_llm_clients(model1, model2),
            coverage=prompt_coverage(context, diff),
        )

    def run_single(self, client: object, provider: str, model: str) -> EvaluationResult:
        try:
            response, trace_id, trace_url = _invoke_llm(
                client,
                self.prompt,
                operation="evaluate_pr_compare",
                context=self.context,
            )
        except Exception as exc:  # pragma: no cover - exercised in integration
            return _apply_coverage_floor(
                _fallback_evaluation(
                    f"LLM invocation failed: {exc}", provider=provider, model=model
                ),
                self.coverage,
            )

        content = getattr(response, "content", None) or str(response)
        result = _parse_llm_response(content, provider, client=client)
        result.model = model
        result.langsmith_trace_id = trace_id
        result.langsmith_trace_url = trace_url
        return _apply_coverage_floor(result, self.coverage)


def _classify_change_type(
    diff: str | None,
) -> Literal["infrastructure", "application", "mixed"]:
    """Classify a PR's change type by scanning diff file paths.

    Returns ``"infrastructure"`` when ≥ *INFRA_THRESHOLD* of changed files
    match infrastructure path patterns, ``"application"`` when fewer than
    (1 − INFRA_THRESHOLD) match, and ``"mixed"`` otherwise.
    """
    if not diff or not diff.strip():
        return "application"  # default when no diff available

    # Extract file paths from unified diff headers: "diff --git a/path b/path"
    # and "--- a/path" / "+++ b/path" lines
    file_paths: set[str] = set()
    for line in diff.splitlines():
        if line.startswith("diff --git"):
            parts = line.split()
            if len(parts) >= 4:
                # "diff --git a/foo b/foo" → "foo"
                path = parts[2].removeprefix("a/")
                file_paths.add(path)
        elif line.startswith("+++ b/") or line.startswith("--- a/"):
            path = line[6:]  # strip "+++ b/" or "--- a/"
            if path and path != "/dev/null":
                file_paths.add(path)

    if not file_paths:
        return "application"

    infra_count = sum(
        1
        for fp in file_paths
        if any(fp.startswith(pat) or fp.endswith(pat) for pat in INFRA_PATH_PATTERNS)
    )
    ratio = infra_count / len(file_paths)
    LOGGER.debug(
        "Change-type classification: %d/%d files are infrastructure (%.0f%%)",
        infra_count,
        len(file_paths),
        ratio * 100,
    )

    if ratio >= INFRA_THRESHOLD:
        return "infrastructure"
    if ratio <= (1 - INFRA_THRESHOLD):
        return "application"
    return "mixed"


def _get_chain_depth() -> int:
    """Read follow-up chain depth from environment.

    Set by the verifier context builder when the linked issue contains a
    ``<!-- follow-up-depth: N -->`` marker injected by agents-verify-to-new-pr.
    """
    raw = os.environ.get("CHAIN_DEPTH", "0")
    try:
        return max(0, int(raw))
    except (ValueError, TypeError):
        return 0


VERIFIER_CONTEXT_TITLE = "# Verifier context"
CI_SECTION = "## CI Information"
ACCEPTANCE_SECTION = "## Plan sources (scope, tasks, acceptance)"
ACCEPTANCE_EVIDENCE_SECTION = "## Acceptance evidence"
DIFF_SUMMARY_SECTION = "## PR Diff Summary"
FULL_DIFF_SECTION = "## PR Diff (full)"
UPSTREAM_DIFF_TRUNCATION = re.compile(r"\.\.\.diff truncated after \d+ characters\.")
TRUNCATION_MARKER = "[truncated: verifier prompt budget exceeded]"
SUMMARY_DELTA_SUFFIX = re.compile(r"\s+\((?:\+\d+/-\d+|binary)\)\s*$")
CoverageStatus = Literal["complete", "truncated", "unavailable", "not_declared"]


@dataclass(frozen=True)
class FileCoverage:
    path: str
    status: Literal["complete", "truncated", "omitted"]
    included_chars: int
    total_chars: int


@dataclass(frozen=True)
class PromptCoverage:
    """What the model actually receives, computed before any model call."""

    acceptance: CoverageStatus
    acceptance_evidence: CoverageStatus
    code: CoverageStatus
    files: tuple[FileCoverage, ...]
    code_included_chars: int
    code_total_chars: int
    context_truncated: bool
    reasons: tuple[str, ...]
    acceptance_source_discovery: CoverageStatus = "not_declared"

    @property
    def sufficient(self) -> bool:
        return not self.reasons

    @property
    def code_ratio(self) -> float:
        if self.code_total_chars <= 0:
            return 1.0 if self.code == "complete" else 0.0
        return self.code_included_chars / self.code_total_chars

    def to_dict(self) -> dict[str, object]:
        status_counts = {
            status: sum(1 for item in self.files if item.status == status)
            for status in ("complete", "truncated", "omitted")
        }
        return {
            "sufficient": self.sufficient,
            "acceptance": self.acceptance,
            "acceptance_evidence": self.acceptance_evidence,
            "acceptance_source_discovery": self.acceptance_source_discovery,
            "code": self.code,
            "files_total": len(self.files),
            "files_complete": status_counts["complete"],
            "files_truncated": status_counts["truncated"],
            "files_omitted": status_counts["omitted"],
            "omitted_files": [item.path for item in self.files if item.status == "omitted"],
            "code_included_chars": self.code_included_chars,
            "code_total_chars": self.code_total_chars,
            "code_ratio": round(self.code_ratio, 4),
            "context_truncated": self.context_truncated,
            "reasons": list(self.reasons),
        }

    def render(self) -> str:
        lines = [
            "## Verifier input coverage",
            "",
            "This block is computed deterministically before the model call and states "
            "which evidence below is complete. Text that is not shown was not reviewed.",
            "",
            f"- Acceptance / plan sources: {self.acceptance}",
            f"- Linked-issue acceptance discovery: {self.acceptance_source_discovery}",
            f"- Acceptance evidence: {self.acceptance_evidence}",
            (
                f"- Changed code: {self.code} — {len(self.files)} file(s); "
                f"{sum(1 for f in self.files if f.status == 'complete')} complete, "
                f"{sum(1 for f in self.files if f.status == 'truncated')} truncated, "
                f"{sum(1 for f in self.files if f.status == 'omitted')} omitted; "
                f"{self.code_included_chars}/{self.code_total_chars} characters shown"
            ),
        ]
        partial = [f for f in self.files if f.status != "complete"]
        for item in partial[:40]:
            lines.append(
                f"  - {item.path}: {item.status} ({item.included_chars}/{item.total_chars} chars)"
            )
        if len(partial) > 40:
            lines.append(f"  - ... {len(partial) - 40} more partial file(s)")
        if self.sufficient:
            lines.append("- Coverage verdict: sufficient for a PASS decision.")
        else:
            lines.append("- Coverage verdict: INCOMPLETE — do not return PASS. Reasons:")
            lines.extend(f"  - {reason}" for reason in self.reasons)
        return "\n".join(lines)


@dataclass(frozen=True)
class PromptInputs:
    context_block: str
    diff_block: str
    coverage: PromptCoverage


def _budget_from_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _code_fence_marker(line: str) -> tuple[str, bool, int] | None:
    """Inspect a fence without treating an info string as a closing marker.

    Retain indentation for nested/indented source snippets; their literal
    headings must remain inert too. A root fence cannot close at four spaces.
    """
    match = re.match(r"^([ \t]*)(`{3,}|~{3,})(.*)$", line.rstrip("\r\n"))
    if not match:
        return None
    indent, marker, suffix = match.groups()
    if marker[0] == "`" and "`" in suffix:
        return None
    return marker, not suffix.strip(" \t"), len(indent.expandtabs(4))


def _split_verifier_context(context: str) -> list[tuple[str, str]] | None:
    """Split a structured verifier context into its builder sections.

    Returns ``None`` for free-form context. Plan sources embed PR/issue bodies
    that may contain arbitrary ``##`` headings, so only the builder's own
    headings are used, located in the order the builder writes them: the
    full diff is always last, and the summary is the last one before it.  The
    generated acceptance-evidence block follows plan sources and must be
    split independently: large untrusted comments or artifacts must not spend
    the acceptance-plan budget.
    """
    text = "\n" + context
    # Evidence payloads are fenced with a fence longer than any backtick run
    # in the payload. Only builder headings outside those fences are structural.
    headings: dict[str, list[int]] = {
        heading: []
        for heading in (
            CI_SECTION,
            ACCEPTANCE_SECTION,
            ACCEPTANCE_EVIDENCE_SECTION,
            DIFF_SUMMARY_SECTION,
            FULL_DIFF_SECTION,
        )
    }
    offset = 0
    fence_char = ""
    fence_length = 0
    fence_indent = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        fence = _code_fence_marker(line)
        if fence:
            marker, closing, indent = fence
            if not fence_char:
                fence_char, fence_length = marker[0], len(marker)
                fence_indent = indent
            elif (
                marker[0] == fence_char
                and len(marker) >= fence_length
                and closing
                and indent <= max(3, fence_indent)
            ):
                fence_char, fence_length = "", 0
                fence_indent = 0
        elif not fence_char and stripped in headings:
            headings[stripped].append(offset)
        offset += len(line)
    ci = next(iter(headings[CI_SECTION]), -1)
    plan = next((pos for pos in headings[ACCEPTANCE_SECTION] if pos > ci), -1)
    anchor = max(ci, plan, 0)
    full = next((pos for pos in reversed(headings[FULL_DIFF_SECTION]) if pos > anchor), -1)
    summary_end = full if full >= 0 else len(text)
    summary = next(
        (pos for pos in reversed(headings[DIFF_SUMMARY_SECTION]) if anchor < pos < summary_end), -1
    )
    evidence_end = summary if summary >= 0 else summary_end
    evidence = next(
        (
            pos
            for pos in reversed(headings[ACCEPTANCE_EVIDENCE_SECTION])
            if max(plan, 0) < pos < evidence_end
        ),
        -1,
    )
    if (
        not context.startswith(VERIFIER_CONTEXT_TITLE)
        and max(ci, plan, evidence, summary, full) < 0
    ):
        return None
    marks = [("preamble", 0)]
    if ci >= 0:
        marks.append(("ci", ci))
    if plan >= 0:
        marks.append(("acceptance", plan))
    if evidence >= 0:
        marks.append(("acceptance_evidence", evidence))
    if summary >= 0:
        marks.append(("diff_summary", summary))
    if full >= 0:
        marks.append(("full_diff", full))
    sections = []
    for index, (name, start) in enumerate(marks):
        end = marks[index + 1][1] if index + 1 < len(marks) else len(text)
        body = text[start:end].strip("\n")
        if body or name != "preamble":
            sections.append((name, body))
    return sections


def _strip_diff_fence(section: str) -> str:
    body = section.split("\n", 1)[1] if "\n" in section else ""
    body = body.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[1] if "\n" in body else ""
    if body.rstrip().endswith("```"):
        body = body.rstrip()[:-3]
    return body.strip("\n")


def _split_diff_files(diff: str) -> list[tuple[str | None, str]]:
    def decode_quoted_path(raw: str) -> tuple[str, str] | None:
        if not raw.startswith('"'):
            return None
        chunks: list[bytes] = []
        index = 1
        escapes = {
            "a": "\a",
            "b": "\b",
            "f": "\f",
            "n": "\n",
            "r": "\r",
            "t": "\t",
            "v": "\v",
            "\\": "\\",
            '"': '"',
        }
        while index < len(raw):
            char = raw[index]
            if char == '"':
                try:
                    return b"".join(chunks).decode("utf-8"), raw[index + 1 :]
                except UnicodeDecodeError:
                    return None
            if char != "\\":
                chunks.append(char.encode("utf-8"))
                index += 1
                continue
            if index + 1 >= len(raw):
                return None
            escaped = raw[index + 1]
            if escaped in "01234567":
                octal = raw[index + 1 : index + 4]
                if len(octal) != 3 or not all(char in "01234567" for char in octal):
                    return None
                byte = int(octal, 8)
                if byte > 0xFF:
                    return None
                chunks.append(bytes([byte]))
                index += 4
                continue
            if escaped not in escapes:
                return None
            chunks.append(escapes[escaped].encode("utf-8"))
            index += 2
        return None

    def normalized_path(raw: str, *, strip_prefix: bool = True) -> str | None:
        value = raw.rstrip("\n").split("\t", 1)[0]
        if value == "/dev/null":
            return ""
        if value.startswith('"'):
            parsed = decode_quoted_path(value)
            if parsed is None or parsed[1].strip():
                return None
            value = parsed[0]
        return value[2:] if strip_prefix and value.startswith(("a/", "b/")) else value

    def destination_from_git_header(line: str) -> str | None:
        payload = line.removeprefix("diff --git ").rstrip("\n")

        # Mode-only changes have no +++ or rename metadata. Prefer the
        # unambiguous identical-path split rather than an embedded " b/".
        if payload.startswith("a/"):
            identical = [
                payload[match.start() + 3 :]
                for match in re.finditer(r" b/", payload)
                if payload[2 : match.start()] == payload[match.start() + 3 :]
            ]
            if len(identical) == 1:
                return identical[0]

        separator = max(payload.rfind(" b/"), payload.rfind(' "b/'))
        source = (
            decode_quoted_path(payload)
            if payload.startswith('"')
            else (payload[:separator], payload[separator:]) if separator > 0 else None
        )
        if source is None or not source[1].startswith(" "):
            return None
        destination = source[1].lstrip()
        decoded = (
            decode_quoted_path(destination) if destination.startswith('"') else (destination, "")
        )
        if decoded is None or decoded[1].strip():
            return None
        if not source[0].startswith("a/") or not decoded[0].startswith("b/"):
            return None
        return decoded[0][2:]

    files: list[tuple[str | None, str]] = []
    current: list[str] = []
    path: str | None = None
    in_hunk = False
    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if current:
                files.append((path, "".join(current)))
            current = [line]
            path = destination_from_git_header(line) or None
            in_hunk = False
        elif current:
            current.append(line)
            if line.startswith("@@"):
                in_hunk = True
            if path is None or in_hunk:
                continue
            if line.startswith("--- "):
                source = normalized_path(line[4:])
                if source is None:
                    path = None
                elif source:
                    path = source
            elif line.startswith("+++ "):
                destination = normalized_path(line[4:])
                if destination is None:
                    path = None
                elif destination:
                    path = destination
            elif line.startswith(("rename to ", "copy to ")):
                # Git's metadata is repo-relative and unambiguous even when an
                # unquoted header contains an embedded " b/" separator.
                destination = normalized_path(line.split(" to ", 1)[1], strip_prefix=False)
                path = destination or None
    if current:
        files.append((path, "".join(current)))
    return files


def _summary_destination_paths(summary: str) -> list[str]:
    """Extract destination paths from the context builder's file summary."""
    paths: list[str] = []
    in_file_changes = False
    for raw_line in summary.splitlines():
        line = raw_line.strip()
        if line == "### File changes":
            in_file_changes = True
            continue
        if in_file_changes and line.startswith("### "):
            break
        if not in_file_changes or not line.startswith("- "):
            continue
        encoded_path = re.search(r' <!-- verifier-file-path:v1 ("(?:[^"\\]|\\.)*") -->$', line)
        if encoded_path:
            try:
                destination = json.loads(encoded_path.group(1))
            except (ValueError, TypeError) as error:
                raise ValueError("Malformed encoded summary destination") from error
            if isinstance(destination, str) and destination:
                paths.append(destination)
            else:
                raise ValueError("Empty or non-string encoded summary destination")
            continue
        if " <!-- verifier-file-path:v1 " in line:
            raise ValueError("Malformed encoded summary destination")
        label = SUMMARY_DELTA_SUFFIX.sub("", line[2:].strip())
        for marker in (" (added)", " (deleted)"):
            if label.endswith(marker):
                label = label[: -len(marker)]
                break
        if " -> " in label:
            label = label.rsplit(" -> ", 1)[1]
        if label and not (label.startswith("...and ") and label.endswith(" more files")):
            paths.append(label)
    return paths


def _fair_shares(sizes: list[int], budget: int) -> list[int]:
    """Water-fill ``budget`` across items so small files are shown whole."""
    shares = [0] * len(sizes)
    remaining = set(range(len(sizes)))
    left = budget
    while remaining and left > 0:
        share = left // len(remaining)
        if share <= 0:
            break
        satisfied = {i for i in remaining if sizes[i] - shares[i] <= share}
        if not satisfied:
            for i in remaining:
                shares[i] += share
            left -= share * len(remaining)
            break
        for i in satisfied:
            left -= sizes[i] - shares[i]
            shares[i] = sizes[i]
        remaining -= satisfied
    return shares


def _diff_file_is_binary_descriptor(text: str) -> bool:
    """True when Git reports a binary change without inspectable text hunks."""
    has_hunk = False
    has_binary_marker = False
    for line in text.splitlines():
        if line.startswith("@@"):
            has_hunk = True
        elif line.startswith("Binary files ") or line.startswith("GIT binary patch"):
            has_binary_marker = True
    return has_binary_marker and not has_hunk


def _excerpt_file(path: str, text: str, share: int) -> tuple[str, FileCoverage]:
    total = len(text)
    if _diff_file_is_binary_descriptor(text):
        return "", FileCoverage(path, "omitted", 0, total)
    if share >= total:
        return text, FileCoverage(path, "complete", total, total)
    omitted_note = "[... remaining lines of {path} omitted: verifier prompt budget ...]\n"
    # Reserve the separator too if the excerpt ends in the middle of a line.
    reserve = len(omitted_note.format(path=path)) + 1
    header_end = text.find("\n@@")
    header_len = header_end + 1 if header_end >= 0 else min(total, 200)
    if share - reserve <= header_len:
        return "", FileCoverage(path, "omitted", 0, total)
    shown = text[: share - reserve]
    cut = shown.rfind("\n")
    if cut > header_len:
        shown = shown[: cut + 1]
    elif not shown.endswith("\n"):
        shown += "\n"
    return shown + omitted_note.format(path=path), FileCoverage(
        path, "truncated", len(shown), total
    )


def _build_code_block(
    diff: str, budget_chars: int
) -> tuple[str, CoverageStatus, tuple[FileCoverage, ...], int, int]:
    files = _split_diff_files(diff)
    if not files:
        if diff.strip():
            return "(diff unavailable)", "unavailable", (), 0, 0
        block = _cap_prompt_text(diff, max(1, budget_chars // TOKEN_CHARS))
        status: CoverageStatus = "complete" if block == diff else "truncated"
        return block, status, (), min(len(diff), len(block)), len(diff)
    if any(path is None for path, _ in files):
        return "(diff unavailable)", "unavailable", (), 0, 0
    # Doc-Lineage#81 review finding (discussion_r4169521235): appending
    # omitted paths after fair-share allocation exceeded the diff budget.
    # Fit text first, then use spare budget for a count-only diagnostic.
    # Omitted paths remain in FileCoverage metadata and still prevent PASS.
    sizes = [0 if _diff_file_is_binary_descriptor(text) else len(text) for _, text in files]
    omission_note = "[{count} changed file(s) omitted entirely — not shown to the reviewer]\n"
    shares = _fair_shares(sizes, max(0, budget_chars))
    parts: list[str] = []
    coverage: list[FileCoverage] = []
    omitted = 0
    for (path, text), share in zip(files, shares, strict=True):
        assert path is not None  # Parse failures were rejected above.
        excerpt, item = _excerpt_file(path, text, share)
        coverage.append(item)
        if excerpt:
            parts.append(excerpt)
        else:
            omitted += 1
    if omitted:
        note_budget = max(0, budget_chars - sum(len(part) for part in parts))
        parts.append(omission_note.format(count=omitted)[:note_budget])
    included = sum(item.included_chars for item in coverage)
    total = sum(item.total_chars for item in coverage)
    status = "complete" if all(item.status == "complete" for item in coverage) else "truncated"
    return "".join(parts).rstrip("\n"), status, tuple(coverage), included, total


def _fit_context_sections(
    sections: list[tuple[str, str]], budget_chars: int
) -> tuple[list[str], dict[str, str]]:
    """Fill sections in priority order (acceptance first), emit in source order."""
    priority = {"acceptance": 0, "ci": 1, "diff_summary": 2, "preamble": 3}
    order = sorted(range(len(sections)), key=lambda i: priority.get(sections[i][0], 9))
    left = budget_chars
    fitted: dict[int, str] = {}
    status: dict[str, str] = {}
    for index in order:
        name, body = sections[index]
        if len(body) <= left:
            fitted[index] = body
            status[name] = "complete"
            left -= len(body) + 2
        elif left > len(TRUNCATION_MARKER) + 80:
            fitted[index] = _cap_prompt_text(body, max(1, left // TOKEN_CHARS))
            status[name] = "truncated"
            left = 0
        else:
            status[name] = "unavailable"
        left = max(0, left)
    return [fitted[i] for i in range(len(sections)) if i in fitted], status


def _acceptance_criteria_sections(plan_sources: str) -> str:
    """Return only acceptance-criteria subsections from structured plan sources."""
    lines: list[str] = []
    fence_char: str | None = None
    fence_len = 0
    fence_indent = 0
    for raw_line in plan_sources.splitlines():
        fence = _code_fence_marker(raw_line)
        if fence:
            marker, closing, indent = fence
            if fence_char is None:
                fence_char = marker[0]
                fence_len = len(marker)
                fence_indent = indent
            elif (
                marker[0] == fence_char
                and len(marker) >= fence_len
                and closing
                and indent <= max(3, fence_indent)
            ):
                fence_char = None
                fence_len = 0
                fence_indent = 0
            lines.append("")
            continue
        lines.append("" if fence_char is not None else raw_line)
    captured: list[str] = []
    index = 0
    while index < len(lines):
        heading = re.match(
            r"^(#{1,6})\s+acceptance[\s_-]*criteria\s*:?[\s]*$",
            lines[index].strip(),
            flags=re.I,
        )
        if not heading:
            index += 1
            continue
        level = len(heading.group(1))
        section: list[str] = []
        index += 1
        while index < len(lines):
            next_heading = re.match(r"^(#{1,6})\s+", lines[index].strip())
            if next_heading and len(next_heading.group(1)) <= level:
                break
            section.append(lines[index])
            index += 1
        captured.append("\n".join(section).strip())
    return "\n\n".join(part for part in captured if part)


def _required_evidence_channels(acceptance: str, *, _bind_attached: bool = True) -> set[str]:
    """Identify explicit evidence deliverables without treating negations as requirements."""
    channels: set[str] = set()
    response_operation = (
        r"(?:include|contain|have|return|display|show|store|emit|render|expose|provide)\w*\b"
    )
    delivery_operation = r"(?:provide|return|display|show|emit|render|expose|store|upload|attach|publish|post|record|capture|include|contain|have|document|generate|link|add|leave)\w*\b"
    capability_operation = r"(?:(?:allow|enable|support)\w*|let(?:s|ting)?)"
    evidence_modifiers = (
        r"(?:(?!(?:and|or|but|must|shall|is|are|not|never|may|can)\b)[\w/-]+\s+){0,6}"
    )
    mandatory_auxiliary = (
        r"(?:(?:must|shall|needs?\s+to)|"
        r"(?:(?:is|are)\s+)?(?:required|needed|mandated|expected|supposed|obliged)\s+to|"
        r"(?:has|have)\s+to)"
    )
    delivery_adverb = r"(?:also|now|still|already|yet|[\w-]+ly)"
    delivery_adverbs = r"(?:" + delivery_adverb + r"\s+){0,3}"
    passive_delivery_prefix = (
        r"(?:be|have\s+" + delivery_adverbs + r"been)" r"(?:\s+" + delivery_adverbs + r"being)?\s+"
    )
    conditional_evidence = r"\b(?:if|when)\s+(?:produced|available|present|uploaded|generated)\b"
    recipient_prefix = (
        r"(?:(?:all|any|some|each|every)\s+)?"
        r"(?:(?:the|its|our|their|your|an?)\s+)?"
        r"(?:(?!(?:and|or|but|must|shall|is|are|not|never|may|can|to|of|for|by|with|who|that|which)\b)[\w/-]+\s+){0,4}"
    )
    recipient_noun = recipient_prefix + r"(?:clients?|users?|consumers?)\b"
    product_recipient = r"(?:to|for)\s+" + recipient_noun
    artifact_destination_object = r"(?:workflow|ci|github actions)\s+artifacts?\b"
    review_destination_noun = (
        r"(?:(?:the|an?)\s+)?(?:"
        r"(?:pr|pull request)\s+body\b(?:\s+editor\b)?|"
        r"(?:pr|pull request)\s+comments?\b|"
        + artifact_destination_object
        + r"|(?:pr|pull request)\b)"
    )
    independent_review_predicate = (
        r"(?:must|shall|needs?\s+to|has\s+to|have\s+to|is|are|will|should|may|can)\b"
    )
    destination_preposition = r"(?:in|into|to|within|for|as|through|via)\s+"
    delivery_destination_item = r"(?:" + review_destination_noun + "|" + recipient_noun + ")"
    delivery_destination_separator_base = r"(?:\s*,\s*(?:(?:and|or)\s+)?|\s+(?:and|or)\s+)"
    delivery_destination_separator = (
        delivery_destination_separator_base + r"(?:" + destination_preposition + r")?"
    )
    shared_storage_separator_base = delivery_destination_separator_base.replace("(?:and|or)", "and")
    shared_storage_separator = (
        shared_storage_separator_base + r"(?:" + destination_preposition + r")?"
    )
    bound_review_destinations = (
        destination_preposition + r"(?:both\s+)?"
        r"(?=(?:"
        + delivery_destination_item
        + delivery_destination_separator
        + r")*"
        + review_destination_noun
        + r")"
        + delivery_destination_item
        + r"(?:"
        + delivery_destination_separator
        + delivery_destination_item
        + r")*"
    )
    # Normalize equivalent destinations before presence predicates, not after.
    acceptance = re.sub(
        r"\bcomments?\s+(?:on|in)\s+(?:(?:the|an?)\s+)?(?:pr|pull request)\b",
        "PR comment",
        acceptance,
        flags=re.I,
    )
    # Presence predicates use the existing passive-delivery grammar, including
    # governing negation and modality, instead of a second affirmative regex.
    acceptance = re.sub(
        r"(?P<prefix>\b(?:no\s+|neither\s+"
        + evidence_modifiers
        + r"(?:evidence|artifacts?|command outputs?|transcripts?)\s+nor\s+)?"
        + evidence_modifiers
        + r"(?:evidence|artifacts?|command outputs?|transcripts?)\s+"
        + mandatory_auxiliary
        + r"\s+"
        + delivery_adverbs
        + r"(?:not\s+)?)"
        r"(?:appear|be\s+present)"
        r"(?P<destination>\s+in\s+(?:an?\s+|the\s+)?"
        r"(?:pr comments?|pull request comments?)\b)",
        lambda match: (
            match["prefix"] + "be recorded" + match["destination"]
            if not re.match(r"(?:no|neither)\s+", match["prefix"], re.I)
            else match[0]
        ),
        acceptance,
        flags=re.I,
    )
    # Lexical aliases share every obligation, negation, destination and product
    # boundary rule. Adding a synonym to only one regex silently diverges them.
    record_aliases = {
        "paste": "record",
        "put": "record",
        "puts": "records",
        "putting": "recording",
        "place": "record",
        "places": "records",
        "placed": "recorded",
        "placing": "recording",
        "pastes": "records",
        "pasted": "recorded",
        "pasting": "recording",
        "write": "record",
        "writes": "records",
        "written": "recorded",
        "writing": "recording",
        "wrote": "recorded",
        "submit": "record",
        "submits": "records",
        "submitted": "recorded",
        "submitting": "recording",
        "deliver": "record",
        "delivers": "records",
        "delivered": "recorded",
        "delivering": "recording",
    }

    quoted_evidence_literal = (
        r"`+[^`]*`+|\"[^\"]*\"|"
        r"(?<!\w)'(?:[^']|(?<=\w)'(?=\w))*'(?!\w)|"
        r"“[^”]*”|(?<!\w)‘(?:[^’]|(?<=\w)’(?=\w))*’(?!\w)"
    )
    parenthetical_actor = (
        r"\b(?:reviewers?|maintainers?|authors?|operators?|agents?|bots?|runners?|"
        r"developers?|engineers?|testers?|auditors?|verifiers?|teams?|users?|"
        r"ui|api|application|service|endpoint)"
    )
    parenthetical_aside = (
        r"(?!(?:(?:and|or)\s+)?"
        + r"(?:"
        + destination_preposition
        + r")?"
        + review_destination_noun
        + r")"
        r"(?:(?!(?:"
        + mandatory_auxiliary
        + r"|must|shall|will|can|could|would|should|may|is|are|was|were|has|have|had|"
        r"required|needed|mandatory|optional|if|when|without|unless|until|not|never|no)\b)"
        r"(?!(?:"
        + delivery_operation
        + "|"
        + "|".join(record_aliases)
        + r")\s+(?:"
        + evidence_modifiers
        + r"(?:evidence|artifacts?|transcripts?|command outputs?)\b|"
        + destination_preposition
        + review_destination_noun
        + r"))"
        r"[\w-]+(?=\s|,)\s*){1,12}"
    )
    acceptance = re.sub(
        r"(?P<literal>"
        + quoted_evidence_literal
        + r")|(?P<actor>"
        + parenthetical_actor
        + r")\s*,\s*"
        + parenthetical_aside
        + r"\s*,\s*",
        lambda match: match[0] if match["literal"] else match["actor"] + " ",
        acceptance,
        flags=re.I,
    )

    def normalize_record_alias(match: re.Match[str]) -> str:
        """Preserve literals and participial modifiers of a prior governing verb."""
        alias = match["alias"]
        if not alias:
            return match[0]
        if alias.lower() in {"written", "pasted", "placed", "submitted", "delivered"}:
            prefix = re.split(
                r"[;,.!?\n]|\b(?:and|or|but|that|which|who|while|after|once|before|when|until|unless|if|since|because|whereas|although)\b",
                acceptance[: match.start()],
                flags=re.I,
            )[-1]
            # Inspect the actor without altering the original checklist semantics.
            prefix = re.sub(
                r"^\s*(?:(?:[-*+]|\d+[.)])\s*(?:\[[ xX]\]\s*)?|\[[ xX]\]\s*)?",
                "",
                prefix,
            )
            active_delivery_subject = (
                alias.lower() in {"placed", "submitted", "delivered"}
                and bool(
                    re.fullmatch(
                        r"\s*(?:(?:the|an?)\s+)?"
                        + evidence_modifiers
                        + r"(?:reviewers?|maintainers?|authors?|operators?|agents?|bots?|runners?|"
                        r"developers?|engineers?|testers?|auditors?|verifiers?|teams?|users?|"
                        r"ui|api|application|service|endpoint)\s+" + delivery_adverbs + r"\s*",
                        prefix,
                        re.I,
                    )
                )
                and not bool(re.search(response_operation + "|" + delivery_operation, prefix, re.I))
            )
            if not active_delivery_subject and not re.search(
                r"\b(?:" + mandatory_auxiliary + r"|is|are|was|were|be|been|being|has|have|had)\s+"
                r"(?:(?:not|never|no\s+longer|" + delivery_adverb + r")\s+)*$",
                prefix,
                re.I,
            ):
                return match[0]
        if alias.lower() == "put" and re.search(
            r"\b(?:(?:is|are|was|were)(?:n['’]t)?|be|been|being)\s+"
            r"(?:(?:not|never|no\s+longer|" + delivery_adverb + r")\s+)*$",
            acceptance[: match.start()],
            re.I,
        ):
            return "recorded"
        return record_aliases[alias.lower()]

    acceptance = re.sub(
        r"(?P<literal>" + quoted_evidence_literal + r"|"
        r"\b(?:the|an?)\s+(?:write|paste|put|place|submit|deliver)\b"
        r"(?:\s+(?!(?:and|or|must|shall|will)\b)[\w-]+){0,6}\s+command\b"
        r"(?=\s+(?:(?:must|shall|will)\s+output|outputs)\b))|"
        r"(?P<alias>\b(?:put|puts|putting|place|places|placed|placing|paste|pastes|pasted|pasting|write|writes|written|writing|wrote|"
        r"submit|submits|submitted|submitting|deliver|delivers|delivered|delivering)\b)"
        r"(?=\s+"
        + evidence_modifiers
        + r"(?:evidence|artifacts?|transcripts?|command outputs?|pr comments?|pull request comments?)\b"
        r"|\s+"
        + destination_preposition
        + r"(?:both\s+)?"
        + delivery_destination_item
        + r"|\s+(?:(?:in|into|to|as)\s+(?:(?:its|the|an?)\s+)?"
        r"(?:database|audit log|storage|application log)\b|" + product_recipient + r")"
        r"\s+by\s+(?:(?:the|an?)\s+)?(?:application|app|service|api|endpoint)\b)",
        normalize_record_alias,
        acceptance,
        flags=re.I,
    )
    # Use the same product-response operation vocabulary when coalescing object
    # groups and when excluding response fields from review deliverables.
    response_subject = r"(?:responses?|payloads?|return\s+values?|reports?|exports?)"
    optional_delivery_modal = r"(?:may|can|could|would|should)"
    product_auxiliary = (
        r"(?:" + mandatory_auxiliary + r"|will|" + optional_delivery_modal + r"|do|does|did)\s+"
    )
    product_actor = r"(?:(?:the|an?)\s+)?(?:application|app|service|api|endpoint)"
    delivery_governor_auxiliary = (
        r"(?:"
        + mandatory_auxiliary
        + r"|will|"
        + optional_delivery_modal
        + r"|has|have|had|is|are|was|were|do|does|did)"
    )
    product_aspect = (
        r"(?:"
        + delivery_governor_auxiliary
        + r"\s+)?"
        + delivery_adverbs
        + r"(?:have\s+)?(?:be\s+|been\s+)?(?:being\s+)?"
        + delivery_adverbs
    )
    product_evidence_object = (
        r"(?:(?:the|an?)\s+)?"
        + evidence_modifiers
        + r"(?:transcripts?|command outputs?|evidence|artifacts?)\s+"
    )
    product_destination = (
        r"(?:(?:in|into|to|as)\s+(?:(?:its|the|an?)\s+)?"
        r"(?:database|audit log|storage|application log)\b|" + product_recipient + r")"
    )
    bound_product_delivery = re.compile(
        r"\b"
        + product_actor
        + r"\s+"
        + product_aspect
        + r"(?:record|capture|attach|generate|return|display|emit|render|expose|provide)\w*\s+"
        + product_evidence_object
        + product_destination
        + r"(?!"
        + delivery_destination_separator
        + review_destination_noun
        + r")"
        + r"|\b"
        + product_evidence_object
        + product_aspect
        + r"(?:recorded|captured|attached|generated|returned|displayed|emitted|rendered|exposed|provided)\s+"
        + product_destination
        + r"\s+by\s+"
        + product_actor
        + r"\b(?!"
        + delivery_destination_separator
        + review_destination_noun
        + r")",
        re.I,
    )
    shared_storage_review_destination = re.compile(
        r"(?P<predicate>\b"
        + product_actor
        + r"\s+"
        + product_aspect
        + r"(?:record|capture|attach|generate)\w*\s+"
        + product_evidence_object
        + r")"
        r"(?:in|into|to|as)\s+(?:(?:its|the|an?)\s+)?"
        r"(?:database|audit log|storage|application log)"
        + shared_storage_separator_base
        + r"(?P<preposition>"
        + destination_preposition
        + r")?(?P<destination>"
        + review_destination_noun
        + r")",
        re.I,
    )
    storage_destination = (
        r"(?:in|into|to|as)\s+(?:(?:its|the|an?)\s+)?"
        r"(?:database|audit log|storage|application log)\b"
    )
    coordinated_governor = (
        r"(?:"
        + delivery_governor_auxiliary
        + r"\s+)?"
        + delivery_adverbs
        + r"(?:(?:not|never|no\s+longer)\s+)?"
        + delivery_adverbs
        + r"(?:have\s+)?(?:be\s+|been\s+)?(?:being\s+)?"
        + delivery_adverbs
    )
    coordinated_operation = (
        r"(?:record|capture|attach|generate|return|display|emit|render|expose|provide)\w*\s+"
        + product_evidence_object
    )
    shared_review_tail = r"(?:" + shared_storage_separator + review_destination_noun + r"){0,3}"
    shared_passive_product_review_destination = re.compile(
        r"(?P<predicate>\b"
        + product_evidence_object
        + coordinated_governor
        + r"(?:recorded|captured|attached|generated|returned|displayed|emitted|rendered|exposed|provided)\s+)"
        + product_destination
        + r"\s+by\s+"
        + product_actor
        + shared_storage_separator_base
        + r"(?P<preposition>"
        + destination_preposition
        + r")?"
        + r"(?P<destination>"
        + review_destination_noun
        + r")",
        re.I,
    )
    storage_chain_head = re.compile(
        r"\b(?P<actor>"
        + product_actor
        + r")\s+"
        + r"(?P<governor>"
        + coordinated_governor
        + r")"
        + coordinated_operation
        + storage_destination
        + shared_review_tail,
        re.I,
    )
    storage_chain_member = re.compile(
        r"\s+(?P<conjunction>and|or)\s+(?P<predicate>"
        + coordinated_operation
        + r"(?:"
        + storage_destination
        + shared_review_tail
        + r"|(?:in|into|to|as)\s+"
        + review_destination_noun
        + r"))",
        re.I,
    )

    def normalize_storage_coordination(text: str) -> str:
        """Restore a bounded elided product actor/governor before clause splitting."""
        literals = [match.span() for match in re.finditer(quoted_evidence_literal, text)]
        output: list[str] = []
        consumed = 0
        for head in storage_chain_head.finditer(text):
            if head.start() < consumed or any(
                start <= head.start() < end for start, end in literals
            ):
                continue
            cursor = head.end()
            members = []
            while member := storage_chain_member.match(text, cursor):
                if any(start < member.end() and member.start() < end for start, end in literals):
                    break
                # Alternative review delivery is outside this finite inheritance
                # repair; preserve it unchanged instead of changing its semantics.
                if member["conjunction"].lower() == "or" and not re.match(
                    coordinated_operation + storage_destination, member["predicate"], re.I
                ):
                    break
                members.append(member)
                cursor = member.end()
            output.extend((text[consumed : head.end()],))
            for member in members:
                output.append("; " + head["actor"] + " " + head["governor"] + member["predicate"])
            consumed = cursor
            reset = re.match(
                r"\s+(?:and|or)\s+(?=(?:" + mandatory_auxiliary + r"|will)\s+)",
                text[cursor:],
                re.I,
            )
            if reset:
                # A new explicit governor starts a separate obligation. Do not
                # inherit the preceding product modality or negation into it.
                output.append("; ")
                consumed += reset.end()
        return "".join(output) + text[consumed:] if output else text

    # Positive and negated obligations must recognize the same passive aspects.
    evidence_term = re.compile(
        r"\b(?:evidence|artifacts?|transcripts?|command outputs?|workflow runs?|"
        r"pr comments?|pull request comments?)\b",
        re.I,
    )
    requirement = re.compile(
        r"\b(?:"
        + mandatory_auxiliary
        + r"|required|mandatory|(?:is|are)\s+needed|must|shall|needs? to|"
        r"publish(?:es|ed)?|upload(?:s|ed)?|"
        r"attach(?:es|ed)?|captur(?:e|es|ed)|record(?:s|ed|ing)?|provid(?:e|es|ed)|"
        r"includ(?:e|es|ed)|link(?:s|ed)?|post(?:s|ed)?|"
        r"(?:add(?:s|ed)?|leav(?:e|es)|left)\s+(?:(?:an?|the)\s+)?"
        r"(?:pr|pull request)\s+comments?|"
        r"document(?:s|ed)?|prov(?:e|es|ed)|show(?:s|ed)?)\b",
        re.I,
    )

    def body_occurrences(
        text: str, gate: bool, *, pronoun_delivery: bool = False
    ) -> tuple[list[dict[str, Any]], str]:
        """Classify complete, bounded body predicates before residual evidence gating."""
        body = r"(?:pr|pull request)\s+body\b"
        qualified_object = (
            evidence_modifiers + r"(?:evidence|artifacts?|transcripts?|command outputs?)\b"
        )
        noun = r"(?:(?:the|an?|any|no)\s+)?" + qualified_object
        noun = r"(?:" + noun + r")(?:\s+(?:and|or)\s+(?:" + noun + r")){0,3}"
        noun = r"(?P<body_object>" + noun + r")"
        exclusion_operation = (
            r"(?:exclude\w*|omit\w*|remove\w*|avoid\w*|suppress\w*|leave\s+out|left\s+out)\b"
        )
        operation = (
            r"(?:"
            + exclusion_operation
            + "|"
            + response_operation
            + (r"|upload\w*" if pronoun_delivery else "")
            + r"|include\w*|contain\w*|attach\w*|provide\w*|publish\w*|post\w*|record\w*|capture\w*|document\w*|add\w*|show\w*|store\w*|have|left|leave\w*)\b"
        )
        auxiliary = (
            r"(?:(?:is|are|was|were)\s+(?:not|never|no\s+longer)\s+"
            r"(?:required|needed|mandated|expected|supposed|obliged)\s+to|"
            r"(?:does|do|did)\s+(?:not|never)\s+(?:need|have)\s+to|"
            + mandatory_auxiliary
            + r"|is|are|was|were|has|have|had|will|"
            + optional_delivery_modal
            + r")"
        )
        polarity = r"(?:(?:not|never|no\s+longer)\s+)?"
        aspect = (
            delivery_adverbs
            + r"(?:"
            + passive_delivery_prefix
            + r"|been\s+"
            + delivery_adverbs
            + r")?"
            + delivery_adverbs
        )
        body_destination = r"(?:(?:the|an?)\s+)?" + body + r"(?:\s+editor\b)?"
        destination_item = delivery_destination_item
        destination_separator = delivery_destination_separator
        destination = (
            destination_preposition + r"(?:both\s+)?"
            r"(?=(?:"
            + destination_item
            + destination_separator
            + r")*"
            + body_destination
            + r")"
            + destination_item
            + r"(?:"
            + destination_separator
            + destination_item
            + r")*"
        )
        families = [
            r"\b"
            + noun
            + r"\s+"
            + destination
            + r"\s+(?:(?:is|are)|"
            + mandatory_auxiliary
            + r")\s+"
            + polarity
            + r"(?:be\s+)?"
            + r"(?:required|needed|mandatory|optional)\b",
            r"\b" + mandatory_auxiliary + r"\s+" + polarity + operation + r"\s+" + destination,
            r"\b" + body + r"\s+" + auxiliary + r"\s+" + polarity + operation + r"\s+" + noun,
            r"\bthere\s+" + auxiliary + r"\s+" + polarity + r"be\s+" + noun + r"\s+" + destination,
            r"\b"
            + noun
            + r"\s+(?:is|are)\s+"
            + polarity
            + r"(?:required|needed|mandatory|optional)\s+"
            + destination,
            r"\b"
            + noun
            + r"\s+"
            + auxiliary
            + r"\s+"
            + polarity
            + aspect
            + operation
            + r"\s+"
            + destination,
            r"\b(?:"
            + auxiliary
            + r"\s+)?"
            + polarity
            + aspect
            + operation
            + r"\s+"
            + noun
            + r"\s+"
            + destination,
            r"\b"
            + body
            + r"\s+(?:is|are)\s+"
            + polarity
            + r"(?:required|needed|mandatory|optional)\b",
        ]
        if gate:
            families.insert(0, r"\b(?:without|unless|until)\s+" + noun + r"\s+" + destination)
        candidates = sorted(
            (match for family in families for match in re.finditer(family, text, re.I)),
            key=lambda match: (match.start(), -len(match[0])),
        )
        records: list[dict[str, Any]] = []
        consumed_end = -1
        residual = list(text)
        for match in candidates:
            if match.start() < consumed_end:
                continue
            clause = match[0]
            # Object qualifiers are not governing polarity/modality predicates.
            # For example, excluded-case or optional-case evidence is still a
            # mandatory deliverable. Keep the predicate and post-object state.
            polarity_clause = clause
            object_prohibited = False
            if match.groupdict().get("body_object") is not None:
                start, end = match.span("body_object")
                polarity_clause = clause[: start - match.start()] + clause[end - match.start() :]
                object_prohibited = bool(
                    re.search(
                        r"\bno\s+"
                        + evidence_modifiers
                        + r"(?:evidence|artifacts?|transcripts?|command outputs?)\b",
                        match["body_object"],
                        re.I,
                    )
                )
            body_match = re.search(body, clause, re.I)
            assert body_match is not None
            is_gate = gate and bool(re.match(r"(?:without|unless|until)\b", clause, re.I))
            prohibited = not is_gate and (
                object_prohibited
                or bool(
                    re.search(
                        r"\b(?:not|never|no\s+longer)\b",
                        polarity_clause,
                        re.I,
                    )
                )
            )
            if not is_gate and re.search(exclusion_operation, polarity_clause, re.I):
                prohibited = not prohibited
            mandatory_optionality = bool(
                re.search(
                    r"\b(?:(?:is|are)|"
                    + mandatory_auxiliary
                    + r")\s+(?:not|never|no\s+longer)\s+(?:be\s+)?optional\b",
                    polarity_clause,
                    re.I,
                )
            )
            if mandatory_optionality:
                prohibited = False
            optional = (
                not is_gate
                and bool(
                    re.search(
                        r"\b(?:optional|" + optional_delivery_modal + r")\b", polarity_clause, re.I
                    )
                    or re.match(r"\s*" + conditional_evidence, text[match.end() :], re.I)
                )
                and not mandatory_optionality
            )
            editor = re.match(r"\s+editor\b", clause[body_match.end() :], re.I)
            product = bool(editor) and product_comment_object(
                text[: match.start() + body_match.start()], clause[body_match.end() :]
            )
            disposition = (
                "prohibited"
                if prohibited
                else "product" if product else "optional" if optional else "required"
            )
            destinations = {"body"}
            if re.search(r"\b(?:pr comments?|pull request comments?)\b", clause, re.I):
                destinations.add("comments")
            if re.search(artifact_destination_object, clause, re.I):
                destinations.add("artifacts")
            if disposition == "product":
                # The editor is a product surface, but coordinated actual
                # review destinations retain their own delivery obligation.
                destinations.discard("body")
                if destinations:
                    disposition = "required"
            records.append(
                {
                    "span": (match.start(), match.end()),
                    "disposition": disposition,
                    "destinations": destinations,
                }
            )
            residual[match.start() : match.end()] = " " * len(clause)
            consumed_end = match.end()
        return records, "".join(residual)

    def remaining_delivery(text: str) -> bool:
        # Product object-field nouns are not requests to deliver evidence.
        actions = re.sub(
            r"\bevidence\s+(?:links?|records?)\b"
            r"(?:\s+(?:and|or)\s+(?:links?|records?)\b"
            r"(?=\s*(?:$|[;,.!?]|(?:and|or)\b|(?:to|of|for)\s+evidence\b)))*",
            "evidence",
            text,
            flags=re.I,
        )
        # Adjectives on product subjects/fields are not independent delivery
        # predicates. Preserve a post-object passive requirement instead.
        passive_requirement = re.search(
            r"\b(?:evidence|artifacts?|transcripts?|command outputs?|workflow runs?|"
            r"pr comments?|pull request comments?)\b(?:\s+(?:links?|records?))?\s+"
            r"(?:(?:is|are)\s+)?(?:required|mandatory|needed)\b",
            text,
            re.I,
        )
        actions = re.sub(r"\b(?:required|mandatory)\b", " ", actions, flags=re.I)
        return bool(
            evidence_term.search(text) and (requirement.search(actions) or passive_requirement)
        )

    def normalize_product_capability(text: str) -> str:
        """Canonicalize product recognition only, not the original obligation text."""
        text = re.sub(
            r"\b(?:won['’]t|can['’]t|couldn['’]t|wouldn['’]t|shouldn['’]t|"
            r"mustn['’]t|shan['’]t|doesn['’]t|don['’]t|didn['’]t)\s+"
            r"(?=" + capability_operation + r"\b)",
            "",
            text,
            flags=re.I,
        )
        text = re.sub(
            r"\b(?:(?P<modal>must|shall|will|should|can|may)\s+(?:not|never)|"
            r"(?:does|do|did)\s+(?:not|never)|cannot)\s+(?=" + capability_operation + r"\b)",
            lambda match: (match["modal"] or "") + " ",
            text,
            flags=re.I,
        )
        return re.sub(
            r"\b(?:(?:is|are|was|were)|(?:has|have|had)\s+(?:(?:not|never)\s+)?been|"
            r"support(?:s|ed|ing)?)\s+"
            r"(?:(?:not|never|now|currently|already|still|[\w-]+ly)\s+){0,3}letting\b",
            "let",
            text,
            flags=re.I,
        )

    def product_comment_object(prefix: str, destination: str) -> bool:
        """Classify the governing operation's subject, not domain words anywhere."""
        prefix = normalize_product_capability(prefix)
        operations = list(
            re.finditer(
                r"\b(?!renderer\b)(?:"
                + response_operation
                + r"|"
                + capability_operation
                + r"|display|show|store|include|contain|attach|upload|add|leave|left|post|publish|provide|document|record|capture|link)\w*\b",
                prefix,
                re.I,
            )
        )
        if not operations:
            return False
        capability = bool(re.fullmatch(capability_operation, operations[0][0], re.I))
        if capability:
            actor = (
                recipient_prefix + r"(?:(?:api|ui)\s+)?"
                r"(?:users?|clients?|consumers?|reviewers?|maintainers?|authors?|operators?)"
            )
            base_operations = {
                "display",
                "show",
                "store",
                "include",
                "contain",
                "attach",
                "upload",
                "add",
                "leave",
                "post",
                "publish",
                "provide",
                "document",
                "record",
                "capture",
                "return",
                "emit",
                "render",
                "expose",
                "have",
            }
            for index, current in enumerate(operations[1:], start=1):
                current_capability = bool(re.fullmatch(capability_operation, current[0], re.I))
                if current[0].lower() not in base_operations and not current_capability:
                    return False
                previous = operations[index - 1]
                between = prefix[previous.end() : current.start()]
                if re.fullmatch(capability_operation, previous[0], re.I):
                    if current_capability:
                        return False
                    complement = (
                        r"\s+"
                        if re.fullmatch(r"let(?:s|ting)?", previous[0], re.I)
                        else r"\s+to\s*"
                    )
                    recognized = re.fullmatch(r"\s*" + actor + complement, between, re.I)
                else:
                    # Consume only an entire recognized preceding object.
                    # An unknown intervening clause may never be skipped or
                    # have capability inheritance restored by a later link.
                    between = re.sub(
                        r"^\s*"
                        + evidence_modifiers
                        + r"(?:evidence|artifacts?|transcripts?|command outputs?|pr comments?|pull request comments?)\b",
                        "",
                        between,
                        count=1,
                        flags=re.I,
                    )
                    recognized = re.fullmatch(
                        r"\s*,?\s*(?:and|or)\s+"
                        + delivery_adverbs
                        + ("" if current_capability else r"(?:(?:" + actor + r"\s+)?to\s*)?")
                        + r"\s*",
                        between,
                        re.I,
                    )
                if not recognized:
                    # Decline before subject heuristics can rescue an
                    # unrecognized affirmative delivery as product behavior.
                    return False
        operation = operations[0] if capability else operations[-1]
        subject = prefix[: operation.start()]
        if capability:
            subject = re.sub(r"\b(?:does|do|did)\s+not\s*$", "", subject, flags=re.I)
        if not capability and len(operations) > 1:
            between = prefix[operations[-2].end() : operation.start()]
            prior_comments = list(
                re.finditer(r"\b(?:pr|pull request)\s+comments?\b", between, re.I)
            )
            if prior_comments:
                between = between[prior_comments[-1].end() :]
            if not re.fullmatch(r"\s*(?:and|or)\s*", between, re.I):
                # A later delivery has its own subject; do not inherit an
                # earlier UI/API actor across "transcript that must be posted".
                subject = re.split(
                    r"\b(?:and|or|that|which|who|while|after|once|before|when|until|unless|if|since|because|whereas)\b",
                    between,
                    flags=re.I,
                )[-1]
        nested_subject = re.search(
            r"\b(?:(?P<explicit>that|whether)|(?P<implicit>"
            + product_auxiliary
            + r"(?:verify|check|assert))(?!\s+(?:that|whether)\b))"
            r"\s+(?P<subject>(?:(?:the|an?)\s+)?"
            r"(?:[\w-]+\s+)*?(?:ui|api|application|interface|service|cli|endpoint|renderer|"
            r"reviewers?|maintainers?|authors?|operators?))\s+(?P<nested_aux>"
            + product_auxiliary
            + r")?\s*$",
            subject,
            re.I,
        )
        if (
            nested_subject
            and nested_subject["implicit"]
            and (
                nested_subject["nested_aux"]
                or re.search(r"\b(?:who|which|that)\b", subject[: nested_subject.start()], re.I)
            )
        ):
            # A check predicate inside a relative qualifier cannot supply
            # the outer delivery's actor. Decline ambiguous attachment.
            nested_subject = None
        if nested_subject:
            # A direct nested clause's actor governs this operation, not a
            # reviewer merely asked to verify that product behavior. An outer
            # relative clause with another verb cannot match this boundary.
            subject = nested_subject["subject"]
        subject = re.split(product_auxiliary, subject, maxsplit=1, flags=re.I)[0]
        plain_subject = re.sub(r"^\s*(?:[-*]\s*(?:\[[ xX]\]\s*)?)?", "", subject)
        if re.match(
            r"(?:for|when|while|during|after|before|if|once|under|with|without|upon)\b",
            plain_subject,
            re.I,
        ):
            fronted = re.match(
                r"(?P<adjunct>.*?)\s+(?P<subject>(?:the|an?)\s+.+)$", plain_subject, re.I
            )
            supported_adjunct = (
                r"for reviewers? access|for backward compatibility|under reviewers? supervision|"
                r"when reviewers? requests? access|"
                r"(?:when|while) (?:using|testing|accessing|operating) [\w-]+"
            )
            if not fronted or not re.fullmatch(supported_adjunct, fronted["adjunct"], re.I):
                # A partial grammar must decline unknown attachments. In
                # particular, never consume "maintainers of" or an unknown
                # human role to reach a product noun in its modifier.
                return False
            subject = fronted["subject"]
        actor_head = re.search(
            r"\b(?:(?:api|ui)\s+)?(?:reviewers?|maintainers?|authors?|operators?)\b"
            r"|\b(?:ui|api|application|interface|service|cli|endpoint|renderer)\b",
            subject,
            re.I,
        )
        if actor_head and re.search(
            r"\b(?:reviewers?|maintainers?|authors?|operators?)\b", actor_head[0], re.I
        ):
            # Preserve the initial human head regardless of later modifiers;
            # a product noun inside that modifier cannot change the actor.
            return False
        # A participial modifier can qualify an already named actor, but an
        # introductory "When using OAuth" precedes the actual actor. Never
        # discard a later subject merely because the introduction uses a verb.
        for qualifier in re.finditer(r"\b(?:using|testing|accessing|operating)\b", subject, re.I):
            if re.search(
                r"\b(?:reviewers?|maintainers?|authors?|operators?|ui|api|application|"
                r"interface|service|cli|endpoint|renderer)\b",
                subject[: qualifier.start()],
                re.I,
            ):
                subject = subject[: qualifier.start()]
                break
        # Relative/prepositional modifiers do not change the subject head:
        # "reviewer of the endpoint" is human; "endpoint used by reviewers"
        # is a product. Introductory words need no arbitrary length ceiling.
        subject = re.split(
            r"\b(?:of|that|which|who|" r"(?:used|operated|provided|managed)\s+by)\b",
            subject,
            maxsplit=1,
            flags=re.I,
        )[0]
        words = re.findall(r"[\w-]+", subject.lower())
        product_destination = bool(
            re.search(
                r"^\s*(?:in|into|to|as)\s+(?:(?:its|the|an?)\s+)?"
                r"(?:(?:json|api|audit|output)\s+)*"
                r"(?:responses?|payloads?|outputs?|fields?|records?|storage|data)\b"
                r"|^\s*(?:fields?|metadata)\b",
                destination,
                re.I,
            )
        )
        field_operation = bool(
            re.fullmatch(
                r"(?:include|contain|display|show|store|return|emit|render|expose)\w*",
                operation[0],
                re.I,
            )
        )
        review_destination = bool(
            re.search(
                r"\b(?:with|containing|including)\s+(?:[\w-]+\s+)*?"
                r"(?:results?|evidence|transcripts?|command outputs?)\b"
                r"|\b(?:on|in|to)\s+(?:(?:the|this|reviewing)\s+)?(?:pr|pull request)\b",
                destination,
                re.I,
            )
        )
        return bool(
            words
            and words[-1]
            in {
                "ui",
                "api",
                "application",
                "interface",
                "service",
                "cli",
                "endpoint",
                "renderer",
            }
            and (capability or product_destination or (field_operation and not review_destination))
        )

    perfect_delivery_prohibition = re.compile(
        r"\b(?:has|have|had|will)\s+"
        + delivery_adverbs
        + r"(?:not|never|no\s+longer)\s+"
        + delivery_adverbs
        + r"(?:have\s+"
        + delivery_adverbs
        + r")?"
        + r"(?:been\s+(?:being\s+)?"
        + delivery_adverbs
        + r")?"
        + delivery_operation,
        re.I,
    )
    progressive_delivery_prohibition = (
        r"\b(?:is|are|was|were|will|must|shall)\s+"
        + delivery_adverbs
        + r"(?:not|never|no\s+longer)\s+"
        + delivery_adverbs
        + r"(?:be\s+|been\s+)?(?:being\s+)?"
        + delivery_adverbs
        + r"(?=\w*ing\b)"
        + delivery_operation
    )
    aspect_delivery_prohibition = re.compile(
        perfect_delivery_prohibition.pattern
        + "|"
        + progressive_delivery_prohibition
        + r"|\b(?:is|are|was|were)\s+"
        + delivery_adverbs
        + r"(?:not|never|no\s+longer)\s+"
        + delivery_adverbs
        + r"(?:being\s+)?"
        + delivery_adverbs
        + r"(?=\w*(?:ed|en)\b)"
        + delivery_operation,
        re.I,
    )
    evidence_prohibition = re.compile(
        aspect_delivery_prohibition.pattern + r"|"
        r"\b(?:"
        + mandatory_auxiliary
        + r")\s+"
        + delivery_adverbs
        + r"(?:not|never)\s+"
        + delivery_adverbs
        + r"(?:"
        + passive_delivery_prefix
        + r")?"
        + delivery_adverbs
        + delivery_operation
        + r"(?:\s+"
        + evidence_modifiers
        + r"(?:evidence|artifacts?|transcripts?|command outputs?|workflow runs?|pr comments?|pull request comments?))?"
        + r"|"
        r"\b(?:must|shall|may|should|can|do|does|did|will)\s+"
        + r"(?=(?:(?:not|never|be|have|been|being)\s+){0,5}"
        + r"(?:also|now|still|already|[\w-]+ly)\s+)"
        + delivery_adverbs
        + r"(?:not|never)\s+"
        + delivery_adverbs
        + r"(?:"
        + passive_delivery_prefix
        + r")?"
        + delivery_adverbs
        + delivery_operation
        + r"(?:\s+"
        + evidence_modifiers
        + r"(?:evidence|artifacts?|transcripts?|command outputs?|workflow runs?|pr comments?|pull request comments?))?"
        + r"|"
        r"\b(?:evidence|artifacts?|transcripts?|command outputs?)\s+"
        r"(?:has|have|had|can|could|would|will|should|may|must|shall)\s+(?:not|never)\s+"
        r"(?:been|be)\s+(?:(?:being|\w+ly)\s+)*" + delivery_operation + r"|"
        r"\b(?:"
        + mandatory_auxiliary
        + r"|may|should|can|do|does|did)\s+(?:not|never)\s+(?:be\s+)?"
        + response_operation
        + r"(?:\s+(?:[\w/-]+\s+){0,4}(?:evidence|artifacts?|transcripts?|command outputs?|pr comments?|pull request comments?)\b)?|"
        r"\b(?:evidence|artifacts?|transcripts?|command outputs?)\s+"
        r"(?:does|do|did)\s+(?:not|never)\s+(?:need|have)\s+to\s+"
        + passive_delivery_prefix
        + response_operation
        + r"|"
        r"\bnever\s+(?:upload|attach|provide|publish|post|record|capture|include|document|generate|link|add|leave)\w*\b|"
        r"\b(?:evidence|artifacts?|transcripts?|command outputs?|workflow runs?|"
        r"pr comments?|pull request comments?)\s+(?:is|are|was|were)\s+"
        r"(?:not|never|no\s+longer)\s+(?:being\s+)?"
        r"(?:uploaded|attached|provided|published|posted|recorded|captured|included|documented|generated|linked)\b|"
        r"\b(?:(?:is|are|was|were)\s+(?:not|never|no\s+longer)\s+"
        r"(?:required|needed|mandated|expected|supposed|obliged|allowed|permitted)\s+to|"
        r"(?:does|do|did)\s+not\s+(?:need|have)\s+to|needs?\s+not)\s+"
        + r"(?:"
        + passive_delivery_prefix
        + r")?"
        + delivery_operation
        + r"|"
        r"\bno\s+(?:\w+\s+){0,3}(?:evidence|artifacts?|transcripts?|command outputs?|"
        r"workflow runs?|pr comments?|pull request comments?)"
        r"\s+(?:is|are)\s+(?:required|needed|mandatory)\b"
        r"|\b(?:evidence|artifacts?|transcripts?|command outputs?|workflow runs?|"
        r"pr comments?|pull request comments?)"
        r"\s+(?:is|are)\s+not\s+(?:required|needed|mandatory)\b"
        r"|\b(?:must|shall|may|should|can|do|does|did)\s+not\s+"
        r"(?:upload|attach|provide|publish|post|record|capture|include|document|generate|link|add|leave)\b"
        r"(?:\s+(?:the\s+|an?\s+|any\s+)?(?:[\w-]+\s+){0,4}"
        r"(?:evidence|artifacts?|transcripts?|"
        r"command outputs?|workflow runs?|pr comments?|pull request comments?))?"
        r"|\b(?:evidence|artifacts?|transcripts?|command outputs?|workflow runs?|"
        r"pr comments?|pull request comments?)\s+"
        r"(?:must|shall|may|should)\s+not\s+be\s+"
        r"(?:uploaded|attached|provided|published|posted|recorded|captured|"
        r"included|documented|generated|linked)\b"
        r"|\bneither\s+"
        + evidence_modifiers
        + r"(?:evidence|artifacts?|transcripts?|command outputs?|"
        r"workflow runs?|pr comments?|pull request comments?)\s+nor\s+"
        + evidence_modifiers
        + r"(?:evidence|artifacts?|transcripts?|command outputs?|"
        r"workflow runs?|pr comments?|pull request comments?)\s+"
        r"(?:is|are)\s+(?:required|needed|mandatory)\b"
        r"|\bno\s+(?:\w+\s+){0,4}(?:evidence|artifacts?|transcripts?|command outputs?|"
        r"workflow runs?|pr comments?|pull request comments?)\s+"
        r"(?:(?:must|shall|may|should)\s+(?:not\s+)?be|was|were|is|are)\s+"
        r"(?:left|added)\b"
        r"|\bno\s+(?:\w+\s+){0,4}(?:evidence|artifacts?|transcripts?|command outputs?|"
        r"workflow runs?|pr comments?|pull request comments?)\s+"
        r"(?:must|shall|may|should)\s+(?:not\s+)?(?:be\s+)?"
        r"(?:uploaded|attached|provided|published|posted|recorded|captured|"
        r"included|documented)\b"
        r"|\b(?:evidence|artifacts?|transcripts?|command outputs?|workflow runs?|"
        r"pr comments?|pull request comments?)\s+need\s+not\s+(?:be\s+)?"
        r"(?:uploaded|attached|provided|published|posted|recorded|captured|"
        r"included|documented)\b"
        r"|\bno\s+(?:\w+\s+){0,4}(?:evidence|artifacts?|transcripts?|command outputs?|"
        r"workflow runs?|pr comments?|pull request comments?)\s+is\s+generated\b"
        r"|\b(?:evidence|artifacts?|transcripts?|command outputs?|workflow runs?|"
        r"pr comments?|pull request comments?)\s+(?:does|do)\s+not\s+need\s+(?:to\s+be\s+)?"
        r"(?:uploaded|attached|provided|published|posted|recorded|captured|"
        r"included|documented|generated)\b"
        r"|\bno\s+(?:\w+\s+){0,4}(?:evidence|artifacts?|transcripts?|command outputs?|"
        r"workflow runs?|pr comments?|pull request comments?)\s+needs?\s+to\s+be\s+"
        r"(?:uploaded|attached|provided|published|posted|recorded|captured|"
        r"included|documented|generated)\b",
        re.I,
    )
    negative_gate = re.compile(
        r"(?:\b(?:must\s+not|shall\s+not|may\s+not|can\s+not|cannot|can't|"
        r"do\s+not|does\s+not|no|never)\s+"
        r"(?:\w+\s+){0,3}(?:proceed\w*|merge\w*|ship\w*|release\w*|complete\w*|pass\w*)\b"
        r"|\bnever\s+(?:\w+\s+){0,5}proceed\w*\b)"
        r".{0,160}\b(?:without|unless|until)\b.{0,160}"
        r"\b(?:attach\w*|upload\w*|evidence|artifacts?|transcripts?|"
        r"command outputs?|workflow runs?|pr comments?|pull request comments?)\b",
        re.I,
    )
    criteria: list[str] = []
    for raw_line in acceptance.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if criteria and not re.match(r"^(?:[-*+]|\d+[.)])\s+", line):
            criteria[-1] += " " + line
        else:
            criteria.append(line)
    for criterion in criteria:
        # Canonicalize supported list markers once so every downstream negation,
        # product-output and checklist guard uses the same established syntax.
        criterion = re.sub(r"^\s*(?:[-*+]|\d+[.)])(?=\s)", "-", criterion)
        criterion = re.sub(
            r"\b(is|are|does|do|did|must|should|could|would|need|has|have|had|was|were|ca)n['’]t\b",
            lambda match: ("can" if match[1].lower() == "ca" else match[1]) + " not",
            criterion,
            flags=re.I,
        )
        criterion = re.sub(r"\bcannot\b", "can not", criterion, flags=re.I)
        criterion = re.sub(r"\bwon['’]t\b", "will not", criterion, flags=re.I)
        criterion_checklist = bool(re.match(r"^\s*(?:[-*+]|\d+[.)])\s*\[[ xX]\]", criterion))
        criterion_bullet = bool(re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", criterion))
        # Quoted parser inputs are examples, including their verbs and clause
        # delimiters. Remove only the literal following the parser operation;
        # an actual delivery instruction after the example still applies.
        criterion = re.sub(
            r"\b(?:parser|verifier|code|script|implementation)\b.{0,80}?"
            r"\b(?:recogniz|pars|detect|classif|match|identif|support|handl|validat)\w*\b\s*"
            r"(?:(?:the|a|an|phrase|syntax|example|literal|string|text|quoted|following)\b\s*){0,4}"
            r"(?::\s*)?"
            r"(?P<example>" + quoted_evidence_literal + r")",
            lambda match: match.group(0)[: match.start("example") - match.start()] + " ",
            criterion,
            flags=re.I,
        )
        criterion = normalize_storage_coordination(criterion)
        criterion = shared_passive_product_review_destination.sub(
            lambda match: match["predicate"]
            + (match["preposition"] or "in ")
            + match["destination"],
            criterion,
        )
        # Shared destinations retain their predicate after actor inheritance.
        criterion = shared_storage_review_destination.sub(
            lambda match: match["predicate"]
            + (match["preposition"] or "in ")
            + match["destination"],
            criterion,
        )
        # Split independent mandatory clauses after optional evidence, including
        # named actors and modified subjects. Extra noun modifiers need a modal
        # so adjective lists such as "failing and restored passing transcript"
        # stay attached to their delivery verb.
        named_actor_delivery_predicate = (
            r"(?:(?!(?:and|or|but|while|whereas)\b)[\w-]+\s+){1,6}(?="
            + delivery_governor_auxiliary
            + r"\s+)"
            + coordinated_governor
            + delivery_operation
        )
        clause_boundary = (
            r"\s*;\s*|,?\s+(?:but|whereas)\s+|"
            r"(?:,?\s+(?:and|while)\s+)(?="
            + delivery_governor_auxiliary
            + r"\s+)(?="
            + coordinated_governor
            + delivery_operation
            + r")|"
            r"(?:,?\s+(?:and|while)\s+)(?="
            + review_destination_noun
            + r"\s+"
            + independent_review_predicate
            + r")|"
            r"(?:,?\s+(?:and|while)\s+|[,\.]\s+)(?="
            r"(?:optionally\s+)?(?:"
            r"(?:an?\s+|the\s+)?(?:validation\s+|exact-head\s+)?"
            r"(?:evidence|artifacts?|transcripts?|command outputs?|"
            r"workflow runs?|pr comments?|pull request comments?)|"
            r"(?:an?\s+|the\s+)?(?:[\w-]+\s+){1,4}?"
            r"(?:evidence|artifacts?|transcripts?|command outputs?|"
            r"workflow runs?|pr comments?|pull request comments?)\s+"
            r"(?:must|shall|needs?\s+to|(?:is|are)\s+(?:required|mandatory|needed))\b|"
            + named_actor_delivery_predicate
            + r"|"
            r"(?:publish|upload|attach|capture|record|provide|include|post|document|prove|show|link|add|leave)\b"
            r"))"
        )
        clause_evidence_antecedent: str | None = None
        pronoun_pr_delivery = re.compile(
            r"\b(?:attach|upload|publish|post|record|capture|provide|include|document|link)\w*\b"
            r".{0,40}\b(?:it|them|this|they|these|those|both)\b.{0,40}\b(?:pr|pull request)\b"
            r"|\b(?:it|them|this|they|these|those|both)\b.{0,40}"
            r"\b(?:attached|uploaded|published|posted|recorded|captured|provided|"
            r"included|documented|linked)\b.{0,40}\b(?:pr|pull request)\b",
            re.I,
        )
        fragments = []
        # Shared-predicate destination lists are not independent clauses.
        # Preserve their original text and delimiters using recognized spans,
        # rather than making later noun-only fragments infer a missing verb.
        criterion_body_records, _ = body_occurrences(
            criterion, bool(negative_gate.search(criterion))
        )
        split_parts = []
        split_start = 0
        review_destination_spans = [
            match.span() for match in re.finditer(bound_review_destinations, criterion, re.I)
        ]
        for boundary_match in re.finditer(clause_boundary, criterion, re.I):
            if re.fullmatch(r",\s+", boundary_match[0]) and re.match(
                r"(?:that|which)\b", criterion[boundary_match.end() :], re.I
            ):
                # A punctuated relative predicate still belongs to its noun.
                continue
            independent_predicate = re.match(
                r"(?:"
                + review_destination_noun
                + r"\s+"
                + independent_review_predicate
                + r"|"
                + named_actor_delivery_predicate
                + r"|"
                + delivery_governor_auxiliary
                + r"\s+)",
                criterion[boundary_match.end() :],
                re.I,
            )
            if not independent_predicate and (
                any(
                    record["span"][0] <= boundary_match.start()
                    and boundary_match.end() <= record["span"][1]
                    for record in criterion_body_records
                )
                or any(
                    start <= boundary_match.start() and boundary_match.end() <= end
                    for start, end in review_destination_spans
                )
            ):
                continue
            split_parts.extend((criterion[split_start : boundary_match.start()], boundary_match[0]))
            split_start = boundary_match.end()
        split_parts.append(criterion[split_start:])
        for part_index in range(0, len(split_parts), 2):
            fragment = split_parts[part_index]
            boundary = split_parts[part_index - 1] if part_index else ""
            if (
                fragments
                and re.fullmatch(r"\s*,?\s*and\s+", boundary, re.I)
                and not re.match(r"\s*" + delivery_governor_auxiliary + r"\s+", fragment, re.I)
                and re.fullmatch(
                    r"\s*(?:(?!(?:and|or|but|must|shall|is|are|not|never)\b)[\w/-]+\s+){0,4}"
                    r"(?:evidence|artifacts?|transcripts?|command outputs?)\s+"
                    + bound_review_destinations
                    + r"\s*[.!]?\s*",
                    fragment,
                    re.I,
                )
            ):
                predicates = list(
                    re.finditer(
                        r"\b(?P<predicate>(?:"
                        + mandatory_auxiliary
                        + r"\s+)?(?:(?:not|never)\s+)?"
                        + delivery_operation
                        + r")\s+",
                        fragments[-1],
                        re.I,
                    )
                )
                if predicates:
                    fragment = predicates[-1]["predicate"] + " " + fragment.lstrip()
            if (
                fragments
                and re.fullmatch(r"\s*(?:,\s*(?:(?:and|or)\s*)?|(?:and|or)\s*)", boundary, re.I)
                and re.fullmatch(
                    r"\s*(?:(?:the|an?)\s+)?(?:pr comments?|pull request comments?|workflow artifacts?)"
                    r"(?:\s*,\s*(?:(?:and|or)\s+)?(?:(?:the|an?)\s+)?"
                    r"(?:pr comments?|pull request comments?|workflow artifacts?))*\s*",
                    fragment,
                    re.I,
                )
                and body_occurrences(fragments[-1] + boundary + fragment, False)[0]
            ):
                fragments[-1] += boundary + fragment
                continue
            if (
                fragments
                and re.fullmatch(r"\s*,?\s*(?:and|or)\s+", boundary, re.I)
                and re.search(r"\b" + capability_operation + r"\b", fragments[-1], re.I)
            ):
                combined = fragments[-1] + boundary + fragment
                capability_objects = list(
                    re.finditer(
                        r"\b(?:evidence|artifacts?|transcripts?|command outputs?|pr comments?|pull request comments?)\b",
                        combined,
                        re.I,
                    )
                )
                if capability_objects:
                    last_object = capability_objects[-1]
                    if last_object.start() >= len(
                        fragments[-1] + boundary
                    ) and product_comment_object(
                        combined[: last_object.start()], combined[last_object.end() :]
                    ):
                        # Only positive whole-chain recognition can preserve
                        # bare shared verbs across a coordination boundary.
                        # Semicolons and unknown/finite clauses stay separate.
                        fragments[-1] = combined
                        continue
            noun_only = re.fullmatch(
                r"\s*(?:(?:an?|the|validation|workflow|exact-head|evidence)\s+)*"
                r"(?:artifacts?|command outputs?|transcripts?|evidence\s+(?:links?|records?))\s*",
                fragment,
                re.I,
            )
            prior_product = fragments and re.search(
                r"\b"
                + response_subject
                + r"\s+"
                + "(?:"
                + product_auxiliary
                + ")?"
                + response_operation
                + r"|\b(?:[\w-]+\s+){1,6}"
                + product_auxiliary
                + r"(?:return|display|emit|render|expose)\w*\b",
                fragments[-1],
                re.I,
            )
            if noun_only and prior_product:
                fragments[-1] += " and " + fragment
            else:
                fragments.append(fragment)
        for line in fragments:
            objects = [
                m.group(0)
                for m in evidence_term.finditer(line)
                if not re.search(r"(?:pr|pull request) comments?", m.group(0), re.I)
            ]
            if objects:
                clause_evidence_antecedent = " and ".join(objects)
            resolved_antecedent = None
            working_line = line
            if (
                clause_evidence_antecedent
                and not evidence_term.search(line)
                and pronoun_pr_delivery.search(line)
            ):
                working_line = re.sub(
                    r"\b(?:it|them|this|they|these|those|both)\b",
                    clause_evidence_antecedent,
                    line,
                    count=1,
                    flags=re.I,
                )
                resolved_antecedent = clause_evidence_antecedent
            # Excluded destinations are not delivery targets. Keep the
            # generic evidence object and other independent deliveries.
            working_line = re.sub(
                r"\b(?:outside|rather\s+than|instead\s+of)\s+"
                r"(?:(?:the|an?)\s+)?(?:pr|pull request)\s+comments?\b",
                "excluded destination",
                working_line,
                flags=re.I,
            )
            gate = bool(negative_gate.search(working_line))
            requirement_text = working_line if gate else evidence_prohibition.sub(" ", working_line)
            body_records, body_residual = body_occurrences(
                working_line if gate else aspect_delivery_prohibition.sub(" ", working_line),
                gate,
                pronoun_delivery=bool(resolved_antecedent),
            )
            # An optional evidence noun can be the object of a mandatory
            # explanation (for example, "a PR comment must explain why
            # artifacts are optional"). Remove only that optional subject;
            # do not discard a separate required channel in the same clause.
            requirement_text = re.sub(
                r"\b(?:evidence|artifacts?|transcripts?|command outputs?|workflow runs?|"
                r"pr comments?|pull request comments?)(?:\s+(?:upload|attachment|publication|"
                r"posting|capture|recording|generation))?\s+(?:is|are)\s+optional\b",
                " ",
                requirement_text,
                flags=re.I,
            )
            if not evidence_term.search(requirement_text) and not body_records:
                continue
            checklist = criterion_checklist
            bullet = criterion_bullet
            optional_evidence = bool(
                re.search(
                    r"\boptional(?:ly)?\b(?![-/])|"
                    r"\b"
                    + optional_delivery_modal
                    + r"\s+"
                    + delivery_adverbs
                    + r"(?:(?:not|never|no\s+longer)\s+)?"
                    + delivery_adverbs
                    + r"(?:"
                    + passive_delivery_prefix
                    + r")?"
                    + delivery_adverbs
                    + delivery_operation
                    + r"|"
                    + conditional_evidence,
                    requirement_text,
                    re.I,
                )
            )
            explanatory_comment = bool(
                re.search(
                    r"\b(?:pr comments?|pull request comments?)\b.{0,80}"
                    r"\b(?:explain|document)\w*\b.{0,80}\boptional\b",
                    requirement_text,
                    re.I,
                )
            )
            # Optional/conditional evidence clauses never create a hard floor,
            # whether or not the source used checklist syntax. Clause splitting
            # preserves a separate required comment/transcript on the same item.
            if (
                optional_evidence
                and not explanatory_comment
                and not any(record["disposition"] == "required" for record in body_records)
            ):
                continue
            meta_behavior = bool(
                re.search(
                    r"\b(?:parser|verifier|code|script|implementation)\b.{0,80}"
                    r"\b(?:recogniz|pars|detect|classif|match|identif|support|handl|validat)\w*\b"
                    r".{0,80}\b(?:evidence|artifacts?|transcripts?|command outputs?|"
                    r"workflow runs?|pr comments?|pull request comments?)\b",
                    requirement_text,
                    re.I,
                )
                or re.search(
                    r"\b(?:evidence|artifacts?|transcripts?|command outputs?|workflow runs?|"
                    r"pr comments?|pull request comments?)\b.{0,40}"
                    r"\b(?:parser|verifier|code|script|implementation)\b.{0,80}"
                    r"\b(?:recogniz|pars|detect|classif|match|identif|support|handl|validat)\w*\b",
                    requirement_text,
                    re.I,
                )
                or re.search(
                    r"\b(?:parser|verifier|code|script|implementation)\b.{0,40}"
                    r"\b(?:evidence|artifacts?|transcripts?|command outputs?|workflow runs?|"
                    r"pr comments?|pull request comments?)\b.{0,80}"
                    r"\b(?:recogniz|pars|detect|classif|match|identif|support|handl|validat)\w*\b",
                    requirement_text,
                    re.I,
                )
            )
            # Requirements about understanding evidence syntax are software
            # behavior, not evidence-delivery requirements. Nominal upload
            # nouns (for example, "supports artifact uploads") are not delivery
            # verbs unless the criterion explicitly mandates upload/attach/etc.
            if meta_behavior:
                explicit_delivery = bool(
                    re.search(
                        r"\b(?:must|shall|required|needs? to)\s+(?:\w+\s+){0,4}"
                        r"(?:upload|attach|publish|post|record|capture|provide|include|document)\b",
                        requirement_text,
                        re.I,
                    )
                )
                if not explicit_delivery:
                    continue
            checklist_deliverable = bool(
                checklist
                and evidence_term.search(requirement_text)
                and not re.match(r"^\s*[-*]\s*\[[ xX]\]\s*no\s", requirement_text, re.I)
            )
            if not (
                gate
                or any(record["disposition"] == "required" for record in body_records)
                or checklist_deliverable
                or (checklist and requirement.search(requirement_text))
                or (bullet and requirement.search(requirement_text))
                or requirement.search(requirement_text)
            ):
                continue
            if body_records:
                for record in body_records:
                    if record["disposition"] == "required":
                        channels.update(record["destinations"])
                requirement_text = (
                    body_residual if gate else evidence_prohibition.sub(" ", body_residual)
                )
                if optional_evidence and not explanatory_comment:
                    continue
                if not evidence_term.search(requirement_text):
                    continue
            # Remove only a delivery object governed by a recognized product
            # capability. Qualifiers such as "validation" do not turn that
            # product input into workflow evidence. Classify the residual so
            # a separate reviewer obligation retains its own destination.
            attached_delivery_pattern = re.compile(
                r"(?:\s*,\s*(?:that|which)\s+|\s+(?:(?:that|which)\s+)?)"
                r"(?P<actor>(?:(?!(?:and|or|that|which|must|shall|needs?|has|have|is|are)\b)[\w/-]+\s+){0,6})"
                + r"(?P<auxiliary>"
                + r"(?:"
                + mandatory_auxiliary
                + r"|will)"
                + r")\s+"
                + delivery_adverbs
                + r"(?P<aspect>"
                + passive_delivery_prefix
                + r")?"
                + delivery_adverbs
                + r"(?P<operation>"
                + delivery_operation
                + r")",
                re.I,
            )
            bound_spans = []
            bound_end = -1
            for attached_object in re.finditer(
                (
                    r"\b(?P<object>evidence|artifacts?|transcripts?|command outputs?|pr comments?|pull request comments?)\b"
                    if _bind_attached and not resolved_antecedent
                    else r"(?!)"
                ),
                requirement_text,
                re.I,
            ):
                if attached_object.start() < bound_end:
                    continue
                attached_delivery = attached_delivery_pattern.match(
                    requirement_text[attached_object.end() :]
                )
                if attached_delivery and evidence_term.fullmatch(
                    attached_delivery["actor"].strip()
                ):
                    # A noun qualifier is not a second actor/antecedent.
                    continue
                bound_destination = (
                    re.match(
                        r"\s+(?P<destination>" + bound_review_destinations + r")",
                        requirement_text[attached_object.end() + attached_delivery.end() :],
                        re.I,
                    )
                    if attached_delivery
                    else None
                )
                if attached_delivery and bound_destination:
                    # Bind the antecedent, mandatory predicate and destination
                    # before capability suppression. Reuse the same classifier
                    # on this isolated obligation, without inventing an actor
                    # or maintaining an artifact-only destination grammar.
                    # Actor qualifiers identify who delivers, not what is
                    # delivered. Keep only the bound object/predicate in the
                    # classifier input so "artifact reviewer" cannot replace
                    # a transcript or evidence object with an artifact channel.
                    predicate = " ".join(
                        part.strip()
                        for part in (
                            attached_delivery["auxiliary"],
                            attached_delivery["aspect"] or "",
                            attached_delivery["operation"],
                        )
                        if part.strip()
                    )
                    obligation = (
                        f"{attached_object['object']} {predicate}"
                        if attached_delivery["aspect"]
                        else f"{predicate} {attached_object['object']}"
                    )
                    destination = bound_destination["destination"]
                    destination_channels = set()
                    if re.search(r"\b(?:pr|pull request)\s+body\b", destination, re.I):
                        destination_channels.add("body")
                    if re.search(r"\b(?:pr|pull request)\s+comments?\b", destination, re.I):
                        destination_channels.add("comments")
                    if re.search(artifact_destination_object, destination, re.I):
                        destination_channels.add("artifacts")
                    bare_pr = bool(
                        re.search(
                            r"\b(?:pr|pull request)\b(?!\s+(?:body|comments?)\b)",
                            destination,
                            re.I,
                        )
                    )
                    # A named destination selects its channel; an artifact
                    # antecedent is not a second upload obligation. A generic
                    # PR destination still needs object-specific classification.
                    if bare_pr or not destination_channels:
                        destination_channels.update(
                            _required_evidence_channels(
                                f"{obligation} {destination}", _bind_attached=False
                            )
                        )
                    channels.update(destination_channels)
                    bound_end = (
                        attached_object.end() + attached_delivery.end() + bound_destination.end()
                    )
                    bound_spans.append(
                        (
                            attached_object.start(),
                            bound_end,
                            " ",
                        )
                    )
                    continue
            for start, end, replacement in reversed(bound_spans):
                requirement_text = requirement_text[:start] + replacement + requirement_text[end:]
            product_spans = []
            for product_delivery in re.finditer(
                r"\b(?P<operation>"
                + delivery_operation
                + r")\s+(?P<object>"
                + evidence_modifiers
                + r"(?:evidence|artifacts?|transcripts?|command outputs?|pr comments?|pull request comments?)\b)",
                requirement_text,
                re.I,
            ):
                prefix = requirement_text[: product_delivery.end()]
                if re.search(capability_operation, prefix, re.I) and product_comment_object(
                    requirement_text[: product_delivery.start()] + product_delivery["operation"],
                    requirement_text[product_delivery.end() :],
                ):
                    attached_delivery = attached_delivery_pattern.match(
                        requirement_text[product_delivery.end() :]
                    )
                    product_spans.append(
                        (
                            *product_delivery.span(),
                            product_delivery["object"] if attached_delivery else " ",
                        )
                    )
            for start, end, replacement in reversed(product_spans):
                requirement_text = requirement_text[:start] + replacement + requirement_text[end:]
            if (bound_spans or product_spans) and not remaining_delivery(requirement_text):
                continue
            lower = requirement_text.lower()
            delivery_object = r"(?:command outputs?|transcripts?|artifacts?|evidence)\b"
            # Bind the destination to the immediate positive delivery object,
            # not a later prohibited pronoun clause such as 'do not attach it'.
            explicit_review_destination = bool(
                re.search(
                    r"\b(?:provide|upload|attach|publish|post|record|capture|document)\w*\b\s+"
                    r"(?:(?:the|an?|any)\s+)?" + artifact_destination_object + "|"
                    r"\b" + delivery_operation + r"\s+"
                    r"(?:(?!(?:and|or|but|must|shall|is|are|not|never)\b)[\w/-]+\s+){0,4}"
                    + delivery_object
                    + r"\s+"
                    + bound_review_destinations
                    + "|"
                    + delivery_object
                    + r"\s+(?:"
                    + mandatory_auxiliary
                    + r"\s+"
                    + passive_delivery_prefix
                    + r")?"
                    + delivery_operation
                    + r"\s+"
                    + bound_review_destinations,
                    requirement_text,
                    re.I,
                )
            )
            response_prefix = re.compile(
                r"\b(?:" + response_subject + r"|(?:command[- ]?outputs?|transcripts?)\s+api"
                r"|api\s+(?:command[- ]?outputs?|transcripts?)(?:\s+\w+){0,3}"
                r")\b\s+" + "(?:" + product_auxiliary + ")?" + response_operation,
                re.I,
            )
            response_match = response_prefix.search(requirement_text)
            if response_match and not explicit_review_destination:
                # Only the immediate object of this product operation is a
                # field noun. A later reviewer predicate must remain gating.
                response_object = requirement_text[response_match.end() :]
                # Normalize only bounded object nouns, never a later finite
                # predicate such as "records evidence in a PR comment".
                field_noun = (
                    r"(?:(?:links?|records?)(?:\s+(?:and|or)\s+(?:links?|records?))*"
                    r"\s+(?:to|of|for)\s+(?:(?:the|an?)\s+)?"
                    r"(?:(?:supporting|execution|validation|test|review|collected|recorded)\s+){0,3}evidence\b"
                    r"|(?:links?|records?)\s+as\s+fields?\b"
                    r"|evidence\s+(?:links?|records?)\b"
                    r"|(?:links?|records?)\b(?=\s*(?:$|[;,.!?]|(?:and|or)\b)))"
                )
                response_object = re.sub(
                    r"^\s+(?:(?:the|a|an)\s+)?"
                    + field_noun
                    + r"(?:\s*(?:,\s*(?:(?:and|or)\s+)?|(?:and|or)\s+)"
                    + r"(?:(?:the|a|an)\s+)?"
                    + field_noun
                    + r")*",
                    " evidence",
                    response_object,
                    count=1,
                    flags=re.I,
                )
                delivery_text = requirement_text[: response_match.start()] + response_object
                if not remaining_delivery(delivery_text):
                    continue
                requirement_text = delivery_text
                lower = requirement_text.lower()
            response_destination = re.search(
                r"\b(?:transcripts?|command outputs?)\b.{0,40}"
                r"\b(?:in|into|to)\b.{0,30}"
                r"\b(?:responses?|payloads?|return\s+values?)\b",
                requirement_text,
                re.I,
            )
            review_delivery = re.search(
                r"\b(?:attach|upload|publish|post|record|capture|provide|include|document)\w*"
                r"\b.{0,80}\b(?:in|into|to)\s+(?:the\s+)?(?:pr|pull request)\b",
                requirement_text,
                re.I,
            )
            if response_destination and not review_delivery:
                continue
            line_channels: set[str] = set()
            # Artifact domain nouns in product acceptance (UI, storage, icons)
            # are not workflow evidence deliverables. An explicit delivery into
            # PR content wins even when an API is the actor; otherwise a product
            # actor or product destination is application behavior, not evidence.
            if re.search(r"\b(?:workflow\s+)?artifacts?\b", lower):
                explicit_artifact_delivery = bool(
                    re.search(
                        r"\b(?:upload|attach|publish|post|record|capture|provide|include|document)"
                        r"(?:s)?\s+(?:(?:an?|the|any|workflow|validation|exact-head|evidence)\s+){0,4}"
                        r"artifacts?\b",
                        requirement_text,
                        re.I,
                    )
                    or re.search(
                        r"\b"
                        + mandatory_auxiliary
                        + r"\s+"
                        + passive_delivery_prefix
                        + r"(?:uploaded|attached|published|posted|recorded|captured|provided|"
                        r"included|documented)\s+as\s+(?:(?:an?|the)\s+)?"
                        r"(?:(?:workflow|validation|exact-head|evidence)\s+)?artifacts?\b",
                        requirement_text,
                        re.I,
                    )
                    or re.search(
                        r"\bartifacts?\b.{0,60}\b(?:must|shall|is|required|needs? to)"
                        r"(?:\s+\w+){0,3}\s+be\s+"
                        r"(?:uploaded|attached|published|posted|recorded|captured|provided|"
                        r"included|documented)\b",
                        requirement_text,
                        re.I,
                    )
                )
                product_artifact_destination = bool(
                    re.search(r"\bproduct\s+(?:upload|artifacts?)\b", lower)
                    or re.search(
                        r"\b(?:upload|attach|publish|post|record|capture|provide|include|document)"
                        r"\w*\b.{0,40}\bartifacts?\b"
                        r".{0,30}\b(?:through|to|into|in|via)\b.{0,30}"
                        r"\b(?:storage|database|data\s+store|object\s+store|bucket|"
                        r"filesystem|file\s+system|ui|interface|application|users?|"
                        r"responses?|payloads?|return\s+values?)\b",
                        requirement_text,
                        re.I,
                    )
                    or re.search(
                        r"\bartifacts?\b.{0,60}\b(?:uploaded|attached|published|posted|"
                        r"recorded|captured|provided|included|documented)\b.{0,40}"
                        r"\b(?:by|through|to|into|in|via)\b.{0,30}"
                        r"\b(?:storage|database|data\s+store|object\s+store|bucket|"
                        r"filesystem|file\s+system|ui|interface|application|users?|"
                        r"responses?|payloads?|return\s+values?)\b",
                        requirement_text,
                        re.I,
                    )
                )
                artifact_delivery_into_pr = bool(
                    re.search(
                        r"\b(?:upload|attach|publish|post|record|capture|provide|include|document)"
                        r"\w*\b.{0,60}\bartifacts?\b.{0,40}"
                        r"\b(?:to|into|in)\s+(?:the\s+)?(?:pr|pull request)\b",
                        requirement_text,
                        re.I,
                    )
                    or re.search(
                        r"\b(?:pr|pull request)\b.{0,40}"
                        r"\b(?:must\s+)?(?:include|contain|have)\b.{0,40}\bartifacts?\b",
                        requirement_text,
                        re.I,
                    )
                    or re.search(
                        r"\bartifacts?\b\s+(?:"
                        + mandatory_auxiliary
                        + r"|is|are|will)\s+(?:"
                        + passive_delivery_prefix
                        + r")?"
                        + delivery_operation
                        + r"\s+"
                        + bound_review_destinations,
                        requirement_text,
                        re.I,
                    )
                    or (
                        gate
                        and bool(re.search(r"\bartifacts?\b", lower))
                        and bool(re.search(r"\b(?:pr|pull request)\b", lower))
                    )
                )
                product_artifact_actor = bool(
                    re.search(
                        r"\b(?:ui|api|application|interface|service|worker|cli|database|"
                        r"users?|endpoint|renderer)\b\s+"
                        + "(?:"
                        + product_auxiliary
                        + ")?"
                        + r"(?:(?:"
                        + capability_operation
                        + r")\s+(?:"
                        + recipient_noun
                        + r"\s+(?:to\s+)?)?)?"
                        + r"(?:upload|attach|publish|post|record|capture|"
                        r"provide|include|document)\w*\b.{0,60}\bartifacts?\b",
                        normalize_product_capability(requirement_text),
                        re.I,
                    )
                )
                evidence_named_artifact = bool(
                    re.search(artifact_destination_object, lower)
                    or re.search(
                        r"\b(?:failing and passing |validation |exact-head |workflow |ci |build )artifacts?\b",
                        lower,
                    )
                    or re.search(r"\bvalidation artifacts?\b", lower)
                    or re.search(r"\brequired\s+evidence\s+artifacts?\b", lower)
                    or re.search(r"\bevidence\s+artifacts?\s*:", lower)
                    or re.search(
                        r"\bevidence\s+artifacts?\s+(?:is|are)\s+"
                        r"(?:required|mandatory|needed)\b",
                        lower,
                    )
                    or re.search(
                        r"\b(?:evidence\s+)?artifacts?\s+"
                        r"(?:upload|attachment|publication|posting|capture|recording|generation)"
                        r"\s+(?:is|are)\s+(?:required|mandatory|needed)\b",
                        lower,
                    )
                    or re.search(
                        r"\b(?:upload|attachment|publication|posting|capture|recording|generation)"
                        r"\s+of\s+(?:(?:an?|the|any|evidence|validation|workflow)\s+){0,4}"
                        r"artifacts?\s+(?:is|are)\s+(?:required|mandatory|needed)\b",
                        lower,
                    )
                )
                if (
                    artifact_delivery_into_pr
                    or evidence_named_artifact
                    or (
                        explicit_artifact_delivery
                        and not (product_artifact_actor or product_artifact_destination)
                    )
                ):
                    artifact_description = bool(
                        re.search(
                            r"\bartifacts?\s+(?:metadata|preview|icon|schema|parser)\b", lower
                        )
                    )
                    if not artifact_description and (
                        artifact_delivery_into_pr
                        or evidence_named_artifact
                        or not (product_artifact_actor or product_artifact_destination)
                    ):
                        line_channels.add("artifacts")
                    elif not re.search(r"\b(?:pr comments?|pull request comments?)\b", lower):
                        continue
                elif not re.search(r"\b(?:pr comments?|pull request comments?)\b", lower):
                    continue
            comment_objects = list(
                re.finditer(
                    r"\b(?:pr comments?|pull request comments?)\b",
                    requirement_text,
                    re.I,
                )
            )
            # Union delivery occurrences: a product object cannot erase an
            # earlier mandatory comment, and unresolved subjects keep the floor.
            product_comment_behavior = bool(comment_objects) and all(
                product_comment_object(
                    requirement_text[: item.start()],
                    requirement_text[
                        item.end() : (
                            comment_objects[index + 1].start()
                            if index + 1 < len(comment_objects)
                            else len(requirement_text)
                        )
                    ],
                )
                for index, item in enumerate(comment_objects)
            )
            explicit_comment_delivery = bool(
                (
                    explicit_review_destination
                    and re.search(
                        r"\b(?:pr comments?|pull request comments?)\b", requirement_text, re.I
                    )
                )
                or re.search(
                    r"\b(?:attach|upload|include|post|publish|record|capture|provide|document|add|leave|left|link)\w*\b"
                    r"(?:\s+\w+){0,10}\s+\b(?:pr comments?|pull request comments?)\b",
                    requirement_text,
                    re.I,
                )
                or re.search(
                    r"\b(?:pr comments?|pull request comments?)\b.{0,40}"
                    r"\b(?:(?:is|are)\s+(?:required|mandatory|needed)|"
                    r"(?:must|shall|needs? to)\b|"
                    r"(?:is|are|must|shall|needs? to)\s+(?:be\s+)?(?:posted|published)\b)",
                    requirement_text,
                    re.I,
                )
                or re.search(
                    r"\b(?:evidence|command outputs?|transcripts?)\b.{0,40}"
                    r"\b(?:(?:is|are)\s+(?:required|mandatory|needed)|"
                    + mandatory_auxiliary
                    + r"\s+"
                    + passive_delivery_prefix
                    + r"(?:provided|posted|published|recorded|captured|returned|displayed))"
                    r"\s+in\s+(?:an?\s+|the\s+)?(?:pr comments?|pull request comments?)\b",
                    requirement_text,
                    re.I,
                )
                or re.search(
                    r"\bexact-head\s+(?:pr comments?|pull request comments?)\b",
                    requirement_text,
                    re.I,
                )
                or (gate and bool(re.search(r"\b(?:pr comments?|pull request comments?)\b", lower)))
                or re.search(
                    r"\bthere\s+"
                    + mandatory_auxiliary
                    + r"\s+be\s+(?:(?:an?|the)\s+)?(?:pr comments?|pull request comments?)\b",
                    requirement_text,
                    re.I,
                )
            )
            # Consume one product persistence operation and its immediate
            # storage destination, not later reviewer delivery predicates.
            if bound_product_delivery.search(requirement_text):
                delivery_text = bound_product_delivery.sub(" ", requirement_text, count=1)
                if not remaining_delivery(delivery_text):
                    continue
                requirement_text = delivery_text
                lower = requirement_text.lower()
            storage_operation = re.compile(
                r"\b(?:(?:the|an?)\s+)?(?:application|app|service|api|endpoint)\s+"
                + "(?:"
                + product_auxiliary
                + r"|(?:has|have|had|(?:will|won['’]t)\s+(?:(?:not|never|no\s+longer|"
                + delivery_adverb
                + r")\s+)*have)\s+(?:(?:not|never|no\s+longer|"
                + delivery_adverb
                + r")\s+)*)?"
                + r"(?:have\s+"
                + delivery_adverbs
                + r")?"
                + r"(?:"
                + passive_delivery_prefix
                + r")?"
                + delivery_adverbs
                + r"(?:record|capture|attach|generate)\w*\s+"
                + r"(?:(?:the|an?)\s+)?"
                + evidence_modifiers
                + r"(?:transcripts?|command outputs?|evidence|artifacts?)\s+"
                r"(?:in|into|to|as)\s+(?:(?:its|the|an?)\s+)?"
                r"(?:database|audit log|storage|application log)\b"
                + r"(?!\s+(?:and|or)\s+(?:(?:in|into|to|for|as)\b|"
                + review_destination_noun
                + r"))",
                re.I,
            )
            if storage_operation.search(requirement_text):
                delivery_text = storage_operation.sub(" ", requirement_text, count=1)
                if not remaining_delivery(delivery_text):
                    continue
                requirement_text = delivery_text
                lower = requirement_text.lower()
            # Record aliases are product output only with an immediate bounded
            # product recipient, never merely because the actor is a service.
            product_output_operation = (
                response_operation + "|"
                r"record\w*\b(?=\s+(?:(?:the|an?)\s+)?"
                + evidence_modifiers
                + r"(?:command outputs?|transcripts?|evidence)\s+"
                + product_recipient
                + ")"
            )
            product_output_prefix = re.compile(
                r"^\s*(?:[-*]\s*(?:\[[ xX]\]\s*)?)?"
                r"(?!(?:[\w-]+\s+){0,5}(?:reviewers?|authors?|maintainers?|operators?|"
                r"validation|evidence)\b)"
                r"(?:[\w-]+\s+){1,6}"
                + product_auxiliary
                + r"(?:return|display|emit|render|expose)\w*\b|"
                r"\b(?:ui|api|application|interface|service|cli|endpoint|renderer)\b\s+"
                + "(?:"
                + product_auxiliary
                + ")?"
                + "(?:"
                + product_output_operation
                + ")",
                re.I,
            )
            product_output_match = product_output_prefix.search(requirement_text)
            reverse_product_output = bool(
                re.search(
                    r"\b(?:command outputs?|transcripts?)\b.{0,60}"
                    + "(?:"
                    + product_output_operation
                    + r"|record\w*\b(?=\s+"
                    + product_recipient
                    + ")"
                    + ")"
                    + r".{0,60}"
                    r"\b(?:ui|api|application|interface|service|cli|endpoint|renderer)\b",
                    requirement_text,
                    re.I,
                )
            )
            preserve_explicit_comment_delivery = bool(
                explicit_comment_delivery and not product_comment_behavior
            )
            if (
                product_output_match
                and not preserve_explicit_comment_delivery
                and not explicit_review_destination
            ):
                delivery_text = product_output_prefix.sub(" ", requirement_text, count=1)
                if not remaining_delivery(delivery_text):
                    continue
                requirement_text = delivery_text
                lower = requirement_text.lower()
            elif (
                reverse_product_output
                and not line_channels
                and not preserve_explicit_comment_delivery
                and not explicit_review_destination
            ):
                continue
            if re.search(r"\b(?:pr comments?|pull request comments?)\b", lower):
                if explicit_comment_delivery and not product_comment_behavior:
                    line_channels.add("comments")
                elif not line_channels:
                    continue
            if not line_channels:
                command_behavior = bool(
                    re.search(
                        r"\b(?:cli\s+)?command\b\s+(?:(?:must|shall|will)\s+output|outputs)\b",
                        requirement_text,
                        re.I,
                    )
                )
                if command_behavior and not explicit_review_destination:
                    # A command that outputs JSON describes product behavior;
                    # it is not itself a request to deliver command output.
                    # Preserve a separate downstream evidence requirement.
                    delivery_text = re.sub(
                        r"\b(?:cli\s+)?command\b\s+(?:(?:must|shall|will)\s+output|outputs)\b",
                        " ",
                        requirement_text,
                        count=1,
                        flags=re.I,
                    )
                    if not remaining_delivery(delivery_text):
                        continue
                if re.search(r"\bworkflow runs?\b", lower):
                    without_workflow_run = re.sub(r"\bworkflow runs?\b", " ", lower)
                    workflow_status_only = bool(
                        re.fullmatch(
                            r"\s*(?:[-*]\s*(?:\[[ x]\]\s*)?)?"
                            r"(?:[\w-]+\s+){0,5}workflow runs?\s+"
                            r"(?:(?:must|shall|should|will)\s+(?:pass|succeed|finish|complete|"
                            r"be\s+(?:green|successful|passing|complete))|"
                            r"(?:is|are)\s+(?:required|needed|successful|passing|complete))"
                            r"(?:\s+[\w-]+)*\s*[.!]?\s*",
                            lower,
                        )
                        and not re.search(
                            r"\b(?:link\w*|urls?|provide\w*|include\w*|attach\w*|"
                            r"upload\w*|publish\w*|post\w*|record\w*|capture\w*)\b",
                            lower,
                        )
                    )
                    if workflow_status_only and not evidence_term.search(without_workflow_run):
                        # CI/workflow success belongs in the CI section, not
                        # artifact retrieval. Preserve a transcript/output named
                        # in the same clause rather than discarding the clause.
                        continue
                line_channels.add("overall")
            if (
                resolved_antecedent
                and "artifacts" in line_channels
                and re.search(r"\b(?:command outputs?|transcripts?)\b", resolved_antecedent, re.I)
                and not re.search(r"\b(?:pr comments?|pull request comments?)\b", lower)
            ):
                line_channels.add("overall")
            channels.update(line_channels)
    return channels


def _required_evidence_is_missing(evidence: str, channels: set[str]) -> bool:
    """Read only builder-owned statuses for the required retrieval channels."""
    # Comment and artifact bodies are untrusted. Their status-looking lines
    # cannot overwrite the builder's own preamble.
    preamble = re.split(
        r"\n### Bounded (?:PR body|PR comments|referenced workflow artifacts)\n",
        evidence,
        maxsplit=1,
    )[0]
    labels = {
        "overall": "Overall retrieval status",
        "comments": "PR comments",
        "body": "PR body",
        "artifacts": "Referenced workflow artifacts",
    }
    for channel in channels:
        match = re.search(
            rf"^- {labels[channel]}:\s*\*\*(present|absent|unavailable)\*\*",
            preamble,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        if not match or match.group(1).lower() != "present":
            return True
    return False


def _acceptance_discovery_coverage(
    sections: list[tuple[str, str]] | None,
) -> CoverageStatus:
    # Only the builder-owned inventory before CI is authoritative. An issue
    # body or retained comment cannot replace it with its own status block.
    preamble = next((body for name, body in sections or [] if name == "preamble"), "")
    marker = "## Context source coverage"
    if marker not in preamble:
        return "not_declared"
    match = re.search(
        r"^## Context source coverage\n.*?^```json\n(.*?)\n```", preamble, re.M | re.S
    )
    if not match:
        return "unavailable"
    try:
        inventory = json.loads(match.group(1))
        discovery = inventory.get("acceptance_source_discovery")
        if discovery is None:
            return "not_declared"
        if not isinstance(discovery, dict) or not isinstance(discovery.get("required", True), bool):
            return "unavailable"
        if discovery.get("required") is False:
            return "not_declared"
        if discovery.get("status") == "included":
            return "complete"
        if discovery.get("status") == "truncated":
            return "truncated"
        return "unavailable"
    except (ValueError, AttributeError, TypeError):
        return "unavailable"


def build_prompt_inputs(context: str, diff: str | None) -> PromptInputs:
    """Bound the context and diff blocks and report what reaches the model."""
    context_budget = (
        _budget_from_env("VERIFIER_CONTEXT_BUDGET_TOKENS", VERIFIER_CONTEXT_BUDGET_TOKENS)
        * TOKEN_CHARS
    )
    evidence_budget = (
        _budget_from_env(
            "VERIFIER_ACCEPTANCE_EVIDENCE_BUDGET_TOKENS", VERIFIER_CONTEXT_BUDGET_TOKENS
        )
        * TOKEN_CHARS
    )
    diff_budget = (
        _budget_from_env("VERIFIER_DIFF_BUDGET_TOKENS", VERIFIER_DIFF_BUDGET_TOKENS) * TOKEN_CHARS
    )
    context_text = context.strip() if context and context.strip() else ""
    diff_text = diff.strip() if diff and diff.strip() else ""
    sections = _split_verifier_context(context_text) if context_text else None
    reasons: list[str] = []
    acceptance_source_discovery = _acceptance_discovery_coverage(sections)
    if acceptance_source_discovery in {"truncated", "unavailable"}:
        reasons.append(
            "Required linked-issue acceptance discovery is "
            f"{acceptance_source_discovery}; completeness cannot be judged."
        )

    code_source = diff_text if "diff --git " in diff_text else ""
    non_diff_file_input = bool(diff_text) and not code_source
    upstream_truncated = False
    acceptance_source = ""
    evidence_source = ""
    if sections is not None:
        full = next((body for name, body in sections if name == "full_diff"), "")
        if full:
            context_diff = _strip_diff_fence(full)
            if not code_source:
                upstream_truncated = bool(UPSTREAM_DIFF_TRUNCATION.search(context_diff))
                code_source = UPSTREAM_DIFF_TRUNCATION.sub("", context_diff).strip()
        acceptance_source = next((body for name, body in sections if name == "acceptance"), "")
        evidence_source = next(
            (body for name, body in sections if name == "acceptance_evidence"), ""
        )
        sections = [
            (name, body)
            for name, body in sections
            if name not in {"full_diff", "acceptance_evidence"}
        ]
    if not code_source:
        code_source = diff_text

    if sections is None:
        context_block = _cap_prompt_text(
            context_text or "(context unavailable)", context_budget // TOKEN_CHARS
        )
        context_truncated = bool(context_text) and context_block != context_text
        acceptance: CoverageStatus = "truncated" if context_truncated else "not_declared"
        acceptance_evidence: CoverageStatus = "not_declared"
    else:
        fitted, section_status = _fit_context_sections(sections, context_budget)
        context_block = "\n\n".join(fitted)
        context_truncated = any(value != "complete" for value in section_status.values())
        acceptance = section_status.get("acceptance", "unavailable")  # type: ignore[assignment]
        if evidence_source:
            evidence_block = _cap_prompt_text(evidence_source, evidence_budget // TOKEN_CHARS)
            acceptance_evidence = "complete" if evidence_block == evidence_source else "truncated"
            context_block = "\n\n".join(part for part in (context_block, evidence_block) if part)
        else:
            acceptance_evidence = "not_declared"
    if acceptance == "truncated":
        reasons.append("Acceptance/plan sources were truncated to fit the prompt budget.")
    elif acceptance == "unavailable":
        reasons.append("Acceptance/plan sources do not fit or are unavailable.")
    required_evidence_channels = _required_evidence_channels(
        _acceptance_criteria_sections(acceptance_source)
    )
    if required_evidence_channels:
        if acceptance_evidence in {"not_declared", "unavailable"} or _required_evidence_is_missing(
            evidence_source, required_evidence_channels
        ):
            reasons.append(
                "Required acceptance evidence is unavailable; completeness cannot be judged."
            )
        elif acceptance_evidence == "truncated":
            reasons.append("Required acceptance evidence was truncated to fit the prompt budget.")

    if code_source:
        diff_block, code, files, included, total = _build_code_block(code_source, diff_budget)
    else:
        diff_block, code, files, included, total = "(diff unavailable)", "unavailable", (), 0, 0
    if upstream_truncated:
        code = "truncated"
        reasons.append("The context builder truncated the PR diff before the verifier received it.")
    omitted = [item.path for item in files if item.status == "omitted"]
    summary_body = next((body for name, body in sections or [] if name == "diff_summary"), "")
    if files and summary_body:
        diff_paths = {item.path for item in files}
        try:
            missing = [
                path for path in _summary_destination_paths(summary_body) if path not in diff_paths
            ]
        except ValueError:
            missing = []
            code = "truncated"
            reasons.append(
                "Encoded summary destination metadata is malformed; coverage is unknown."
            )
        if missing:
            code = "truncated"
            reasons.append(
                f"{len(missing)} file(s) listed in the diff summary are absent from the diff: "
                + ", ".join(missing[:10])
            )
    if code == "unavailable":
        if non_diff_file_input:
            reasons.append(
                "Supplied --diff-file is not a complete Git diff; changed code is unavailable."
            )
        reasons.append("Changed code is unavailable; completeness cannot be judged.")
    elif omitted:
        reasons.append(f"{len(omitted)} changed file(s) are omitted from the prompt entirely.")
    elif code == "truncated":
        reasons.append(
            "Changed code was truncated to fit the prompt budget; a PASS is not allowed."
        )
    if total and included / total < MIN_CODE_COVERAGE_RATIO:
        reasons.append(
            f"Only {included}/{total} changed-code characters fit the prompt "
            f"(minimum {MIN_CODE_COVERAGE_RATIO:.0%})."
        )
    elif not files and code == "truncated" and not upstream_truncated:
        reasons.append("The supplied diff was truncated to fit the prompt budget.")

    coverage = PromptCoverage(
        acceptance=acceptance,
        acceptance_evidence=acceptance_evidence,
        code=code,
        files=files,
        code_included_chars=included,
        code_total_chars=total,
        context_truncated=context_truncated,
        reasons=tuple(reasons),
        acceptance_source_discovery=acceptance_source_discovery,
    )
    context_block = coverage.render() + "\n\n" + (context_block or "(context unavailable)")
    return PromptInputs(context_block=context_block, diff_block=diff_block, coverage=coverage)


def prompt_coverage(context: str, diff: str | None) -> PromptCoverage:
    return build_prompt_inputs(context, diff).coverage


def _apply_coverage_floor(
    result: EvaluationResult, coverage: PromptCoverage | None
) -> EvaluationResult:
    """Never let a PASS stand on evidence the model did not receive."""
    if coverage is None:
        return result
    result.input_coverage = coverage.to_dict()
    if coverage.sufficient or result.verdict != "PASS" or not result.used_llm:
        return result
    note = "Verifier input coverage incomplete; PASS withheld: " + "; ".join(coverage.reasons)
    result.verdict = "CONCERNS"
    result.concerns = [note, *result.concerns]
    result.summary = f"{note}\n\n{result.summary}" if result.summary else note
    return result


def _evaluation_output_text(result: EvaluationResult) -> str:
    """CLI/file text aligned with the structured verdict after post-processing."""
    if result.verdict != "PASS":
        parts = [result.summary] if result.summary else []
        if result.concerns:
            parts.append("Concerns:\n" + "\n".join(f"- {item}" for item in result.concerns))
        raw_detail = result.raw_content or ""
        stale_spans: list[tuple[int, int]] = []
        if result.raw_content:
            decoder = json.JSONDecoder()
            for index, char in enumerate(result.raw_content):
                if char != "{":
                    continue
                try:
                    raw_result, end = decoder.raw_decode(result.raw_content, index)
                except json.JSONDecodeError:
                    continue
                if (
                    isinstance(raw_result, dict)
                    and raw_result.get("verdict") == "PASS"
                    and (not stale_spans or index >= stale_spans[-1][1])
                ):
                    stale_spans.append((index, end))
            for start, end in reversed(stale_spans):
                raw_detail = raw_detail[:start] + raw_detail[end:]
            raw_detail = raw_detail.strip()
        if raw_detail and raw_detail != result.summary:
            parts.append("Raw model detail (prior to verdict post-processing):\n" + raw_detail)
        body = "\n\n".join(parts)
        return f"Verdict: {result.verdict}\n\n{body}"
    return result.raw_content or result.summary or ""


def _prepare_prompt(context: str, diff: str | None) -> str:
    inputs = build_prompt_inputs(context, diff)
    diff_block = inputs.diff_block
    context_block = inputs.context_block

    change_type = _classify_change_type(_bounded_diff_for_classification(diff))

    if change_type == "infrastructure":
        if PROMPT_PATH.is_file():
            # Custom prompt file exists — append the lightweight addendum
            LOGGER.info("Infrastructure PR detected; appending infra guidance to custom prompt")
            prompt = _load_prompt()
            prompt = prompt.rstrip() + "\n\n" + INFRA_PROMPT_ADDENDUM + "\n"
        else:
            # No custom prompt — use the full infrastructure-specific prompt
            LOGGER.info("Using infrastructure-relaxed evaluation prompt")
            prompt = _ensure_prompt_rubric(PR_EVALUATION_PROMPT_INFRA)
    else:
        prompt = _load_prompt()

    # Append chain-depth guidance for follow-up iterations
    chain_depth = _get_chain_depth()
    if chain_depth > 0:
        LOGGER.info(
            "Follow-up chain depth %d detected; appending depth-aware guidance",
            chain_depth,
        )
        prompt = prompt.rstrip() + "\n\n" + CHAIN_DEPTH_ADDENDUM.format(depth=chain_depth) + "\n"

    return prompt.format(context=context_block, diff=diff_block)


def _cap_prompt_text(text: str, token_budget: int) -> str:
    max_chars = max(1, token_budget) * TOKEN_CHARS
    if len(text) <= max_chars:
        return text
    marker = "\n[truncated: verifier prompt budget exceeded]"
    if max_chars <= len(marker):
        return marker[:max_chars]
    return (text[: max_chars - len(marker)].rstrip() + marker)[:max_chars]


def _bounded_diff_for_classification(diff: str | None) -> str:
    if not diff:
        return ""
    max_chars = max(1, EVAL_PAIR_BUDGET_TOKENS // 4) * TOKEN_CHARS
    max_lines = 1000
    scanned_chars = 0
    scan_text = diff[:max_chars]
    lines = []
    for index, line in enumerate(io.StringIO(scan_text)):
        if index >= max_lines or scanned_chars >= max_chars:
            break
        scanned_chars += len(line)
        line = line.rstrip("\n\r")
        if line.startswith(("diff --git ", "+++ ", "--- ")):
            lines.append(line)
        if len(lines) >= 500:
            break
    if lines:
        return "\n".join(lines)
    return diff[:max_chars]


def _extract_pr_metadata(context: str) -> tuple[int | None, str | None]:
    if not context:
        return None, None
    for line in context.splitlines():
        if "Pull request:" not in line:
            continue
        match = re.search(r"\[#(?P<number>\d+)\]\((?P<url>[^)]+)\)", line)
        if match:
            return int(match.group("number")), match.group("url")
        match = re.search(r"#(?P<number>\d+)", line)
        if match:
            return int(match.group("number")), None
    return None, None


def _build_llm_config(
    *,
    operation: str,
    context: str | None = None,
    pr_number: int | None = None,
    issue_number: int | None = None,
) -> dict[str, object]:
    if pr_number is None and context:
        pr_number, _ = _extract_pr_metadata(context)

    try:
        from tools.llm_provider import build_langsmith_metadata

        return build_langsmith_metadata(
            operation=operation,
            pr_number=pr_number,
            issue_number=issue_number,
        )
    except ImportError:
        pass

    # Inline fallback when tools.llm_provider is unavailable
    repo = os.environ.get("GITHUB_REPOSITORY", "unknown")
    run_id = os.environ.get("GITHUB_RUN_ID") or os.environ.get("RUN_ID") or "unknown"
    if pr_number is not None:
        issue_or_pr = str(pr_number)
    elif issue_number is not None:
        issue_or_pr = str(issue_number)
    else:
        env_pr = os.environ.get("PR_NUMBER", "")
        env_issue = os.environ.get("ISSUE_NUMBER", "")
        issue_or_pr = (
            env_pr if env_pr.isdigit() else env_issue if env_issue.isdigit() else "unknown"
        )
    metadata = {
        "repo": repo,
        "run_id": run_id,
        "issue_or_pr_number": issue_or_pr,
        "operation": operation,
        "pr_number": str(pr_number) if pr_number is not None else None,
        "issue_number": (str(issue_number) if issue_number is not None else None),
    }
    tags = [
        "workflows-agents",
        f"operation:{operation}",
        f"repo:{repo}",
        f"issue_or_pr:{issue_or_pr}",
        f"run_id:{run_id}",
    ]
    return {"metadata": metadata, "tags": tags}


def _invoke_llm(
    client: object,
    prompt: str,
    *,
    operation: str,
    context: str | None = None,
    pr_number: int | None = None,
    issue_number: int | None = None,
) -> tuple[object, str | None, str | None]:
    """Invoke LLM and extract trace information.

    Returns:
        Tuple of (response, trace_id, trace_url)
    """
    config = _build_llm_config(
        operation=operation,
        context=context,
        pr_number=pr_number,
        issue_number=issue_number,
    )
    try:
        response = client.invoke(prompt, config=config)
    except TypeError as exc:
        LOGGER.warning(
            "LLM invoke failed with config/metadata; using config/metadata fallback. Error: %s",
            exc,
        )
        response = client.invoke(prompt)

    # Extract trace ID from response if available
    trace_id = None
    trace_url = None
    try:
        from tools.llm_provider import derive_langsmith_trace_url, extract_trace_id

        trace_id = extract_trace_id(response)
        if trace_id:
            trace_url = derive_langsmith_trace_url(trace_id)
            LOGGER.info("LangSmith trace: %s", trace_url)
    except ImportError:
        LOGGER.debug("tools.llm_provider not available for trace extraction")
    except Exception as exc:
        LOGGER.debug("Failed to extract trace ID: %s", exc)

    return response, trace_id, trace_url


def _format_scores(scores: EvaluationScores | None) -> list[str]:
    if not scores:
        return ["- Scores: unavailable"]
    return [
        "- Scores:",
        f"  - Correctness: {scores.correctness}/10",
        f"  - Completeness: {scores.completeness}/10",
        f"  - Quality: {scores.quality}/10",
        f"  - Testing: {scores.testing}/10",
        f"  - Risks: {scores.risks}/10",
    ]


def _format_followup_issue_body(
    result: EvaluationResult,
    *,
    pr_number: int | None,
    pr_url: str | None,
    run_url: str | None,
) -> str:
    lines = ["## LLM Evaluation Follow-up", ""]
    lines.append(f"- Verdict: {result.verdict}")
    if result.summary:
        lines.append(f"- Summary: {result.summary.strip()}")
    lines.extend(_format_scores(result.scores))

    lines.append("")
    lines.append("## Concerns")
    if result.concerns:
        for concern in result.concerns:
            if concern:
                lines.append(f"- {concern}")
    else:
        lines.append("- No explicit concerns were returned.")

    if result.error:
        lines.append("")
        lines.append("## Evaluation Error")
        lines.append(result.error)

    lines.append("")
    lines.append("## Links")
    if pr_number:
        pr_label = f"#{pr_number}"
        lines.append(f"- PR: {pr_url or pr_label}")
    if run_url:
        lines.append(f"- Evaluation run: {run_url}")

    return "\n".join(lines).strip() + "\n"


def _should_create_issue(_result: EvaluationResult) -> bool:
    # Disabled: automatic issue creation is no longer desired
    return False


def _create_followup_issue(
    result: EvaluationResult,
    context: str,
    *,
    labels: list[str],
    run_url: str | None,
) -> int | None:
    if not _should_create_issue(result):
        return None

    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return None

    pr_number, pr_url = _extract_pr_metadata(context)
    body = _format_followup_issue_body(
        result,
        pr_number=pr_number,
        pr_url=pr_url,
        run_url=run_url,
    )
    title = "LLM evaluation concerns"
    if pr_number:
        title = f"LLM evaluation concerns for PR #{pr_number}"

    try:
        issue = api_client.create_issue(repo, token, title, body, labels)
    except RuntimeError as exc:
        print(f"pr_verifier: failed to create follow-up issue: {exc}", file=sys.stderr)
        return None

    issue_number = issue.get("number")
    if isinstance(issue_number, int):
        return issue_number
    return None


def _fallback_evaluation(
    message: str, provider: str | None = None, model: str | None = None
) -> EvaluationResult:
    return EvaluationResult(
        verdict="CONCERNS",
        scores=None,
        concerns=["LLM evaluation could not run."],
        summary="Review the PR manually or re-run once LLM credentials are available.",
        provider_used=provider,
        model=model,
        used_llm=False,
        error=message,
    )


def _text_from_response_content(content: object) -> str | None:
    """Return provider text, or None when the payload carries no text blocks."""
    if isinstance(content, str):
        return content if content and not content.isspace() else None
    if isinstance(content, Mapping):
        block_type = content.get("type")
        for key in ("text", "content"):
            text = content.get(key)
            if (
                isinstance(text, str)
                and text
                and not text.isspace()
                and block_type in (None, "text", "output_text")
            ):
                return text
        return None
    if isinstance(content, list):
        text_blocks: list[str] = []
        for block in content:
            if isinstance(block, str):
                text = block
            elif isinstance(block, Mapping):
                if block.get("type") not in (None, "text", "output_text"):
                    text = None
                else:
                    text = block.get("text")
                    if not isinstance(text, str):
                        text = block.get("content")
            else:
                if getattr(block, "type", None) not in (None, "text", "output_text"):
                    text = None
                else:
                    text = getattr(block, "text", None)
                    if not isinstance(text, str):
                        text = getattr(block, "content", None)
            if isinstance(text, str):
                text_blocks.append(text)
        if any(block and not block.isspace() for block in text_blocks):
            # Concatenate without a separator: a provider may split one JSON
            # document across blocks, and an inserted newline inside a string
            # literal would make the reassembled payload invalid JSON.
            return "".join(text_blocks)
    return None


def _coerce_response_content(content: object) -> str:
    """Return text from provider response blocks without losing a safe fallback."""
    text = _text_from_response_content(content)
    if text is not None:
        return text
    try:
        return json.dumps(content, default=str)
    except MemoryError:
        raise
    except Exception:
        try:
            return str(content)
        except MemoryError:
            raise
        except Exception:
            return f"<unserializable {type(content).__name__}>"


def _parse_llm_response(
    content: object, provider: str, *, client: object | None = None
) -> EvaluationResult:
    content_text = _coerce_response_content(content)
    repair = _build_verifier_repair_callback(client) if client is not None else None
    parsed = parse_structured_output(
        content_text,
        EvaluationPayload,
        repair=repair,
        max_repair_attempts=SCHEMA_REPAIR_POLICY.max_attempts,
    )
    if parsed.payload is None:
        decision = SCHEMA_REPAIR_POLICY.terminal_decision(
            repair_attempts_used=parsed.repair_attempts_used,
            error_stage=parsed.error_stage,
            has_payload=False,
        )
        if parsed.error_stage == "repair_validation":
            error = f"Failed to parse JSON response after repair: {parsed.error_detail}"
        else:
            error = f"Failed to parse JSON response: {parsed.error_detail}"
        if decision == "escalate":
            error = f"Schema repair policy escalated verifier output: {error}"
        return EvaluationResult(
            verdict="CONCERNS",
            scores=None,
            concerns=[],
            summary=None,
            provider_used=provider,
            used_llm=True,
            raw_content=content_text,
            error=error,
        )

    payload = parsed.payload
    return EvaluationResult(
        verdict=payload.verdict,
        scores=payload.scores,
        confidence=payload.confidence,
        concerns=payload.concerns,
        summary=payload.summary,
        provider_used=provider,
        used_llm=True,
        raw_content=parsed.raw_content or content_text,
    )


def _build_verifier_repair_callback(client: object) -> Callable[[str, str, str], str | None]:
    repair = build_repair_callback(client)

    def _repair(schema_json: str, validation_errors: str, raw_response: str) -> str | None:
        repaired = repair(
            schema_json,
            validation_errors,
            _cap_prompt_text(raw_response, EVAL_SCHEMA_REPAIR_BUDGET_TOKENS),
        )
        if not repaired:
            return None
        # The repair path must be stricter than the parse path. A reply of only
        # thinking/metadata blocks, or of empty text blocks, is still truthy, and
        # serializing it would hand the parser block metadata dressed up as a
        # repair attempt — burning the one retry on noise.
        text = _text_from_response_content(repaired)
        if text is None or not text.strip():
            return None
        return text

    return _repair


def _is_auth_error(exc: Exception) -> bool:
    """Check if an exception is an authentication/authorization error."""
    exc_str = str(exc).lower()
    # Common auth error patterns from various LLM APIs
    auth_patterns = ["401", "unauthorized", "forbidden", "403", "permission", "authentication"]
    return any(pattern in exc_str for pattern in auth_patterns)


def evaluate_pr(
    context: str,
    diff: str | None = None,
    model: str | None = None,
    provider: str | None = None,
) -> EvaluationResult:
    """Evaluate a PR against its acceptance criteria.

    Args:
        context: The PR context markdown (issue body, PR description, etc.)
        diff: Optional PR diff or summary
        model: Optional model name (e.g., 'gpt-4o', 'gpt-5.2', 'o1-mini').
            Uses default if not specified.
        provider: Optional provider ('openai' or 'github-models').
            Auto-selects if not specified.

    Returns:
        EvaluationResult with verdict, scores, and concerns.
    """
    resolved = _get_llm_client(model=model, provider=provider)
    coverage = prompt_coverage(context, diff)
    if resolved is None:
        return _apply_coverage_floor(
            _fallback_evaluation("LLM client unavailable (missing credentials or dependency)."),
            coverage,
        )

    client, provider_name = resolved
    prompt = _prepare_prompt(context, diff)
    change_type = _classify_change_type(_bounded_diff_for_classification(diff))
    pr_number, _ = _extract_pr_metadata(context)
    trace_id, trace_url = None, None
    try:
        response, trace_id, trace_url = _invoke_llm(
            client,
            prompt,
            operation="evaluate_pr",
            context=context,
            pr_number=pr_number,
        )
    except Exception as exc:  # pragma: no cover - exercised in integration
        # If auth error and not explicitly requesting a provider, try fallback
        if _is_auth_error(exc) and provider is None:
            fallback_provider = "openai" if "github-models" in provider_name else "github-models"
            fallback_resolved = _get_llm_client(model=model, provider=fallback_provider)
            if fallback_resolved is not None:
                fallback_client, fallback_provider_name = fallback_resolved
                try:
                    response, trace_id, trace_url = _invoke_llm(
                        fallback_client,
                        prompt,
                        operation="evaluate_pr_fallback",
                        context=context,
                        pr_number=pr_number,
                    )
                    content = getattr(response, "content", None) or str(response)
                    result = _parse_llm_response(
                        content, fallback_provider_name, client=fallback_client
                    )
                    # Add note about fallback
                    if result.summary:
                        result = EvaluationResult(
                            verdict=result.verdict,
                            scores=result.scores,
                            concerns=result.concerns,
                            summary=result.summary,
                            provider_used=fallback_provider_name,
                            model=result.model,
                            used_llm=result.used_llm,
                            error=f"Primary provider ({provider_name}) failed, used fallback",
                            raw_content=result.raw_content,
                            change_type=change_type,
                            langsmith_trace_id=trace_id,
                            langsmith_trace_url=trace_url,
                        )
                    else:
                        result.change_type = change_type
                        result.langsmith_trace_id = trace_id
                        result.langsmith_trace_url = trace_url
                    return _apply_coverage_floor(result, coverage)
                except Exception as fallback_exc:
                    result = _fallback_evaluation(
                        f"Primary ({provider_name}): {exc}; "
                        f"Fallback ({fallback_provider_name}): {fallback_exc}"
                    )
                    result.change_type = change_type
                    return _apply_coverage_floor(result, coverage)
        result = _fallback_evaluation(f"LLM invocation failed: {exc}")
        result.change_type = change_type
        return _apply_coverage_floor(result, coverage)

    content = getattr(response, "content", None) or str(response)
    result = _parse_llm_response(content, provider_name, client=client)
    result.change_type = change_type
    result.langsmith_trace_id = trace_id
    result.langsmith_trace_url = trace_url
    return _apply_coverage_floor(result, coverage)


def evaluate_pr_multiple(
    context: str, diff: str | None = None, model1: str | None = None, model2: str | None = None
) -> list[EvaluationResult]:
    change_type = _classify_change_type(_bounded_diff_for_classification(diff))
    runner = ComparisonRunner.from_environment(context, diff, model1, model2)
    is_valid, error_message = _validate_comparison_clients(runner.clients)
    if not is_valid:
        result = _fallback_evaluation(error_message)
        result.change_type = change_type
        return [_apply_coverage_floor(result, runner.coverage)]
    results: list[EvaluationResult] = []
    for client, provider, model in runner.clients:
        result = runner.run_single(client, provider, model)
        result.change_type = change_type
        results.append(result)
    return results


def _provider_family(provider: str) -> str:
    label = provider.lower()
    if "github-models" in label:
        return "github-models"
    if "openai" in label:
        return "openai"
    if "anthropic" in label or "claude" in label:
        return "anthropic"
    return label.split("/", 1)[0].strip() or "unknown"


def _get_provider_families(clients: list[tuple[object, str, str]]) -> set[str]:
    """Extract the set of unique provider families from a list of clients.

    Args:
        clients: List of (client, provider, model) tuples.

    Returns:
        Set of provider family names (e.g., {"openai", "anthropic"}).
    """
    return {_provider_family(provider) for _, provider, _ in clients}


def _validate_comparison_clients(clients: list[tuple[object, str, str]]) -> tuple[bool, str]:
    """Validate that client list is sufficient for cross-family comparison.

    Args:
        clients: List of (client, provider, model) tuples.

    Returns:
        Tuple of (is_valid, error_message).
        is_valid is True if there are >= 2 clients from >= 2 different provider families.
        error_message describes the reason if validation fails.
    """
    families = _get_provider_families(clients)
    if len(clients) < 2:
        family_str = ", ".join(sorted(families)) or "none"
        return (
            False,
            f"unverified: compare mode requires two cross-family verifier judges; "
            f"available families: {family_str}.",
        )
    if len(families) < 2:
        family_str = ", ".join(sorted(families)) or "none"
        return (
            False,
            f"unverified: compare mode requires two cross-family verifier judges; "
            f"available families: {family_str}.",
        )
    return True, ""


def _normalize_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip().lower())
    return cleaned


def _compact_text(text: str, limit: int = 160) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: max(0, limit - 3)].rstrip()}..."


def _provider_label(result: EvaluationResult, index: int) -> str:
    return result.provider_used or f"provider-{index + 1}"


def _format_confidence(confidence: float | None) -> str:
    if confidence is None:
        return "N/A"
    return f"{confidence:.0%}"


def _shared_concerns(results: list[EvaluationResult]) -> list[str]:
    counts: dict[str, dict[str, object]] = {}
    for result in results:
        for concern in result.concerns:
            normalized = _normalize_text(concern)
            if not normalized:
                continue
            entry = counts.setdefault(normalized, {"count": 0, "text": concern})
            entry["count"] = int(entry["count"]) + 1
    shared = []
    for entry in counts.values():
        if int(entry["count"]) > 1:
            shared.append(str(entry["text"]))
    return shared


def _unique_concerns(results: list[EvaluationResult]) -> dict[int, list[str]]:
    counts: dict[str, int] = {}
    for result in results:
        for concern in result.concerns:
            normalized = _normalize_text(concern)
            if not normalized:
                continue
            counts[normalized] = counts.get(normalized, 0) + 1

    unique: dict[int, list[str]] = {}
    for index, result in enumerate(results):
        unique_concerns: list[str] = []
        for concern in result.concerns:
            normalized = _normalize_text(concern)
            if normalized and counts.get(normalized, 0) == 1:
                unique_concerns.append(concern)
        unique[index] = unique_concerns
    return unique


def format_comparison_report(results: list[EvaluationResult]) -> str:
    lines = ["## Provider Comparison Report", ""]
    if not results:
        lines.append("No evaluation results available.")
        return "\n".join(lines).strip() + "\n"

    if len(results) == 1:
        lines.append("Only one provider was available; comparison skipped.")
        lines.append("")

    labels = [_provider_label(result, index) for index, result in enumerate(results)]

    lines.append("### Provider Summary")
    lines.append("| Provider | Model | Verdict | Confidence | Summary |")
    lines.append("| --- | --- | --- | --- | --- |")
    for index, result in enumerate(results):
        summary_source = result.summary or result.raw_content or ""
        summary = _compact_text(summary_source, limit=200) if summary_source else "N/A"
        model_name = result.model or "N/A"
        conf = _format_confidence(result.confidence)
        lines.append(f"| {labels[index]} | {model_name} | {result.verdict} | {conf} | {summary} |")
    lines.append("")

    # Add expandable full details for each provider
    lines.append("<details>")
    lines.append("<summary>📋 Full Provider Details (click to expand)</summary>")
    lines.append("")
    for index, result in enumerate(results):
        lines.append(f"#### {labels[index]}")
        if result.model:
            lines.append(f"- **Model:** {result.model}")
        lines.append(f"- **Verdict:** {result.verdict}")
        lines.append(f"- **Confidence:** {_format_confidence(result.confidence)}")
        if result.scores:
            lines.append("- **Scores:**")
            lines.append(f"  - Correctness: {result.scores.correctness}/10")
            lines.append(f"  - Completeness: {result.scores.completeness}/10")
            lines.append(f"  - Quality: {result.scores.quality}/10")
            lines.append(f"  - Testing: {result.scores.testing}/10")
            lines.append(f"  - Risks: {result.scores.risks}/10")
        if result.summary:
            lines.append(f"- **Summary:** {result.summary}")
        if result.concerns:
            lines.append("- **Concerns:**")
            for concern in result.concerns:
                lines.append(f"  - {concern}")
        if result.error:
            lines.append(f"- **Error:** {result.error}")
        lines.append("")
    lines.append("</details>")
    lines.append("")

    lines.append("### Agreement")
    agreements: list[str] = []
    verdicts = {result.verdict for result in results}
    if len(verdicts) == 1:
        verdict = verdicts.pop()
        agreements.append(f"- Verdict: {verdict} (all providers)")

    for key in SCORE_KEYS:
        scores = [getattr(result.scores, key) for result in results if result.scores is not None]
        if len(scores) != len(results):
            continue
        min_score = min(scores)
        max_score = max(scores)
        if max_score - min_score <= 1:
            avg_score = sum(scores) / len(scores)
            agreements.append(
                f"- {key.capitalize()}: scores within 1 point (avg {avg_score:.1f}/10, "
                f"range {min_score:.1f}-{max_score:.1f})"
            )

    for concern in _shared_concerns(results):
        agreements.append(f"- Concern: {concern}")

    if not agreements:
        lines.append("- No clear areas of agreement.")
    else:
        lines.extend(agreements)
    lines.append("")

    lines.append("### Disagreement")
    rows: list[tuple[str, list[str]]] = []
    if len(verdicts) > 1:
        rows.append(("Verdict", [result.verdict for result in results]))

    for key in SCORE_KEYS:
        scores = [
            getattr(result.scores, key) if result.scores is not None else None for result in results
        ]
        available = [score for score in scores if score is not None]
        if len(available) < 2:
            continue
        min_score = min(available)
        max_score = max(available)
        if max_score - min_score > 1:
            rendered = [f"{score:.1f}/10" if score is not None else "N/A" for score in scores]
            rows.append((key.capitalize(), rendered))

    if rows:
        header = "| Dimension | " + " | ".join(labels) + " |"
        separator = "| --- | " + " | ".join(["---"] * len(labels)) + " |"
        lines.append(header)
        lines.append(separator)
        for dimension, values in rows:
            lines.append("| {dim} | {vals} |".format(dim=dimension, vals=" | ".join(values)))
    else:
        lines.append("No major disagreements detected.")
    lines.append("")

    lines.append("### Unique Insights")
    unique_map = _unique_concerns(results)
    for index, result in enumerate(results):
        insights = unique_map.get(index, [])
        if not insights:
            summary = result.summary or ""
            if summary:
                insights = [_compact_text(summary, limit=300)]
        if not insights:
            insights = ["No unique insights reported."]
        lines.append(f"- {labels[index]}: {'; '.join(insights)}")
    lines.append("")

    # Add LangSmith trace links if available
    trace_urls = [
        (labels[i], result.langsmith_trace_url)
        for i, result in enumerate(results)
        if result.langsmith_trace_url
    ]
    if trace_urls:
        lines.append("### 🔍 LangSmith Traces")
        for label, url in trace_urls:
            lines.append(f"- [{label}]({url})")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _load_text(path: str | None) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8")
    return sys.stdin.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate PRs against acceptance criteria.")
    parser.add_argument("--context-file", help="Path to verifier context markdown.")
    parser.add_argument("--diff-file", help="Path to PR diff or summary.")
    parser.add_argument("--output-file", help="Path to write evaluation output.")
    parser.add_argument(
        "--model",
        help="LLM model to use (e.g., gpt-4o, gpt-4o-mini, gpt-5.2, o1-mini).",
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "github-models"],
        help=(
            "LLM provider: 'openai' (requires OPENAI_API_KEY) or "
            "'github-models' (uses GITHUB_TOKEN)."
        ),
    )
    parser.add_argument(
        "--model2",
        help="Second LLM model for compare mode (defaults to --model if not specified).",
    )
    parser.add_argument(
        "--create-issue",
        action="store_true",
        help="Create a follow-up issue on CONCERNS/FAIL verdicts when running in GitHub Actions.",
    )
    parser.add_argument(
        "--issue-label",
        action="append",
        default=[],
        help="Label to apply to follow-up issues (repeatable).",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run evaluations across multiple providers and output a comparison report.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON payload to stdout.")
    args = parser.parse_args()

    context = _load_text(args.context_file)
    diff = _load_text(args.diff_file) if args.diff_file else None
    if args.compare:
        results = evaluate_pr_multiple(context, diff=diff, model1=args.model, model2=args.model2)
        report = format_comparison_report(results)
        if args.output_file:
            Path(args.output_file).write_text(report, encoding="utf-8")
        if args.json:
            payload = {
                "results": [result.model_dump() for result in results],
                "report": report,
            }
            print(json.dumps(payload, ensure_ascii=True))
        else:
            print(report)
        return

    result = evaluate_pr(context, diff=diff, model=args.model, provider=args.provider)
    issue_labels = args.issue_label or [
        "agent:codex"
    ]  # callers should pass --issue-label to match PR agent
    run_url = None
    if (
        os.environ.get("GITHUB_RUN_ID")
        and os.environ.get("GITHUB_SERVER_URL")
        and os.environ.get("GITHUB_REPOSITORY")
    ):
        run_url = (
            f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}"
            f"/actions/runs/{os.environ['GITHUB_RUN_ID']}"
        )
    if args.create_issue:
        try:
            issue_number = _create_followup_issue(
                result, context, labels=issue_labels, run_url=run_url
            )
            if issue_number:
                print(f"Created follow-up issue #{issue_number}.", file=sys.stderr)
        except Exception as exc:
            print(f"Failed to create follow-up issue: {exc}", file=sys.stderr)

    output_text = _evaluation_output_text(result)

    if args.output_file:
        Path(args.output_file).write_text(output_text, encoding="utf-8")

    if args.json:
        print(json.dumps(result.model_dump(), ensure_ascii=True))
    else:
        print(output_text)


if __name__ == "__main__":
    main()
