# Copilot Instructions for this Repository

> **Skills Loaded**: This file contains embedded skills that help with CI debugging, GitHub operations, and meta-patterns. Consult the relevant section when facing issues.

## Quick Reference - When to Apply Which Skill

| Situation | Skill Section |
|-----------|---------------|
| CI failing with mypy errors | [CI Debugging - Mypy](#mypy-type-errors) |
| CI failing with coverage errors | [CI Debugging - Coverage](#coverage-threshold-failures) |
| Workflow failing / startup_failure | [Debugging Workflow Failures](#skill-debugging-workflow-failures) |
| Need to push changes | [GitHub Operations](#standard-pr-workflow) |
| Authentication errors with `gh` | [GitHub Operations - PAT](#authentication--pat-usage) |
| Making same mistake 3+ times | [Meta - Create a Skill](#recognize-when-to-create-a-new-skill) |

---

## Skill: GitHub Operations

### Authentication & PAT Usage
- **Codespaces PAT**: When performing GitHub operations that require elevated permissions (pushing to protected branches, creating releases, etc.), always check if a `CODESPACES_PAT` or `GH_TOKEN` environment variable is available
- Use `gh auth status` to verify current authentication before operations
- If authentication fails, remind the user they may need to set up a PAT with appropriate scopes
- If GITHUB_TOKEN is set and blocking PAT usage: `unset GITHUB_TOKEN` first

### Branch Protection Rules
- **Never assume direct push to `main` is allowed** - most repos have branch protection
- Always create a feature branch first: `git checkout -b fix/descriptive-name`
- Push to the feature branch, then create a PR
- Check for existing branch protection: `gh api repos/{owner}/{repo}/branches/main/protection`

### Standard PR Workflow
1. Create a branch: `git checkout -b type/description` (types: fix, feat, chore, docs)
2. Make changes and commit with conventional commit messages
3. Push branch: `git push origin branch-name`
4. Create PR: `gh pr create --title "type: description" --body "..."`
5. Wait for CI to pass before requesting merge

---

## Skill: CI Debugging

**Trigger**: CI is failing. Before attempting fixes, diagnose the root cause.

### Diagnostic Steps
1. Get the run ID: `gh run list --repo owner/repo --limit 1 --json databaseId`
2. Get failing job: `gh api repos/{owner}/{repo}/actions/runs/{id}/jobs | jq '.jobs[] | select(.conclusion == "failure")'`
3. Get logs: `gh run view {id} --repo owner/repo --log-failed`

### Mypy Type Errors
- If mypy fails on modules with existing type issues, add overrides to `pyproject.toml`:
  ```toml
  [[tool.mypy.overrides]]
  module = ["problematic_module.*"]
  ignore_errors = true
  ```
- **Critical**: The `exclude` pattern in mypy config only prevents direct checking, NOT imports from other modules. Use `ignore_errors = true` in overrides instead.

### Coverage Threshold Failures
- Check both `pyproject.toml` (`[tool.coverage.report] fail_under`) AND workflow files for `coverage-min` settings
- These must match or the lower one wins

### jsonschema Version Conflicts
- Pin to compatible range: `jsonschema>=4.17.3,<4.23.0`
- Version 4.23.0+ has breaking changes with referencing

### Nightly Tests Running in Regular CI
- Add `conftest.py` with pytest hook to skip `@pytest.mark.nightly` tests:
  ```python
  def pytest_collection_modifyitems(config, items):
      for item in items:
          if "nightly" in item.keywords:
              item.add_marker(pytest.mark.skip(reason="Nightly test"))
  ```

---

## Skill: Meta-Patterns

### Recognize When to Create a New Skill

**Trigger**: You've made the same type of mistake or forgotten the same pattern 3+ times.

**Rule**: If you're doing something for the third time, it should be a skill.

**Signs you need a new skill**:
- Forgot to check for PAT before GitHub operations (again)
- Forgot branch protection rules (again)
- Had to re-diagnose the same CI failure pattern
- User expressed frustration about repeated issues

**How to create a skill**:
1. Identify the trigger condition
2. Document the correct steps
3. Add common failure patterns
4. Add to the relevant section of this file

---

## Skill: Debugging Workflow Failures

**Trigger**: A GitHub Actions workflow is failing, especially with `startup_failure` or mysterious errors.

### MANDATORY: Historical Analysis First

**BEFORE theorizing about causes or making fixes:**

1. **Find the boundary between success and failure**:
   ```bash
   gh run list --repo owner/repo --workflow="workflow.yml" --limit 100 --json databaseId,conclusion,createdAt \
     --jq '[.[] | select(.conclusion == "success" or .conclusion == "startup_failure")] | group_by(.conclusion) | .[] | {conclusion: .[0].conclusion, first: .[-1].createdAt, last: .[0].createdAt}'
   ```

2. **Find commits between last success and first failure**:
   ```bash
   git log --oneline --since="LAST_SUCCESS_DATE" --until="FIRST_FAILURE_DATE" -- path/to/workflow.yml
   ```

3. **Examine the exact diff that broke it**:
   ```bash
   git show COMMIT_SHA -- path/to/workflow.yml
   ```

4. **Fix ONLY what the diff changed** - don't "improve" unrelated things

### Anti-Patterns (DO NOT DO)

- ❌ **Theorizing without data**: "Maybe X is causing Y" without checking history
- ❌ **Removing features to fix symptoms**: If removing `models: read` makes the workflow run, but LLM calls then fail silently, you haven't fixed anything
- ❌ **Broad changes**: If one workflow broke, don't change 31 files
- ❌ **Fixing what worked**: If something worked before a specific commit, the fix is reverting/correcting that commit's change

### startup_failure Specific

`startup_failure` with zero jobs means GitHub couldn't even parse/validate the workflow. Common causes:
- Invalid YAML syntax
- **Top-level `permissions:` block on `workflow_call` reusable workflows** (this conflicts with caller permissions)
- Invalid permission scopes
- Circular workflow references

**Documented in**: `docs/INTEGRATION_GUIDE.md` in Workflows repo

---

## Repository-Specific Notes

### Manager-Database (stranske/Manager-Database)
- Has modules with type issues: `adapters/`, `api/`, `etl/`, `embeddings.py`
- Uses Prefect 2.x - import schedules from `prefect.client.schemas.schedules`
- Coverage threshold: 75%

### Travel-Plan-Permission
- Python package in `src/travel_plan_permission/`
- Config files in `config/`
- Templates in `templates/`
