# Workflow Topology & Agent Routing Guide (WFv1)

This guide describes the slimmed-down GitHub Actions footprint after Issues #2190 and #2466. Every workflow now follows the
`<area>-<NN>-<slug>.yml` naming convention with 10-point number gaps so future additions slot in cleanly. The Gate workflow
remains the required merge check, while **Agents 70 Orchestrator** continues to drive readiness/bootstrap and the
**Agents 71–73 Codex Belt** automates the queue → branch → PR → merge conveyor for labeled Codex issues. For the executive
summary of buckets, required checks, and automation roles, begin with
[docs/ci/WORKFLOW_SYSTEM.md](ci/WORKFLOW_SYSTEM.md) before diving into the topology details below.

If you need the quick roster of which workflows stay active, which ones retired, and the policy guardrails that bind them,
start with the high-level [Workflow System Overview](ci/WORKFLOW_SYSTEM.md). This guide then dives into naming, routing, and
operational detail for the kept set.

> _Gate rerun trigger:_ this paragraph was touched on 2025-10-13 to force a fresh Gate workflow execution.

## WFv1 Naming Scheme

| Prefix | Purpose | Active Examples |
| ------ | ------- | ---------------- |
| `pr-` | Pull-request CI wrappers | `pr-00-gate.yml`, `pr-11-ci-smoke.yml` |
| `maint-` | Post-CI maintenance and self-tests | `maint-45-cosmetic-repair.yml`, `maint-46-post-ci.yml`, `maint-47-disable-legacy-workflows.yml`, `maint-50-tool-version-check.yml`, `maint-52-validate-workflows.yml`, `maint-60-release.yml`, `maint-61-release-please.yml`, `maint-coverage-guard.yml` |
| `health-` | Repository health & policy checks | `health-40-sweep.yml`, `health-40-repo-selfcheck.yml`, `health-41-repo-health.yml`, `health-42-actionlint.yml`, `health-43-ci-signature-guard.yml`, `health-44-gate-branch-protection.yml`, `health-50-security-scan.yml` |
| `agents-` | Agent orchestration entry points | `agents-63-issue-intake.yml`, `agents-64-verify-agent-assignment.yml`, `agents-70-orchestrator.yml`, `agents-71-codex-belt-dispatcher.yml`, `agents-72-codex-belt-worker.yml`, `agents-73-codex-belt-conveyor.yml`, `agents-80-pr-event-hub.yml`, `agents-81-gate-followups.yml`, `agents-guard.yml`, `agents-pr-meta.yml`, `agents-moderate-connector.yml`, `agents-keepalive-*.yml`, `agents-debug-issue-event.yml` |
| `reusable-` | Reusable composites invoked by other workflows | `reusable-10-ci-python.yml`, `reusable-12-ci-docker.yml`, `reusable-13-cross-repo-smoke.yml`, `reusable-16-agents.yml`, `reusable-18-autofix.yml`, `reusable-agents-issue-bridge.yml` |
| `selftest-` | Manual self-tests & experiments | `selftest-reusable-ci.yml` |
| `autofix.yml` | CI autofix loop | `autofix.yml` |

**Naming checklist**
1. Choose the correct prefix for the workflow's scope.
2. Select a two-digit block that leaves room for future additions (e.g. use another `maint-3x` slot for maintenance jobs).
3. Title-case the workflow name so it matches the filename (`maint-45-cosmetic-repair.yml` → `Maint 45 Cosmetic Repair`).
4. Update this guide, `docs/ci/WORKFLOWS.md`, and the overview in `docs/ci/WORKFLOW_SYSTEM.md` whenever workflows are added,
   renamed, or removed.

Tests under `tests/test_workflow_naming.py` enforce the naming policy and inventory parity.

## Final Workflow Set

The active roster below mirrors the **Keep** list in the [Workflow System Overview](ci/WORKFLOW_SYSTEM.md). Each entry links back to the filenames under `.github/workflows/` and should be reflected in `docs/ci/WORKFLOWS.md` and the unit tests whenever the inventory changes.

### PR Checks
- **`pr-00-gate.yml`** — Required orchestrator that calls the reusable Python (3.12/3.13), reusable-workflow docs guard, and Docker smoke workflows, then fails fast if any leg does not succeed. A lightweight `detect_doc_only` job mirrors the former PR‑14 filters (Markdown, `docs/`, `assets/`) to skip heavy legs and post the friendly notice when a PR is documentation-only, while the cheap docs guard still checks Workflows reusable input/output documentation.
- **`pr-11-ci-smoke.yml`** — Minimal invariant CI that runs on push/PR to phase-2-dev and main. Installs the project, validates imports, and runs `pytest tests/test_invariants.py` for fast regression detection; the checkout now relies on the default workflow token since the job never leaves the repository.

_Inline Gate helper_
- **Gate summary job (`pr-00-gate.yml`)** — Post-CI job that downloads artifacts, computes coverage deltas, runs the label-gated autofix routine, and updates the PR summary comment with a stable marker.

