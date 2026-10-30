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
from tools.verifier_shadow_adjudicate import (
    RUN_RESERVE_SECONDS,
    _json_object,
    adjudicate,
    blind,
    build_prompt,
    evaluators_for,
    make_client,
    validate,
)
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
    """Every non-diagnostic labelled case the production prompt can judge, in corpus order.

    On a snapshot that fails the production coverage check, the verifier answers
    UNVERIFIABLE_INPUT without calling any model, for every judge alike (2026-10-29: 44 of 62
    cases), so those cases cost a dispatch and measure nothing about a judge.
    """
    from tools.generate_mutation_cases import coverage_sufficient
    from tools.run_judge_backend_screen import corpus_cases_with_snapshots

    cases = corpus_cases_with_snapshots(json.loads(path.read_text(encoding="utf-8")), ROOT)
    for case in cases:
        case["evaluable"] = bool(coverage_sufficient(case["production_snapshot"]))
    return [case for case in cases if case["evaluable"]]


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
        entries = []
        if judges:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(judges)) as pool:
                futures = [
                    pool.submit(
                        run_candidate, j, context, diff, evaluator, timeout=JUDGE_TIMEOUT_SECONDS
                    )
                    for j in judges
                ]
                entries = [f.result() for f in futures]
        outside = external_candidates(config, corpus=True)
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


def _judge_key(entry: dict[str, Any]) -> tuple[str, str]:
    return entry["provider"], entry["model"]


