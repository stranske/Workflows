"""Regenerate the #3998 escaped-defect, churn, and uncovered-mass ranking.

The sort is the Orchestrator ``escaped_defect_priority`` order: fix and revert
weight, then non-merge churn, then uncovered statements plus branches. Issue
#3998's printed integers stay the preserved snapshot. A fresh 180-day window
does not reproduce that order. #4405 was unmerged at the recorded observation,
so its counters are not subtracted from that historical Gate remainder.
Inputs are pinned local evidence; validation never fetches repository history.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/issue-4426"
RANKING_JSON = EVIDENCE / "ranking.json"
RANKING_MD = EVIDENCE / "ranking.md"
CONTRACT_PATH = EVIDENCE / "contract-3998.json"
MEASUREMENT_PATH = EVIDENCE / "coverage-measurement.json"
INVENTORY_PATH = EVIDENCE / "pr-inventory.json"

# Orchestrator src/escaped_defect_priority.py blob at retrieval on 2026-11-06.
# coverage-autopilot.py is not in this repository; this is the ranking command
# the issue text quotes ("fix commit touched this file", then churn, then mass).
ORCHESTRATOR_BLOB = "3447463191e5b2d27acf15b3ae5f45f51a9ac484"
FIX_SUBJECT_PATTERN = r"^\s*(?:fix|bugfix|hotfix|patch)\b[^:]*:|^\s*(?:fix|fixes|fixed)\s+"
REVERT_SUBJECT_PATTERN = r"^\s*revert\b"
REVERT_WEIGHT = 3.0
FIX_WEIGHT = 1.0
LOOKBACK_DAYS = 180
CHECKED_ON = "2026-11-06"

TARGETS = (
    "scripts/sync_test_dependencies.py",
    "scripts/langchain/issue_pr_context.py",
    "scripts/langchain/verifier_config.py",
    "tools/langchain_client.py",
    "scripts/langchain/task_validator.py",
    "scripts/langchain/pr_verifier.py",
)

# Independent counts from git log at the pinned revisions, not from ranking.json.
PRE_ROUND_COUNTS = {
    "scripts/sync_test_dependencies.py": (18.0, 20),
    "scripts/langchain/issue_pr_context.py": (7.0, 9),
    "scripts/langchain/verifier_config.py": (8.0, 10),
    "tools/langchain_client.py": (14.0, 20),
    "scripts/langchain/task_validator.py": (7.0, 10),
    "scripts/langchain/pr_verifier.py": (46.0, 54),
}
CURRENT_COUNTS = {
    "scripts/sync_test_dependencies.py": (17.0, 20),
    "scripts/langchain/issue_pr_context.py": (2.0, 3),
    "scripts/langchain/verifier_config.py": (4.0, 5),
    "tools/langchain_client.py": (12.0, 18),
    "scripts/langchain/task_validator.py": (7.0, 10),
    "scripts/langchain/pr_verifier.py": (62.0, 75),
}
PRE_ROUND_ORDER = (
    "scripts/langchain/pr_verifier.py",
    "scripts/sync_test_dependencies.py",
    "tools/langchain_client.py",
    "scripts/langchain/verifier_config.py",
    "scripts/langchain/task_validator.py",
    "scripts/langchain/issue_pr_context.py",
)
CURRENT_ORDER = (
    "scripts/langchain/pr_verifier.py",
    "scripts/sync_test_dependencies.py",
    "tools/langchain_client.py",
    "scripts/langchain/task_validator.py",
    "scripts/langchain/verifier_config.py",
    "scripts/langchain/issue_pr_context.py",
)


def lookback_since(committer_iso: str, days: int = LOOKBACK_DAYS) -> str:
    """Return the UTC instant ``days`` before a timezone-aware committer timestamp."""
    if days < 0:
        raise ValueError("lookback days must be non-negative")
    anchor = datetime.fromisoformat(committer_iso)
    if anchor.tzinfo is None:
        raise ValueError("committer timestamp needs a timezone")
    since = anchor.astimezone(UTC) - timedelta(days=days)
    return since.strftime("%Y-%m-%dT%H:%M:%SZ")


def subject_weight(subject: str) -> float:
    """Weight one commit subject the way escaped_defect_priority.py does."""
    if re.search(REVERT_SUBJECT_PATTERN, subject, re.IGNORECASE):
        return REVERT_WEIGHT
    if re.search(FIX_SUBJECT_PATTERN, subject, re.IGNORECASE):
        return FIX_WEIGHT
    return 0.0


def parse_name_only_log(raw: str) -> dict[str, dict[str, float | int]]:
    """Parse ``git log --name-only --pretty=format:%x00%s`` into per-path scores."""
    scores: dict[str, dict[str, float | int]] = {}
    weight = 0.0
    for line in raw.split("\n"):
        if line.startswith("\x00"):
            weight = subject_weight(line[1:])
            continue
        path = line.strip()
        if not path:
            continue
        row = scores.setdefault(path, {"escaped": 0.0, "churn": 0})
        row["churn"] = int(row["churn"]) + 1
        if weight:
            row["escaped"] = float(row["escaped"]) + weight
    return scores


def rank_targets(
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Sort by escaped-defect weight, then churn, then uncovered mass, then path."""

    def sort_key(row: dict[str, object]) -> tuple[float, int, int, str]:
        return (
            -float(row["escaped_defect_weight"]),
            -int(row["churn"]),
            -int(row["uncovered_statements_and_branches"]),
            str(row["path"]),
        )

    return sorted(rows, key=sort_key)


