# Quick Reference

A two-page operator cheat-sheet for the day-to-day controls of the automation
system. For definitions of the terms used here, see [`GLOSSARY.md`](GLOSSARY.md).
For the authoritative label inventory, see [`LABELS.md`](LABELS.md). Where this
page and those disagree, **they win.**

---

## Pause and resume

There are **three pause spellings with different scopes — they are not
interchangeable.** Pick by scope first. Full detail:
[`ops/PAUSE_RESUME_RUNBOOK.md`](ops/PAUSE_RESUME_RUNBOOK.md).

| Scope | Label | How to pause | How to resume |
|-------|-------|--------------|---------------|
| **One PR** (canonical) | `agents:paused` | Add the label to the PR | Remove the label; next Gate/keepalive event resumes |
| **One repo** | `keepalive:paused` | **Create** the label in the repo | **Delete** the label from the repo |
| One PR (legacy alias) | `agents:pause` | Add to the PR | See trap below — do not just remove |

> **Existence-semantics trap (`keepalive:paused`).** This label pauses *every*
> keepalive run in the repository **by merely existing** — it does **not** need to
> be applied to any issue or PR. To pause, create the label; to resume, **delete
> the label from the repo**. Removing it from an issue/PR does nothing; the repo
> stays paused as long as the label exists. Consumer:
> `.github/scripts/agents_orchestrator_resolve.js` (`KEEPALIVE_PAUSE_LABEL`).

> **Legacy `agents:pause` trap.** `agents:pause` is a legacy alias still honored
> by `keepalive_loop.js` and the PR-health checks (but **not** by
> `keepalive_gate.js`, which only checks `agents:paused`). If a PR already carries
> `agents:pause`, either leave it until the blocker clears or **replace** it with
> `agents:paused` in the same operation — removing it by itself can resume
> keepalive unexpectedly. Use `agents:paused` for all new pauses.

**Other holds (not "pause" labels but stop work):**

- `agents:max-runs:0` — explicit per-PR hold; prevents any keepalive dispatch.
- `needs-human` — independently confirmed authority blocker on an issue/PR.
  Automation failure, ambiguity, exhausted retries, and design choices are not
  sufficient; the record must name the exact human action and evidence.
- `agents:auto-pilot-pause` — pauses auto-pilot dispatch on an issue.

**Resume checklist** (from the runbook):

1. Remove the relevant pause control.
2. Confirm no durable blocker remains (`needs-human`, `agent:needs-attention`).
3. Confirm the PR still has one concrete `agent:<name>` label **and**
   `agents:keepalive`.
4. Add `agent:retry` if you need an immediate keepalive dispatch (otherwise the
   next Gate pass resumes it).
5. Record why work resumed in the PR/issue.

---

## How keepalive is driven

Keepalive nudges an agent through a PR until all acceptance criteria are checked
complete. It runs in two complementary ways:

- **Event-driven loop** — `agents-keepalive-loop.yml`. Triggers on the **Gate**
  workflow's `workflow_run: completed`, on `pull_request: labeled`, and on manual
  `workflow_dispatch`. Each Gate completion re-evaluates the PR and dispatches the
  next round if unchecked tasks remain.
- **Hourly sweep** — `agents-keepalive-sweep.yml`, cron `23 * * * *`. A round
  ending with zero commits emits no event, so a stalled PR would never be
  re-evaluated; the sweep re-runs the loop for every open `agent:*` PR to
  resurface stalls. It makes no dispatch decision of its own and honors
  `agents:paused` / `needs-human` / `agents:max-runs:0`.

**Activation guardrails** (all must hold, per
[`keepalive/GoalsAndPlumbing.md`](keepalive/GoalsAndPlumbing.md)):

1. PR carries an `agent:*` label (e.g. `agent:codex`, `agent:claude`).
2. Gate for the current head SHA completed **successfully**.
3. The PR body's Automated Status Summary has **unchecked tasks**.

To force one immediate re-dispatch on a healthy PR: add `agent:retry` (keepalive
consumes and removes it, and co-removes any stale `agent:rate-limited`).

