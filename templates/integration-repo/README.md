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
