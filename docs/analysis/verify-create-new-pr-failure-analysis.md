# Why `verify:create-new-pr` Never Creates a PR

## Executive Summary

The `verify:create-new-pr` pipeline successfully creates a follow-up issue but the
subsequent auto-pilot run fails to reach the `create-pr` step. The root cause is a
**concurrency queue collision**: a downstream workflow (`agents-71-codex-belt-dispatcher`)
adds the `status:in-progress` label using a non-`GITHUB_TOKEN` credential, which fires
an `issues: labeled` event that enters the same concurrency group as the pending
`create-pr` re-dispatch. GitHub cancels the pending re-dispatch to make room for the
label-triggered run, which then evaluates its `if:` condition and **skips** (issue
lacks `agents:auto-pilot` label). Net result: useful run cancelled, useless run skipped.

---

## The Failure: Issue #1407 Timeline

Issue #1407 was created by `agents-verify-to-new-pr.yml` from PR #1403 on 2026-02-09.
The bridge workflow (`agents-verify-to-new-pr-autopilot.yml`) dispatched auto-pilot
with `force_step: 'optimize'`. Here is what happened:

### Run chain in concurrency group `agents-auto-pilot-...-1407`

| Time (UTC)  | Run ID         | Event              | Step             | Result      |
|-------------|----------------|--------------------|------------------|-------------|
| 09:43:39    | —              | Issue #1407 created | —               | Labels: `agent:codex`, `follow-up` |
| 09:46:44    | 21820084713    | workflow_dispatch  | apply            | **success** |
| 09:50:05    | 21820155408    | workflow_dispatch  | capability-check | **success** |
| 09:51:06    | ↳ (within run) | —                  | adds `agent:codex` (no-op, already present) | — |
| 09:51:06    | ↳ (within run) | —                  | dispatches belt dispatcher | — |
| 09:51:13    | ↳ (within run) | re-dispatch step   | dispatches next with `force_step=auto` | — |
| **09:51:14** | **21820206063** | **workflow_dispatch** | **→ create-pr** | **CANCELLED (0 jobs)** |
| 09:51:31    | —              | belt dispatcher    | adds `status:in-progress` via `stranske-automation-bot` | Fires `issues: labeled` event |
| 09:51:33    | 21820216256    | **issues** (labeled) | — | **skipped** (`if:` false — no `agents:auto-pilot` label) |
| 09:51:35    | 21820217172    | issues (labeled)   | — | cancelled (0 jobs) |
| 09:52:00    | 21820229579    | issues (labeled)   | — | cancelled (0 jobs) |

### What happened

1. Capability-check (21820155408) completed successfully and re-dispatched auto-pilot
   with `force_step=auto` to continue the pipeline → run 21820206063 queued as PENDING.

2. While 21820155408 was still running its re-dispatch verification loop, the belt
   dispatcher it had launched added `status:in-progress` to issue #1407 using
   `stranske-automation-bot` (a non-`GITHUB_TOKEN` credential).

3. This fired an `issues: labeled` event → GitHub triggered `agents-auto-pilot.yml`
   → run 21820216256 entered concurrency group `agents-auto-pilot-...-1407`.

4. GitHub's concurrency rule (`cancel-in-progress: false`) allows max 1 running +
   1 pending. The group already had 21820155408 running + 21820206063 pending.
   **GitHub cancelled 21820206063 (pending) to make room for 21820216256.**

5. When 21820216256 started, its `if:` condition evaluated to false (issue #1407
   lacks `agents:auto-pilot` label) → **skipped**.

6. The `create-pr` step never executed. No PR was created. Pipeline stalled.

### Evidence sources

- **Run data**: `gh run view 21820206063` — cancelled, 0 jobs
- **Run data**: `gh run view 21820216256` — skipped, 1 job (condition false)
- **Token logs**: `Selected token: KEEPALIVE_APP` in all auto-pilot API calls
- **Issue events**: `gh api repos/stranske/Workflows/issues/1407/events` — `status:in-progress` added at 09:51:31 by `stranske-automation-bot`
- **Belt dispatcher**: `.github/workflows/agents-71-codex-belt-dispatcher.yml:327` — `addLabels` with `withRetry` (non-GITHUB_TOKEN)

---

## Root Cause Analysis

