# Plan: Consolidate Python CI into `pr-10-ci-python.yml`

## 1. Context and Goals
- **Problem statement:** Python checks are currently distributed across several workflows/jobs, which slows iteration and duplicates bootstrapping.
- **Goal:** Deliver a single CI job in `pr-10-ci-python.yml` that enforces formatting (Black), linting (Ruff), type checking (Mypy), unit tests, and coverage reporting while remaining fast and reliable.
- **Constraints:**
  - Maintain the existing workflow filename to preserve downstream reporting integrations.
  - Ensure version pinning for Python tooling leverages the shared environment file called out in Issue 7.
  - Add concurrency controls so newer pushes cancel in-flight runs for the same PR/commit.
  - Avoid running the job on documentation-only changes using the same path filters as the Docker workflow (`docs/**`, `**/*.md`, `.github/ISSUE_TEMPLATE/**`).

## 2. In-Scope Deliverables
1. Update `pr-10-ci-python.yml` to define a single job (`ci-python`) that sequences the required validations.
2. Introduce/consume a shared environment file (e.g., `.github/env/python-ci.env`) that pins versions for Python 3.x, Black, Ruff, Mypy, Pytest, Coverage (or reference existing file if already present).
3. Configure workflow-level `concurrency` with the group pattern `ci-${{ github.ref }}-${{ github.event.pull_request.number || github.sha }}` and `cancel-in-progress: true`.
4. Mirror Docker workflow `paths-ignore` rules to skip docs-only PRs.
5. Emit coverage summary details to the GitHub Step Summary (and maintain compatibility with existing coverage collection).
6. Update documentation (if needed) to explain the unified workflow for maintainers.

## 3. Out of Scope
- Modifying the logical content of tests or lint rules beyond tool version bumps required for compatibility.
- Introducing new tooling beyond Black, Ruff, Mypy, Pytest, Coverage.
- Changes to non-Python CI workflows other than aligning path filters if necessary for integration consistency.

## 4. Proposed Workflow Structure
```
name: CI (Python)

on:
  pull_request:
    paths-ignore:
      - 'docs/**'
      - '**/*.md'
      - '.github/ISSUE_TEMPLATE/**'
  push:
    branches: [ main ]
    paths-ignore: (same as above)

concurrency:
  group: ci-${{ github.ref }}-${{ github.event.pull_request.number || github.sha }}
  cancel-in-progress: true

jobs:
  ci-python:
    runs-on: ubuntu-latest
    env:
      <<: from shared env file
    steps:
      - checkout
      - setup python (from env pins)
      - install dependencies (pip)
      - run black --check
      - run ruff
      - run mypy
      - run pytest with coverage
      - generate coverage XML/HTML as needed
      - append coverage summary to $GITHUB_STEP_SUMMARY
      - upload artifacts (optional)
```

### Step Details
- **Checkout & caching:** Continue using `actions/checkout@v4` and add pip cache keyed on `requirements.lock` if not already present to mitigate slower installs.
- **Environment file:** Use `env: python-version`, `black-version`, etc., loaded via `env:` block and referenced in `actions/setup-python` and pip install commands.
- **Tool installation:** Prefer `pip install --upgrade pip` followed by pinned versions from env to maintain deterministic behaviour.
- **Linting/formatting:** Sequence `black --check .` before `ruff check .` to provide fast fail feedback. Use the same Python invocation to reduce repeated startup cost.
- **Type checking:** Run `mypy` with repository config, ensure `MYPYPATH` exported if required.
- **Tests + coverage:** Execute `pytest --maxfail=1 --disable-warnings --cov=src --cov-report=xml --cov-report=term-missing`. Coverage should fail the job when thresholds unmet (unless soft gate is desired; confirm with stakeholders).
- **Coverage summary:** Parse `coverage xml` or `coverage json` to extract total percent and echo to `$GITHUB_STEP_SUMMARY`. Re-use existing scripts if available.
- **Artifacts:** Upload `.coverage` / HTML to `actions/upload-artifact` if existing flow relies on them.

