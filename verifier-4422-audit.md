# Verifier 4422 audit

Audit check time: 2026-11-06T18:26:25Z. Timezone of this stamp: UTC.
Campaign check date: 2026-10-24. Clock time on that date: unknown. Timezone of the bare date: unknown.
Stated issue, comment, and pull-request timestamps use a Z suffix, so those instants are UTC.

This file records the campaign definition recovered before any production verifier edit.
The initial evidence check below is one GitHub run lookup. It does not download logs or artifacts,
does not query another repository, and does not reconstruct the historical population.

## Recovered campaign definition

Recovery commands, run on 2026-11-06:

- `gh issue view 4036 --repo stranske/Workflows --comments`
- `gh issue view 4422 --repo stranske/Workflows --comments`
- `gh pr view 4037 --repo stranske/Workflows --comments`

Reprint command, no network:

```text
python3 verifier_4422_audit.py campaign-definition
```

`python3` in this checkout is the repository CI interpreter, Python 3.14
(`/opt/hostedtoolcache/Python/3.14.10/x64/bin/python3`).
`/opt/anaconda3/bin/python3` is not installed here.

```json
{
  "facts": {
    "baseline_measurement_text": "Measured 2026-10-17 on the 17 PRs merged for released issues since 01:45Z: 16 of 17 source issues are still OPEN after merge",
    "baseline_since_clock": "01:45Z",
    "baseline_since_date": "unknown",
    "counter_risk_1158_reopen_clock": "04:12Z",
    "counter_risk_1158_reopen_date": "unknown",
    "issue_4036_closed_at": "2026-11-03T15:06:42Z",
    "issue_4036_created_at": "2026-10-17T12:00:41Z",
    "issue_4036_state": "closed",
    "issue_4422_created_at": "2026-11-03T15:06:40Z",
    "pr_4037_head_ref_oid": "81424fd16d450008afe612c1198328f2ff72a822",
    "pr_4037_merge_commit": "021ec67ef580c83a88402a1574e27ea34db14dde",
    "pr_4037_merged_at": "2026-10-18T02:31:22Z"
  },
  "issue_4036_timeline": [
    {
      "event": "closed",
      "timestamp": "2026-10-18T02:31:24Z"
    },
    {
      "event": "reopened",
      "timestamp": "2026-10-18T02:31:47Z"
    },
    {
      "event": "closed",
      "timestamp": "2026-11-03T00:31:08Z"
    },
    {
      "event": "reopened",
      "timestamp": "2026-11-03T00:39:55Z"
    },
    {
      "event": "closed",
      "timestamp": "2026-11-03T15:06:42Z"
    }
  ],
  "linked_verifier_evidence": [
    {
      "citation": "stranske/Counter_Risk#1168",
      "kind": "provider comparison report",
      "repository": "stranske/Counter_Risk",
      "timestamp": "unknown"
    },
    {
      "citation": "stranske/Counter_Risk#1169",
      "kind": "provider comparison report",
      "repository": "stranske/Counter_Risk",
      "timestamp": "unknown"
    },
    {
      "citation": "stranske/Counter_Risk#1158",
      "clock": "04:12Z",
      "kind": "issue timeline closed/reopened",
      "repository": "stranske/Counter_Risk",
      "timestamp": "unknown"
    },
    {
      "citation": "Manager-Database#1809",
      "kind": "provider comparison report",
      "repository": "unknown",
      "timestamp": "unknown"
    },
    {
      "citation": "Pension-Data#972",
      "kind": "provider comparison report",
      "repository": "unknown",
      "timestamp": "unknown"
    },
    {
      "citation": "trip-planner#1915",
      "kind": "provider comparison report",
      "repository": "unknown",
      "timestamp": "unknown"
    },
    {
      "citation": "Doc-Lineage#107",
      "kind": "source issue closed by a closer lane",
      "repository": "unknown",
      "timestamp": "unknown"
    },
    {
      "citation": "stranske/Workflows#3985",
      "kind": "deterministic acceptance gate",
      "repository": "stranske/Workflows",
      "timestamp": "unknown"
    },
    {
      "citation": "stranske/Workflows#3967",
      "kind": "related auto-pilot rule",
      "repository": "stranske/Workflows",
      "timestamp": "unknown"
    },
    {
      "citation": "stranske/Workflows actions run 39090617832",
      "comment_created_at": "2026-10-18T02:46:37Z",
      "kind": "comment on issue #4036",
      "october_24_outcome_claimed": false,
      "repository": "stranske/Workflows",
      "stated_report": "openai files reviewed 2 of 2 and anthropic files reviewed 2 of 2; verdict UNVERIFIABLE_INPUT/PASS because acceptance-artifact retrieval was incomplete",
      "stated_subject": "multi-file agent PR 4065"
    },
    {
      "citation": "stranske/Workflows actions run 39280806595",
      "comment_created_at": "2026-10-19T16:47:57Z",
      "immutable_source": "af60a4aee8464009986ab91764b7d48dc7a2c36d",
      "kind": "comment on issue #4036",
      "repository": "stranske/Workflows",
      "stated_report": "HTTP 400 string_above_max_length before model review; comparison.json CONCERNS; used_llm=false",
      "stated_subject": "release #4135"
    },
    {
      "citation": "stranske/Workflows actions run 39902391881",
      "comment_created_at": "2026-10-23T05:42:02Z",
      "kind": "comment on issue #4036",
      "merge_sha": "9e26d43a67c2736878efd41fa97ccf11902880c7",
      "original_head": "0a9dc057c1dbccc1d280d1ae63c9226a63e12240",
      "repository": "stranske/Workflows",
      "stated_report": "OpenAI FAIL / Anthropic CONCERNS over eight chunks",
      "stated_subject": "stranske/Workflows#4193"
    }
  ],
  "rules": {
    "agent_pr_definition": "unknown",
    "baseline_equals_campaign_population": "unknown",
    "check_date": "2026-10-24",
    "check_date_clock": "unknown",
    "closure_clock_start": "pull request merge",
    "closure_population": "merged released-issue PRs",
    "closure_target_percent": 80,
    "closure_timestamp_source": "unknown",
    "closure_within_hours": 2,
    "demand_equals_released_issue_population": "unknown",
    "demand_statement": "all merged agent PRs with a linked issue",
    "eligibility_window_end": "unknown",
    "eligibility_window_start": "unknown",
    "linked_issue_required_for_truncation_population": "unknown",
    "measurement_also_uses": "issue states",
    "measurement_command": "gh pr view --json comments",
    "owner_excluded_repository": "stranske/collab-admin",
    "owner_exclusion_in_issue_4036": false,
    "owner_exclusion_source": "Issue #4422 requires the exclusion. scripts/list_registered_consumer_repos.py names the repository.",
    "released_issue_definition": "unknown",
    "seven_day_window_start_rule": "unknown",
    "truncation_concerns_target_count": 0,
    "truncation_marker": "truncated",
    "truncation_population": "verifier reports for merged agent PRs",
    "truncation_verdict": "CONCERNS",
    "truncation_window": "within 7 days after merge"
  },
  "sources": [
    "gh issue view 4036 --repo stranske/Workflows --comments",
    "gh issue view 4422 --repo stranske/Workflows --comments",
    "gh pr view 4037 --repo stranske/Workflows --comments"
  ],
  "timezone": {
    "check_date_timezone": "unknown",
    "evidence": "Issue, comment, and pull-request timestamps use a Z suffix.",
    "stated_timestamps": "UTC"
  }
}
```

