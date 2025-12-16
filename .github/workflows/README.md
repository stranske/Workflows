# Workflow & Agent Automation Quick Start (Issue #2466)

This guide gives maintainers a fast reference for the streamlined CI and agent
automation stack. Pair it with
[docs/WORKFLOW_GUIDE.md](../../docs/WORKFLOW_GUIDE.md) for the canonical
inventory and naming rules.

---
## 1. Architecture Snapshot
Core layers:
- Gate orchestrator (`pr-00-gate.yml`): single required check that fans out to Python 3.11/3.12 CI and the Docker smoke test using the reusable workflows, then enforces that every leg succeeds.
- Minimal invariant CI (`pr-11-ci-smoke.yml`): lean push/PR workflow that installs the project once on Python 3.11, sanity-checks imports, and executes the invariant tests from Issue #3651 so regressions surface quickly.
- Gate summary (`pr-00-gate.yml` post-CI jobs): integrated post-CI reporting that batches small hygiene fixes, posts Gate summaries, and manages trivial failure remediation using the composite autofix action.
- Agents orchestration (`agents-70-orchestrator.yml` + `reusable-16-agents.yml`): single entry point for Codex readiness, bootstrap, diagnostics, and watchdog sweeps. Use the [Agent task issue template][agent-task-template] (auto-labels `agents` + `agent:codex`) to raise work for Codex; the issue bridge listens for `agent:codex` and hands issues to the orchestrator. Legacy consumer shims remain removed following Issue #2650.
- PR metadata management (`agents-pr-meta.yml`): serializes Codex activation commands and PR body decoration through dedicated jobs that share a concurrency group keyed by PR number. This prevents marker thrash while keeping activation dispatch responsive.
- Agents intake + orchestration (`agents-63-issue-intake.yml`, `agents-70-orchestrator.yml`, `reusable-16-agents.yml`): unified entry point for ChatGPT topic imports and Codex readiness/bridge sweeps. Use the [Agent task issue template][agent-task-template] (auto-labels `agents` + `agent:codex`) to raise work for Codex; the intake workflow handles both label-triggered bridges and manual dispatch while keeping parsing and bridge logic centralised.
- Codex belt automation (`agents-71-codex-belt-dispatcher.yml`, `agents-72-codex-belt-worker.yml`, `agents-73-codex-belt-conveyor.yml`): hands-off conveyor for labelled issues—dispatcher selects `agent:codex` + `status:ready` issues and prepares a `codex/issue-*` branch, worker opens or refreshes the PR with labels/assignees, and conveyor merges after Gate success before re-queuing the dispatcher.
- Cosmetic repair (`maint-45-cosmetic-repair.yml`): manual pytest run plus guardrail fixer that opens labelled repair PRs when drift is detected.
- Governance & Health: `health-40-repo-selfcheck.yml`, `health-41-repo-health.yml`, `health-42-actionlint.yml`, `health-43-ci-signature-guard.yml`, `health-44-gate-branch-protection.yml`, labelers, dependency review, CodeQL.
- Keepalive heartbeat (`maint-keepalive.yml`): twice-daily cron + dispatch workflow that posts a timestamped comment (with run link) to the Ops heartbeat issue using `ACTIONS_BOT_PAT` and fails fast if either the issue variable or PAT is missing.
- Coverage guard (`maint-coverage-guard.yml`): daily cron + dispatch workflow that fetches the latest Gate coverage artifacts, compares them to the configured baseline, and maintains the rolling `[coverage] baseline breach` issue.

### 1.1 Current CI Topology (Issue #2439)
The CI stack now routes every pull request through a single Gate workflow that orchestrates the reusable CI and Docker checks:

| Lane | Workflow(s) | Purpose | Required Status Today | Future Plan |
|------|-------------|---------|-----------------------|-------------|
| Gate orchestrator | `pr-00-gate.yml` job `gate` | Coordinates Python (3.11 + 3.12) and Docker smoke runs, fails fast if any leg fails | Required (`Gate / gate`) | Remains the authoritative CI gate |
| Reusable CI | `reusable-10-ci-python.yml` via `pr-00-gate.yml` | Standard Python toolchain (Black, Ruff, mypy, pytest, coverage upload) used by Gate | Called by Gate | Continue to be the single CI entry point |
| Reusable Docker smoke | `reusable-12-ci-docker.yml` via `pr-00-gate.yml` | Deterministic Docker build and smoke probe | Called by Gate | Continue to be the single Docker entry point |
| Gate summary | `pr-00-gate.yml` post-CI jobs | Integrated reporting that posts Gate summaries, commits small hygiene fixes (success runs), and retries trivial CI failures | Not required | Remains optional |

