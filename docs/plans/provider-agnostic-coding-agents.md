# Provider-Agnostic Coding Agents Plan (Phased, Codex-Safe)

**Status:** In progress — Phases 0–4 marked complete but **significant gaps remain** (see audit below); Phase 5 partially started

## Progress (as implemented)

- ✅ Phase 0 — Runner hardening
- ✅ Phase 1 — Agent registry + resolver helper
- ⚠️ Phase 2 — Registry-driven PR automation routing (keepalive/autofix done; **bot-comment partially hardcoded**)
- ⚠️ Phase 3 — Registry-driven issue→PR path (**auto-pilot partially done; orchestrators/auto-label/gate-followups still hardcoded**)
- ⚠️ Phase 4 — Verifier + follow-up chain (**reusable verifier done; verify-to-issue/verify-to-new-pr partially done**)
- 🟡 Phase 5 — Delegation / re-routing between agents (kickoff done: `agent:auto` label semantics)

> **Feb 18 2026 audit note:** An independent audit of every workflow in both
> `.github/workflows/` and `templates/consumer-repo/` found that Phases 2–4
> were marked "complete" prematurely. Significant hardcoded `agent:codex`
> references remain. See **§ Audit: Remaining Hardcoded References** below.

## Claude availability (current reality)

- ✅ Claude *API* integration is already present (workflows pass `CLAUDE_API_STRANSKE` and install `langchain-anthropic`).
- ✅ `reusable-claude-run.yml` now exists and is called from keepalive-loop and autofix-loop.
- ✅ Phase 5A added `run-claude` jobs to keepalive-loop and autofix-loop templates.

## Why

The Workflows repo has a strong, production-hardened Codex CLI runner and a working end-to-end agent pipeline (auto-pilot → PR → keepalive → verify). However, many parts of the system encode “Codex-ness” (labels, branch names, workflow routing, mentions, follow-up defaults), making it hard to:

- add additional providers without duplicating logic,
- switch providers safely,
- and support controlled delegation between agents based on capacity/effectiveness.

This plan defines an incremental refactor that keeps **Codex as the default** until each phase is explicitly enabled.

## Goals

- Make the “coding agent execution” plumbing **provider-agnostic** while preserving existing Codex behavior.
- Centralize agent-specific assumptions (runner workflow, required secrets, branch scheme, mention policy, capability constraints).
- Enable optional **delegation / re-routing** between agents (system-driven, policy constrained).
- Maintain strict **no-noise** and keepalive invariants (see `docs/keepalive/GoalsAndPlumbing.md`).
- Keep consumer repos safe: phased rollout, explicit template sync, validation gates.

## Non-goals (for this plan)

- Replacing Codex as the default everywhere on day one.
- Introducing a new UI-triggering comment mechanism (avoid `@codex`-style triggers where it could activate UI agents).
- Rewriting the whole pipeline (auto-pilot sequencing, keepalive guardrails, verification pipeline) in one PR.

## Canonical Constraints to Respect

- Keepalive contracts:
  - `docs/keepalive/GoalsAndPlumbing.md`
  - `docs/keepalive/Agents.md`
  - `docs/keepalive/MULTI_AGENT_ROUTING.md`
  - `docs/keepalive/Observability_Contract.md`
- Sync policy for consumer templates:
  - Sync-able artifacts must be declared in `.github/sync-manifest.yml`.
  - Any synced workflow changes require mirrored updates under `templates/consumer-repo/`.
- Noisy artifacts must not be committed/synced inadvertently (especially under `.github/` and `templates/`).

## Audit: Remaining Hardcoded References (Feb 18, 2026)

A full audit of every `agents-*.yml`, `reusable-*.yml`, and consumer template
was conducted on Feb 18, 2026. Below is the complete inventory of remaining
hardcoded `agent:codex` references and other agent-specific coupling, organized
by which phase should have addressed them.

### Pre-existing bug: `agents-pr-meta-v4.yml` dispatch

The auto-pilot template at line 2392 dispatches `agents-pr-meta-v4.yml`. This
file has **never existed** in any consumer repo (confirmed across Counter_Risk,
Portable-Alpha-Extension-Model, Trend_Model_Project, Travel-Plan-Permission).
It only exists in the Workflows repo's own `.github/workflows/`. The dispatch
silently fails (try/catch) in every consumer repo, meaning the "Automated
Status Summary" PR body build is never triggered by auto-pilot on PR creation.

