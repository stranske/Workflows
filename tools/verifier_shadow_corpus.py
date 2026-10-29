#!/usr/bin/env python3
"""Run every verifier judge -- the production pair and every shadow candidate -- on the labelled corpus.

The daily shadow waits for live verifications, and the saved inputs of those expire after 7 days. The
frozen verifier corpus (``config/model_eval_pilot.json``) already holds the production inputs of real
merged PRs from several repositories, each with an independently adjudicated label (PASS or NON_PASS;
a few NON_PASS cases are controlled defects). This tool gives all judges the SAME production prompt
for each case at once, then the daily job's blind adjudicator rates every evaluation, so the
candidates can be graded on a whole sample in one dispatch instead of over weeks.

It reuses the shadow's code paths unchanged: in-workflow judges run the production compare slot
(``scripts/langchain/verifier_shadow.py``), external judges the saved-input path
(``tools/verifier_shadow_external.py``), and ratings come from ``tools/verifier_shadow_adjudicate.py``.
The report applies the same criteria as the daily report (no window, since the sample is fixed) and
adds each judge's agreement with the corpus label. Records are kept apart from the daily ledger:
this is a trial on recorded work, not production use. Nothing posts, labels or promotes.
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

from scripts.langchain.verifier_shadow import (
    SCHEMA,
    evaluate_like_production,
    run_candidate,
)
from tools.verifier_shadow_adjudicate import RUN_RESERVE_SECONDS, adjudicate, make_client
from tools.verifier_shadow_external import (
    RUN_BUDGET_SECONDS,
    external_candidates,
    gh_is_public,
    run_external,
)
from tools.verifier_shadow_report import FINDINGS, PASS, _valid, evaluate_candidate

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "config/model_eval_pilot.json"
# a corpus input is a whole production capture, often longer than a live run's
JUDGE_TIMEOUT_SECONDS = 600
CASE_RESERVE_SECONDS = JUDGE_TIMEOUT_SECONDS + RUN_BUDGET_SECONDS + RUN_RESERVE_SECONDS


def production_judges() -> list[dict[str, str]]:
    """The production compare pair, resolved from the registry exactly as the verifier resolves it."""
    from tools.llm_registry import load_slot_config

    return [
        {"provider": s.provider, "model": s.model}
        for s in load_slot_config()
        if s.provider in ("openai", "anthropic")
    ]


def corpus_cases(path: Path = CORPUS) -> list[dict[str, Any]]:
    """Every non-diagnostic labelled case with a production input snapshot, in corpus order."""
    from tools.generate_mutation_cases import coverage_sufficient
    from tools.run_judge_backend_screen import corpus_cases_with_snapshots

    cases = corpus_cases_with_snapshots(json.loads(path.read_text(encoding="utf-8")), ROOT)
    for case in cases:
        case["evaluable"] = bool(coverage_sufficient(case["production_snapshot"]))
    return cases


def case_inputs(case: dict[str, Any]) -> tuple[str, str | None]:
    snapshot = case["production_snapshot"]
    return snapshot["context"], snapshot.get("diff", snapshot.get("diff_summary"))


def comparison_of(production: list[dict[str, Any]]) -> dict[str, Any]:
    """The production entries in the ``comparison.json`` shape the adjudicator reads."""
    return {
        "results": [
            {
                "provider_used": e["provider"],
                "model": e["model"],
                "verdict": e.get("verdict"),
                "used_llm": e.get("used_llm"),
                "error": e.get("error"),
                **(e.get("review") or {}),
            }
            for e in production
        ]
    }


def judge_case(
    case: dict[str, Any],
    production: list[dict[str, str]],
    config: dict[str, Any],
    *,
    evaluator: Callable[..., Any] = evaluate_like_production,
    externals: Callable[..., list[dict[str, Any]]] = run_external,
    is_public: Callable[[str], bool] = gh_is_public,
) -> dict[str, Any]:
    """One record: every judge on the case's production prompt. A failing judge is data."""
    context, diff = case_inputs(case)
    snapshot = case["production_snapshot"]
    produced = {(p["provider"], p["model"]) for p in production}
    inside = [
        c
        for c in config.get("candidates", [])
        if c.get("runner") != "external" and (c["provider"], c["model"]) not in produced
    ]
    previous = os.environ.get("CHAIN_DEPTH")
    os.environ["CHAIN_DEPTH"] = str(snapshot.get("chain_depth", 0))  # the prompt reads it per case
    try:
        judges = production + inside
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(judges)) as pool:
            futures = [
                pool.submit(
                    run_candidate, j, context, diff, evaluator, timeout=JUDGE_TIMEOUT_SECONDS
                )
                for j in judges
            ]
            entries = [f.result() for f in futures]
        outside = external_candidates(config)
        if outside and is_public(case["repo"]):
            entries += externals(outside, context, diff)
        else:  # the external tiers may only see public repositories
            entries += [
                {**_empty(c), "external": True, "error": "skipped: private repository"}
                for c in outside
            ]
    finally:
        if previous is None:
            os.environ.pop("CHAIN_DEPTH", None)
        else:
            os.environ["CHAIN_DEPTH"] = previous
    return {
        "schema": SCHEMA,
        "recorded_at": datetime.now(UTC).isoformat(),
        "repository": case["repo"],
        "pr_number": case["pr"],
        "run_id": f"corpus-{case['case_id']}",
        "corpus": {
            "case_id": case["case_id"],
            "expected_verdict": case["expected_verdict"],
            "category": case["category"],
            "input_kind": snapshot.get("input_kind"),
            "evaluable": case.get("evaluable"),
        },
        "production_slots": entries[: len(production)],
        "candidates": entries[len(production) :],
    }