### Timestamp boundaries

| Boundary | Value | Status |
| --- | --- | --- |
| Timezone of Z-suffixed timestamps | UTC | stated |
| Campaign check date | 2026-10-24 | stated, date only |
| Check-date clock | unknown | not stated |
| Check-date timezone | unknown | the date token has no zone |
| Truncation window | within 7 days after merge | stated |
| Start rule for that 7-day window | unknown | not stated |
| Closure window | 2 hours after pull request merge | stated |
| Closure timestamp source when comments and issue state disagree | unknown | not stated |
| Eligibility window start | unknown | not stated |
| Eligibility window end | unknown | not stated |
| Baseline clock in the 2026-10-17 measurement sentence | 01:45Z | stated |
| Calendar date of that 01:45Z | unknown | not written as one timestamp |
| Counter_Risk #1158 reopen clock | 04:12Z | stated |
| Calendar date of that 04:12Z | unknown | not written as one timestamp |
| PR #4037 merged | 2026-10-18T02:31:22Z | stated |
| PR #4037 merge commit | 021ec67ef580c83a88402a1574e27ea34db14dde | stated |
| Issue #4036 created | 2026-10-17T12:00:41Z | stated |
| Issue #4036 final close | 2026-11-03T15:06:42Z | stated |
| Issue #4422 created | 2026-11-03T15:06:40Z | stated |