def landed_unit_reduction(
    *,
    merged: bool,
    coverage_artifact_available: bool,
    measured_unit_reduction: int | None,
) -> int | None:
    """Count a coverage delta only when the PR merged and the artifact exists.

    An unmerged PR contributes zero landed units. A merged PR without comparable
    evidence has unknown improvement, represented by None, even if the ledger
    counts no credit toward acceptance. A measured zero remains distinct.
    """
    if not merged:
        return 0
    if coverage_artifact_available:
        return measured_unit_reduction
    return None


def uncovered_statements_and_branches(summary: dict[str, int]) -> int:
    """Return missing statements plus missing branch outcomes."""
    return int(summary["missing_lines"]) + int(summary["missing_branches"])


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


RANKING_INPUTS_SHA256 = "de9d7b70280bbb6afe92ac5ba17a31ef7613be6bf1b60b8a141fd93cedf9f477"


def _ranking_inputs(root: Path) -> dict:
    """Validate bounded, pinned history without subprocesses or remote access."""
    path = root / "docs/evidence/issue-4426/ranking-inputs.json"
    if path.stat().st_size > 150_000:
        raise ValueError("ranking inputs exceed the byte limit")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != RANKING_INPUTS_SHA256:
        raise ValueError("ranking input digest mismatch")
    record = json.loads(data)
    if record["schema"] != "workflows.issue-4426-ranking-inputs/v1":
        raise ValueError("unexpected ranking input schema")
    if record["targets"] != list(TARGETS) or set(record["windows"]) != {"pre_round", "current"}:
        raise ValueError("unexpected ranking input scope")
    for window in record["windows"].values():
        if len(window["commits"]) > 256:
            raise ValueError("ranking inputs exceed the commit limit")
        if window["since"] != lookback_since(window["committer"]):
            raise ValueError("ranking input window mismatch")
        seen = set()
        for commit in window["commits"]:
            if not re.fullmatch(r"[0-9a-f]{40}", commit["oid"]) or commit["oid"] in seen:
                raise ValueError("invalid or duplicate ranking commit")
            seen.add(commit["oid"])
            if not commit["paths"] or not set(commit["paths"]) <= set(TARGETS):
                raise ValueError("unexpected ranking commit path")
    return record


def _input_window(root: Path, revision: str, since: str) -> dict:
    for window in _ranking_inputs(root)["windows"].values():
        if window["revision"] == revision and window["since"] == since:
            return window
    raise ValueError("revision/window is not in the pinned ranking inputs")


def _history_rows(
    repo: Path,
    revision: str,
    since: str,
    uncovered_by_path: dict[str, int],
    issue_targets: dict[str, dict[str, int]],
    extra_by_path: dict[str, dict[str, int | None]] | None = None,
) -> list[dict[str, object]]:
    window = _input_window(repo, revision, since)
    raw = "\n".join(
        "\x00" + commit["subject"] + "\n" + "\n".join(commit["paths"])
        for commit in window["commits"]
    )
    parsed = parse_name_only_log(raw)
    rows: list[dict[str, object]] = []
    for path in TARGETS:
        score = parsed.get(path, {"escaped": 0.0, "churn": 0})
        issue = issue_targets[path]
        extra = (extra_by_path or {}).get(path, {})
        rows.append(
            {
                "path": path,
                "escaped_defect_weight": float(score["escaped"]),
                "churn": int(score["churn"]),
                "fix_commit_touched": float(score["escaped"]) > 0,
                "uncovered_statements_and_branches": uncovered_by_path[path],
                "missing_lines": extra.get("missing_lines"),
                "missing_branches": extra.get("missing_branches"),
                "num_partial_branches": extra.get("num_partial_branches"),
                "num_statements": extra.get("num_statements"),
                "issue_rank": issue["rank"],
                "issue_escaped_defect_signals": issue["escaped_defect_signals"],
                "issue_churn": issue["churn"],
                "issue_uncovered_statements_and_branches": issue[
                    "uncovered_statements_and_branches"
                ],
                "snapshot_escaped_and_churn_match": (
                    float(score["escaped"]) == issue["escaped_defect_signals"]
                    and int(score["churn"]) == issue["churn"]
                ),
            }
        )
    ranked = rank_targets(rows)
    for index, row in enumerate(ranked, start=1):
        row["regenerated_rank"] = index
    return ranked


