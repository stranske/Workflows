# Autofix Workflow Logic

## Overview

The autofix workflow is designed to automatically fix formatting and lint issues on pull requests. Understanding when and how it runs is crucial for effective use.

## When Autofix Runs

The autofix workflow (`reusable-18-autofix.yml`) is triggered by the Gate workflow (`pr-00-gate.yml`) with the following conditions:

```yaml
if: |
  always() &&
  github.event_name == 'pull_request' &&
  github.event.pull_request.head.repo.full_name == github.repository &&
  contains(github.event.pull_request.labels.*.name, 'autofix')
```

### Key Points:

1. **`always()` function**: The autofix workflow runs **regardless** of whether Gate passes or fails
2. **Label requirement**: PR must have the `autofix` label
3. **Same repo only**: Only works for PRs from branches in the same repository (not forks)
4. **Pull request events only**: Only triggers on `pull_request` events (not push events)

## Why Autofix Might Be Skipped

Even with `always()`, autofix can be skipped for several reasons:

### 1. Missing `autofix` Label
If the PR doesn't have the `autofix` label, the workflow won't run at all.

**Solution**: Add the `autofix` label to your PR.

### 2. Fork PR
Autofix cannot push commits to fork PRs due to permission restrictions.

**Solution**: For fork PRs, autofix creates a patch artifact that can be downloaded and applied manually.

### 3. Loop Guard
If the last commit was already made by the autofix workflow (detected by commit message prefix), it skips to prevent infinite loops.

**Solution**: This is intentional behavior - no action needed.

### 4. No Changes Needed
If Black and Ruff find no issues to fix, autofix completes but doesn't create a commit.

**Solution**: Check the autofix summary comment to confirm all checks passed.

## Autofix Trigger Classification

The autofix workflow receives a `trigger_class` parameter that indicates why it was triggered:

```yaml
trigger_class: ${{ needs.summary.outputs.state == 'failure' && 'ci-failure' || 'ci-success' }}
```

- **`ci-failure`**: Gate failed (formatting, lint, or test failures)
- **`ci-success`**: Gate passed (running for preventive cleanup)

**Important**: Autofix runs in BOTH cases! The classification is for logging and metrics only.

## Common Misconception

❌ **Wrong**: "Autofix only runs when Gate fails"  
✅ **Correct**: "Autofix runs on every PR with the `autofix` label, regardless of Gate status"

❌ **Wrong**: "If Gate passes, autofix is not needed"  
✅ **Correct**: "Autofix can still apply cleanup even when Gate passes (e.g., import sorting, trailing whitespace)"

## Autofix Workflow Steps

1. **Guard check**: Skip if last commit was an autofix commit (loop prevention)
2. **Detect mode**: Check for `autofix:clean` label (tests-only mode)
3. **Install tools**: Ruff and Black with pinned versions
4. **Apply fixes**:
   - **Standard mode**: Fix all Python files in `src/` and `tests/`
   - **Clean mode**: Only fix test files (cosmetic changes)
5. **Commit and push**: If changes were made
6. **Update PR comment**: Add autofix status summary
7. **Label management**: Add `autofix:applied`, remove old labels

## Manual Formatting vs. Autofix

### When to format manually:

- **Before first push**: Format locally before creating PR
- **After making changes**: Run `black .` before committing
- **When autofix is blocked**: Fork PRs or permission issues

### When to rely on autofix:

- **After PR creation**: Let autofix clean up on first CI run
- **Ongoing work**: Autofix will catch formatting drift
- **Team collaboration**: Ensures consistent formatting across contributors

## Best Practices

1. **Add `autofix` label early**: Include it when creating the PR
2. **Watch for autofix commits**: Wait for autofix to complete before force-pushing
3. **Check autofix comments**: Review the summary to see what was fixed
4. **Format locally first**: Reduce autofix cycles by running Black locally
5. **Don't rely on autofix for passing CI**: Format issues should be rare, not routine

## Debugging Autofix

### Autofix shows as "SKIPPED"

Check these in order:

1. Does PR have `autofix` label? (most common issue)
2. Is PR from the same repo (not a fork)?
3. Was last commit made by autofix? (loop guard)
4. Is the workflow disabled or blocked?

### Autofix runs but doesn't commit

Possible reasons:

1. No formatting/lint issues found (good!)
2. Changes were outside allowed file globs
3. Dry run mode enabled (testing)
4. Push failed due to conflicts

### Autofix creates too many commits

This happens when:

1. Making changes while autofix is running
2. Not formatting locally before pushing
3. Multiple quick pushes triggering multiple autofix runs

**Solution**: Wait for autofix to complete, then pull and continue work.

## Related Documentation

- [Gate Workflow](WORKFLOWS.md#gate) - Main CI orchestrator
- [PR Workflow](../CONTRIBUTING.md) - Contribution guidelines
- [Issue #1347](https://github.com/stranske/Trend_Model_Project/issues/1347) - Loop guard implementation

## Summary

The autofix workflow is a safety net that runs on EVERY PR with the `autofix` label, whether Gate passes or fails. It's designed to catch formatting drift and apply fixes automatically, reducing manual formatting work and ensuring code consistency.

The `always()` function ensures autofix gets a chance to fix issues even when CI fails, making it most useful exactly when things go wrong - not when everything is already perfect.
