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
const graphqlCalls = [];
const github = {{
  paginate: async (method, args) => method(args),
  graphql: async (_query, args) => {{
    graphqlCalls.push(args);
    const graphStatus = payload.graphqlErrorsByIssue?.[args.number];
    if (graphStatus) {{
      const error = new Error(`graphql failed: ${{graphStatus}}`);
      error.status = graphStatus;
      throw error;
    }}
    const linked = payload.linkedPullRequestsByIssue?.[args.number]
      ?? payload.linkedPullRequests
      ?? [];
    return {{
      repository: {{
        issue: {{
          closedByPullRequestsReferences: {{
            nodes: linked,
            pageInfo: {{ hasNextPage: false, endCursor: null }},
          }},
        }},
      }},
    }};
  }},
  rest: {{
    issues: {{
      listForRepo: async () => payload.issues,
      listEventsForTimeline: async (args) =>
        payload.timelines?.[args.issue_number] ?? payload.timeline,
      get: async (args) => ({{
        data: payload.currentIssues?.[args.issue_number] ?? payload.currentIssue,
      }}),
      listComments: async () => payload.comments,
      createComment: async (args) => calls.push(['comment', args.body]),
      removeLabel: async (args) => {{
        const status = payload.removeLabelStatuses?.[args.issue_number]
          ?? payload.removeLabelStatus;
        if (status) {{
          const error = new Error(`removeLabel failed: ${{status}}`);
          error.status = status;
          throw error;
        }}
        calls.push(['remove', args.issue_number]);
      }},
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
  process.stdout.write(JSON.stringify({{ result, calls, graphqlCalls }}));
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


def _linked(payload: dict[str, Any]) -> Any:
    script = f"""
const helper = require({json.dumps(str(HELPER))});
const payload = JSON.parse(process.argv[1]);
const calls = [];
const github = {{
  graphql: async (_query, args) => {{
    calls.push(args);
    const key = args.after ?? 'first';
    return payload.pages[key];
  }},
}};
(async () => {{
  try {{
    const result = await helper.readLinkedPullRequests(
      async (callback) => callback(github),
      'stranske',
      'Workflows',
      3405
    );
    process.stdout.write(JSON.stringify({{ result, calls }}));
  }} catch (error) {{
    process.stdout.write(JSON.stringify({{ error: error.message, calls }}));
  }}
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
    assert consumer_helper.read_bytes() == HELPER.read_bytes()


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
    ]

    blocking = _node("helper.blockingPullRequestsFromTimeline(payload.events)", {"events": events})

    assert [entry["number"] for entry in blocking] == [11, 12]


def test_connected_event_uses_graphql_linked_prs_and_blocks_reclaim() -> None:
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
                },
                {"event": "connected", "created_at": claim_timestamp},
            ],
            "linkedPullRequests": [
                {
                    "number": 3550,
                    "url": "https://example.test/pull/3550",
                    "state": "OPEN",
                    "mergedAt": None,
                }
            ],
            "comments": [],
            "now": "2026-09-03T00:00:00Z",
        }
    )

    assert result["result"]["reclaimableCount"] == 0
    assert result["calls"] == []
    assert result["graphqlCalls"][0] == {
        "owner": "stranske",
        "repo": "Workflows",
        "number": 3405,
        "after": None,
    }


def test_remove_label_404_is_reported_as_already_released() -> None:
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
            "linkedPullRequests": [],
            "comments": [],
            "removeLabelStatus": 404,
            "now": "2026-09-03T00:00:00Z",
        }
    )

    assert result["result"]["reclaimedCount"] == 0
    assert result["result"]["alreadyReleasedCount"] == 1
    assert result["result"]["failures"] == []


def test_linked_pr_lookup_paginates_and_blocks_on_page_two() -> None:
    result = _linked(
        {
            "pages": {
                "first": {
                    "repository": {
                        "issue": {
                            "closedByPullRequestsReferences": {
                                "nodes": [],
                                "pageInfo": {"hasNextPage": True, "endCursor": "page-2"},
                            }
                        }
                    }
                },
                "page-2": {
                    "repository": {
                        "issue": {
                            "closedByPullRequestsReferences": {
                                "nodes": [
                                    {
                                        "number": 3550,
                                        "url": "https://example.test/pull/3550",
                                        "state": "MERGED",
                                        "mergedAt": "2026-09-24T08:00:00Z",
                                    }
                                ],
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                            }
                        }
                    }
                },
            }
        }
    )

    assert result["result"] == [
        {
            "number": 3550,
            "state": "merged",
            "merged": True,
            "url": "https://example.test/pull/3550",
        }
    ]
    assert [call["after"] for call in result["calls"]] == [None, "page-2"]


def test_one_issue_graphql_failure_does_not_skip_later_issue() -> None:
    claim_timestamp = "2026-09-01T00:00:00Z"
    timeline = [
        {
            "event": "labeled",
            "label": {"name": "status:in-progress"},
            "created_at": claim_timestamp,
        }
    ]
    result = _sweep(
        {
            "issues": [{"number": 3405}, {"number": 3406}],
            "currentIssues": {
                "3405": {"labels": [{"name": "status:in-progress"}]},
                "3406": {"labels": [{"name": "status:in-progress"}]},
            },
            "timelines": {"3405": timeline, "3406": timeline},
            "graphqlErrorsByIssue": {"3405": 503},
            "linkedPullRequestsByIssue": {"3406": []},
            "comments": [],
            "now": "2026-09-03T00:00:00Z",
        }
    )

    assert result["result"]["reclaimedCount"] == 1
    assert result["result"]["failures"] == [
        {
            "issueNumber": 3405,
            "phase": "assessment",
            "status": 503,
            "message": "graphql failed: 503",
        }
    ]
    assert ["remove", 3406] in result["calls"]


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