def _reconcile_judges(
    record: dict[str, Any], production: list[dict[str, str]], config: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Retain matching judgments; ratings cover only the exact evaluator set they saw."""
    produced = {_judge_key(p) for p in production}
    candidates = [
        c
        for c in config.get("candidates", [])
        if c.get("runner") != "external" and _judge_key(c) not in produced
    ] + external_candidates(config, corpus=True)
    missing = []
    changed = False
    for slot, requested in (("production_slots", production), ("candidates", candidates)):
        previous = record.get(slot, [])
        by_key = {_judge_key(e): e for e in previous}
        retained = [by_key[_judge_key(j)] for j in requested if _judge_key(j) in by_key]
        absent = [j for j in requested if _judge_key(j) not in by_key]
        changed = changed or bool(absent) or retained != previous
        record[slot] = retained
        missing.append(absent)
    if changed:
        record.pop("adjudication", None)
    return missing[0], missing[1], changed


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
    adjudicate_here: bool = True,
) -> dict[str, int]:
    """Judge and adjudicate each case not already in ``records``; resumable through ``checkpoint``.

    ``adjudicate_here=False`` only judges: the ratings then come from a Claude Code session
    (``prompts`` / ``apply``) instead of a paid API call per case.
    """
    counts = {
        "judged": 0,
        "adjudicated": 0,
        "failed": 0,
        "already_done": 0,
        "out_of_time": 0,
        "awaiting_session_adjudication": 0,
    }
    client = None
    for case in cases:
        record = next((r for r in records if r["corpus"]["case_id"] == case["case_id"]), None)
        missing_production, missing_candidates = production, config.get("candidates", [])
        if record is not None:
            missing_production, missing_candidates, changed = _reconcile_judges(
                record, production, config
            )
            if changed and checkpoint is not None:
                checkpoint()
        complete = record is not None and not missing_production and not missing_candidates
        if complete and record.get("adjudication") and not record["adjudication"].get("error"):
            counts["already_done"] += 1
            continue
        if not adjudicate_here and complete:
            counts["awaiting_session_adjudication"] += 1
            continue
        if deadline is not None and time.monotonic() + CASE_RESERVE_SECONDS > deadline:
            counts["out_of_time"] += 1
            continue
        if record is None:
            record = judge(case, production, config)
            records.append(record)
        elif not complete:
            fresh = judge(case, missing_production, {**config, "candidates": missing_candidates})
            for slot in ("production_slots", "candidates"):
                record[slot].extend(fresh[slot])
            # Restore requested ordering after appending the new judgments.
            _reconcile_judges(record, production, config)
            record["recorded_at"] = fresh["recorded_at"]
        if not complete:
            counts["judged"] += 1
            if checkpoint is not None:
                checkpoint()
        if not adjudicate_here:
            counts["awaiting_session_adjudication"] += 1
            continue
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


def blind_prompt(record: dict[str, Any], case: dict[str, Any]) -> tuple[str, list]:
    """The adjudicator's prompt for one case, with the same blinding and order as the API path."""
    context, diff = case_inputs(case)
    evaluators = evaluators_for(record, comparison_of(record["production_slots"]))
    labelled = blind(evaluators, f"{record.get('repository')}:{record.get('run_id')}")
    return build_prompt(context, diff, labelled), labelled


def write_prompts(records: list[dict[str, Any]], cases: list[dict[str, Any]], out: Path) -> int:
    """One blind prompt file per case still needing ratings; the label key never leaves this tool."""
    by_id = {c["case_id"]: c for c in cases}
    out.mkdir(parents=True, exist_ok=True)
    written = 0
    for record in records:
        case = by_id.get(record["corpus"]["case_id"])
        adjudication = record.get("adjudication") or {}
        if case is None or (adjudication and not adjudication.get("error")):
            continue
        prompt, labelled = blind_prompt(record, case)
        if not any(key.startswith("candidate:") for _, key, _ in labelled):
            continue
        (out / f"{case['case_id']}.txt").write_text(prompt, encoding="utf-8")
        written += 1
    return written


def apply_answers(
    records: list[dict[str, Any]], cases: list[dict[str, Any]], answers: Path, adjudicator: str
) -> dict[str, int]:
    """Validate each session answer exactly as an API answer is validated, and store it."""
    by_id = {c["case_id"]: c for c in cases}
    counts = {"applied": 0, "rejected": 0, "missing": 0}
    for record in records:
        case = by_id.get(record["corpus"]["case_id"])
        if case is None or (record.get("adjudication") and not record["adjudication"].get("error")):
            continue
        path = answers / f"{case['case_id']}.json"
        if not path.exists():
            counts["missing"] += 1
            continue
        context, diff = case_inputs(case)
        _, labelled = blind_prompt(record, case)
        base = {
            "provider": "claude-code-session",
            "model": adjudicator,
            "adjudicated_at": datetime.now(UTC).isoformat(),
            "error": None,
        }
        answer = _json_object(path.read_text(encoding="utf-8"))
        try:
            if answer is None:
                raise ValueError("answer is not a JSON object")
            record["adjudication"] = {**base, **validate(answer, labelled, context, diff)}
            counts["applied"] += 1
        except (TypeError, ValueError, AttributeError, KeyError) as exc:
            record["adjudication"] = {**base, "error": f"malformed session answer: {exc}"}
            counts["rejected"] += 1
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


def one_per_case(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One record per corpus case: a successful adjudication first, then the newest."""

    def rank(record: dict[str, Any]) -> tuple[bool, str]:
        adjudication = record.get("adjudication") or {}
        return (bool(adjudication) and not adjudication.get("error"), record.get("recorded_at", ""))

    best: dict[str, dict[str, Any]] = {}
    for record in records:
        key = record["corpus"]["case_id"]
        if key not in best or rank(record) > rank(best[key]):
            best[key] = record
    return list(best.values())


def report(records: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    records = one_per_case(records)
    # a fixed sample has no time window; the minimum number of adjudicated cases still applies
    fixed = {**config, "window": {**config["window"], "min_days": 0, "max_days": 1}}
    now = datetime.now(UTC)
    production = [
        (e["provider"], e["model"]) for e in (records[0]["production_slots"] if records else [])
    ]
    judged = {(e["provider"], e["model"]) for r in records for e in r["candidates"]}
    # a trial of selected candidates reports only those, not every candidate in the config
    candidates = [c for c in config.get("candidates", []) if (c["provider"], c["model"]) in judged]
    return {
        "generated_at": now.isoformat(),
        "cases": len(records),
        "adjudicated": sum(
            1 for r in records if r.get("adjudication") and not r["adjudication"].get("error")
        ),
        "repositories": sorted({r["repository"] for r in records}),
        "candidates": [
            evaluate_candidate(records, c, fixed, now=now, started_at=now) for c in candidates
        ],
        "labels": {
            f"{'production' if key in production else 'candidate'}:{key[0]}:{key[1]}": label_agreement(
                records, key
            )
            for key in production + [(c["provider"], c["model"]) for c in candidates]
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
    run.add_argument(
        "--candidates",
        default="",
        help="comma separated provider:model keys; only these candidates judge (default: all)",
    )
    run.add_argument(
        "--no-adjudicate",
        action="store_true",
        help="judge only; rate the records afterwards in a Claude Code session (prompts/apply)",
    )
    prm = sub.add_parser("prompts", help="write one blind adjudication prompt per unrated case")
    prm.add_argument("records", type=Path, nargs="+")
    prm.add_argument("--out", type=Path, required=True)
    app = sub.add_parser("apply", help="validate session answers and store them in the records")
    app.add_argument("records", type=Path, nargs="+")
    app.add_argument("--answers", type=Path, required=True)
    app.add_argument("--adjudicator", required=True, help="the model that wrote the answers")
    rep = sub.add_parser("report", help="merge shard records and write the report")
    rep.add_argument("records", type=Path, nargs="+")
    rep.add_argument("--markdown", type=Path, required=True)
    rep.add_argument("--json", type=Path, required=True)
    for p in (run, rep, prm, app):
        p.add_argument("--config", type=Path, default=ROOT / "config/verifier_shadow.json")
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))

    if args.command in ("prompts", "apply"):
        cases = corpus_cases()
        files = {path: json.loads(path.read_text(encoding="utf-8")) for path in args.records}
        every = [r for records in files.values() for r in records]
        if args.command == "prompts":
            print(f"wrote {write_prompts(every, cases, args.out)} blind prompt(s) to {args.out}")
            return 0
        counts = apply_answers(every, cases, args.answers, args.adjudicator)
        for path, records in files.items():
            _save(path, records)
        print(f"session adjudication: {counts}")
        return 0

    if args.command == "report":
        wanted = {case["case_id"] for case in corpus_cases()}
        records = [
            r
            for path in args.records
            for r in json.loads(path.read_text(encoding="utf-8"))
            if r["corpus"]["case_id"] in wanted  # a case the corpus no longer selects never counts
        ]
        result = report(records, config)
        args.json.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
        args.markdown.write_text(markdown(result), encoding="utf-8")
        print(markdown(result))
        return 0

    started = time.monotonic()
    if args.candidates:  # a trial of new candidates: the production pair plus only these
        wanted = {key.strip() for key in args.candidates.split(",") if key.strip()}
        config = {
            **config,
            "candidates": [
                c for c in config["candidates"] if f"{c['provider']}:{c['model']}" in wanted
            ],
        }
        unknown = wanted - {f"{c['provider']}:{c['model']}" for c in config["candidates"]}
        if unknown:
            parser.error(f"not in the candidate config: {', '.join(sorted(unknown))}")
    cases = corpus_cases()[args.shard :: args.shards][: args.max_cases]
    restored = json.loads(args.records.read_text()) if args.records.exists() else []
    # a checkpoint from another case selection or shard split keeps only this shard's cases
    mine = {case["case_id"] for case in cases}
    records = [r for r in restored if r["corpus"]["case_id"] in mine]
    counts = run_corpus(
        cases,
        records,
        config,
        production=production_judges(),
        judge=judge_case,
        deadline=None if args.budget_seconds is None else started + args.budget_seconds,
        checkpoint=lambda: _save(args.records, records),
        adjudicate_here=not args.no_adjudicate,
    )
    _save(args.records, records)
    print(f"corpus shard {args.shard}/{args.shards}: {len(cases)} case(s): {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
