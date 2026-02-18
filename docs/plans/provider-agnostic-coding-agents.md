# Provider-Agnostic Coding Agents Plan (Phased, Codex-Safe)

**Status:** In progress — P0/P1/P2 + Phase 3 + backing scripts refactoring complete (Feb 18); remaining: API contracts are documented and preserved, prompt directory path `.github/codex/prompts/` intentionally unchanged

## Progress (as implemented)

- ✅ Phase 0 — Runner hardening
- ✅ Phase 1 — Agent registry + resolver helper
- ✅ Phase 2 — Registry-driven PR automation routing (keepalive/autofix done; bot-comment uses registry; `reusable-16-agents`/`reusable-pr-context` widened)
- ✅ Phase 3 — Registry-driven issue→PR path (belt 71/72/73 refactored; auto-pilot/auto-label/orchestrators fixed; issue bridge assignees use registry; `agents_belt_scan.js` generalized; all backing scripts use registry-driven defaults; **API contracts preserved**)
- ✅ Phase 4 — Verifier + follow-up chain (verifier/verify-to-issue/verify-to-new-pr all use registry-driven defaults; verify-assignment generalized; **Codex CLI runner section intentionally unchanged**)
- ✅ Phase 5A/5B/5C — Dual-runner routing complete; `reusable-claude-run.yml` now fully compliant with runner output contract; bot-comment-handler default registry-driven; all consumer workflows have `run-claude`/`autofix-claude`
- 🟡 Phase 5D — Delegation policy (`agent:auto` heuristic not yet implemented)

### Scripts refactored (Feb 18, session 2)
All `.github/scripts/` and `scripts/` modules now use registry-driven agent defaults
instead of hardcoded `'codex'` fallbacks. API contracts (HTML markers, dispatch event
types, prompt file paths, bot logins) are preserved with explanatory comments.

Scripts updated:
- `agents_pr_meta_keepalive.js` — registry default, `agent-activation-marker` detection
- `keepalive_contract.js` — registry default for `ensureAgentPreface()`
- `keepalive_instruction_template.js` — registry default for mention
- `keepalive_loop.js` — registry default, error type `'agent'` (was `'codex'`), generic display text
- `keepalive_post_work.js` — registry default for alias + dispatch
- `keepalive_worker_gate.js` — API contract comment on marker
- `keepalive_orchestrator_gate_runner.js` — registry default
- `agents_pr_meta_orchestrator.js` — registry default, JSDoc update
- `agents_pr_meta_update_body.js` — API contract comments on bot logins + marker
- `merge_manager.js` — `from:claude`, `from:auto` recognition
- `post_completion_comment.js` — JSDoc update, API contract comments
- `scripts/keepalive-runner.js` — registry defaults, agent-agnostic display text, widened agent triggers

Tests updated:
- `agents-belt-scan.test.js` — added `isAgentBeltBranch` + `identifyReadyBeltPRs` tests
- `keepalive-loop.test.js` — updated error type assertion `'codex'` → `'agent'`

> **Feb 18 2026 audit note:** An independent audit of every workflow in both
> `.github/workflows/` and `templates/consumer-repo/` found that Phases 2–4
> were marked "complete" prematurely. Significant hardcoded `agent:codex`
> references remain. See **§ Audit: Remaining Hardcoded References** below.

## Claude availability (current reality)

- ✅ Claude *API* integration is already present (workflows pass `CLAUDE_API_STRANSKE` and install `langchain-anthropic`).
- ✅ `reusable-claude-run.yml` now exists and is called from keepalive-loop and autofix-loop.
- ✅ Phase 5A added `run-claude` jobs to keepalive-loop and autofix-loop templates.
- ⚠️ `run-claude` jobs require a configured `CLAUDE_AUTH_JSON` runner secret; this is **distinct** from `CLAUDE_API_STRANSKE` (used for LLM analysis in other workflows) and is required for end-to-end `agent:claude` runs.

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

**Methodology:** Every `agents-*.yml`, `reusable-*.yml`, and consumer template
was searched for all Codex coupling patterns: `agent:codex`, `from:codex`,
`codex/issue-`, `@codex`, `CODEX_AUTH_JSON`, `CODEX_SUMMARY`, `CODEX_HOME`,
`codex_`, `post_codex_comment`, `chatgpt-codex-connector`, `codex-keepalive-marker`,
and the literal word `codex` in descriptive text, variable names, job names,
and comments. Every match was reviewed in context.

The coupling falls into several categories:

1. **Label references** (`agent:codex`, `from:codex`) — blocking agent-agnostic routing
2. **Branch prefix assumptions** (`codex/issue-`) — blocking non-codex belt runs
3. **UI trigger mentions** (`@codex start`) — risk of CLI/UI overlap (Phase 6 scope)
4. **Auth/secret assumptions** (`CODEX_AUTH_JSON`) — Codex-specific but intentional per-agent
5. **Assignee assumptions** (`chatgpt-codex-connector`) — Codex-specific bot users
6. **Prompt path assumptions** (`.github/codex/prompts/`) — directory name is codex-specific
7. **Cosmetic/comment text** — misleading but not functionally blocking

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

| File | Line(s) | Category | Issue |
|------|---------|----------|-------|
| `reusable-bot-comment-handler.yml` | 171 | label | `let agent = 'codex'; // default` — hardcoded fallback |
| `reusable-bot-comment-handler.yml` | 185, 191 | label | `labelSet.has('agent:claude')` / `labelSet.has('agent:codex')` — should use registry resolver |
| `reusable-bot-comment-handler.yml` | 327, 525, 530 | assignee | Hardcoded `chatgpt-codex-connector` assignee array; `agentAssignees` map only has codex/claude |
| `reusable-bot-comment-handler.yml` | 403–435 | prompt path | Writes dynamic prompt to `.github/codex/prompts/` — codex-specific directory |
| `reusable-16-agents.yml` | 12, 14 | input default | `'copilot,codex'` default agent list |
| `reusable-16-agents.yml` | 29–39 | input | `codex_user`, `codex_command_phrase` inputs |
| `reusable-16-agents.yml` | 79, 84, 89, 91 | input + label | `bootstrap_issues_label` defaults to `agent:codex` |
| `reusable-16-agents.yml` | 234, 244 | routing | Hardcoded agent→bot-user map (`codex: ['chatgpt-codex-connector']`) |
| `reusable-16-agents.yml` | 343–469 | entire job | "Codex Preflight" job — entirely Codex-specific |
| `reusable-16-agents.yml` | 527, 543, 563 | label | `agent:codex` in table headers and log output |
| `reusable-16-agents.yml` | 581–810 | entire job | "Bootstrap Codex PRs" job — hardcoded `agent:codex` fallback label |
| `reusable-16-agents.yml` | 829–960 | entire job | "Codex Keepalive Sweep" job — codex-specific |
| `reusable-pr-context.yml` | 221 | label | `pr.hasAnyLabel(['agent:codex', 'agent:copilot', 'agents:keepalive'])` — missing `agent:claude`, `agent:auto` |

`reusable-16-agents.yml` is heavily Codex-specific throughout (preflight,
bootstrap, keepalive sweep jobs). Making it fully agnostic is a larger effort
than the original Phase 2 scope anticipated.

### Phase 3 gaps (issue→PR path)

| File | Line(s) | Category | Issue |
|------|---------|----------|-------|
| **`agents-auto-pilot.yml`** | 345 | label | `hasAgentCodex = labels.includes('agent:codex')` — used for early-exit check |
| **`agents-auto-pilot.yml`** | 1532 | comment | `needs-human instead of agent:codex` |
| **`agents-auto-pilot.yml`** | 1971 | branch | `let branchPrefix = 'codex/issue-'` — hardcoded (should read from registry) |
| **`agents-auto-pilot.yml`** | 2213, 2225 | text | "Codex belt worker" / "Codex session logs" in user-facing messages |
| **`agents-auto-pilot.yml`** | 2276, 2279, 2287, 2296 | text | "codex belt worker" dispatch messages |
| **`agents-auto-pilot.yml`** | 2373 | label | PR creation hardcodes `labels: ['agent:codex', 'agents:keepalive', 'autofix']` |
| **`agents-auto-pilot.yml`** | 2383 | text | Status message hardcodes `` `agent:codex` `` |
| **`agents-auto-pilot.yml`** | 2392 | dispatch | `agents-pr-meta-v4.yml` (see pre-existing bug above) |
| **`agents-auto-label.yml`** | 34 (template 29) | label | Guard: `!contains(..., 'agent:codex')` — should check all `agent:*` labels |
| **`agents-70-orchestrator.yml`** | 21, 131–132 | input/output | `codex_user`, `codex_command_phrase` outputs |
| **`agents-70-orchestrator.yml`** | 74 | label | `bootstrap_issues_label: "agent:codex"` |
| **`agents-orchestrator.yml`** (template) | 5, 33 | comment | "Codex continues work", "Codex bootstrap" |
| **`agents-orchestrator.yml`** (template) | 65 | input | `readiness_agents: "copilot,codex"` |
| **`agents-orchestrator.yml`** (template) | 78 | label | `bootstrap_issues_label: "agent:codex"` |
| `reusable-70-orchestrator-init.yml` | 22, 60–63, 458–459 | input/output | `codex_user`, `codex_command_phrase` throughout |
| `reusable-70-orchestrator-main.yml` | 25, 28, 208, 499, 615 | routing | `agentAlias` defaults to `'codex'` throughout |
| `reusable-70-orchestrator-main.yml` | 840, 1209 | marker | `codex-keepalive-marker` regex — used by pr-meta too |
| `reusable-70-orchestrator-main.yml` | 1179–1182, 1273, 1291–1292 | routing | Agent alias fallback to `codex`, passes `codex_user` |
| `reusable-70-orchestrator-main.yml` | 1355–1442 | jobs | "Codex Belt Dispatcher" / "Guard existing Codex PRs" / "Codex Belt Worker" — job names codex-specific |
| `reusable-70-orchestrator-main.yml` | 1930, 1932, 2604, 2621 | dispatch | `codex-pr-comment-command` event type, `chatgpt-codex-connector` assignees |
| `reusable-70-orchestrator-main.yml` | 2771–3241 | jobs | "Summarise Codex dispatch outcomes", "Scan Codex promotion queue", "Promote Codex PRs" — all codex-named |
| `reusable-agents-issue-bridge.yml` | 319 | branch | `let branchPrefix = 'codex/issue-'` — should read from registry `getAgentConfig()` |
| `reusable-agents-issue-bridge.yml` | 1167 | assignee | Hardcoded `['chatgpt-codex-connector', 'stranske-automation-bot']` |
| `reusable-agents-issue-bridge.yml` | 1633 | variable | `codexPromptMsg` variable name |