### Maintenance & Repo Health
- **`maint-39-test-llm-providers.yml`** — Manual dispatch harness to smoke-test GitHub Models and OpenAI credentials via `tools.llm_provider` before other maintenance runs; the workflow now avoids minting redundant GitHub App tokens so the test stays lightweight.
- **`maint-45-cosmetic-repair.yml`** — Manual dispatch utility that runs `pytest -q`, applies guard-gated cosmetic fixes via `scripts/ci_cosmetic_repair.py`, and (when not in dry-run mode) opens a labelled PR with the default workflow token—no extra GitHub App mint required.
- **`maint-46-post-ci.yml`** — Post-CI recovery watcher triggered by `workflow_run` on Gate completion. It inspects the Gate summary job before touching the repo, and only checks out helpers / installs the token-balanced API client when the summary leg actually failed, keeping the default token pool free unless recovery is required.
- **`maint-47-disable-legacy-workflows.yml`** — Manual dispatch utility to disable retired workflows that still appear in the Actions UI (with a dry-run preview + allowlist overrides); now relies solely on the default workflow token because the helper script never leaves the repository.
- **`maint-50-tool-version-check.yml`** — Weekly/manual tool-version audit that reads `autofix-versions.env`, hits PyPI to detect drifts, and files/refreshes the maintenance issue via the default token + load-balanced helper (no extra App mint).
- **`maint-52-sync-dev-versions.yml`** — Fans out to each registered consumer repo (or a supplied subset), reports `autofix-versions.env` freshness for visibility, then syncs the dev-dependency pins using the PAT provided via `REPO_TOKEN`; now reuses `scripts/list_registered_consumer_repos.py` and avoids redundant GitHub App token mints.
- **`maint-52-validate-workflows.yml`** — PR/push workflow that dry-parses every workflow file with `yq`, runs actionlint with the repo allowlist, and caches both binaries; no extra GitHub App token is minted because the job never leaves the repository.
- **`maint-60-release.yml`** — Tag-triggered release workflow that publishes notes with `softprops/action-gh-release` when a `v*` tag is pushed; only the default workflow token is needed, so no extra App mint runs. (Retains a legacy floating-`v1` tag step for any `v1.*` push, but consumers ride `@main` — the single supported pin — so the floating tag is no longer part of normal operation.)
- **`maint-61-release-please.yml`** — Main-branch release-please automation that opens or updates the Conventional Commits-driven Release PR from the manifest seeded at `1.1.2`, preferring the Workflows GitHub App token so the generated PR can trigger Gate.
- **`maint-62-integration-consumer.yml`** — Nightly + release-triggered integration tests that reuse `reusable-10-ci-python.yml` across multiple matrices and file/resolve the `integration-test` issue via the load-balanced API client (no extra app mint).
- **`maint-65-sync-label-docs.yml`** — Syncs `docs/LABELS.md` into every registered consumer repo (plus the integration tests repo) when the source doc changes or on demand, using the shared registered-repo helper and PAT gating for cross-repo pushes.
- **`maint-66-monthly-audit.yml`** — First-of-month workflow that gathers workflow-run stats, runs the API wrapper guard, and files/updates the monthly audit issue; relies on the shared API client so no extra npm installs or App-token mints are needed.
- **`maint-68-sync-consumer-repos.yml`** — Manifest-driven consumer sync that validates template/scripts, hashes the template set, and opens PAT-backed sync PRs for each registered repo; the jobs now rely solely on the shared API client and repo PATs (no extra App token mints).
- **`maint-69-sync-integration-repo.yml`** — Keeps Workflows-Integration-Tests aligned with `templates/integration-repo/`, regenerates `requirements.lock`, and pushes updates using PATs; no GitHub App token mint is required because the workflow stays inside the two repos.
- **`maint-69-sync-labels.yml`** — Propagates the canonical `.github/labels-core.yml` set to every registered consumer repo (or a provided subset), reusing the registered-repo helper + load-balanced API client without any additional App-token minting.
- **`maint-70-fix-integration-formatting.yml`** — Manual formatter for Workflows-Integration-Tests that resolves the repo default branch, applies `black`+`ruff` fixes, and pushes via PAT only when a token is available; runs read-only otherwise.
- **`maint-71-auto-fix-integration.yml`** — Auto-triggered integration fixer that watches “Integration CI failed” issues/comments, re-runs the formatting routine, and pushes via PAT when available (otherwise posting a skipped note).
- **`maint-71-merge-sync-prs.yml`** — Scans each registered consumer repo for open `sync/workflows-*` PRs, closes stale duplicates, deletes leftover same-repo sync branches tied to closed/merged sync PRs, and (optionally) auto-merges passing PRs using the shared repo helper + PATs.
- **`maint-72-fix-pr-body-conflicts.yml`** — Periodically removes stray `pr_body.md` files from consumer repos and ensures `.gitignore` blocks them, reusing the registered-repo helper + PAT discovery so cleanups only run when push access is available.
- **`maint-74-ledger-base-sync.yml`** — Keeps `.agents` ledger base entries aligned with the repo’s default branch by running `scripts/ledger_migrate_base.py` and opening a helper PR (no extra App token mint needed).
- **`maint-auto-update-pypi-versions.yml`** — Daily PyPI watcher that updates `autofix-versions.env`, regenerates supporting files, and opens a PR when new tool versions land (runs entirely with the default token + GH CLI).
- **`maint-coverage-guard.yml`** — Scheduled coverage baseline monitor with a rate-limit gate that now relies solely on the shared API client + default token.
- **`maint-coverage-guard.yml`** — Daily cron + dispatch workflow that monitors Gate coverage artifacts and maintains the rolling coverage baseline breach issue.
- **`health-40-sweep.yml`** — Weekly sweep that fans out to Actionlint and branch-protection verification. Pull requests trigger the Actionlint leg (paths-filter gated) while schedule/manual runs execute both checks to keep the enforcement snapshots fresh. Manual dispatchers can now pass `run_branch_protection=false` to skip the API-heavy branch guard when they only need the workflow lint pass.
- **`health-40-repo-selfcheck.yml`** — Monday 06:20 UTC governance probe that inventories the required automation labels, snapshots default-branch protection, and (when `BRANCH_PROTECTION_TOKEN` is present) enforces Gate + Guard contexts before publishing the consolidated status table to the run summary. Falls back to a read-only mode whenever only the installation token is available so the branch-protection visibility signal still lands even if we cannot mutate settings.
- **`health-41-repo-health.yml`** — Weekly repository health sweep that writes a single run-summary report covering stale branches, unassigned issues, and default-branch protection drift, with optional `workflow_dispatch` reruns. Manual runs can now toggle the branch and PR scans (`include_branches` / `include_prs`) to avoid the expensive enumeration APIs when only part of the report is needed.
- **`health-42-actionlint.yml`** — Underlying Actionlint job invoked by the sweep (and still runnable via manual dispatch when you need a focused lint dry run). Uses tool caches instead of minting extra GitHub App tokens so retries don't burn API quota.
- **`health-43-ci-signature-guard.yml`** — Guards the Gate workflow manifest by hashing `.github/signature-fixtures/**` and verifying them through the `signature-verify` composite, ensuring Gate job wiring stays tamper-proof without minting extra GitHub App tokens.
- **`health-44-gate-branch-protection.yml`** — Enforces branch-protection policy via `tools/enforce_gate_branch_protection.py` when the PAT is configured (now triggered on PRs or by the consolidated sweep) and skips minting extra GitHub App tokens because enforcement already runs with the configured `BRANCH_PROTECTION_TOKEN`.
- **`health-50-security-scan.yml`** — Security scanning workflow triggered on push, PR, and schedule. Runs CodeQL vulnerability scans using the configured PAT priority list without minting additional GitHub App tokens.
- **`health-67-integration-sync-check.yml`** — Daily + event-driven comparison between `templates/integration-repo/` and the Workflows-Integration-Tests repo. Manual dispatchers can now toggle the CI/versions/input checks individually to avoid cloning/running sections they don't need while still filing drift issues when enabled checks detect problems.
- **`health-68-consumer-sync-drift.yml`** — Daily + change-triggered drift detector for consumer repos. Uses the shared `scripts/list_registered_consumer_repos.py` helper to build the repo list (also accepts a manual override) before running `scripts/check_consumer_sync_drift.py`, and files/updates the `consumer-sync` issue when inconsistencies surface.
- **`health-71-sync-health-check.yml`** — Daily monitor that inspects the recent `maint-68-sync-consumer-repos` runs. Manual dispatches can tweak `lookback_runs`/`max_age_hours`, and the workflow now reuses `scripts/list_registered_consumer_repos.py` (instead of ad-hoc parsing) without minting an extra GitHub App token.
- **`health-72-template-sync.yml`** — Keeps manifest-declared exact template-sync files in sync between Workflows and the consumer template. For PRs from this repo it auto-runs `scripts/sync_templates.sh` + pushes deltas, then validates via `scripts/validate_template_sync.py`, relying only on the installation token.
- **`health-75-api-rate-diagnostic.yml`** — Hourly rate-limit snapshotter that polls every configured PAT/App pool, posts a tabular summary, and (on-demand) can fan out to load-balancer simulations and consumer-repo churn reports. Manual dispatch inputs gate the expensive legs (`include_consumer_repos`, `run_load_sharing_checks`, `verify_actions_access`) so that day-to-day runs stay light on API calls while still allowing deep dives when quota pressure crops up.
- **`health-claude-cli-auth-debug.yml`** — Archived manual Claude CLI auth harness (now lives in `archives/diagnostics/`). Run it ad-hoc only when investigating Claude CLI regressions; otherwise leave it out of the automated health rotation.
- **`health-codex-auth-check.yml`** — Twice-daily JWT expiry guard for `CODEX_AUTH_JSON`. Lists any open `auth-expiring` issue before running, then decodes the stored token and files/updates an issue when the remaining lifetime drops below 48 h (or has already expired). Manual reruns can force a check even if an issue already exists.
- **`health-keepalive-auth-diagnostic.yml`** — Archived manual harness for verifying GitHub App push scopes + Claude/Codex secrets across consumer repos. Lives under `archives/diagnostics/` and should only be run when debugging keepalive auth not covered by automated monitors.
- **`health-keepalive-e2e.yml`** — PR-only safeguard that runs through the keepalive orchestration helpers on every workflow change and, when labeled `e2e:codex-ping`, executes a minimal real Codex call to prove the reusable runner still works. The default orchestration leg now uses just the installation token (no extra GitHub App mints) to keep API load low.

