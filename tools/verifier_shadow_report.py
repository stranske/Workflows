#!/usr/bin/env python3
"""Evaluate shadow-run candidate verifiers by the quality of their work (config/verifier_shadow.json).

Inputs are the ``verifier-shadow.json`` records the verifier workflow uploads (collected across the
fleet and merged into a ledger by ``collect``) and the blind adjudications that
``tools/verifier_shadow_adjudicate.py`` adds to them. The production verifier runs two judges from
different provider families and expects them to disagree, so a candidate is not graded by verdict
agreement: it is graded by how often its evaluation is inaccurate, how rigorously it covers the
tasks and acceptance criteria, and how useful its review is, each against the production judges'
work on the same runs. The result is MEETS, DOES NOT MEET (the failing criterion is named) or
INSUFFICIENT (with the runs and days still needed). Nothing here promotes a model.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

PASS = "PASS"


ACCEPTED_PIPELINES = {"compare-slot/v3"}


def _valid(entry: dict[str, Any] | None) -> bool:
    """A usable measurement: the judge answered, without a harness error (parse failure, timeout)."""
    return (
        bool(entry)
        and bool(entry.get("used_llm"))
        and entry.get("verdict") is not None
        and not entry.get("error")
    )


def _current(entry: dict[str, Any]) -> bool:
    """Candidate entries from an earlier, non-production pipeline are not evidence."""
    return entry.get("pipeline") in ACCEPTED_PIPELINES


def _comparable(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Runs whose production verdict came from the pipeline candidates reproduce.

    Expanded-profile runs are judged in production by the semantic package matrix, not by the
    per-slot path candidates take, so pairing the two would compare different pipelines.
    """
    return [r for r in records if r.get("semantic_mode") is not True]


