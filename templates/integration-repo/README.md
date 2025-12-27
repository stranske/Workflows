# Integration Test Consumer Repository Template

This template provisions a minimal Python project wired to the reusable CI workflow from this
repository. It is intended to validate compatibility from an external consumer perspective
(e.g., GitHub Actions `uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@v1`).

## Files
- `.github/workflows/ci.yml` — invokes the reusable workflow using a provided ref placeholder.
- `pyproject.toml` — minimal Python project configuration with pytest.
- `src/example/__init__.py` — tiny implementation code.
- `tests/test_example.py` — simple passing test to exercise workflow steps.
- `.gitignore` — ignore common Python build artifacts.

## Usage
1. Render the template:
   ```bash
   python -m tools.integration_repo /tmp/workflows-integration --workflow-ref "stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@v1"
   ```
2. Push the generated repository to GitHub.
3. Enable Actions and confirm the workflow passes across multiple Python versions.

The placeholder string `__WORKFLOW_REF__` inside the template files is replaced with your provided
workflow reference when rendering.

## Automated Sync

This template is automatically synced to the [Workflows-Integration-Tests](https://github.com/stranske/Workflows-Integration-Tests) repository:

- **Sync Workflow**: `.github/workflows/maint-69-sync-integration-repo.yml`
- **Health Check**: `.github/workflows/health-67-integration-sync-check.yml`
- **Trigger**: Pushes to main that modify `templates/integration-repo/**` or `.github/workflows/autofix-versions.env`

The Integration-Tests repo serves as the live validation environment for the reusable CI workflow.