### Agents & Issues
- **Consumer default entry points** — New consumer repos should install the template-managed pair `agents-80-pr-event-hub.yml` + `agents-81-gate-followups.yml` (along with `agents-verifier.yml`, `pr-00-gate.yml`, `AGENTS.md`, and `CLAUDE.md`). Treat `agents-pr-meta-v4.yml` as Workflows-local infrastructure, not a default consumer setup file.
- **`agents-63-issue-intake.yml`** — Canonical front door for Codex issues. It normalizes ChatGPT export blobs / topic lists, dedupes and validates the resulting queue, optionally re-formats the new issues via LangChain, and drives the label-enforced issue bridge when `agent_bridge` mode is selected. The workflow now relies solely on the installation token + the shared API client (no ad-hoc GitHub App token mints), so manual reruns and workflow_call invocations stay lightweight while still enforcing the single-agent label contract before dispatching work to the belt.
- **`agents-64-verify-agent-assignment.yml`** — Workflow-call validator that enforces the single `agent:*` label contract and confirms the assignee belongs to the approved automation roster. It now runs entirely on the default workflow token with the shared retry helper (no bespoke GitHub App mint), so verification hooks stay lightweight for orchestrator and issue-bridge callers.
- **`agents-capability-check.yml`** — Pre-flight guard that fires when an `agent:*` label lands on an issue. It installs the LangChain extras, runs `scripts/langchain/capability_check.py` to classify tasks as actionable/partial/blocked, adds `needs-human` + removes agent labels on BLOCKED outcomes, and posts/updates a structured comment so humans know why automation paused. Already reuses the shared API client for retries and only runs when labels demand it, so no extra optimization was required.
- **`agents-70-orchestrator.yml`** — 30-minute cron plus manual dispatch entry point for readiness, Codex/Claude bootstrap, diagnostics, verification, and keepalive sweeps. Delegates to `reusable-16-agents.yml`, so optimization lives in the reusable stack; this wrapper simply sequences the cron/manual hooks, feeds `options_json`, and never mints extra tokens beyond the shared API client. When adding new stages, read `.github/agents/registry.yml` and treat every listed agent key the same so we can add Claude or future providers without touching the orchestrator again.
- **`agents-71-codex-belt-dispatcher.yml`** — Cron + manual dispatcher that selects the next `agent:codex` + `status:ready` issue, prepares the deterministic `codex/issue-*` branch, labels the source issue as in-progress, and repository-dispatches the worker. It already enforces GitHub App → PAT → `GITHUB_TOKEN` token selection, dry-run preview mode, and per-agent concurrency groups so no further optimization was required.
- **`agents-72-codex-belt-worker.yml`** — Repository-dispatch consumer that re-validates labels, ensures the branch diverges from the base (empty commit when needed), and opens or refreshes the Codex automation PR with labels, assignees, and activation comment. Like the dispatcher it prefers App tokens, falls back to PAT/`GITHUB_TOKEN`, honours per-agent concurrency, and exposes a dry-run guard for diagnostics.
- **`agents-73-codex-belt-conveyor.yml`** — Gate follower that squash-merges successful belt PRs, deletes the branch, closes the originating issue, posts audit breadcrumbs, and re-dispatches the dispatcher so the queue keeps moving. It reuses the shared API client for token load balancing, requires Gate success before merging, blocks bootstrap-only placeholders, and mirrors the same dry-run + concurrency protections as the dispatcher/worker.
- **`agents-auto-label.yml`** — Issue/PR label suggester that feeds LangChain embeddings through the shared API client, applies labels with the default token, and posts suggestion comments when confidence drops below auto-apply thresholds. Removing the redundant App mint keeps the workflow lightweight on every issue event.
- **`agents-auto-pilot.yml`** — Full issue-to-PR automation pipeline (format → optimize → apply → capability check → PR creation → keepalive → verify). Apply `agents:auto-pilot` to start, and add an optional `runner:<name>` label (for example `runner:claude`) when you want a specific agent to own the run. Manual `agent:<name>` labels still trigger the issue intake bridge; the new `runner:` override exists so auto-pilot can stay label-driven without colliding with manual workflows. Runner overrides are now validated against `.github/agents/registry.yml`, so stray `runner:*` labels from other automation are ignored instead of misrouting agents. If no override exists, auto-pilot falls back to the registry default, adds that `agent:` label for you, and hands tasks to keepalive without extra per-job token churn.
- **`agents-autofix-dispatcher.yml`** — Triggered when Gate posts `autofix_gate_failure`. It still needs a GitHub App token to dispatch `agents-autofix-loop.yml`, but otherwise the job simply forwards the failing run ID/PR/head SHA so the loop can attempt repairs.
- **`agents-autofix-loop.yml`** — Handles larger fix-ups (pyproject sync, scripted rewrites, merge conflict handling) after the dispatcher fires. It now also listens to Gate `workflow_run` events as a safety net, so existing repos that haven’t wired the new dispatch signal still get autop-run coverage. Every GitHub API call routes through the token-aware retry helper (the callbacks now use the rotated client), and the loop continues to label PRs (`autofix:conflict`, `needs-human`) when automation cannot complete the repair.
- **`agents-autofix-rebase.yml`** — Rebase helper kicked off from Gate when `mergeable_state` is `dirty`/`behind`. It merges the base branch into same-repo PRs with the App token, tagging the PR with `autofix:conflict` plus a comment whenever a manual rebase is still required.
- **`agents-bot-comment-autolabel.yml`** — Watches review comments and automatically applies `autofix:bot-comments` whenever a trusted bot (Copilot, Claude, CodeRabbit, etc.) suggests changes. This guarantees the bot-comment handler fires without waiting for a human to apply the label.
- **`agents-72-codex-belt-worker-dispatch.yml`** — Convenience wrapper around the belt worker so maintainers can run the worker via `workflow_dispatch` with explicit inputs (issue, branch, dry run, etc.) without touching the reusable workflow directly.
- **`agents-bot-comment-handler.yml`** — Runs the existing inline-comment application logic. In addition to the prior label/Gate/manual triggers it now auto-runs when trusted bot review comments land, so inline suggestions on non-agent PRs are applied without manual relabeling. Override the trusted logins via `BOT_COMMENT_LOGINS` when repositories add more bots.
- **`agents-guard.yml`** (aka Health 45 Agents Guard) — PR workflow that validates agent-related labels and permissions for both `pull_request` and `pull_request_target`. It now relies entirely on the shared API client/token balancer, so there’s no bespoke App-token mint ahead of safety checks.
- **`agents-issue-optimizer.yml`** — Powers the analyzer/apply/format stages for legacy agent issues. It fires on the `agents:*` optimizer labels or via manual dispatch, skips when `agents:auto-pilot` is present, enforces recursion guards via the GitHub CLI, and runs the LangChain optimizer before posting suggestions or applying changes. It now uses only the shared API client (no manual App-token mint) for GH CLI/auth flows.
- **`agents-80-pr-event-hub.yml`** — Consumer-template consolidated PR event hub that fans out keepalive metadata, bot-comment handling, and verification follow-ups after a single PR context fetch.
- **`agents-81-gate-followups.yml`** — Consumer-template consolidated Gate follow-up hub that coordinates keepalive, autofix, and post-CI recovery.
- **`agents-pr-meta-v4.yml`** — Workflows-repo PR metadata/keepalive front door: listens to issue comments, PR updates, and Gate completions to detect `@agent` activations, enforce gate/run-cap rules, dispatch the orchestrator, and write dispatch summaries. This remains a Workflows-local service workflow; the current consumer default is the `agents-80-pr-event-hub.yml` / `agents-81-gate-followups.yml` pair distributed from `templates/consumer-repo/`.
- **`agents-verifier.yml`** — Label-driven verification runner. When a merged PR gets `verify:*` (or when dispatched manually), it routes the request through the reusable verifier workflow to run checkbox/evaluate/compare modes, posts the structured summary, and opens follow-up issues on failures. It now mints a GitHub App token before checking out the caller repo/Workflows scripts so cross-repo verification works under the service account while still falling back to the installation token when App credentials are missing, and it explicitly waits for `pr-00-gate.yml`, `pr-11-ci-smoke.yml`, and `selftest-ci.yml` to finish so the verifier never outruns Workflows’ CI set.
- **`agents-verify-to-issue-v2.yml`** — Converts verification feedback into an agent-ready follow-up issue whenever `verify:create-issue` is applied to a merged PR. It gathers the verification comments, original issue context, and PR metadata, runs LangChain templates, and opens a structured issue using the appropriate PAT/App token so ownership stays consistent.
- **`agents-verify-to-new-pr.yml`** — Handles the `verify:create-new-pr` label end-to-end: collects verification comments, reconstructs the original issue context, creates a follow-up issue (carrying over the `agent:*` label plus a `runner:<agent>` override), and now dispatches `agents-auto-pilot.yml` (optimize step) inline so automation continues without a separate bridge workflow.
- **`agents-moderate-connector.yml`** — Moderates connector-style PR comments. Uses allow/deny lists plus heuristics (checklist/commit/code indicators and known noise phrases) to delete “I can’t run Codex here” spam while preserving legitimate updates. Skips moderation when `agents:debug` is on the PR so humans can inspect noisy runs. Relies on the shared API client; no workflow changes were required.
- **`agents-weekly-metrics.yml`** — Weekly cron that aggregates artifacts from keepalive, autofix, verifier, auto-pilot, terminal-disposition, and bot-comment auth runs, generates a Markdown summary, uploads it, and posts/updates the tracking issue. Now relies entirely on the shared API client (installation token) for artifact downloads and issue updates—no bespoke App token. The tracking issue it appends to is one of the durable trackers documented in [`docs/ops/DURABLE_TRACKING_ISSUES.md`](ops/DURABLE_TRACKING_ISSUES.md); do not close it as part of routine triage.

