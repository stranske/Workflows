# TODO: Extended Auto-Pilot Implementation

**Status**: Planned, not yet started
**Priority**: Medium
**Estimated effort**: 2-3 hours

## Overview

Create `agents-auto-pilot-extended.yml` - a second version of auto-pilot that extends through verification and handles follow-up PRs (steps 1-5 of the original design).

**Agent-Agnostic Design**: This workflow uses the agent registry system (`.github/agents/registry.yml`). It works with any agent that has the required capabilities, not just Codex. The workflow routes via `agent:auto` labels and uses `resolveAgentFromLabels()` to determine which agent to invoke.

## Key Requirements

### 1. Resolve Inline Coding Agent Comments Before Merge

**Problem**: Current auto-pilot doesn't wait for bot review comments to be resolved.

**Solution**: Add a pre-merge step that:
- Polls for bot comments (copilot-pull-request-reviewer, etc.)
- Waits for comments to be marked as resolved
- OR times out after X minutes and applies `needs-human` label

```yaml
pre-merge-bot-check:
  needs: create-pr
  steps:
    - name: Wait for bot reviews
      run: |
        # Poll for unresolved bot comments
        # If any unresolved after 10 minutes, exit
        # If all resolved, proceed
```

### 2. Wait for Gate to Pass Before Verification

**Problem**: Need to ensure CI is green before applying verification labels.

**Solution**: Add explicit Gate wait step:

```yaml
wait-for-gate:
  needs: pre-merge-bot-check
  steps:
    - name: Poll Gate status
      run: |
        # Wait for pr-00-gate.yml to complete
        # Max wait: 15 minutes
        # If failing, exit (will retry on next push)
```

### 3. Incorporate verify:create-new-pr Logic

**Good idea!** The `agents-verify-to-new-pr.yml` workflow already exists and does:
1. Reads verification CONCERNS/FAIL from PR comments
2. Uses LLM reasoning model to analyze what work remains
3. Creates a 4-round LLM pipeline (analyze → tasks → acceptance criteria → format)
4. Posts new issue with `agent:codex` label

**Integration approach**:
```yaml
handle-verification:
  steps:
    - name: Read verification verdict
      # Parse PASS/CONCERNS/FAIL from verifier comment

    - name: Decide on follow-up
      # If PASS: done
      # If CONCERNS with ≤2 tasks: inline completion
      # If CONCERNS with ≥3 tasks OR FAIL: apply verify:create-new-pr

    - name: Apply verify:create-new-pr label
      if: needs_followup_pr
      run: gh pr edit $PR --add-label "verify:create-new-pr"

    - name: Wait for verify-to-new-pr workflow
      # Poll for workflow completion (max 5 min)
      # Get new issue number from PR comments

    - name: Ensure agent label on new issue
      # The verify-to-new-pr workflow should add agent:auto label
      # If missing, add it to ensure issue gets picked up by auto-pilot
      run: |
        if ! gh issue view $NEW_ISSUE --json labels | grep -q "agent:auto"; then
          gh issue edit $NEW_ISSUE --add-label "agent:auto"
        fi

    - name: Link follow-up
      # Comment: "Follow-up work: #<issue>"
      # The new issue will be picked up by auto-pilot
```

**Chain depth enforcement** (CRITICAL):
```yaml
- name: Check chain depth
  run: |
    # Parse original issue body for "Part of #<parent>"
    # Count depth: original → follow-up #1 → follow-up #2
    # If depth >= 2:
    #   Apply "needs-human" instead of "verify:create-new-pr"
    #   Comment: "Chain depth limit reached (3 PRs). Human review needed."
    #   Exit
```

This prevents:
- ❌ Infinite loops (issue → PR → verification → follow-up → verification → follow-up...)
- ✅ Max 3 PRs per issue chain (original + 2 follow-ups)

## Architecture: Prevent Divergence

**Use composition, not duplication**:

```yaml
# agents-auto-pilot-extended.yml
name: Auto-Pilot Extended

on:
  issues:
    types: [labeled]
  workflow_dispatch:

jobs:
  # Reuse standard auto-pilot for steps 1-8
  run-standard-autopilot:
    uses: ./.github/workflows/agents-auto-pilot.yml
    with:
      issue_number: ${{ github.event.issue.number }}
      # ... other inputs
    secrets: inherit

  # Add post-merge verification (steps 9-12)
  post-merge-verification:
    needs: run-standard-autopilot
    if: needs.run-standard-autopilot.outputs.pr_merged == 'true'
    runs-on: ubuntu-latest
    steps:
      - name: Apply verification label
        # ... step 9

      - name: Wait for verification
        # ... step 10

      - name: Handle verification feedback
        # ... step 11-12
```