PR #4037's merge instant is a fact. It is not used as the eligibility window start.
The measurement sentence's "since 01:45Z" is not converted into `2026-10-17T01:45:00Z`.

### Rules that stay unresolved

- `released-issue` has no label, milestone, or release-workflow definition.
- "Merged agent PRs with a linked issue" is not stated to be the same set as "merged released-issue PRs".
- The 2026-10-17 count of 17 pulls since 01:45Z is not stated to be the campaign population.
- The closure measurement names `gh pr view --json comments` and issue states, without saying which timestamp wins.
- Issue #4036 does not mention an owner-excluded repository. Issue #4422 adds that exclusion. The repository list names `stranske/collab-admin`. This audit does not query it.

### Linked verifier evidence retained from the sources

The JSON above copies the citations. Report bodies were not downloaded in this step.
Comment timestamps on the three Workflows run citations come from the issue comment API.
The other citation timestamps were not present in the issue text.

Issue #4036's timeline, from the timeline API, is included because the issue was closed and reopened more than once. The current state is closed at 2026-11-03T15:06:42Z. That close is not evidence that the 2026-10-24 targets were met.

## Initial real-input check

Command:

```text
python3 verifier_4422_audit.py initial-evidence
```

That command runs exactly:

```text
gh run view 39090617832 --repo stranske/Workflows --json databaseId,conclusion,status,headSha,event,url,displayTitle,createdAt,updatedAt,workflowName,headBranch
```

The run id is the one named in the 2026-10-18T02:46:37Z comment on issue #4036.
The exclusion check rejects `stranske/collab-admin` before `gh` is invoked.

Stop rule: 2 attempts and 120 seconds of elapsed time. A failed attempt may be retried once inside that budget. When the budget is already spent, the command does not start another attempt. If the command exits non-zero, stop. Do not edit production verifier code, download a second run, or query another repository in that same step.

Ran once on 2026-11-06 immediately after 2026-11-06T18:26:25Z. Wall time was 0.53 seconds. Exit code 0. Attempt count 1.

```json
{
  "attempts": 1,
  "command": [
    "gh",
    "run",
    "view",
    "39090617832",
    "--repo",
    "stranske/Workflows",
    "--json",
    "databaseId,conclusion,status,headSha,event,url,displayTitle,createdAt,updatedAt,workflowName,headBranch"
  ],
  "elapsed_seconds": 0.465,
  "errors": [],
  "outcome": {
    "conclusion": "success",
    "createdAt": "2026-10-18T02:35:09Z",
    "databaseId": 39090617832,
    "displayTitle": "Agents Verifier",
    "event": "workflow_dispatch",
    "headBranch": "main",
    "headSha": "021ec67ef580c83a88402a1574e27ea34db14dde",
    "status": "completed",
    "updatedAt": "2026-10-18T02:39:02Z",
    "url": "https://github.com/stranske/Workflows/actions/runs/39090617832",
    "workflowName": "Agents Verifier"
  },
  "stop_reason": null,
  "stop_rule": {
    "max_attempts": 2,
    "max_elapsed_seconds": 120.0
  }
}
```

### What this outcome establishes

- Run 39090617832 exists in `stranske/Workflows`.
- Workflow name: Agents Verifier. Event: `workflow_dispatch`. Branch: `main`.
- Workflow conclusion: `success`. Status: `completed`.
- Created 2026-10-18T02:35:09Z. Updated 2026-10-18T02:39:02Z. Both UTC.
- `headSha` is `021ec67ef580c83a88402a1574e27ea34db14dde`, the same commit recorded as PR #4037's merge commit.
- URL: https://github.com/stranske/Workflows/actions/runs/39090617832

### What this outcome does not establish

- The run JSON does not name pull request 4065. The issue comment does. This check does not confirm that link.
- The run JSON does not include a verifier report, a changed-file inventory, or a `truncated` marker.
- Workflow conclusion `success` is the Actions result. It is not a provider verdict and it is not the 2026-10-24 campaign result.
- No production verifier file was edited before or during this check.

## Follow-ups

Later tasks still have to locate the deployed verifier revision, download the report, reconcile files, and reconstruct the historical population. Those steps are outside this initial check.
