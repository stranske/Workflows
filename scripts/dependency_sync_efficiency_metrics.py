#!/usr/bin/env python3
"""Produce an auditable dependency/sync maintenance-efficiency report.

The collector intentionally accepts a portable JSON snapshot.  That keeps the
calculation hermetic, makes partial GitHub history explicit, and lets the
scheduled workflow remain a thin data collector rather than a second policy
engine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any

LANES = ("dependency-bot", "sync-generated", "dev-tool-sync", "traditional")
THRESHOLDS = {
    "generated_prs": 40,
    "stale_or_replacement_rate": 0.05,
    "avoidable_replacements_per_repo_batch": 0,
    "agent_exception_episodes": 5,
    "stable_force_pushes_per_pr": 1.0,
    "stable_ready_transitions_per_pr": 1.0,
    "stable_median_review_settlement_minutes": 30.0,
}
STABLE_SYNC_BRANCHES = {"sync/workflows-candidate", "sync/workflows-delivery"}


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except (AttributeError, OverflowError, TypeError, ValueError):
        return None


def first(value: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if value.get(key) is not None:
            return value[key]
    return None


def labels(pr: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for item in pr.get("labels", []):
        if not item:
            continue
        name = item.get("name", item) if isinstance(item, dict) else item
        result.add(str(name).lower())
    return result


def lane_for(pr: dict[str, Any]) -> str:
    repo = str(first(pr, "repo", "repository", "repository_name") or "")
    if repo.endswith("/Collab-Admin"):
        return "collab-admin-excluded"
    author = str(first(pr, "author", "author_login", "user") or "").lower()
    branch = str(first(pr, "head_ref", "headRefName", "branch") or "").lower()
    title = str(pr.get("title", "")).lower()
    if branch.startswith("deps/sync-dev-versions-") or "sync dev versions" in title:
        return "dev-tool-sync"
    if branch.startswith("sync/workflows-") or "sync workflow templates" in title:
        return "sync-generated"
    if author in {"dependabot[bot]", "renovate[bot]", "app/dependabot", "app/renovate"}:
        return "dependency-bot"
    if branch.startswith(("dependabot/", "renovate/")) or "dependencies" in labels(pr):
        return "dependency-bot"
    return "traditional"


def generated(lane: str) -> bool:
    return lane in {"dependency-bot", "sync-generated", "dev-tool-sync"}


def replacement(pr: dict[str, Any]) -> bool:
    haystack = " ".join(
        str(pr.get(key, "")) for key in ("title", "body", "terminal_disposition")
    ).lower()
    return "supersedes #" in haystack or "superseded" in haystack or "replacement" in haystack


def state(pr: dict[str, Any]) -> str:
    return str(first(pr, "state", "status") or "open").lower()


def is_stale(pr: dict[str, Any], now: datetime) -> bool:
    if state(pr) != "open":
        return False
    updated = parse_time(first(pr, "updated_at", "updatedAt", "created_at", "createdAt"))
    return bool(updated and now - updated > timedelta(days=7))


def exception_fingerprint(pr: dict[str, Any]) -> str | None:
    explicit = str(pr.get("exception_fingerprint", "")).strip()
    if explicit:
        return explicit
    if not pr.get("check_failure_cluster") and not pr.get("review_thread_ids"):
        return None
    payload = {
        "repo": first(pr, "repo", "repository", "repository_name"),
        "head": first(pr, "head_sha", "headRefOid"),
        "checks": sorted(pr.get("check_failure_cluster", [])),
        "threads": sorted(pr.get("review_thread_ids", [])),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def reporting_window(snapshot: dict[str, Any], now: datetime) -> tuple[datetime, datetime]:
    """Return inclusive-start/exclusive-end bounds for weekly event counts."""
    period = snapshot.get("period") or {}
    start = parse_time(period.get("start"))
    end = parse_time(period.get("end"))
    if start and end:
        return start, end
    return now - timedelta(days=7), now


def in_window(value: str | None, start: datetime, end: datetime) -> bool:
    stamp = parse_time(value)
    return bool(stamp and start <= stamp < end)


def elapsed_minutes(start: str | None, end: str | None) -> float | None:
    start_at = parse_time(start)
    end_at = parse_time(end)
    if not start_at or not end_at or end_at < start_at:
        return None
    return round((end_at - start_at).total_seconds() / 60, 1)


def stable_sync_key(pr: dict[str, Any]) -> str | None:
    if lane_for(pr) != "sync-generated":
        return None
    branch = str(first(pr, "head_ref", "headRefName", "branch") or "").lower()
    if branch not in STABLE_SYNC_BRANCHES:
        return None
    return f"{first(pr, 'repo', 'repository', 'repository_name')}#{pr.get('number', '?')}"


def calculate(snapshot: dict[str, Any], now: datetime) -> dict[str, Any]:
    pulls = list(snapshot.get("pulls", []))
    window_start, window_end = reporting_window(snapshot, now)
    lane_counts: Counter[str] = Counter()
    created: Counter[str] = Counter()
    merged: Counter[str] = Counter()
    closed: Counter[str] = Counter()
    stale: Counter[str] = Counter()
    replacements: Counter[str] = Counter()
    source_to_prs: dict[str, set[str]] = defaultdict(set)
    exception_fingerprints: set[str] = set()
    generated_prs: list[dict[str, Any]] = []
    stable_sync_prs: dict[str, dict[str, Any]] = {}
    timestamped_snapshot = False

    for pr in pulls:
        lane = lane_for(pr)
        pr["_lane"] = lane
        if lane == "collab-admin-excluded":
            continue
        lane_counts[lane] += 1
        if not generated(lane):
            continue
        generated_prs.append(pr)
        stable_key = stable_sync_key(pr)
        if stable_key:
            stable_sync_prs[stable_key] = pr
        created_at = first(pr, "created_at", "createdAt")
        merged_at = first(pr, "merged_at", "mergedAt")
        closed_at = first(pr, "closed_at", "closedAt")
        pr_has_times = bool(created_at or merged_at or closed_at)
        timestamped_snapshot = timestamped_snapshot or pr_has_times
        pr_state = state(pr)

        if pr_has_times:
            if in_window(created_at, window_start, window_end):
                created[lane] += 1
            if in_window(merged_at, window_start, window_end):
                merged[lane] += 1
            elif in_window(closed_at, window_start, window_end) and pr_state == "closed":
                closed[lane] += 1
        else:
            # Legacy fixtures omit event times; treat snapshot membership as the week.
            created[lane] += 1
            if merged_at or pr_state == "merged":
                merged[lane] += 1
            elif pr_state == "closed":
                closed[lane] += 1

        if is_stale(pr, now):
            stale[lane] += 1
        if replacement(pr):
            replacements[lane] += 1
        source = str(
            first(
                pr, "source_commit", "sourceCommit", "wave_id", "batch_id", "head_sha", "headRefOid"
            )
            or "unknown"
        )
        pr["_source"] = source
        source_to_prs[source].add(
            f"{first(pr, 'repo', 'repository', 'repository_name')}#{pr.get('number', '?')}"
        )
        fingerprint = exception_fingerprint(pr)
        if fingerprint:
            exception_fingerprints.add(fingerprint)

    collab_admin = [pr for pr in pulls if pr.get("_lane") == "collab-admin-excluded"]
    runs_by_source: Counter[str] = Counter()
    for run in snapshot.get("workflow_runs", []):
        source = str(first(run, "source_commit", "head_sha", "headSha") or "unknown")
        runs_by_source[source] += 1
    if timestamped_snapshot:
        generated_total = sum(created[lane] for lane in LANES)
        rate_universe = [
            pr
            for pr in generated_prs
            if in_window(first(pr, "created_at", "createdAt"), window_start, window_end)
            or (
                not first(pr, "created_at", "createdAt")
                and (
                    in_window(first(pr, "merged_at", "mergedAt"), window_start, window_end)
                    or in_window(first(pr, "closed_at", "closedAt"), window_start, window_end)
                    or in_window(first(pr, "updated_at", "updatedAt"), window_start, window_end)
                )
            )
        ]
    else:
        generated_total = len(generated_prs)
        rate_universe = generated_prs
    stale_or_replacement = {
        f"{first(pr, 'repo', 'repository', 'repository_name')}#{pr.get('number', '?')}"
        for pr in rate_universe
        if is_stale(pr, now) or replacement(pr)
    }
    replacement_rate = len(stale_or_replacement) / generated_total if generated_total else 0.0
    amplification = {
        source: len(prs) for source, prs in sorted(source_to_prs.items()) if source != "unknown"
    }
    actions_per_source = {source: runs_by_source.get(source, 0) for source in amplification}
    avoidable_replacements: Counter[str] = Counter()
    for pr in generated_prs:
        if not replacement(pr):
            continue
        repo = str(first(pr, "repo", "repository", "repository_name") or "unknown")
        batch = str(pr["_source"])
        avoidable_replacements[f"{repo}/{batch}"] += 1

    stable_event_counts: dict[str, Counter[str]] = {key: Counter() for key in stable_sync_prs}
    for event in snapshot.get("timeline_events", []):
        key = f"{first(event, 'repo', 'repository', 'repository_name')}#{event.get('number', '?')}"
        if key not in stable_event_counts:
            continue
        event_at = first(event, "created_at", "submitted_at", "createdAt", "submittedAt")
        if event_at and not in_window(event_at, window_start, window_end):
            continue
        event_name = str(first(event, "event", "type") or "unknown").lower()
        stable_event_counts[key][event_name] += 1

    stable_churn: dict[str, dict[str, Any]] = {}
    review_settlement_minutes: list[float] = []
    head_to_seal_minutes: list[float] = []
    for key, pr in sorted(stable_sync_prs.items()):
        events = stable_event_counts[key]
        delivery = pr.get("delivery_record") if isinstance(pr.get("delivery_record"), dict) else {}
        review_minutes = elapsed_minutes(
            delivery.get("review_started_at"), delivery.get("sealed_at")
        )
        seal_minutes = elapsed_minutes(delivery.get("head_observed_at"), delivery.get("sealed_at"))
        if review_minutes is not None:
            review_settlement_minutes.append(review_minutes)
        if seal_minutes is not None:
            head_to_seal_minutes.append(seal_minutes)
        stable_churn[key] = {
            "force_pushes": events["head_ref_force_pushed"],
            "ready_transitions": events["ready_for_review"],
            "draft_transitions": events["converted_to_draft"],
            "review_requests": events["review_requested"],
            "review_submissions": events["reviewed"],
            "delivery_state": delivery.get("delivery_state"),
            "review_settlement_minutes": review_minutes,
            "head_to_seal_minutes": seal_minutes,
        }

    stable_pr_count = len(stable_sync_prs)
    stable_force_pushes = sum(item["force_pushes"] for item in stable_churn.values())
    stable_ready_transitions = sum(item["ready_transitions"] for item in stable_churn.values())
    force_pushes_per_pr = stable_force_pushes / stable_pr_count if stable_pr_count else 0.0
    ready_transitions_per_pr = (
        stable_ready_transitions / stable_pr_count if stable_pr_count else 0.0
    )
    median_review_settlement = (
        round(float(median(review_settlement_minutes)), 1) if review_settlement_minutes else None
    )
    median_head_to_seal = (
        round(float(median(head_to_seal_minutes)), 1) if head_to_seal_minutes else None
    )
    period = dict(snapshot.get("period") or {})
    # Persist concrete bounds only when the collector supplied them so fingerprints
    # stay stable across generation timestamps for otherwise identical evidence.
    if "start" not in period and snapshot.get("period"):
        period["start"] = window_start.isoformat().replace("+00:00", "Z")
    if "end" not in period and snapshot.get("period"):
        period["end"] = window_end.isoformat().replace("+00:00", "Z")
    metrics = {
        "period": period,
        "lane_counts": {lane: lane_counts[lane] for lane in LANES},
        "created": {lane: created[lane] for lane in LANES},
        "merged": {lane: merged[lane] for lane in LANES},
        "closed": {lane: closed[lane] for lane in LANES},
        "stale": {lane: stale[lane] for lane in LANES},
        "replacement": {lane: replacements[lane] for lane in LANES},
        "generated_prs": generated_total,
        "stale_or_replacement_numerator": len(stale_or_replacement),
        "stale_or_replacement_rate": replacement_rate,
        "source_change_to_consumer_pr_amplification": amplification,
        "actions_runs_per_source_change": actions_per_source,
        "avoidable_replacements_per_repo_batch": dict(sorted(avoidable_replacements.items())),
        "agent_exception_fingerprints": sorted(exception_fingerprints),
        "agent_exception_episodes": len(exception_fingerprints),
        "collab_admin_excluded": len(collab_admin),
        "stable_sync_prs_observed": stable_pr_count,
        "stable_pr_force_push_events": stable_force_pushes,
        "stable_pr_ready_for_review_events": stable_ready_transitions,
        "stable_pr_converted_to_draft_events": sum(
            item["draft_transitions"] for item in stable_churn.values()
        ),
        "stable_pr_review_requested_events": sum(
            item["review_requests"] for item in stable_churn.values()
        ),
        "stable_pr_review_submitted_events": sum(
            item["review_submissions"] for item in stable_churn.values()
        ),
        "stable_force_pushes_per_pr": force_pushes_per_pr,
        "stable_ready_transitions_per_pr": ready_transitions_per_pr,
        "stable_median_review_settlement_minutes": median_review_settlement,
        "stable_median_head_to_seal_minutes": median_head_to_seal,
        "stable_pr_churn": stable_churn,
    }
    breaches = {
        "generated_prs": generated_total > THRESHOLDS["generated_prs"],
        "stale_or_replacement_rate": replacement_rate >= THRESHOLDS["stale_or_replacement_rate"],
        "avoidable_replacements_per_repo_batch": any(
            count > THRESHOLDS["avoidable_replacements_per_repo_batch"]
            for count in avoidable_replacements.values()
        ),
        "agent_exception_episodes": len(exception_fingerprints)
        > THRESHOLDS["agent_exception_episodes"],
        "stable_force_pushes_per_pr": force_pushes_per_pr
        > THRESHOLDS["stable_force_pushes_per_pr"],
        "stable_ready_transitions_per_pr": ready_transitions_per_pr
        > THRESHOLDS["stable_ready_transitions_per_pr"],
        "stable_median_review_settlement_minutes": median_review_settlement is not None
        and median_review_settlement > THRESHOLDS["stable_median_review_settlement_minutes"],
    }
    collection = snapshot.get("collection", {})
    return {
        "schema": "dependency-sync-efficiency/v1",
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "collection": {
            "history_complete": bool(collection.get("history_complete", False)),
            "window_complete": bool(collection.get("window_complete", False)),
            "failures": list(collection.get("failures", [])),
            "limitations": list(collection.get("limitations", [])),
        },
        "metrics": metrics,
        "thresholds": THRESHOLDS,
        "advisory_slo": {
            "breaches": breaches,
            "state": "breach" if any(breaches.values()) else "baseline-pass",
        },
    }


def fingerprint(report: dict[str, Any]) -> str:
    evidence = {
        "collection": report["collection"],
        "metrics": report["metrics"],
        "advisory_slo": report["advisory_slo"],
    }
    return hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()[:16]


def markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    rows = [
        "| Lane | Created | Merged | Closed | Stale | Replacements |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for lane in LANES:
        rows.append(
            "| {lane} | {created} | {merged} | {closed} | {stale} | {replacement} |".format(
                lane=lane,
                created=metrics["created"][lane],
                merged=metrics["merged"][lane],
                closed=metrics["closed"][lane],
                stale=metrics["stale"][lane],
                replacement=metrics["replacement"][lane],
            )
        )
    limitations = report["collection"]["limitations"] or ["No collection limitations reported."]
    avoidable = metrics.get("avoidable_replacements_per_repo_batch") or {}
    avoidable_lines = [
        f"Avoidable replacement repository/batches: **{len(avoidable)}** (target = 0)",
        *[f"- Avoidable replacement: {key} ({count})" for key, count in avoidable.items()],
    ]
    period = metrics.get("period") or {}
    period_line = ""
    if period.get("start") and period.get("end"):
        period_line = f"Reporting window: **{period['start']}** → **{period['end']}**"
    stable_rows = [
        "| Stable PR | Force pushes | Ready | Draft | Reviews | Review to seal | Head to seal |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key, item in metrics["stable_pr_churn"].items():
        review_to_seal = (
            f"{item['review_settlement_minutes']:.1f}m"
            if item["review_settlement_minutes"] is not None
            else "n/a"
        )
        head_to_seal = (
            f"{item['head_to_seal_minutes']:.1f}m"
            if item["head_to_seal_minutes"] is not None
            else "n/a"
        )
        stable_rows.append(
            f"| {key} | {item['force_pushes']} | {item['ready_transitions']} | "
            f"{item['draft_transitions']} | {item['review_submissions']} | "
            f"{review_to_seal} | {head_to_seal} |"
        )
    if not metrics["stable_pr_churn"]:
        stable_rows.append("| No stable sync PRs observed | 0 | 0 | 0 | 0 | n/a | n/a |")
    median_review = metrics["stable_median_review_settlement_minutes"]
    median_seal = metrics["stable_median_head_to_seal_minutes"]
    return "\n".join(
        [
            "# Dependency/sync maintenance efficiency",
            "",
            f"Advisory SLO state: **{report['advisory_slo']['state']}**.",
            *([period_line, ""] if period_line else []),
            *rows,
            "",
            f"Generated PRs: **{metrics['generated_prs']}** (target ≤ {THRESHOLDS['generated_prs']})",
            f"Stale/replacement rate: **{metrics['stale_or_replacement_rate']:.1%}** ({metrics['stale_or_replacement_numerator']}/{metrics['generated_prs']}; target < 5%)",
            *avoidable_lines,
            f"Agent-exception episodes: **{metrics['agent_exception_episodes']}** (target ≤ 5)",
            f"Collab-Admin excluded: **{metrics['collab_admin_excluded']}**",
            "",
            "## Stable delivery convergence",
            "",
            *stable_rows,
            "",
            f"Stable PRs observed: **{metrics['stable_sync_prs_observed']}**",
            f"Force pushes per stable PR: **{metrics['stable_force_pushes_per_pr']:.2f}** "
            f"(target ≤ {THRESHOLDS['stable_force_pushes_per_pr']:.0f})",
            f"Ready transitions per stable PR: **{metrics['stable_ready_transitions_per_pr']:.2f}** "
            f"(target ≤ {THRESHOLDS['stable_ready_transitions_per_pr']:.0f})",
            "Median review-to-seal time: **{}** (target ≤ {:.0f}m)".format(
                f"{median_review:.1f}m" if median_review is not None else "n/a",
                THRESHOLDS["stable_median_review_settlement_minutes"],
            ),
            "Median head-to-seal time: **{}**".format(
                f"{median_seal:.1f}m" if median_seal is not None else "n/a"
            ),
            "",
            "## Collection limits",
            "",
            f"Complete GitHub history: **{str(report['collection']['history_complete']).lower()}**.",
            f"Complete reporting window: **{str(report['collection']['window_complete']).lower()}**.",
            *[f"- Collection failure: {item}" for item in report["collection"]["failures"]],
            *[f"- {item}" for item in limitations],
            "",
            f"Evidence fingerprint: `{fingerprint(report)}`",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--json-out", required=True, type=Path)
    parser.add_argument("--markdown-out", required=True, type=Path)
    parser.add_argument("--now")
    args = parser.parse_args()
    now = parse_time(args.now) if args.now else datetime.now(UTC)
    report = calculate(json.loads(args.input.read_text(encoding="utf-8")), now or datetime.now(UTC))
    args.json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_out.write_text(markdown(report), encoding="utf-8")
    print(f"fingerprint={fingerprint(report)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