## 5. Task Breakdown
| # | Task | Acceptance Criteria Trace |
|---|------|---------------------------|
| 1 | Audit current `pr-10-ci-python.yml` jobs/steps; catalogue tooling invocations. | Establishes baseline for consolidation. |
| 2 | Create/verify shared env file with pinned tool versions; document usage. | Supports deterministic tool versions. |
| 3 | Implement workflow changes: single job, concurrency, path filters, env consumption. | Meets main functional acceptance criteria. |
| 4 | Add coverage summary emission and confirm compatibility with existing post-CI summary automation. | Coverage visible in step summary. |
| 5 | Validate docs-only PR skip by simulating workflow path filtering (e.g., `act` dry run or manual reasoning). | Satisfies “docs-only PRs don’t spend cycles.” |
| 6 | Update internal documentation/changelog outlining new behaviour. | Maintains institutional knowledge. |
| 7 | Run test PR (or act) to verify all steps succeed and concurrency cancels prior runs. | Confirms end-to-end behaviour. |

## 6. Acceptance Criteria Mapping
- **Single CI job enforcing style, types, tests, coverage:** Tasks 1–4 ensure all tooling runs in `ci-python` job.
- **Docs-only PRs skip:** Task 5 validates new `paths-ignore` settings.
- **Coverage posted to step summary:** Task 4 handles summary emission.
- **Pinned versions sourced from shared env file:** Task 2 ensures version pinning centralised.
- **Concurrency cancellation:** Task 3 introduces group/cancel config.

## 7. Validation Strategy
1. Use `act pull_request` (if feasible) or GitHub workflow dry runs to verify the new workflow executes end-to-end.
2. Submit a dedicated test PR touching both code and docs-only changes to confirm path filters behave as expected.
3. Inspect GitHub Action run summary to confirm coverage data appears in Step Summary and overall job status gates merges.
4. Review Post CI Summary automation to ensure it still parses the workflow job name/log location.

## 8. Risks & Mitigations
- **Risk:** Shared env file not present or diverges from Issue 7 expectations. → *Mitigation:* Confirm file location with repo maintainers; if missing, add new env file with documentation.*
- **Risk:** Consolidated job runtime becomes too long. → *Mitigation:* Use pip caching and fail-fast ordering (formatting/lint before tests) to surface issues quickly.
- **Risk:** Coverage formatting incompatible with existing summary tools. → *Mitigation:* Re-use existing scripts or output format; test on staging PR before rollout.
- **Risk:** Tool version conflicts with requirements. → *Mitigation:* Align pinned versions with `requirements.lock` and run tests locally before merging.

## 9. Open Questions
- Does the repository already have the shared env file referenced in Issue 7? If not, should it live under `.github/env/` or `config/ci/`?
- Are there repository-specific commands (e.g., `make lint`) that should wrap tool invocations instead of calling tools directly?
- Should coverage act as a hard gate (fail below threshold) or remain informational? Clarify with maintainers.

## 10. Timeline (Estimate)
| Phase | Duration | Activities |
|-------|----------|------------|
| Planning | 0.5 day | Finalise approach, confirm env file availability. |
| Implementation | 1 day | Update workflow, create env file, wire up coverage summary. |
| Verification | 0.5 day | Run workflow tests, adjust as needed, update docs. |
| Rollout | 0.5 day | Merge after reviewer sign-off, monitor initial runs. |

## 11. Definition of Done Checklist
- [x] `pr-10-ci-python.yml` uses `paths-ignore` mirroring Docker workflow.
- [x] Workflow defines concurrency group `ci-${{ github.ref }}-${{ github.event.pull_request.number || github.sha }}` with cancellation.
- [x] Single `ci-python` job executes Black, Ruff, Mypy, Pytest, and coverage steps.
- [x] Versions pulled from shared env file (added or reused) and documented.
- [x] Coverage percentage posted to `$GITHUB_STEP_SUMMARY`.
- [x] Docs-only PR path filter scenario validated.
- [x] Supporting documentation updated and communicated to stakeholders.

## 12. Completion Notes
- Unified workflow landed in `.github/workflows/pr-10-ci-python.yml`, fulfilling the consolidation design with coverage gating and summary publication.
- Shared pins resolved via `.github/workflows/ci-python-versions.env`, which is referenced by both the workflow and maintainer docs.
- Post-CI summary tooling, workflow automation tests, and operational guides were updated to recognize the new single-job topology.
- Path-ignore alignment verified against `pr-12-docker-smoke.yml`; docs-only change simulations confirm the job is skipped while keeping push protection intact.
- Local test suite (`pytest tests/test_automation_workflows.py tests/test_post_ci_summary.py -q`) passes, covering automation behaviour required by the acceptance criteria.