### Health & Maintenance Highlights
- **`health-72-template-sync.yml`** — Guards manifest-declared exact template-sync files between the repo and the consumer template. On PRs it auto-runs `scripts/sync_templates.sh` (when the PR comes from this repo), commits/pushes template changes, and then `scripts/validate_template_sync.py` enforces parity; on `push` it just runs the validator. The workflow uses the default installation token; no extra GitHub App mint is needed.
- **`agents-keepalive-branch-sync.yml`** — Dispatch-triggered utility that syncs PR branches with their base branch (merges base into head). It still selects an App token/PAT for git pushes because keepalive needs to merge into automation-owned branches, but all logic stays confined to git + summary updates—no extra API calls beyond pushing the merge.
- **`agents-keepalive-dispatch-handler.yml`** — Repository-dispatch handler that receives `codex-pr-comment-command` payloads, selects a write-capable token (App → PAT → installation), and runs `keepalive_post_work.js` to apply sync-required labels, rerun keepalive legs, or emit debugging breadcrumbs. Token selection remains by design because the handler must write to PRs immediately after the dispatch event.
- **`agents-keepalive-loop.yml`** — Core keepalive orchestrator that wakes up after Gate completion, re-validates labels/run caps, builds the task appendix, and dispatches the correct registry-backed agent workflow until Acceptance Criteria are satisfied or failure limits are hit. The workflow already uses the shared API client for retries, captures prompts via artifacts, and posts iteration summaries, so no further optimization was required.
- **`agents-keepalive-loop-reporter.yml`** — Watches keepalive loop `workflow_run` events and updates the summary comment when runs cancel/fail. Reuses the shared API client/installation token—no bespoke App mint—because it only needs to write PR comments.
- **`agents-debug-issue-event.yml`** — Debug workflow that dumps GitHub context on issue events (labeled, unlabeled, opened, reopened). Useful for troubleshooting label triggers; it never mutates issues and simply echoes payload details for humans.
- **`agents-decompose.yml`** — Handles the `agents:decompose` label by running LangChain’s `task_decomposer.py`, posting suggested subtasks, and removing the trigger label. It now relies entirely on the shared API client/token load balancer (no bespoke GitHub App mint) for checkout and label cleanup.
- **`agents-dedup.yml`** — Runs when new issues open (non-bot authors). It builds embeddings via `scripts/langchain/issue_dedup.py`, flags near-duplicate open issues, and posts guidance for merging/closing duplicates. The redundant GitHub App mint was removed so the shared API client handles all API traffic.