**Benefits**:
- ✅ Standard auto-pilot remains unchanged (stable, well-tested)
- ✅ Extended version **calls** standard, no code duplication
- ✅ Easy to switch: change issue label from `agents:auto-pilot` to `agents:auto-pilot-extended`
- ✅ Both versions maintained independently

## Implementation Steps

1. **Phase 1: Create workflow skeleton**
   - Copy structure from agents-auto-pilot.yml
   - Add workflow_call to run-standard-autopilot
   - Add post-merge-verification job with placeholder steps

2. **Phase 2: Implement pre-merge bot check**
   - Poll for bot comments
   - Wait for resolution or timeout
   - Add to standard auto-pilot's merge step

3. **Phase 3: Add Gate wait**
   - Poll for pr-00-gate.yml completion
   - Timeout after 15 minutes

4. **Phase 4: Implement verification**
   - Apply verify:compare label (or verify:evaluate for simple PRs)
   - Wait for agents-verifier.yml
   - Read verdict from PR comments

5. **Phase 5: Handle follow-ups**
   - Parse verification results
   - Decide: inline vs follow-up PR
   - If follow-up: apply verify:create-new-pr, wait, link
   - Enforce chain depth limit (max 3)

6. **Phase 6: Test**
   - Test with simple PR (should PASS)
   - Test with incomplete PR (should create follow-up)
   - Test with 2-level chain (should create follow-up)
   - Test with 3-level chain (should apply needs-human)

7. **Phase 7: Document**
   - Update docs/agent-automation.md
   - Add usage examples
   - Document switching between standard and extended

## Open Questions

- [ ] Should extended be opt-in or default for all auto-pilot runs?
  - **Recommendation**: Opt-in initially (separate label), default after proven stable

- [ ] What timeout values for each phase?
  - **Recommendation**: Bot check: 10min, Gate: 15min, Verification: 10min, Follow-up inline: 15min

- [ ] How to handle chain depth for manually-created follow-ups?
  - **Recommendation**: Parse issue body for "Part of #<parent>" and count depth

## Agent Registry Integration

The extended auto-pilot uses the agent registry system for routing:

```javascript
const { resolveAgentFromLabels } = require('./.github/scripts/agent_registry.js');

// Resolve which agent to use based on labels
const labels = await getIssueLabels(issueNumber);
const agentKey = resolveAgentFromLabels(labels);
// agentKey could be 'codex', 'custom-agent', etc.

// Get agent capabilities
const { getAgentConfig } = require('./.github/scripts/agent_registry.js');
const agentConfig = getAgentConfig(agentKey);

// Check if agent supports verification
if (agentConfig.capabilities?.verifier_checkbox) {
  // Apply verification label
}
```

**Key agent registry files**:
- `.github/agents/registry.yml` - agent definitions and capabilities
- `.github/scripts/agent_registry.js` - routing and capability resolution
- `.github/scripts/keepalive_loop.js` - agent-aware keepalive routing

## Related Files

- `.github/workflows/agents-auto-pilot.yml` - standard version (reuse this)
- `.github/workflows/agents-verifier.yml` - verification workflow
- `.github/workflows/agents-verify-to-new-pr.yml` - follow-up PR creation
- `.github/agents/registry.yml` - agent definitions and capabilities
- `.github/scripts/agent_registry.js` - agent routing logic
- `docs/analysis/autopilot-40pr-evaluation-feb-2026.md` - evaluation report
- `docs/analysis/verify-compare-40pr-evaluation-feb-2026.md` - verifier evaluation
- `skills/pr-finalize/` - similar logic for manual PR workflows

## Success Metrics (After Implementation)

- [ ] Chain depth never exceeds 3
- [ ] 90%+ of verification follow-ups tracked correctly
- [ ] No infinite loops observed
- [ ] Average time from issue to complete closure: <2 hours (for simple issues)
- [ ] needs-human rate: <30% (down from current 40%)

## Timeline

- Skill implementation + testing: 1-2 days
- Extended auto-pilot implementation: 2-3 days
- Testing + refinement: 3-5 days
- **Total**: ~1-2 weeks

---

**Next Step**: Implement and test the pr-finalize skill first, then use its logic as a reference for the extended auto-pilot.