- `agents-pr-meta-v4.yml` briefly existed in Trend_Model_Project (Nov 30 – Dec 30, 2025) before the consumer-pattern migration removed it.
- The consumer template has `agents-pr-meta.yml` (thin caller) which **does** support `workflow_dispatch` with the same inputs (`pr_number`, `debug`).
- **Fix:** Change line 2392 to dispatch `agents-pr-meta.yml` (or check for `agents-80-pr-event-hub.yml` when `USE_CONSOLIDATED_WORKFLOWS` is set).

### Phase 2 gaps (PR automation routing)

| File | Line(s) | Issue |
|------|---------|-------|
| `reusable-bot-comment-handler.yml` | 185, 191 | Hardcoded `labelSet.has('agent:claude')` / `labelSet.has('agent:codex')` instead of using registry resolver |

Phase 2 scope included `reusable-bot-comment-handler.yml` but the current
implementation checks labels by string comparison rather than using
`resolveAgentFromLabels()`.

### Phase 3 gaps (issue→PR path)

| File | Line(s) | Issue |
|------|---------|-------|
| **`agents-auto-pilot.yml`** | 345 | `hasAgentCodex = labels.includes('agent:codex')` — used for early-exit check |
| **`agents-auto-pilot.yml`** | 1532 | Comment text: `needs-human instead of agent:codex` |
| **`agents-auto-pilot.yml`** | 2373 | PR creation hardcodes `labels: ['agent:codex', 'agents:keepalive', 'autofix']` — should use `agentKey` |
| **`agents-auto-pilot.yml`** | 2383 | Status message hardcodes `` `agent:codex` `` |
| **`agents-auto-pilot.yml`** | 2392 | Dispatches `agents-pr-meta-v4.yml` (see bug above) |
| **`agents-auto-label.yml`** | 34 (template 29) | Guard condition: `!contains(..., 'agent:codex')` — should check all `agent:*` labels |
| **`agents-70-orchestrator.yml`** | 74 | `bootstrap_issues_label: "agent:codex"` — hardcoded |
| **`agents-orchestrator.yml`** (template) | 78 | `bootstrap_issues_label: "agent:codex"` — hardcoded |

The auto-pilot's issue-labeling path (line 1709–1736) was updated to use
`loadAgentRegistry()`, but the **PR creation path** (line 2373) was missed.
Both orchestrator workflows and auto-label were not touched at all.

### Phase 4 gaps (verifier + follow-up)

| File | Line(s) | Issue |
|------|---------|-------|
| `reusable-agents-verifier.yml` | 310, 333, 993 | Falls back to `agentKey = 'codex'` (acceptable); line 993 hardcodes `'agent:codex'` as fallback label |
| `agents-verify-to-issue-v2.yml` | 341, 352, 354 | Falls back to `agentKey = 'codex'` (acceptable); line 409 text: `agent:codex` |
| `agents-verify-to-issue.yml` | 186 | Text: `agent:codex` in user-facing instruction |
| `agents-verify-to-new-pr.yml` | 741, 753, 755 | Falls back to `agentKey = 'codex'` (acceptable) |

Most of these use `resolveAgentFromLabels()` with a codex fallback, which is
the intended behavior. The user-facing text references are cosmetic but should
use the resolved agent name.

### Phase 5A gaps (labels + capability check)

| File | Line(s) | Issue |
|------|---------|-------|
| `agents-capability-check.yml` | 25 | Done — triggers on `["agent:codex","agent:claude","agent:auto"]` |
| `agents-keepalive-loop.yml` | 483-484 | Comment: "Currently supports: agent:codex -> CLI Codex / Future: agent:claude, etc." — **outdated**, run-claude now exists |
| `agents-keepalive-loop.yml` | 490 | Comment: "Only run for agent:codex label" — outdated |

### Workflows-internal files not synced to consumers