### Autofix
- **`autofix.yml`** — CI Autofix Loop triggered on `pull_request` and `pull_request_target`. It now treats lint/format, Ruff, type-check (`mypy`), and pytest/test failures as “relevant,” automatically re-running when those jobs fail so most routine regressions are handled before humans see Gate noise, and the unnecessary `push` trigger was removed so we no longer spawn no-op runs on every commit. Commits still land directly on the PR branch via the shared token load balancer.
- **`agents-autofix-dispatcher.yml`** — See Agents section; dispatches the heavy repair loop when Gate emits `autofix_gate_failure`.
- **`agents-autofix-loop.yml`** — See Agents section; performs scripted fixes, dependency syncs, and conflict handling before escalating with labels/comments.
- **`agents-autofix-rebase.yml`** — See Agents section; merges the base branch when Gate flags stale branches, preventing common “needs rebase” failures from blocking progress.
- **`agents-bot-comment-autolabel.yml`** / **`agents-bot-comment-handler.yml`** — Automatically harvest trusted bot review comments and apply them via the autofix pathways without manual labelling.

#### Autofix & Lint Coordination
1. **Gate emits signals** — `pr-00-gate.yml` attaches artifacts describing the failing job plus `mergeable_state`. When lint/format/typecheck/test jobs fail it dispatches `autofix_gate_failure`; when the PR is dirty/behind it dispatches `autofix_rebase_needed`.
2. **CI autofix first pass (`autofix.yml`)** — Runs Ruff/formatters/tests where possible and pushes fixes directly to the branch so same-run Gate retries can pass without escalation.
3. **Dispatcher + loop** — `agents-autofix-dispatcher.yml` forwards the failing run metadata to `agents-autofix-loop.yml`, and the loop also listens to `Gate` `workflow_run` events as a fallback so legacy consumers still receive repairs even if the dispatcher signal isn’t wired yet. Once running, the loop reuses PAT/App tokens to run pyproject syncs, scripted rewrites, and base-merge attempts. Loop failures tag PRs with actionable labels/comments (`autofix:conflict`, `needs-human`).
4. **Rebase helper** — `agents-autofix-rebase.yml` runs in parallel to merge the base branch when mergeable_state is `dirty`/`behind`. It only files `autofix:conflict` after proving the automatic merge truly blocks.
5. **Inline comment coverage** — `agents-bot-comment-autolabel.yml` watches for trusted bot review comments and applies `autofix:bot-comments`, which in turn triggers `agents-bot-comment-handler.yml` to apply suggested patches. This closes the loop on CodeRabbit/Claude/Copilot feedback without human intervention.
6. **Conflict + drift cleanup** — For automation-owned branches, the belt worker/conveyor keep them fresh; for consumer sync PRs, `maint-71-merge-sync-prs.yml` and `maint-45-cosmetic-repair.yml` close stale/autofix branches, delete leftover sync branches, and re-run formatters. Together these keep conflict/inline-comment/formatter issues automated so humans only handle edge cases.