def build_ranking_record(root: Path = ROOT) -> dict:
    """Rebuild the historical ranking from pinned inputs and evidence files."""
    repo = root
    contract = _load(root / "docs/evidence/issue-4426/contract-3998.json")
    measurement = _load(root / "docs/evidence/issue-4426/coverage-measurement.json")
    inventory = _load(root / "docs/evidence/issue-4426/pr-inventory.json")
    issue_targets = {item["path"]: item for item in contract["ranking_method"]["targets"]}
    pre_round = measurement["pre_round"]["main_oid"]
    current = measurement["current"]["origin_main"]
    inputs = _ranking_inputs(root)["windows"]
    assert inputs["pre_round"]["revision"] == pre_round
    assert inputs["current"]["revision"] == current
    pre_iso = inputs["pre_round"]["committer"]
    current_iso = inputs["current"]["committer"]
    pre_since = lookback_since(pre_iso)
    current_since = lookback_since(current_iso)

    issue_uncovered = {
        path: int(issue_targets[path]["uncovered_statements_and_branches"]) for path in TARGETS
    }
    current_counters = measurement["current"]["targets_from_gate_coverage_json"]
    current_uncovered = {
        path: uncovered_statements_and_branches(current_counters[path]) for path in TARGETS
    }
    current_extra = {
        path: {
            "missing_lines": current_counters[path]["missing_lines"],
            "missing_branches": current_counters[path]["missing_branches"],
            "num_partial_branches": current_counters[path]["num_partial_branches"],
            "num_statements": current_counters[path]["num_statements"],
        }
        for path in TARGETS
    }
    pre_rows = _history_rows(repo, pre_round, pre_since, issue_uncovered, issue_targets)
    current_rows = _history_rows(
        repo,
        current,
        current_since,
        current_uncovered,
        issue_targets,
        current_extra,
    )

    pr_4000 = inventory["pull_requests"]["4000"]
    pr_4405 = inventory["pull_requests"]["4405"]
    unmerged_targets = pr_4405["coverage_artifacts"]["targets"]
    unmerged_units = {
        path: uncovered_statements_and_branches(unmerged_targets[path]) for path in TARGETS
    }
    counted_4000 = landed_unit_reduction(
        merged=pr_4000["state"] == "MERGED",
        coverage_artifact_available=pr_4000["coverage_artifacts"]["available"],
        measured_unit_reduction=None,
    )
    counted_4405 = landed_unit_reduction(
        merged=pr_4405["state"] == "MERGED" and pr_4405["merge_commit"] is not None,
        coverage_artifact_available=pr_4405["coverage_artifacts"]["available"],
        measured_unit_reduction=None,
    )
    per_file = []
    for path in TARGETS:
        issue_units = issue_uncovered[path]
        current_units = current_uncovered[path]
        per_file.append(
            {
                "path": path,
                "issue_units": issue_units,
                "current_gate_units": current_units,
                "unattributed_snapshot_difference": issue_units - current_units,
                "lines_plus_partial_branches": (
                    current_extra[path]["missing_lines"]
                    + current_extra[path]["num_partial_branches"]
                ),
                "unmerged_4405_units": unmerged_units[path],
                "counted_reduction": 0,
            }
        )
    issue_total = sum(issue_uncovered.values())
    current_total = sum(current_uncovered.values())
    partial_total = sum(item["lines_plus_partial_branches"] for item in per_file)
    unmerged_total = sum(unmerged_units.values())
    # No credited units does not establish zero actual improvement.
    counted = (counted_4000 or 0) + (counted_4405 or 0)
    return {
        "schema": "workflows.issue-4426-ranking/v1",
        "checked_on": CHECKED_ON,
        "methodology": {
            "source_repo": "stranske/Orchestrator",
            "source_path": "src/escaped_defect_priority.py",
            "source_blob": ORCHESTRATOR_BLOB,
            "retrieval_command": (
                "gh api repos/stranske/Orchestrator/contents/src/escaped_defect_priority.py"
            ),
            "coverage_autopilot_py_in_this_repo": False,
            "sort_keys": [
                "escaped_defect_weight",
                "churn",
                "uncovered_statements_and_branches",
            ],
            "not_by": "file size",
            "fix_subject_pattern": FIX_SUBJECT_PATTERN,
            "revert_subject_pattern": REVERT_SUBJECT_PATTERN,
            "revert_weight": REVERT_WEIGHT,
            "fix_weight": FIX_WEIGHT,
            "lookback_days": LOOKBACK_DAYS,
            "lookback_anchor": (
                "Committer timestamp of the ranked revision, converted to UTC, minus "
                "180 days. This is not wall-clock --since=180.days.ago."
            ),
            "git_command": (
                "git log <revision> --since=<utc-anchor> --no-merges --name-only "
                "--pretty=format:%x00%s"
            ),
            "uncovered_unit": "missing_lines + missing_branches",
            "partial_branch_role": (
                "num_partial_branches is recorded and is not the primary uncovered unit."
            ),
            "issue_snapshot_note": (
                "Issue #3998 integers are preserved. The fresh 180-day window at the "
                "pre-round commit reproduces escaped-defect weight and churn for "
                "scripts/langchain/issue_pr_context.py only. The other five targets differ, "
                "so the printed issue order is not assumed valid."
            ),
        },
        "revisions": {
            "pre_round": pre_round,
            "pre_round_committer": pre_iso,
            "pre_round_since": pre_since,
            "current_main": current,
            "current_committer": current_iso,
            "current_since": current_since,
            "gate_run_id": measurement["current"]["gate"]["run_id"],
            "pre_round_coverage_json_available": measurement["pre_round"]["gate"][
                "coverage_json_available"
            ],
        },
        "historical_issue_order": [item["path"] for item in contract["ranking_method"]["targets"]],
        "regenerated_pre_round": {
            "uncovered_mass_source": (
                "Issue #3998 listed units. Gate run 38980711116 has no coverage.json, "
                "so pre-round per-file missing lines and branches were not recomputed."
            ),
            "order": [row["path"] for row in pre_rows],
            "targets": pre_rows,
        },
        "regenerated_current": {
            "uncovered_mass_source": (
                "Gate run 42250720123 Python 3.14 coverage.json counters stored in "
                "coverage-measurement.json."
            ),
            "order": [row["path"] for row in current_rows],
            "targets": current_rows,
            "file_size_order": [
                row["path"]
                for row in sorted(
                    current_rows,
                    key=lambda item: (-int(item["num_statements"]), str(item["path"])),
                )
            ],
        },
        "final_head_reconciliation": measurement["final_head_reconciliation"],
        "target_snapshot_comparison": measurement["target_snapshot_comparison"],
        "term_report_reconciliation": {
            key: measurement["term_report_reconciliation"][key]
            for key in (
                "source",
                "source_sha256",
                "pre_round_missing_units_by_runtime",
                "final_head_missing_units",
                "unattributed_snapshot_difference_by_runtime",
                "attributable_round_reduction",
                "branch_arcs_recovered",
                "comparable_execution_configuration",
            )
        },
        "contributions": {
            "unit": "missing_lines + missing_branches",
            "numerical_rule_about_units": contract["numerical_rule"]["about_units"],
            "numerical_rule_status": contract["numerical_rule"]["replacement_forbidden"],
            "exception_applies": measurement["contract_decision"]["exception_applies"],
            "pre_round_at_least_90": measurement["contract_decision"]["pre_round_at_least_90"],
            "pull_requests": {
                "4000": {
                    "merged": pr_4000["state"] == "MERGED",
                    "merge_commit": pr_4000["merge_commit"],
                    "diff_paths": [item["path"] for item in pr_4000["files"]],
                    "coverage_artifact_available": pr_4000["coverage_artifacts"]["available"],
                    "measured_unit_reduction": None,
                    "counted_unit_reduction": counted_4000 or 0,
                    "attributable_unit_reduction": counted_4000,
                    "reason": (
                        "PR #4000 merged and added only tests/scripts/test_verifier_config.py. "
                        "Its Gate and selftest artifacts report total_count 0, so no coverage "
                        "delta was recovered. The snapshot-to-current verifier gap is not used "
                        "as that delta."
                    ),
                },
                "4405": {
                    "merged": pr_4405["state"] == "MERGED",
                    "merge_commit": pr_4405["merge_commit"],
                    "head_on_observed_main": pr_4405["head_on_observed_main"],
                    "coverage_artifact_available": pr_4405["coverage_artifacts"]["available"],
                    "artifact_describes_main": False,
                    "measured_landed_unit_reduction": None,
                    "counted_unit_reduction": counted_4405 or 0,
                    "attributable_unit_reduction": counted_4405,
                    "unmerged_target_units": unmerged_total,
                    "reason": (
                        "PR #4405 is open and its head is not on main. The downloaded coverage "
                        "counters describe that unmerged run. They are excluded from the landed "
                        "reduction and are not subtracted from the current Gate remainder."
                    ),
                },
            },
            "counted_landed_reduction": counted,
            "double_count_guard": (
                "Unmerged #4405 units are not added to the #4000 gap and are not subtracted "
                "from the current Gate remainder. The issue-snapshot difference is recorded "
                "separately and is not assigned to either pull request."
            ),
            "per_file": per_file,
            "issue_listed_units": issue_total,
            "current_gate_units": current_total,
            "unattributed_snapshot_difference": issue_total - current_total,
            "current_gate_units_lines_plus_partial_branches": partial_total,
            "remainder_current_gate_units": current_total,
            "about_180_met_by_counted_reduction": counted
            >= contract["numerical_rule"]["about_units"],
        },
    }