| File | Line(s) | Issue |
|------|---------|-------|
| `agents-63-issue-intake.yml` | 129, 1178, 1463 | Hardcoded `agent:codex` references |
| `agents-64-verify-agent-assignment.yml` | 28, 144, 207, 215, 221, 252 | Entire workflow is codex-specific (checks for `agent:codex` label) |
| `reusable-16-agents.yml` | 91, 527, 543, 563, 621, 623 | Hardcoded `agent:codex` default and label checks |
| `reusable-pr-context.yml` | 221 | `pr.hasAnyLabel(['agent:codex', 'agent:copilot', 'agents:keepalive'])` — missing `agent:claude` and `agent:auto` |

### Consumer template: `agents-81-gate-followups.yml`

| Line(s) | Issue |
|---------|-------|
| 280-281 | Comment: "Currently supports: agent:codex -> CLI Codex" — outdated |
| 288-289 | `if: needs.evaluate.outputs.agent_type == 'codex'` — only runs for codex |
| 318 | `run-claude` commented out (placeholder) |
| 486 | `CODEX_SUMMARY` env var name — should be `AGENT_SUMMARY` (keepalive-loop already changed this) |
| 503, 512 | Summary uses codex-only outputs |
| 705 | `labels.includes('agent:codex')` — hardcoded |
| 715 | Comment: "do NOT add agent:codex label" — hardcoded |

**`agents-81-gate-followups.yml` is the largest gap.** It mirrors keepalive-loop's
pre-Phase-5A structure (codex-only `run-codex` job, no `run-claude`, hardcoded
summary references). Phase 5A updated keepalive-loop but entirely missed
gate-followups.

### Scripts with hardcoded references

| File | Issue |
|------|-------|
| `scripts/cleanup_labels.py` | References `agent:codex` in label cleanup logic |
| `scripts/keepalive-runner.js` | References `agent:codex` |
| `scripts/langchain/pr_verifier.py` | References `agent:codex` |

### Consumer repo state (all four repos, Feb 18 2026)

| Item | Counter_Risk | Portable-Alpha | Trend_Model_Project | Travel-Plan-Permission |
|------|---|---|---|---|
| `agents-pr-meta-v4.yml` | **Missing** | **Missing** | **Missing** | **Missing** |
| `agents-pr-meta.yml` | Present | Present | Present | Present |
| `agents-80-pr-event-hub.yml` | Missing | Present | Present | ? |
| `agent_registry.js` | Present | Present | Present | Present |
| `agent_delegation_policy.js` | Present | Present | Present | Present |
| `.github/agent-config.yml` | **Missing** | **Missing** | **Missing** | **Missing** |
| `USE_CONSOLIDATED_WORKFLOWS` var | **Not set** | Not set | Not set | Not set |

> No consumer repo has `.github/agent-config.yml`, so `agent_registry.js`
> always falls back to `default_agent: 'codex'`. This is acceptable for now
> but means registry-driven routing has no effect until the config file is
> created or the registry default is changed.

---

## Current State (Snapshot)

### What's in good shape (post-Phase 5A)

- Keepalive prompt + task appendix is agent-agnostic.
- Keepalive evaluate step extracts `agent_type` from `agent:*` labels.
- `reusable-codex-run.yml` and `reusable-claude-run.yml` both exist and conform to the runner output contract.
- Keepalive-loop has both `run-codex` and `run-claude` jobs with merged outputs.
- Autofix-loop has both `autofix-codex` and `autofix-claude` jobs.
- Capability check triggers on `agent:codex`, `agent:claude`, and `agent:auto`.
- Auto-pilot issue labeling uses `loadAgentRegistry()` for dynamic agent selection.
- Belt workflows (71/72/73) accept `agent_key` parameter and are largely agent-agnostic.
- Verifier and follow-up workflows use `resolveAgentFromLabels()`.

### Where Codex coupling remains (work needed)

- **Auto-pilot PR creation path:** Hardcodes `['agent:codex', ...]` labels on PR creation (line 2373) — Phase 3 gap.
- **Auto-pilot PR meta dispatch:** Dispatches `agents-pr-meta-v4.yml` which doesn't exist in consumers — pre-existing bug.
- **Gate-followups:** Entire workflow still codex-only (no `run-claude`, hardcoded labels/summary) — Phase 5A gap.
- **Auto-label:** Guard condition only checks `agent:codex` — Phase 3 gap.
- **Both orchestrators:** Hardcode `bootstrap_issues_label: "agent:codex"` — Phase 3 gap.
- **reusable-16-agents:** Hardcodes `agent:codex` as default label — Phase 2 gap.
- **reusable-pr-context:** Missing `agent:claude`/`agent:auto` in label check — Phase 5A gap.
- **agents-64-verify-agent-assignment:** Entirely codex-specific — Phase 4 gap.
- **Outdated comments** in keepalive-loop and gate-followups say "Future: agent:claude" when `run-claude` already exists.

