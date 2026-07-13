#!/usr/bin/env python3
"""Run the frozen verifier pilot against explicit provider/model candidates."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts import api_client
from scripts.langchain import pr_verifier
from scripts.langchain.injection_guard import check_prompt_injection

ROOT = Path(__file__).resolve().parent.parent
MAX_LINKED_ISSUE_BODY_CHARS = 4_000
MAX_LINKED_ISSUE_COMMENT_CHARS = 1_200
MAX_LINKED_ISSUE_CONTEXT_CHARS = 8_000


def _linked_issue_numbers(body: str, *, pr_number: int) -> list[int]:
    """Return issue references that state an explicit PR-to-issue relationship."""
    numbers = [
        int(match.group(1))
        for match in re.finditer(
            r"(?i)\b(?:closes|fixes|resolves|related to)\s*:?\s+#(\d+)\b", body
        )
    ]
    return [number for number in dict.fromkeys(numbers) if number != pr_number]


def _bounded_linked_issue_text(value: object, *, limit: int) -> str:
    """Keep untrusted linked-issue text safe and bounded for verifier context."""
    text = str(value or "").strip()
    guard = check_prompt_injection(text)
    if guard["blocked"]:
        return f"[linked issue text omitted by prompt-injection guard: {guard['code']}]"
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n[truncated linked issue context]"


def fetch_pr(repo: str, number: int, token: str) -> tuple[str, str]:
    payload = api_client.fetch_pull_request(repo, number, token)
    diff = api_client.fetch_pull_request_diff(repo, number, token)
    pr_body = str(payload.get("body") or "")
    source_issues: list[str] = []
    remaining_context = MAX_LINKED_ISSUE_CONTEXT_CHARS
    for issue_number in _linked_issue_numbers(pr_body, pr_number=number):
        if remaining_context <= 0:
            break
        try:
            issue = api_client.fetch_issue(repo, issue_number, token)
            disposition_comments = [
                _bounded_linked_issue_text(
                    comment.get("body"), limit=MAX_LINKED_ISSUE_COMMENT_CHARS
                )
                for comment in api_client.fetch_issue_comments(repo, issue_number, token)
                if any(
                    marker in str(comment.get("body") or "").casefold()
                    for marker in ("verifier", "verify:compare", "disposition", "terminal")
                )
            ][-3:]
            source_issue = "\n".join(
                (
                    "Source issue: "
                    f"#{issue_number} — "
                    + _bounded_linked_issue_text(issue.get("title"), limit=300),
                    _bounded_linked_issue_text(
                        issue.get("body"), limit=MAX_LINKED_ISSUE_BODY_CHARS
                    ),
                    "## Durable verifier/disposition context",
                    (
                        "\n\n---\n\n".join(disposition_comments)
                        if disposition_comments
                        else "No matching source-issue verifier or disposition comments were found."
                    ),
                )
            )
        except Exception as exc:
            print(f"pilot: skipping linked issue #{issue_number}: {exc}", file=sys.stderr)
            continue
        source_issues.append(source_issue[:remaining_context])
        remaining_context -= len(source_issues[-1])
    context = "\n\n".join(
        part
        for part in (
            f"Repository: {repo}\nPR: #{number}\nTitle: {payload['title']}\n\n{pr_body}",
            (
                "## Linked source issues\n\n" + "\n\n---\n\n".join(source_issues)
                if source_issues
                else ""
            ),
        )
        if part
    )
    return context, diff


def run_pilot(
    corpus: dict[str, Any],
    candidates: dict[str, Any],
    *,
    token: str,
    fetcher: Callable[[str, int, str], tuple[str, str]] = fetch_pr,
    evaluator: Callable[..., Any] = pr_verifier.evaluate_pr,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    prepared_cases: dict[str, tuple[str, str] | Exception] = {}
    for case in corpus["cases"]:
        case_id = str(case["case_id"])
        try:
            prepared_cases[case_id] = fetcher(case["repo"], case["pr"], token)
        except Exception as exc:  # preserve a shared GitHub read failure for every candidate
            prepared_cases[case_id] = exc
    for candidate in candidates["candidates"]:
        provider = candidate["provider"]
        model = candidate["model_id"]
        for case in corpus["cases"]:
            started = time.perf_counter()
            try:
                prepared = prepared_cases[str(case["case_id"])]
                if isinstance(prepared, Exception):
                    raise prepared
                context, diff = prepared
                result = evaluator(context, diff=diff, model=model, provider=provider)
                actual = "PASS" if result.verdict == "PASS" else "NON_PASS"
                row = {
                    "case_id": case["case_id"],
                    "category": case["category"],
                    "expected_verdict": case["expected_verdict"],
                    "actual_verdict": actual,
                    "schema_valid": result.error is None,
                    "provider": provider,
                    "model_id": model,
                    "confidence": result.confidence,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                    "error": result.error,
                }
            except Exception as exc:  # keep the paired run auditable
                row = {
                    "case_id": case["case_id"],
                    "category": case["category"],
                    "expected_verdict": case["expected_verdict"],
                    "actual_verdict": "NON_PASS",
                    "schema_valid": False,
                    "provider": provider,
                    "model_id": model,
                    "confidence": 0,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                    "error": str(exc),
                }
            results.append(row)
    return {
        "schema": "workflows-verifier-pilot-results/v1",
        "corpus_version": corpus["corpus_version"],
        "results": results,
        "summary": summarize_results(results),
    }


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Produce durable, category-level evidence without selecting a model."""
    candidates: dict[str, dict[str, Any]] = {}
    for row in results:
        candidate_key = f"{row['provider']}/{row['model_id']}"
        candidate = candidates.setdefault(
            candidate_key,
            {
                "provider": row["provider"],
                "model_id": row["model_id"],
                "rows": 0,
                "schema_errors": 0,
                "latency_ms": 0.0,
                "categories": {},
            },
        )
        category = candidate["categories"].setdefault(
            row["category"],
            {
                "rows": 0,
                "agreement": 0,
                "false_pass": 0,
                "false_fail": 0,
                "schema_errors": 0,
                "latency_ms": 0.0,
            },
        )
        expected = row["expected_verdict"]
        actual = row["actual_verdict"]
        schema_valid = row["schema_valid"] is True
        candidate["rows"] += 1
        candidate["schema_errors"] += int(not schema_valid)
        candidate["latency_ms"] += float(row["latency_ms"])
        category["rows"] += 1
        category["agreement"] += int(schema_valid and expected == actual)
        category["false_pass"] += int(expected == "NON_PASS" and actual == "PASS")
        category["false_fail"] += int(expected == "PASS" and actual == "NON_PASS")
        category["schema_errors"] += int(not schema_valid)
        category["latency_ms"] += float(row["latency_ms"])
    for candidate in candidates.values():
        candidate["latency_ms"] = round(candidate["latency_ms"], 3)
        for category in candidate["categories"].values():
            category["latency_ms"] = round(category["latency_ms"], 3)
    return {"candidates": list(candidates.values())}


