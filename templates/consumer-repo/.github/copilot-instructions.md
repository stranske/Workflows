# Copilot Instructions for this Repository

## GitHub Operations

### Authentication & PAT Usage
- **Codespaces PAT**: When performing GitHub operations that require elevated permissions (pushing to protected branches, creating releases, etc.), always check if a `CODESPACES_PAT` or `GH_TOKEN` environment variable is available
- Use `gh auth status` to verify current authentication before operations
- If authentication fails, remind the user they may need to set up a PAT with appropriate scopes

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

## CI/CD Patterns

### Common CI Failures & Fixes

#### Mypy Type Errors
- If mypy fails on modules with existing type issues, add overrides to `pyproject.toml`:
  ```toml
  [[tool.mypy.overrides]]
  module = ["problematic_module.*"]
  ignore_errors = true
  ```
- The `exclude` pattern in mypy config only prevents direct checking, NOT imports from other modules

#### Coverage Threshold Failures
- Check both `pyproject.toml` (`[tool.coverage.report] fail_under`) AND workflow files for `coverage-min` settings
- These must match or the lower one wins

#### jsonschema Version Conflicts
- Pin to compatible range: `jsonschema>=4.17.3,<4.23.0`
- Version 4.23.0+ has breaking changes with referencing

#### Nightly Tests Running in Regular CI
- Add `conftest.py` with pytest hook to skip `@pytest.mark.nightly` tests:
  ```python
  def pytest_collection_modifyitems(config, items):
      for item in items:
          if "nightly" in item.keywords:
              item.add_marker(pytest.mark.skip(reason="Nightly test"))
  ```

## Repository-Specific Notes

### Manager-Database (stranske/Manager-Database)
- Has modules with type issues: `adapters/`, `api/`, `etl/`, `embeddings.py`
- Uses Prefect 2.x - import schedules from `prefect.client.schemas.schedules`
- Coverage threshold: 75%

### Travel-Plan-Permission (this repo)
- Python package in `src/travel_plan_permission/`
- Config files in `config/`
- Templates in `templates/`

## Workflow Tips

### Before Starting Any Fix
1. `gh pr list --repo owner/repo` - Check existing PRs
2. `gh run list --repo owner/repo --branch branch-name` - Check CI status
3. Read the actual error logs: `gh run view {id} --repo owner/repo --log-failed`

### Debugging CI Failures
1. Get the run ID: `gh run list --repo owner/repo --limit 1 --json databaseId`
2. Get failing job: `gh api repos/{owner}/{repo}/actions/runs/{id}/jobs | jq '.jobs[] | select(.conclusion == "failure")'`
3. Get logs: `gh api repos/{owner}/{repo}/actions/jobs/{job_id}/logs`

### Creating Issues
- Follow the repo's issue template format (check `docs/AGENT_ISSUE_FORMAT.md` if exists)
- Include: Why, Scope, Non-Goals, Tasks, Acceptance Criteria