The belt workflows (71/72/73) were updated to accept `agent_key` but the
orchestrator infrastructure that calls them still hardcodes codex assumptions.
The `reusable-70-orchestrator-main.yml` is the second-largest gap after
gate-followups — it has ~100 codex references across job names, routing,
dispatch events, and assignee lists.

### Phase 3 gaps: Belt workflows (71/72/73) — deeper coupling

While the belt workflows accept `agent_key`, they still have substantial
internal codex coupling:

| File | Line(s) | Category | Issue |
|------|---------|----------|-------|
| `agents-71-codex-belt-dispatcher.yml` | 1–3, 78 | naming | Workflow name/job name: "Codex Belt Dispatcher", "Select next Codex issue" |
| `agents-71-codex-belt-dispatcher.yml` | 286 | branch | `let branchPrefix = 'codex/issue-'` — fallback before registry check |
| `agents-71-codex-belt-dispatcher.yml` | 316 | step name | "Create codex branch if missing" |
| `agents-71-codex-belt-dispatcher.yml` | 368 | text | "Codex belt dispatcher queued this issue" |
| `agents-72-codex-belt-worker.yml` | 1–3, 99 | naming | Workflow/job names all say "Codex" |
| `agents-72-codex-belt-worker.yml` | 1018 | commit msg | `chore(codex): initialize belt run` |
| `agents-72-codex-belt-worker.yml` | 1070–1126 | text | "Open or refresh Codex PR", PR title `Codex belt for #N` |
| `agents-72-codex-belt-worker.yml` | 1218–1219 | assignee | `agentKey === 'codex' ? ['chatgpt-codex-connector', ...]` |
| `agents-72-codex-belt-worker.yml` | 1249–1267 | UI trigger | `<!-- codex-activation-marker -->` and `@codex start` posting |
| `agents-72-codex-belt-worker.yml` | 1251–1252, 1292, 1301, 1321 | text | "Codex Worker activated", "Codex activation comment" |
| `agents-73-codex-belt-conveyor.yml` | 1–3, 69 | naming | Workflow/job names all say "Codex" |
| `agents-73-codex-belt-conveyor.yml` | 74 | routing | `(needs.normalize.outputs.agent_key || 'codex') == 'codex'` guard |
| `agents-73-codex-belt-conveyor.yml` | 304 | branch | `let branchPrefix = 'codex/issue-'` — fallback before registry check |
| `agents-73-codex-belt-conveyor.yml` | 386–387 | path | `agents/codex-<n>.md` regex for bootstrap detection |
| `agents-73-codex-belt-conveyor.yml` | 416, 426 | text | "bootstrap for codex", "bootstrap-only Codex PR" |

### Phase 4 gaps (verifier + follow-up)