## Phase Plan

### Phase 0 — Runner hardening (no behavior change)

**Objective:** Make the existing Codex runner safer and more stable without changing the surrounding pipeline.

**Work items**
- Remove `eval` use when invoking Codex CLI.
  - Accept either a JSON array (preferred) or a restricted string format.
  - Build an args array and pass arguments without shell evaluation.
- Pin Codex CLI version (and optionally cache) to reduce upstream breakage.
- Establish the **agent-runner output contract** as a documented interface (even if only Codex implements it initially).

**Acceptance criteria**
- Codex runs succeed as before (keepalive/autofix/verifier modes).
- No `eval` remains in the execution path.
- The runner uses a pinned Codex version.

**Rollout**
- Safe to deploy broadly; no consumer template behavior change if only reusable runner changes.

---

### Phase 1 — Introduce an Agent Registry + resolver helper

**Objective:** Centralize agent definitions so workflows don’t embed Codex assumptions.

**Deliverables**
- New registry file, e.g. `.github/agents/registry.yml` (source of truth):
  - `agent_key` (codex, claude, gemini, …)
  - runner workflow (`reusable-codex-run.yml`, future `reusable-<agent>-run.yml`)
  - required secrets / environment requirements
  - branch scheme (prefix pattern)
  - mention policy (typically “do not post UI trigger mentions”)
  - capabilities/constraints (e.g., “supports PR keepalive”, “supports issue belt”, “supports autofix”)
- New JS helper under `.github/scripts/`:
  - `resolveAgentFromLabels(labels)`
  - `getAgentConfig(agentKey)`
  - `getRunnerWorkflow(agentKey)`

**Acceptance criteria**
- No existing workflows are required to change routing yet.
- Registry + helper has unit tests (add to existing JS test harness where appropriate).

**Rollout**
- Land registry + helper first, unused, to keep risk low.

---

### Phase 2 — Provider-agnostic entrypoints (keepalive + autofix + bot-comment)

**Objective:** Make PR-based automation multi-agent capable without touching the belt.

**Scope**
- Update these workflows to use the registry for routing:
  - `.github/workflows/agents-keepalive-loop.yml`
  - `.github/workflows/agents-autofix-loop.yml`
  - `.github/workflows/reusable-bot-comment-handler.yml`
- Mirror required changes in:
  - `templates/consumer-repo/.github/workflows/` equivalents
- Keep default agent = Codex unless a non-codex `agent:*` label is present.

**Implementation approach**
- Replace hard-coded `uses: .../reusable-codex-run.yml` with:
  - either a small set of conditional jobs (run-codex/run-claude/...) generated from registry keys,
  - or a new generic reusable runner workflow (`reusable-agent-run.yml`) that dispatches internally by `agent_key`.

**Acceptance criteria**
- For `agent:codex` PRs, behavior is unchanged.
- For any unknown agent label, workflows fail fast with a clear summary reason.
- Keepalive summary/state remains stable and compliant with Observability Contract.

**Rollout**
- Start with Workflows repo, then sync templates to a single reference consumer repo, then expand.

> **Audit status (Feb 18):**
> - ✅ `agents-keepalive-loop.yml` — has `run-codex` + `run-claude`, merged outputs
> - ✅ `agents-autofix-loop.yml` — has `autofix-codex` + `autofix-claude`, uses registry
> - ⚠️ `reusable-bot-comment-handler.yml` — checks `agent:claude`/`agent:codex` by
>   string comparison (lines 185, 191) instead of using `resolveAgentFromLabels()`
> - ❌ `reusable-16-agents.yml` — hardcodes `agent:codex` as default (lines 91, 527, 621)
> - ❌ `reusable-pr-context.yml` — missing `agent:claude`/`agent:auto` in label check (line 221)

