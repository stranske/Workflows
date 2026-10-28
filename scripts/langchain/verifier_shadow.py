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
PIPELINE = "compare-slot/v2"


def evaluate_like_production(
    context: str, diff: str | None = None, model: str | None = None, provider: str | None = None
) -> Any:
    """Judge one PR exactly as ONE production compare slot does.

    ``pr_verifier.evaluate_pr`` uses a lenient coverage rule (``evaluate_minimum=True``) that the
    production comparison does not, so candidates run through it answered an easier question than the
    incumbent (a candidate PASS where production said UNVERIFIABLE_INPUT). Production runs
    ``ComparisonRunner.run_single`` per slot: strict coverage, chunked review, coverage floor.
    """
    from scripts.langchain import pr_verifier as pv

    resolved = pv._get_llm_client(model=model, provider=provider)
    coverage = pv.prompt_coverage(context, diff)
    if resolved is None:
        return pv._apply_coverage_floor(
            pv._fallback_evaluation("LLM client unavailable (missing credentials or dependency)."),
            coverage,
        )
    client, provider_name = resolved
    runner = pv.ComparisonRunner(
        context=context,
        diff=diff,
        prompt=pv._prepare_prompt(context, diff),
        clients=[(client, provider_name, model or "")],
        coverage=coverage,
    )
    return runner.run_single(client, provider_name, model or "")


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
        "pipeline": PIPELINE,
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
        if entry["error"]:  # keep what the model said, to tell a bad schema from a harness fault
            entry["raw_excerpt"] = str(getattr(result, "raw_content", "") or "")[:400]
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
        # never shadow a model that is already a production judge on this run
        todo = [
            c
            for c in config.get("candidates", [])
            if (c["provider"], c["model"]) not in produced and c.get("runner") != "external"
        ]  # external candidates are judged later by tools/verifier_shadow_external.py
        # all candidates judge at once, so the step costs one candidate's latency, not their sum
        if todo:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(todo), 12)) as pool:
                futures = [pool.submit(run_candidate, c, context, diff, evaluator) for c in todo]
                candidates = [
                    f.result() for f in futures
                ]  # config order; run_candidate never raises
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
        record = run_shadow(
            context,
            diff,
            comparison,
            config,
            production_verdict=os.environ.get("PRODUCTION_VERDICT") or None,
            evaluator=evaluate_like_production,
            meta={
                "repository": os.environ.get("GITHUB_REPOSITORY"),
                "run_id": os.environ.get("GITHUB_RUN_ID"),
                "pr_number": os.environ.get("PR_NUMBER"),
                "head_sha": os.environ.get("PR_HEAD_SHA"),
                "ci_failed": os.environ.get("CI_FAILED") == "true",
                # production used the semantic package matrix for this run (expanded profile), which
                # the single-prompt slot path below cannot reproduce; the report excludes such runs
                "semantic_mode": os.environ.get("VERIFIER_SEMANTIC_MODE") == "1",
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