| File | Line(s) | Category | Issue |
|------|---------|----------|-------|
| `reusable-agents-verifier.yml` | 6, 48–50 | comment/input | "Runs Codex in verifier mode", `CODEX_AUTH_JSON` input |
| `reusable-agents-verifier.yml` | 310, 333, 336 | label | Falls back to `agentKey = 'codex'` (acceptable) |
| `reusable-agents-verifier.yml` | 352–428 | entire section | Codex CLI install, auth setup, `codex exec` invocation — verifier is Codex-only |
| `reusable-agents-verifier.yml` | 993–994 | label | Hardcodes `'agent:codex'` and `'from:codex'` as fallback labels |
| `agents-verify-to-issue-v2.yml` | 341, 352, 354 | label | Falls back to `agentKey = 'codex'` (acceptable) |
| `agents-verify-to-issue-v2.yml` | 409 | text | `agent:codex` in user-facing instruction |
| `agents-verify-to-issue.yml` | 186 | text | `agent:codex` in user-facing instruction |
| `agents-verify-to-new-pr.yml` | 741, 753, 755 | label | Falls back to `agentKey = 'codex'` (acceptable) |
| `agents-64-verify-agent-assignment.yml` | 28, 144, 207, 215, 221, 252 | label | Entire workflow checks only `agent:codex` |

The verifier itself (`reusable-agents-verifier.yml`) runs `codex exec` directly
(lines 352–428). Making it agent-agnostic would require either calling
`reusable-codex-run.yml`/`reusable-claude-run.yml` dynamically or adding a
Claude verification path.

### Phase 5A gaps (labels + capability check)

| File | Line(s) | Category | Issue |
|------|---------|----------|-------|
| `agents-capability-check.yml` | 25 | — | **Done** — triggers on `["agent:codex","agent:claude","agent:auto"]` |
| `agents-keepalive-loop.yml` | 317 | prompt path | `.github/codex/prompts/keepalive_next_task.md` fallback — directory is codex-named |
| `agents-keepalive-loop.yml` | 403–417 | auth | `HAS_CODEX_AUTH` / `CODEX_AUTH_JSON` check — intentional per-agent but comment misleading |
| `agents-keepalive-loop.yml` | 483–490 | comment | Outdated: "Currently supports: agent:codex" / "Future: agent:claude" — run-claude now exists |

### Consumer template: `agents-81-gate-followups.yml`

**✅ Fixed.** Previously the largest gap; now has dual-runner support matching keepalive-loop.

| Item | Status | Notes |
|------|--------|-------|
| Keepalive routing | ✅ | `run-codex` + `run-claude` jobs with agent_type routing |
| Summary merging | ✅ | Uses `AGENT_SUMMARY`, merges outputs from both runners |
| Preflight auth | ✅ | Checks `CODEX_AUTH_JSON`, `CLAUDE_AUTH_JSON`, and APP secrets |
| Autofix routing | ✅ | `autofix` (codex) + `autofix-claude` jobs with agent_type condition |
| Prepare agent resolution | ✅ | Uses `resolveAgentFromLabels()` with registry |
| Metrics merging | ✅ | `metrics` job needs both autofix jobs, merges results |
| Prompt path | ⚠️ | `.github/codex/prompts/` — intentionally codex-branded directory (shared) |

### Consumer template: `agents-issue-intake.yml`

| Line(s) | Category | Issue |
|---------|----------|-------|
| 42, 45 | input default | `bridge_agent` defaults to `"codex"` |
| 46 | input | `post_codex_comment` — codex-specific input name |
| 130 | routing | `let agent = ... || 'codex'` fallback |
| 145 | label | `agent:codex, agents:codex` pattern matching |
| 188–193 | routing | Skips `post_agent_comment` specifically for codex to avoid CLI/UI conflict |

### Workflows-internal files not synced to consumers

| File | Line(s) | Category | Issue |
|------|---------|----------|-------|
| `agents-63-issue-intake.yml` | 41–52 | input | `post_codex_comment`, `open_as_draft` described as "Codex" params |
| `agents-63-issue-intake.yml` | 129, 1178, 1463 | label | `agent:codex` in guard labels |
| `agents-63-issue-intake.yml` | 155, 179–258 | routing | `post_codex_comment` normalization logic |
| `agents-63-issue-intake.yml` | 1342 | job name | "Validate Codex issue labels" |
| `agents-63-issue-intake.yml` | 1380 | routing | `defaultAgent = ... || 'codex'` |
| `agents-63-issue-intake.yml` | 1735 | branch | `codex-issue-${{` branch name template |
| `agents-63-issue-intake.yml` | 1755 | routing | `post_codex_comment` passed to bridge |
| `agents-64-verify-agent-assignment.yml` | all | label | Entire workflow checks only for `agent:codex` |
| `agents-keepalive-dispatch-handler.yml` | 6, 129, 187 | event type | `codex-pr-comment-command` dispatch event; `AGENT_ALIAS` defaults to `codex` |
| `agents-keepalive-loop-reporter.yml` | 100 | routing | `agent_type: state.agent_type || 'codex'` |
| `agents-moderate-connector.yml` | 70, 178–181 | assignee/text | `chatgpt-codex-connector[bot]`; regex patterns matching "use codex" / "sign up for codex" |

