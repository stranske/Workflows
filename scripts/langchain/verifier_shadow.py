#!/usr/bin/env python3
"""Shadow-run candidate verifier judges next to the production comparison (no effect on any verdict).

The reusable verifier workflow calls this after the production comparison has produced
``comparison.json`` and its unified verdict. For each candidate in ``config/verifier_shadow.json`` it
runs the production single-judge code path (``pr_verifier.evaluate_pr``) on the SAME context and diff
and writes one record to ``verifier-shadow.json``, which the workflow uploads with the comparison
artifacts. Nothing here posts a comment, sets a label, writes a step output or changes the exit
status: a failure of any candidate becomes an ``error`` field in the record. The records are read
back by ``tools/verifier_shadow_report.py``, which applies the pre-registered criteria.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = "workflows-verifier-shadow-record/v1"
CANDIDATE_TIMEOUT_SECONDS = 300


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _production_slots(comparison: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-judge verdicts of the production comparison, as the head-to-head baseline."""
    slots = []
    for result in comparison.get("results", []) or []:
        slots.append(
            {
                "provider": result.get("provider_used") or result.get("provider"),
                "model": result.get("model"),
                "verdict": result.get("verdict"),
                "used_llm": bool(result.get("used_llm")),
                "error": result.get("error"),
            }
        )
    return slots


def run_candidate(
    candidate: dict[str, Any],
    context: str,
    diff: str | None,
    evaluator: Callable[..., Any],
    *,
    timeout: int = CANDIDATE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """One candidate verdict; any failure is data, never an exception."""
    entry: dict[str, Any] = {
        "provider": candidate["provider"],
        "model": candidate["model"],
        "verdict": None,
        "used_llm": False,
        "error": None,
        "latency_s": None,
        "confidence": None,
        "concerns": None,
    }
    started = time.perf_counter()
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(
            evaluator, context, diff=diff, model=candidate["model"], provider=candidate["provider"]
        )
        result = future.result(timeout=timeout)
        entry.update(
            {
                "verdict": getattr(result, "verdict", None),
                "used_llm": bool(getattr(result, "used_llm", False)),
                "error": getattr(result, "error", None),
                "confidence": getattr(result, "confidence", None),
                "concerns": len(getattr(result, "concerns", []) or []),
            }
        )
    except concurrent.futures.TimeoutError:
        entry["error"] = f"timed out after {timeout}s"
    except Exception as exc:  # noqa: BLE001 - a candidate must never break the production run
        entry["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    entry["latency_s"] = round(time.perf_counter() - started, 2)
    return entry


def run_shadow(
    context: str,
    diff: str | None,
    comparison: dict[str, Any],
    config: dict[str, Any],
    *,
    production_verdict: str | None,
    evaluator: Callable[..., Any],
    meta: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """The shadow record for one verification. Disabled config or no candidates: an empty record."""
    slots = _production_slots(comparison)
    produced = {(s["provider"], s["model"]) for s in slots}
    candidates = []
    if config.get("enabled"):
        for candidate in config.get("candidates", []):
            if (candidate["provider"], candidate["model"]) in produced:
                continue  # never shadow a model that is already a production judge on this run
            candidates.append(run_candidate(candidate, context, diff, evaluator))
    return {
        "schema": SCHEMA,
        "recorded_at": (now or datetime.now(UTC)).isoformat(),
        "production_verdict": production_verdict,
        "production_slots": slots,
        "candidates": candidates,
        **(meta or {}),
    }


def _read(path: str | None) -> str | None:
    if not path or not Path(path).is_file():
        return None
    return Path(path).read_text(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context-file", required=True)
    parser.add_argument("--diff-file")
    parser.add_argument("--comparison", default="comparison.json")
    parser.add_argument("--config", default="config/verifier_shadow.json")
    parser.add_argument("--output", default="verifier-shadow.json")
    args = parser.parse_args(argv)
    try:
        config = load_config(Path(args.config))
        context = _read(args.context_file)
        if not context:
            raise ValueError("verifier context is missing or empty; no candidate was called")
        diff = _read(args.diff_file)
        comparison = json.loads(_read(args.comparison) or "{}")
        from scripts.langchain.pr_verifier import evaluate_pr

        record = run_shadow(
            context,
            diff,
            comparison,
            config,
            production_verdict=os.environ.get("PRODUCTION_VERDICT") or None,
            evaluator=evaluate_pr,
            meta={
                "repository": os.environ.get("GITHUB_REPOSITORY"),
                "run_id": os.environ.get("GITHUB_RUN_ID"),
                "pr_number": os.environ.get("PR_NUMBER"),
                "head_sha": os.environ.get("PR_HEAD_SHA"),
                "ci_failed": os.environ.get("CI_FAILED") == "true",
            },
        )
    except Exception as exc:  # noqa: BLE001 - shadow problems are logged, never raised
        record = {
            "schema": SCHEMA,
            "error": f"{type(exc).__name__}: {str(exc)[:200]}",
            "candidates": [],
        }
    Path(args.output).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"shadow: {len(record.get('candidates', []))} candidate verdict(s) recorded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
