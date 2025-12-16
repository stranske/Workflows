# Reusable CI & Automation Workflows

Issues #2190 and #2466 consolidated the GitHub Actions surface into four
reusable composites plus a set of manual self-tests. These building blocks
underpin the Gate workflow, maintenance jobs, and Codex automation. Treat the
orchestrator as the single entry point for agents; legacy consumer wrappers were
retired and now live only in git history, with verification notes captured in
[ARCHIVE_WORKFLOWS.md](archive/ARCHIVE_WORKFLOWS.md).

| Reusable Workflow | File | Purpose |
| ------------------ | ---- | ------- |
| Reusable CI | `.github/workflows/reusable-10-ci-python.yml` | Primary Python quality gate (lint, types, pytest, coverage). Used by Gate for Python 3.11/3.12. |
| Reusable Docker Smoke | `.github/workflows/reusable-12-ci-docker.yml` | Docker build + smoke test harness consumed by Gate and downstream callers. |
| Autofix | `.github/workflows/reusable-18-autofix.yml` | Formatting / lint autofix composite invoked by the Gate summary job. |
| Agents Toolkit | `.github/workflows/reusable-16-agents.yml` | Readiness, Codex bootstrap, diagnostics, verification, keepalive, and watchdog routines dispatched exclusively through the orchestrator. |
| Selftest: Reusables | `.github/workflows/selftest-reusable-ci.yml` | Manual workflow that bundles the reusable CI matrix with publication logic. Modes toggle summary vs comment output and single vs dual-runtime matrices; optional inputs override Python versions, artifact downloads, and comment presentation. |

## 1. Reusable CI (`reusable-10-ci-python.yml`)
Consumer example (excerpt from `pr-00-gate.yml`):

```yaml
jobs:
  python-ci:
    name: python ci
    uses: ./.github/workflows/reusable-10-ci-python.yml
    with:
      python-versions: '["3.11", "3.12"]'
      primary-python-version: '3.11'
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
    uses: stranske/Trend_Model_Project/.github/workflows/reusable-12-ci-docker.yml@main
```

No inputs are required; extend by forking the workflow and layering additional
steps if your project needs extra smoke assertions.

## 3. Autofix (`reusable-18-autofix.yml`)
Used by the Gate summary job to apply hygiene fixes once CI
succeeds. Inputs gate behaviour behind opt-in labels and allow custom commit
prefixes. The composite enforces size/path heuristics before pushing changes
with `SERVICE_BOT_PAT`.

## 4. Agents Toolkit (`reusable-16-agents.yml`)
Exposes the agent automation stack as a reusable component. All top-level
automation calls flow through **Agents 70 Orchestrator**, which normalises the
inputs and forwards them here. Dispatch the orchestrator either via the Actions
UI or by posting a JSON payload through the `params_json` input. The
[catalog page](ci/WORKFLOWS.md#manual-orchestrator-dispatch) carries the full
walkthrough; the condensed CLI flow is repeated below for quick reference:

```bash
cat <<'JSON' > orchestrator.json
{
  "enable_readiness": true,
  "enable_preflight": true,
  "enable_bootstrap": true,
  "bootstrap_issues_label": "agent:codex",
  "options_json": "{\"diagnostic_mode\":\"dry-run\"}"
}
JSON

export GITHUB_TOKEN="$(gh auth token)"  # Token must allow workflow dispatch

gh workflow run agents-70-orchestrator.yml \
  --ref main \
  --raw-field params_json="$(cat orchestrator.json)"
```

The same payload can be passed to the REST endpoint with `curl` if preferred. Ensure the GitHub CLI (for the example above) or `jq` + a shell that supports process substitution (for the REST command in [docs/ci/WORKFLOWS.md](ci/WORKFLOWS.md#manual-orchestrator-dispatch)) are available before running the snippets.

Example orchestrator snippet:

```yaml
jobs:
  orchestrate:
    uses: ./.github/workflows/reusable-16-agents.yml
    with:
      enable_readiness: ${{ inputs.enable_readiness || 'false' }}
      readiness_agents: ${{ inputs.readiness_agents || 'copilot,codex' }}
      enable_preflight: ${{ inputs.enable_preflight || 'false' }}
      enable_bootstrap: ${{ inputs.enable_bootstrap || 'false' }}
      bootstrap_issues_label: ${{ fromJson(inputs.options_json || '{}').bootstrap_issues_label || 'agent:codex' }}
      options_json: ${{ inputs.options_json || '{}' }}
```

Timeouts live inside the reusable workflow so the orchestrator avoids invalid
syntax. Each automation path has a bound sized to its typical runtime plus
headroom (readiness/preflight: 15 minutes, diagnostics: 20 minutes, bootstrap:
30 minutes, keepalive: 25 minutes).

## 5. Selftest: Reusables (`selftest-reusable-ci.yml`)
Hosts the matrix that validates the reusable CI executor across feature
combinations (coverage delta, soft gate, metrics, history, classification)
and publishes the verification results. Dispatch the workflow manually to
select summary vs. PR comment reporting, enable dual-runtime execution, or
override the Python version list entirely via the `python_versions` input.
Artifact downloads remain optional (`enable_history`), and the comment/summary
titles plus dispatch reason can be customised to document ad-hoc runs.

## Adoption Notes
1. Reference the files directly via `uses: stranske/Trend_Model_Project/.github/workflows/<file>@main` in external repos.
2. Pin versions or branch references explicitly; do not rely on floating defaults.
3. When adopting the agents toolkit, point automation at `agents-70-orchestrator.yml`. Historical consumer wrappers were removed;
   consult [ARCHIVE_WORKFLOWS.md](archive/ARCHIVE_WORKFLOWS.md) only if you need the retirement log.

## Customisation Points
| Area | How to Extend | Notes |
| ---- | ------------- | ----- |
| Coverage reporting | Chain an additional job that depends on the reusable CI job to upload coverage artifacts. | Keep job IDs stable when referencing outputs. |
| Autofix heuristics | Update the Gate summary job to widen size limits or adjust glob filters. | Avoid editing the reusable composite unless behaviour must change globally. |
| Agents options | Provide extra keys inside `params_json` (and embed `options_json` when structured overrides are required) and update the reusable workflow to honour them. | Remember GitHub only supports 10 dispatch inputs; keep new flags in JSON. |

## Security & Permissions
- CI workflows default to `permissions: contents: read`; escalate only when artifacts require elevated scopes.
- Autofix pushes require `SERVICE_BOT_PAT`; keep fallback disabled unless intentionally allowing `github-actions[bot]` commits.
- Agents automation exercises repository write scopes and continues to fail fast if secrets are missing. The orchestrator honours
  PAT priority (`OWNER_PR_PAT` → `SERVICE_BOT_PAT` → `GITHUB_TOKEN`).

Keep this document aligned with the final workflow roster; update it whenever
inputs or defaults change.
