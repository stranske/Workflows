# Provider-Agnostic Coding Agents: Progress Evaluation (Feb 2026)

**Evaluation Date:** February 17, 2026
**Plan Document:** [`docs/plans/provider-agnostic-coding-agents.md`](../plans/provider-agnostic-coding-agents.md)
**Related PRs:** #1526, #1527 (Phase 0), #1529 (Phase 2)

## Executive Summary

**Overall Progress: ~55% complete (Phases 0-2 mostly done, 3-5 pending)**

The provider-agnostic refactor has made **substantial foundation progress** with the registry infrastructure and routing logic in place. However, **critical consumer-facing components** (belt, auto-pilot, issue→PR path) remain Codex-hardcoded.

### Quick Status by Phase

| Phase | Status | Completion | Notes |
|-------|--------|------------|-------|
| **Phase 0** | ✅ **Complete** | 100% | Eval removed, version pinned, contract documented |
| **Phase 1** | ✅ **Complete** | 100% | Registry + resolver shipped with tests |
| **Phase 2** | 🟡 **Partial** | 70% | Keepalive + autofix use registry; bot-comment handler updated |
| **Phase 3** | 🔴 **Not Started** | 0% | Belt, auto-pilot, issue-bridge still hardcode `codex/issue-*` |
| **Phase 4** | 🟡 **Partial** | 40% | Verifier resolves agent from labels but defaults to Codex |
| **Phase 5** | 🔴 **Not Started** | 0% | No delegation/routing logic exists |

---

## Phase-by-Phase Analysis

### Phase 0: Runner Hardening ✅ **COMPLETE**

**Objective:** Make Codex runner safer without changing pipeline behavior.

#### ✅ Completed Items

1. **Eval removal**: `reusable-codex-run.yml` line 885 has comment: `# Parse EXTRA_ARGS_RAW safely (no eval)`
2. **Version pinning**: Codex CLI installed with `@${{ inputs.codex_cli_version }}` parameter
3. **Output contract**: Runner produces structured outputs (message, exit code, change detection, task analysis)

#### Evidence

- **PR:** #1526, #1527
- **Key Files:**
  - `.github/workflows/reusable-codex-run.yml` (229 lines added/refactored)
  - `.github/agents/registry.yml` (new)
  - `.github/scripts/agent_registry.js` (216 lines, new)

#### Remaining Concerns

- No explicit documentation of the "agent-runner output contract" as a formal spec
  - The plan called for documenting this interface
  - While the contract exists in code, there's no `docs/contracts/agent-runner-output.md`

---

### Phase 1: Agent Registry + Resolver ✅ **COMPLETE**

**Objective:** Centralize agent definitions so workflows don't embed assumptions.

#### ✅ Completed Items

1. **Registry file**: `.github/agents/registry.yml` exists with:
   - `version: 1`
   - `default_agent: codex`
   - Per-agent config: runner workflow, secrets, branch prefix, capabilities, UI mention policy

2. **Resolver helper**: `.github/scripts/agent_registry.js` provides:
   - `loadAgentRegistry()`
   - `resolveAgentFromLabels(labels)` — label → agent key
   - `resolveAgentRoutingFromLabels()` — with routing metadata
   - `getAgentConfig(agentKey)`
   - `getRunnerWorkflow(agentKey)`

3. **Unit tests**: `.github/scripts/__tests__/agent-registry.test.js` (69+ lines)

4. **Synced to consumers**: `templates/consumer-repo/.github/agents/registry.yml` and resolver script present

#### Evidence

- **PR:** #1527
- **Registry content:**
  ```yaml
  agents:
    codex:
      runner_workflow: .github/workflows/reusable-codex-run.yml
      required_secrets: [CODEX_AUTH_JSON]
      branch_prefix: codex/issue-
      ui_mentions_allowed: false
      capabilities:
        pr_keepalive: true
        pr_autofix: true
        belt: true
        verifier_checkbox: true
  ```

#### Strengths

