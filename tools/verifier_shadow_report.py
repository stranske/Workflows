#!/usr/bin/env python3
"""Evaluate shadow-run candidate verifiers against the criteria pre-registered in config/verifier_shadow.json.

Inputs are the ``verifier-shadow.json`` records the verifier workflow uploads (collected across the
fleet and merged into a ledger by ``collect``). For each candidate the head-to-head baseline is the
production slot that has the same provider (the judge it would replace); the unified production verdict
is reported alongside. The result is one of MEETS, DOES NOT MEET (the failing criterion is named) or
INSUFFICIENT (the window has not produced enough paired runs, with the number still needed). Nothing here
promotes a model: it prints what the pre-registered criteria say, and a human reads it once.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

PASS = "PASS"


ACCEPTED_PIPELINES = {"compare-slot/v2"}


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


def paired_runs(records: list[dict[str, Any]], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Runs where the candidate and the production slot it replaces both gave a usable verdict."""
    out = []
    for record in records:
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
        for record in records
        for c in record.get("candidates", [])
        if c.get("provider") == candidate["provider"]
        and c.get("model") == candidate["model"]
        and _current(c)
    ]


def evaluate_candidate(
    records: list[dict[str, Any]],
    candidate: dict[str, Any],
    config: dict[str, Any],
    *,
    now: datetime,
    started_at: datetime | None,
) -> dict[str, Any]:
    crit, window = config["criteria"], config["window"]
    pairs = paired_runs(records, candidate)
    tries = attempted(records, candidate)
    n = len(pairs)
    inc_pass = [p for p in pairs if p["slot"]["verdict"] == PASS]
    inc_flag = [p for p in pairs if p["slot"]["verdict"] != PASS]
    misses = [p for p in inc_flag if p["candidate"]["verdict"] == PASS]
    extra = [p for p in inc_pass if p["candidate"]["verdict"] != PASS]
    agree = sum(
        (p["candidate"]["verdict"] == PASS) == (p["slot"]["verdict"] == PASS) for p in pairs
    )
    coverage = (len([t for t in tries if _valid(t)]) / len(tries)) if tries else None
    days = ((now - started_at).total_seconds() / 86400.0) if started_at else 0.0
    checks = {
        "coverage": coverage is not None and coverage >= crit["coverage_min"],
        "candidate_misses": len(misses)
        <= max(
            crit["candidate_miss_max_absolute"],
            math.floor(crit["candidate_miss_max_share_of_incumbent_flags"] * len(inc_flag)),
        ),
        "extra_flags": len(extra)
        <= max(
            crit["extra_flag_max_absolute"],
            math.ceil(crit["extra_flag_max_share_of_incumbent_passes"] * len(inc_pass)),
        ),
        "class_agreement": n > 0 and agree / n >= crit["class_agreement_min"],
    }
    failed = [name for name, ok in checks.items() if not ok]
    runs_short = max(0, window["min_runs"] - n)
    days_short = max(0.0, window["min_days"] - days)
    if failed and n >= window["min_runs"]:
        status = "DOES NOT MEET"
    elif failed and misses:
        status = "DOES NOT MEET"  # a candidate miss is decisive even before the window closes
    elif runs_short or days_short:
        status = "INSUFFICIENT" if days < window["max_days"] else "INSUFFICIENT AT CAP"
    elif failed:
        status = "DOES NOT MEET"
    else:
        status = "MEETS"
    return {
        "candidate": f"{candidate['provider']}:{candidate['model']}",
        "status": status,
        "paired_runs": n,
        "attempts": len(tries),
        "coverage": None if coverage is None else round(coverage, 3),
        "incumbent_pass_runs": len(inc_pass),
        "incumbent_flag_runs": len(inc_flag),
        "candidate_misses": [_ref(p) for p in misses],
        "extra_flags": [_ref(p) for p in extra],
        "class_agreement": None if not n else round(agree / n, 3),
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
        f"Generated {result['generated_at']}; {result['records']} shadow record(s). "
        "Pre-registered criteria: `config/verifier_shadow.json`. Nothing here promotes a model.",
        "",
    ]
    lines += [
        "| Candidate | Status | Paired runs | Still needed (runs / days) | Misses | Extra flags | Agreement |",
        "|---|---|---:|---|---:|---:|---:|",
    ]
    for c in result["candidates"]:
        lines.append(
            f"| {c['candidate']} | **{c['status']}** | {c['paired_runs']} | "
            f"{c['runs_still_needed']} / {c['days_still_needed']} | {len(c['candidate_misses'])} | "
            f"{len(c['extra_flags'])} | {c['class_agreement']} |"
        )
    lines.append("")
    for c in result["candidates"]:
        lines += [
            f"### {c['candidate']}: **{c['status']}**",
            "",
            f"- paired runs {c['paired_runs']} (attempts {c['attempts']}, coverage {c['coverage']}), "
            f"observed {c['days_observed']} days",
            f"- still needed: {c['runs_still_needed']} paired run(s), {c['days_still_needed']} day(s)",
            f"- class agreement with the replaced production judge: {c['class_agreement']}",
            f"- candidate misses (candidate PASS, incumbent not): {len(c['candidate_misses'])} "
            f"of {c['incumbent_flag_runs']} incumbent flags",
            f"- extra flags (candidate not PASS, incumbent PASS): {len(c['extra_flags'])} "
            f"of {c['incumbent_pass_runs']} incumbent passes",
            f"- failed criteria: {', '.join(c['failed_criteria']) or 'none'}",
        ]
        for label, refs in (("misses", c["candidate_misses"]), ("extra flags", c["extra_flags"])):
            lines += [f"  - {label}: {r}" for r in refs]
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
