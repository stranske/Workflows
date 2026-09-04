# Label Reference Guide

This document describes all labels that trigger automated workflows or affect CI/CD behavior in repositories using the Workflows system.

## Quick Reference

| Label | Trigger | Effect
|-------|---------|--------
| `autofix` | PR labeled | Triggers automated code fixes
| `autofix:clean` | PR labeled | Triggers clean-mode autofix (more aggressive)
| `agent:codex` | Issue or PR labeled | Routes the issue or PR to the Codex agent
| `agent:claude` | Issue or PR labeled | Routes the issue or PR to the Claude Code agent
| `agent:cursor` | Issue or PR labeled | Routes consumer Gate-followup keepalive to the Cursor runner
| `agent:gemini` | Issue or PR labeled | Routes consumer Gate-followup keepalive to the Gemini runner
| `agent:aider` | Issue or PR labeled | Routes the issue or PR to the Aider agent for cheap, low-complexity tasks — runner lands in a follow-up phase
| `agent:auto` | Issue or PR labeled | Delegates routing to the auto-delegation policy; do not combine with concrete `agent:<name>` labels
| `agent:retry` | PR labeled | Consolidated consumers require a manual Gate-followups dispatch; the root/non-consolidated keepalive workflow forces a retry and clears recovery labels
| `agent:rate-limited` | Auto-applied | Marks a PR as backing off from a rate-limit failure
| ~~`agent:codex-invite`~~ | *(deprecated)* | No workflow, script, or tool references this label by name; the generic `agent:<name>-invite` mechanism in `reusable-agents-issue-bridge.yml` still works but this specific label is unmaintained — see detail section below
| `agent:needs-attention` | Auto-applied | Indicates agent needs human intervention
| `status:ready` | Issue labeled | Marks issue as ready for agent processing
| `agents:format` | Issue labeled | Direct issue formatting
| `agents:formatted` | Auto-applied | Indicates issue has been formatted
| `agents:optimize` | Issue labeled | Analyzes issue and posts suggestions
| `agents:apply-suggestions` | Issue labeled | Applies optimization suggestions
| `agents:auto-pilot` | Issue labeled | Runs issue-to-PR automation
| `agents:auto-pilot-pause` | Issue labeled | Pauses auto-pilot dispatch
| `agents:paused` | PR labeled | Pauses keepalive loop on PR
| `agents:keepalive` | PR labeled | Enables keepalive loop on PR
| `agents:max-runs:<K>` | PR labeled | Caps keepalive run count; `agents:max-runs:0` is an explicit hold
| `needs-human` | Issue or PR labeled | Blocks automation until a human clears the blocker
| `security:bypass-guard` | Issue or PR labeled | Bypasses prompt-injection guard after explicit approval
| `agents:allow-change` | PR labeled | Allows guarded automation changes that require explicit permission
| `automerge` | PR labeled | Marks a completed agent PR for guarded automerge
| `runtime-ac` / runtime verification labels | PR labeled | Blocks external auto-merge until local Orchestrator runtime AC checks pass
| `status:in-progress` | Issue labeled | Marks an issue claimed by the belt dispatcher/worker
| `from:<agent>` | PR labeled | Records the automation agent that produced the PR
| `runner:<agent>` | Issue labeled | Selects an auto-pilot runner without triggering issue intake
| `verify:checkbox` | PR labeled | Runs verifier checkbox mode after merge
| `verify:evaluate` | PR labeled | Runs verifier evaluation mode after merge
| `verify:compare` | PR labeled | Runs verifier comparison mode after merge
| `verify:create-issue` | PR labeled | Creates follow-up issue from verification
| `verify:create-new-pr` | PR labeled | Creates follow-up issue and PR from verification

---

## Autofix Labels

### `autofix`

**Applies to:** Pull Requests

**Trigger:** When applied to an open, non-draft PR

