# Maintenance Workflow Review — 2026-02-22

This log mirrors the health-workflow audit but targets the `maint-*` workflows. Each entry captures the current trigger model, purpose, optimizations, and any follow-up actions so we can track progress while iterating on the maintenance suite.

## Workflow Notes

### `maint-39-test-llm-providers.yml`
- **Purpose**: Manual dispatch harness that sanity-checks GitHub Models and OpenAI provider keys through `tools.llm_provider` helpers before running keepalive or agent updates.
- **Optimizations applied (2026-02-22)**: Dropped the unnecessary GitHub App token mint + checkout override, since the workflow only runs standalone provider checks and never calls the GitHub API directly. This keeps the manual test lightweight and avoids consuming app credentials just to read the repo.
- **Next steps**: Consider extending the summary step to reflect which providers were exercised (and why a provider was skipped) instead of always reporting success.

### `maint-45-cosmetic-repair.yml`
- **Purpose**: Manual pytest + hygiene runner that executes `scripts/ci_cosmetic_repair.py` to auto-fix formatting-only failures and open a helper PR when changes exist.
- **Optimizations applied (2026-02-22)**:
  - Removed the redundant GitHub App token mint + checkout override; the workflow already has `contents:write` and only needs the default token to push the cosmetic branch, so skipping the mint drops an API call from every run.
  - Guarded the PR-creation step behind `dry-run != true` so exploratory runs don't waste time/requests trying to open a no-op helper PR.
- **Next steps**: Extend the run summary to include whether pytest failed and whether fixes were applied so dispatchers know if a manual follow-up is still required.

### `maint-46-post-ci.yml`
- **Purpose**: Gate follower that rebuilds/post the coverage + CI summary whenever the Gate run's own summary leg fails or is missing, then reapplies the commit status.
- **Optimizations applied (2026-02-22)**:
  - Removed the unconditional GitHub App token mint plus the always-on checkout; the workflow now inspects the Gate summary first and only checks out helper scripts if recovery is actually required.
  - Moved the `setup-api-client` install behind the same condition so we only install Octokit dependencies and load-balance additional tokens when there is real recovery work to do.
- **Next steps**: Hook the coverage artifact download into `run-id` detection for other required workflows so Maint 46 can heal more than just Gate summaries.

### `maint-47-disable-legacy-workflows.yml`
- **Purpose**: Manual dispatch shim that disables legacy workflows left in the Actions UI after archival, with dry-run and allowlist overrides.
- **Optimizations applied (2026-02-22)**: Removed the redundant GitHub App token mint. The helper script only reads repository files plus the default installation token for API writes, so minting a separate App token wasted an API call without providing extra capabilities.
- **Next steps**: Flesh out `tools/disable_legacy_workflows.py` so it actually hits the Actions REST API before re-enabling automatic disablement.

### `maint-50-tool-version-check.yml`
- **Purpose**: Weekly/manual audit that reads `autofix-versions.env`, hits PyPI for the latest formatter/test tool versions, and opens/refreshes the maintenance issue when drift exists.
- **Optimizations applied (2026-02-22)**:
  - Removed the redundant GitHub App token mint + duplicate sparse checkout; the workflow now relies on the default token and the existing `setup-api-client` load balancer for issue API traffic.
  - Simplified the GitHub Script invocation to use one checkout, keeping the repo workspace hot for both the Python env file and helper scripts.
- **Next steps**: Cache the PyPI JSON responses (or add timeouts/backoffs) so transient PyPI outages don't fail the entire run.

### `maint-51-dependency-refresh.yml`
- **Purpose**: Twice-monthly/manual dependency refresh that compiles `requirements.lock`, verifies tool pins, and (when not in dry-run) opens a helper PR with the refreshed snapshot.
- **Optimizations applied (2026-02-22)**: Removed the GitHub App token mint + checkout override so the workflow now reuses the default workflow token for both checkout and the PR helper (the run already needs `fetch-depth: 0` for branch pushes).
- **Next steps**: Capture the normalized compile output during the upgrade step so the verification leg can diff against a temp file instead of running `uv pip compile` twice.

