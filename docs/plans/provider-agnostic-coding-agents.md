# Provider-Agnostic Coding Agents Plan (Phased, Codex-Safe)

**Status:** In progress (Phases 0–4 complete; Phase 5 kickoff complete)

## Progress (as implemented)

- ✅ Phase 0 — Runner hardening
- ✅ Phase 1 — Agent registry + resolver helper
- ✅ Phase 2 — Registry-driven PR automation routing (keepalive/autofix/bot-comment)
- ✅ Phase 3 — Registry-driven issue→PR path (belt + issue bridge + auto-pilot)
- ✅ Phase 4 — Verifier + follow-up chain is agent-aware
- 🟡 Phase 5 — Delegation / re-routing between agents (kickoff done: `agent:auto` label semantics)

## Claude availability (current reality)

- ✅ Claude *API* integration is already present (workflows pass `CLAUDE_API_STRANSKE` and install `langchain-anthropic`).
- ❌ There is currently no Claude runner workflow (e.g. `reusable-claude-run.yml`) in this repo, so `agent:claude` cannot yet run keepalive/autofix/bot-comment end-to-end.
- ✅ Plan below assumes we will wire `agent:claude` using API-based execution first (Codex-safe), then optionally introduce a dedicated Claude CLI later if desired.

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

## Current State (Snapshot)

### What’s already in good shape

- Keepalive prompt + task appendix is largely agent-agnostic.
- Keepalive evaluate step already extracts an `agent_type` from `agent:*` labels.
- `reusable-codex-run.yml` produces rich, structured outputs (message, exit code, change detection, task completion analysis).

### Where Codex coupling is concentrated

- Branch naming: hard-coded `codex/issue-<n>` appears in auto-pilot and issue-bridge logic.
- Labels: `agent:codex`, `from:codex`, and follow-up issue creation defaults.
- Routing: keepalive/autofix still call `reusable-codex-run.yml` directly.
- Mentions: some belt flows still post `@codex start` (risk of UI/CLI overlap).

### Security / operational risks worth addressing early

- `reusable-codex-run.yml` currently uses `eval` to run `codex_args`.
- Codex CLI is installed unpinned (`npm install -g @openai/codex`) each run.

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

---

### Phase 5B — Implement a Claude runner (`reusable-claude-run.yml`)

**Objective:** Provide a runner workflow for `agent:claude` that is safe by default and matches the core “agent runner” contract.

**Constraints**
- Must not introduce UI-triggering `@codex`/`@claude` mentions.
- Must be gated by explicit labels (`agent:claude` or `agent:auto` policy selection).

**Acceptance criteria**
- `agent:claude` can run at least one PR automation mode (start with keepalive) end-to-end in the Workflows repo when `CLAUDE_API_STRANSKE` is available.

---

### Phase 5C — Enable registry-driven routing to Claude in PR automation

**Objective:** Actually run Claude when `agent:claude` is present.

**Work items**
- Keepalive: add a `run-claude` job alongside `run-codex`, using `getRunnerWorkflow()`.
- Autofix + bot-comment: route to Claude runner when labeled.

**Acceptance criteria**
- With `agent:claude`, the matching runner job runs.
- With `agent:auto`, the policy can select Claude only when safe.

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

## Open Questions (to resolve before implementation)

1. **Second agent target:** which provider is next (Claude, Gemini, GitHub Models-based), and what auth/secrets model?
2. **Branch naming:** do we standardize on `agents/<agent>/issue-<n>` for non-codex, while keeping `codex/issue-<n>`?
3. **UI mentions policy:** can we eliminate `@codex start` entirely from belt activation and rely exclusively on CLI keepalive?
4. **Delegation thresholds:** what constitutes “ineffective” for switching (N failures, no commits, low alignment score)?