### Three-part mechanism

**Part 1: Non-`GITHUB_TOKEN` API calls trigger workflow events.**

`GITHUB_TOKEN` has a built-in safety mechanism: API calls made with it do NOT fire
new workflow events (preventing recursive loops). But auto-pilot's `createTokenAwareRetry`
routes API calls through `KEEPALIVE_APP` or other PATs for rate-limit distribution.
These tokens DO fire events.

Every `addLabels` call made during the auto-pilot step chain — and every `addLabels`
call made by workflows dispatched by auto-pilot (belt dispatcher, belt worker) — fires
a new `issues: labeled` event because a non-`GITHUB_TOKEN` is used.

**Part 2: `issues: labeled` trigger is too broad.**

```yaml
on:
  issues:
    types: [labeled, closed]
```

GitHub does not support label-name filtering on the `on.issues` trigger. ANY label
addition to ANY issue fires this trigger. The `if:` condition on the job does filter
correctly (requires `agents:auto-pilot` label), but this filter runs AFTER the run
enters the concurrency group.

**Part 3: Concurrency queue is FIFO with max 1 pending.**

```yaml
concurrency:
  group: agents-auto-pilot-${{ github.repository }}-${{ ... issue number ... }}
  cancel-in-progress: false
```

With `cancel-in-progress: false`, GitHub allows 1 running + 1 pending run per group.
When a third run arrives, the existing PENDING run is cancelled to make room. This
means a spurious `issues: labeled` run can cancel a legitimate `workflow_dispatch`
re-dispatch that was queued and waiting to execute.

### Why this specifically affects `verify:create-new-pr`

The verify-to-new-pr pipeline creates follow-up issues WITHOUT the `agents:auto-pilot`
label (they get `agent:codex` and `follow-up`). This means:

1. Label-triggered `issues` event runs → `if:` condition evaluates to false → **skipped**
2. But the skipped run still entered the concurrency group and **displaced the pending
   create-pr re-dispatch**

Issues that DO have `agents:auto-pilot` are also affected, but the spurious runs would
at least evaluate to true and re-run the pipeline (potentially recovering). Issues
WITHOUT `agents:auto-pilot` get the worst outcome: displaced run + skipped replacement.

---

## History of Past Fix Attempts

### PR #905 (Jan 17) — First auto-pilot implementation
- **What it did**: Introduced the self-dispatching pipeline architecture
- **Productive elements**: Self-dispatch via `workflow_dispatch` correctly avoids
  `GITHUB_TOKEN` event suppression for the re-dispatch mechanism
- **Problem**: Did not address label event interference

### PR #910 (Jan 17) — Foundation fixes
- **What it did**: Early pipeline fixes and stabilization
- **Productive elements**: Established the step chain (format → optimize → apply →
  capability-check → create-pr → monitor-pr)
- **Problem**: Kept the broad `issues: [labeled]` trigger

### PR #1269 (Jan 31) — Label ordering fix
- **What it did**: Fixed label-based state detection ordering
- **Productive elements**: Correct step determination based on label presence
- **Problem**: Did not address that label additions during steps trigger new runs

### PR #1280 (Feb 1) — Trigger interference fix
- **What it did**: Attempted to reduce false triggers from label events
- **Productive elements**: Tightened the `if:` condition on the auto-pilot job
- **Problem**: `if:` condition is evaluated AFTER concurrency group entry — runs
  that are filtered out still displace pending runs

### PR #1288 (Feb 2) — Remove `agent:codex` from triggers
- **What it did**: Removed `agent:codex` from the list of labels that trigger
  auto-pilot
- **Productive elements**: Reduced one source of false triggers
- **Problem**: The trigger is `issues: [labeled]` (ALL labels), not specific labels.
  The `if:` condition filters at the wrong level. The fix had no effect on the
  concurrency collision.

### PR #1317 (Feb 3) — Parsing fix
- **What it did**: Fixed JSON/YAML parsing errors in optimizer output consumption
- **Productive elements**: Fixed a real bug in the optimize → apply step transition
- **Unrelated**: Did not address the concurrency/trigger issue