Each non-transient run/fix failure adds `agent:retry` and explicitly dispatches
a bounded retry while the failure threshold remains. At the threshold (default
3), keepalive pauses that strategy; the hourly sweep owns the next recovery
review. A possible access or
authority boundary adds `agent:needs-attention` and an immediately due
independent challenge; the hourly sweep reads that state and passes its exact
boundary fingerprint into a current-state recheck while ordinary sweep traffic
remains non-forced. Every scheduled sweep wakeup bypasses state and completed-
runner debounce so a zero-event stall is actually re-evaluated; only the due
fingerprint carries challenge provenance, signed with the dedicated
`KEEPALIVE_AUTHORITY_SIGNING_KEY` and bound to the repository, PR, random nonce, and exact sweep run/attempt.
Unsigned or forged claims fail closed as ordinary non-forced rechecks. A replacement boundary is
therefore checked on the next sweep. A green recheck clears
the challenge; only the sweep-selected allowlisted authority projection failing
again records the exact runner-reported action before replacing
`agent:needs-attention` with `needs-human`. A generic manual retry or another
`github-actions[bot]` workflow cannot confirm it.
Confirmed human holds are challenged again after 24 hours by the reviewed-repo
controller so stale assumptions cannot idle a PR.

---

## How to find a verification result

After a PR is **merged**, a `verify:*` label triggers `agents-verifier.yml`,
which posts a **verification report comment on the PR**.

- The verdict is **PASS / CONCERNS / FAIL**.
- **CI-failure hard gate:** if any polled CI workflow concluded `failure` on the
  merge commit, the verdict is floored at **CONCERNS** before the LLM even runs —
  a merge that breaks `main` can never PASS.
- To turn concerns into follow-up work: apply `verify:create-issue` (issue only)
  or `verify:create-new-pr` (issue + bootstrapped PR).

**Fleet/aggregate metrics** are surfaced via the weekly summary tracker (issue `#2211`, posted Mondays 06:00 UTC) and the LangSmith dashboard wired by
`maint-80-langsmith-metrics-dashboard.yml`. See the README "Verification
Pipeline" section.

---

## Key labels at a glance

Canonical definitions: [`LABELS.md`](LABELS.md).

| Label | What it does |
|-------|--------------|
| `agents:auto-pilot` | Runs the full issue-to-merge pipeline (on an issue) |
| `agent:codex` / `agent:claude` | Route the issue/PR to that agent runner |
| `agent:auto` | Delegate routing to the auto-delegation policy (capacity-stuck recovery) |
| `agent:retry` | Force one keepalive re-dispatch (auto-removed) |
| `agents:keepalive` | Enable the keepalive loop on a PR |
| `agents:paused` | Pause keepalive on one PR (canonical) |
| `agents:max-runs:<K>` | Cap keepalive rounds; `:0` is an explicit hold |
| `needs-human` | Durable human blocker; stops automation |
| `autofix` / `autofix:clean` | Run the formatting/hygiene repair loop |
| `automerge` | Mark a completed PR for guarded automerge (does not bypass branch protection) |
| `verify:evaluate` / `verify:compare` | Run the post-merge verifier |
| `status:ready` | Issue ready for the belt dispatcher |
| `status:in-progress` | Issue claimed by the belt (set by dispatcher/worker, cleared by conveyor) |

> Labels trigger on the `labeled` event — **re-applying an already-present label
> does not re-trigger.** Remove and re-add to fire again.

---

## Key consumer-present workflows

These run inside each consumer repo (synced from
`templates/consumer-repo/.github/workflows/`). When a doc cites a workflow not in
the Workflows-root `.github/workflows/`, check the consumer template directory
before assuming drift.

| Workflow | Role |
|----------|------|
| **`pr-00-gate.yml`** (the Gate) | Single PR-required check; its `summary` job publishes the commit status and the consolidated PR comment. Drives keepalive via `workflow_run`. Doc-only PRs skip core CI. |
| **`agents-80-pr-event-hub.yml`** | Consolidated PR event hub (pr-meta + bot-comment handlers); reacts to PR events, comments, and Gate completion. |
| **`agents-81-gate-followups.yml`** | Gate-completion follow-ups: keepalive evaluation plus the Gate-driven **autofix repair** routing (replaces the legacy `agents-autofix-dispatcher.yml` `repository_dispatch` path). |
| `agents-issue-intake.yml`, `agents-verifier.yml`, `autofix.yml`, `ci.yml` | Other current consumer entry points (see [`CLAUDE.md`](../CLAUDE.md)). |

On the **Workflows repo itself**, the equivalent keepalive plumbing is
`agents-keepalive-loop.yml` + `agents-keepalive-sweep.yml`, and the belt is
`agents-71/72/73-codex-belt-*.yml`.

---

## See also

- [`GLOSSARY.md`](GLOSSARY.md) — term definitions.
- [`LABELS.md`](LABELS.md) — canonical label inventory.
- [`ops/PAUSE_RESUME_RUNBOOK.md`](ops/PAUSE_RESUME_RUNBOOK.md) — pause scopes.
- [`keepalive/GoalsAndPlumbing.md`](keepalive/GoalsAndPlumbing.md) — keepalive contract.
- [`ops/RUNBOOK.md`](ops/RUNBOOK.md) — operational runbook.