### Auth and prompt path coupling (intentional but noted)

These are legitimately Codex-specific (they configure the Codex runner) and
are not expected to be made generic. They're listed for completeness:

| File | Category | Notes |
|------|----------|-------|
| `reusable-codex-run.yml` | all | Entire workflow is the Codex runner — intentionally codex-specific |
| `reusable-agents-verifier.yml` L352–428 | auth+exec | Installs Codex CLI, runs `codex exec` — would need a `reusable-claude-verifier` equivalent |
| `health-codex-auth-check.yml` | all | Checks Codex auth token expiry — intentionally codex-specific |
| `health-keepalive-e2e.yml` | all | E2E test including optional Codex ping — intentionally codex-specific |
| `.github/codex/prompts/` directory | path | Directory name is codex-branded; prompts are used by both agents |

### `.github/scripts/` — JS modules used by workflows

| File | Codex refs | Category | Notes |
|------|-----------|----------|-------|
| `agent_registry.js` | 0 | — | Clean |
| `agent_delegation_policy.js` | 3 | fallback | `'codex'` default in policy; comment text. Acceptable — policy is agent-aware by design. |
| `agents_belt_scan.js` | ~10 | branch + naming | `isCodexBranch()`, `codex/issue-` regex, `identifyReadyCodexPRs` — should be parameterized by agent |
| `agents_orchestrator_resolve.js` | ~15 | defaults + naming | `'copilot,codex'` defaults, `codex_user`/`codex_command_phrase`, `bootstrap_issues_label: 'agent:codex'` |
| `agents_pr_meta_keepalive.js` | ~20 | markers + mentions | `codex-keepalive-marker/round/trace`, `@codex` activation detection, `chatgpt-codex-connector` |
| `agents_pr_meta_orchestrator.js` | 3 | dispatch | `codex-pr-comment-command` event type, agent alias default `'codex'` |
| `agents_pr_meta_update_body.js` | 2 | marker + assignee | `codex-completion-checkpoint`, `chatgpt-codex-connector[bot]` |
| `keepalive_contract.js` | 4 | markers | `codex-keepalive-marker/round/trace` HTML comment markers; agent alias default `'codex'` |
| `keepalive_gate.js` | 3 | marker + assignee | `chatgpt-codex-connector`, `agents-72-codex-belt-worker.yml`, `@codex` detection |
| `keepalive_instruction_template.js` | 5 | prompt path | `.github/codex/prompts/` paths; `getKeepaliveInstructionWithMention('codex')` |
| `keepalive_loop.js` | ~25 | prompt paths + fallbacks | `.github/codex/prompts/*.md`; `codex-session` artifact patterns; backwards-compat `codex_exit_code` aliases; `agent_type` default `'codex'` |
| `keepalive_orchestrator_gate_runner.js` | 2 | fallback | `primaryAgent \|\| 'codex'`, `agents-72-codex-belt-worker.yml` |
| `keepalive_post_work.js` | 6 | dispatch + fallback | `codex-pr-comment-command` event type, agent alias default `'codex'` |
| `keepalive_worker_gate.js` | 1 | marker | `codex-keepalive-marker` default |
| `merge_manager.js` | 1 | label | `fromAlt \|\| 'from:codex'` |
| `post_completion_comment.js` | 5 | marker + naming | `codex-completion-checkpoint` marker, "Codex Completion Checkpoint" heading, `codex-prompt.md` file paths |

> Scripts not listed above (`agents-guard.js`, `agents_dispatch_summary.js`,
> `agents_verifier_context.js`, `autopilot_metrics.js`, `bot-comment-handler.js`,
> `bot-comment-dismiss.js`, `keepalive_guard_utils.js`, `keepalive_prompt_composer.js`,
> `keepalive_prompt_routing.js`, `keepalive_review_guard.js`, `keepalive_state.js`,
> `conflict_detector.js`) have **zero** codex references — already clean.

> The `keepalive_loop.js` backwards-compat aliases (`codex_exit_code` → `agent_exit_code` etc.)
> at lines 2343–2347 are intentional shims for older callers and should be kept until
> all consumers are synced.

### `scripts/` — top-level scripts