---

### Phase 3 — Provider-agnostic issue→PR path (belt + issue-bridge + auto-pilot)

**Objective:** Remove hard-coded `codex/issue-*` assumptions while preserving backwards compatibility.

**Strategy (compatibility-first)**
- Create generic belt workflows parameterized by `agent_key`:
  - `agents-71-belt-dispatcher.yml`
  - `agents-72-belt-worker.yml`
  - `agents-73-belt-conveyor.yml`
- Keep existing Codex belt workflows as thin wrappers calling the generic versions with `agent_key=codex`.

**Required changes**
- Update branch naming logic in:
  - `.github/workflows/agents-auto-pilot.yml`
  - `.github/workflows/reusable-agents-issue-bridge.yml`
- Update any validation that assumes `codex/issue-` prefix.

**Acceptance criteria**
- Existing Codex belt continues to function with no user-facing behavior change.
- A second agent can run belt end-to-end when explicitly configured and secrets are present.

> **Audit status (Feb 18):**
> - ✅ Belt workflows (71/72/73) — accept `agent_key` input, use `getAgentConfig()`
> - ⚠️ `agents-auto-pilot.yml` — issue labeling uses `loadAgentRegistry()` (done),
>   but **PR creation path** still hardcodes `['agent:codex', ...]` at line 2373
> - ⚠️ `agents-auto-pilot.yml` — dispatches `agents-pr-meta-v4.yml` (line 2392)
>   which doesn't exist in any consumer repo (pre-existing bug, see audit above)
> - ❌ `agents-auto-label.yml` — guard only checks `agent:codex` (line 34)
> - ❌ `agents-70-orchestrator.yml` — hardcoded `bootstrap_issues_label: "agent:codex"` (line 74)
> - ❌ `agents-orchestrator.yml` (template) — hardcoded `bootstrap_issues_label: "agent:codex"` (line 78)

---

### Phase 4 — Verifier + follow-up chain becomes agent-aware

**Objective:** Follow-up issues/PRs should preserve the originating agent intent rather than defaulting to `agent:codex`.

**Scope**
- Update `.github/workflows/reusable-agents-verifier.yml` and follow-up creators to:
  - resolve agent from the source PR labels (or registry default),
  - apply `agent:<key>` label on follow-up issues,
  - optionally tag provenance (e.g. `from:<key>`), without hard-coding `from:codex`.

**Acceptance criteria**
- Follow-up creation uses the same agent key as the triggering PR unless overridden.

> **Audit status (Feb 18):**
> - ✅ `reusable-agents-verifier.yml` — uses `resolveAgentFromLabels()` with codex fallback
> - ⚠️ `agents-verify-to-issue-v2.yml` — uses resolver, but line 409 has user-facing
>   text hardcoding `agent:codex` as an example
> - ⚠️ `agents-verify-to-issue.yml` — line 186 has user-facing text: `agent:codex`
> - ✅ `agents-verify-to-new-pr.yml` — uses `resolveAgentFromLabels()` with codex fallback
> - ❌ `agents-64-verify-agent-assignment.yml` — entirely codex-specific
>   (checks for `agent:codex` label exclusively, lines 28/144/207/215/221/252)

---

### Phase 5 — Delegation / re-routing between agents (capacity + effectiveness)

**Objective:** Allow system-controlled delegation where one agent can hand off to another based on policy.

**Important principle**
- Delegation should be **system-driven**, not “agent self-assigns” from free-form output.

**Design**
- Introduce a routing mode (label or config), e.g. `agent:auto`:
  - keepalive evaluate step chooses the agent per round.
- Treat `agent:claude` as a first-class peer label alongside `agent:codex`.
- Define measurable signals for switching:
  - capacity (in-progress runs per agent)
  - effectiveness (recent rounds produce commits / checked tasks / Gate pass)
  - safety constraints (secrets present, correct environment)
- Encode the decision in:
  - run summaries and/or keepalive state marker fields (not PR comments).

**Acceptance criteria**
- With `agent:auto`, default remains Codex unless a switch is justified by policy.
- Switching agents is idempotent and doesn’t break keepalive run-cap rules.

---

### Phase 5A — Label + registry plumbing for `agent:auto` and `agent:claude`