### Reusable Composites
- **`reusable-10-ci-python.yml`** — Python lint/type/test reusable invoked by Gate and downstream repositories.
- **`reusable-11-ci-node.yml`** — Node lint/type/test reusable that powers JavaScript/TypeScript consumers (ESLint, Prettier, tsc, Jest/Vitest). Runs entirely within the repo using the default workflow token, so callers don’t burn extra API calls just to fetch sources.
- **`reusable-12-ci-docker.yml`** — Docker smoke reusable invoked by Gate and external consumers. Builds the repo’s container image, runs a local health probe, and now relies solely on the default workflow token (no extra GitHub App mint) because it only needs repo read access.
- **`reusable-13-cross-repo-smoke.yml`** — Cross-repo smoke reusable that checks out the host repository plus a pinned dependency repository and runs caller-provided install/smoke shell commands. Consumer repos opt in through synced `cross-repo-smoke.yml` wired to `CROSS_REPO_SMOKE_*` repository variables and the `CROSS_REPO_TOKEN` secret.
- **`reusable-16-agents.yml`** — Agents toolkit composite that powers orchestrator/agents-70 by fanning out optional stages: readiness probes, per-agent preflight checks, bootstrap diagnostics, watchdogs, keepalive sweeps, and issue verification. Handles token fallbacks (SERVICE_BOT_PAT, ACTIONS_BOT_PAT, GitHub App) and exposes `options_json` so callers can toggle dry-runs or extra automation without rewriting YAML. When designing new workflows, assume at least **two** active agents (Codex + Claude) and rely on `.github/agents/registry.yml` + `agent_registry.js` so stage-specific logic can iterate over every configured agent rather than hard-coding Codex-only paths. Use the `preflight_overrides_json` input when you need to temporarily override an agent’s assignable login or command phrase. See [plans/multi-agent-toolkit.md](plans/multi-agent-toolkit.md) for the checklist we follow when extending Toolkit stages to future agents.
- **`reusable-18-autofix.yml`** — Autofix harness used by the Gate summary job: determines auth path (App token → Service bot PAT → default token), applies formatter fixes directly for same-repo branches, uploads patches when pushes aren’t allowed, and records mode/delivery metadata so callers know whether changes landed or a patch artifact was produced.
- **`reusable-20-pr-meta.yml`** — PR metadata/keepalive reusable for consumer repos. Dual-checks out the consumer repo + Workflows scripts, detects keepalive activations from comments/Gate runs, updates PR body sections, and dispatches the keepalive orchestrator using the provided PATs/default token (no App mint required).
- **`reusable-70-orchestrator-init.yml`** — Preflight stage for Agents 70 orchestrator. Checks PAT rate limits, determines whether there’s work, selects the keepalive token source (App token > PATs), and resolves the per-agent readiness/preflight/bootstrap/keepalive parameters before passing them to the main orchestrator.
- **`reusable-70-orchestrator-main.yml`** — Executes the orchestrator stages (keepalive gate, readiness, preflight, diagnostics, bootstrap, watchdog, keepalive sweep) using the outputs from the init workflow. Requires the GitHub App token when PATs aren’t available so keepalive writes still run under `agents-workflows-bot`.
- **`reusable-bot-comment-handler.yml`** — Collects unresolved bot review comments, generates a per-agent prompt, and dispatches the appropriate runner. Prefers GitHub App client ID auth, records the selected App auth mode, keeps a warning-only legacy App ID fallback, and still falls back to `service_bot_pat` or `GITHUB_TOKEN` so consumer repos don’t have to configure extra secrets.
- **`reusable-codex-run.yml`** — Codex execution wrapper that checks out the target PR branch, installs the pinned Codex CLI, runs the prompt, and pushes commits when the GitHub App token is available (otherwise drops to read-only mode using `GITHUB_TOKEN`).
- **`reusable-claude-run.yml`** — Claude CLI wrapper for keepalive/autofix scenarios. It mints the Workflows GitHub App token when available so branch pushes can mirror Codex parity, reuses the shared setup-api-client checkout, hardens the Workflows scripts checkout (detecting blobless-clone ghost dirs and reinstalling @octokit deps), and exposes inputs for prompt files, sandbox/safety flags, runtime caps, and appendices. Use it anywhere Claude needs to run the same branch-update loop as Codex.
- **`reusable-agents-issue-bridge.yml`** — Shared issue→PR bridge used by `agents-63-issue-intake.yml`; reads `.github/agents/registry.yml` to honor each agent’s branch prefix + assignee list, applies invite/create modes, and now relies solely on the shared token chain (service bot / owner PAT / default token) without minting extra App tokens.
- **`reusable-agents-verifier.yml`** — Post-merge verifier reusable that waits for CI (tracking every configured workflow until each has both started and completed), builds PR context, runs checkbox/evaluate/compare modes via the agent verifier stack, and opens follow-up issues when acceptance criteria fail. It mints the Workflows GitHub App token up front so both the caller repo and the Workflows scripts checkout succeed for private/same-repo callers, then falls back to `GITHUB_TOKEN` automatically when App secrets are absent.

