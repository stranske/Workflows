#!/usr/bin/env python3
"""
LLM-based progress review for agent work alignment.

This module evaluates whether an agent's recent work is meaningfully advancing
toward acceptance criteria, even if task checkboxes haven't been completed yet.

The key insight is distinguishing between:
- Legitimate prep work (refactoring, utilities, dependencies) that enables tasks
- Scope drift (working on tangential improvements not in acceptance criteria)
- Stalled work (spinning without meaningful progress)

Run with:
    python scripts/langchain/progress_reviewer.py \
        --acceptance-criteria "criterion 1" "criterion 2" \
        --recent-commits "commit1 msg" "commit2 msg" \
        --files-changed "file1.py" "file2.py" \
        --rounds-without-completion 8 \
        --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

# ---------------------------------------------------------------------------
# Prompt template for progress review
# ---------------------------------------------------------------------------

PROGRESS_REVIEW_PROMPT = """
You are evaluating whether an automated coding agent is making meaningful progress
toward its assigned acceptance criteria.

## Context
The agent has been working for {rounds_without_completion} consecutive rounds without
completing any task checkboxes. However, file changes indicate ongoing activity.

Your job is to determine if:
1. The agent is doing **legitimate prep work** (building utilities, refactoring,
   adding dependencies) that will enable task completion soon
2. The agent has **drifted off scope** - working on tangential improvements not
   required by the acceptance criteria
3. The agent is **stalled** - making changes but not advancing toward any criteria

## Acceptance Criteria (What the agent SHOULD be working toward)
{acceptance_criteria}

## Recent Commit Messages (What the agent HAS been doing)
{recent_commits}

## Files Changed Recently
{files_changed}

## Analysis Instructions

1. **Alignment Check**: Do the recent commits relate to the acceptance criteria?
   - Direct work on criteria = HIGH alignment
   - Enabling infrastructure (tests, utils, deps) = MEDIUM alignment
   - Unrelated improvements or refactoring = LOW alignment

2. **Progress Trajectory**: Is there a clear path from recent work to criteria completion?
   - Clear dependency chain = making progress
   - No visible connection = likely drifted

3. **Efficiency Assessment**: Given {rounds_without_completion} rounds of work:
   - Is this reasonable prep time for the scope?
   - Are commits getting closer to criteria or diverging?

## Response Format
Respond with a JSON object:
{{
  "recommendation": "CONTINUE | REDIRECT | STOP",
  "confidence": 0.0-1.0,
  "alignment_score": 0-10,
  "trajectory": "advancing | plateau | diverging",
  "analysis": {{
    "prep_work_identified": ["list of legitimate prep work items"],
    "scope_drift_identified": ["list of off-scope work items"],
    "estimated_rounds_to_completion": null or integer,
    "blocking_issues": ["any issues preventing progress"]
  }},
  "feedback_for_agent": "Specific guidance to redirect the agent if needed",
  "summary": "Brief explanation of recommendation"
}}