**Effect:** Initiates the CI Autofix Loop which:
1. Runs linting and formatting checks
2. Automatically commits fixes for:
   - Code formatting using the repository's configured formatters
   - Import organization
   - Trailing whitespace
   - Type annotation fixes (mypy suggestions)
3. Posts a summary comment on the PR

**Prerequisites:**
- PR must be from the same repository (not a fork)
- PR must not be in draft state
- PR must be open

**Workflow:** `autofix.yml` (CI Autofix Loop)

---

### `autofix:clean`

**Applies to:** Pull Requests

**Trigger:** When applied to an open, non-draft PR

**Effect:** Triggers a more aggressive "clean" mode autofix that:
1. Performs all standard autofix operations
2. Additionally runs cosmetic repairs
3. May reorganize imports more aggressively

**Note:** This label provides a stronger fix that might make more changes than the standard `autofix` label.

**Workflow:** `autofix.yml` (CI Autofix Loop)

---

## Agent Labels

### `agent:codex`

**Applies to:** Issues and Pull Requests

**Trigger:** When applied to an issue or PR

**Effect:**
1. Activates the Codex agent assignment workflow
2. Validates that a valid agent assignee is present
3. If validated, enables automated code generation for the issue
4. Creates a `codex/issue-<number>` branch for agent work
5. On PRs, routes keepalive evaluation through the local sweep and the registry-backed shared runner

**Prerequisites:**
- Issue must have a valid agent assignee (configured in repository settings)
- Issue should have clear requirements in the description

**Workflow:** `agents-issue-intake.yml` (Agents Issue Intake); on PRs, `agents-keepalive-sweep.yml` routes evaluation to the shared registry-backed implementation.

---

### `agent:claude`

**Applies to:** Issues and Pull Requests

**Trigger:** When applied to an issue or PR

**Effect:**
1. Routes the issue or PR to the Claude Code agent, the parallel surface to `agent:codex`
2. On issues, drives the same intake path as `agent:codex`; issue-triggered runs use invite mode and post human instructions rather than creating a branch/PR directly
3. On PRs, keepalive dispatches work via `reusable-claude-run.yml` per `.github/agents/registry.yml`
4. Branch prefix `claude/issue-<number>` is used for agent work (see `.github/agents/registry.yml`)

**Prerequisites:**
- Repository has a valid `CLAUDE_CODE_OAUTH_TOKEN` or `CLAUDE_AUTH_JSON` secret (per `.github/agents/registry.yml`)
- Issue or PR should have clear requirements

**Lifecycle:** Applied at issue claim / PR creation by an opener that already has Claude capacity. Removed when work completes (PR merged or issue closed). Co-applied with `agents:keepalive` on the PR so keepalive is enabled.

**Workflow:** `agents-auto-label.yml`, `agents-81-gate-followups.yml`, `agents-guard.yml`, `reusable-pr-context.yml`; runner is `reusable-claude-run.yml` per `.github/agents/registry.yml`.

---

### `agent:cursor`

**Applies to:** Issues and Pull Requests

**Trigger:** When applied to an issue or PR

**Effect:**
1. Identifies Cursor as the intended route in registry-aware automation
2. On PRs, dispatches the `run-cursor` consumer keepalive job in `agents-81-gate-followups.yml`
3. Branch prefix `cursor/issue-<number>` is reserved for Cursor work (see `.github/agents/registry.yml`)

**Prerequisites:**
- Repository has a valid `CURSOR_API_KEY` secret (per `.github/agents/registry.yml`)
- Issue or PR should have clear requirements

**Workflow:** On PRs, `agents-81-gate-followups.yml` dispatches `reusable-cursor-run.yml` after registry-backed routing and secret preflight succeed.

---

### `agent:gemini`

**Applies to:** Issues and Pull Requests

**Trigger:** When applied to an issue or PR

**Effect:**
1. Identifies Gemini as the intended route in registry-aware automation
2. On PRs, dispatches the `run-gemini` consumer keepalive job in `agents-81-gate-followups.yml`
3. Branch prefix `gemini/issue-<number>` is reserved for Gemini work

