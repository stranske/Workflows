#!/usr/bin/env python3
"""
Evaluate pull requests with an LLM-backed rubric.

Run with:
    python scripts/langchain/pr_verifier.py --context-file verifier-context.md --json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from scripts import api_client
from scripts.langchain.structured_output import (
    build_repair_callback,
    parse_structured_output,
)

LOGGER = logging.getLogger(__name__)

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

Ignore CI workflow status - focus on code quality and acceptance criteria fulfillment.

**Verdict guidelines:**
- **PASS**: correctness and completeness are satisfied.  Testing gaps alone
  should NOT prevent a PASS if the implementation is functionally correct.
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
- **correctness**: This is the primary criterion — does the fix address the
  original concerns?  Weight correctness heavily.
- **completeness**: Evaluate whether the specific concerns from the prior
  verification have been addressed.  Do not expand scope beyond what was asked.
- At chain depth {depth}, focus strictly on whether THIS iteration resolves
  its targeted concerns.  Avoid raising new concerns that were not part of
  the original feedback.
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


def _get_llm_client(
    model: str | None = None, provider: str | None = None
) -> tuple[object, str] | None:
    """Get an LLM client for evaluation.

    Args:
        model: Optional model name override.
        provider: Optional provider override ('openai' or 'github-models').
                  If not specified, uses OpenAI if OPENAI_API_KEY is set and model
                  is specified, otherwise falls back to GitHub Models.

    Returns:
        Tuple of (client, provider_name) or None if no credentials available.
    """
    try:
        from tools.langchain_client import build_chat_client
    except ImportError:
        return None

    resolved = build_chat_client(model=model, provider=provider)
    if not resolved:
        return None
    return resolved.client, resolved.provider_label


def _get_llm_clients(
    model1: str | None = None, model2: str | None = None
) -> list[tuple[object, str, str]]:
    try:
        from tools.langchain_client import build_chat_clients
    except ImportError:
        return []

    clients = build_chat_clients(model1=model1, model2=model2)
    return [(entry.client, entry.provider, entry.model) for entry in clients]


@dataclass(frozen=True)
class ComparisonRunner:
    context: str
    diff: str | None
    prompt: str
    clients: list[tuple[object, str, str]]  # (client, provider, model)

    @classmethod
    def from_environment(
        cls, context: str, diff: str | None, model1: str | None = None, model2: str | None = None
    ) -> ComparisonRunner:
        return cls(
            context=context,
            diff=diff,
            prompt=_prepare_prompt(context, diff),
            clients=_get_llm_clients(model1, model2),
        )

    def run_single(self, client: object, provider: str, model: str) -> EvaluationResult:
        try:
            response = _invoke_llm(
                client,
                self.prompt,
                operation="evaluate_pr_compare",
                context=self.context,
            )
        except Exception as exc:  # pragma: no cover - exercised in integration
            return _fallback_evaluation(
                f"LLM invocation failed: {exc}", provider=provider, model=model
            )

        content = getattr(response, "content", None) or str(response)
        result = _parse_llm_response(content, provider, client=client)
        result.model = model
        return result


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


def _prepare_prompt(context: str, diff: str | None) -> str:
    diff_block = diff.strip() if diff and diff.strip() else "(diff unavailable)"
    context_block = context.strip() if context and context.strip() else "(context unavailable)"

    change_type = _classify_change_type(diff)

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
) -> object:
    config = _build_llm_config(
        operation=operation,
        context=context,
        pr_number=pr_number,
        issue_number=issue_number,
    )
    try:
        return client.invoke(prompt, config=config)
    except TypeError as exc:
        LOGGER.warning(
            "LLM invoke failed with config/metadata; using config/metadata fallback. Error: %s",
            exc,
        )
        return client.invoke(prompt)


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


def _parse_llm_response(
    content: str, provider: str, *, client: object | None = None
) -> EvaluationResult:
    parsed = parse_structured_output(
        content,
        EvaluationPayload,
        repair=(build_repair_callback(client) if client is not None else None),
        max_repair_attempts=1,
    )
    if parsed.payload is None:
        if parsed.error_stage == "repair_validation":
            error = f"Failed to parse JSON response after repair: {parsed.error_detail}"
        else:
            error = f"Failed to parse JSON response: {parsed.error_detail}"
        return EvaluationResult(
            verdict="CONCERNS",
            scores=None,
            concerns=[],
            summary=None,
            provider_used=provider,
            used_llm=True,
            raw_content=content,
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
        raw_content=parsed.raw_content or content,
    )


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
    if resolved is None:
        return _fallback_evaluation("LLM client unavailable (missing credentials or dependency).")

    client, provider_name = resolved
    prompt = _prepare_prompt(context, diff)
    change_type = _classify_change_type(diff)
    pr_number, _ = _extract_pr_metadata(context)
    try:
        response = _invoke_llm(
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
                    response = _invoke_llm(
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
                        )
                    else:
                        result.change_type = change_type
                    return result
                except Exception as fallback_exc:
                    result = _fallback_evaluation(
                        f"Primary ({provider_name}): {exc}; "
                        f"Fallback ({fallback_provider_name}): {fallback_exc}"
                    )
                    result.change_type = change_type
                    return result
        result = _fallback_evaluation(f"LLM invocation failed: {exc}")
        result.change_type = change_type
        return result

    content = getattr(response, "content", None) or str(response)
    result = _parse_llm_response(content, provider_name, client=client)
    result.change_type = change_type
    return result


def evaluate_pr_multiple(
    context: str, diff: str | None = None, model1: str | None = None, model2: str | None = None
) -> list[EvaluationResult]:
    change_type = _classify_change_type(diff)
    runner = ComparisonRunner.from_environment(context, diff, model1, model2)
    if not runner.clients:
        result = _fallback_evaluation("LLM client unavailable (missing credentials or dependency).")
        result.change_type = change_type
        return [result]
    results: list[EvaluationResult] = []
    for client, provider, model in runner.clients:
        result = runner.run_single(client, provider, model)
        result.change_type = change_type
        results.append(result)
    return results


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
    issue_labels = args.issue_label or ["agent:codex"]
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

    output_text = result.raw_content or result.summary or ""

    if args.output_file:
        Path(args.output_file).write_text(output_text, encoding="utf-8")

    if args.json:
        print(json.dumps(result.model_dump(), ensure_ascii=True))
    else:
        print(output_text)


if __name__ == "__main__":
    main()