def _empty(candidate: dict[str, Any]) -> dict[str, Any]:
    from scripts.langchain.verifier_shadow import PIPELINE

    return {
        "provider": candidate["provider"],
        "model": candidate["model"],
        "verdict": None,
        "used_llm": False,
        "pipeline": PIPELINE,
    }


def run_corpus(
    cases: list[dict[str, Any]],
    records: list[dict[str, Any]],
    config: dict[str, Any],
    *,
    production: list[dict[str, str]],
    judge: Callable[..., dict[str, Any]] = judge_case,
    client_factory: Callable[[dict[str, str]], Any] = make_client,
    deadline: float | None = None,
    checkpoint: Callable[[], None] | None = None,
) -> dict[str, int]:
    """Judge and adjudicate each case not already in ``records``; resumable through ``checkpoint``."""
    done = {
        r["corpus"]["case_id"]
        for r in records
        if r.get("adjudication") and not r["adjudication"].get("error")
    }
    counts = {"judged": 0, "adjudicated": 0, "failed": 0, "already_done": 0, "out_of_time": 0}
    client = None
    for case in cases:
        if case["case_id"] in done:
            counts["already_done"] += 1
            continue
        if deadline is not None and time.monotonic() + CASE_RESERVE_SECONDS > deadline:
            counts["out_of_time"] += 1
            continue
        record = next((r for r in records if r["corpus"]["case_id"] == case["case_id"]), None)
        if record is None:  # a record whose adjudication failed is re-adjudicated, not re-judged
            record = judge(case, production, config)
            records.append(record)
            counts["judged"] += 1
            if checkpoint is not None:
                checkpoint()
        context, diff = case_inputs(case)
        client = client or client_factory(config["adjudicator"])
        record["adjudication"] = adjudicate(
            record,
            context,
            diff,
            comparison_of(record["production_slots"]),
            client,
            config["adjudicator"],
        )
        counts["failed" if record["adjudication"].get("error") else "adjudicated"] += 1
        if checkpoint is not None:
            checkpoint()
    return counts


def label_agreement(records: list[dict[str, Any]], key: tuple[str, str]) -> dict[str, Any]:
    """How one judge's verdicts line up with the corpus labels (a check, not a grade)."""
    n = passes = false_pass = missed_pass = unverifiable = 0
    for record in records:
        entry = next(
            (
                e
                for e in record["production_slots"] + record["candidates"]
                if (e["provider"], e["model"]) == key
            ),
            None,
        )
        if entry is None or not _valid(entry):
            continue
        n += 1
        expected = record["corpus"]["expected_verdict"]
        verdict = entry["verdict"]
        passes += expected == PASS
        false_pass += expected != PASS and verdict == PASS
        missed_pass += expected == PASS and verdict in FINDINGS
        unverifiable += verdict == "UNVERIFIABLE_INPUT"
    return {
        "usable": n,
        "label_pass": passes,
        "label_non_pass": n - passes,
        "false_pass": false_pass,
        "finding_on_pass_label": missed_pass,
        "unverifiable": unverifiable,
    }