**Prerequisites:**
- Repository has a valid `GEMINI_API_KEY` secret (per `.github/agents/registry.yml`)

**Workflow:** On PRs, `agents-81-gate-followups.yml` dispatches `reusable-gemini-run.yml` after registry-backed routing and secret preflight succeed.

---

### `agent:aider`

**Applies to:** Issues and Pull Requests

Registered ahead of its runner (lands in a follow-up phase). `agent:aider` is reserved for cheap,
low-complexity tasks via Aider with a configurable backend model. Until its `reusable-aider-run.yml`
runner and registry entry ship, applying this label will not dispatch a runner. See
`docs/guides/ADD_NEW_AGENT.md` and the rollout plan for sequencing.

---

### `agent:auto`

**Applies to:** Issues and Pull Requests

**Trigger:** When applied to an issue or PR

**Effect:**
1. Delegates routing to the auto-delegation policy in `.github/scripts/agent_delegation_policy.js`
2. The policy switches between Codex and Claude based on stall/effectiveness signals
3. Used to recover from capacity-stuck PRs: **add** `agent:auto` to the PR (alongside the existing `agent:<name>` label); keepalive will override the concrete label and route through auto-delegation
4. Selects a runner through the delegation policy without mutating labels; if no current agent is recorded, the policy chooses the default available agent or the first available alternative

**Prerequisites:**
- When `agent:auto` is present, any co-present concrete `agent:<name>` label is silently ignored; `agent:auto` always wins
- Existing delegation state improves switch decisions, but the initial-selection path can choose an agent without a concrete label

**Lifecycle:** Applied manually or by orchestrator/closer when a PR is capacity-stuck. The delegation policy reads it on keepalive ticks and either keeps the current runner choice or switches the runner decision for that dispatch.

**Workflow:** `agents-auto-label.yml`, `reusable-pr-context.yml`, `agents-capability-check.yml`, `agents-guard.yml`; policy implementation is `.github/scripts/agent_delegation_policy.js`.

---

### `agent:retry`

**Applies to:** Pull Requests

**Trigger:** Recovery marker only; applying the label does not trigger a retry by itself

**Effect:**
1. Records that a retry was requested
2. Does not set `force_retry` or remove recovery labels merely by being applied

**Prerequisites:**
- PR has a concrete `agent:codex` or `agent:claude` label so a runner can be re-dispatched
- PR has `agents:keepalive`

**Recovery:** Force a bounded retry by manually dispatching `agents-81-gate-followups.yml` with `pr_number=<PR>` and `force_retry=true`; after the run is confirmed, remove stale recovery labels manually if they remain.

**Workflow:** `agents-81-gate-followups.yml` accepts the explicit `force_retry` dispatch input; no Workflows-local fallback is attempted.

---

### `agent:rate-limited`

**Applies to:** Pull Requests

**Trigger:** Auto-applied by workflows during rate-limit backoff

**Effect:**
1. Marks the PR as currently backed off due to API/runner rate limits
2. Used with the matching concrete `agent:<name>` label to flag backoff for the current route; switch to `agent:auto` only after removing the concrete routing label
3. Remains an observability/backoff marker until automation or an operator explicitly removes it

**Prerequisites:**
- Applied automatically; no manual action required

**Lifecycle:** Applied when a dispatch hits a rate limit. It does not by itself trigger a runner, and the current consumer Gate-followup wrapper does not promise label cleanup. After a successful forced retry, remove it manually if it remains.

**Workflow:** Producer workflows apply the marker; recovery uses an explicit `agents-81-gate-followups.yml` dispatch with `force_retry=true`.

---

### ~~`agent:codex-invite`~~ *(deprecated)*

> **Deprecated.** `grep -rn codex-invite .github/ scripts/ tools/` returns no matches. The label is not referenced by name in any active workflow, script, or tool. The underlying `-invite` suffix mechanism in `reusable-agents-issue-bridge.yml` remains functional for any `agent:<name>-invite` label, but `agent:codex-invite` specifically is unmaintained. Do not apply this label; use `force_mode: false` at the workflow call site instead if you need invite-mode control.