| File | Codex refs | Notes |
|------|-----------|-------|
| `cleanup_labels.py` | 4 | `agent:codex`, `from:codex`, `codex-ready`, `codex` in label lists — should add `agent:claude`, `from:claude` equivalents |
| `keepalive-runner.js` | ~30 | Heavily coupled: `chatgpt-codex-connector`, `@codex` pattern, `codex-pr-comment-command` dispatch, `agent:codex` default, `codex-keepalive-marker`, "Codex Keepalive" heading, "Codex has not commented yet" messages |
| `langchain/pr_verifier.py` | 1 | `issue_labels = args.issue_label or ["agent:codex"]` — should use registry or accept any `agent:*` |
| `analyze_codex_session.py` | (name) | Codex-specific by design — acceptable |

### Tests that will need updates

Test files mirror the assumptions of their source. When fixing source scripts/workflows,
these test files must also be updated:

| Test file | Depends on |
|-----------|------------|
| `.github/scripts/__tests__/agents-belt-scan.test.js` | `isCodexBranch()` function name + `codex/issue-` pattern |
| `.github/scripts/__tests__/keepalive-contract.test.js` | `codex-keepalive-marker/round/trace` patterns |
| `.github/scripts/__tests__/keepalive-loop.test.js` | `.github/codex/prompts/` paths, summary output format |
| `.github/scripts/__tests__/agent-registry.test.js` | Registry defaults (already clean) |
| `.github/scripts/__tests__/agent-delegation-policy.test.js` | Policy defaults (already agent-aware) |
| `tests/keepalive-runner.test.js` | `@codex` activation, `codex-pr-comment-command`, `agent:codex` label |
| `tests/workflows/test_codex_belt_pipeline.py` | Belt workflow names, branch patterns |
| `tests/tools/test_codex_jsonl_parser.py` | Codex-specific by design — acceptable |
| `tests/tools/test_codex_log_analyzer.py` | Codex-specific by design — acceptable |
| `tests/tools/test_codex_session_analyzer.py` | Codex-specific by design — acceptable |

### Consumer repo state (all four repos, Feb 18 2026)

| Item | Counter_Risk | Portable-Alpha | Trend_Model_Project | Travel-Plan-Permission |
|------|---|---|---|---|
| `agents-pr-meta-v4.yml` | **Missing** | **Missing** | **Missing** | **Missing** |
| `agents-pr-meta.yml` | Present | Present | Present | Present |
| `agents-80-pr-event-hub.yml` | Missing | Present | Present | ? |
| `agent_registry.js` | Present | Present | Present | Present |
| `agent_delegation_policy.js` | Present | Present | Present | Present |
| `.github/agents/registry.yml` | **Missing** | **Missing** | **Missing** | **Missing** |
| `USE_CONSOLIDATED_WORKFLOWS` var | **Not set** | Not set | Not set | Not set |

> No consumer repo has `.github/agents/registry.yml`, so `loadAgentRegistry()`
> always falls back to `default_agent: 'codex'`. However, label-based routing
> still works: PRs with `agent:claude` labels will resolve to Claude via
> `resolveAgentFromLabels()` regardless of whether a registry file exists.
> The registry file is only needed to change the *default* agent (when no
> explicit `agent:*` label is present).

---

## Current State (Snapshot)

### What's in good shape (post-Phase 5A)

- Keepalive prompt + task appendix is agent-agnostic.
- Keepalive evaluate step extracts `agent_type` from `agent:*` labels.
- Both `reusable-codex-run.yml` and `reusable-claude-run.yml` conform to the runner output contract (including `error-category`, `error-type`, `error-recovery`).
- Keepalive-loop has both `run-codex` and `run-claude` jobs with merged outputs.
- Autofix-loop has both `autofix-codex` and `autofix-claude` jobs.
- Capability check triggers on `agent:codex`, `agent:claude`, and `agent:auto`.
- Auto-pilot issue labeling uses `loadAgentRegistry()` for dynamic agent selection.
- Belt workflows (71/72/73) accept `agent_key` parameter and are largely agent-agnostic.
- Verifier and follow-up workflows use `resolveAgentFromLabels()`.

### Where Codex coupling remains (work needed)

