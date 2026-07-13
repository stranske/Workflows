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


def fetch_pr(repo: str, number: int, token: str) -> tuple[str, str]:
    payload = api_client.fetch_pull_request(repo, number, token)
    diff = api_client.fetch_pull_request_diff(repo, number, token)
    context = f"Repository: {repo}\nPR: #{number}\nTitle: {payload['title']}\n\n{payload.get('body') or ''}"
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
    for candidate in candidates["candidates"]:
        provider = candidate["provider"]
        model = candidate["model_id"]
        for case in corpus["cases"]:
            started = time.perf_counter()
            try:
                context, diff = fetcher(case["repo"], case["pr"], token)
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
    }


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
    args = parser.parse_args()
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not token:
        raise SystemExit("GITHUB_TOKEN is required")
    payload = run_pilot(
        json.loads(args.corpus.read_text()),
        json.loads(args.candidates.read_text()),
        token=token,
    )
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