### Self-tests
- **`selftest-reusable-ci.yml`** — Manual entry point that houses the verification matrix and comment/summary/dual-runtime publication logic.

## Archived & Legacy Workflows

The following workflows were decommissioned during the CI consolidation effort. Keep these references around for historical context only; do not resurrect them without a fresh review. For the authoritative ledger (including verification notes), see [ARCHIVE_WORKFLOWS.md](archive/ARCHIVE_WORKFLOWS.md).

- **`pr-14-docs-only.yml`** — Former docs-only fast path superseded by Gate’s internal detection.
- **`maint-47-check-failure-tracker.yml`** — Replaced by the consolidated post-CI summary embedded in the Gate workflow.
- **Historical consumer wrappers** — Fully replaced by the orchestrator. Their retirement history now lives in [ARCHIVE_WORKFLOWS.md](archive/ARCHIVE_WORKFLOWS.md).
- **Legacy selftest wrappers** (`selftest-80-pr-comment.yml`, `selftest-82-pr-comment.yml`, `selftest-83-pr-comment.yml`, `selftest-84-reusable-ci.yml`, `selftest-88-reusable-ci.yml`, `selftest-81-reusable-ci.yml`) — Superseded by the consolidated `selftest-reusable-ci.yml`; these wrappers are now removed from `.github/workflows/` and live only in history.

## Trigger Wiring Tips
1. When renaming a workflow, update any `workflow_run` consumers. In this roster that includes the Gate summary job.
2. The orchestrator relies on the workflow names, not just filenames. Keep `name:` fields synchronized with filenames to avoid missing triggers.
3. Reusable workflows stay invisible in the Actions tab; top-level consumers should include summary steps for observability.

### Failure rollup quick reference
- The Gate summary job updates the "CI failures in last 24 h" issue labelled `ci-failure`, aggregating failure signatures with links back to the offending Gate runs.
- Auto-heal closes the issue after a full day without repeats while preserving an occurrence history in the body.
- Escalations apply the `priority: high` label once the same signature fires three times.

## Agent Operations
- Use **Agents 70 Orchestrator** for readiness checks, Codex bootstrap, diagnostics, and keepalive sweeps. The **Agents 71–73 Codex Belt** now owns the queue automation loop—dispatcher selects issues, worker opens/refreshes the PR, conveyor merges after Gate, and the dispatcher is re-triggered. Historical consumer shims remain retired (see [ARCHIVE_WORKFLOWS.md](archive/ARCHIVE_WORKFLOWS.md)), and the Agent task issue template still auto-labels issues (`agents`, `agent:codex`) so the bridge can open the branch/PR before the belt takes over.
- Optional flags beyond the standard inputs belong in the `params_json` payload; the orchestrator parses it with `fromJson()` and forwards toggles to `reusable-16-agents.yml`. Include an `options_json` string inside the payload for nested keepalive or cleanup settings when required.
- Provide a PAT when bootstrap needs to push branches. The orchestrator honours PAT priority (`OWNER_PR_PAT` → `SERVICE_BOT_PAT` → `GITHUB_TOKEN`) via the reusable composite.

## Verifier Workflow
The verifier validates merged PRs against tasks and acceptance criteria using label-triggered modes.