**Objective:** Make the label surface area real and consistent across Workflows + consumer repos.

**Work items**
- Add labels (and sync them): `agent:auto`, `agent:claude`, `from:claude`.
- Update label-triggered workflows (notably capability check) to trigger on `agent:auto` and `agent:claude`, not just `agent:codex`.

**Acceptance criteria**
- `agent:auto` and `agent:claude` exist in Workflows, and `agent:auto`/`agent:claude` exist in consumer repos after label sync.

> **Audit status (Feb 18):**
> - ✅ `agents-capability-check.yml` — triggers on `["agent:codex","agent:claude","agent:auto"]`
> - ✅ Labels added via Phase 5A commit (Feb 17)
> - ❌ `agents-81-gate-followups.yml` — **completely missed by Phase 5A**.
>   Still has codex-only `run-codex` job (line 289: `if: agent_type == 'codex'`),
>   commented-out `run-claude` placeholder (line 318), hardcoded `CODEX_SUMMARY`
>   env var (line 486), and codex-only outputs in summary. This is the same
>   pattern keepalive-loop had before Phase 5A updated it, but gate-followups
>   was not updated.

---

### Phase 5B — Implement a Claude runner (`reusable-claude-run.yml`)

**Objective:** Provide a runner workflow for `agent:claude` that is safe by default and matches the core “agent runner” contract.

**Constraints**
- Must not introduce UI-triggering `@codex`/`@claude` mentions.
- Must be gated by explicit labels (`agent:claude` or `agent:auto` policy selection).

**Acceptance criteria**
- `agent:claude` can run at least one PR automation mode (start with keepalive) end-to-end in the Workflows repo when `CLAUDE_API_STRANSKE` is available.

> **Audit status (Feb 18):**
> - ✅ `reusable-claude-run.yml` exists and is referenced from keepalive-loop and autofix-loop

---

### Phase 5C — Enable registry-driven routing to Claude in PR automation

**Objective:** Actually run Claude when `agent:claude` is present.

**Work items**
- Keepalive: add a `run-claude` job alongside `run-codex`, using `getRunnerWorkflow()`.
- Autofix + bot-comment: route to Claude runner when labeled.

**Acceptance criteria**
- With `agent:claude`, the matching runner job runs.
- With `agent:auto`, the policy can select Claude only when safe.

> **Audit status (Feb 18):**
> - ✅ Keepalive-loop: `run-claude` job added, routes to `reusable-claude-run.yml`
> - ✅ Autofix-loop: `autofix-claude` job added, routes to `reusable-claude-run.yml`
> - ❌ Gate-followups: still codex-only (mirrors pre-5A keepalive structure)
> - ⚠️ Bot-comment-handler: checks labels by string but does route to Claude

---

### Phase 5D — Delegation policy (capacity + effectiveness)

**Objective:** Make `agent:auto` meaningful with a transparent, system-driven decision.

**Work items**
- Define a small policy function (first-pass heuristic) using only:
  - label intent (`agent:auto`)
  - available secrets
  - recent progress signals already captured by keepalive state
- Persist the chosen agent and reason in keepalive state.

**Acceptance criteria**
- `agent:auto` runs deterministically and records why it chose Codex vs Claude.

---

### Phase 6 — Remove or quarantine UI-trigger mentions (`@codex`)

**Objective:** Reduce risk of CLI/UI agent overlap and make provider-neutral routing easier.

**Work items**
- Eliminate `@codex start` posting from belt/bootstraps where CLI automation already exists.
- Keep compatibility via config flags where needed.

**Acceptance criteria**
- No automation path posts `@codex start` by default.

---

## Testing & Validation Strategy

- Unit tests:
  - JS: agent resolver + registry loader + routing decisions.
  - Existing keepalive tests should be extended to validate non-codex routing.
- Workflow validation:
  - `scripts/validate_workflow_yaml.py` for touched workflows and templates.
- Integration rehearsal (incremental):
  - Run keepalive/autofix e2e health workflows in the Workflows repo first.
  - Sync templates to a single consumer repo and validate before broad propagation.

## Sync Policy Checklist (must be revisited each phase)

If adding/modifying consumer-facing workflows, ensure:
- New files added to `.github/sync-manifest.yml` (when sync-able)
- Files copied/updated under `templates/consumer-repo/`
- Validation CI passes, including drift checks

