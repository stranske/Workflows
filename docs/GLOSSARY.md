# Glossary

Plain-language definitions of the recurring terms in this repository's
automation system, each grounded in the workflow, script, or doc that owns the
behavior. Use this when a label name, workflow name, or piece of pipeline jargon
is unfamiliar.

For the full label inventory see [`LABELS.md`](LABELS.md). For the keepalive
contract see [`keepalive/GoalsAndPlumbing.md`](keepalive/GoalsAndPlumbing.md).
For a one-page operator cheat-sheet see
[`QUICK_REFERENCE.md`](QUICK_REFERENCE.md).

> **Source-of-truth rule.** Where this glossary names a label, the canonical
> definition is in [`LABELS.md`](LABELS.md). Where it names a workflow, the
> canonical behavior is the workflow file under `.github/workflows/`. This file
> is a navigational summary, not a second source of truth — if it ever disagrees
> with those, they win.

---

## Pipeline & loop terms

### Auto-pilot
The fully automated issue-to-merge pipeline triggered by the `agents:auto-pilot`
label on an issue. Stages: Format → Optimize → Apply → Capability Check →
Create PR → Keepalive → Verify → (optional) Follow-up. Self-chains between
stages via `workflow_dispatch` with a `force_step` input rather than label
triggers, which avoids race conditions. Implemented by `agents-auto-pilot.yml`.
See the "Auto-Pilot Pipeline" section of the top-level
[`README.md`](../README.md).

### Keepalive
The iterative loop that nudges an agent through small, verifiable increments on
a single PR until every acceptance criterion is checked complete. It injects the
PR's Scope/Tasks/Acceptance Criteria into the agent prompt, dispatches the
matching agent runner, watches for the PR head SHA to advance, and repeats.
Enabled by the `agents:keepalive` label on a PR (alongside a concrete `agent:*`
label). The canonical contract is
[`keepalive/GoalsAndPlumbing.md`](keepalive/GoalsAndPlumbing.md); the
implementation is `agents-keepalive-loop.yml` plus
`.github/scripts/keepalive_loop.js` and `keepalive_gate.js`.

### Event-driven loop
How keepalive is *normally* driven: it reacts to events rather than polling.
`agents-keepalive-loop.yml` triggers on `workflow_run` completion of the **Gate**
workflow, on `pull_request: labeled`, and on manual `workflow_dispatch`. Each
Gate completion re-evaluates the PR and dispatches the next round if unchecked
tasks remain. Concurrency is keyed `keepalive-<pr>` with
`cancel-in-progress: false` so rounds never cancel each other.

