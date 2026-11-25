# Reusable CI & Automation Workflows

Issues #2190 and #2466 consolidated the GitHub Actions surface into reusable
composites plus manual self-tests. These building blocks underpin the Gate
workflow, maintenance jobs, and Codex automation. Legacy consumer wrappers and
the retired Agents 70 stack (`agents-70-orchestrator.yml`,
`reusable-70-orchestrator-init.yml`, `reusable-70-orchestrator-main.yml`,
`reusable-16-agents.yml`) live only in git history, with verification notes in
[ARCHIVE_WORKFLOWS.md](archive/ARCHIVE_WORKFLOWS.md).

| Reusable Workflow | File | Purpose |
| ------------------ | ---- | ------- |
| Reusable CI | `.github/workflows/reusable-10-ci-python.yml` | Primary Python quality gate (lint, types, pytest, coverage). Used by Gate for Python 3.13/3.14. |
| Reusable Docker Smoke | `.github/workflows/reusable-12-ci-docker.yml` | Docker build + smoke test harness consumed by Gate and downstream callers. |
| Autofix | `.github/workflows/reusable-18-autofix.yml` | Formatting / lint autofix composite invoked by the Gate summary job. |
| Selftest: Reusables | `.github/workflows/selftest-reusable-ci.yml` | Manual workflow that bundles the reusable CI matrix with publication logic. Modes toggle summary vs comment output and single vs dual-runtime matrices; optional inputs override Python versions, artifact downloads, and comment presentation. |

## 1. Reusable CI (`reusable-10-ci-python.yml`)
Consumer example (excerpt from `pr-00-gate.yml`):

```yaml
jobs:
  python-ci:
    name: python ci
    uses: ./.github/workflows/reusable-10-ci-python.yml
    with:
      python-versions: '["3.13", "3.14"]'
      primary-python-version: '3.14'
      marker: "not quarantine and not slow"
      artifact-prefix: 'gate-'
```

Key inputs include the Python version matrix, optional pytest marker
expression, and the artifact prefix used to namespace uploads. The reusable job
installs dependencies, runs Ruff, Mypy, and pytest with coverage, then bundles
all runtime payloads inside a single `coverage` artifact rooted at
`artifacts/coverage/`.

## 2. Reusable Docker Smoke (`reusable-12-ci-docker.yml`)
Gate calls this composite to build the Docker image and run the smoke-test
command. Downstream repositories can reuse it directly:

```yaml
jobs:
  docker-smoke:
    uses: stranske/Workflows/.github/workflows/reusable-12-ci-docker.yml@v1
```

No inputs are required; extend by forking the workflow and layering additional
steps if your project needs extra smoke assertions.

## 3. Autofix (`reusable-18-autofix.yml`)
Used by the Gate summary job to apply hygiene fixes once CI
succeeds. Inputs gate behaviour behind opt-in labels and allow custom commit
prefixes. The composite enforces size/path heuristics before pushing changes
with `SERVICE_BOT_PAT`.

## 4. Agent automation entry points

Active Workflows-local automation no longer calls `reusable-16-agents.yml` or the
Agents 70 init/main pair. Use these surfaces instead:

- **Issue intake and bridge:** `agents-63-issue-intake.yml` +
  `reusable-agents-issue-bridge.yml`
- **Issue-to-PR pipeline:** `agents-auto-pilot.yml` (`agents:auto-pilot` label)
- **Codex belt queue:** `agents-71-codex-belt-dispatcher.yml` →
  `agents-72-codex-belt-worker.yml` → `agents-73-codex-belt-conveyor.yml`
- **Manual belt promotion:** `agents-73-codex-belt-conveyor-dispatch.yml`
  (`workflow_dispatch`, default preview via `dry_run`)
- **PR keepalive commands:** `agents-pr-meta-v4.yml` dispatches workers directly
  ([#5162](https://github.com/stranske/Workflows/pull/5162); measured capacity
  [#5163](https://github.com/stranske/Workflows/pull/5163))
- **Ad-hoc issue verification:** `agents-64-verify-agent-assignment.yml`

Example manual belt promotion preview:

```bash
gh workflow run agents-73-codex-belt-conveyor-dispatch.yml \
  --ref main \
  --raw-field dry_run=true
```

Example Agents 64 verification:

```bash
gh workflow run agents-64-verify-agent-assignment.yml \
  --ref main \
  --raw-field issue_number=1234
```

## 5. Selftest: Reusables (`selftest-reusable-ci.yml`)
Hosts the matrix that validates the reusable CI executor across feature
combinations (coverage delta, soft gate, metrics, history, classification)
and publishes the verification results. Dispatch the workflow manually to
select summary vs. PR comment reporting, enable dual-runtime execution, or
override the Python version list entirely via the `python_versions` input.
Artifact downloads remain optional (`enable_history`), and the comment/summary
titles plus dispatch reason can be customised to document ad-hoc runs.

## Adoption Notes
1. Reference the files directly via `uses: stranske/Workflows/.github/workflows/<file>@v1` in external repos.
2. Pin versions explicitly (e.g. `@v1.2.3`) or use a commit SHA when strict reproducibility is required.
3. For agent automation, adopt the consumer-template
   `agents-80-pr-event-hub.yml` / `agents-81-gate-followups.yml` pair or call
   the belt and Auto-Pilot workflows above. Consult [ARCHIVE_WORKFLOWS.md](archive/ARCHIVE_WORKFLOWS.md)
   for retired orchestrator history.

## Customisation Points
| Area | How to Extend | Notes |
| ---- | ------------- | ----- |
| Coverage reporting | Chain an additional job that depends on the reusable CI job to upload coverage artifacts. | Keep job IDs stable when referencing outputs. |
| Autofix heuristics | Update the Gate summary job to widen size limits or adjust glob filters. | Avoid editing the reusable composite unless behaviour must change globally. |
| Belt promotion | Tune `dry_run` and promotion bounds on `agents-73-codex-belt-conveyor-dispatch.yml`. | Eligibility selection cannot be bypassed with arbitrary manual targets. |

## Security & Permissions
- CI workflows default to `permissions: contents: read`; escalate only when artifacts require elevated scopes.
- Autofix pushes require `SERVICE_BOT_PAT`; keep fallback disabled unless intentionally allowing `github-actions[bot]` commits.
- Agents automation exercises repository write scopes and continues to fail fast if secrets are missing. Belt and keepalive honour
  PAT priority (`OWNER_PR_PAT` → `SERVICE_BOT_PAT` → `GITHUB_TOKEN`) via the shared API client.

Keep this document aligned with the final workflow roster; update it whenever
inputs or defaults change.