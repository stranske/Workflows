"""Regression coverage for reclaiming stale belt claims without pull requests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / ".github" / "scripts" / "belt_claim_reclaim.js"


def _node(expression: str, payload: dict[str, Any]) -> Any:
    script = f"""
const helper = require({json.dumps(str(HELPER))});
const payload = JSON.parse(process.argv[1]);
const result = {expression};
process.stdout.write(JSON.stringify(result));
"""
    completed = subprocess.run(
        ["node", "-e", script, json.dumps(payload)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _sweep(payload: dict[str, Any]) -> Any:
    script = f"""
const helper = require({json.dumps(str(HELPER))});
const payload = JSON.parse(process.argv[1]);
const calls = [];
const github = {{
  paginate: async (method, args) => method(args),
  rest: {{
    issues: {{
      listForRepo: async () => payload.issues,
      listEventsForTimeline: async () => payload.timeline,
      get: async () => ({{ data: payload.currentIssue }}),
      listComments: async () => payload.comments,
      createComment: async (args) => calls.push(['comment', args.body]),
      removeLabel: async () => calls.push(['remove']),
    }},
  }},
}};
(async () => {{
  const result = await helper.sweepClaims({{
    withRetry: async (callback) => callback(github),
    owner: 'stranske',
    repo: 'Workflows',
    now: payload.now,
  }});
  process.stdout.write(JSON.stringify({{ result, calls }}));
}})();
"""
    completed = subprocess.run(
        ["node", "-e", script, json.dumps(payload)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_stale_claim_without_pr_is_reclaimed() -> None:
    stale = "2026-09-01T00:00:00Z"
    now = "2026-09-03T00:00:00Z"

    reclaimed = _node(
        "helper.evaluateClaim({ ...payload, now: payload.now })",
        {"claimTimestamp": stale, "linkedPullRequests": [], "now": now},
    )
    linked = _node(
        "helper.evaluateClaim({ ...payload, now: payload.now })",
        {
            "claimTimestamp": stale,
            "linkedPullRequests": [{"number": 42, "state": "open"}],
            "now": now,
        },
    )
    fresh = _node(
        "helper.evaluateClaim({ ...payload, now: payload.now })",
        {
            "claimTimestamp": "2026-09-02T12:00:00Z",
            "linkedPullRequests": [],
            "now": now,
        },
    )
    boundary = _node(
        "helper.evaluateClaim({ ...payload, now: payload.now })",
        {
            "claimTimestamp": "2026-09-02T00:00:00Z",
            "linkedPullRequests": [],
            "now": now,
        },
    )

    assert reclaimed["reclaim"] is True
    assert reclaimed["reason"] == "stale-without-pr"
    assert linked == {
        "reclaim": False,
        "stale": True,
        "ageMs": 172800000,
        "reason": "linked-pr-present",
    }
    assert fresh["reclaim"] is False
    assert fresh["reason"] == "inside-claim-window"
    assert boundary["reclaim"] is False
    assert boundary["reason"] == "inside-claim-window"


def test_drained_state_reports_a_reachable_zero() -> None:
    summary = _node("helper.buildSweepSummary(payload)", {"latchedCount": 0})

    assert summary.startswith("Belt claim sweep: none latched.")
    assert "in-progress=0 reclaimable=0" in summary


def test_reclaimable_count_is_reported_alongside_blocking_count() -> None:
    summary = _node(
        "helper.buildSweepSummary(payload)",
        {"latchedCount": 7, "reclaimableCount": 3},
    )

    assert "in-progress=7 reclaimable=3" in summary


def test_claim_and_reclaim_workflows_consume_the_shared_timeout() -> None:
    dispatcher = (ROOT / ".github/workflows/agents-71-codex-belt-dispatcher.yml").read_text()
    sweep = (ROOT / ".github/workflows/health-40-sweep.yml").read_text()
    dispatcher_workflow = yaml.safe_load(dispatcher)
    workflow = yaml.safe_load(sweep)

    transition = next(
        step
        for step in dispatcher_workflow["jobs"]["dispatch"]["steps"]
        if step.get("name") == "Transition issue to in-progress"
    )
    transition_script = transition["with"]["script"]
    assert "belt_claim_reclaim.js" in transition_script
    assert "CLAIM_STALE_MS" in transition_script
    assert "belt_claim_reclaim.js" in sweep
    assert "createTokenAwareRetry" in sweep
    assert "withRetry: retry.withRetry" in sweep
    assert "sweepClaims" in sweep
    assert "belt-claim-reclaim" in workflow["jobs"]


def test_consumer_keepalive_sweep_reclaims_stale_claims() -> None:
    consumer_sweep = (
        ROOT / "templates/consumer-repo/.github/workflows/agents-keepalive-sweep.yml"
    ).read_text()
    manifest = (ROOT / ".github/sync-manifest.yml").read_text()
    consumer_helper = ROOT / "templates/consumer-repo/.github/scripts/belt_claim_reclaim.js"

    assert "reclaim_stale_belt_claims" in consumer_sweep
    assert "belt_claim_reclaim.js" in consumer_sweep
    assert "withRetry: retry.withRetry" in consumer_sweep
    assert "source: .github/scripts/belt_claim_reclaim.js" in manifest
    assert consumer_helper.read_text() == HELPER.read_text()


def test_timeline_only_blocks_open_or_merged_pull_requests() -> None:
    events = [
        {
            "event": "cross-referenced",
            "source": {
                "issue": {
                    "number": 10,
                    "state": "closed",
                    "html_url": "https://example.test/pull/10",
                    "pull_request": {"merged_at": None},
                }
            },
        },
        {
            "event": "cross-referenced",
            "source": {
                "issue": {
                    "number": 11,
                    "state": "open",
                    "html_url": "https://example.test/pull/11",
                    "pull_request": {"merged_at": None},
                }
            },
        },
        {
            "event": "cross-referenced",
            "source": {
                "issue": {
                    "number": 12,
                    "state": "closed",
                    "html_url": "https://example.test/pull/12",
                    "pull_request": {"merged_at": "2026-09-02T00:00:00Z"},
                }
            },
        },
        {
            "event": "connected",
            "subject": {
                "issue": {
                    "number": 13,
                    "state": "closed",
                    "html_url": "https://example.test/pull/13",
                    "pull_request": {},
                }
            },
        },
    ]

    blocking = _node("helper.blockingPullRequestsFromTimeline(payload.events)", {"events": events})

    assert [entry["number"] for entry in blocking] == [11, 12, 13]


def test_sweep_revalidates_and_comments_before_removing_label() -> None:
    claim_timestamp = "2026-09-01T00:00:00Z"
    result = _sweep(
        {
            "issues": [{"number": 3405}],
            "currentIssue": {"labels": [{"name": "status:in-progress"}]},
            "timeline": [
                {
                    "event": "labeled",
                    "label": {"name": "status:in-progress"},
                    "created_at": claim_timestamp,
                }
            ],
            "comments": [],
            "now": "2026-09-03T00:00:00Z",
        }
    )

    assert result["result"]["reclaimedCount"] == 1
    assert [call[0] for call in result["calls"]] == ["comment", "remove"]
    assert "2026-09-01T00:00:00.000Z" in result["calls"][0][1]
    assert "no linked open or merged PR" in result["calls"][0][1]


def test_latest_reapplied_claim_supersedes_the_old_timestamp() -> None:
    result = _node(
        "helper.latestClaimTimestamp(payload.events)",
        {
            "events": [
                {
                    "event": "labeled",
                    "label": {"name": "status:in-progress"},
                    "created_at": "2026-09-01T00:00:00Z",
                },
                {
                    "event": "labeled",
                    "label": {"name": "status:in-progress"},
                    "created_at": "2026-09-02T12:00:00Z",
                },
            ]
        },
    )

    assert result == "2026-09-02T12:00:00.000Z"
