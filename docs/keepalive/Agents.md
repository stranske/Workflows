# Agents Guidance — Keepalive Changes

Automation agents touching **any** keepalive code path must consult the following documents before making changes. Keepalive is **multi-agent** by design—Codex and Claude share the same orchestration surfaces—so every change must read from `.github/agents/registry.yml` (or `agent_registry.js`) instead of hard-coding provider-specific behavior.

## Required Reading

1. **[`GoalsAndPlumbing.md`](GoalsAndPlumbing.md)** — Canonical contract covering:
   - Activation prerequisites (labels, human kickoff, Gate status)
   - Instruction comment formatting and required hidden markers
   - Dispatch, acknowledgement, and branch-sync responsibilities
   - Pause/resume labels and run-cap enforcement
   - The full lifecycle sequence

2. **[`MULTI_AGENT_ROUTING.md`](MULTI_AGENT_ROUTING.md)** — Multi-agent architecture:
   - How `agent:*` labels route to different agent workflows
   - Task appendix injection into prompts
   - Adding support for new agents (Claude, Gemini, etc.)
   - Why explicit task injection matters

3. **[`Observability_Contract.md`](Observability_Contract.md)** — Required observability:
   - Mandatory one-line summaries
   - Marker formats for instruction comments
   - Decision point visibility

4. **[`../analysis/autopilot-40pr-evaluation-feb-2026.md`](../analysis/autopilot-40pr-evaluation-feb-2026.md)** — Auto-pilot pipeline evaluation:
   - 40-PR sample analysis (Workflows + TMP repos)
   - Component-by-component assessment
   - Recommendations and elements to preserve
5. **[`../guides/ADD_NEW_AGENT.md`](../guides/ADD_NEW_AGENT.md)** — Checklist for onboarding new agents (registry entries, runner workflows, docs/tests) so every automation surface treats Codex, Claude, and future agents consistently.

## Auto-Pilot Integration

The keepalive loop is one stage within the larger **auto-pilot pipeline** (`agents-auto-pilot.yml`). Understanding their relationship is essential:

```
Auto-pilot pipeline:
  format → optimize → apply → capability-check → CREATE-PR → KEEPALIVE → verify → done
                                                      │            │
                                                      │            └─ Event-driven loop:
                                                      │               Gate pass → task appendix
                                                      │               → agent runner → push → repeat
                                                      └─ Creates branch + PR with issue context
```

### How Keepalive Fits In

| Auto-pilot does... | Keepalive does... |
|--------------------|--------------------|
| Formats and enriches the issue | Drives the agent through PR tasks |
| Creates the PR and branch | Evaluates Gate results and remaining work |
| Dispatches the next pipeline step | Builds task appendix from PR body checkboxes |
| Triggers verification post-merge | Dispatches the registry-backed agent with explicit task context |

### Critical Integration Points

1. **PR body is the contract**: Auto-pilot writes structured tasks into the PR body. Keepalive reads these tasks via the task appendix. If the PR body format changes, both must be updated together.

2. **Labels are handoff signals**: Auto-pilot applies the selected registry-backed `agent:<name>` label (for example, `agent:codex` or `agent:claude`) and keepalive activates. Every non-transient run/fix failure records automation-owned recovery state and explicitly dispatches a bounded retry through the active workflow (`agents-keepalive-loop.yml` in the root lane or `agents-81-gate-followups.yml` in consolidated consumers). A failed direct dispatch defers that durable lease for the hourly sweep instead of adding a sticky `agent:retry` label; after 3 failures, the current strategy pauses for the same hourly recovery sweep. It does not infer that a human is required. Each hourly sweep wakeup bypasses state debounce so current state is re-evaluated, while ordinary wakeups retain completed-runner debounce. A possible authority boundary enters an independent scheduled challenge whose durable fingerprint is derived only from the routed agent's registry-backed required credentials, shared registry authority credentials, finite permission targets, and HTTP 401/403; arbitrary runner text is never copied or persisted. Both the root and consolidated consumer lanes require a dedicated keepalive or Workflows App token before marking an agent running or writing the final summary, so every mutation of App-owned state uses the same trusted writer class. Every keepalive reader selects durable state only from a marked summary comment owned by `stranske-keepalive[bot]`, `agents-workflows-bot[bot]`, the identity-checked PAT fallbacks `stranske` and `stranske-automation-bot`, or the migration-only legacy `github-actions[bot]` writer; arbitrary users cannot override an earlier trusted state marker. When the selected App encounters a summary from the known legacy writer or the other dedicated App, it preserves the parsed state in a new comment owned by that App because editing the old comment would retain its original author. Only the sweep passes a valid HMAC-signed claim using `KEEPALIVE_AUTHORITY_SIGNING_KEY` and binding that fingerprint to the repository, PR, random nonce, and exact sweep run/attempt; that signed due claim alone may bypass runner debounce and force-dispatch. A generic retry or another workflow sharing `github-actions[bot]` cannot confirm the challenge. Missing signing material fails closed to an ordinary non-forced recheck. A matching second failure may record the projected human action and apply `needs-human`. A different auth failure stays automation-owned and is challenged again on the next sweep.

3. **Gate is the trigger**: Keepalive is event-driven via Gate `workflow_run` completion. Auto-pilot's `monitor-pr` step watches for keepalive progress. Neither polls — both react to events.

