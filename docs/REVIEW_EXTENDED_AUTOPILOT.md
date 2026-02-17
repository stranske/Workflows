# Extended Auto-Pilot Design Review

**Status**: Ready for final review before implementation
**Date**: 2026-02-17
**Context**: Agent-agnostic routing system (Phase 5) completed

---

## Executive Summary

The extended auto-pilot will complete the original design vision: take an issue from creation through merge, verification, and follow-up PRs until all acceptance criteria are met.

**Key Design Principles**:
1. ✅ **Agent-agnostic** - uses registry-based routing (`agent:auto`)
2. ✅ **Composition over duplication** - calls standard auto-pilot, adds verification layer
3. ✅ **Fail-safe chain depth limit** - max 3 PRs (original + 2 follow-ups)
4. ✅ **Graceful degradation** - works with or without verification workflows
5. ✅ **Reuses existing workflows** - leverages verify:create-new-pr logic

---

## Agent-Agnostic System (Completed in Phase 5)

### How It Works

**Agent Registry** (`.github/agents/registry.yml`):
```yaml
version: 1
default_agent: codex

agents:
  codex:
    runner_workflow: .github/workflows/reusable-codex-run.yml
    required_secrets:
      - CODEX_AUTH_JSON
    capabilities:
      pr_keepalive: true
      pr_autofix: true
      verifier_checkbox: true

  claude:
    runner_workflow: .github/workflows/reusable-claude-run.yml
    capabilities:
      pr_keepalive: true
      verifier_checkbox: true

  custom-agent:
    runner_workflow: .github/workflows/reusable-custom-run.yml
    capabilities:
      pr_keepalive: true
```

**Label Routing** (works with ANY registered agent):
- `agent:auto` → routes to `default_agent` (codex)
- `agent:codex` → explicit routing to codex
- `agent:claude` → explicit routing to claude
- `agent:custom-agent` → explicit routing to custom-agent
- Multiple agent labels → error (conflict)

**Extended auto-pilot works with ALL agent labels** - it dynamically resolves the agent from labels and checks that agent's capabilities.

**Capability Checks**:
```javascript
const agentConfig = getAgentConfig(agentKey);
if (agentConfig.capabilities?.verifier_checkbox) {
  // Agent supports verification
  applyVerificationLabel();
}
```

### Impact on Extended Auto-Pilot

✅ **Before** (hardcoded): Workflow only worked with Codex
✅ **After** (registry-based): Workflow works with any registered agent

The extended auto-pilot will:
1. **Read issue labels** to determine agent via `resolveAgentFromLabels()`
   - Works with `agent:auto`, `agent:codex`, `agent:claude`, `agent:custom`, etc.
   - User can apply ANY agent label - workflow adapts dynamically
2. **Check agent capabilities** before applying verification
   - Not all agents may support verification (`verifier_checkbox: true` required)
3. **Use agent-specific runner workflow** for follow-up work
   - Each agent has its own runner workflow path in the registry

**Example**: If user applies `agent:claude`, extended auto-pilot will:
- Resolve agent → `claude`
- Check `claude.capabilities.verifier_checkbox` → if true, apply verification
- Use `claude.runner_workflow` for inline follow-up completions

---

## Extended Auto-Pilot Architecture

### High-Level Flow

```
Issue created with agent:auto label
         ↓
┌─────────────────────────────────────────┐
│  Standard Auto-Pilot (Steps 1-8)        │
│  - Format issue                          │
│  - Optimize                              │
│  - Apply suggestions                     │
│  - Capability check                      │
│  - Create PR                             │
│  - Wait for bot reviews → RESOLVE        │ ← NEW
│  - Wait for Gate → GREEN                 │ ← NEW
│  - Merge PR                              │
└─────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────┐
│  Extended Verification (Steps 9-12)      │
│  - Apply verify label                    │ ← NEW
│  - Wait for verification                 │ ← NEW
│  - Read verdict                          │ ← NEW
│  - Handle follow-ups                     │ ← NEW
│    • PASS → done                         │
│    • CONCERNS (≤2 tasks) → complete      │
│    • CONCERNS (≥3 tasks) → new PR        │
│    • FAIL → new PR                       │
│  - Enforce chain depth limit (max 3)     │ ← NEW
└─────────────────────────────────────────┘
```