## Recommendation Guidelines
- **CONTINUE**: Alignment >= 6, clear trajectory toward criteria, reasonable prep time
- **REDIRECT**: Alignment 3-6, some work is relevant but agent needs course correction
- **STOP**: Alignment < 3, no visible path to criteria, or excessive time spent
""".strip()


class ProgressAnalysis(BaseModel):
    prep_work_identified: list[str] = Field(default_factory=list)
    scope_drift_identified: list[str] = Field(default_factory=list)
    estimated_rounds_to_completion: int | None = None
    blocking_issues: list[str] = Field(default_factory=list)


class ProgressReviewResult(BaseModel):
    recommendation: Literal["CONTINUE", "REDIRECT", "STOP"]
    confidence: float = Field(ge=0, le=1)
    alignment_score: float = Field(ge=0, le=10)
    trajectory: Literal["advancing", "plateau", "diverging"]
    analysis: ProgressAnalysis
    feedback_for_agent: str
    summary: str
    provider_used: str | None = None
    model: str | None = None
    used_llm: bool = False
    error: str | None = None
    langsmith_trace_id: str | None = None
    langsmith_trace_url: str | None = None


# ---------------------------------------------------------------------------
# Heuristic pre-check (fast path)
# ---------------------------------------------------------------------------


def build_review_payload(result: ProgressReviewResult) -> dict:
    payload = result.model_dump()
    if payload.get("review") is None:
        suggestions = []
        analysis = result.analysis
        if analysis and analysis.blocking_issues:
            suggestions.extend([item for item in analysis.blocking_issues if item])
        if analysis and analysis.scope_drift_identified:
            suggestions.extend([item for item in analysis.scope_drift_identified if item])
        payload["review"] = {
            "score": result.alignment_score,
            "feedback": result.feedback_for_agent,
            "suggestions": "; ".join(suggestions),
        }
    return payload


def heuristic_alignment_check(
    acceptance_criteria: list[str],
    recent_commits: list[str],
    _files_changed: list[str],
) -> tuple[float, list[str], list[str]]:
    """
    Quick heuristic check for alignment before invoking LLM.

    Returns:
        (alignment_score, aligned_commits, unaligned_commits)
    """
    # Allowlist for common, meaningful short tokens that frequently appear in
    # acceptance criteria as snake_case parts, and in commits as acronyms.
    # Keep this small to avoid inflating alignment via generic 3-letter words.
    short_token_allowlist = {
        "png",
        "pdf",
        "csv",
        "ppt",
        "pptx",
        "cprs",
        "fcm",
        "json",
        "yaml",
        "yml",
    }

    criteria_keywords = set()
    for criterion in acceptance_criteria:
        # Extract meaningful words from criteria.
        # Note: acceptance criteria often include snake_case identifiers (e.g.
        # render_cprs_ch_png). Split those into tokens so commits like
        # "CPRS-CH PNG" can be recognized as aligned.
        words = re.findall(r"\b[a-z0-9_]{4,}\b", criterion.lower())
        for word in words:
            criteria_keywords.add(word)
            if "_" in word:
                for token in word.split("_"):
                    if len(token) >= 4 or token in short_token_allowlist:
                        criteria_keywords.add(token)

    # Infrastructure words that indicate supporting work
    # These alone don't count as alignment, but combined with criteria keywords they help
    infra_words = {
        "test",
        "tests",
        "testing",
        "fixture",
        "mock",
        "stub",
        "util",
        "utils",
        "utility",
        "helper",
        "helpers",
        "config",
        "configuration",
        "setup",
        "init",
        "dependency",
        "dependencies",
        "requirements",
        "refactor",
        "cleanup",
        "lint",
        "format",
        "formatting",
        "type",
        "types",
        "typing",
        "annotation",
        "annotations",
        "doc",
        "docs",
        "documentation",
        "docstring",
    }

    # Words that indicate potential scope drift when used alone
    generic_commit_prefixes = {"fix", "feat", "chore", "refactor", "style", "perf"}

    aligned = []
    unaligned = []

    for commit in recent_commits:
        commit_lower = commit.lower()
        commit_words = set(re.findall(r"\b[a-z0-9_]{3,}\b", commit_lower))

        # Check for direct criteria match (strong signal)
        criteria_match = criteria_keywords & commit_words
        infra_match = infra_words & commit_words

        # Strong alignment: directly mentions criteria keywords
        if criteria_match:
            aligned.append(commit)
        # Moderate alignment: infrastructure work that supports criteria
        elif infra_match:
            # But only if the commit isn't just a generic prefix + unrelated topic
            non_generic_words = commit_words - generic_commit_prefixes - infra_words
            # If there are non-generic words that aren't in criteria, it's likely drift
            if len(non_generic_words) <= 2:  # Allow some noise
                aligned.append(commit)
            else:
                unaligned.append(commit)
        else:
            unaligned.append(commit)

    if not recent_commits:
        return 0.0, [], []

    alignment_ratio = len(aligned) / len(recent_commits)
    # Scale to 0-10
    alignment_score = alignment_ratio * 10

    return alignment_score, aligned, unaligned


# Patterns for orchestrator bookkeeping files that should not count as "agent work".
# These files are written by the keepalive orchestrator, not the coding agent.
_BOOKKEEPING_PATTERNS = re.compile(
    r"(?:^|/)(?:"
    r"claude-(?:prompt|output)-\d+\.md"
    r"|codex-(?:prompt|output)-\d+\.md"
    r"|claude-(?:session|analysis)-\d+\.(?:jsonl|json)"
    r"|agents/claude-\d+\.md"
    r"|\.agents/"
    r"|autofix-[^/]*$"
    r")",
)


def _filter_bookkeeping_files(files: list[str]) -> list[str]:
    """Remove orchestrator bookkeeping files that don't represent agent work."""
    return [f for f in files if not _BOOKKEEPING_PATTERNS.search(f)]


