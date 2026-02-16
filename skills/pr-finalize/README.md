# PR Finalization Skill

Automates the post-push PR workflow: address bot reviews, fix CI, merge, verify, and handle follow-ups.

## Usage

### Basic usage (auto-detect PR from current branch)
```bash
/pr-finalize
```

### Specify PR number
```bash
/pr-finalize --pr_number 123
```

### Quick verification mode (doc-only or simple PRs)
```bash
/pr-finalize --verify_mode evaluate
```

### Skip verification (for PRs not from issues)
```bash
/pr-finalize --skip_verification true
```

### Allow more iterations for complex PRs
```bash
/pr-finalize --max_iterations 5
```

## When to Use

✅ **Use this skill when:**
- You've pushed a PR and want automated cleanup
- Bot reviews are arriving and you want to address them
- CI is failing and you want automated fixes
- The PR is ready to merge but needs final checks
- You want verification + follow-up handling

❌ **Don't use this skill when:**
- The PR is still work-in-progress (not ready for review)
- You want to manually control each step
- The PR is part of the auto-pilot system (it has its own handling)
- You're waiting for human reviewer feedback (not bots)

## What It Does

1. **Monitors for bot reviews** (copilot-pull-request-reviewer, etc.)
   - Polls every 30 seconds for new comments
   - Evaluates each comment for validity
   - Makes fixes and pushes updates
   - Marks comments as resolved

2. **Fixes CI failures** (parallel with bot reviews)
   - Polls check status every 20 seconds
   - Diagnoses failures from logs
   - Applies fixes and pushes
   - Repeats until green

3. **Merges when ready**
   - Waits for clean state (no new bot comments, CI green)
   - Squash merges with formatted commit message
   - Waits for merge to complete

4. **Applies verification** (if from issue)
   - Adds `verify:compare` or `verify:evaluate` label
   - Waits for verification workflow
   - Reads results

5. **Handles verification feedback**
   - If PASS: done
   - If CONCERNS with minor work: completes inline
   - If CONCERNS with major work: creates follow-up PR via `verify:create-new-pr` label

## Timeouts

| Phase | Timeout | Notes |
|-------|---------|-------|
| Bot reviews | 10 min/iteration | Resets on each push |
| CI fixes | 10 min/iteration | Resets on each push |
| Verification | 10 minutes | One-time wait |
| Follow-up work | 15 minutes | For inline completion |

**Max iterations**: 3 (configurable)
**Typical runtime**: 10-20 minutes
**Max runtime**: ~60 minutes with all iterations

## Installation

The skill is located at `skills/pr-finalize/` in the Workflows repository.

To use it:
1. Ensure Claude Code CLI has access to the skills directory
2. Type `/pr-finalize` in your Claude Code session

The skill will be auto-discovered by Claude Code.

## Examples

### Example 1: Simple PR with bot reviews
```bash
# Push your PR
git push

# Finalize it
/pr-finalize

# Output:
# Monitoring PR #456...
# ✅ Addressed 3 bot review comments
# ✅ CI passing
# ✅ PR merged
# ✅ Verification: PASS
# Total time: 8 minutes
```

### Example 2: PR with CI failures
```bash
/pr-finalize --pr_number 789

# Output:
# Monitoring PR #789...
# ⚠️ CI check 'Gate' failing - diagnosing...
# 🔧 Fixed lint errors, pushing...
# ✅ CI now passing
# ✅ PR merged
# Total time: 12 minutes
```

### Example 3: PR with follow-up work needed
```bash
/pr-finalize --verify_mode compare

# Output:
# ...
# ✅ PR merged
# ⚠️ Verification: CONCERNS (3 tasks incomplete)
# 🔄 Creating follow-up PR...
# Follow-up tracked in issue #234
# Total time: 18 minutes
```

## Troubleshooting

**Skill times out:**
- Increase `max_iterations`: `/pr-finalize --max_iterations 5`
- Check if bot is stuck in a loop (false positives)

**Bot comments not resolved:**
- Skill may evaluate comment as invalid/out-of-scope
- Check skill output for "Skip" decisions
- Manually resolve if needed

**CI keeps failing:**
- After 3 attempts, skill exits with error summary
- Check logs linked in output
- Fix manually and re-run skill

**Verification stuck:**
- Check workflow status: `gh run list --workflow=agents-verifier.yml`
- May need manual intervention if workflow failed