### New Steps (9-12)

#### Step 9: Apply Verification

**Agent capability check**:
```yaml
- name: Check agent supports verification
  id: check_capability
  run: |
    AGENT=$(node -e "
      const { resolveAgentFromLabels, getAgentConfig } =
        require('./.github/scripts/agent_registry.js');
      const labels = ${{ toJSON(github.event.issue.labels) }};
      const agentKey = resolveAgentFromLabels(labels);
      const config = getAgentConfig(agentKey);
      console.log(config.capabilities?.verifier_checkbox ? 'true' : 'false');
    ")
    echo "supports_verification=$AGENT" >> $GITHUB_OUTPUT

- name: Apply verification label
  if: steps.check_capability.outputs.supports_verification == 'true'
  run: |
    MODE="${{ inputs.verify_mode || 'compare' }}"
    gh pr edit $PR_NUMBER --add-label "verify:$MODE"
```

**Auto-detect verify mode** based on PR characteristics:
- Doc-only changes → `verify:evaluate` (quick)
- Substantial code changes → `verify:compare` (thorough)

#### Step 10: Wait for Verification

```yaml
- name: Poll for verification completion
  timeout-minutes: 10
  run: |
    while true; do
      # Check for verification comment from bot
      VERDICT=$(gh pr view $PR_NUMBER --json comments --jq '
        .comments[] |
        select(.author.login | contains("bot")) |
        select(.body | contains("Verification Result")) |
        .body | match("Verdict: (PASS|CONCERNS|FAIL)").captures[0].string
      ')

      if [ -n "$VERDICT" ]; then
        echo "verdict=$VERDICT" >> $GITHUB_OUTPUT
        break
      fi

      sleep 20
    done
```

#### Step 11: Decide Follow-Up Strategy

```yaml
- name: Analyze remaining work
  id: analyze
  run: |
    VERDICT="${{ steps.wait.outputs.verdict }}"

    if [ "$VERDICT" == "PASS" ]; then
      echo "strategy=done" >> $GITHUB_OUTPUT
      exit 0
    fi

    # Count incomplete tasks in verification report
    INCOMPLETE=$(gh pr view $PR_NUMBER --json comments --jq '
      .comments[] |
      select(.body | contains("Verification Result")) |
      .body | scan("- \\[ \\]") | length
    ')

    # Check chain depth
    DEPTH=$(gh issue view $ISSUE --json body --jq '
      .body | scan("Part of #[0-9]+") | length
    ')

    if [ "$DEPTH" -ge 2 ]; then
      echo "strategy=needs-human" >> $GITHUB_OUTPUT
      echo "Chain depth limit reached (3 PRs max)"
    elif [ "$INCOMPLETE" -le 2 ]; then
      echo "strategy=inline" >> $GITHUB_OUTPUT
    else
      echo "strategy=followup-pr" >> $GITHUB_OUTPUT
    fi
```

#### Step 12: Execute Follow-Up Strategy

**Strategy: inline** (≤2 simple tasks):
```yaml
- name: Complete inline
  if: steps.analyze.outputs.strategy == 'inline'
  run: |
    # Resolve which agent to use
    AGENT=$(node -e "
      const { resolveAgentFromLabels, getRunnerWorkflow } =
        require('./.github/scripts/agent_registry.js');
      const labels = ${{ toJSON(github.event.issue.labels) }};
      const agentKey = resolveAgentFromLabels(labels);
      const workflow = getRunnerWorkflow(agentKey);
      console.log(workflow);
    ")

    # Trigger agent to complete remaining tasks
    gh workflow run "$AGENT" \
      -f issue_number=$ISSUE \
      -f instruction="Complete remaining verification tasks"

    # Wait for completion (max 15 min)
    # Re-run verification
```