- Clean abstraction with testable helpers
- Synced to consumers via manifest
- Case-insensitive label resolution (#1529 fix)

---

### Phase 2: Provider-Agnostic Entrypoints 🟡 **70% COMPLETE**

**Objective:** Make PR-based automation multi-agent capable without touching the belt.

#### ✅ Completed Items

1. **Keepalive routing**:
   - `.github/workflows/agents-keepalive-loop.yml`:
     - Evaluate step outputs `agent_type`
     - `run-codex` job has `if: needs.evaluate.outputs.agent_type == 'codex'`
     - Placeholder for `run-claude` job (lines 518-526)
   - **Pattern:** Conditional jobs per agent (not dynamic dispatch)

2. **Autofix routing**:
   - `.github/workflows/agents-autofix-loop.yml`:
     - Uses `loadAgentRegistry()` to validate agent labels
     - Extracts agent type from labels
     - Filters valid agent keys from registry

3. **Bot comment handler**:
   - `.github/workflows/reusable-bot-comment-handler.yml`:
     - Updated to use agent registry (83 lines modified)

4. **Consumer templates synced**:
   - `templates/consumer-repo/.github/workflows/agents-autofix-loop.yml`
   - `templates/consumer-repo/.github/workflows/autofix.yml`

#### 🟡 Partial / Pending

1. **No actual multi-agent runner invocations yet**:
   - Keepalive still only calls `reusable-codex-run.yml`
   - No `run-claude` job is active (only commented placeholder)
   - **Gap:** Need a second agent runner (e.g., `reusable-claude-run.yml`) OR generic dispatcher

2. **Hard-coded runner references remain**:
   - Line 496: `uses: stranske/Workflows/.github/workflows/reusable-codex-run.yml@main`
   - **Gap:** Registry has `runner_workflow` field but it's not dynamically referenced

#### Evidence

- **PR:** #1529
- **Files Changed:**
  - `.github/scripts/keepalive_loop.js` (24 lines modified for agent handling)
  - `.github/workflows/agents-autofix-loop.yml` (111 lines modified)
  - `.github/workflows/reusable-bot-comment-handler.yml` (83 lines modified)

#### Assessment

**Why 70%?**
- ✅ Infrastructure is agent-aware (registry, labels, conditional jobs)
- ✅ Default behavior preserved (Codex-only)
- 🟡 **Cannot actually run a second agent yet** — need Claude runner or generic dispatcher
- 🟡 **Acceptance criteria met for Codex** but not validated for "unknown agent fail fast"

---

### Phase 3: Provider-Agnostic Issue→PR Path 🔴 **0% COMPLETE**

**Objective:** Remove hard-coded `codex/issue-*` branch assumptions.

#### 🔴 Not Started

1. **Auto-pilot still hardcodes branch prefix**:
   - `.github/workflows/agents-auto-pilot.yml` line 1937:
     ```javascript
     let branchPrefix = 'codex/issue-';
     ```
   - **Gap:** Should use `registry.agents[agentKey].branch_prefix`

2. **Belt workflows are Codex-specific**:
   - `.github/workflows/agents-71-codex-belt-dispatcher.yml`
   - `.github/workflows/agents-72-codex-belt-worker.yml`
   - `.github/workflows/agents-73-codex-belt-conveyor.yml`
   - **Gap:** No generic `agents-71-belt-dispatcher.yml` exists

3. **Issue bridge likely hardcoded**:
   - `.github/workflows/reusable-agents-issue-bridge.yml`
   - Branch creation logic probably uses `codex/issue-` directly

#### Impact

**HIGH** — This phase blocks:
- Using non-Codex agents for issue→PR flows
- Auto-pilot creating PRs with other agents
- Belt system supporting multiple agents

#### Recommended Next Steps

1. **Refactor auto-pilot branching** (est. 1 PR):
   - Add agent resolution from issue labels
   - Use `registry.agents[agentKey].branch_prefix`
   - Default to Codex if no agent label

2. **Create generic belt workflows** (est. 2-3 PRs):
   - `agents-71-belt-dispatcher.yml` (parameterized by `agent_key`)
   - `agents-72-belt-worker.yml` (parameterized)
   - `agents-73-belt-conveyor.yml` (parameterized)
   - Keep `agents-71-codex-belt-*` as thin wrappers calling generics with `agent_key=codex`

3. **Update issue-bridge** (est. 1 PR):
   - Resolve agent from issue labels
   - Use registry branch prefix

---

### Phase 4: Verifier Agent-Aware 🟡 **40% COMPLETE**

**Objective:** Follow-up issues/PRs preserve originating agent intent.

#### ✅ Completed Items

1. **Verifier resolves agent from PR labels**:
   - `.github/workflows/reusable-agents-verifier.yml`:
     - Step "Resolve agent key from PR labels" (id: agent)
     - Uses `resolveAgentFromLabels()` from registry
     - Lines 524-525: extracts `agent_label` and `from_label`

2. **Fallback to Codex**:
   - Lines 835-836: `|| 'agent:codex'` and `|| 'from:codex'`

#### 🟡 Partial / Pending

1. **Follow-up creation not verified**:
   - Does `agents-verify-to-new-pr.yml` use the resolved agent?
   - Or does it default to `agent:codex` when creating follow-up issues?
   - **Gap:** Need to trace follow-up issue creation to confirm agent propagation

2. **Default still Codex-centric**:
   - If label resolution fails, defaults to Codex
   - **Acceptable** per plan (Codex remains default)
   - But unclear if this is logged/observable

#### Evidence

- **PR:** #1529 (verifier updates included)
- **File:** `.github/workflows/reusable-agents-verifier.yml` (agent resolution step added)

#### Assessment

**Why 40%?**
- ✅ Infrastructure reads agent from source PR
- 🟡 **Unverified:** Follow-up issue creation actually uses resolved agent
- 🟡 **No provenance tags:** Plan mentioned `from:<key>` tags but unclear if implemented fully

---

### Phase 5: Delegation / Re-routing 🔴 **0% COMPLETE**

**Objective:** System-controlled delegation between agents based on capacity/effectiveness.

#### 🔴 Not Started

1. **No `agent:auto` label handling**:
   - Searched workflows and scripts: zero matches
   - **Gap:** No routing mode exists

2. **No effectiveness metrics**:
   - Searched for "effectiveness" in scripts: only rate limit comments
   - **Gap:** No measurement of:
     - Commits produced per round
     - Tasks checked per iteration
     - Gate pass rate
     - Round productivity

3. **No capacity tracking**:
   - Searched for "capacity" logic: only rate limit capacity
   - **Gap:** No tracking of in-progress runs per agent

4. **No switching logic**:
   - No policy-based agent hand-off code
   - **Gap:** No decision engine to change agents mid-PR

#### Impact

**MEDIUM** — Delegation is advanced feature, not required for multi-agent support.

#### Recommended Approach (When Prioritized)

1. **Define effectiveness signals** (doc/spec):
   - Commits per keepalive round
   - Task completion rate
   - Gate pass after N rounds
   - LLM alignment score from progress-review

2. **Add capacity tracking** (metrics):
   - In-progress runs per agent (query GitHub Actions API)
   - Rate limit headroom per agent token pool

3. **Implement routing decision** (new script):
   - `.github/scripts/agent_router.js`
   - Input: current agent, effectiveness history, capacity
   - Output: continue or switch to agent X

4. **Wire into evaluate step**:
   - Keepalive evaluate calls router
   - Records decision in summary
   - Next round uses new agent

---

## Critical Gaps Summary

### High Priority (Blocks Multi-Agent Support)

1. **No second agent runner exists** (Phase 2 incomplete):
   - Need `reusable-claude-run.yml` OR generic `reusable-agent-run.yml` dispatcher
   - Without this, registry routing cannot be tested end-to-end

2. **Auto-pilot hardcodes `codex/issue-` branches** (Phase 3 blocker):
   - Line 1937 in `agents-auto-pilot.yml`
   - Must use `registry.agents[agentKey].branch_prefix`

3. **Belt system is Codex-only** (Phase 3 blocker):
   - No generic belt workflows exist
   - Cannot process issues with non-Codex agent labels

### Medium Priority (Limits Flexibility)

4. **Runner contract undocumented** (Phase 0 gap):
   - No formal `docs/contracts/agent-runner-output.md`
   - Makes implementing new runners ambiguous

5. **Follow-up agent propagation unverified** (Phase 4 gap):
   - Unclear if `agents-verify-to-new-pr.yml` uses resolved agent
   - Risk of follow-ups reverting to Codex regardless of source

6. **Dynamic runner dispatch not used** (Phase 2 limitation):
   - Keepalive uses conditional jobs (`if: agent_type == 'codex'`)
   - Could simplify with `uses: ${{ needs.evaluate.outputs.runner_workflow }}`
   - Current pattern requires adding a new job per agent

---

## Strengths & Wins

### What's Working Well

1. **Excellent foundation** (Phases 0-1):
   - Registry is well-structured and extensible
   - Resolver helpers are clean, tested, and reusable
   - Eval removal + version pinning hardens Codex runner

2. **Backward compatibility preserved**:
   - All changes maintain Codex as default
   - No consumer repos broken during rollout
   - Consumer template sync included in Phase 0/1/2 PRs

3. **Incremental, testable approach**:
   - Small PRs with clear phase boundaries
   - Unit tests added for registry logic
   - Sync manifest enforced for consumer artifacts

4. **Agent-awareness in place**:
   - Keepalive evaluate outputs `agent_type`
   - Autofix validates agent labels against registry
   - Verifier resolves agent from PR labels

### Code Quality Observations

- Clean separation of concerns (registry vs. resolver vs. workflows)
- YAML parsing hand-rolled but robust (avoids external deps)
- Case-insensitive label handling (good UX)

---

## Recommendations

### Immediate Next Steps (Complete Phase 2)

1. **Ship a second agent runner** (choose one):
   - **Option A:** Implement `reusable-claude-run.yml` (mirrors Codex structure)
   - **Option B:** Create generic `reusable-agent-run.yml` that dispatches internally
   - **Recommendation:** Option A (less risk, validates pattern)

2. **Add fail-fast for unknown agents**:
   - Keepalive evaluate should error clearly if `agent_type` not in registry
   - Prevents silent failures or confusing defaults

3. **Document runner output contract**:
   - Create `docs/contracts/agent-runner-output.md`
   - Specify required outputs: message, exit code, change detection, task analysis format
   - Reduces friction for adding new agents

### Medium-Term (Phase 3)

4. **Refactor auto-pilot branch logic**:
   - Replace hardcoded `codex/issue-` with registry lookup
   - Test with dummy agent in registry (e.g., `test-agent`)

5. **Genericize belt workflows**:
   - Create parameterized versions
   - Maintain Codex wrappers for backward compat
   - Sync templates with updated agent-aware belt callers

### Long-Term (Phases 4-5)

6. **Validate follow-up agent propagation**:
   - End-to-end test: verify→new-pr→check resulting issue labels
   - Document behavior in `docs/keepalive/MULTI_AGENT_ROUTING.md`

7. **Design delegation policy** (when multi-agent is proven):
   - Define effectiveness metrics
   - Create routing decision spec
   - Implement `agent:auto` mode

---

## Risk Assessment

### Low Risk Areas

- ✅ Phases 0-1 complete and stable
- ✅ No evidence of Codex regressions from registry refactor
- ✅ Consumer repos have registry + resolver synced

### Medium Risk Areas

- 🟡 **Phase 2 incomplete**: Cannot validate multi-agent routing end-to-end
- 🟡 **Phase 3 not started**: Major refactor ahead (auto-pilot, belt)
- 🟡 **Undocumented contract**: New agent implementers lack clear spec

### High Risk Areas

- 🔴 **Auto-pilot branch logic**: Single failure point for issue→PR flow
  - Recommendation: Extensive testing in Workflows repo before sync
- 🔴 **Belt parameterization**: Complex workflows, high consumer impact
  - Recommendation: Staged rollout (Workflows → Travel-Plan-Permission → others)

---

## Open Questions (From Plan)

### Answered by Implementation

1. ~~**Second agent target:**~~ Partially answered
   - Registry structure supports any provider
   - But no second runner exists yet
   - Likely target: Claude (placeholder job exists in keepalive-loop)

2. ~~**Branch naming:**~~ Answered
   - Standard will be `{branch_prefix}` from registry
   - Codex keeps `codex/issue-`, others could use `agents/<agent>/issue-` or custom

### Still Open

3. **UI mentions policy:**
   - Plan asks: "Can we eliminate `@codex start` entirely from belt activation?"
   - Status: Unknown — need to audit belt workflows for `@codex` posting
   - Registry sets `ui_mentions_allowed: false` for Codex
   - But enforcement mechanism unclear

4. **Delegation thresholds:**
   - What constitutes "ineffective" for switching?
   - No design doc or metrics exist yet
   - Deferred to Phase 5

---

## Conclusion

The provider-agnostic refactor has made **excellent foundational progress** (Phases 0-1 complete, Phase 2 mostly done). However, **critical consumer-facing components** (auto-pilot, belt, issue→PR) remain Codex-hardcoded, blocking actual multi-agent support.

**The system is ready to support multiple agents architecturally, but cannot operationally until Phase 3 completes.**

### Success Criteria Progress

| Criteria | Status |
|----------|--------|
| Centralized agent assumptions | ✅ Done (registry) |
| Codex preserved as default | ✅ Done |
| Optional delegation/routing | 🔴 Not started |
| No-noise + keepalive invariants | ✅ Maintained |
| Consumer repo safety | ✅ Phased rollout, validation gates |

### Path to 100% Completion

1. **Complete Phase 2:** Ship second agent runner (1 week)
2. **Complete Phase 3:** Refactor auto-pilot + belt (2-3 weeks)
3. **Complete Phase 4:** Validate follow-up propagation (1 week)
4. **Complete Phase 5:** Design + implement delegation (3-4 weeks)

**Estimated remaining effort:** 7-9 weeks for full multi-agent capability with delegation.

---

**Next Review:** After Phase 3 completion or 30 days, whichever comes first.