Legacy wrappers (`pr-10-ci-python.yml`, `pr-12-docker-smoke.yml`) have been removed now that branch protection enforces the Gate job directly.

### 1.2 Naming policy & archive status (Issue #1669)
- Active workflows **must** use one of the WFv1 prefixes: `pr-*`, `maint-*`, `agents-*`, or `reusable-*`. Guard tests (`tests/test_workflow_naming.py`) enforce this policy.
- Historical directories `Old/.github/workflows/` and `.github/workflows/archive/` were removed. Reference [ARCHIVE_WORKFLOWS.md](../../ARCHIVE_WORKFLOWS.md) when you need the legacy slugs.
- New workflows should document their purpose in this README and in [WORKFLOW_AUDIT_TEMP.md](../../WORKFLOW_AUDIT_TEMP.md) so future audits inherit a complete inventory.

Flow:
1. PR opened → labelers apply path + agent labels.
2. Labels / branch rules trigger CI, autofix, readiness.
3. Maintainer approval (CODEOWNERS) → `automerge` merges low-risk.
4. Schedules (health, CodeQL) maintain hygiene.

---
## 2. Label Cheat Sheet

| Label | Purpose | Source |
|-------|---------|--------|
| `agent:codex` / `agent:copilot` | Marks automation-owned issues and PRs | Agent labeler |
| `from:codex` / `from:copilot` | Origin marker for automation PRs | Agent labeler |
| `autofix:clean` | Opt-in label gating Gate summary jobs. Automation also applies `autofix:applied`, `autofix:debt`, `autofix:patch`, and `autofix:clean-only` to describe the outcome. | Gate summary |
| `ci-failure` | Pins the rolling CI dashboard issue | Gate summary |
| Area labels | Scope classification for review routing | Path labeler |

---
## 3. Required Secrets & Variables

| Name | Type | Req | Purpose | Notes |
|------|------|-----|---------|-------|
| `SERVICE_BOT_PAT` | Secret | Rec | Allows automation to push branches and leave comments | `repo` scope |
| `AUTOFIX_OPT_IN_LABEL` | Var | Opt | Overrides the default autofix opt-in label | Defaults to `autofix:clean` |
| `OPS_HEALTH_ISSUE` | Var | Req | Issue number for repo-health updates | Repo health jobs skip updates when unset |

All other jobs rely on the default `GITHUB_TOKEN` permissions noted in the
workflow files.

---
## 4. Trigger Matrix