4. **Self-dispatch**: Auto-pilot uses `force_step` re-dispatch, not label changes, to sequence its stages. The keepalive loop is triggered independently by Gate completion, not by auto-pilot dispatch.

5. **Repo playbook context**: The Orchestrator registry is the single editable owner for curated per-repo definition-of-done and gotcha rules. `repo_knowledge.py --export-agents-md <owner/repo> --repo-path <checkout> --apply` may write a small generated section in a repo's `AGENTS.md` between `<!-- BEGIN orch-playbook -->` and `<!-- END orch-playbook -->`; humans should edit the registry, not the generated block. Keepalive owns freshness validation: Gate runs `scripts/check_agents_md_freshness.py` in warning-only mode so stale cited paths or commands surface without wedging unrelated PRs while the registry is seeded.

6. **Stall rotation and challenge before `needs-human`**: When an auto-pilot stall cap is reached, the pipeline tries a *different* eligible agent before requesting an independent authority challenge. It is registry-driven and bounded — the stalled agent is recorded with an `agents:tried-<agent>` label, so each rotation shrinks the candidate set. Exhausting eligible agents proves only that the current strategies stalled, not that a human is required. Two paths:
   - **Belt lane (create-PR: no branch / no commits)** — no PR/keepalive history exists yet, so the pure decision helper [`agent_stall_rotation.js`](../../.github/scripts/agent_stall_rotation.js) (`decideStallRotation`, capability `belt`) picks the next untried belt-capable agent, swaps the `agent:<name>` label, and re-dispatches the belt via `agents-71-codex-belt-dispatcher.yml` with the new `agent_key`.
   - **Keepalive lane (monitor-PR: a PR exists)** — reuses the existing registry-driven delegation policy ([`agent_delegation_policy.js`](../../.github/scripts/agent_delegation_policy.js)) rather than rebuilding rotation: auto-pilot adds `agent:auto` to the issue and PR so `decideNextAgent` rotates across the fuller keepalive-capable set (codex/claude/cursor/gemini) on its next round. If `agent:auto` is already present, delegation has had its chance and auto-pilot escalates.

   Both paths are **fail-safe**: any error or "no untried eligible agent left" routes to automation retry or an independent challenge with a concrete owner and next action. It does not silently become a human request. Capability gating means the set of rotation targets grows automatically as the registry marks more agents `belt`/`pr_keepalive` capable — no workflow edit needed.

## Key Principles

1. **Task Focus**: Agents must work on PR tasks, not unrelated improvements. Tasks are explicitly injected via the task appendix.

2. **Agent Agnostic**: The keepalive prompt is agent-agnostic. Routing is determined by the `agent:*` label, not hardcoded agent names.
   - Manual runs still use `agent:<name>` labels to trigger the bridge. When you’re using auto-pilot, add `agents:auto-pilot` plus an optional `runner:<name>` label (for example `runner:claude`). Auto-pilot records the override, applies the matching `agent:<name>` label when the capability check completes, and keeps keepalive/autofix/verifier flows aligned without kicking off the issue intake workflow.

3. **No `@codex` in Prompts**: Do not use `@codex` or other agent mentions in automated prompts—this can trigger the UI version of agents. Let the routing handle which agent runs.

4. **Verify Before Marking Complete**: Only mark task checkboxes complete after verifying the implementation works.

5. **Follow-up Chain Depth**: Follow-up chains **must not** exceed depth 2 (original + 2 follow-ups). `agents-verify-to-new-pr.yml` enforces the limit and applies `needs-human` instead of creating additional follow-up issues when the limit is reached. See [`verify-compare-40pr-evaluation-feb-2026.md`](../analysis/verify-compare-40pr-evaluation-feb-2026.md) for the evaluation baseline that motivated this guardrail.

6. **Capacity Mode**: When auth, API quota, or local workspace constraints limit the next action, record one of `normal`, `graphql-only`, `local-only`, `blocked-on-auth`, or `blocked-on-rate-reset` in the durable state surface for that workflow. Include the blocked command, quota/auth snapshot when relevant, reset time if known, and next safe action.

7. **`gh` token precedence during debugging**: When investigating workflow failures, `gh` will prefer `GH_TOKEN`/`GITHUB_TOKEN` env vars over stored auth. If checks/log visibility looks inconsistent, temporarily unset env tokens and retry diagnostics:

```bash
unset GH_TOKEN GITHUB_TOKEN
gh auth status
```

If there is no stored auth session, run commands with an explicit token (for example `GH_TOKEN="$CODESPACES" ...`) and document scope limitations instead of assuming repository misconfiguration.

## Keepalive Implementations

The repository supports two keepalive implementations. The **Codex CLI keepalive** is the current, canonical flow. The **legacy UI connector-bot** flow is retained for historical context and compatibility.

See [`Keepalive_Approaches.md`](Keepalive_Approaches.md) for a full comparison and the rationale for preferring the CLI approach.

Do not mark checklist items complete or dispatch new keepalive rounds until the acceptance criteria in the canonical guide are satisfied. Update all relevant documents together if the contract evolves.

## Implementation-Level Details

For the technical patterns inside each agent runner workflow — CLI invocation flags, unpushed commit detection, artifact filtering, commit/push retry logic — see the **[Agent Runner Implementation Guide](../guides/AGENT_RUNNER_IMPLEMENTATION.md)**. That guide covers the mechanics that this document intentionally omits.
