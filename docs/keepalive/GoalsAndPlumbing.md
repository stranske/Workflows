# Keepalive — Goals & Plumbing (Canonical Reference)

> **Audience:** Human maintainers and automation agents responsible for the keepalive workflow. Review this document **before** touching any keepalive logic or dispatch plumbing.

## Quick Navigation
- [Purpose & Scope](#purpose--scope)
- [Lifecycle Overview](#lifecycle-overview)
- [1. Activation Guardrails](#1-activation-guardrails)
- [2. Repeat Contract](#2-repeat-contract)
- [3. Run Cap Enforcement](#3-run-cap-enforcement)
- [4. Pause & Stop Controls](#4-pause--stop-controls)
- [5. No-Noise Policy](#5-no-noise-policy)
- [6. Instruction Prompt Contract](#6-instruction-prompt-contract)
- [7. Agent Routing](#7-agent-routing)
- [8. Capacity Mode Contract](#8-capacity-mode-contract)
- [9. Branch-Sync Gate](#9-branch-sync-gate)
- [10. Orchestrator Invariants](#10-orchestrator-invariants)
- [11. Restart & Success Conditions](#11-restart--success-conditions)
- [12. Issue Context & Status Summary](#12-issue-context--status-summary)
- [13. Progress Detection & Checkbox Reconciliation](#13-progress-detection--checkbox-reconciliation)
- [Appendix: Operator Checklist](#appendix-operator-checklist)

---

## Purpose & Scope

- **Purpose:** Maintain a safe, iterative loop where keepalive nudges an agent through small, verifiable increments on a PR until every acceptance criterion is complete—while guaranteeing predictable behaviour and safety rails.
- **Scope:** Activation requirements, dispatch plumbing, throttling, branch-sync guarantees, and shutdown rules for the GitHub PR keepalive workflow.
- **Applicability:** This contract covers the registry-driven CLI keepalive implementation for Codex, Claude, and future agents. The legacy UI connector-bot flow is documented separately in [`Keepalive_Approaches.md`](Keepalive_Approaches.md).
- **Non-goals:** Guidance for automation unrelated to keepalive.

---

## Lifecycle Overview

1. **PR labeled:** A PR receives an `agent:*` routing label (for example, `agent:codex` or `agent:claude`) and the `agents:keepalive` opt-in label.
2. **Guarded check:** Orchestrator guardrails confirm the label, Gate success, and run-cap capacity before running the agent.
3. **Agent execution:** The appropriate agent workflow runs with explicit task context injected into the prompt.
4. **Timed repeats:** Subsequent Gate completions trigger re-evaluation and continue if tasks remain.
5. **Definition of done:** As soon as the acceptance criteria are all checked complete, keepalive posts no further rounds.
6. **Suspend on label change:** If the label disappears or the guardrails fail mid-run, the workflow records the skip reason and stays silent until a human re-applies the label.

---

## 1. Activation Guardrails

Keepalive **must not** dispatch an agent unless *all* conditions hold:

1. **PR opt-in:** The PR carries both an `agent:*` routing label (for example, `agent:codex` or `agent:claude`) and `agents:keepalive`.
2. **Gate green:** The Gate workflow for the current head SHA completed successfully.
3. **Tasks present:** The PR body contains unchecked actionable tasks, including visible checkboxes outside the Automated Status Summary.

> **Note on auto-pilot:** Issue formatting now runs inside the auto-pilot workflow before a PR exists. Gate guardrails apply to **PR keepalive dispatch**, not the issue‑formatting phase of auto-pilot.
>
> **Root workflow-run filter:** The root keepalive loop rejects push-triggered Gate runs at the job condition before runner allocation. Pull-request and manually dispatched Gate runs remain eligible even when GitHub omits the `pull_requests` association, because `evaluateKeepaliveLoop` can recover the open PR from the run head SHA.
>
> **Multi-Agent Note:** The `agent:*` label determines which agent workflow runs. See [`MULTI_AGENT_ROUTING.md`](MULTI_AGENT_ROUTING.md) for details.

### Periodic re-evaluation (keepalive sweep)

Eligible-but-idle PRs must be re-evaluated even when no Gate completion or label event fires. The hourly `agents-keepalive-sweep.yml` workflow selects every open non-draft PR carrying both an `agent:*` routing label and `agents:keepalive`, then dispatches the PR's registered evaluation workflow:

| Mode | `vars.USE_CONSOLIDATED_WORKFLOWS` | Sweep job | Loop dispatched |
|------|-----------------------------------|-----------|-----------------|
| **Root Workflows repo** | `!= 'true'` (default) | root `agents-keepalive-sweep.yml` | `agents-keepalive-loop.yml` |
| **Consumer consolidated** | `== 'true'` | `sweep_consolidated` | `agents-81-gate-followups.yml` |
| **Consumer non-consolidated** | `!= 'true'` or unset | `sweep_nonconsolidated` | `agents-81-gate-followups.yml` |

The sweep makes no new routing decision — it re-dispatches the PR's already-registered evaluation workflow. Consolidated mode dispatches `agents-keepalive-loop.yml` directly (the full guardrail-and-dispatch loop). Non-consolidated mode dispatches `agents-81-gate-followups.yml`, which triggers a gate-followup evaluation; the keepalive loop's guardrail check runs as part of that dispatch, not as a standalone wakeup. Unchanged PRs are near-free no-ops via state fingerprint/debounce. The consumer template always runs a `name_mode` job that records which path is active and which is skipped, so a structurally inactive path (`vars.USE_CONSOLIDATED_WORKFLOWS unset — no periodic re-evaluation in this repo` via the consolidated job) is distinguishable from a healthy quiet re-evaluation (fallback or consolidated job ran; 0 eligible PRs).

`agent:auto` delegation policy reads capacity on **keepalive ticks** (`docs/LABELS.md`); those ticks come from the sweep jobs above in each mode, not from a silent workflow skip.

---

## 2. Repeat Contract

Before the next agent run:

- Re-validate the activation guardrails.
- Confirm the concurrent run cap is still available (see Section 3).
- Check failure tracking—after repeated failures, pause the current strategy and
  route automation recovery; do not infer a human requirement.

If any requirement fails, keepalive stays silent—no PR comments. Operators may record the skip reason in run summaries only.

---

## 3. Run Cap Enforcement

- **Default limit:** Maximum of **1** concurrent agent run per PR.
- **Label override:** Respect `agents:max-runs:<K>` when present (integer 1–5); `agents:max-runs:0` is an explicit hold.
- **Enforcement:** Dispatch only when the count of in-progress runs is `< K`. If at cap, exit quietly after updating the run summary.
- **Round budget:** The loop enforces `max_iterations` as the ordinary per-PR round budget. The default is 12 rounds unless overridden by keepalive config.
- **Budget exhaustion:** When the current iteration reaches `max_iterations`, keepalive stops that dispatch strategy, records reason `round-budget-exhausted`, and dispatches one forced recovery lease. The durable state records that lease as issued and consumes it only after an agent runner actually starts and returns a real result. Skipped or cancelled runners, preflight-only failures, temporary operator guards, and failed direct dispatches defer the same lease for a later direct retry. Later ordinary events cannot mint a second lease for the same terminal reason and budget. Raising the budget or making later ordinary progress resets that boundary; the forced run itself may cross the persisted budget once and cannot recursively dispatch itself.

---

## 4. Pause & Stop Controls

- Removing the `agent:*` label halts new dispatches until a label is re-applied and all guardrails pass again.
- Respect the `agents:paused` label, which blocks *all* keepalive activity.
- Every non-transient run/fix failure records automation-owned retry state and explicitly dispatches a bounded retry while below the failure threshold. If direct dispatch fails, the durable lease is deferred for the hourly sweep to retry directly; automation does not add a sticky `agent:retry` label.
- After repeated failures (default: 3), the loop pauses the current strategy and dispatches one non-recursive forced recovery lease. A complete-but-failing Gate uses that lease for one real fix attempt even when its ordinary Gate-fix budget is exhausted; after the forced run, the hourly keepalive sweep owns the next recovery review.
- A possible access or authority boundary adds `agent:needs-attention` with an immediately due independent challenge. Durable state extracts only a closed allowlist of facts: a credential named by the routed agent's registry-backed `required_secrets` or the registry's shared authority list, a finite permission target, and HTTP 401/403. Its fingerprint and human action are derived only from those facts; arbitrary runner text is never copied or persisted. Every hourly sweep wakeup bypasses state debounce so an unchanged zero-commit round is re-evaluated, while ordinary wakeups retain completed-runner debounce. Both the root and consolidated consumer lanes require a dedicated keepalive or Workflows App token before marking an agent running or writing the final summary, so every mutation of App-owned state uses the same trusted writer class. Every keepalive reader selects durable state only from a marked summary comment authored by `stranske-keepalive[bot]`, `agents-workflows-bot[bot]`, the identity-checked PAT fallbacks `stranske` and `stranske-automation-bot`, or the migration-only legacy `github-actions[bot]` writer; an arbitrary later commenter cannot replace the preceding trusted state. If a selected App finds a summary from the known legacy writer or the other dedicated App, it migrates the parsed state to a newly created App-owned comment instead of editing the old marker in place, because GitHub preserves the original author. The sweep signs a v2 claim over the current authoritative challenge generation, exact fingerprint and due/expiry times, PR head, repository/PR, nonce, and sweep run/attempt. A matching claim may bypass runner debounce only after a conditional, PR-wide single-use receipt is persisted on `keepalive-authority-state`. Generic retries, old envelopes, and other workflows sharing `github-actions[bot]` cannot consume or confirm the challenge. Missing signing material permits an ordinary recheck without a challenge claim; a supplied invalid claim or unavailable ledger denies the challenge path. A green recheck clears the challenge. Only the signed sweep-selected projection failing again may record its allowlisted credential or permission remedy before replacing `agent:needs-attention` with `needs-human`; a different auth failure starts a new automation-owned challenge that the next sweep can evaluate. The reviewed-repo controller challenges confirmed holds again after 24 hours.
- Agent delegation treats two consecutive zero-progress rounds as stalled. Commit churn is not progress unless it advances checklist state or reaches a green Gate.
- On an `agent:auto` PR with no recorded current agent, `decideNextAgent` first honors an available co-present concrete `agent:<name>` label. Without one, it may consult the Orchestrator route-weights export for the first choice. When an `agent:auto` PR later stalls and switches agents, it may consult the same export (`ROUTE_WEIGHTS_URL`, defaulting to the `exports/route-weights` branch JSON documented in `stranske/Orchestrator`). Any fetch/parse/staleness or insufficient-evidence result falls back to today's static preference without blocking keepalive.

**To resume after failure:**
1. Investigate the failure reason in the keepalive summary comment
2. Route a concrete automation recovery and record its worker
3. Fix the code, prompt, CI, routing, or task decomposition
4. Add or re-apply `agent:retry`; the next Gate pass will restart the loop

Do not edit the state marker manually. Use the supported `agent:retry` or workflow-dispatch recheck; the dedicated keepalive app then updates or clears the bot-owned recovery state.

---

### Authority challenge ledger (v2)

The dedicated `keepalive-authority-state` branch stores `.github/keepalive-authority/<PR>.json` for each PR. The first challenge generation is initialized from the repository default branch by a workflow using a dedicated App token with `contents: write`; the workflow token remains read-only. Each generation records its originating PR head as well as the boundary fingerprint, canonical due/expiry times, monotonic revision, and at most one receipt naming the downstream workflow attempt and provider. Sweep signing, preparation, consumption, and confirmation all require that same head. Legacy records without an originating head are readable only for fail-closed migration and cannot be signed or consumed as current authority.

Each update supplies the previous file SHA to the Contents API. The runner conditionally changes `available` to non-authorizing `prepared`, writes and rereads its attempt-bound primary reservation, then conditionally changes `prepared` to `consumed`. A definite reservation refusal may conditionally release only the same preparation before any grant exists. A conflicting or ambiguous preparation/consumption write grants no run; a consumed receipt is never refunded. Ordinary runner completions never write this ledger. Missing or malformed state fails closed, and summary comments or labels cannot restore authority. The owner attempt must have actually started a worker before receipt-backed confirmation may apply `needs-human`. A crash after consumption may leave zero executions, so the guarantee is at most one grant rather than exactly-once execution.

PR head and labels live outside the authority ledger, so their reads and ledger writes cannot form one transaction. After consumption, the consumer rechecks the PR and its reservation and denies a grant if the head, routing labels, or attempt binding changed. Confirmation checks the PR before and after its ledger write. An unavailable read or stale head preserves the existing receipt and hard label for reconciliation; it never rotates confirmed state into fresh execution authority or removes `needs-human`. A fresh same-head read may rotate only when the hard label is already absent. These checks narrow the cross-resource race without claiming atomicity against later PR metadata changes. The original worker attempt retries confirmation once against the same consumed receipt after an ambiguous read or conditional write. That retry cannot grant another execution or remove the hard label.

## 5. No-Noise Policy

When preconditions are missing (labels absent, Gate not green, run cap reached), keepalive must not add new PR comments. At most, log a concise operator summary explaining the skipped action.

---

## 6. Instruction Prompt Contract

When running is allowed:

1. **Task injection:** The prompt includes an appendix with explicitly extracted Scope, Tasks, and Acceptance Criteria from the PR body.
2. **Agent-agnostic prompt:** The base prompt (`.github/codex/prompts/keepalive_next_task.md`) is agent-agnostic—no `@codex` or agent mentions.
3. **Progress tracking:** The appendix includes progress count (e.g., "3/10 tasks complete, 7 remaining").

Example prompt appendix:
```markdown
---
## PR Tasks and Acceptance Criteria

**Progress:** 3/10 tasks complete, 7 remaining

### Scope
Add visibility for CLI agent iterations in the PR body.

### Tasks
Complete these in order. Mark checkbox done ONLY after implementation is verified:

- [x] Add output for `final-message` from the agent action
- [ ] Write iteration summary to GITHUB_STEP_SUMMARY
- [ ] Create new section in PR body for CLI Codex status
...

### Acceptance Criteria
The PR is complete when ALL of these are satisfied:

- [ ] CLI agent iterations are visible in the PR body
...
---
```

---

## 7. Agent Routing

The keepalive loop routes to agent workflows through `.github/agents/registry.yml` and the shared `agent_registry.js` helpers. Do not hard-code provider names in new orchestration logic unless the code is inside that provider's runner workflow.

| Label | Agent | Workflow |
|-------|-------|----------|
| `agent:codex` | Codex CLI (gpt-5.6-terra; fallback gpt-5.5) | `reusable-codex-run.yml` |
| `agent:claude` | Claude CLI | `reusable-claude-run.yml` |
| `agent:cursor` | Cursor | `reusable-cursor-run.yml` (root and consumer Gate-followups) |
| `agent:gemini` | Gemini | `reusable-gemini-run.yml` (root and consumer Gate-followups) |

The table above is a snapshot of the current registry, not a second source of truth. See [`MULTI_AGENT_ROUTING.md`](MULTI_AGENT_ROUTING.md) and [`../guides/ADD_NEW_AGENT.md`](../guides/ADD_NEW_AGENT.md) for implementation details and how to add new agents.

---

## 8. Capacity Mode Contract

Capacity mode is a phased operator contract for recording whether automation can safely continue. It is not a universal hard blocker; adopt it first in workflows and workloops that already have a durable state surface such as PR comments, issue markers, run summaries, or metrics artifacts.

Use these values when recording mode:

| Mode | Meaning | Required state fields |
|------|---------|-----------------------|
| `normal` | API quota, auth, and local workspace are sufficient for the next action. | Next action and current owner. |
| `graphql-only` | REST is constrained, but known-safe GraphQL reads or writes remain available. | Quota snapshot, blocked REST command, next GraphQL-safe action. |
| `local-only` | Remote writes are unsafe or unavailable, but local validation can continue. | Blocked remote command, local checks to run, next remote retry condition. |
| `blocked-on-auth` | Required token or agent credential is missing, expired, or lacks scope. | Missing credential/scope, failing command, required human action. |
| `blocked-on-rate-reset` | API quota is exhausted or below the workflow's safety threshold. | Quota snapshot, reset time when known, next safe action after reset. |

When a workflow or automation records a non-`normal` mode, include the exact command or API operation that was blocked, any relevant reset time, and the next safe action. Do not assume GraphQL writes are safe unless that workflow already has a tested GraphQL path.

---

## 9. Branch-Sync Gate

Before the next round begins:

1. Verify that the PR head SHA changed after the agent reported "done".
2. If unchanged, the agent may have failed to push. The loop will retry on the next Gate pass.
3. After repeated failures (default: 3), pause the current strategy and add `agent:retry` with a concrete automation-owned recovery action.

---

## 10. Orchestrator Invariants

- **No self-cancellation:** Configure concurrency as `keepalive-{pr}` with `cancel-in-progress: false`.
- **Explicit bails:** For early exits (missing preconditions, run cap reached, Gate not green), write a one-line reason to the run summary.
- **Summary comment:** Update the keepalive summary comment with iteration status, agent output preview, and failure tracking.

---

## 11. Restart & Success Conditions

- Removing and re-applying the `agent:*` label restarts the workflow once the activation guardrails pass again.
- To reset failure count: edit the keepalive summary comment and set `failure: {}` in the state marker, then add `agent:retry` when the concrete recovery is ready.
- Keepalive stands down when **all acceptance criteria are checked complete**. At that point the orchestrator stops issuing further rounds.

---

## 12. Issue Context & Status Summary

The source issue is the task of record. The `auto-status-summary` block is a
machine-owned projection refreshed by PR metadata (`pr-meta` in the event hub).
Source-issue edits reach that block on the next metadata refresh, not immediately;
manual edits inside the block can be overwritten on regeneration. Keep durable
source tasks in the source issue. Reviewer-added checkboxes outside the block
remain in the PR body across regeneration, including before the managed preamble.
Keepalive includes those visible checkboxes in its dispatch decision, task appendix,
and live progress counts, so a completed summary cannot hide remaining PR work.
Blockquoted reviewer tasks count as visible work. Fenced examples, HTML comments,
placeholder tasks, status metrics, and the standard PR template Workflow Source
choices do not count as additional work. A live recount with outstanding work
removes any stale `automerge` label before publishing progress. Adding an outside checkbox does not mark it complete; it must
be explicitly checked after verification. It is not copied back to the source issue.


The Keepalive workflow depends on the **Automated Status Summary** block in the PR body to extract Scope, Tasks, and Acceptance Criteria.

### Data Flow
1. **Issue Intake:** Creates a PR with the Issue content embedded.
2. **PR Meta Update:** `agents-pr-meta` workflow parses the source Issue for Scope/Tasks/Acceptance and generates the Automated Status Summary block.
3. **Keepalive Execution:** The keepalive loop extracts tasks from the Automated Status Summary and injects them into the agent prompt via the task appendix.

### Failure Modes & Recovery
- **Missing Workflow Source:** If the PR lacks a source issue, it may still be valid. Add either a hidden `<!-- meta:issue:<issue_number> -->` marker plus a visible `Related to #<issue_number>` or `Closes #<issue_number>` line, or mark another valid source in the PR body/labels. Supported non-issue sources are local request, automation run, sync/maintenance campaign, Dependabot, review follow-up, and direct GitHub PR. Use `Related to` for active campaign/controller issues that must remain open.
- **Missing Sections:** If the source Issue lacks "Scope"/"Tasks"/"Acceptance", update the source Issue text.
- **No Tasks:** If no checkboxes are found, keepalive will stop with reason `no-checklists`.

---

## 13. Progress Detection & Checkbox Reconciliation

Keepalive now has two ways to detect task completion and keep PR checkboxes in sync:

1. **Session analysis (preferred):** After an agent run, `scripts/analyze_codex_session.py` analyzes the Codex JSONL session via `tools/codex_session_analyzer.py`. If an LLM provider is available, it returns a list of completed tasks plus quality signals (confidence, data quality, effort score).
2. **Commit/file analysis (fallback):** `.github/scripts/keepalive_loop.js` runs `analyzeTaskCompletion()` to match commits and changed files against unchecked tasks when LLM data is unavailable or incomplete.

### Auto-Update Rules
- **Auto-check only high confidence matches.** Low/medium confidence matches are logged but not applied.
- **Apply only to existing task/acceptance checkboxes.** Scope remains informational and is not mutated.
- **No changes when evidence is weak.** If no high-confidence matches exist, the PR body is left untouched.

### Operational Notes
- The keepalive summary comment flags when files changed but no checkboxes were updated, prompting the next iteration to reconcile tasks.
- The reconciliation step uses the same task text from the Automated Status Summary to avoid accidental mismatch.
- LLM analysis is optional; if unavailable, the commit/file matcher remains active.

### Deliberate-Break Gate

The Gate installs declared project dependencies before the proof, then removes
the installed head distribution so archived-base tests cannot import head code
from site-packages. Its successful pip install report identifies the requested
distribution for both `pyproject.toml` and `setup.py` projects. Missing/ambiguous
report metadata or a failed uninstall stops the job; a warning alone cannot
authorize a potentially contaminated base test. This isolation rule is identical
in the source Gate and the create-only consumer Gate template.

Gate runs an opt-in execution check when the PR body's Acceptance Criteria declares a deliberate-break marker:

```markdown
<!-- deliberate-break: test=tests/test_feature.py::test_runtime_contract test-file=tests/test_feature.py break-file=src/feature.py -->
```

When present, `scripts/check_deliberate_break.py` runs the named test on the PR head, archives the base ref, overlays only the named test file onto that base tree, and reruns the same test. The expected result is green on head and red on base; green on both is reported as `FAIL_HOLLOW`, and red on head is reported as `FAIL_BROKEN`. If no marker is present, the step logs `skipped: no deliberate-break marker` and exits successfully.

The default command is `python -m pytest <test-id> -o addopts= -q`: the named
head/base proof clears suite-wide pytest `addopts` (for example, full-suite
coverage or optional plugin switches). Other pytest configuration, including
`pythonpath`, stays active. This does not change the separate full-suite CI gate.
If the named test requires a custom option, preserve it with an explicit
`command=` in the marker; explicit commands are used unchanged on head and base:

```markdown
<!-- deliberate-break: test=tests/test_feature.py::test_runtime_contract test-file=tests/test_feature.py break-file=src/feature.py command="python -m pytest tests/test_feature.py::test_runtime_contract --run-integration -q" -->
```

An explicit command also retains repository `addopts` unless it explicitly
overrides them. Ensure the command actually executes the named test rather than
skipping it; otherwise the head/base proof can be hollow.

The same Gate step applies the `acceptance-criteria` label when a marker is present. That label arms the runtime acceptance merge guard so non-CI-verifiable merge lanes defer to the local Orchestrator runtime acceptance path instead of merging on prose evidence alone.

---

## Appendix: Operator Checklist

| Phase | Key Checks |
|-------|------------|
| Activation | `agent:*` label present · Gate success |
| Repeat | Activation guardrails still true · run cap respected · failure threshold not exceeded |
| Routing | Correct registry-backed agent workflow triggered based on label |
| Capacity | Mode recorded when automation is rate-limited, auth-blocked, or local-only |
| Prompt | Task appendix injected · Progress visible |
| Exit | All acceptance criteria satisfied or max iterations reached |

Keep this document in sync with [`MULTI_AGENT_ROUTING.md`](MULTI_AGENT_ROUTING.md) and [`Observability_Contract.md`](Observability_Contract.md) whenever the workflow evolves.

### Runner-dispatch debounce: productive vs. zero-output completions

The debounce that stops a runner being dispatched twice for the same work is keyed on
`(head_sha, provider)`. It used to record **any** finished dispatch as terminal `completed`,
including a run that produced nothing — and the only thing that clears that key is a new head
commit, which only the agent being refused could push. Clearing the gate required the action
the gate forbade (#3433).

That is not hypothetical. codex exits 0 when its Linux sandbox fails to start
(`bwrap: loopback: Failed RTM_NEWADDR`, #3438), reporting a successful turn with no commit and
no tasks done. Two consumer PRs sat frozen at iteration 1/12 for four hours while the hourly
sweep ran past them, because a debounced PR is indistinguishable from a healthy one.

**What the debounce does now:**

| Prior record for this head | Decision |
|---|---|
| `pending`, not yet stale | refuse — wait for the in-flight run |
| `completed`, productive | refuse — a new head commit is the next step |
| `completed`, unchanged head with unfinished checklist | dispatch a bounded continuation even if a checkbox advanced |
| `completed`, unchanged head with missing or changed checklist snapshot | dispatch a bounded continuation; unknown progress is not proof of completion |
| `completed`, zero-output, within the retry allowance | dispatch (`retry-unproductive-completion`) |
| `completed`, zero-output, allowance spent, cooldown running | refuse (`unproductive-cooldown`) |
| `completed`, zero-output, cooldown elapsed | dispatch (`retry-after-unproductive-cooldown`) |

Keepalive reservations persist a checklist baseline using the same visible Tasks and Acceptance
Criteria parser that drives dispatch. After summary reconciliation, completion records the live
PR head and a second checklist snapshot. Python marks the run productive when the head changed or
the same checklist gained at least one completed item. A changed checklist identity, missing
baseline, or failed lookup is **unmeasured**, not zero progress; it cannot manufacture task credit
or reset the bounded zero-output streak. Other callers retain the legacy `--produced-work`
verdict. A completion replay reuses its first persisted observation rather than crediting an
unrelated later body edit.
Productivity and completion are separate: advancing from 0/2 to 1/2 is productive but unfinished,
so the same-head reservation may continue. An attempted measured run with a missing, empty, or
changed after snapshot likewise cannot prove the checklist finished. The persisted
`completion_incomplete` flag and `continuation_completions` counter carry this disposition across
reservations and completion replays; older measured-partial records are recognized from their
stored after snapshot. The existing allowance and time-based cooldown bound continuations.
A measured fully checked list, an observed new head, or a new reservation head clears the
continuation latch.

GitHub Actions reservations also bind the repository, run ID and run attempt. Completion must
match that binding and head key before writing state; an explicitly productive result from
the owning attempt may report its new head. A late completion from an older run or
rerun attempt returns `recorded=false`, `reason=stale-attempt` without overwriting the newer
reservation. Rerun from the reservation step, not a completion-only job; an unmatched pending
reservation remains recoverable through the existing stale-pending timeout. Existing callers
without GitHub attempt identity retain legacy behavior. This is a workflow-attempt fence,
not an atomic compare-and-swap guarantee from the backing storage.

The authoritative PR-comment backend uses append-only `runner-reservation` markers
with a fresh reservation ID and separate `runner-completion` receipts bound to that
ID. A completion never PATCHes the reservation, so an older completion racing a new
reservation cannot overwrite its pending owner. Readers use the newest GraphQL
comment cursor, walk backward, and stop at the latest authoritative reservation,
joining only a matching trusted marked receipt. Cursor boundaries avoid the
offset-page shift when ordinary comments are deleted during a read. GraphQL
reads use full-width `fullDatabaseId` values for comment ordering and REST
receipt identities, including IDs beyond the legacy `databaseId` Int width.
If an older GHES schema rejects that field, the reader retries only that
unknown-field error with the legacy `databaseId` query; other GraphQL errors
still fail closed. GraphQL's bare `github-actions` login is normalized to the
trusted `github-actions[bot]` identity only when `author.__typename` is `Bot`;
a same-named non-Bot actor gains no marker authority. They use
`GITHUB_GRAPHQL_URL` when available; on GHES the fallback derives
`/api/graphql` from the REST `/api/v3` root. Legacy `runner-dispatch` records remain readable
until a new reservation exists; later writes by old clients cannot supersede the
new marker family. A completion retry reuses its own receipt (or returns without
writing when identical), preventing unbounded growth from retries. Missing or
malformed authority fails closed.

This is completion-write isolation, not serialization of simultaneous dispatch
attempts. Explicit repository-variable storage retains its legacy single-writer
contract; concurrent automation uses the authoritative PR-comment backend through
`--storage auto`. Reservation history is durable evidence; only the matching
completion receipt for an attempt may be updated, never the current reservation.

Signed authority challenges also reserve the current head and workflow attempt
before dispatch. The root and consumer loops invoke `should-dispatch
--authority-challenge` instead of emitting an unconditional permission to run.
That path reuses the existing HMAC envelope verifier and requires a workflow-dispatch
event, the trusted workflow bot, current run/attempt identity, and authoritative
auto storage. It conditionally prepares the head-bound ledger generation, writes
the primary reservation, consumes the exact preparation, and rereads the
attempt-bound reservation before granting. Preparation alone cannot run a worker
or accept completion. A definite reservation failure releases only that preparation;
ambiguous consumption or freshness failures remain spent and refuse dispatch.

With `--storage auto`, completion reads only the primary PR-comment reservation
and writes its matching receipt there, never to an empty or stale repository-variable fallback. A missing primary
reservation returns `recorded=false`, `reason=authoritative-reservation-missing`;
a primary read/write failure returns `reason=authoritative-storage-unavailable`.
These checks apply even when the completing job has no workflow identity. Automatic
dispatch also requires a successful primary read and reservation write. A storage
failure returns `should_dispatch=false`, `reason=authoritative-storage-unavailable`,
with a recovery instruction; it never creates a fallback-only reservation whose
completion could not be committed. If the primary has no record, existing fallback
records are still read for debounce: an older pending run must finish or age out
before the same head can be reserved in the primary. A failed legacy-state read
also refuses dispatch, rather than assuming no earlier run exists. In this migration
lookup, repository-variable HTTP 401/403 errors propagate as unavailable; only a
404 means the variable is absent. Explicit single-store reads retain their historical
best-effort authorization handling. Once the primary contains a record, the fallback
is not consulted or written. Recover by retrying
the reservation step after storage is healthy; no head change or manual state
cleanup is needed. A pending primary reservation retains its
stale-pending timeout. A failed reservation write response can be ambiguous, so
the caller immediately re-reads primary state and grants only if the exact pending
reservation was persisted; otherwise it refuses the dispatch. Explicit single-store callers
retain their existing read behavior. Repository-variable writes propagate
HTTP 401/403 failures instead of treating them as successful no-ops; callers
must not report a reservation or completion as persisted after a denied write.
The PATCH-404 to POST creation path remains supported.

Authoritative storage failures also emit a warning on stderr identifying reservation
or completion, the read/write operation, exception and cause types, and HTTP status
when available. Raw exception text,
URLs and response bodies are omitted so diagnostic logging does not expose credentials.

**Why the allowance expires into a cooldown rather than a refusal.** Refusing until the head
changes would put the original latch back one step further out. A cooldown is cleared by time
alone — nothing the gate forbids is needed to open it — and the hourly keepalive sweep wakes it.
For the same reason, a `completed_at` that cannot be parsed lets the dispatch through: a gate
that cannot measure itself must fail toward motion, not silence.

Every refusal states its drainable quantity next to its blocking state, so a run log never says
only that dispatch is closed without saying what would open it. A granted dispatch renders that
field empty, which keeps "no drainable path stated" from ever reading as "nothing is blocking".

Constants live in `scripts/runner_lib/core.py`:
`UNPRODUCTIVE_COMPLETION_RETRY_LIMIT` and `UNPRODUCTIVE_COMPLETION_COOLDOWN_SECONDS`.