### `maint-52-sync-dev-versions.yml`
- **Purpose**: Keeps consumer repos' dev-tool pins aligned with `autofix-versions.env` by verifying versions, building a repo matrix, and pushing PRs via PAT-backed clones.
- **Optimizations applied (2026-02-22)**:
  - Dropped all GitHub App token mint steps; the workflow now relies on the existing PAT inputs (`OWNER_PR_PAT`/`SERVICE_BOT_PAT`) and the default token for read-only operations.
  - Replaced the inline YAML parsing logic with the shared `scripts/list_registered_consumer_repos.py` helper so repo discovery stays consistent with other health/maint workflows.
- **Next steps**: Emit a structured run summary that lists which repos were updated vs. skipped (pyproject missing) to make dry-run reviews faster.

### `maint-52-validate-workflows.yml`
- **Purpose**: Push/PR workflow that parses all workflow files with `yq` and runs `actionlint` with the repo allowlist to prevent syntax errors from landing.
- **Optimizations applied (2026-02-22)**: Removed the unnecessary GitHub App token mint and `GITHUB_TOKEN` override for actionlint; the job only reads repository files, so minting an app token wasted an API call each run.
- **Next steps**: Consider running actionlint directly via the reusable composite under `health-42` to share caching/configuration code.

### `maint-60-release.yml`
- **Purpose**: Creates GitHub Releases whenever a `v*` tag lands and, for `v1.*` tags, refreshes the floating `v1` branch pointer.
- **Optimizations applied (2026-02-22)**: Removed the redundant GitHub App token mint + checkout override; the workflow only needs the default token to update floating tags and publish releases via `softprops/action-gh-release`.
- **Next steps**: Add a sanity guard so floating-tag updates only run when the push originated from this repo (not forks) to avoid surprise ref moves.

### `maint-61-create-floating-v1-tag.yml`
- **Purpose**: Legacy manual fallback for updating the floating `v1` tag; superseded by `maint-73-refresh-reusable-tags.yml`.
- **Optimizations applied (2026-02-22)**: Removed the unused GitHub App token mint—the step only ever checked out the repo before calling `scripts/update-floating-tag.sh`, so the default workflow token is sufficient.
- **Next steps**: Archive this workflow after confirming maint-73 has fully replaced it (or wire it to fail-fast with a deprecated notice so no one runs it by mistake).

### `maint-62-integration-consumer.yml`
- **Purpose**: Runs the integration-consumer scenarios via `reusable-10-ci-python.yml` and opens/closes the `integration-test` issue when failures occur.
- **Optimizations applied (2026-02-22)**: Removed the redundant GitHub App token mint; the job already installs the full API client + token load balancer, so minting an extra token for the helper checkout provided no benefit.
- **Next steps**: Inline the summary step into the GitHub Script output so issue updates include direct links to the failed matrix leg.

### `maint-65-sync-label-docs.yml`
- **Purpose**: Pushes the canonical consumer guide at `templates/consumer-repo/docs/LABELS.md` into every consumer repo plus Workflows-Integration-Tests whenever that source changes (or on manual dispatch).
- **Optimizations applied (2026-02-22)**:
  - Removed the needless GitHub App token mint; the workflow now just checks out the needed files and relies on PATs for cross-repo pushes.
  - Reused `scripts/list_registered_consumer_repos.py` so repo discovery stays centralized instead of re-parsing YAML inline.
- **Next steps**: Capture per-repo sync results and include them in the summary table to make dry-run validation faster.

### `maint-66-monthly-audit.yml`
- **Purpose**: Monthly workflow that scans workflow runs, highlights failures, runs the API wrapper guard, and files/updates the `workflow-audit` issue with a checklist.
- **Optimizations applied (2026-02-22)**: Removed the redundant GitHub App token mint and the manual `npm install` of Octokit packages; the shared API client already installs and balances tokens for the audit scripts.
- **Next steps**: Cache the workflow run JSON so multiple audit reruns in the same day don't hammer the Actions API.