**Applies to:** Issues (must be paired with `agent:codex`)

**Trigger:** When applied to an issue together with `agent:codex`

**Effect:**
1. The issue-bridge label parser in `.github/workflows/reusable-agents-issue-bridge.yml` strips the `-invite` suffix and records `invite=true` for the base `agent:codex` entry (see the `inviteSuffix` handling around the `parses agent:<name>-invite` block).
2. The mode-resolution step then selects `invite` mode for codex when the calling workflow does not force its input mode (`force_mode: false`). If the caller leaves `force_mode` at its default `true`, the bridge respects the requested input mode instead.
3. Applying `agent:codex-invite` alone (without `agent:codex`) is rejected: the bridge fails with `Invite labels (agent:codex-invite) require a matching base agent:<name>.`

**Workflow:** `.github/workflows/reusable-agents-issue-bridge.yml` (label parser + mode resolution). The generic `agent:<name>-invite` mechanism is implemented in the same file, so the same pattern applies to other concrete agents.

---

### `runner:<agent>`

**Applies to:** Issues

**Trigger:** When applied to an issue that also has `agents:auto-pilot`

**Effect:**
1. Overrides the agent that auto-pilot will use (`runner:claude`, `runner:codex`, etc.)
2. Auto-pilot reads this label during capability/check-pr steps and adds the matching `agent:<name>` label when it dispatches the belt
3. Does **not** trigger the issue intake workflow by itself, so manual `agent:<name>` behavior is unaffected

**Workflow:** `agents-auto-pilot.yml`

---

### `agent:needs-attention`

**Applies to:** Issues and Pull Requests

**Trigger:** Automatically applied by workflows

**Effect:**
1. Signals that human intervention is required
2. Agent processing is paused until addressed
3. Typically applied when:
   - Agent encounters an error
   - CI checks fail repeatedly
   - Agent requests clarification

**Action Required:** Review the issue/PR, address concerns, and remove the label to resume agent processing.

**Workflow:** Multiple workflows may apply this label

---

### `status:ready`

**Applies to:** Issues

**Trigger:** When applied to an issue with agent labels

**Effect:**
1. Marks the issue as ready for agent processing
2. Used in conjunction with `agent:codex` to signal readiness
3. May trigger the next step in the agent automation pipeline

**Workflow:** `agents-issue-intake.yml` handles ordinary agent intake. The
separate `agents:auto-pilot` route dispatches Agents 71 and the Agents 72
wrapper when end-to-end automation is requested.

---

## Issue Formatting Labels (LangChain Enhancement)

These labels control the LangChain-powered issue formatting pipeline introduced in #484.

### `agents:format`

**Applies to:** Issues

**Trigger:** When applied to an issue

**Effect:**
1. Automatically formats the raw issue body into the AGENT_ISSUE_TEMPLATE structure
2. Uses LLM (GitHub Models API) with fallback to regex-based formatting
3. Adds proper sections: Why, Scope, Non-Goals, Tasks, Acceptance Criteria, Implementation Notes
4. Converts task items to checkboxes
5. Replaces the issue body with formatted version
6. Removes `agents:format` label and adds `agents:formatted`

**Use Case:** Quick, one-step formatting without review. Best for issues that are already well-structured but need template compliance.

**Workflow:** `agents-issue-optimizer.yml`

---

### `agents:formatted`

**Applies to:** Issues

**Trigger:** Automatically applied after formatting completes

**Effect:**
1. Indicates the issue has been formatted to AGENT_ISSUE_TEMPLATE
2. Signals the issue is ready for agent processing
3. Prevents re-formatting (workflows skip issues with this label)

**Note:** This is a result label, not a trigger label. Do not apply manually.

**Workflow:** Applied by `agents-issue-optimizer.yml`

