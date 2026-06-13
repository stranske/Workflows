# Workloop State

## 2026-06-13T09:46Z - opener (claude_code) issue #2268 -> PR (agent:auto delegation)

- **Selected lane:** `stranske/Workflows` issue [#2268](https://github.com/stranske/Workflows/issues/2268) (`P1: agent:auto delegation is structurally inert`), branch `claude/issue-2268-auto-delegation`, base `main`. Oldest unlinked P1 from the 2026-06-13 repo-review batch; cap was 2/5 (unlinked-liveness override).
- **Three coordinated fixes implemented:**
  1. **Effectiveness signal** (`agent_delegation_policy.js`): a commit-less green Gate no longer counts as progress. `calculateEffectiveness` `effective = commits>=1 || tasks>=1` (dropped `|| gatePassed`; `gatePassed` still returned for reporting); `detectStall` progress test dropped `|| round.gate === 'pass'` so the consecutive-no-progress counter is not reset by green gates.
  2. **Effectiveness-entry guard** (`keepalive_loop.js` ~3853): broadened from `action === 'run'` to `['run','fix','conflict']` so stuck fix/conflict rounds are recorded in `effectiveness_history`.
  3. **Root output wiring** (`.github/workflows/agents-keepalive-loop.yml`): added `agent_routing_mode`, `delegation_reason`, `delegation_should_switch` to the `evaluate` job `outputs:` block and to the summary step `inputs` object, mirroring the consumer template's `agents-81-gate-followups.yml`.
  4. **auto+concrete** (`keepalive_loop.js` ~2385): chose the CODE path — when `agent:auto` is present alongside a concrete `agent:<X>` label, filter to auto-only before `resolveAgentRoutingFromLabels` so auto wins and keepalive stays enabled. This makes the documented "add `agent:auto` alongside" capacity-stuck runbook work, so no CLAUDE.md/LABELS.md change was needed.
- **Sync mirror:** `agent_delegation_policy.js` and `keepalive_loop.js` are sync-manifest mirrored root->consumer (kept byte-identical); copied both modified files into `templates/consumer-repo/.github/scripts/` to keep drift-check green. The test file and the root workflow are not synced.
- **Tests:** added `detectStall fires after 3 zero-commit green-gate rounds` (asserts `isStalled===true`, `consecutiveRounds===3`) and changed the old `calculateEffectiveness returns effective=true when gate passed` to `...does NOT count a commit-less gate pass as effective` (now asserts `effective===false`, `gatePassed===true`). `node --test agent-delegation-policy.test.js` -> `pass 22 fail 0`; `keepalive-loop.test.js` -> `pass 104 fail 0`.
- **Deliberate-break gate (acceptance criterion):** temporarily restored `|| round.gate === 'pass'` in `detectStall` -> new test FAILED with `isStalled` actual `false` / expected `true`; re-applied fix -> passes. JS `node -c` and YAML parse all OK; `git diff --check` clean.
- **Next action:** ready-for-review PR opened with `agent:claude`, `agents:keepalive`, `autofix`; keepalive/Gate owns iteration.

## 2026-06-13T09:13Z - closer (codex) review-fix pushed for #2289

- **Selected complex lane:** `stranske/Workflows` PR [#2289](https://github.com/stranske/Workflows/pull/2289), source issue `#2265`, branch `claude/issue-2265-autopilot-verify-paren`.
- **Blocker:** two unresolved review threads required mirroring the `verify_step` github-script parse/runtime repair from `.github/workflows/agents-auto-pilot.yml` into the consumer template at `templates/consumer-repo/.github/workflows/agents-auto-pilot.yml`.
- **Action:** pushed rebased commit `ae57662b` to the PR branch. The template verify step now closes `createTokenAwareRetry({...})` with `});`, binds `issueNumber` from `process.env.ISSUE_NUMBER`, and removes the stale `agentKey` belt-dispatcher log. Added `test_auto_pilot_verify_step_parses_in_source_and_template` to guard the source/template pair.
- **Validation:** `python -m pytest tests/workflows/test_workflow_agents_consolidation.py -q -rA` passed (`62 passed`); `python scripts/validate_template_completeness.py` passed; `scripts/sync_templates.sh` reported all files already in sync; AsyncFunction parse checks passed for both source and template verify-step script bodies.
- **Review state:** resolved review threads `PRRT_kwDOQprj9M6JUFOW` and `PRRT_kwDOQprj9M6JUFRf`; posted evidence comment https://github.com/stranske/Workflows/pull/2289#issuecomment-4698092479.
- **Next action:** wait for fresh CI on head `ae57662b` to finish. Final snapshot: PR non-draft, `MERGEABLE`, `mergeStateStatus=UNSTABLE`; review threads resolved; checks still in progress (`Gate` python ci/ledger validation, `enforce`, `CodeQL`). If they settle green, merge #2289; Workflows convention means no verifier label unless a repo-specific verifier target is explicitly intended.

## 2026-06-13T08:23Z - closer (codex) review-fix pushed for #2288

- **Selected complex lane:** `stranske/Workflows` PR [#2288](https://github.com/stranske/Workflows/pull/2288), source issue `#2264`, branch `codex/issue-2264-health40-aggregate-heredoc`.
- **Blocker:** two unresolved Copilot review threads in `tests/workflows/test_health40_repo_selfcheck_aggregate.py` flagged indentation/layout-sensitive regex assertions.
- **Action:** relaxed the aggregate heredoc extraction and close-gate assertion regexes to tolerate YAML indentation and line wrapping while preserving the required contract checks.
- **Validation:** `python -m pytest tests/workflows/test_health40_repo_selfcheck_aggregate.py -q -rA` passed (`2 passed`); `python -m py_compile tests/workflows/test_health40_repo_selfcheck_aggregate.py` passed.
- **Next action:** wait for fresh PR checks and review-thread state after push; if checks are green and review threads are resolved, merge and apply the appropriate verifier handling for source issue `#2264`.