### PR #1369 (Feb 5) — Rate limiting overhaul
- **What it did**: Introduced `createTokenAwareRetry` and token load balancer
- **Productive elements**: Solved rate limit exhaustion across concurrent workflows
- **Inadvertent regression**: By routing ALL API calls through non-`GITHUB_TOKEN`
  credentials, this change made `addLabels` calls fire `issues: labeled` events
  that were previously suppressed by `GITHUB_TOKEN`

### PR #1381 (Feb 7) — Artifact download fix
- **What it did**: Fixed artifact download failures in the verify-to-new-pr bridge
- **Productive elements**: Fixed the bridge workflow so it correctly extracts the
  issue number and dispatches auto-pilot
- **Problem**: Fixed the pipeline up to the auto-pilot dispatch, but the auto-pilot
  itself still fails at create-pr due to concurrency collision

### PR #1382 (Feb 8) — Dispatch verification
- **What it did**: Added dispatch verification loop (poll for new run after dispatch)
- **Productive elements**: Better observability — logs confirm the dispatch was
  accepted before the run gets cancelled
- **Problem**: Verification confirms the dispatch worked but cannot prevent
  subsequent cancellation by concurrent label events

### Summary of what worked vs. what didn't

| Category | What worked | What didn't |
|----------|-------------|------------|
| Architecture | Self-dispatch pipeline (eliminates label-dependency between steps) | Keeping `issues: [labeled]` trigger on the same workflow |
| Trigger filtering | `if:` condition correctly rejects spurious label events | Filter runs AFTER concurrency group entry — too late |
| Rate limiting | Token rotation prevents rate exhaustion | Non-`GITHUB_TOKEN` calls fire events that create concurrency collisions |
| Verification | Verify pipeline correctly creates follow-up issues | Follow-up issues lack `agents:auto-pilot`, so spurious runs skip rather than recover |
| Artifact handling | Bridge workflow correctly downloads artifacts and dispatches | — |
| Parsing | Optimizer output is correctly parsed and applied | — |

---

## Proposed Solutions

### Solution A: Use `GITHUB_TOKEN` for `addLabels` during auto-pilot steps (Recommended)

**What**: In the auto-pilot step chain, use the default `github` client (which uses
`GITHUB_TOKEN`) for `addLabels` calls instead of routing through `withRetry`/token
load balancer. Keep `withRetry` for all other API calls.

**Why it works**: `GITHUB_TOKEN` API calls do NOT fire `issues: labeled` events.
No events → no spurious runs → no concurrency collisions.