---

### `agents:optimize`

**Applies to:** Issues

**Trigger:** When applied to an issue

**Effect:**
1. Analyzes the issue for agent compatibility and formatting quality
2. Posts a comment with suggestions including:
   - Tasks that are too broad (should be split)
   - Tasks the agent cannot complete (with reasons)
   - Subjective acceptance criteria (with objective alternatives)
   - Missing sections or formatting issues
3. Includes embedded JSON with structured suggestions
4. Prompts user to add `agents:apply-suggestions` to apply changes

**Use Case:** Two-step formatting with human review. Best for issues needing significant restructuring.

**Workflow:** `agents-issue-optimizer.yml`

---

### `agents:apply-suggestions`

**Applies to:** Issues

**Trigger:** When applied to an issue that has received optimization suggestions

**Prerequisites:**
- Issue must have a comment with optimization suggestions (from `agents:optimize`)
- The suggestions comment must contain valid JSON in `<!-- suggestions-json: -->` marker

**Effect:**
1. Extracts approved suggestions from the analysis comment
2. Applies all suggestions to reformat the issue body
3. Moves blocked tasks to "## Deferred Tasks (Requires Human)" section
4. Removes both `agents:optimize` and `agents:apply-suggestions` labels
5. Adds `agents:formatted` label

**Workflow:** `agents-issue-optimizer.yml`

---

## Workflow Source Labels

These labels let direct GitHub PRs and non-issue-origin PRs integrate with
Workflows source classification without forcing a GitHub issue.

| Label | Applies to | Effect
|-------|------------|--------
| `workflow:source-issue` | Pull Requests | PR source is a GitHub issue.
| `workflow:source-local-request` | Pull Requests | PR source is a local Codex/user request.
| `workflow:source-automation` | Pull Requests | PR source is an automation or workflow run.
| `workflow:source-sync` | Pull Requests | PR source is a sync or maintenance campaign.
| `workflow:source-dependabot` | Pull Requests | PR source is Dependabot or dependency automation.
| `dependency:repair-promotion` | Pull Requests | Agent-owned replacement whose first commit reproduces a classified dependency-bot delta.
| `workflow:source-review-followup` | Pull Requests | PR source is review feedback follow-up.
| `workflow:source-direct-pr` | Pull Requests | PR was started directly on GitHub without a source issue.
| `workflow:no-automation` | Pull Requests | Fully opts the PR out of automation management and automation-triggered follow-up actions.
| `workflow:source-needed` | Pull Requests | Source context is missing or ambiguous.

The Workflow Source table is validated as a three-column Markdown table so label
rows do not introduce an extra empty column in GitHub rendering.

Use these labels as a backup to the PR template's Workflow Source section. If a
PR has no linked issue and no valid Workflow Source, the PR metadata automation
posts one repair comment instead of repeatedly treating the PR as issue-delivery
work.

---

## Verifier Labels

These labels trigger the post-merge verifier workflow on a merged PR.

### `verify:checkbox`

**Applies to:** Pull Requests

**Trigger:** When applied to a merged PR

**Effect:** Verifies acceptance criteria checkbox completion and opens follow-up issues if gaps are detected.

**CI failure hard gate:** If any polled CI workflow concludes `failure` on the merge commit, the verdict is floored at CONCERNS before the LLM runs, so a merge that breaks `main` can never verify PASS.

**Workflow:** `agents-verifier.yml`

---

### `verify:evaluate`

**Applies to:** Pull Requests

**Trigger:** When applied to a merged PR

**Effect:** Runs an LLM evaluation of the work and posts a report with optional follow-up issues.

**CI failure hard gate:** If any polled CI workflow concludes `failure` on the merge commit, the verdict is floored at CONCERNS before the LLM runs, so a merge that breaks `main` can never verify PASS.

**Workflow:** `agents-verifier.yml`

---

### `verify:compare`

**Applies to:** Pull Requests

**Trigger:** When applied to a merged PR