def paired_runs(records: list[dict[str, Any]], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Runs where the candidate and the production slot it replaces both gave a usable verdict."""
    out = []
    for record in _comparable(records):
        cand = next(
            (
                c
                for c in record.get("candidates", [])
                if c.get("provider") == candidate["provider"]
                and c.get("model") == candidate["model"]
                and _current(c)
            ),
            None,
        )
        slot = next(
            (
                s
                for s in record.get("production_slots", [])
                if s.get("provider") == candidate.get("replaces_provider", candidate["provider"])
            ),
            None,
        )
        if _valid(cand) and _valid(slot):
            out.append({"record": record, "candidate": cand, "slot": slot})
    return out


def attempted(records: list[dict[str, Any]], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        c
        for record in _comparable(records)
        for c in record.get("candidates", [])
        if c.get("provider") == candidate["provider"]
        and c.get("model") == candidate["model"]
        and _current(c)
    ]


FINDINGS = {"FAIL", "CONCERNS"}


def _key(candidate: dict[str, Any]) -> str:
    return f"candidate:{candidate['provider']}:{candidate['model']}"


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _share(ratings: list[dict[str, Any]], accuracy: str) -> float | None:
    return (
        round(sum(r.get("accuracy") == accuracy for r in ratings) / len(ratings), 3)
        if ratings
        else None
    )


def adjudicated_runs(records: list[dict[str, Any]], candidate: dict[str, Any]) -> list[dict]:
    """Runs where the adjudicator rated this candidate's evaluation, with the incumbents' ratings."""
    out = []
    for record in _comparable(records):
        adj = record.get("adjudication") or {}
        if adj.get("error"):
            continue
        ratings = adj.get("ratings") or {}
        mine = ratings.get(_key(candidate))
        if not mine or not mine.get("rated"):
            continue
        incumbents = [
            r for k, r in ratings.items() if k.startswith("production:") and r.get("rated")
        ]
        out.append({"record": record, "candidate": mine, "incumbents": incumbents})
    return out


def warnings_for(records: list[dict[str, Any]], candidate: dict[str, Any]) -> list[dict]:
    """Runs where the candidate stands against BOTH production judges (context, never a grade alone).

    A candidate PASS where both production judges raised a finding is the serious sign; a finding
    where both production judges passed is the milder one. UNVERIFIABLE_INPUT is not a finding.
    """
    out = []
    for record in _comparable(records):
        cand = next(
            (
                c
                for c in record.get("candidates", [])
                if c.get("provider") == candidate["provider"]
                and c.get("model") == candidate["model"]
                and _current(c)
                and _valid(c)
            ),
            None,
        )
        slots = [s for s in record.get("production_slots", []) if _valid(s)]
        if cand is None or len(slots) < 2:
            continue
        verdicts = {s["verdict"] for s in slots}
        if cand["verdict"] == PASS and verdicts <= FINDINGS:
            kind = "pass_against_both_findings"
        elif cand["verdict"] in FINDINGS and verdicts == {PASS}:
            kind = "finding_against_both_passes"
        else:
            continue
        rating = ((record.get("adjudication") or {}).get("ratings") or {}).get(_key(candidate))
        out.append(
            {
                "kind": kind,
                "run": _ref({"record": record}),
                "adjudicated_accuracy": (rating or {}).get("accuracy"),
                "reference_verdict": (record.get("adjudication") or {}).get("reference_verdict"),
            }
        )
    return out


def evaluate_candidate(
    records: list[dict[str, Any]],
    candidate: dict[str, Any],
    config: dict[str, Any],
    *,
    now: datetime,
    started_at: datetime | None,
) -> dict[str, Any]:
    """Grade the candidate's WORK, as rated by the blind adjudicator, against the incumbents' work
    on the same runs -- never by whether its verdict matches a production judge's."""
    crit, window = config["criteria"], config["window"]
    runs = adjudicated_runs(records, candidate)
    tries = attempted(records, candidate)
    n = len(runs)
    mine = [r["candidate"] for r in runs]
    theirs = [i for r in runs for i in r["incumbents"]]
    usable = (len([t for t in tries if _valid(t)]) / len(tries)) if tries else None
    inaccurate, inc_inaccurate = _share(mine, "inaccurate"), _share(theirs, "inaccurate")
    coverage = _mean([r["coverage"] for r in mine if r.get("coverage") is not None])
    inc_coverage = _mean([r["coverage"] for r in theirs if r.get("coverage") is not None])
    useful = _mean([r["usefulness"] for r in mine if r.get("usefulness")])
    inc_useful = _mean([r["usefulness"] for r in theirs if r.get("usefulness")])
    warnings = warnings_for(records, candidate)
    decisive = [
        w
        for w in warnings
        if w["kind"] == "pass_against_both_findings" and w["adjudicated_accuracy"] == "inaccurate"
    ]
    days = ((now - started_at).total_seconds() / 86400.0) if started_at else 0.0

    def within(value: float | None, reference: float | None, slack: float, higher_is_better: bool):
        if value is None or reference is None:
            return False
        return value >= reference - slack if higher_is_better else value <= reference + slack

    checks = {
        "usable_evaluations": usable is not None and usable >= crit["usable_min"],
        "inaccuracy": within(
            inaccurate, inc_inaccurate, crit["inaccurate_share_max_excess"], False
        ),
        "rigor": within(coverage, inc_coverage, crit["coverage_max_shortfall"], True),
        "usefulness": within(useful, inc_useful, crit["usefulness_max_shortfall"], True),
        "no_false_pass_against_both_findings": not decisive,
    }
    failed = [name for name, ok in checks.items() if not ok]
    runs_short = max(0, window["min_runs"] - n)
    days_short = max(0.0, window["min_days"] - days)
    if decisive:
        status = "DOES NOT MEET"  # an inaccurate PASS over two production findings is decisive
    elif runs_short or days_short:
        status = "INSUFFICIENT" if days < window["max_days"] else "INSUFFICIENT AT CAP"
    elif failed:
        status = "DOES NOT MEET"
    else:
        status = "MEETS"
    return {
        "candidate": f"{candidate['provider']}:{candidate['model']}",
        "status": status,
        "adjudicated_runs": n,
        "attempts": len(tries),
        "usable_share": None if usable is None else round(usable, 3),
        "inaccurate_share": inaccurate,
        "incumbent_inaccurate_share": inc_inaccurate,
        "partly_inaccurate_share": _share(mine, "partly_inaccurate"),
        "criteria_coverage": coverage,
        "incumbent_criteria_coverage": inc_coverage,
        "usefulness": useful,
        "incumbent_usefulness": inc_useful,
        "warnings": warnings,
        "decisive": [w["run"] for w in decisive],
        "inaccurate_runs": [
            {
                "run": _ref(r),
                "errors": [e.get("why") for e in r["candidate"].get("errors", [])][:3],
            }
            for r in runs
            if r["candidate"].get("accuracy") == "inaccurate"
        ],
        "failed_criteria": failed,
        "runs_still_needed": runs_short,
        "days_still_needed": round(days_short, 1),
        "days_observed": round(days, 1),
    }


def _ref(pair: dict[str, Any]) -> str:
    r = pair["record"]
    return f"{r.get('repository')}#{r.get('pr_number')} (run {r.get('run_id')})"


def evaluate(records: list[dict[str, Any]], config: dict[str, Any], *, now: datetime | None = None):
    now = now or datetime.now(UTC)

    def started_for(candidate: dict[str, Any]) -> datetime | None:
        """A candidate's window starts at the first record that includes it (not the first record)."""
        stamps = [
            r["recorded_at"] for r in records if r.get("recorded_at") and attempted([r], candidate)
        ]
        return min(datetime.fromisoformat(s) for s in stamps) if stamps else None

    return {
        "generated_at": now.isoformat(),
        "records": len(records),
        "candidates": [
            evaluate_candidate(records, c, config, now=now, started_at=started_for(c))
            for c in config.get("candidates", [])
        ],
    }


def markdown(result: dict[str, Any]) -> str:
    lines = [
        "## Verifier shadow report",
        "",
        f"Generated {result['generated_at']}; {result['records']} shadow record(s). Each candidate's "
        "work is rated by a blind adjudicator (accuracy with quoted evidence, coverage of every task "
        "and acceptance criterion, usefulness) and compared with the production judges' work on the "
        "same runs. Criteria: `config/verifier_shadow.json`. Nothing here promotes a model.",
        "",
        "| Candidate | Status | Adjudicated runs | Still needed (runs / days) | Inaccurate (vs incumbents) "
        "| Coverage (vs incumbents) | Usefulness (vs incumbents) | Warnings |",
        "|---|---|---:|---|---|---|---|---:|",
    ]
    for c in result["candidates"]:
        lines.append(
            f"| {c['candidate']} | **{c['status']}** | {c['adjudicated_runs']} | "
            f"{c['runs_still_needed']} / {c['days_still_needed']} | "
            f"{c['inaccurate_share']} ({c['incumbent_inaccurate_share']}) | "
            f"{c['criteria_coverage']} ({c['incumbent_criteria_coverage']}) | "
            f"{c['usefulness']} ({c['incumbent_usefulness']}) | {len(c['warnings'])} |"
        )
    lines.append("")
    for c in result["candidates"]:
        lines += [
            f"### {c['candidate']}: **{c['status']}**",
            "",
            f"- adjudicated runs {c['adjudicated_runs']}; attempts {c['attempts']}, usable share "
            f"{c['usable_share']}; observed {c['days_observed']} days",
            f"- still needed: {c['runs_still_needed']} adjudicated run(s), "
            f"{c['days_still_needed']} day(s)",
            f"- inaccurate evaluations: {c['inaccurate_share']} (production judges on the same runs: "
            f"{c['incumbent_inaccurate_share']}); partly inaccurate: {c['partly_inaccurate_share']}",
            f"- task/criteria coverage: {c['criteria_coverage']} "
            f"(production: {c['incumbent_criteria_coverage']})",
            f"- usefulness (1-5): {c['usefulness']} (production: {c['incumbent_usefulness']})",
            f"- failed criteria: {', '.join(c['failed_criteria']) or 'none'}",
        ]
        lines += [
            f"  - inaccurate: {r['run']}: {'; '.join(e for e in r['errors'] if e)}"
            for r in c["inaccurate_runs"]
        ]
        lines += [
            f"  - warning ({w['kind']}): {w['run']}, adjudicated {w['adjudicated_accuracy']}, "
            f"best-supported verdict {w['reference_verdict']}"
            for w in c["warnings"]
        ]
        lines.append("")
    return "\n".join(lines)


def shadow_records_from_zip(blob: bytes) -> list[dict[str, Any]]:
    """The shadow record(s) in a ``comparison-results-*`` artifact archive."""
    out = []
    with zipfile.ZipFile(BytesIO(blob)) as archive:
        for name in archive.namelist():
            if name.endswith("verifier-shadow.json"):
                try:
                    record = json.loads(archive.read(name))
                except ValueError:
                    continue
                if record.get("candidates"):
                    out.append(record)
    return out


def merge_ledger(ledger: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Append records not already present, keyed by repository and run id."""
    seen = {(r.get("repository"), r.get("run_id")) for r in ledger}
    merged = list(ledger)
    for record in new:
        key = (record.get("repository"), record.get("run_id"))
        if key not in seen:
            merged.append(record)
            seen.add(key)
    return merged


def collect(
    repos: list[str],
    *,
    since: datetime,
    list_artifacts: Callable[[str], list[dict[str, Any]]],
    download: Callable[[str, int], bytes],
) -> list[dict[str, Any]]:
    """Shadow records from recent ``comparison-results-*`` artifacts of every repository."""
    found: list[dict[str, Any]] = []
    for repo in repos:
        for artifact in list_artifacts(repo):
            created = datetime.fromisoformat(artifact["created_at"].replace("Z", "+00:00"))
            if artifact.get("expired") or created < since:
                continue
            if not str(artifact.get("name", "")).startswith("comparison-results-"):
                continue
            for record in shadow_records_from_zip(download(repo, int(artifact["id"]))):
                record.setdefault("repository", repo)
                found.append(record)
    return found


def gh_list_artifacts(repo: str) -> list[dict[str, Any]]:
    out = subprocess.run(
        ["gh", "api", f"repos/{repo}/actions/artifacts?per_page=100", "--jq", ".artifacts"],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return json.loads(out.stdout or "[]")
    except ValueError:
        return []


def gh_download(repo: str, artifact_id: int) -> bytes:
    return subprocess.run(
        ["gh", "api", f"repos/{repo}/actions/artifacts/{artifact_id}/zip"],
        capture_output=True,
        check=False,
    ).stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("config/verifier_shadow.json"))
    parser.add_argument(
        "--repos", default="", help="comma separated owner/name list to collect from"
    )
    parser.add_argument("--days", type=int, default=8)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text())
    ledger = json.loads(args.ledger.read_text()) if args.ledger.exists() else []
    repos = [r.strip() for r in args.repos.split(",") if r.strip()]
    if repos:
        since = datetime.now(UTC) - timedelta(days=args.days)
        ledger = merge_ledger(
            ledger,
            collect(repos, since=since, list_artifacts=gh_list_artifacts, download=gh_download),
        )
    args.ledger.write_text(json.dumps(ledger, indent=1) + "\n")
    result = evaluate(ledger, config)
    text = markdown(result)
    if args.markdown:
        args.markdown.write_text(text)
    else:
        print(text)
    if args.json:
        args.json.write_text(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