- **Auto-pilot PR creation path:** Hardcodes `['agent:codex', ...]` labels on PR creation (line 2373) — Phase 3 gap.
- **Auto-pilot PR meta dispatch:** Dispatches `agents-pr-meta-v4.yml` which doesn't exist in consumers — pre-existing bug.
- ~~**Gate-followups:** Entire workflow still codex-only~~ — **Fixed**: now has `run-claude`, `autofix-claude`, registry-driven agent resolution, widened auth check.
- **Auto-label:** Guard condition only checks `agent:codex` — Phase 3 gap.
- **Both orchestrators:** Hardcode `bootstrap_issues_label: "agent:codex"` — Phase 3 gap.
- **reusable-16-agents:** Hardcodes `agent:codex` as default label — Phase 2 gap.
- **reusable-pr-context:** Missing `agent:claude`/`agent:auto` in label check — Phase 5A gap.
- ~~**agents-64-verify-agent-assignment:** Entirely codex-specific~~ — **Fixed** (Phase 4).
- ~~**Outdated comments** in keepalive-loop and gate-followups~~ — **Fixed**: comments updated, auth messages agent-agnostic.

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
> - ⚠️ Belt workflows (71/72/73) — accept `agent_key` input, use `getAgentConfig()`,
>   but still have ~30 internal codex refs: workflow/job names, branch prefix fallbacks,
>   `@codex start` posting (72 L1267), commit msg `chore(codex):`, assignee logic,
>   `codex-activation-marker`, bootstrap regex `agents/codex-<n>.md`
> - ⚠️ `agents-auto-pilot.yml` — issue labeling uses `loadAgentRegistry()` (done),
>   but **PR creation path** still hardcodes `['agent:codex', ...]` at line 2373;
>   branch prefix hardcoded `codex/issue-` at L1971; dispatches `agents-pr-meta-v4.yml`
> - ❌ `agents-auto-label.yml` — guard only checks `agent:codex` (line 34)
> - ❌ `agents-70-orchestrator.yml` — `bootstrap_issues_label: "agent:codex"` (L74),
>   `codex_user`/`codex_command_phrase` outputs (L131–132)
> - ❌ `agents-orchestrator.yml` (template) — `bootstrap_issues_label: "agent:codex"` (L78),
>   `readiness_agents: "copilot,codex"` (L65)
> - ❌ `reusable-70-orchestrator-main.yml` — ~100 codex refs: job names, `codex-pr-comment-command`
>   dispatch event, `codex-keepalive-marker` regex, `chatgpt-codex-connector` assignees,
>   `codex_user`/`codex_command_phrase` inputs, "Codex belt worker" naming throughout
> - ❌ `reusable-70-orchestrator-init.yml` — `codex_user`/`codex_command_phrase` inputs/outputs
> - ❌ `reusable-agents-issue-bridge.yml` — `codex/issue-` branch prefix (L319),
>   `chatgpt-codex-connector` assignees (L1167), `codexPromptMsg` (L1633)
> - ❌ Scripts backing Phase 3: `agents_belt_scan.js` (~10 refs),
>   `agents_orchestrator_resolve.js` (~15 refs), `agents_pr_meta_keepalive.js` (~20 refs),
>   `agents_pr_meta_orchestrator.js` (3 refs), `keepalive_gate.js` (3 refs),
>   `keepalive_post_work.js` (6 refs), `keepalive_instruction_template.js` (5 refs)

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
> - ✅ `agents-81-gate-followups.yml` — now has `run-claude` job, dual-output
>   merging in summary, `AGENT_SUMMARY` env var, `autofix-claude` job, and
>   registry-driven agent resolution in prepare step. Preflight auth check
>   widened to accept `CLAUDE_AUTH_JSON`.

---

### Phase 5B — Implement a Claude runner (`reusable-claude-run.yml`)

**Objective:** Provide a runner workflow for `agent:claude` that is safe by default and matches the core “agent runner” contract.

**Constraints**
- Must not introduce UI-triggering `@codex`/`@claude` mentions.
- Must be gated by explicit labels (`agent:claude` or `agent:auto` policy selection).

**Acceptance criteria**
- `agent:claude` can run at least one PR automation mode (start with keepalive) end-to-end in the Workflows repo when `CLAUDE_API_STRANSKE` is available.

> **Audit status (Feb 18):**
> - ✅ `reusable-claude-run.yml` exists and is referenced from keepalive-loop, autofix-loop, and gate-followups
> - ✅ Now fully compliant with runner output contract: `error-category`, `error-type`, `error-recovery` added via `error_classifier.js`

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
> - ✅ Keepalive-loop: `run-claude` job added, routes to `reusable-claude-run.yml`; preflight auth check widened
> - ✅ Autofix-loop: `autofix-claude` job added, routes to `reusable-claude-run.yml`
> - ✅ Gate-followups: `run-claude` + `autofix-claude` jobs added; prepare step resolves `agent_type` via registry; metrics merges both autofix results
> - ✅ Bot-comment-handler: uses `resolveAgentFromLabels()` primary with string-comparison fallback; default agent now registry-driven via `loadAgentRegistry()`

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