**Effect:** Runs the verifier across multiple models and posts a comparison report.

**CI failure hard gate:** If any polled CI workflow concludes `failure` on the merge commit, the verdict is floored at CONCERNS before the LLM runs, so a merge that breaks `main` can never verify PASS.

**Workflow:** `agents-verifier.yml`

---

### `verify:create-issue`

**Applies to:** Pull Requests

**Trigger:** When applied to a merged PR that has verification feedback

**Prerequisites:**
- PR must be merged
- PR must have a verification comment (from `verify:evaluate` or `verify:compare`)

**Effect:**
1. Extracts concerns and low scores from verification feedback
2. Creates a new follow-up issue with:
   - Link to original PR
   - Extracted concerns from verification
   - Scores below 7/10
   - Suggested tasks for addressing issues
3. Posts comment on original PR linking to new issue
4. Removes the `verify:create-issue` label after completion
5. Adds `agents:optimize` label to new issue for agent formatting

**Use Case:** User-triggered creation of follow-up work from verification feedback. Replaces automatic issue creation which was too aggressive.

**Workflow:** `agents-verify-to-issue-v2.yml`

---

### `verify:create-new-pr`

**Applies to:** Pull Requests

**Trigger:** When applied to a merged PR that has verification feedback

**Prerequisites:**
- PR must be merged
- PR must already have verification context (for example from `verify:evaluate` or `verify:compare`)

**Effect:**
1. Creates a follow-up issue from verification concerns
2. Creates and bootstraps a follow-up PR for that issue
3. Removes `verify:create-new-pr` label after processing

**Workflow:** `agents-verify-to-new-pr.yml`

---

## Keepalive Control Labels

### `agents:paused`

**Applies to:** Pull Requests

**Trigger:** When applied to a PR with active keepalive

**Effect:**
1. Pauses all keepalive activity on the PR
2. Agent will not be dispatched until label is removed
3. Useful for manual intervention or debugging

**To Resume:** Remove the `agents:paused` label.

**Workflow:** `agents-81-gate-followups.yml`

---

### `agents:keepalive`

**Applies to:** Pull Requests

**Trigger:** When applied to a PR

**Effect:**
1. Enables the keepalive loop for the PR
2. Agent continues working until all tasks are complete
3. Tracks progress and updates PR status

**Prerequisites:**
- PR must have an `agent:*` label
- Gate workflow must pass

**Workflow:** `agents-81-gate-followups.yml`

---

### `agents:max-runs:<K>`

**Applies to:** Pull Requests

**Trigger:** Read during keepalive evaluation

**Effect:**
1. Caps how many keepalive rounds a PR may run.
2. `agents:max-runs:0` is an explicit hold and prevents dispatch.
3. Values `K >= 1` are enforced by the keepalive loop when it evaluates the PR.

**Consumer:** `.github/scripts/keepalive_gate.js` parses the prefix, and
`.github/scripts/keepalive_loop.js` enforces the zero-run hold alongside
`agents:paused` and `needs-human`.

---

### `needs-human`

**Applies to:** Issues and Pull Requests

**Trigger:** Read by agent, keepalive, verifier, and guard workflows

**Effect:**
1. Stops automation until a human removes the label.
2. Marks an independently confirmed policy, product, or external authority
   blocker; automation failure or exhausted retries alone are insufficient.
3. May be applied by verifier follow-up policy, auto-pilot blockers, and
   capability checks only after they record the exact human action. Keepalive
   failures use `agent:retry` or `agent:needs-attention`, not this label.

**Consumers:** `.github/scripts/keepalive_loop.js`,
`.github/workflows/agents-auto-pilot.yml`,
`.github/workflows/agents-verify-to-new-pr.yml`,
`.github/workflows/agents-capability-check.yml`.

---

### `security:bypass-guard`

**Applies to:** Issues and Pull Requests

**Trigger:** Prompt-injection guard evaluation

**Effect:**
1. Explicitly bypasses the prompt-injection guard after a trusted reviewer has
   accepted the risk.