### Hourly sweep (keepalive sweep)
The safety net for the event-driven loop. A round that ends with **zero commits**
produces no follow-up event, so a silently stalled PR would otherwise never be
re-evaluated. `agents-keepalive-sweep.yml` runs on a cron (`23 * * * *`, hourly)
and re-dispatches the existing keepalive loop for every open PR carrying an
`agent:*` label, so stalls resurface on their own. It makes **no dispatch
decision of its own** — it only re-runs the loop, whose state-fingerprint makes
an unchanged PR a near-free no-op. It honors the operator guardrails
`agents:paused`, `needs-human`, and `agents:max-runs:0` (issue #2267), so a
paused or human-blocked PR is never re-dispatched by the sweep.

### Bootstrap PR
The initial draft PR an orchestrator/opener creates for an issue before any real
agent work exists — a branch (e.g. `codex/issue-<n>`) plus a PR body carrying the
issue context, used as the surface keepalive then iterates on. Whether bootstrap
PRs open as drafts is controlled by the `draft_pr` output of
`reusable-70-orchestrator-init.yml` (see
[`INTEGRATION_GUIDE.md`](INTEGRATION_GUIDE.md)); the lightweight bootstrap path is
the `.github/actions/codex-bootstrap-lite/` composite action. Belt and verifier
tooling treat a bootstrap-only placeholder (no substantive diff) as not yet
mergeable.

---

## The belt (Agents 71–73)

The belt automates the *queue → branch → PR → merge* conveyor for labeled Codex
issues, as three workflows that hand off in sequence. See the executive summary
at the top of [`WORKFLOW_GUIDE.md`](WORKFLOW_GUIDE.md).

### Dispatcher
`agents-71-codex-belt-dispatcher.yml`. Cron + manual entry point that **selects**
the next eligible issue (an `agent:codex` + `status:ready` issue), prepares the
deterministic `codex/issue-<n>` branch, marks the source issue
`status:in-progress`, and dispatches the worker.

### Worker
`agents-72-codex-belt-worker.yml`. Repository-dispatch consumer that re-validates
labels, ensures the branch diverges from the base (adding an empty commit if
needed), and **opens or refreshes** the Codex automation PR with labels,
assignees, and an activation comment.

### Conveyor
`agents-73-codex-belt-conveyor.yml`. The Gate follower that **closes the loop**:
squash-merges a successful belt PR, deletes the branch, closes the originating
issue, posts audit breadcrumbs, and re-dispatches the dispatcher so the queue
keeps moving. Requires Gate success before merging and blocks bootstrap-only
placeholders. It is the consumer that removes `status:in-progress`.

---

## Lanes (local automation)

The opener and closer **lanes** are local automations (Codex CLI + Claude Code
scheduled tasks) that drive issue→PR→merge→verify work across the supported
`stranske/*` repos. The in-repo system-of-record contract is
[`ops/LOCAL_LANES.md`](ops/LOCAL_LANES.md); the implementation lives outside this
checkout under `~/.codex`.

### Opener lane
*Discover-and-create.* Reads the human-approved review queue and live fleet
issues, then materializes the highest-priority unlinked implementation issue as
a new issue (when needed) plus a ready-for-review PR, applying the matching
`agent:*` label to the PR. Cap: **at most 5 active opener-owned PRs** across the
whole fleet at any time. Round outcomes: `new_issue` | `advance` | `no_op`.

### Closer lane
*Cleanup-merge-verify.* Drives existing PRs through merge → verify → close →
optional bounded follow-up. Round outcomes: `merge` | `close` | `followup_only`
| `no_op`.

### Sentinel / handoff
The two lanes alternate via a shared baton **sentinel** at
`~/.codex/handoff/lane-handoff.json` (a single cross-lane JSON holding the baton,
the most-recent productive action, queue pressures, and scoped blockers) and
hand off through the relay helper `~/.codex/bin/handoff-relay.sh`. Described in
[`ops/LOCAL_LANES.md`](ops/LOCAL_LANES.md) ("State locations").

### Capacity-stuck
A recovery state for a PR whose assigned agent has stalled — e.g. an
`agent:<X>` label co-present with `agent:rate-limited`, or `agent:<X>` with no
commits for hours despite keepalive enabled. The fix is to **add** `agent:auto`
alongside the existing label (do not remove it); the delegation policy
(`.github/scripts/agent_delegation_policy.js`) then detects the stall and
switches to the alternative agent. See `agent:auto` in [`LABELS.md`](LABELS.md).

---

## The Gate and merge

### The Gate
`pr-00-gate.yml` — the single PR-required check that orchestrates CI enforcement.
Its final `summary` job aggregates artifacts, computes coverage deltas,
**publishes the commit status**, and maintains the consolidated PR comment.
Doc-only PRs skip the core CI legs (`doc_only` / `run_core` detection). The Gate
is the event that drives the keepalive loop: keepalive and gate-followups both
trigger on its `workflow_run: completed`. The Gate is distributed to consumers as
a create-only starting point (see [`CLAUDE.md`](../CLAUDE.md)).

### Guarded merge / `automerge`
The automated merge path for completed agent PRs, gated so it cannot bypass
safety. The `automerge` label marks a PR eligible; `.github/scripts/merge_manager.js`
then checks an allowlist file (`.github/autoapprove-allowlist.json`, with `patterns`
and `max_lines_changed`) and requires Gate success. Per [`LABELS.md`](LABELS.md),
`automerge` **does not** bypass required checks, branch protection, or review
policy — hence "guarded." Applied by keepalive on a tasks-complete terminal when
appropriate.

### Autofix
The automated formatting/hygiene repair loop. Applying the `autofix` label (or
`autofix:clean` for a more aggressive pass) runs the CI Autofix Loop
(`autofix.yml`), which commits formatting/import/whitespace/type fixes and posts
a summary. There is also a **Gate-driven** repair path: when Gate fails,
`agents-81-gate-followups.yml` (via `workflow_run`) routes the failure to
`agents-autofix-loop.yml`, which handles larger fix-ups (pyproject sync, scripted
rewrites, merge-conflict handling). `agents-autofix-dispatcher.yml` is now only a
compatibility bridge for the legacy `autofix_gate_failure` `repository_dispatch`
signal.

---

## Verification

### Verifier / `verify:*` labels
The post-merge quality check. Applying a `verify:*` label to a **merged** PR
triggers `agents-verifier.yml`:

- `verify:checkbox` — verifies acceptance-criteria checkbox completion.
- `verify:evaluate` — runs an LLM evaluation and posts a report.
- `verify:compare` — runs the comparison across multiple models (two providers
  must unanimously PASS).
- `verify:create-issue` / `verify:create-new-pr` — turn verification feedback
  into a follow-up issue (and, for the latter, a bootstrapped follow-up PR).

**CI-failure hard gate:** if any polled CI workflow concludes `failure` on the
merge commit, the verdict is floored at CONCERNS before the LLM runs, so a merge
that breaks `main` can never verify PASS. See the Verifier Labels section of
[`LABELS.md`](LABELS.md).

### Repo-review evaluator
The weekly design-vs-implementation review tooling. `scripts/repo_review_coordinator.py`
is the Phase-4 entry point that drives the per-repo round-1 fan-out and round-2
negotiation and renders `human-decision-packet.md`; `scripts/repo_review_evaluator.py`
is the standalone preflight that produces the per-repo `review-inputs.md`
artifacts. Human decisions recorded in `config/repo_review_feedback.json` feed the
approved issue queue that the opener lane consumes. Full lifecycle:
[`ops/REPO_REVIEW_PROCESS.md`](ops/REPO_REVIEW_PROCESS.md).

---

## Control labels

### Run cap — `agents:max-runs:<K>`
Caps how many keepalive **rounds** a PR may run. `agents:max-runs:0` is an
explicit hold that prevents dispatch entirely (one of the three sweep
guardrails); values `K >= 1` are enforced by the keepalive loop when it evaluates
the PR. The prefix is parsed by `.github/scripts/keepalive_gate.js` and enforced
by `keepalive_loop.js`. (Distinct from the per-PR *concurrency* default — by
default at most one agent run is in progress per PR; see Run Cap Enforcement in
[`keepalive/GoalsAndPlumbing.md`](keepalive/GoalsAndPlumbing.md).) See
[`LABELS.md`](LABELS.md).

### `agents:paused`
Pauses **all keepalive activity on one PR**. Scope: a single PR. Resume by
removing the label. Consumer: `.github/scripts/keepalive_gate.js` (`PAUSE_LABEL`).
This is the canonical per-PR pause spelling — see the
[Pause/Resume Runbook](ops/PAUSE_RESUME_RUNBOOK.md) for the related
repo-scoped `keepalive:paused` (existence-semantics) and the legacy
`agents:pause` alias.

### `needs-human`
A durable human blocker on an issue or PR. Stops automation until a human removes
the label; marks a policy/product/access/repeated-failure blocker that should not
be retried blindly. Applied by verifier follow-up policy, auto-pilot blockers,
capability checks, and repeated keepalive failures (default: 3 failures →
`needs-human`). One of the three sweep guardrails. See [`LABELS.md`](LABELS.md).

### `agent:auto`
Delegates agent routing to the auto-delegation policy
(`.github/scripts/agent_delegation_policy.js`), which switches between Codex and
Claude based on stall/effectiveness signals. Do **not** combine with a concrete
`agent:<name>` label as a steady state — but the documented capacity-stuck
recovery is to *add* `agent:auto` alongside the existing label, after which
`agent:auto` wins and routes through delegation. See [`LABELS.md`](LABELS.md).

---

## See also

- [`LABELS.md`](LABELS.md) — canonical label inventory (source of truth for every
  label named above).
- [`QUICK_REFERENCE.md`](QUICK_REFERENCE.md) — one-page operator cheat-sheet.
- [`keepalive/GoalsAndPlumbing.md`](keepalive/GoalsAndPlumbing.md) — keepalive
  contract and guardrails.
- [`ops/PAUSE_RESUME_RUNBOOK.md`](ops/PAUSE_RESUME_RUNBOOK.md) — the three pause
  spellings and their scopes.
- [`ops/LOCAL_LANES.md`](ops/LOCAL_LANES.md) — opener/closer lane contract.
- [`ops/REPO_REVIEW_PROCESS.md`](ops/REPO_REVIEW_PROCESS.md) — weekly review →
  approved-queue lifecycle.
- [`WORKFLOW_GUIDE.md`](WORKFLOW_GUIDE.md) — full workflow inventory.