### `maint-68-sync-consumer-repos.yml`
- **Purpose**: Manifest-driven sync engine that validates templates/scripts, then pushes PRs to every registered consumer repository with the latest workflows, prompts, scripts, and docs.
- **Optimizations applied (2026-02-22)**: Removed all GitHub App token mint steps; the workflow already uses PATs for repo pushes and the load-balanced API client for GitHub calls, so minting extra tokens only added latency.
- **Next steps**: Move `REGISTERED_CONSUMER_REPOS` into the manifest helper so repo additions only need to land in one place.

### `maint-69-sync-integration-repo.yml`
- **Purpose**: Syncs the integration test repository with template workflows/scripts and regenerates requirements to keep CI parity.
- **Optimizations applied (2026-02-22)**: Removed the GitHub App token mint so the workflow just checks out templates with the default token (PAT handles pushes to the integration repo).
- **Next steps**: Capture the files touched in the run summary so dry-run previews don't require digging through raw logs.

### `maint-69-sync-labels.yml`
- **Purpose**: Pushes the required `labels-core.yml` set into all consumer repos so workflows have the expected triggers/markers.
- **Optimizations applied (2026-02-22)**:
  - Dropped the GitHub App token mint + duplicate checkout; the workflow now performs a single checkout and uses the shared API client for retries.
  - Replaced the inline repo-list parser with `scripts/list_registered_consumer_repos.py` so consumer roster changes propagate automatically.
- **Next steps**: Extend the run summary to list which repos were updated vs. skipped when running in dry-run mode.

### `maint-70-fix-integration-formatting.yml`
- **Purpose**: Manual formatter that applies `black`/`ruff` fixes to Workflows-Integration-Tests when its CI fails due to styling drift.
- **Optimizations applied (2026-02-22)**: Uses the shared API client + PAT discovery instead of minting an App token, and skips the entire clone/fix flow when no PAT is available (updating the summary accordingly).
- **Next steps**: Detect which files were changed and include them in the run summary for faster follow-up reviews.

### `maint-71-auto-fix-integration.yml`
- **Purpose**: Watches “Integration CI failed” issues/comments and automatically reruns the formatting routine against Workflows-Integration-Tests when the latest run concluded as failure.
- **Optimizations applied (2026-02-22)**: Dropped the App token mint + ad-hoc Octokit install; the job now reuses the shared API client and explicitly discovers PAT availability, skipping clone/push work (with a summary notice) when no PAT is configured.
- **Next steps**: Consider auto-closing the source issue when the follow-up run passes to keep the queue tidy.

### `maint-71-merge-sync-prs.yml`
- **Purpose**: Closes stale sync PRs and merges the latest passing sync PR in each consumer repo.
- **Optimizations applied (2026-02-22)**: Removed the GitHub App token mint, switched to the shared API client, and now rely on `scripts/list_registered_consumer_repos.py` so repo discovery stays centralized.
- **Current credential contract (2026-08-15)**: Maint 71 requires `OWNER_PR_PAT` for every reconciliation mode and fails closed when that owner-scoped credential is missing, invalid, or exhausted; service/default-token fallback is not supported for fleet reads or mutations.
- **Next steps**: Surface per-repo merge outcomes in the run summary for quicker triage.

### `maint-72-fix-pr-body-conflicts.yml`
- **Purpose**: Weekly/manual cleanup that deletes stray `pr_body.md` files and enforces `.gitignore` entries across every consumer repo.
- **Optimizations applied (2026-02-22)**: Replaced the inline repo-list parser with `scripts/list_registered_consumer_repos.py`, removed the GitHub App token mint, and added PAT detection so the job skips (with a warning) whenever no push-capable PAT is available.
- **Next steps**: Add a run summary table listing repos cleaned vs. skipped to simplify follow-up.