2. Should be used narrowly and removed after the guarded action completes.

**Consumer:** `.github/scripts/prompt_injection_guard.js`.

---

### `agents:allow-change`

**Applies to:** Pull Requests

**Trigger:** Agent guard evaluation

**Effect:**
1. Signals maintainer permission for protected automation changes after the
   change has been justified.
2. Allows the guard to pass without Code Owner approval only when every
   protected workflow diff is limited to `uses: owner/action@ref` dependency
   reference updates and the PR author is Dependabot, Renovate, or a repository
   owner/member/collaborator.
3. Does not bypass review for protected workflow logic edits, deletes, renames,
   or dependency changes whose patch cannot be inspected.

**Consumers:** `.github/scripts/agents-guard.js`,
`.github/workflows/maint-auto-label-dep-prs.yml`.

---

### Runtime AC merge labels

**Labels:** `runtime-ac`, `runtime-verification`, `acceptance-criteria`,
`verification-spec`, `verification-plan`, `ac-checks`, `runtime-checks`

**Applies to:** Pull Requests

**Trigger:** Runtime acceptance criteria or verification labels applied to a PR.
Prefixed labels such as `verify:runtime-ac` are treated the same as
`runtime-ac`.

**Effect:**
1. Blocks external merge lanes from merging the PR directly.
2. Requires maintainers to merge through the local Orchestrator runtime AC guard
   after the runtime acceptance spec passes.
3. Fails closed if an external merge lane cannot read PR labels.

**Consumers:** `.github/scripts/runtime_ac_merge_guard.js`,
`.github/workflows/agents-73-codex-belt-conveyor.yml`,
`.github/workflows/agents-81-gate-followups.yml`. Agents 73 is callable-only;
Agents 81 is the active local guarded merge route.

---

### `automerge`

**Applies to:** Pull Requests

**Trigger:** Guarded merge sweeps

**Effect:**
1. Marks a completed agent PR as eligible for the guarded automerge path.
2. Does not bypass required checks, branch protection, or review policy.
3. Is applied by keepalive on a tasks-complete success terminal when appropriate.

**Consumers:** `.github/scripts/keepalive_loop.js`,
`.github/scripts/merge_manager.js`,
`.github/workflows/agents-auto-pilot.yml`,
`.github/workflows/agents-81-gate-followups.yml`.

---

### `status:in-progress`

**Applies to:** Issues

**Trigger:** Belt dispatcher or worker claim

**Effect:**
1. Records that an issue has active belt work in progress.
2. Is cleared by Agents 81 after it successfully merges the linked completed PR.
3. Is also cleared by Agents 73 when that callable-only recovery path is invoked.

**Consumers:** `.github/workflows/agents-71-codex-belt-dispatcher.yml`,
`.github/workflows/agents-72-codex-belt-worker.yml`,
`.github/workflows/agents-81-gate-followups.yml`, and the callable-only
`.github/workflows/agents-73-codex-belt-conveyor.yml` recovery component.

---

### `from:<agent>`

**Applies to:** Pull Requests

**Trigger:** PR creation or verification follow-up creation

**Effect:**
1. Records the automation source that produced a PR, such as `from:codex`,
   `from:claude`, or `from:auto`.
2. Helps merge and verifier tooling distinguish agent-origin PRs from manual PRs.

**Consumers:** `.github/scripts/merge_manager.js`,
`.github/workflows/agents-72-codex-belt-worker.yml`,
`.github/workflows/agents-verify-to-new-pr.yml`,
`.github/workflows/agents-verify-to-issue-v2.yml`,
`.github/workflows/reusable-agents-verifier.yml`.

---

## Informational Labels

These labels are used for categorization but do not trigger workflows.

### `follow-up`

**Applies to:** Issues

**Effect:** Indicates this issue was created as follow-up to another issue or PR.

**Applied by:** `agents-verify-to-issue-v2.yml` workflow

---