def report(records: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    # a fixed sample has no time window; the minimum number of adjudicated cases still applies
    fixed = {**config, "window": {**config["window"], "min_days": 0, "max_days": 1}}
    now = datetime.now(UTC)
    production = [
        (e["provider"], e["model"]) for e in (records[0]["production_slots"] if records else [])
    ]
    return {
        "generated_at": now.isoformat(),
        "cases": len(records),
        "adjudicated": sum(
            1 for r in records if r.get("adjudication") and not r["adjudication"].get("error")
        ),
        "repositories": sorted({r["repository"] for r in records}),
        "candidates": [
            evaluate_candidate(records, c, fixed, now=now, started_at=now)
            for c in config.get("candidates", [])
        ],
        "labels": {
            f"{'production' if key in production else 'candidate'}:{key[0]}:{key[1]}": label_agreement(
                records, key
            )
            for key in production
            + [(c["provider"], c["model"]) for c in config.get("candidates", [])]
        },
    }


def markdown(result: dict[str, Any]) -> str:
    lines = [
        "## Verifier shadow corpus trial",
        "",
        f"Generated {result['generated_at']}: {result['cases']} labelled corpus case(s) from "
        f"{', '.join(result['repositories'])}; {result['adjudicated']} adjudicated. Every judge saw the "
        "same production prompt for each case. Evidence class: a trial on recorded production inputs "
        "with independent labels, not production use. Same criteria as the daily report, without the "
        "time window.",
        "",
        "| Candidate | Status | Adjudicated | Inaccurate (vs production) | Coverage (vs production) "
        "| Usefulness (vs production) | Warnings | Failed criteria |",
        "|---|---|---:|---|---|---|---:|---|",
    ]
    for c in result["candidates"]:
        lines.append(
            f"| {c['candidate']} | **{c['status']}** | {c['adjudicated_runs']} | "
            f"{c['inaccurate_share']} ({c['incumbent_inaccurate_share']}) | "
            f"{c['criteria_coverage']} ({c['incumbent_criteria_coverage']}) | "
            f"{c['usefulness']} ({c['incumbent_usefulness']}) | {len(c['warnings'])} | "
            f"{', '.join(c['failed_criteria']) or 'none'} |"
        )
    lines += [
        "",
        "### Agreement with the corpus labels",
        "",
        "| Judge | Usable | PASS labels | NON_PASS labels | PASS on a NON_PASS label "
        "| Finding on a PASS label | UNVERIFIABLE_INPUT |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for key, a in result["labels"].items():
        lines.append(
            f"| {key} | {a['usable']} | {a['label_pass']} | {a['label_non_pass']} | "
            f"{a['false_pass']} | {a['finding_on_pass_label']} | {a['unverifiable']} |"
        )
    lines.append("")
    for c in result["candidates"]:
        lines += [
            f"- inaccurate: {c['candidate']}: {r['run']}: {'; '.join(e for e in r['errors'] if e)}"
            for r in c["inaccurate_runs"]
        ]
    return "\n".join(lines) + "\n"


def _save(path: Path, records: list[dict[str, Any]]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(records, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="judge and adjudicate one shard of the corpus")
    run.add_argument("--records", type=Path, required=True)
    run.add_argument("--shard", type=int, default=0)
    run.add_argument("--shards", type=int, default=1)
    run.add_argument("--max-cases", type=int, default=None)
    run.add_argument("--budget-seconds", type=float, default=None)
    rep = sub.add_parser("report", help="merge shard records and write the report")
    rep.add_argument("records", type=Path, nargs="+")
    rep.add_argument("--markdown", type=Path, required=True)
    rep.add_argument("--json", type=Path, required=True)
    for p in (run, rep):
        p.add_argument("--config", type=Path, default=ROOT / "config/verifier_shadow.json")
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))

    if args.command == "report":
        records = [r for path in args.records for r in json.loads(path.read_text(encoding="utf-8"))]
        result = report(records, config)
        args.json.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
        args.markdown.write_text(markdown(result), encoding="utf-8")
        print(markdown(result))
        return 0

    started = time.monotonic()
    cases = corpus_cases()[args.shard :: args.shards][: args.max_cases]
    records = json.loads(args.records.read_text()) if args.records.exists() else []
    counts = run_corpus(
        cases,
        records,
        config,
        production=production_judges(),
        deadline=None if args.budget_seconds is None else started + args.budget_seconds,
        checkpoint=lambda: _save(args.records, records),
    )
    _save(args.records, records)
    print(f"corpus shard {args.shard}/{args.shards}: {len(cases)} case(s): {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