| Workflow | Trigger(s) | Notes |
|----------|-----------|-------|
| `pr-00-gate.yml` | pull_request, workflow_dispatch | Orchestrates reusable Python 3.11/3.12 CI and Docker smoke tests, then enforces all-success before reporting `gate`.
| `pr-11-ci-smoke.yml` | push (`main`), pull_request (`main`), workflow_dispatch | Minimal invariant sweep that installs the project with dev extras, caches pip dependencies, runs the package import sanity check, and executes `pytest tests/test_invariants.py -q`.
| `health-41-repo-health.yml` | schedule (weekly), workflow_dispatch | Monday hygiene summary of stale branches and unassigned issues.
| `maint-47-disable-legacy-workflows.yml` | workflow_run (`Gate`) | Disables legacy workflows as documented for Maint 47.
| `maint-coverage-guard.yml` | schedule (daily), workflow_dispatch | Soft coverage guard that monitors the latest Gate coverage artifacts and updates the `[coverage] baseline breach` issue.
| `maint-keepalive.yml` | schedule (17 */12 * * *), workflow_dispatch | Posts an Ops heartbeat comment with a UTC timestamp so scheduled runs leave an observable trace.
| `health-40-repo-selfcheck.yml` | schedule (daily + weekly), workflow_dispatch | Governance audit that validates labels, PAT availability, and branch protection; defaults to verify-only mode and escalates to enforce+verify when `BRANCH_PROTECTION_TOKEN` is present while keeping a single failure tracker issue current.
| `health-42-actionlint.yml` | pull_request (workflows), push (`main`), schedule, workflow_dispatch | Workflow schema lint with reviewdog annotations.
| `health-43-ci-signature-guard.yml` | pull_request/push (`main`) | Validates the signed job manifest for `pr-00-gate.yml`.
| `agents-63-issue-intake.yml` | issues, workflow_dispatch, workflow_call | Canonical intake workflow that normalizes ChatGPT topic lists and bridges `agent:codex` issues into the orchestrator. |
| `maint-45-cosmetic-repair.yml` | workflow_dispatch | Manual pytest + cosmetic fixer that raises guard-gated PRs for tolerated drift. |
| `agents-71-codex-belt-dispatcher.yml` | schedule (*/30), workflow_dispatch | Picks the next `agent:codex` + `status:ready` issue, prepares the `codex/issue-*` branch, and dispatches the worker. |
| `agents-72-codex-belt-worker.yml` | repository_dispatch (`codex-belt.work`), workflow_dispatch | Validates the queued issue, updates labels/assignees, and opens or refreshes the Codex automation PR. |
| `agents-73-codex-belt-conveyor.yml` | workflow_run (`Gate`, completed) | Squash-merges successful `codex/issue-*` PRs after Gate, deletes the branch, closes the source issue, and re-triggers the dispatcher. |
| `agents-70-orchestrator.yml` | schedule (*/20), workflow_dispatch | Unified agents toolkit entry point delegating to `reusable-16-agents.yml`. |
| `reusable-16-agents.yml` | workflow_call | Composite implementing readiness, bootstrap, diagnostics, and watchdog jobs. |
| `reusable-10-ci-python.yml` | workflow_call | Unified CI executor for the Python stack. |
| `reusable-12-ci-docker.yml` | workflow_call | Docker smoke reusable consumed by `pr-00-gate.yml`. |
| `reusable-18-autofix.yml` | workflow_call | Autofix composite consumed by Gate summary jobs. |

---
## 5. Adopt Reusable Workflows

CI consumer example:

```yaml
name: CI
on:
  workflow_call:
    inputs:
      marker:
        type: string
        default: "not quarantine and not slow"
      python-version:
        type: string
        default: "3.12"
jobs:
  ci:
    uses: stranske/Trend_Model_Project/.github/workflows/reusable-10-ci-python.yml@main
    with:
      marker: ${{ inputs.marker }}
      python-version: ${{ inputs["python-version"] }}
```
Autofix commits use the configurable prefix (default `chore(autofix):`). Set the repository variable
`AUTOFIX_COMMIT_PREFIX` to change the prefix once and every workflow picks up the new value. The
consolidated Gate workflow consumes the same reusable entry points, so any new repository can call
`reusable-10-ci-python.yml` and `reusable-12-ci-docker.yml` directly without needing an intermediate wrapper.

When `ACTIONS_BOT_PAT` is unavailable or the pull request originates from a fork, the reusable
autofix workflow automatically switches to a patch-only fallback that relies on `GITHUB_TOKEN`,
uploads `autofix-patch-pr-<PR>` artifacts, and records the delivery path in the PR status comment
so maintainers know where to fetch the fix.

```yaml
name: Agents utilities
on:
  workflow_dispatch:
jobs:
  call:
    uses: stranske/Trend_Model_Project/.github/workflows/reusable-16-agents.yml@main
    with:
      enable_readiness: true
      enable_preflight: true
      enable_watchdog: true
      enable_diagnostic: false
```
Use a tagged ref when versioned.

### Agents Orchestration (Issue #2615)
Issue #2615 finishes the topology cleanup: **Agents 70 Orchestrator is now the
only automation entry point.** All Codex work should begin with an [Agent task
issue][agent-task-template]. The template pre-applies the `agents` and
`agent:codex` labels so the bridge workflow can prepare a branch/PR as soon as
the issue is ready.

The lifecycle is:

1. Create an issue via the Agent task template and capture background, goals,
   and guardrails.
2. Once the issue is labelled `agent:codex`, `agents-63-codex-issue-bridge.yml`
   opens or refreshes the automation branch/PR and posts the boilerplate
   `@codex start` comment when configured.
3. `agents-70-orchestrator.yml` (cron or manual dispatch) runs the readiness /
   bootstrap pipeline through `reusable-16-agents.yml`, honouring the PR and
   verification settings returned by the bridge.

Manual dispatches pass their toggles directly to the orchestrator. Use the
`options_json` field for advanced overrides:

```json
{
  "enable_bootstrap": true,
  "bootstrap": { "label": "agent:codex" },
  "diagnostic_mode": "dry-run",
  "require_all": true
}
```

Omit keys to accept defaults. `enable_bootstrap` controls Codex branch/PR
creation, and the nested `bootstrap.label` lets you target alternate label
queues if needed. Keep `enable_keepalive` disabled unless a sweep is required.

The guard test `tests/test_workflow_agents_consolidation.py` enforces the
single-entry topology and ensures documentation references remain in sync with
the orchestrator inputs.

### Cosmetic Repair (Maint 45)
`maint-45-cosmetic-repair.yml` is the manual guardrail fixer that partners with Post CI. It exists for maintainers to re-run the pytest suite, apply formatting or low-risk hygiene patches via `scripts/ci_cosmetic_repair.py`, and open a labelled follow-up PR when drift is detected.

Key traits:
1. Triggered manually through `workflow_dispatch` and inherits repository write permissions so it can push repair branches.
2. Accepts inputs for base branch, Python version, dry-run toggles, and branch suffix to coordinate parallel repair attempts.
3. Runs pytest in allow-fail mode to surface current failures before executing the cosmetic fixer.
4. Uses the same cosmetic repair helper consumed by the autofix follower, ensuring identical formatting rules across automated and manual flows.
5. Captures repair summaries and emits outputs that downstream tooling (like Gate summary jobs) can render in job summaries.

Guardrails: `tests/test_workflow_naming.py` asserts the workflow remains in the inventory, and the repair helper’s behaviour is covered by tests for `scripts/ci_cosmetic_repair.py`.

---
## 6. Onboarding Checklist (~7m)
1. Create labels `automerge`, `risk:low`, `agent:codex`, `agent:copilot`, `codex-ready`.
2. Add area labels.
3. Add `SERVICE_BOT_PAT` or set `CODEX_ALLOW_FALLBACK=true` (temporary).
4. Ensure Actions write permission.
5. Add CI / Autofix / Agents consumers.
6. Open dummy PR → verify labels.
7. Dispatch readiness.

---
## 7. Troubleshooting
| Symptom | Cause | Ref |
|---------|-------|-----|
| No labels | Labeler/perms missing | `pr-02-label-agent-prs.yml` |
| Bootstrap blocked | PAT missing & fallback off | troubleshooting doc |
| Autofix skipped | Title match / opt-in absent | Autofix README |
| No dependency review | Fork PR / disabled | `pr-31-dependency-review.yml` |
| No CodeQL alerts | First run indexing | `pr-30-codeql.yml` |

### 7.1 Autofix Loop Guard (Issue #1347)
Loop prevention layers:
1. The consolidated workflow only reacts to completed CI runs (no direct `push` trigger).
2. Guard logic only fires when the workflow actor is `github-actions` (or `github-actions[bot]`) **and** the latest commit subject begins with the standardized prefix `chore(autofix):`.
3. Scheduled cleanup (`maint-31-autofix-residual-cleanup.yml`) and reusable autofix consumers adopt the same prefix + actor guard, so automation commits short-circuit immediately instead of chaining runs.
4. The CI style job runs independently and does not trigger autofix.

Result: Each human push generates at most one autofix patch sequence; autofix commits do not recursively spawn new runs.

---
## 7.2 Codex Kickoff Flow (Issue #1351)
End‑to‑end lifecycle for automation bootstrapped contributions:
1. Maintainer opens Issue with label `codex-ready` (and optional spec details).
2. Labeling with `agent:codex` triggers `agents-41-assign.yml`, which creates a bootstrap branch/PR, assigns Codex, and posts the kickoff command.
3. `agents-42-watchdog.yml` (dispatched by the assigner) waits ~7 minutes for the cross-referenced PR and posts a success or timeout diagnostic comment.
4. When automation pushes commits, path labelers, CI, and autofix re-evaluate.
Troubleshooting: If branch/PR not created, verify the label `codex-ready`, confirm `agents-41-assign.yml` completed successfully with write permissions, and ensure no conflicting bootstrap branch already exists.

---
## 7.3 Coverage Soft Gate (Issues #1351, #1352)
Purpose: Provide early visibility of coverage / hotspot data without failing PRs.