### `needs-formatting`

**Applies to:** Issues

**Effect:** Indicates the issue needs formatting to AGENT_ISSUE_TEMPLATE structure.

**Applied by:** Issue lint workflow (when enabled)

---

## CI/Build Labels

### `skip-ci` (if configured)

**Applies to:** Pull Requests

**Effect:** Some workflows may skip when this label is present. Check individual workflow configurations.

---

## Label Interaction Matrix

| Existing Label | New Label Added | Result
|---------------|-----------------|--------
| (none) | `autofix` | Triggers autofix
| `autofix` | `autofix:clean` | May trigger clean mode
| (none) | `agent:codex` | Triggers agent assignment (Codex runner)
| (none) | `agent:claude` | Triggers agent assignment (Claude runner)
| (none) | `agent:auto` | Delegates routing to `agent_delegation_policy.js`
| `agent:codex` | `agent:auto` | Invalid mixed routing; remove `agent:codex` before using `agent:auto`
| `agent:claude` | `agent:auto` | Invalid mixed routing; remove `agent:claude` before using `agent:auto`
| `agent:<name>` + `agents:keepalive` | `agent:retry` | Consolidated: records a recovery request; root/non-consolidated: forces the keepalive retry and cleanup handler
| `agent:retry` | Manual Gate-followups dispatch | Consolidated only: forces the retry and does not imply automatic label cleanup
| `agent:rate-limited` | Successful forced retry | Remove stale recovery labels manually if automation leaves them behind
| `agent:codex` | `agent:codex-invite` | Selects issue-bridge `invite` mode for `agent:codex` when `force_mode: false`; with the default forced input mode, the requested mode still wins
| `agent:codex` | `status:ready` | Agent begins processing
| `agent:needs-attention` | (removed) | Agent resumes processing
| (none) | `agents:format` | Direct formatting
| (none) | `agents:optimize` | Analyzes and posts suggestions
| `agents:optimize` | `agents:apply-suggestions` | Applies suggestions, adds `agents:formatted`
| `agents:formatted` | `agent:codex` | Issue ready for agent processing
| `agents:auto-pilot` | `runner:<agent>` | Auto-pilot uses the selected runner when it dispatches work
| (none) | `agents:keepalive` | Enables keepalive monitoring for an agent PR
| `agents:keepalive` | `agents:paused` | Pauses keepalive and agent dispatch until resumed
| `agents:paused` | (removed) | Keepalive can resume on the next eligible event
| Merged PR with verifier report | `verify:create-issue` | Creates a verifier follow-up issue
| Merged PR with verifier report | `verify:create-new-pr` | Creates and bootstraps a verifier follow-up PR

---

## Troubleshooting

### Autofix not running

1. Check that the PR is not a draft
2. Verify the PR is from the same repository (not a fork)
3. Check the Actions tab for any failed workflow runs

### Agent not processing issue

1. Verify `agent:codex` label is present
2. Check that a valid agent assignee is assigned
3. Look for `agent:needs-attention` label
4. Review the workflow run logs in the Actions tab

### Label applied but nothing happened

1. Labels only trigger on the `labeled` event - re-applying won't re-trigger
2. Remove and re-add the label to trigger again
3. Check workflow permissions in repository settings

---

## For Repository Administrators

### Configuring Agent Assignees

Valid agent assignees are configured per-repository. Contact your repository administrator to:
1. Add new agent assignees
2. Modify agent permissions
3. Configure agent environments

### Adding New Label Triggers

To add new label-triggered functionality:
1. Update the relevant workflow file
2. Add the label to this documentation
3. Sync documentation to consumer repositories

---

*Last updated: May 13, 2026*

> **Source of truth.** This file is the canonical consumer label inventory. It is synced to every supported consumer repository via `.github/sync-manifest.yml` (`templates/consumer-repo/docs/LABELS.md` → `docs/LABELS.md`); changes here propagate on the next scheduled sync.
*Source of truth: Workflows repository*