**Strategy: followup-pr** (≥3 tasks or complex):
```yaml
- name: Create follow-up PR
  if: steps.analyze.outputs.strategy == 'followup-pr'
  run: |
    # Apply verify:create-new-pr label
    gh pr edit $PR_NUMBER --add-label "verify:create-new-pr"

    # Wait for agents-verify-to-new-pr.yml to complete (max 5 min)
    # ... polling logic ...

    # Get new issue number from PR comments
    NEW_ISSUE=$(gh pr view $PR_NUMBER --json comments --jq '
      .comments[] |
      select(.body | contains("Created follow-up issue")) |
      .body | match("#([0-9]+)").captures[0].string
    ')

    # Ensure agent:auto label on new issue
    gh issue edit $NEW_ISSUE --add-label "agent:auto"

    # Link back
    gh issue comment $ISSUE --body "Follow-up work tracked in #$NEW_ISSUE"
```

**Strategy: needs-human** (chain depth limit):
```yaml
- name: Escalate to human
  if: steps.analyze.outputs.strategy == 'needs-human'
  run: |
    gh pr edit $PR_NUMBER --add-label "needs-human"
    gh issue comment $ISSUE --body "⚠️ Chain depth limit reached (3 PRs).
    Original issue → PR #$PR_1 → PR #$PR_2 → PR #$PR_3.

    Remaining work requires human review to prevent infinite loops."
```

---

## Critical: Pre-Merge Checks

**NEW: Bot Review Resolution** (before merge):
```yaml
pre-merge-checks:
  runs-on: ubuntu-latest
  needs: create-pr
  steps:
    - name: Wait for bot reviews to be resolved
      timeout-minutes: 10
      run: |
        while true; do
          UNRESOLVED=$(gh pr view $PR_NUMBER --json reviewThreads --jq '
            .reviewThreads | map(select(.isResolved == false)) | length
          ')

          if [ "$UNRESOLVED" -eq 0 ]; then
            echo "All bot reviews resolved"
            break
          fi

          echo "Waiting for $UNRESOLVED review threads to be resolved..."
          sleep 30
        done
```

**NEW: Gate Wait** (before merge):
```yaml
    - name: Wait for Gate to pass
      timeout-minutes: 15
      run: |
        while true; do
          STATUS=$(gh pr checks $PR_NUMBER --json name,state,conclusion --jq '
            .[] | select(.name == "Gate") | .conclusion
          ')

          if [ "$STATUS" == "success" ]; then
            echo "Gate passed"
            break
          elif [ "$STATUS" == "failure" ]; then
            echo "::error::Gate failed"
            exit 1
          fi

          sleep 20
        done
```

**Merge only when**:
- ✅ Bot reviews resolved
- ✅ Gate passed
- ✅ No unresolved comments

---

## Chain Depth Enforcement

**Problem**: Without limits, verification loops can create infinite PR chains.

**Solution**: Track chain depth and enforce maximum.

### Tracking Chain Depth

**In follow-up issue body**:
```markdown
## Context

Part of #123 (original issue)

<!-- Chain depth: 1 -->
```

**Parsing chain depth**:
```bash
DEPTH=$(gh issue view $ISSUE --json body --jq '
  (.body | scan("Part of #[0-9]+") | length) +
  (.body | scan("Chain depth: ([0-9]+)") | .[0] | tonumber // 0)
')
```

### Chain Depth Limits

| Depth | Description | Action |
|-------|-------------|--------|
| 0 | Original issue | Apply verification |
| 1 | First follow-up | Apply verification |
| 2 | Second follow-up | Apply verification (LAST) |
| 3+ | Depth limit | Apply `needs-human`, no more PRs |

**Rationale**: 3 PRs should be enough for any issue. If not, human design is needed.

---

## Workflow Composition (Prevent Divergence)

### Current Auto-Pilot (Stable, Well-Tested)

```yaml
# agents-auto-pilot.yml
name: Auto-Pilot

on:
  issues:
    types: [labeled]
  workflow_dispatch:

jobs:
  # Steps 1-8 (format, optimize, apply, create PR, merge)
  ...
```

### Extended Auto-Pilot (New)

