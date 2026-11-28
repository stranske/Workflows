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
1. From the root of a Workflows checkout, render the project into an empty directory.
   ```bash
   python -m tools.integration_repo /tmp/workflows-integration --workflow-ref "stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@v1"
   ```
2. Push the generated repository to GitHub.
3. Enable Actions and confirm the workflow passes across multiple Python versions.

The placeholder string `__WORKFLOW_REF__` inside the template files is replaced with your provided
workflow reference when rendering.

## How the integration repository stays current

Rendering a new project copies the full template and adds the two coverage-trend helpers.
The existing integration repository has its own README, example code and project settings.
It receives selected CI workflows, version pins, scripts and label guidance through Maint 69.
The sync also merges coverage exclusions and dependency pins into its project configuration
and regenerates its lockfile. [Integration repository](https://github.com/stranske/Workflows-Integration-Tests)

Maint 69 runs on changes to its listed source paths, on a daily schedule and by manual dispatch.
Its apply step defines the delivered paths. Health 67 checks the receiver’s CI configuration and
version pins. [Maint 69 delivery workflow](https://github.com/stranske/Workflows/blob/main/.github/workflows/maint-69-sync-integration-repo.yml) · [Health 67 checks](https://github.com/stranske/Workflows/blob/main/.github/workflows/health-67-integration-sync-check.yml)

## Check dependency updates

In the existing integration checkout, install the tracked requirements and run
`python scripts/validate_dependency_test_setup.py` from the project root. The command
checks that the lock's compile header includes the project's extras and that its direct
dependencies have compatible pins. It also flags direct test assertions that compare a
package's `__version__` or an imported package metadata version lookup to a fixed version.
A freshly rendered fixture has no lock, so the command runs its assertion check alone.