### How to trigger verification
1. Ensure the PR body includes Tasks and Acceptance Criteria sections with checkboxes.
2. Apply one of the `verify:*` labels to the PR before merging.
3. Merge the PR; `agents-verifier.yml` runs in the default branch and reads the label to pick a mode.

### What each mode does
- **Checkbox (`verify:checkbox`)** — Validates acceptance-criteria checkboxes against implementation evidence in the merged PR.
- **Evaluate (`verify:evaluate`)** — Runs LLM-based evaluation for correctness, quality, and completeness using the merged PR context.
- **Compare (`verify:compare`)** — Runs evaluation with multiple models to compare verdicts, rubric scores, and coverage.

### Expected outputs
- **Run summary** — Verdict (PASS/FAIL), highlights, and links to the acceptance/task context.
- **Issue on failure** — Follow-up issue creation is manual and label-triggered:
  apply `verify:create-issue` for an issue-only follow-up or
  `verify:create-new-pr` for a bootstrapped follow-up PR when a
  CONCERNS/FAIL verdict needs more work.
- **Mode-specific report** — Checkbox mode posts criteria coverage, Evaluate posts a structured rubric report, Compare posts a model comparison table.
These outputs land in the Actions run summary, with any follow-up issue filed in the same repository.

### When to use each mode
- **Checkbox** — Lightweight audit of acceptance criteria after merge when you only need evidence checks.
- **Evaluate** — Higher-confidence validation when requirements are complex or subjective.
- **Compare** — Benchmarking or model selection when evaluation quality is under review.

## Verifier Troubleshooting
- **No verifier run** — Ensure the PR was merged, the `verify:*` label was applied before merge, and the repository includes `agents-verifier.yml`.
- **Verifier skipped** — Confirm the PR body includes Tasks and Acceptance Criteria sections with checkboxes.
- **Follow-up issue missing** — Check the run summary for a PASS verdict and
  confirm `verify:create-issue` or `verify:create-new-pr` was applied to the
  merged PR; ordinary verifier CONCERNS/FAIL verdicts do not automatically open
  follow-up issues.
- **Auth or API errors** — Confirm `SERVICE_BOT_PAT` is configured and has repo/issue permissions.


### Manual dispatch quick steps
1. Open **Actions → Agents 70 Orchestrator → Run workflow**.
2. Supply inputs such as `enable_bootstrap: true` and `bootstrap_issues_label: agent:codex` either via dedicated fields or inside `options_json`.
3. Review the `orchestrate` job summary for readiness tables, bootstrap planner output, verification notes, and links to spawned PRs. Failures provide direct links for triage.
4. For CLI/API usage, reuse the `params_json` example in [docs/ci/WORKFLOWS.md](ci/WORKFLOWS.md#manual-orchestrator-dispatch) and post it directly—either with `gh workflow run agents-70-orchestrator.yml --raw-field params_json="$(cat orchestrator.json)"` or with a REST call such as `curl -X POST ... '{"ref":"phase-2-dev","inputs":{"params_json":"$(cat orchestrator.json)"}}'`. Export `GITHUB_TOKEN` to a PAT or workflow token that can dispatch workflows before invoking the CLI/API call. Mix in individual overrides only when a flag must diverge from the JSON payload.

### Troubleshooting signals
- **Immediate readiness failure** — missing PAT or scope. Inspect the `Authentication` step and rerun with `SERVICE_BOT_PAT`.
- **Bootstrap skipped** — no labelled issues matched `bootstrap_issues_label`. Add the label and rerun.
- **Branch push blocked** — repository protections blocking automation. Grant the PAT required scopes or adjust branch rules.

## Maintenance Playbook
1. PRs rely on the Gate workflow listed above. Keep it green; the post-CI summary will report its status automatically.
2. Monitor failure tracker issues surfaced by the Gate summary job; it owns the delegation and auto-heal path end to end.
3. Use `Health 40 Sweep` when you want the combined Actionlint + branch-protection sweep, or `Health 42 Actionlint` (`workflow_dispatch`) for an Actionlint-only rehearsal of complex workflow edits before pushing.
4. Dispatch `Maint 45 Cosmetic Repair` when you need a curated pytest + hygiene sweep that opens a helper PR with fixes.
5. Run `Maint 47 Disable Legacy Workflows` after archival sweeps to disable any retired workflows that still appear in the Actions UI.

## Additional References
- `.github/workflows/README.md` — Architecture snapshot for the CI + agent stack.
- `docs/ci/WORKFLOWS.md` — Acceptance-criteria checklist for the final workflow set.
- `docs/agent-automation.md` — Detailed description of the agent orchestrator and options.
- **`reusable-10-ci-python.yml`** — Primary Python CI composite (lint → format → mypy → pytest + coverage). Accepts matrix inputs and installs uv caches; optionally uses the GitHub App token for checkout when provided, but callers can rely on the default token.
- **`reusable-pr-context.yml`** — GraphQL-based PR context fetcher used across workflows to gather labels/files/CI state in one call. Falls back to the caller’s token but prefers the GitHub App token or owner PAT when available to reduce per-run API limits.
- **`selftest-ci.yml`** — Workflows’ own CI smoke (JS tests, Python tests, lint/YAML validation). Now relies solely on the default workflow token because the jobs only read this repo.
- **`selftest-reusable-ci.yml`** — Scheduled/manual harness that drives `reusable-10-ci-python.yml` across multiple feature combinations (metrics, history, coverage delta, soft gate) and posts summary/comment outputs. Relies on the default workflow token plus inherited secrets—no extra token plumbing needed.
