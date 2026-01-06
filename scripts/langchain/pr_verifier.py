#!/usr/bin/env python3
"""
Evaluate pull requests with an LLM-backed rubric.

Run with:
    python scripts/langchain/pr_verifier.py --context-file verifier-context.md --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

PR_EVALUATION_PROMPT = """
You are reviewing a pull request to ensure it meets the documented acceptance criteria.

PR Context:
{context}

PR Diff (summary or full):
{diff}

Provide an evaluation that covers:
- correctness
- completeness
- quality
- testing
- risks

Respond in JSON with:
{
  "verdict": "PASS | CONCERNS | FAIL",
  "confidence": 0.0-1.0,
  "scores": {
    "correctness": 0-10,
    "completeness": 0-10,
    "quality": 0-10,
    "testing": 0-10,
    "risks": 0-10
  },
  "concerns": ["..."],
  "summary": "concise report"
}
""".strip()

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
    used_llm: bool = False
    raw_content: str | None = None
    error: str | None = None


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


def _get_llm_clients() -> list[tuple[object, str]]:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        return []

    github_token = os.environ.get("GITHUB_TOKEN")
    openai_token = os.environ.get("OPENAI_API_KEY")
    if not github_token and not openai_token:
        return []

    from tools.llm_provider import DEFAULT_MODEL, GITHUB_MODELS_BASE_URL

    clients: list[tuple[object, str]] = []
    if github_token:
        clients.append(
            (
                ChatOpenAI(
                    model=DEFAULT_MODEL,
                    base_url=GITHUB_MODELS_BASE_URL,
                    api_key=github_token,
                    temperature=0.1,
                ),
                "github-models",
            )
        )
    if openai_token:
        clients.append(
            (
                ChatOpenAI(
                    model=DEFAULT_MODEL,
                    api_key=openai_token,
                    temperature=0.1,
                ),
                "openai",
            )
        )
    return clients


@dataclass(frozen=True)
class ComparisonRunner:
    context: str
    diff: str | None
    prompt: str
    clients: list[tuple[object, str]]

    @classmethod
    def from_environment(cls, context: str, diff: str | None) -> ComparisonRunner:
        return cls(
            context=context,
            diff=diff,
            prompt=_prepare_prompt(context, diff),
            clients=_get_llm_clients(),
        )

    def run_single(self, client: object, provider: str) -> EvaluationResult:
        try:
            response = client.invoke(self.prompt)
        except Exception as exc:  # pragma: no cover - exercised in integration
            return _fallback_evaluation(f"LLM invocation failed: {exc}", provider=provider)

        content = getattr(response, "content", None) or str(response)
        return _parse_llm_response(content, provider)


def _prepare_prompt(context: str, diff: str | None) -> str:
    prompt = _load_prompt()
    diff_block = diff.strip() if diff and diff.strip() else "(diff unavailable)"
    context_block = context.strip() if context and context.strip() else "(context unavailable)"
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


def _should_create_issue(result: EvaluationResult) -> bool:
    return result.verdict in {"CONCERNS", "FAIL"}


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

    payload = json.dumps({"title": title, "body": body, "labels": labels}).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues",
        data=payload,
        method="POST",
    )
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("Content-Type", "application/json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")

    with urllib.request.urlopen(request) as response:
        data = json.loads(response.read().decode("utf-8"))
    issue_number = data.get("number")
    if isinstance(issue_number, int):
        return issue_number
    return None


def _fallback_evaluation(message: str, provider: str | None = None) -> EvaluationResult:
    return EvaluationResult(
        verdict="CONCERNS",
        scores=None,
        concerns=["LLM evaluation could not run."],
        summary="Review the PR manually or re-run once LLM credentials are available.",
        provider_used=provider,
        used_llm=False,
        error=message,
    )


def _extract_json_block(text: str) -> str | None:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def _parse_verdict(text: str) -> Literal["PASS", "CONCERNS", "FAIL"]:
    match = re.search(r"\b(PASS|CONCERNS|FAIL)\b", text, re.IGNORECASE)
    if match:
        return match.group(1).upper()  # type: ignore[return-value]
    return "CONCERNS"


def _parse_llm_response(content: str, provider: str) -> EvaluationResult:
    json_block = _extract_json_block(content)
    if json_block:
        try:
            payload = json.loads(json_block)
            return EvaluationResult.model_validate(
                {
                    **payload,
                    "provider_used": provider,
                    "used_llm": True,
                    "raw_content": content,
                }
            )
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            return EvaluationResult(
                verdict=_parse_verdict(content),
                scores=None,
                concerns=[],
                summary=content,
                provider_used=provider,
                used_llm=True,
                raw_content=content,
                error=f"Failed to parse JSON response: {exc}",
            )

    return EvaluationResult(
        verdict=_parse_verdict(content),
        scores=None,
        concerns=[],
        summary=content,
        provider_used=provider,
        used_llm=True,
        raw_content=content,
    )


def evaluate_pr(context: str, diff: str | None = None) -> EvaluationResult:
    resolved = _get_llm_client()
    if resolved is None:
        return _fallback_evaluation("LLM client unavailable (missing credentials or dependency).")

    client, provider = resolved
    prompt = _prepare_prompt(context, diff)
    try:
        response = client.invoke(prompt)
    except Exception as exc:  # pragma: no cover - exercised in integration
        return _fallback_evaluation(f"LLM invocation failed: {exc}")

    content = getattr(response, "content", None) or str(response)
    return _parse_llm_response(content, provider)


def evaluate_pr_multiple(context: str, diff: str | None = None) -> list[EvaluationResult]:
    runner = ComparisonRunner.from_environment(context, diff)
    if not runner.clients:
        return [_fallback_evaluation("LLM client unavailable (missing credentials or dependency).")]
    results: list[EvaluationResult] = []
    for client, provider in runner.clients:
        results.append(runner.run_single(client, provider))
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
    lines.append("| Provider | Verdict | Confidence | Summary |")
    lines.append("| --- | --- | --- | --- |")
    for index, result in enumerate(results):
        summary_source = result.summary or result.raw_content or ""
        summary = _compact_text(summary_source) if summary_source else "N/A"
        lines.append(
            f"| {labels[index]} | {result.verdict} | {_format_confidence(result.confidence)} | {summary} |"
        )
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
                insights = [_compact_text(summary)]
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
        results = evaluate_pr_multiple(context, diff=diff)
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

    result = evaluate_pr(context, diff=diff)
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