```yaml
# agents-auto-pilot-extended.yml
name: Auto-Pilot Extended

on:
  issues:
    types: [labeled]
  workflow_dispatch:

jobs:
  # Reuse standard auto-pilot
  run-standard:
    uses: ./.github/workflows/agents-auto-pilot.yml
    with:
      issue_number: ${{ github.event.issue.number }}
    secrets: inherit

  # Add verification layer
  post-merge-verification:
    needs: run-standard
    if: needs.run-standard.outputs.pr_merged == 'true'
    runs-on: ubuntu-latest
    steps:
      # Pre-merge checks (bot reviews, Gate)
      - uses: ./.github/actions/pre-merge-checks
        with:
          pr_number: ${{ needs.run-standard.outputs.pr_number }}

      # Step 9: Apply verification
      - name: Apply verification
        # ... (see above)

      # Step 10: Wait for verification
      - name: Wait for verification
        # ... (see above)

      # Step 11: Analyze follow-up
      - name: Analyze follow-up
        # ... (see above)

      # Step 12: Execute strategy
      - name: Execute strategy
        # ... (see above)
```

**Benefits**:
- ✅ No code duplication
- ✅ Standard auto-pilot unchanged (stable)
- ✅ Easy to switch modes (change label)
- ✅ Both workflows maintained independently

---

## Testing Plan

### Phase 1: Unit Tests
- [ ] Chain depth parsing logic
- [ ] Agent capability detection
- [ ] Follow-up strategy decision logic

### Phase 2: Integration Tests (in Workflows repo)

**Test Case 1: Simple PR (should PASS)**
- Issue: "Fix typo in README"
- Expected: 1 PR, verification PASS, no follow-up

**Test Case 2: Complex PR (should create follow-up)**
- Issue: "Add new feature X with tests"
- Expected: 1 PR, verification CONCERNS (≥3 tasks), follow-up PR created

**Test Case 3: Chain depth limit**
- Create: Original issue → PR #1 (CONCERNS) → Issue #2 → PR #2 (CONCERNS) → Issue #3 → PR #3 (CONCERNS)
- Expected: PR #3 gets `needs-human`, no Issue #4 created

**Test Case 4: Agent capability check**
- Create agent without `verifier_checkbox` capability
- Expected: Skip verification phase

**Test Case 5: Bot review resolution**
- PR with bot comments
- Expected: Wait for resolution before merge

**Test Case 6: Gate failure**
- PR with failing Gate
- Expected: Wait for Gate to pass or timeout

### Phase 3: Production Test (in Travel-Plan-Permission)

- Apply `agents:auto-pilot-extended` label to real issue
- Monitor end-to-end flow
- Verify metrics, timing, error handling

---

## Rollout Plan

### Week 1: Development
- [ ] Create `agents-auto-pilot-extended.yml` skeleton
- [ ] Implement pre-merge checks (bot review, Gate)
- [ ] Implement verification steps (9-10)

### Week 2: Follow-Up Logic
- [ ] Implement follow-up decision logic (step 11)
- [ ] Implement follow-up execution (step 12)
- [ ] Implement chain depth enforcement
- [ ] Add agent capability checks

### Week 3: Testing
- [ ] Unit tests
- [ ] Integration tests in Workflows repo
- [ ] Fix issues, refine timeouts

### Week 4: Production Trial
- [ ] Deploy to Workflows repo
- [ ] Trial with 5-10 real issues
- [ ] Monitor metrics: chain depth, needs-human rate, completion rate
- [ ] Adjust based on results

### Week 5: Sync to Consumers
- [ ] Update documentation
- [ ] Sync to Travel-Plan-Permission, Manager-Database, etc.
- [ ] Switch default from `auto-pilot` to `auto-pilot-extended`

---

## Success Metrics (After 30 Days)

| Metric | Current | Target | How to Measure |
|--------|---------|--------|----------------|
| First-fix rate (chain ends at original PR) | 35% | 50%+ | Count PRs without follow-ups |
| Average chain depth | 2.7 PRs | 2.0 PRs | Avg depth across all chains |
| Max chain depth observed | 6 PRs | 3 PRs (enforced) | Max depth hit before needs-human |
| needs-human rate | 40% | <30% | % of issues labeled needs-human |
| Complete closure rate (no human intervention) | ~60% | 70%+ | % of issues fully closed by automation |

