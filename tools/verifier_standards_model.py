#!/usr/bin/env python3
"""Cost/benefit model of verification standards (docs/ops/VERIFIER_STANDARDS_ANALYSIS.md).

A verification *standard* is an operating point (how often a bad PR still passes, how often a good PR
is flagged) plus a blocking mode (advisory, time-boxed block, or hard block). This model prices each
standard in agent-hours per PR and in human minutes per week, from measured inputs, and shows how the
answer moves with the assumptions that were not measured. It is arithmetic, not a forecast: change
``PARAMS`` and the tables change.

Measured inputs (see the analysis for sources and evidence class):
* ``t_verify_h``: added merge-cycle time of a PR with one verification round (median, within repo).
* ``prs_per_week`` and ``verified_share``: 161 merged keepalive PRs in 33 days, 39% verified.
* operating points: judges and combinations scored on 35 comparable cases (16 good, 19 bad).
* ``persistent_ff``: share of flagged good PRs that every judge flags (2 of 3 here).

Assumptions (ranges are swept): rework and escape costs, bad-PR base rate, how much of the
benchmark's detection survives in production (``realism``), human minutes per escalated stall.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

PARAMS = {
    "t_verify_h": 0.3,  # measured: +0.27 h (Workflows) to +0.46 h (consumers) median per verified PR
    "prs_per_week": 34.0,  # measured: 161 merged keepalive PRs over 33 days
    "verified_share": 0.39,  # measured: 63 of 161 merged PRs carried a verification result
    "c_rework_h": 1.0,  # assumed: one fix round + CI + re-verify (range 0.5 to 2)
    "c_fix_h": 1.0,  # assumed: a caught bad PR costs one fix round, instead of an escape
    "timebox_h": 2.0,  # assumed: block for at most this long, then merge with a follow-up issue
    "stall_wait_h": 12.0,  # assumed: delay until a human clears a persistent hard block
    "stall_minutes": 15.0,  # assumed: human minutes per escalated persistent block
    "human_budget_min_week": 30.0,  # owner's standing budget per system
    "persistent_ff": 2 / 3,  # measured: 2 of the 3 flagged good cases were flagged by every judge
    "advisory_action": 0.5,  # assumed: share of advisory flags someone acts on
}
BAD_RATES = (0.02, 0.05, 0.10)  # Brain: 1.8% overall, 10-13% among verifier-judged runs (selection)
ESCAPE_RATIOS = (3, 10, 30)  # C_escape / C_rework
REALISM = (1.0, 0.5, 0.25)  # share of benchmark detection that survives in production


@dataclass(frozen=True)
class Standard:
    name: str
    fp: float  # share of bad PRs that still pass
    ff: float  # share of good PRs flagged
    mode: str  # "none" | "advisory" | "timebox" | "hard"


def standard_cost(
    s: Standard, *, bad: float, ratio: float, realism: float = 1.0, p: dict | None = None
) -> dict[str, float]:
    """Expected delay-hours added per verified PR, and human minutes per week for the pool.

    Everything is wall-clock delay to finishing the work: the verification round, fix rounds, waiting
    on a block, and the repair of an escaped defect (``ratio`` times a rework round).
    """
    p = p or PARAMS
    c_esc = ratio * p["c_rework_h"]
    if s.mode == "none":
        return {"hours_per_pr": bad * c_esc, "human_min_week": 0.0, "stalls_per_week": 0.0}
    # detection that survives in production; an undetected bad PR escapes
    catch = (1 - s.fp) * realism
    if s.mode == "advisory":
        catch *= p["advisory_action"]
    ff = s.ff
    persistent = p["persistent_ff"]  # a flag every judge repeats cannot be fixed by another round
    hours = p["t_verify_h"]
    hours += bad * ((1 - catch) * c_esc + catch * p["c_fix_h"])
    stalls = 0.0
    good_flagged = (1 - bad) * ff
    if s.mode == "hard":
        # transient flags cost a fix round; persistent flags wait for a human
        hours += good_flagged * (
            (1 - persistent) * p["c_rework_h"] + persistent * p["stall_wait_h"]
        )
        stalls = p["prs_per_week"] * p["verified_share"] * good_flagged * persistent
    elif s.mode == "timebox":
        # transient flags cost a fix round; persistent flags wait out the box, then merge
        hours += good_flagged * ((1 - persistent) * p["c_rework_h"] + persistent * p["timebox_h"])
    else:  # advisory: a flag on a good PR costs a look, not a block
        hours += good_flagged * 0.1
    return {
        "hours_per_pr": hours,
        "human_min_week": stalls * p["stall_minutes"],
        "stalls_per_week": stalls,
    }


def weekly_hours(cost: dict[str, float], p: dict | None = None) -> float:
    p = p or PARAMS
    return cost["hours_per_pr"] * p["prs_per_week"] * p["verified_share"]


def breakeven_bad_rate(s: Standard, *, ratio: float, realism: float = 1.0) -> float | None:
    """Bad-PR base rate above which this standard beats no verification (None: never)."""
    lo, hi = 0.0, 1.0
    none = Standard("none", 1.0, 0.0, "none")
    gain = lambda b: (  # noqa: E731
        standard_cost(none, bad=b, ratio=ratio)["hours_per_pr"]
        - standard_cost(s, bad=b, ratio=ratio, realism=realism)["hours_per_pr"]
    )
    if gain(hi) <= 0:
        return None
    if gain(lo) >= 0:
        return 0.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if gain(mid) < 0 else (lo, mid)
    return hi


def markdown(standards: list[Standard]) -> str:
    out = ["| Standard | Mode | Bad PRs that pass | Good PRs flagged |", "|---|---|---:|---:|"]
    for s in standards:
        out.append(f"| {s.name} | {s.mode} | {s.fp:.0%} | {s.ff:.0%} |")
    for ratio in ESCAPE_RATIOS:
        out += [
            "",
            f"Delay-hours per verified PR at an escape/rework cost ratio of {ratio} "
            "(lower is better; realism 1.0)",
            "",
            "| Standard | bad 2% | bad 5% | bad 10% | human min/week (hard blocks) |",
            "|---|---:|---:|---:|---:|",
        ]
        for s in standards:
            cells = [standard_cost(s, bad=b, ratio=ratio) for b in BAD_RATES]
            out.append(
                f"| {s.name} | "
                + " | ".join(f"{c['hours_per_pr']:.2f}" for c in cells)
                + f" | {cells[1]['human_min_week']:.0f} |"
            )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operating-points", required=True, help="JSON: name -> [fp, ff]")
    args = parser.parse_args(argv)
    points = json.loads(Path(args.operating_points).read_text())
    standards = [Standard(n, fp, ff, "hard") for n, (fp, ff) in points.items()]
    print(markdown(standards))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
