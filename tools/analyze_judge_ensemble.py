#!/usr/bin/env python3
"""Quantify what extra verifier judges would buy: agreement, third-judge tie-breaks and failover.

Input: one or more screen outputs. Each is either this repository's judge-backend screen
(``workflows-judge-backend-screen/v1``) or the MAINT-78 Codex CLI screen; both carry one row per
(judge, case) with the expected verdict and the judge's verdict.

Two options are evaluated, and neither is enabled by this tool:

1. **Tie-break**: when two judges disagree, a third decides. Value = of the disagreements, how often
   the third judge matches the adjudicated truth.
2. **Failover**: when one judge's token pool is exhausted, a backup takes its slot. Value = how the
   backup's PASS decisions perform when it stands in for the missing judge.

The production compare contract is deliberately strict (PASS needs complete exact-slot coverage, a
configured FAIL always survives, and a missing judge cannot be replaced by an available fallback).
So a judge may hold PASS authority only after it has earned it. This tool reports, per judge, the
evidence blockers to that authority, using the same gates as the verifier selection policy, and it
says "insufficient evidence" when the sample cannot support a claim. An 8-case screen cannot.
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from statistics import NormalDist
from typing import Any

from tools.evaluate_model_benchmark import wilson_interval
from tools.run_judge_backend_screen import wilson_upper

SCHEMA = "workflows-judge-ensemble-analysis/v1"
MIN_DISAGREEMENTS = 5  # below this, a tie-break's value cannot be estimated at all


def cases_needed_for_bound(bound: float) -> int:
    """Smallest number of NON_PASS cases with zero false passes that Wilson-bounds the rate."""
    for n in range(1, 10_000):
        if wilson_upper(0, n) <= bound:
            return n
    return 10_000


def load_judgments(paths: list[Path]) -> tuple[dict[str, dict[str, str | None]], dict[str, str]]:
    """judge -> case -> 'PASS' | 'NON_PASS' | None (invalid), plus the shared case truth."""
    decisions: dict[str, dict[str, str | None]] = {}
    truth: dict[str, str] = {}
    fingerprint = None
    for index, path in enumerate(paths):
        data = json.loads(path.read_text())
        identity = (data.get("input_fingerprint"), data.get("prompt_sha256_by_case"))
        if index and identity != fingerprint:
            raise ValueError(f"inconsistent corpus or prompt fingerprint in {path}")
        fingerprint = identity
        for row in data.get("rows", []):
            judge = str(row.get("judge") or row.get("model_id"))
            case = str(row["case_id"])
            expected = str(row["expected_verdict"])
            if truth.setdefault(case, expected) != expected:
                raise ValueError(f"inconsistent expected verdict for {case}")
            valid = row.get("schema_valid", True)
            value = (row.get("raw_verdict") or row["actual_verdict"]) if valid else None
            if value not in {None, "PASS", "NON_PASS", "CONCERNS", "FAIL"}:
                raise ValueError(f"invalid verdict for {judge} on {case}")
            observed = decisions.setdefault(judge, {})
            if case in observed and observed[case] != value:
                raise ValueError(f"conflicting results for {judge} on {case} in {path}")
            observed[case] = value
    return decisions, truth


def _score(outcomes: dict[str, str], truth: dict[str, str]) -> dict[str, Any]:
    false_pass = sum(truth[c] == "NON_PASS" and v == "PASS" for c, v in outcomes.items())
    false_fail = sum(truth[c] == "PASS" and v != "PASS" for c, v in outcomes.items())
    correct = sum(v == truth[c] for c, v in outcomes.items())
    non_pass = sum(truth[c] == "NON_PASS" for c in outcomes)
    return {
        "cases": len(outcomes),
        "correct": correct,
        "false_pass": false_pass,
        "false_fail": false_fail,
        "false_pass_wilson_upper_bound": wilson_upper(false_pass, non_pass),
    }


def _fail_closed(value: str | None) -> str:
    return "PASS" if value == "PASS" else "NON_PASS"  # an invalid result can never be a PASS


def judge_authority(
    name: str,
    decisions: dict[str, str | None],
    truth: dict[str, str],
    *,
    bound: float,
    categories: dict[str, str] | None = None,
    baseline: dict[str, str | None] | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cases = sorted(truth)
    missing = [c for c in cases if c not in decisions]
    invalid = sum(decisions.get(c) is None for c in cases if c in decisions)
    scored = _score({c: _fail_closed(decisions[c]) for c in cases if c in decisions}, truth)
    blockers = []
    if missing:
        blockers.append(f"{len(missing)} case(s) not judged")
    if scored["false_pass"]:
        blockers.append(f"{scored['false_pass']} false PASS observed")
    if invalid:
        blockers.append(f"{invalid} invalid result(s)")
    non_pass = sum(v == "NON_PASS" for v in truth.values())
    if scored["false_pass_wilson_upper_bound"] > bound:
        blockers.append(
            f"false-PASS upper bound {scored['false_pass_wilson_upper_bound']} exceeds {bound} "
            f"on {non_pass} NON_PASS case(s); {cases_needed_for_bound(bound)} are needed with zero errors"
        )
    profile = (
        policy
        or json.loads(
            (Path(__file__).resolve().parents[1] / "config/model_selection_policy.json").read_text()
        )
    )["profiles"]["verifier-balanced"]
    stage = profile["approval_stage"]
    gates = stage["quality_gates"]
    z = NormalDist().inv_cdf((1 + stage.get("confidence_level", 0.95)) / 2)
    present = [c for c in cases if c in decisions]
    correct = sum(
        decisions[c] is not None and _fail_closed(decisions[c]) == truth[c] for c in present
    )
    pass_count = sum(truth[c] == "PASS" for c in present)
    non_pass_count = len(present) - pass_count
    category_counts = {
        k: sum((categories or {}).get(c) == k for c in present)
        for k in profile["candidate_stage"]["required_case_categories"]
    }
    floors = stage.get("minimum_cases_per_category_overrides", {})
    paired = baseline is not None and set(baseline) == set(truth) and not missing
    baseline_success = (
        sum(baseline[c] is not None and _fail_closed(baseline[c]) == truth[c] for c in cases)
        if paired
        else 0
    )
    approval_gates = {
        "minimum_adjudicated_cases": len(present) >= stage["minimum_adjudicated_cases"],
        "minimum_cases_per_category": all(
            n >= floors.get(k, stage["minimum_cases_per_category"])
            for k, n in category_counts.items()
        ),
        "task_success_rate_wilson_lower_bound": wilson_interval(correct, len(present), z=z)[0]
        >= gates["task_success_rate_wilson_lower_bound"],
        "false_pass_rate_wilson_upper_bound": wilson_interval(
            scored["false_pass"], non_pass_count, z=z
        )[1]
        <= gates["false_pass_rate_wilson_upper_bound"],
        "false_fail_rate_wilson_upper_bound": wilson_interval(
            scored["false_fail"], pass_count, z=z
        )[1]
        <= gates["false_fail_rate_wilson_upper_bound"],
        "schema_error_rate_wilson_upper_bound": wilson_interval(invalid, len(present), z=z)[1]
        <= gates["schema_error_rate_wilson_upper_bound"],
        "paired_success_noninferiority": paired
        and (correct - baseline_success) / max(1, len(cases))
        >= -gates["paired_success_noninferiority_margin"],
    }
    blockers.extend(
        f"approval gate failed or unmeasured: {k}"
        for k, passed in approval_gates.items()
        if not passed
    )
    return {
        "approval_gates": approval_gates,
        "judge": name,
        **scored,
        "invalid": invalid,
        "authority_blockers": blockers,
        "may_hold_pass_authority": not blockers,
    }


def strict_and(
    a: dict[str, str | None], b: dict[str, str | None], cases: list[str]
) -> dict[str, str]:
    """The production contract: PASS only when both judges returned a valid PASS."""
    return {c: "PASS" if a.get(c) == "PASS" and b.get(c) == "PASS" else "NON_PASS" for c in cases}


def majority(judges: list[dict[str, str | None]], cases: list[str]) -> dict[str, str]:
    need = len(judges) // 2 + 1
    return {
        c: (
            "PASS"
            if all(j.get(c) in {"PASS", "CONCERNS"} for j in judges)
            and sum(j.get(c) == "PASS" for j in judges) >= need
            else "NON_PASS"
        )
        for c in cases
    }


def analyze(
    decisions: dict[str, dict[str, str | None]],
    truth: dict[str, str],
    *,
    bound: float = 0.05,
    categories: dict[str, str] | None = None,
    baseline_model: str | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cases = sorted(truth)
    names = sorted(decisions)
    authority = [
        judge_authority(
            n,
            decisions[n],
            truth,
            bound=bound,
            categories=categories,
            baseline=decisions.get(baseline_model),
            policy=policy,
        )
        for n in names
    ]
    pairs = []
    for a, b in itertools.combinations(names, 2):
        both = [c for c in cases if c in decisions[a] and c in decisions[b]]
        agree = sum(_fail_closed(decisions[a][c]) == _fail_closed(decisions[b][c]) for c in both)
        pairs.append(
            {
                "judges": [a, b],
                "cases": len(both),
                "agreement": round(agree / len(both), 3) if both else None,
                "both_wrong": sum(
                    _fail_closed(decisions[a][c]) != truth[c]
                    and _fail_closed(decisions[b][c]) != truth[c]
                    for c in both
                ),
                "strict_and": _score(strict_and(decisions[a], decisions[b], both), truth),
            }
        )
    tie_breaks = []
    for trio in itertools.permutations(names, 3):
        a, b, c = trio
        if a > b:
            continue  # the pair is unordered; the third judge is the tie-breaker
        both = [x for x in cases if all(x in decisions[j] for j in trio)]
        disagreements = [
            x for x in both if {decisions[a][x], decisions[b][x]} == {"PASS", "CONCERNS"}
        ]
        third_right = sum(_fail_closed(decisions[c][x]) == truth[x] for x in disagreements)
        maj = majority([decisions[a], decisions[b], decisions[c]], both)
        tie_breaks.append(
            {
                "pair": [a, b],
                "tie_breaker": c,
                "cases": len(both),
                "disagreements": len(disagreements),
                "tie_breaker_right_on_disagreements": third_right,
                "majority_of_three": _score(maj, truth),
                "estimable": len(disagreements) >= MIN_DISAGREEMENTS,
            }
        )
    failovers = []
    for primary, backup in itertools.permutations(names, 2):
        both = [c for c in cases if c in decisions[primary] and c in decisions[backup]]
        failovers.append(
            {
                "unavailable": primary,
                "backup": backup,
                "backup_alone": _score(
                    {c: _fail_closed(decisions[backup][c]) for c in both}, truth
                ),
                "backup_may_hold_pass_authority": next(
                    a["may_hold_pass_authority"] for a in authority if a["judge"] == backup
                ),
            }
        )
    eligible = [a["judge"] for a in authority if a["may_hold_pass_authority"]]
    needed = cases_needed_for_bound(bound)
    non_pass = sum(v == "NON_PASS" for v in truth.values())
    return {
        "schema": SCHEMA,
        "cases": len(cases),
        "non_pass_cases": non_pass,
        "judges": authority,
        "pairs": pairs,
        "tie_breaks": tie_breaks,
        "failovers": failovers,
        "recommendation": {
            "tie_break": _tie_break_verdict(tie_breaks, eligible),
            "failover": _failover_verdict(failovers, eligible),
            "sample_note": (
                f"{non_pass} NON_PASS case(s) observed; {needed} are needed with zero false PASS to "
                f"bound the false-PASS rate at {bound}. Small-sample results cannot enable either option."
            ),
        },
        "enables_anything": False,
    }


def _tie_break_verdict(tie_breaks: list[dict[str, Any]], eligible: list[str]) -> str:
    if len(eligible) < 3:
        return (
            f"not enabled: {len(eligible)} of the judges meet the PASS-authority gates "
            "(three are needed so that every vote carries authority)"
        )
    useful = [
        t
        for t in tie_breaks
        if t["estimable"] and set(t["pair"] + [t["tie_breaker"]]).issubset(eligible)
    ]
    if not useful:
        return f"insufficient evidence: fewer than {MIN_DISAGREEMENTS} disagreements to learn from"
    best = max(useful, key=lambda t: t["tie_breaker_right_on_disagreements"] / t["disagreements"])
    share = best["tie_breaker_right_on_disagreements"] / best["disagreements"]
    return (
        f"candidate: {best['tie_breaker']} breaks ties for {best['pair']} and is right on "
        f"{share:.0%} of {best['disagreements']} disagreements; confirm on the larger corpus first"
    )


def _failover_verdict(failovers: list[dict[str, Any]], eligible: list[str]) -> str:
    if len(eligible) < 2:
        return (
            f"not enabled: {len(eligible)} judge(s) meet the PASS-authority gates; a backup must "
            "earn the same authority as the judge it replaces"
        )
    return (
        "candidate: "
        + ", ".join(sorted(eligible))
        + " may stand in for one another; confirm on the larger corpus first"
    )


def markdown(result: dict[str, Any]) -> str:
    lines = [
        "## Judge ensemble analysis",
        "",
        f"{result['cases']} cases ({result['non_pass_cases']} NON_PASS). **Nothing is enabled by this report.**",
        "",
        "| Judge | Correct | False PASS | False-PASS upper bound | Invalid | PASS authority |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for judge in result["judges"]:
        lines.append(
            f"| {judge['judge']} | {judge['correct']}/{judge['cases']} | {judge['false_pass']} | "
            f"{judge['false_pass_wilson_upper_bound']} | {judge['invalid']} | "
            f"{'yes' if judge['may_hold_pass_authority'] else 'no: ' + '; '.join(judge['authority_blockers'])} |"
        )
    lines += [
        "",
        "### Pairs (production strict-AND contract)",
        "",
        "| Pair | Agreement | Both wrong | False PASS | False FAIL |",
        "|---|---:|---:|---:|---:|",
    ]
    for pair in result["pairs"]:
        lines.append(
            f"| {' + '.join(pair['judges'])} | {pair['agreement']} | {pair['both_wrong']} | "
            f"{pair['strict_and']['false_pass']} | {pair['strict_and']['false_fail']} |"
        )
    recommendation = result["recommendation"]
    lines += [
        "",
        f"**Tie-break:** {recommendation['tie_break']}",
        f"**Failover:** {recommendation['failover']}",
        f"**Sample:** {recommendation['sample_note']}",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", nargs="+", type=Path, required=True)
    parser.add_argument("--false-pass-bound", type=float, default=0.05)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args(argv)
    decisions, truth = load_judgments(args.inputs)
    if len(decisions) < 2:
        raise SystemExit("need at least two judges")
    categories = {}
    baselines = set()
    for path in args.inputs:
        data = json.loads(path.read_text())
        for row in data.get("rows", []):
            if row.get("category"):
                case = row["case_id"]
                if categories.setdefault(case, row["category"]) != row["category"]:
                    raise ValueError(f"inconsistent category for {case}")
        if (data.get("baseline") or {}).get("judge"):
            baselines.add(data["baseline"]["judge"])
    if len(baselines) > 1:
        raise ValueError("inconsistent incumbent baseline")
    result = analyze(
        decisions,
        truth,
        bound=args.false_pass_bound,
        categories=categories,
        baseline_model=next(iter(baselines), None),
    )
    result["ordered_input_manifest"] = [str(path) for path in args.inputs]
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    text = markdown(result)
    if args.markdown:
        args.markdown.write_text(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