### `maint-73-refresh-reusable-tags.yml`
- **Purpose**: Formerly ensured floating `v*` tags stayed aligned with `main`; now deprecated because repos consume `@main` directly.
- **Optimizations applied (2026-02-22)**: Replaced the full tag-refresh logic with a single skip step so the workflow exits immediately with a notice instead of minting tokens and running git commands.
- **Next steps**: Remove the workflow entirely once all references are confirmed dead.

### `maint-74-ledger-base-sync.yml`
- **Purpose**: Runs `scripts/ledger_migrate_base.py` to realign `.agents` ledger base entries with the default branch and opens a helper PR when changes exist.
- **Optimizations applied (2026-02-22)**: Removed the GitHub App token mint; the workflow already uses the shared API client + default token for repo operations, so the extra mint was redundant.
- **Next steps**: Include a summary of which ledgers changed to speed up PR reviews.

### `maint-80-langsmith-metrics-dashboard.yml`
- **Purpose**: Weekly/manual LangSmith trace coverage roll-up that scrapes recent `agents-auto-pilot` artifacts, aggregates metrics, uploads a combined report, and refreshes `docs/dashboards/langsmith-metrics.md`.
- **Notes (2026-02-22)**: Workflow already scopes API usage to the default token + `gh` CLI, generates artifacts, and supports manual reruns. No code changes required during this pass; documentation captures current behavior for traceability.

### `maint-auto-update-pypi-versions.yml`
- **Purpose**: Daily automation that checks PyPI via `scripts/update_versions_from_pypi.py`, updates `autofix-versions.env`, regenerates supporting files, and opens a helper PR when new tool versions exist.
- **Optimizations applied (2026-02-22)**: Removed the unnecessary GitHub App token mint; the workflow uses the default installation token + PAT for pushes, so the extra mint was redundant.
- **Next steps**: Surface the updated versions (tool → old → new) in the PR body without relying on raw script output.

### `maint-coverage-guard.yml`
- **Purpose**: Runs the coverage baseline monitor after Gate, with a rate-limit gate that defers when API quota is low.
- **Optimizations applied (2026-02-22)**: Removed the redundant GitHub App token mint from both the gate and guard jobs; both already use the shared API client and installation token for API calls.
- **Next steps**: Consider persisting historical coverage metrics to compare against prior weeks automatically.

### `maint-auto-label-dep-prs.yml`

- **Purpose**: Adds `agents:allow-change` to dependency-bot PRs so automation workflows can touch them.
- **Notes (2026-02-22)**: Workflow is already minimal (pure `gh pr edit` with the default token); no changes required.

### `maint-auto-lock-deps.yml`

- **Purpose**: When a dependency bot updates lock inputs, this job regenerates `requirements.lock` with `uv` and pushes the update back to the PR branch.
- **Notes (2026-02-22)**: Process already uses the default token, a single checkout, and targeted `uv` commands—no adjustments needed this pass.

### `maint-dependabot-weekly-sweep.yml`

- **Purpose**: Retired weekly automation that scanned consumer repos for open Dependabot PRs and auto-merged them when checks passed.
- **Retirement note**: The workflow was removed when the repo moved to bot-agnostic dependency handling; queue visibility now lives in the Sync/Dependabot campaign surfaces.

### `maint-sync-env-from-pyproject.yml`
- **Purpose**: Keeps `.github/workflows/autofix-versions.env` aligned with `pyproject.toml` whenever main receives dependency updates.
- **Optimizations applied (2026-02-22)**: Removed the redundant GitHub App token mint; the workflow commits directly to main with the default token.
- **Next steps**: Deduplicate the inline TOML parsing with `scripts/update_versions_from_pypi.py` to avoid two separate parsers.

### `maint-sync-action-versions.yml`
- **Purpose**: Scans `.github/workflows/*.yml` for action pins and syncs them into the template workflows via an automated PR.
- **Notes (2026-02-22)**: Already uses the shared API client, a single checkout, and scoped sed updates; no changes required this pass.