def render_ranking_markdown(record: dict) -> str:
    """Render the ranking record in the same order the tests lock."""
    method = record["methodology"]
    revisions = record["revisions"]
    contributions = record["contributions"]
    lines = [
        "# Issue #4426 regenerated coverage ranking",
        "",
        f"Checked {record['checked_on']}. Machine-readable fields are in `ranking.json`.",
        "The ranking commands are Orchestrator `src/escaped_defect_priority.py` "
        f"(blob `{method['source_blob']}`). `coverage-autopilot.py` is not in this repository. "
        "The preserved #3998 issue integers are not overwritten by this regeneration.",
        "",
        "## Method",
        "",
        "Sort keys are escaped-defect weight, then churn, then uncovered statements and "
        "branches. File size is not the ranking method. A revert subject weighs "
        f"{method['revert_weight']:g} and a fix subject weighs {method['fix_weight']:g}. "
        f"The window is {method['lookback_days']} days before the ranked revision's committer "
        "timestamp, in UTC. The git command is:",
        "",
        "```bash",
        method["git_command"],
        "```",
        "",
        f"Uncovered mass is `{method['uncovered_unit']}`. {method['partial_branch_role']}",
        method["issue_snapshot_note"],
        "",
        "## Regenerated order",
        "",
        f"Pre-round revision `{revisions['pre_round']}`, committer "
        f"`{revisions['pre_round_committer']}`, since `{revisions['pre_round_since']}`. "
        "Tier 3 uses the issue's listed units because that Gate run has no coverage.json.",
        "",
        "| Rank | Target | Escaped-defect weight | Churn | Issue uncovered units | Snapshot match |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in record["regenerated_pre_round"]["targets"]:
        lines.append(
            f"| {row['regenerated_rank']} | `{row['path']}` | "
            f"{row['escaped_defect_weight']:g} | {row['churn']} | "
            f"{row['uncovered_statements_and_branches']} | "
            f"{'yes' if row['snapshot_escaped_and_churn_match'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            f"Current main `{revisions['current_main']}`, committer "
            f"`{revisions['current_committer']}`, since `{revisions['current_since']}`. "
            f"Tier 3 uses Gate run {revisions['gate_run_id']}.",
            "",
            "| Rank | Target | Escaped-defect weight | Churn | Missing lines + branches | Statements |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in record["regenerated_current"]["targets"]:
        lines.append(
            f"| {row['regenerated_rank']} | `{row['path']}` | "
            f"{row['escaped_defect_weight']:g} | {row['churn']} | "
            f"{row['uncovered_statements_and_branches']} | {row['num_statements']} |"
        )
    historical = ", ".join(f"`{path}`" for path in record["historical_issue_order"])
    current_order = ", ".join(f"`{path}`" for path in record["regenerated_current"]["order"])
    size_order = ", ".join(f"`{path}`" for path in record["regenerated_current"]["file_size_order"])
    lines.extend(
        [
            "",
            f"Historical issue order: {historical}.",
            f"Regenerated current order: {current_order}.",
            f"Current file-size order: {size_order}.",
            "The regenerated order disagrees with both the issue snapshot and file size. "
            "`scripts/langchain/issue_pr_context.py` has more uncovered units than "
            "`scripts/langchain/verifier_config.py` and still ranks lower because its "
            "escaped-defect weight is lower.",
            "",
            "## Landed contribution and remainder",
            "",
            contributions["numerical_rule_status"],
            "The pre-round 90% close-without-a-PR exception is inactive: recovered coverage "
            "was below 90% when the round opened.",
            f"Counted landed reduction from #4000 and #4405: "
            f"{contributions['counted_landed_reduction']}.",
            contributions["double_count_guard"],
            "Counted credit is not actual improvement: #4000 attribution is unknown, "
            "not a measured zero. See final-head-gate.json for the verified later "
            "#4481 run and the unresolved comparable artifact recovery.",
            f"Log-derived final-head target units: "
            f"{record['term_report_reconciliation']['final_head_missing_units']}. "
            "Original-round log-derived units and the unattributed difference are "
            "recorded separately in coverage-measurement.json. These counters do not "
            "replace the historical downloaded Gate snapshot or establish attribution.",
            f"Issue-listed units: {contributions['issue_listed_units']}. "
            f"Current Gate units: {contributions['current_gate_units']}. "
            f"Unattributed snapshot difference: "
            f"{contributions['unattributed_snapshot_difference']}. "
            "That difference is not a #4000 measurement and is not added to the unmerged "
            "#4405 counters.",
            f"Lines plus partial branches on the current Gate artifact: "
            f"{contributions['current_gate_units_lines_plus_partial_branches']}. "
            "This alternate total is not the remainder.",
            f"Remainder on the current Gate artifact: "
            f"{contributions['remainder_current_gate_units']} uncovered statements and branches "
            "across the six targets.",
            (
                f"The counted reduction of {contributions['counted_landed_reduction']} meets "
                f"the about-{contributions['numerical_rule_about_units']} rule."
                if contributions["about_180_met_by_counted_reduction"]
                else f"The counted reduction of {contributions['counted_landed_reduction']} "
                f"leaves the about-{contributions['numerical_rule_about_units']} rule unmet."
            ),
            "",
            "| Target | Issue units | Current Gate units | Unattributed difference | "
            "Unmerged #4405 units | Counted reduction |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in contributions["per_file"]:
        lines.append(
            f"| `{row['path']}` | {row['issue_units']} | {row['current_gate_units']} | "
            f"{row['unattributed_snapshot_difference']} | {row['unmerged_4405_units']} | "
            f"{row['counted_reduction']} |"
        )
    lines.extend(
        [
            "",
            f"Unmerged #4405 target units sum to "
            f"{contributions['pull_requests']['4405']['unmerged_target_units']} and stay "
            "outside the remainder.",
            "",
        ]
    )
    comparison = record["target_snapshot_comparison"]
    lines.extend(
        [
            "## Original-round and final-head target accounting",
            "",
            f"Run {comparison['baseline_run_id']} (Python 3.12 and 3.13) versus "
            f"run {comparison['final_run_id']} (Python 3.14), artifact metadata "
            f"{comparison['final_artifact_id']}. Counters come from uniquely recovered "
            "term reports; archive bytes and branch arcs remain unavailable. "
            "The two baseline runtimes agree for these targets. Denominator changes "
            "are final minus baseline statements plus branches. Every target still "
            "requires comparable execution; no target exclusion is claimed. "
            "This table preserves the historical rankings above.",
            "",
            "| Target | Baseline units (3.12 / 3.13) | Final units | "
            "Unattributed difference (3.12 / 3.13) | Denominator change (3.12 / 3.13) | "
            "Attributable reduction |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in comparison["targets"]:
        baseline = row["baseline_missing_units_by_runtime"]
        difference = row["unattributed_difference_by_runtime"]
        denominator = row["denominator_change_by_runtime"]
        lines.append(
            f"| `{row['path']}` | {baseline['3.12']} / {baseline['3.13']} | "
            f"{row['final_missing_units']} | {difference['3.12']} / {difference['3.13']} | "
            f"{denominator['3.12']:+d} / {denominator['3.13']:+d} | "
            f"{row['attributable_round_reduction'] if row['attributable_round_reduction'] is not None else 'unknown'} |"
        )
    rows = comparison["targets"]
    baseline_totals = {
        version: sum(row["baseline_missing_units_by_runtime"][version] for row in rows)
        for version in ("3.12", "3.13")
    }
    final_total = sum(row["final_missing_units"] for row in rows)
    differences = {
        version: sum(row["unattributed_difference_by_runtime"][version] for row in rows)
        for version in ("3.12", "3.13")
    }
    lines.extend(
        [
            "",
            f"Totals are {baseline_totals['3.12']} / {baseline_totals['3.13']} baseline units, "
            f"{final_total} final units, and an unattributed snapshot difference of "
            f"{differences['3.12']} / {differences['3.13']} (Python 3.12 / 3.13).",
        ]
    )
    for row in rows:
        if all(value == 0 for value in row["unattributed_difference_by_runtime"].values()):
            lines.append(
                f"The zero snapshot difference for `{row['path']}` "
                "does not establish measured zero improvement."
            )
    attribution = comparison["attributable_round_reduction"]
    lines.extend(
        [
            (
                "Attributable round-wide reduction remains unknown."
                if attribution is None
                else f"Attributable round-wide reduction: {attribution}."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def test_subject_weights_follow_the_orchestrator_regex() -> None:
    assert subject_weight("fix(sync): keep the package removed") == FIX_WEIGHT
    assert subject_weight("Fix shared agent-tooling contracts") == FIX_WEIGHT
    assert subject_weight("fix sync test dependency scan (#2006)") == FIX_WEIGHT
    assert subject_weight('Revert "fix: one"') == REVERT_WEIGHT
    assert subject_weight("prefix the fix with care") == 0.0
    assert subject_weight("Fix/verifier skip placeholder content (#296)") == 0.0
    assert subject_weight("feat: add the module") == 0.0
    assert subject_weight("chore: consolidate cleanup") == 0.0


def test_lookback_is_anchored_to_the_revision_clock() -> None:
    assert lookback_since("2026-11-06T10:54:02-06:00") == "2026-05-10T16:54:02Z"
    assert lookback_since("2026-10-16T20:23:58-05:00") == "2026-04-20T01:23:58Z"
    with pytest.raises(ValueError, match="timezone"):
        lookback_since("2026-11-06T10:54:02")
    with pytest.raises(ValueError, match="non-negative"):
        lookback_since("2026-11-06T10:54:02Z", days=-1)


def test_rank_does_not_let_uncovered_mass_or_file_size_lead() -> None:
    ranked = rank_targets(
        [
            {
                "path": "large.py",
                "escaped_defect_weight": 0.0,
                "churn": 0,
                "uncovered_statements_and_branches": 9999,
            },
            {
                "path": "churn.py",
                "escaped_defect_weight": 0.0,
                "churn": 2,
                "uncovered_statements_and_branches": 1,
            },
            {
                "path": "defect.py",
                "escaped_defect_weight": 1.0,
                "churn": 0,
                "uncovered_statements_and_branches": 0,
            },
        ]
    )
    assert [row["path"] for row in ranked] == ["defect.py", "churn.py", "large.py"]


def test_landed_reduction_drops_unmerged_and_unmeasured_deltas() -> None:
    assert (
        landed_unit_reduction(
            merged=False,
            coverage_artifact_available=True,
            measured_unit_reduction=312,
        )
        == 0
    )
    assert (
        landed_unit_reduction(
            merged=True,
            coverage_artifact_available=False,
            measured_unit_reduction=14,
        )
        is None
    )
    assert (
        landed_unit_reduction(
            merged=True,
            coverage_artifact_available=True,
            measured_unit_reduction=14,
        )
        == 14
    )

    assert (
        landed_unit_reduction(
            merged=True, coverage_artifact_available=True, measured_unit_reduction=0
        )
        == 0
    )
    assert (
        landed_unit_reduction(
            merged=True, coverage_artifact_available=True, measured_unit_reduction=None
        )
        is None
    )


def test_final_target_accounting_does_not_overwrite_historical_rankings() -> None:
    record = build_ranking_record()
    comparison = record["target_snapshot_comparison"]
    assert comparison == _load(MEASUREMENT_PATH)["target_snapshot_comparison"]
    assert record["revisions"]["gate_run_id"] == 42250720123
    assert comparison["final_run_id"] == 42287174423
    assert len(comparison["targets"]) == 6
    markdown = render_ranking_markdown(record)
    assert (
        "| `scripts/sync_test_dependencies.py` | 6 / 6 | 6 | 0 / 0 | +51 / +51 | unknown |"
        in markdown
    )
    assert (
        "| `scripts/langchain/pr_verifier.py` | 283 / 283 | 200 | 83 / 83 | +874 / +874 | unknown |"
        in markdown
    )
    assert "Attributable round-wide reduction remains unknown." in markdown


def test_parser_weights_revert_above_fix_and_ignores_prose() -> None:
    raw = (
        "\x00fix: one\n"
        "scripts/langchain/pr_verifier.py\n"
        "\n"
        '\x00Revert "fix: one"\n'
        "scripts/langchain/pr_verifier.py\n"
        "\n"
        "\x00prefix the fix with care\n"
        "scripts/sync_test_dependencies.py\n"
    )
    parsed = parse_name_only_log(raw)
    assert parsed["scripts/langchain/pr_verifier.py"] == {"escaped": 4.0, "churn": 2}
    assert parsed["scripts/sync_test_dependencies.py"] == {"escaped": 0.0, "churn": 1}


def _ranking_record() -> tuple[Path, dict]:
    return ROOT, build_ranking_record(ROOT)


def test_regenerated_ranking_reorders_the_six_targets() -> None:
    _repo, record = _ranking_record()
    pre_round = {
        row["path"]: (row["escaped_defect_weight"], row["churn"])
        for row in record["regenerated_pre_round"]["targets"]
    }
    current = {
        row["path"]: (row["escaped_defect_weight"], row["churn"])
        for row in record["regenerated_current"]["targets"]
    }
    assert pre_round == PRE_ROUND_COUNTS
    assert current == CURRENT_COUNTS
    assert tuple(record["regenerated_pre_round"]["order"]) == PRE_ROUND_ORDER
    assert tuple(record["regenerated_current"]["order"]) == CURRENT_ORDER
    assert record["historical_issue_order"] == list(TARGETS)
    assert record["regenerated_current"]["order"] != record["historical_issue_order"]
    assert (
        record["regenerated_current"]["order"] != record["regenerated_current"]["file_size_order"]
    )
    matches = [
        row["path"]
        for row in record["regenerated_pre_round"]["targets"]
        if row["snapshot_escaped_and_churn_match"]
    ]
    assert matches == ["scripts/langchain/issue_pr_context.py"]

    by_path = {row["path"]: row for row in record["regenerated_current"]["targets"]}
    verifier = by_path["scripts/langchain/verifier_config.py"]
    context = by_path["scripts/langchain/issue_pr_context.py"]
    assert (
        context["uncovered_statements_and_branches"] > verifier["uncovered_statements_and_branches"]
    )
    assert context["regenerated_rank"] > verifier["regenerated_rank"]
    assert record["revisions"]["pre_round_since"] == "2026-04-20T01:23:58Z"
    assert record["revisions"]["current_since"] == "2026-05-10T16:54:02Z"
    assert record["revisions"]["pre_round_coverage_json_available"] is False


def test_pinned_per_file_subjects_match_the_recorded_history_scores() -> None:
    repo, record = _ranking_record()
    revisions = {
        record["revisions"]["pre_round"]: (
            record["revisions"]["pre_round_since"],
            record["regenerated_pre_round"]["targets"],
        ),
        record["revisions"]["current_main"]: (
            record["revisions"]["current_since"],
            record["regenerated_current"]["targets"],
        ),
    }
    for revision, (since, rows) in revisions.items():
        for row in rows:
            subjects = _input_window(repo, revision, since)["per_path_subjects"][row["path"]]
            assert len(subjects) == row["churn"]
            assert (
                sum(subject_weight(subject) for subject in subjects) == row["escaped_defect_weight"]
            )


def test_contribution_ledger_does_not_double_count() -> None:
    _repo, record = _ranking_record()
    contributions = record["contributions"]
    assert contributions["counted_landed_reduction"] == 0
    assert contributions["about_180_met_by_counted_reduction"] is False
    reconciled = record["term_report_reconciliation"]
    assert reconciled["pre_round_missing_units_by_runtime"] == {"3.12": 402, "3.13": 402}
    assert reconciled["final_head_missing_units"] == 238
    assert reconciled["unattributed_snapshot_difference_by_runtime"] == {"3.12": 164, "3.13": 164}
    assert reconciled["attributable_round_reduction"] is None
    assert reconciled["branch_arcs_recovered"] is False
    assert reconciled["comparable_execution_configuration"] is False
    assert contributions["numerical_rule_about_units"] == 180
    assert "does not replace" in contributions["numerical_rule_status"]
    assert contributions["exception_applies"] is False
    assert contributions["issue_listed_units"] == 398
    assert contributions["current_gate_units"] == 327
    assert contributions["remainder_current_gate_units"] == 327
    assert contributions["unattributed_snapshot_difference"] == 71
    assert contributions["current_gate_units_lines_plus_partial_branches"] == 287
    assert contributions["pull_requests"]["4000"]["counted_unit_reduction"] == 0
    assert contributions["pull_requests"]["4000"]["coverage_artifact_available"] is False
    assert contributions["pull_requests"]["4000"]["measured_unit_reduction"] is None
    assert contributions["pull_requests"]["4000"]["attributable_unit_reduction"] is None
    assert contributions["pull_requests"]["4405"]["merged"] is False
    assert contributions["pull_requests"]["4405"]["counted_unit_reduction"] == 0
    assert contributions["pull_requests"]["4405"]["unmerged_target_units"] == 312
    assert contributions["pull_requests"]["4405"]["artifact_describes_main"] is False
    assert contributions["pull_requests"]["4405"]["attributable_unit_reduction"] == 0
    per_file_difference = sum(
        item["unattributed_snapshot_difference"] for item in contributions["per_file"]
    )
    assert per_file_difference == contributions["unattributed_snapshot_difference"]
    assert sum(item["counted_reduction"] for item in contributions["per_file"]) == 0
    assert sum(item["current_gate_units"] for item in contributions["per_file"]) == 327
    assert sum(item["unmerged_4405_units"] for item in contributions["per_file"]) == 312
    # The unmerged total is not removed from the current remainder.
    assert (
        contributions["remainder_current_gate_units"]
        - contributions["pull_requests"]["4405"]["unmerged_target_units"]
        != contributions["remainder_current_gate_units"]
    )


def test_committed_ranking_record_matches_the_regeneration() -> None:
    _repo, record = _ranking_record()
    assert _load(RANKING_JSON) == record
    assert RANKING_MD.read_text(encoding="utf-8") == render_ranking_markdown(record)
    readme = (EVIDENCE / "README.md").read_text(encoding="utf-8")
    assert "ranking.md" in readme
    assert "327" in readme
    assert "about-180" in readme or "about 180" in readme


if __name__ == "__main__":
    record = build_ranking_record(ROOT)
    RANKING_JSON.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    RANKING_MD.write_text(render_ranking_markdown(record), encoding="utf-8")


def test_ranking_regeneration_never_invokes_subprocesses(monkeypatch) -> None:
    import subprocess

    def forbidden(*args, **kwargs):
        raise AssertionError("ranking validation must not run git or access the network")

    monkeypatch.setattr(subprocess, "run", forbidden)
    assert build_ranking_record(ROOT) == _load(RANKING_JSON)


def test_ranking_rejects_unpinned_or_unbounded_inputs(tmp_path: Path) -> None:
    path = tmp_path / "docs/evidence/issue-4426/ranking-inputs.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}")
    with pytest.raises(ValueError, match="digest mismatch"):
        _ranking_inputs(tmp_path)
    path.write_bytes(b" " * 150_001)
    with pytest.raises(ValueError, match="byte limit"):
        _ranking_inputs(tmp_path)


def test_ranking_rejects_an_unrecorded_revision_or_window() -> None:
    with pytest.raises(ValueError, match="not in the pinned"):
        _input_window(ROOT, "0" * 40, "2026-05-10T16:54:02Z")


def test_rendered_accounting_changes_with_record_values() -> None:
    record = copy.deepcopy(_load(RANKING_JSON))
    before = render_ranking_markdown(record)
    comparison = record["target_snapshot_comparison"]
    row = comparison["targets"][0]
    row["final_missing_units"] = 3
    row["baseline_missing_units_by_runtime"] = {"3.12": 9, "3.13": 10}
    row["unattributed_difference_by_runtime"] = {"3.12": 6, "3.13": 7}
    row["attributable_round_reduction"] = 2
    comparison["attributable_round_reduction"] = 2
    after = render_ranking_markdown(record)
    assert after != before
    assert "| 9 / 10 | 3 | 6 / 7 | +51 / +51 | 2 |" in after
    assert "Totals are 405 / 406 baseline units, 235 final units" in after
    assert "difference of 170 / 171" in after
    assert "The zero snapshot difference" not in after
    assert "Attributable round-wide reduction: 2." in after
    assert "Attributable round-wide reduction remains unknown." not in after
