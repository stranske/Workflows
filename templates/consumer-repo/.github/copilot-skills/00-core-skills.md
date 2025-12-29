# GitHub Copilot Skills

This file defines reusable skills and patterns for Copilot to use when working in this repository.

## Skill: Recognize When to Create a New Skill (Meta-Skill)

**Trigger**: When you notice ANY of these patterns:
- Same type of error occurring 3+ times in a session
- Repeating the same debugging steps multiple times
- User expressing frustration about repeated failures
- Discovering a non-obvious fix that took multiple attempts
- Finding that a "simple" task required unexpected steps

**Action**:
1. STOP and acknowledge the pattern
2. Document the learning immediately:
   - What was the repeated failure?
   - What was the root cause?
   - What is the correct approach?
3. Add a new skill to this file or `copilot-instructions.md`
4. Commit the skill update as part of the fix

**Examples of patterns that should become skills**:
- "I tried excluding files from mypy but it didn't work" → Document that `exclude` doesn't prevent import-based checking
- "I pushed directly to main and it was rejected" → Document branch protection workflow
- "CI kept failing and I didn't know why" → Document how to read CI logs properly
- "I forgot to use the PAT again" → Document PAT requirements upfront

**Key insight**: If you're doing something for the third time, it should be a skill.

---

## Skill: Safe GitHub Push

**Trigger**: When pushing changes to any repository

**Steps**:
1. Check current branch: `git branch --show-current`
2. If on `main` or `master`, create a new branch first
3. Check for existing remote: `git remote -v`
4. Verify authentication: `gh auth status`
5. Push to feature branch, never directly to protected branches
6. Create PR if changes are ready for review

## Skill: Debug CI Failure

**Trigger**: When CI is failing on a PR

**Steps**:
1. List recent runs: `gh run list --repo {owner}/{repo} --branch {branch} --limit 5`
2. Get the failing run ID
3. View failed logs: `gh run view {id} --repo {owner}/{repo} --log-failed`
4. If logs are truncated, get job ID and fetch full logs via API
5. Parse error messages and identify root cause
6. Apply appropriate fix based on error type (see Common Fixes below)

## Skill: Fix Mypy Errors

**Trigger**: When mypy type checking fails in CI

**Pattern**:
```toml
# Add to pyproject.toml if module has unfixable type issues
[[tool.mypy.overrides]]
module = ["module_name.*"]
ignore_errors = true
```

**Note**: The `exclude` option only prevents direct file checking. If a module is imported by checked code, it still gets type-checked. Use `[[tool.mypy.overrides]]` with `ignore_errors = true` for modules you want to completely skip.

## Skill: Create Proper Issue

**Trigger**: When creating a GitHub issue

**Template**:
```markdown
## Why
[Business/technical justification]

## Scope
- [ ] Task 1
- [ ] Task 2

## Non-Goals
- What this issue does NOT include

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2

## Implementation Notes
Technical details or constraints
```

## Skill: Verify PR Status

**Trigger**: When checking if a PR is ready to merge

**Steps**:
1. `gh pr checks {pr_number} --repo {owner}/{repo}`
2. Check for "All checks were successful"
3. If failing, identify which check failed
4. Apply appropriate fix skill

## Common Error Patterns

| Error | Likely Cause | Fix |
|-------|-------------|-----|
| `Incompatible types in assignment` | mypy type mismatch | Add to mypy overrides |
| `ModuleNotFoundError: No module named 'X'` | Missing dependency or import path changed | Check package version, update import |
| `coverage below threshold` | Tests don't cover enough code | Lower threshold or add tests |
| `fatal: unable to access` | Auth issue | Check PAT/token |
| `refusing to allow` | Branch protection | Use PR workflow |