def run_preflight(
    corpus: dict[str, Any],
    candidates: dict[str, Any],
    *,
    token: str,
    fetcher: Callable[[str, int, str], tuple[str, str]] = fetch_pr,
    evaluator: Callable[..., Any] = pr_verifier.evaluate_pr,
) -> dict[str, Any]:
    """Run one representative case per candidate before the full paired pilot."""
    cases = corpus.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("pilot corpus requires at least one case for preflight")
    preflight_corpus = {**corpus, "cases": [cases[0]]}
    report = run_pilot(
        preflight_corpus,
        candidates,
        token=token,
        fetcher=fetcher,
        evaluator=evaluator,
    )
    report["stage"] = "candidate-preflight"
    return report


def unusable_candidates(report: dict[str, Any]) -> list[str]:
    """Return candidates without a schema-valid row for every corpus case."""
    results = [row for row in report.get("results", []) if isinstance(row, dict)]
    if not results:
        return ["<no-results>"]
    expected_case_ids = {str(row.get("case_id", "")) for row in results}
    valid_case_ids: dict[tuple[str, str], set[str]] = {}
    candidates: set[tuple[str, str]] = set()
    for row in results:
        key = (str(row.get("provider", "")), str(row.get("model_id", "")))
        candidates.add(key)
        if row.get("schema_valid") is True:
            valid_case_ids.setdefault(key, set()).add(str(row.get("case_id", "")))
    return [
        f"{provider}/{model}"
        for provider, model in sorted(candidates)
        if valid_case_ids.get((provider, model), set()) != expected_case_ids
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=ROOT / "config/model_eval_pilot.json")
    parser.add_argument(
        "--candidates", type=Path, default=ROOT / "config/model_eval_candidates.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preflight-output", type=Path)
    args = parser.parse_args()
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not token:
        raise SystemExit("GITHUB_TOKEN is required")
    corpus = json.loads(args.corpus.read_text())
    candidates = json.loads(args.candidates.read_text())
    try:
        preflight = run_preflight(
            corpus,
            candidates,
            token=token,
        )
    except ValueError as exc:
        print(f"pilot preflight error: {exc}", file=sys.stderr)
        return 1
    preflight_output = args.preflight_output or args.output.with_name("pilot-preflight.json")
    preflight_output.write_text(json.dumps(preflight, indent=2) + "\n")
    unusable = unusable_candidates(preflight)
    if unusable:
        print(
            "pilot preflight error: candidates produced no schema-valid rows: "
            + ", ".join(unusable),
            file=sys.stderr,
        )
        return 1
    payload = run_pilot(corpus, candidates, token=token)
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    unusable = unusable_candidates(payload)
    if unusable:
        print(
            "pilot error: candidates produced no schema-valid rows: " + ", ".join(unusable),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
