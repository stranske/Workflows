#!/usr/bin/env python3
"""Run the frozen verifier pilot against explicit provider/model candidates."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts import api_client
from scripts.langchain import pr_verifier

ROOT = Path(__file__).resolve().parent.parent


def _linked_issue_numbers(body: str, *, pr_number: int) -> list[int]:
    """Return issue references that state an explicit PR-to-issue relationship."""
    import re

    numbers = [
        int(match.group(1))
        for match in re.finditer(r"(?im)^\s*(?:closes|fixes|resolves|related to)\s+#(\d+)\b", body)
    ]
    return [number for number in dict.fromkeys(numbers) if number != pr_number]


def fetch_pr(repo: str, number: int, token: str) -> tuple[str, str]:
    payload = api_client.fetch_pull_request(repo, number, token)
    diff = api_client.fetch_pull_request_diff(repo, number, token)
    pr_body = str(payload.get("body") or "")
    source_issues: list[str] = []
    for issue_number in _linked_issue_numbers(pr_body, pr_number=number):
        issue = api_client.fetch_issue(repo, issue_number, token)
        disposition_comments = [
            str(comment.get("body") or "")
            for comment in api_client.fetch_issue_comments(repo, issue_number, token)
            if any(
                marker in str(comment.get("body") or "").casefold()
                for marker in ("verifier", "verify:compare", "disposition", "terminal")
            )
        ][-3:]
        source_issues.append(
            "\n".join(
                (
                    f"Source issue: #{issue_number} — {issue.get('title') or ''}",
                    str(issue.get("body") or ""),
                    "## Durable verifier/disposition context",
                    (
                        "\n\n---\n\n".join(disposition_comments)
                        if disposition_comments
                        else "No matching source-issue verifier or disposition comments were found."
                    ),
                )
            )
        )
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
            {"rows": 0, "agreement": 0, "false_pass": 0, "false_fail": 0, "schema_errors": 0},
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
    for candidate in candidates.values():
        candidate["latency_ms"] = round(candidate["latency_ms"], 3)
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
    """Return candidates that produced no schema-valid evaluation row."""
    if not report.get("results"):
        return ["<no-results>"]
    health: dict[tuple[str, str], bool] = {}
    for row in report.get("results", []):
        if not isinstance(row, dict):
            continue
        key = (str(row.get("provider", "")), str(row.get("model_id", "")))
        health[key] = health.get(key, False) or row.get("schema_valid") is True
    return [f"{provider}/{model}" for (provider, model), usable in health.items() if not usable]


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
    preflight = run_preflight(
        corpus,
        candidates,
        token=token,
    )
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