| # | File | Fix | Status |
|---|------|-----|--------|
| 1 | `agents-auto-pilot.yml` (template + Workflows) L2392 | Change `agents-pr-meta-v4.yml` → `agents-pr-meta.yml` | ✅ Done |

### P1: Blocks `agent:claude` / `agent:auto` from working end-to-end

| # | File | Fix | Status |
|---|------|-----|--------|
| 2 | `agents-auto-pilot.yml` L2373 | Replace `['agent:codex', ...]` with `` [`agent:${agentKey}`, ...] `` | ✅ Done |
| 3 | `agents-auto-pilot.yml` L2383 | Update status message to use `agentKey` | ✅ Done |
| 4 | `agents-81-gate-followups.yml` (template) | Add `run-claude` job; merge outputs in reconcile + summary | ✅ Done |
| 5 | `agents-auto-label.yml` L34 (template L29) | Widen guard to include `agent:claude`, `agent:auto` | ✅ Done |
| 6 | `agents-70-orchestrator.yml` / `agents_orchestrator_resolve.js` | Read `bootstrap_issues_label` default from registry | ✅ Done |
| 7 | `agents-orchestrator.yml` (template) L78 | Updated description text | ✅ Done |
| 8 | `reusable-16-agents.yml` L621 | Bootstrap fallback reads from registry | ✅ Done |
| 9 | `reusable-pr-context.yml` L221 | Add `agent:claude`, `agent:auto` to label check | ✅ Done |
| 10 | `agents-64-verify-agent-assignment.yml` | Generalize to check any `agent:*` label | ✅ Done |

### P2: Cosmetic / correctness in non-default agent scenarios

| # | File | Fix | Status |
|---|------|-----|--------|
| 11 | `agents-auto-pilot.yml` L345 | `hasAgentCodex` → `hasAgentLabel` with `agent:*` check | ✅ Done |
| 12 | `agents-auto-pilot.yml` L1532 | Comment text updated | ✅ Done |
| 13 | `agents-keepalive-loop.yml` comment | Updated "Future: agent:claude" → "Supports" | ✅ Done |
| 14 | `agents-81-gate-followups.yml` comment | Same | ✅ Done |
| 15 | `agents-verify-to-issue.yml` L186 | Already says `agent:*` (no change needed) | ✅ N/A |
| 16 | `agents-verify-to-issue-v2.yml` L409 | Already says `agent:*` (no change needed) | ✅ N/A |
| 17 | `scripts/cleanup_labels.py` | Added `agent:auto`, `from:claude` to FUNCTIONAL_LABELS | ✅ Done |
| 18 | `scripts/keepalive-runner.js` | Deferred — large script, needs dedicated pass | ⏳ Deferred |
| 19 | `scripts/langchain/pr_verifier.py` | Added comment about `--issue-label` override | ✅ Done |
| — | `agents-auto-pilot.yml` L2213-2296 | User-facing text: "Codex belt worker" → "belt worker" | ✅ Done |
| — | `agents-81-gate-followups.yml` L776 | `labels.includes('agent:codex')` → `.some(l => l.startsWith('agent:'))` | ✅ Done |
| — | `agents-81-gate-followups.yml` L784-809 | "Escalate to Codex CLI" → "agent CLI" | ✅ Done |

### Sync policy items

| # | Item | Action | Status |
|---|------|--------|--------|
| 20 | Template changes mirrored in `templates/consumer-repo/` | All edits applied to both | ✅ Done |
| 21 | `.github/sync-manifest.yml` | Verify modified files are in manifest | ⏳ Pending |
| 22 | Trigger sync to consumer repos | `gh workflow run maint-68-sync-consumer-repos.yml` | ⏳ Pending |
| 23 | Validate in reference consumer (Travel-Plan-Permission) | Smoke test after sync | ⏳ Pending |

---

## Open Questions (to resolve before implementation)

1. **Second agent target:** which provider is next (Claude, Gemini, GitHub Models-based), and what auth/secrets model?
2. **Branch naming:** do we standardize on `agents/<agent>/issue-<n>` for non-codex, while keeping `codex/issue-<n>`?
3. **UI mentions policy:** can we eliminate `@codex start` entirely from belt activation and rely exclusively on CLI keepalive?
4. **Delegation thresholds:** what constitutes "ineffective" for switching (N failures, no commits, low alignment score)?
5. **Consumer `agent-config.yml`:** Should the sync create a default `.github/agent-config.yml` in consumer repos, or is the registry fallback to `codex` sufficient?
6. **`USE_CONSOLIDATED_WORKFLOWS` rollout:** When should consumer repos enable the event-hub and should the pr-meta-v4 dispatch check for it?