Low Coverage Spotlight (follow-up Issue #1386):
- A secondary table "Low Coverage (<X%)" appears when any parsed file has coverage below the configured threshold (default 50%).
- Customize the threshold with the `low-coverage-threshold` workflow input when calling `reusable-10-ci-python.yml`.
- Table is separately truncated to the hotspot limit (15) with a truncation notice if more remain.
Implemented follow-ups (Issue #1352):
- Normalized artifact naming: `coverage-<python-version>` (e.g. `coverage-3.11`).
- Consistent file set per matrix job: `coverage.xml`, `coverage.json`, `htmlcov/**`, `pytest-junit.xml`, `pytest-report.xml`.
- Retention window input `coverage-artifact-retention-days` has a default value of 10.
  This default is chosen to fall within the recommended 7–14 day observation horizon, allowing reviewers to compare multiple consecutive runs without long-term storage bloat.
  Adjust as needed; it is suggested to keep the retention window within 7–14 days unless you are auditing longer-term trends.
- Single canonical coverage tracking issue auto-updated with summary + hotspots + job log links.
- Run Summary includes a single "Soft Coverage Gate" section (job log table de-duplicated into universal logs job).
- Trend artifacts shipped: `coverage-trend.json` (single run) and cumulative `coverage-trend-history.ndjson` (history) for longitudinal analysis.

Activation (consumer of `reusable-10-ci-python.yml`):
```yaml
with:
  enable-soft-gate: 'true'
```
Outputs:
- Run Summary section: "Soft Coverage Gate" with average coverage (across matrix), worst job, and top 15 lowest-covered files (hotspots).
- Artifacts (per Python version): `coverage-<ver>` bundle (xml/json/htmlcov + JUnit variants) retained N days (default 10).
- Aggregated artifacts: `coverage-trend` (JSON for this run), `coverage-trend-history` (NDJSON accumulating all runs).
- Canonical coverage Issue comment (create-or-update) containing run link, summary, hotspots, and job log links (deduped from summary table).

### Agents Orchestration (Issue #2466)

---
## 7.4 Selftest: Reusables & Reusable CI

### Consolidated runner (Issue #2651 & Issue #2814 refresh)

- **Entry point:** Dispatch **Selftest: Reusables** (`.github/workflows/selftest-reusable-ci.yml`) from the Actions tab when you need a
  comment, workflow summary, or dual-runtime verification. The workflow also runs on a nightly cron (06:30 UTC); only PR and push
  triggers remain disabled after consolidation.
- **Inputs:**
  - `mode` — `summary`, `comment`, or `dual-runtime`. Summary posts only to the workflow run, comment publishes to a PR, and
    dual-runtime fans out to both Python 3.11 and 3.12 before surfacing a summary.
  - `post_to` — `none` or `pr-number`. When paired with `mode: comment`, supply `pull_request_number` so the runner knows where
    to post. The workflow validates the number and fails fast on bad input rather than silently skipping the comment.
  - `enable_history` — toggle to download the `selftest-report` artifact emitted by the reusable matrix. Leave disabled for a
    lightweight run; enable it when you need the JSON report locally.
  - Optional niceties: `reason`, `summary_title`, and `comment_title`. The `reason` field is optional but recommended for audit
    breadcrumbs. Defaults keep the previous wrappers’ headings for familiarity.
- **Behavioural guardrails:** Both the log-surface step and the PR-comment finaliser fail the job when verification outputs are
  missing or mismatched. This keeps “unknown” outcomes from sneaking through when the reusable matrix changes. The workflow also
  respects the matrix result—any upstream failure bubbles up as an error after the report is posted.
- **Comment lifecycle:** When `mode: comment` and `post_to: pr-number`, the workflow updates an existing comment marked with
  `<!-- selftest-reusable-comment -->` or creates a new one. Manual reruns therefore refresh the same comment instead of spamming
  reviewers.
- **CLI snippet:**

  ```bash
  gh workflow run "Selftest: Reusables" \
    --raw-field mode=comment \
    --raw-field post_to=pr-number \
    --raw-field pull_request_number=1234 \
    --raw-field enable_history=true
  ```

  The CLI automatically prompts for the branch/ref; omit `pull_request_number` (or set `post_to=none`) when you only need the
  workflow summary.

### Nightly verification (Issue #1660 follow-up)

- **Trigger scope:** The nightly cron (06:30 UTC) exercises the full scenario matrix using the runner’s summary mode. Manual
  `workflow_dispatch` invocations share the same path so maintainers can rehearse changes to
  `.github/workflows/reusable-10-ci-python.yml` or its helpers.
- **Diagnostics:** Each run uploads a `selftest-report` artifact summarising expected vs actual artifacts. Use it alongside the
  job logs to validate reusable updates before promoting changes.
- **Failure triage workflow:** When a run fails, download diagnostics with the GitHub CLI:

  ```bash
  gh run download <run-id> --dir selftest-artifacts
  gh run view <run-id> --log
  ```

  Inspect `selftest-artifacts/selftest-report/selftest-report.json` for mismatched artifacts and reproduce dependency drift
  issues locally or validate fixes with `pytest tests/test_lockfile_consistency.py -k "up_to_date" -q`.
## 7.5 Universal Logs Summary (Issue #1351)
Source: `logs_summary` job inside `reusable-10-ci-python.yml` enumerates all jobs via the Actions API and writes a Markdown table to the run summary. Columns include Job, Status (emoji), Duration, and Log link.

How to access logs:
1. Open the PR → Checks tab → select the CI run.
2. Scroll to the Run Summary table; click the log link for any job.
3. Fallback: Use the GitHub UI Jobs list if the summary table is missing.

If missing:
- Confirm the `logs_summary` job executed (it is unconditional). If skipped, check for GitHub API rate limits in its step logs.

---
## 7.6 Gate-Only Protection (Issue #2439)
Branch protection now requires the `Gate / gate` job directly. The historical wrappers have been removed and all automation listens to the Gate workflow via `workflow_run` triggers. No further action is required beyond keeping the reusable workflows healthy.

---
## 7.7 Quick Reference – Coverage & Logs
| Concern | Job / File | How to Enable | Artifact / Output | Fails Build? |
|---------|------------|---------------|-------------------|--------------|
| Coverage soft gate | Job: `coverage_soft_gate` in `reusable-10-ci-python.yml` | `enable-soft-gate: 'true'` | Run summary section, coverage artifacts | No |
| Universal logs table | Job: `logs_summary` | Always on | Run summary Markdown table | No |
| Gate aggregation | Job: `gate` in `pr-00-gate.yml` | Always on | Single pass/fail gate | Yes (required) |

Note: The gate job will become the only required status after successful observation window.


---
## 8. Extensibility
- Add quarantine job via new inputs.
- Tune dependency severity gating.
- Tag releases for stable reuse.

1. Navigate to **Actions → Agents 70 Orchestrator → Run workflow**.
2. Provide the desired inputs (e.g. `enable_bootstrap: true`,
   `bootstrap_issues_label: agent:codex`, `options_json` overrides).
3. Review the `orchestrate` job summary for readiness tables, bootstrap
   planners, watchdog status, and keepalive signals.
4. Rerun as needed; Gate summary jobs will echo failing runs in the `ci-failure`
   rollup when Gate is affected.

`reusable-16-agents.yml` remains the single implementation surface for readiness
probes, diagnostics, bootstrap, keepalive, and watchdog jobs. `reuse-agents.yml`
exists for workflow-call reuse so downstream repositories can adopt the same
inputs without duplicating JSON parsing.

---
## 6. Onboarding Checklist (~7 min)

1. Confirm labels `agent:codex`, `agent:copilot`, `autofix`, and `ci-failure`
   exist.
2. Verify repository variables (`OPS_HEALTH_ISSUE`, optional
   `AUTOFIX_OPT_IN_LABEL`) are set.
3. Review Gate and its integrated summary jobs on a recent PR to familiarise yourself
   with the consolidated reporting.
4. Trigger a manual Agents 70 Orchestrator run in dry-run mode (`enable_bootstrap`
   false) to observe readiness output and ensure secrets resolve.
5. Consult `docs/ci/WORKFLOWS.md` for the authoritative workflow roster before
   adding or renaming jobs.

---
## 7. Retired Wrappers

- `agents-consumer.yml`, `agents-41*`, and `agents-42-watchdog.yml` were removed
  during the consolidation. Historical payload examples now live in
  `Old/workflows/` and the repository archive docs.
- `pr-10-ci-python.yml`, `pr-12-docker-smoke.yml`, and the merge-manager flows
  remain archived in `ARCHIVE_WORKFLOWS.md`.

Refer to the archive if you need to resurrect behaviour for forensic analysis;
otherwise, prefer the consolidated orchestrator and reusable workflows.

[agent-task-template]: https://github.com/stranske/Trend_Model_Project/issues/new?template=agent_task.yml