**Scope of change**: ~6 locations in `agents-auto-pilot.yml` where `addLabels` is
called during active step execution (format, optimize, apply, capability-check).
Also 1 location in `agents-71-codex-belt-dispatcher.yml` (the `status:in-progress`
label that directly caused the #1407 failure).

**Risk**: Low. Label additions are single lightweight API calls that won't exhaust
`GITHUB_TOKEN`'s rate limit. The rate limiting system was designed for high-volume
paginated calls, not individual REST calls.

**What it doesn't fix**: The broad `issues: [labeled]` trigger remains. External
actors (humans, other bots) adding labels to issues with `agents:auto-pilot` will
still trigger runs. But those are legitimate triggers (human intervention), not
self-inflicted interference.

**Implementation**:
```javascript
// BEFORE (fires events via non-GITHUB_TOKEN):
await withRetry((client) => client.rest.issues.addLabels({
  owner, repo, issue_number, labels: ['agent:codex']
}));

// AFTER (suppresses events via GITHUB_TOKEN):
await github.rest.issues.addLabels({
  owner: context.repo.owner,
  repo: context.repo.repo,
  issue_number: issueNumber,
  labels: ['agent:codex']
});
```

### Solution B: Split `issues: labeled` trigger into a separate lightweight workflow

**What**: Remove `issues: [labeled, closed]` from `agents-auto-pilot.yml`. Create a
small `agents-auto-pilot-trigger.yml` that:
1. Triggers on `issues: [labeled, closed]`
2. Checks if the label is `agents:auto-pilot`
3. If yes, dispatches `agents-auto-pilot.yml` via `workflow_dispatch`

**Why it works**: The lightweight trigger workflow has NO concurrency group (or its
own separate one). The auto-pilot workflow only triggers on `workflow_dispatch`, so
spurious label events never enter its concurrency group.

**Risk**: Medium. Adds a workflow indirection layer. The dispatch must use a
non-`GITHUB_TOKEN` credential (otherwise `workflow_dispatch` events from
`GITHUB_TOKEN` are suppressed too).

**What it doesn't fix**: If the trigger workflow itself uses a non-`GITHUB_TOKEN`
credential to dispatch, other label events could still trigger it. But without a
shared concurrency group with auto-pilot, they can't cancel pending auto-pilot runs.

### Solution C: Also add `agents:auto-pilot` label to verify-to-new-pr follow-up issues

**What**: In `agents-verify-to-new-pr.yml`, add `agents:auto-pilot` to the labels
applied to the follow-up issue (currently only `agent:codex` and `follow-up`).

**Why it helps**: When spurious `issues: labeled` runs DO fire, the `if:` condition
would evaluate to TRUE instead of skipping. The run would proceed and re-evaluate
state, likely reaching `create-pr` on its own. This turns a guaranteed failure into
a potential recovery.

**Risk**: Low. But this is a mitigation, not a fix — the concurrency collision still
happens, and the re-dispatched run is still cancelled. The label-triggered run might
or might not arrive at the correct step depending on timing and label state.

**Should be combined with Solution A**, not used alone.

### Solution D: Change downstream workflows to use `GITHUB_TOKEN` for label additions

**What**: In `agents-71-codex-belt-dispatcher.yml` (line 327) and
`agents-72-codex-belt-worker.yml` (line 981), use `github.rest.issues.addLabels`
directly instead of `withRetry` when adding `status:in-progress`.

**Why it works**: Same mechanism as Solution A — `GITHUB_TOKEN` suppresses events.

**Risk**: Low. These are single API calls.

**This is the minimum viable fix for the #1407 failure** since the specific label
that caused the collision was `status:in-progress` from the belt dispatcher.
But Solution A is more comprehensive (prevents future similar issues from other
label additions within the step chain).

---

## Implemented Solution

The fix combines two changes that address the problem at different layers:

### Change 1: Gate job prevents spurious runs from entering concurrency group

**Files changed:**
- `.github/workflows/agents-auto-pilot.yml`
- `templates/consumer-repo/.github/workflows/agents-auto-pilot.yml`

**Before:**
```yaml
concurrency:
  group: agents-auto-pilot-...-${{ issue_number }}
  cancel-in-progress: false

jobs:
  auto-pilot:
    if: <complex condition>   # Evaluated AFTER concurrency group entry
```

**After:**
```yaml
# No workflow-level concurrency

jobs:
  gate:
    runs-on: ubuntu-latest
    timeout-minutes: 2
    if: |
      github.event_name == 'workflow_dispatch' ||
      (github.event.action == 'labeled' &&
       github.event.label.name == 'agents:auto-pilot') ||
      (github.event.action == 'closed' && ...)
    steps:
      - run: echo "proceed=true" >> "$GITHUB_OUTPUT"

  auto-pilot:
    needs: [gate]
    concurrency:
      group: agents-auto-pilot-...-${{ issue_number }}
      cancel-in-progress: false
```

The gate job has **no concurrency group** and runs instantly. Its `if:` only passes
for `agents:auto-pilot` label specifically (not "any label when auto-pilot present"),
`workflow_dispatch`, or `closed` events. Spurious label events from `status:in-progress`,
`agents:formatted`, etc. are rejected at the gate and **never enter the concurrency
group**, so they cannot displace pending re-dispatched runs.

### Change 2: Follow-up issues get `agents:auto-pilot` label

**Files changed:**
- `.github/workflows/agents-verify-to-new-pr.yml`
- `templates/consumer-repo/.github/workflows/agents-verify-to-new-pr.yml`

Follow-up issues are now created with `['follow-up', 'agent:codex', 'agents:auto-pilot']`
instead of `['follow-up', 'agent:codex']`. This ensures that if any residual label
events DO somehow pass the gate, the auto-pilot job's `check_enabled` step will
evaluate to true and the run can proceed (recovering instead of skipping).

### Verification plan

After implementation:
1. Apply `verify:create-new-pr` to a test PR
2. Verify follow-up issue is created with `agents:auto-pilot` label
3. Verify auto-pilot runs through all steps without cancellation
4. Check Actions tab for absence of spurious `issues` event runs in the concurrency
   group during the step chain
5. Confirm PR is created automatically