def build_review_prompt(
    acceptance_criteria: list[str],
    recent_commits: list[str],
    files_changed: list[str],
    rounds_without_completion: int,
) -> str:
    """Build the prompt for LLM review."""
    criteria_text = "\n".join(f"- {c}" for c in acceptance_criteria) or "No criteria provided"
    commits_text = "\n".join(f"- {c}" for c in recent_commits[-20:]) or "No commits"  # Last 20
    files_text = "\n".join(f"- {f}" for f in files_changed[-30:]) or "No files"  # Last 30

    return PROGRESS_REVIEW_PROMPT.format(
        rounds_without_completion=rounds_without_completion,
        acceptance_criteria=criteria_text,
        recent_commits=commits_text,
        files_changed=files_text,
    )


def parse_llm_response(content: str) -> ProgressReviewResult | None:
    """Parse LLM response into structured result."""
    # Try to extract JSON from response
    json_match = re.search(r"\{[\s\S]*\}", content)
    if not json_match:
        return None

    try:
        data = json.loads(json_match.group())
        # Normalize recommendation
        rec = data.get("recommendation", "").upper()
        if rec not in ("CONTINUE", "REDIRECT", "STOP"):
            rec = "REDIRECT"  # Default to safe middle ground
        data["recommendation"] = rec

        # Normalize trajectory
        traj = data.get("trajectory", "").lower()
        if traj not in ("advancing", "plateau", "diverging"):
            traj = "plateau"
        data["trajectory"] = traj

        return ProgressReviewResult(**data)
    except (json.JSONDecodeError, ValidationError):
        return None


# ---------------------------------------------------------------------------
# LangSmith tracing helpers
# ---------------------------------------------------------------------------


def _build_llm_config(
    *,
    operation: str,
    pr_number: int | None = None,
) -> dict[str, object]:
    """Build LangSmith metadata/tags for LLM call."""
    import os

    try:
        from tools.llm_provider import build_langsmith_metadata

        return build_langsmith_metadata(
            operation=operation,
            pr_number=pr_number,
        )
    except ImportError:
        pass

    # Inline fallback when tools.llm_provider is unavailable
    repo = os.environ.get("GITHUB_REPOSITORY", "unknown")
    run_id = os.environ.get("GITHUB_RUN_ID") or os.environ.get("RUN_ID") or "unknown"
    env_pr = os.environ.get("PR_NUMBER", "")
    issue_or_pr = env_pr if env_pr.isdigit() else str(pr_number) if pr_number else "unknown"

    metadata = {
        "repo": repo,
        "run_id": run_id,
        "issue_or_pr_number": issue_or_pr,
        "operation": operation,
        "pr_number": str(pr_number) if pr_number is not None else None,
    }
    tags = [
        "workflows-agents",
        f"operation:{operation}",
        f"repo:{repo}",
        f"issue_or_pr:{issue_or_pr}",
        f"run_id:{run_id}",
    ]
    return {"metadata": metadata, "tags": tags}


def _invoke_llm_with_trace(
    llm: object,
    prompt: str,
    *,
    operation: str,
    pr_number: int | None = None,
) -> tuple[object, str | None, str | None]:
    """Invoke LLM and extract trace information.

    Returns:
        Tuple of (response, trace_id, trace_url)
    """
    config = _build_llm_config(operation=operation, pr_number=pr_number)

    try:
        response = llm.invoke(prompt, config=config)
    except TypeError:
        # Fallback if config not supported
        response = llm.invoke(prompt)

    # Extract trace ID from response if available
    trace_id = None
    trace_url = None
    try:
        from tools.llm_provider import derive_langsmith_trace_url, extract_trace_id

        trace_id = extract_trace_id(response)
        if trace_id:
            trace_url = derive_langsmith_trace_url(trace_id)
    except ImportError:
        pass

    return response, trace_id, trace_url


# ---------------------------------------------------------------------------
# Progress review with LLM
# ---------------------------------------------------------------------------