## Remediation Plan (Feb 18, 2026)

The following work items address gaps found in the audit. They are grouped by
priority (P0 = actively broken, P1 = blocks agent:claude, P2 = cosmetic or
correctness-when-not-codex).

### P0: Actively broken

| # | File | Fix |
|---|------|-----|
| 1 | `agents-auto-pilot.yml` (template + Workflows) L2392 | Change `agents-pr-meta-v4.yml` → `agents-pr-meta.yml` |

### P1: Blocks `agent:claude` / `agent:auto` from working end-to-end

| # | File | Fix |
|---|------|-----|
| 2 | `agents-auto-pilot.yml` L2373 | Replace `['agent:codex', ...]` with `[\`agent:${agentKey}\`, ...]` (use existing `agentKey` from registry) |
| 3 | `agents-auto-pilot.yml` L2383 | Update status message to use `agentKey` |
| 4 | `agents-81-gate-followups.yml` (template) | Add `run-claude` job (mirror keepalive-loop Phase 5A pattern); merge outputs in post-work and summary |
| 5 | `agents-auto-label.yml` L34 (template L29) | Widen guard: `!contains(... 'agent:codex') && !contains(... 'agent:claude') && !contains(... 'agent:auto')` |
| 6 | `agents-70-orchestrator.yml` L74 | Parameterize `bootstrap_issues_label` or read from registry |
| 7 | `agents-orchestrator.yml` (template) L78 | Same as above |
| 8 | `reusable-16-agents.yml` L91/527/621 | Use registry resolver instead of hardcoded `agent:codex` default |
| 9 | `reusable-pr-context.yml` L221 | Add `agent:claude`, `agent:auto` to label check array |
| 10 | `agents-64-verify-agent-assignment.yml` | Generalize to check for any `agent:*` label, not just `agent:codex` |

### P2: Cosmetic / correctness in non-default agent scenarios

| # | File | Fix |
|---|------|-----|
| 11 | `agents-auto-pilot.yml` L345 | Rename `hasAgentCodex` → `hasAgentLabel` and check for any `agent:*` |
| 12 | `agents-auto-pilot.yml` L1532 | Update comment text |
| 13 | `agents-keepalive-loop.yml` L483-484, 490 | Update outdated comments ("Future: agent:claude" → already implemented) |
| 14 | `agents-81-gate-followups.yml` L280-281 | Same outdated comment |
| 15 | `agents-verify-to-issue.yml` L186 | Update user-facing text from `agent:codex` to `agent:*` |
| 16 | `agents-verify-to-issue-v2.yml` L409 | Same |
| 17 | `scripts/cleanup_labels.py` | Update `agent:codex` references |
| 18 | `scripts/keepalive-runner.js` | Update `agent:codex` references |
| 19 | `scripts/langchain/pr_verifier.py` | Update `agent:codex` references |

### Sync policy items

| # | Item | Action |
|---|------|--------|
| 20 | All template changes must be mirrored in `templates/consumer-repo/` | Verify after each fix |
| 21 | `.github/sync-manifest.yml` | Verify all modified files are in manifest |
| 22 | Trigger sync to consumer repos | `gh workflow run maint-68-sync-consumer-repos.yml` |
| 23 | Validate in reference consumer (Travel-Plan-Permission) | Smoke test after sync |

---

## Open Questions (to resolve before implementation)

1. **Second agent target:** which provider is next (Claude, Gemini, GitHub Models-based), and what auth/secrets model?
2. **Branch naming:** do we standardize on `agents/<agent>/issue-<n>` for non-codex, while keeping `codex/issue-<n>`?
3. **UI mentions policy:** can we eliminate `@codex start` entirely from belt activation and rely exclusively on CLI keepalive?
4. **Delegation thresholds:** what constitutes "ineffective" for switching (N failures, no commits, low alignment score)?
5. **Consumer `agent-config.yml`:** Should the sync create a default `.github/agent-config.yml` in consumer repos, or is the registry fallback to `codex` sufficient?
6. **`USE_CONSOLIDATED_WORKFLOWS` rollout:** When should consumer repos enable the event-hub and should the pr-meta-v4 dispatch check for it?