---

## Design Decisions (Finalized)

### Q1: Verify Mode Selection ✅ AUTO-DETECT

**Decision**: Auto-detect based on PR size/complexity

```yaml
- name: Choose verify mode
  id: choose_mode
  run: |
    # Get PR stats
    ADDITIONS=$(gh pr view $PR --json additions --jq '.additions')
    FILES_CHANGED=$(gh pr view $PR --json changedFiles --jq '.changedFiles')

    # Heuristic:
    # - Small PRs (<50 lines, <3 files) → evaluate (single LLM, 2-3 min)
    # - Large PRs (≥50 lines or ≥3 files) → compare (dual LLM, 5-7 min)
    if [ "$ADDITIONS" -lt 50 ] && [ "$FILES_CHANGED" -lt 3 ]; then
      MODE="evaluate"
    else
      MODE="compare"
    fi

    echo "mode=$MODE" >> $GITHUB_OUTPUT
```

**Rationale**: Optimize for speed when appropriate, thoroughness when needed.

### Q2: Inline Completion Timeout ✅ SCALE BY TASK COUNT

**Decision**: Scale based on task count (5 minutes per task)

```yaml
- name: Set inline timeout
  run: |
    TASK_COUNT=$(gh pr view $PR --json comments --jq '
      .comments[] |
      select(.body | contains("Verification")) |
      .body | scan("- \\[ \\]") | length
    ')

    TIMEOUT=$((TASK_COUNT * 5))  # 5 min per task
    TIMEOUT=$((TIMEOUT < 10 ? 10 : TIMEOUT))  # Min 10 min
    TIMEOUT=$((TIMEOUT > 30 ? 30 : TIMEOUT))  # Max 30 min

    echo "timeout=$TIMEOUT" >> $GITHUB_OUTPUT
```

**Rationale**: Scales with complexity, prevents premature timeout on multi-task fixes.

### Q3: Bot Review Timeout ✅ APPLY NEEDS-HUMAN

**Decision**: 10 minutes, then apply `needs-human` (don't merge with unresolved reviews)

```yaml
- name: Wait for bot reviews
  timeout-minutes: 10
  continue-on-error: true
  id: bot_wait
  run: |
    # ... polling logic ...

- name: Handle timeout
  if: steps.bot_wait.outcome == 'failure'
  run: |
    gh pr edit $PR --add-label "needs-human"
    gh pr comment $PR --body "⚠️ Bot review threads remain unresolved after 10 minutes.

    Please manually resolve before merging."
    exit 1  # Don't proceed to merge
```

**Rationale**: Safety over speed. Unresolved bot comments may indicate real issues.

### Q4: Chain Depth Tracking ✅ PARSE ISSUE BODY

**Decision**: Parse issue body for "Part of #XXX"

```yaml
- name: Calculate chain depth
  id: depth
  run: |
    BODY=$(gh issue view $ISSUE --json body --jq '.body')

    # Count "Part of #XXX" occurrences
    DEPTH=$(echo "$BODY" | grep -o "Part of #[0-9]\+" | wc -l)

    echo "depth=$DEPTH" >> $GITHUB_OUTPUT

    # Enforce limit
    if [ "$DEPTH" -ge 2 ]; then
      echo "Chain depth limit reached (depth=$DEPTH, max=2)"
      echo "exceeds_limit=true" >> $GITHUB_OUTPUT
    else
      echo "exceeds_limit=false" >> $GITHUB_OUTPUT
    fi
```

**Rationale**: Simple, stateless, works with existing issue format. No new infrastructure needed.

---

## Summary

**Ready to implement**:
- ✅ Agent-agnostic design (uses registry routing)
- ✅ Composition architecture (reuses standard auto-pilot)
- ✅ Chain depth enforcement (max 3 PRs)
- ✅ Pre-merge checks (bot reviews, Gate)
- ✅ Graceful degradation (works without verification)

**Need your input on**:
- Verify mode selection strategy (Q1)
- Inline completion timeout (Q2)
- Bot review timeout behavior (Q3)
- Chain depth tracking mechanism (Q4)

**Once approved**, I'll proceed with Week 1 implementation.