def review_progress_with_llm(
    acceptance_criteria: list[str],
    recent_commits: list[str],
    files_changed: list[str],
    rounds_without_completion: int,
    model: str = "gpt-4o-mini",
) -> ProgressReviewResult:
    """
    Use LLM to review agent progress and provide recommendation.
    """
    prompt = build_review_prompt(
        acceptance_criteria,
        recent_commits,
        files_changed,
        rounds_without_completion,
    )
    try:
        from tools.langchain_client import build_chat_client
    except ImportError:
        build_chat_client = None

    resolved = build_chat_client(model=model) if build_chat_client else None
    if not resolved:
        score, aligned, unaligned = heuristic_alignment_check(
            acceptance_criteria, recent_commits, files_changed
        )

        if score >= 6:
            rec = "CONTINUE"
            traj = "advancing"
        elif score >= 3:
            rec = "REDIRECT"
            traj = "plateau"
        else:
            rec = "STOP"
            traj = "diverging"

        return ProgressReviewResult(
            recommendation=rec,
            confidence=0.5,
            alignment_score=score,
            trajectory=traj,
            analysis=ProgressAnalysis(
                prep_work_identified=aligned[:5],
                scope_drift_identified=unaligned[:5],
            ),
            feedback_for_agent="Review your recent work against the acceptance criteria.",
            summary=(
                f"Heuristic review: {len(aligned)}/{len(recent_commits)} commits appear aligned"
            ),
            used_llm=False,
            error="LLM unavailable, using heuristic fallback",
        )

    try:
        import os

        pr_num = None
        env_pr = os.environ.get("PR_NUMBER", "")
        if env_pr.isdigit():
            pr_num = int(env_pr)

        llm = resolved.client
        response, trace_id, trace_url = _invoke_llm_with_trace(
            llm, prompt, operation="review_progress", pr_number=pr_num
        )
        content = response.content if hasattr(response, "content") else str(response)

        result = parse_llm_response(content)
        if result:
            result.used_llm = True
            result.provider_used = resolved.provider
            result.model = resolved.model
            result.langsmith_trace_id = trace_id
            result.langsmith_trace_url = trace_url
            return result

        # Failed to parse, return error result
        return ProgressReviewResult(
            recommendation="REDIRECT",
            confidence=0.3,
            alignment_score=5.0,
            trajectory="plateau",
            analysis=ProgressAnalysis(),
            feedback_for_agent="Unable to analyze progress. Please review acceptance criteria.",
            summary="LLM response parsing failed",
            used_llm=True,
            provider_used=resolved.provider,
            model=resolved.model,
            langsmith_trace_id=trace_id,
            langsmith_trace_url=trace_url,
            error="Failed to parse LLM response",
        )

    except Exception as e:
        # Fall back to heuristic on any error
        score, aligned, unaligned = heuristic_alignment_check(
            acceptance_criteria, recent_commits, files_changed
        )

        return ProgressReviewResult(
            recommendation="REDIRECT",
            confidence=0.4,
            alignment_score=score,
            trajectory="plateau",
            analysis=ProgressAnalysis(
                prep_work_identified=aligned[:5],
                scope_drift_identified=unaligned[:5],
            ),
            feedback_for_agent="Review your recent work against the acceptance criteria.",
            summary=f"LLM error, heuristic fallback: {len(aligned)}/{len(recent_commits)} aligned",
            used_llm=False,
            error=str(e),
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def review_progress(
    acceptance_criteria: list[str],
    recent_commits: list[str],
    files_changed: list[str],
    rounds_without_completion: int,
    use_llm: bool = True,
    model: str = "gpt-4o-mini",
) -> ProgressReviewResult:
    """
    Main entry point for progress review.

    Args:
        acceptance_criteria: List of acceptance criteria from the PR
        recent_commits: List of recent commit messages
        files_changed: List of files changed in recent commits
        rounds_without_completion: Number of rounds without task completion
        use_llm: Whether to use LLM for review
        model: LLM model to use

    Returns:
        ProgressReviewResult with recommendation and analysis
    """
    # Filter out orchestrator bookkeeping files (claude-prompt-*.md, etc.)
    # so they don't inflate alignment scores or file-change counts.
    files_changed = _filter_bookkeeping_files(files_changed)

    if not files_changed and rounds_without_completion >= 2:
        return ProgressReviewResult(
            recommendation="STOP",
            confidence=0.9,
            alignment_score=0.0,
            trajectory="diverging",
            analysis=ProgressAnalysis(
                blocking_issues=[
                    "Zero source files changed across multiple rounds",
                    "Likely infrastructure failure: auth, permissions, or sandbox",
                ],
            ),
            feedback_for_agent=(
                "No source files have been modified. This indicates an infrastructure "
                "issue (authentication, permissions, or sandbox configuration). "
                "Human intervention is required."
            ),
            summary=(
                f"Zero files changed for {rounds_without_completion} rounds — "
                "infrastructure failure, not scope drift"
            ),
            used_llm=False,
        )

    # Quick heuristic check first
    heuristic_score, aligned, unaligned = heuristic_alignment_check(
        acceptance_criteria, recent_commits, files_changed
    )

    # If clearly aligned or clearly not, skip LLM
    if heuristic_score >= 8 and rounds_without_completion < 12:
        return ProgressReviewResult(
            recommendation="CONTINUE",
            confidence=0.7,
            alignment_score=heuristic_score,
            trajectory="advancing",
            analysis=ProgressAnalysis(
                prep_work_identified=aligned[:5],
                scope_drift_identified=unaligned[:3],
            ),
            feedback_for_agent="Work appears aligned. Continue toward task completion.",
            summary=(
                f"Heuristic: {len(aligned)}/{len(recent_commits)} commits aligned with criteria"
            ),
            used_llm=False,
        )

    if heuristic_score <= 2 and rounds_without_completion >= 10:
        return ProgressReviewResult(
            recommendation="STOP",
            confidence=0.7,
            alignment_score=heuristic_score,
            trajectory="diverging",
            analysis=ProgressAnalysis(
                prep_work_identified=aligned[:3],
                scope_drift_identified=unaligned[:5],
            ),
            feedback_for_agent="Work appears unrelated to acceptance criteria. Please stop.",
            summary=f"Heuristic: Only {len(aligned)}/{len(recent_commits)} commits aligned",
            used_llm=False,
        )

    # Ambiguous case - use LLM if available
    if use_llm:
        return review_progress_with_llm(
            acceptance_criteria,
            recent_commits,
            files_changed,
            rounds_without_completion,
            model,
        )

    # No LLM, return heuristic result with REDIRECT
    rec = "CONTINUE" if heuristic_score >= 5 else "REDIRECT"
    return ProgressReviewResult(
        recommendation=rec,
        confidence=0.5,
        alignment_score=heuristic_score,
        trajectory="plateau",
        analysis=ProgressAnalysis(
            prep_work_identified=aligned[:5],
            scope_drift_identified=unaligned[:5],
        ),
        feedback_for_agent="Please verify your work aligns with acceptance criteria.",
        summary=f"Heuristic only: {len(aligned)}/{len(recent_commits)} commits appear aligned",
        used_llm=False,
    )


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Review agent progress against acceptance criteria"
    )
    parser.add_argument(
        "--acceptance-criteria",
        nargs="+",
        action="append",
        default=[],
        help="List of acceptance criteria (can be provided multiple times)",
    )
    parser.add_argument(
        "--recent-commits",
        nargs="+",
        action="append",
        default=[],
        help="List of recent commit messages (can be provided multiple times)",
    )
    parser.add_argument(
        "--files-changed",
        nargs="+",
        action="append",
        default=[],
        help="List of files changed (can be provided multiple times)",
    )
    parser.add_argument(
        "--rounds-without-completion",
        type=int,
        default=0,
        help="Number of rounds without task completion",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable LLM, use heuristics only",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="LLM model to use",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    args = parser.parse_args()

    acceptance_criteria = [item for group in args.acceptance_criteria for item in group]
    recent_commits = [item for group in args.recent_commits for item in group]
    files_changed = [item for group in args.files_changed for item in group]

    result = review_progress(
        acceptance_criteria=acceptance_criteria,
        recent_commits=recent_commits,
        files_changed=files_changed,
        rounds_without_completion=args.rounds_without_completion,
        use_llm=not args.no_llm,
        model=args.model,
    )

    if args.json:
        payload = build_review_payload(result)
        print(json.dumps(payload, indent=2))
    else:
        print(f"Recommendation: {result.recommendation}")
        print(f"Confidence: {result.confidence:.1%}")
        print(f"Alignment Score: {result.alignment_score:.1f}/10")
        print(f"Trajectory: {result.trajectory}")
        print(f"Summary: {result.summary}")
        if result.feedback_for_agent:
            print(f"\nFeedback for Agent:\n{result.feedback_for_agent}")
        if result.langsmith_trace_url:
            print(f"\n🔍 LangSmith Trace: {result.langsmith_trace_url}")

    # Exit code based on recommendation
    if result.recommendation == "STOP":
        return 2
    elif result.recommendation == "REDIRECT":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
