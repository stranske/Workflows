# Workflow Review Checklist
This checklist will track optimization, consolidation, or archival work for every workflow under `.github/workflows`. Mark each workflow as you finish reviewing it and capture notes on required changes.

| Review | Workflow | Notes |
| --- | --- | --- |
| [x] | `agents-63-issue-intake.yml` | Still required as the Codex issue front door; removed four unused GitHub App token mints so queue sync + bridge runs stay within the shared token balancer. |
| [x] | `agents-64-verify-agent-assignment.yml` | Still useful for belt/orchestrator sanity checks; removed the unused GitHub App token mint so it relies solely on the shared token-balanced client. |
| [x] | `agents-70-orchestrator.yml` | Still required; delegates to the reusable init/main stack and just sequences cron/manual dispatch without extra token churn. |
| [x] | `agents-71-codex-belt-dispatcher.yml` | Keeps GitHub App → PAT → `GITHUB_TOKEN` precedence, dry-run controls, and per-agent concurrency intact—no workflow edits needed. |
| [x] | `agents-72-codex-belt-worker-dispatch.yml` | Wrapper that forwards workflow_dispatch inputs to the belt worker; documented behavior (no YAML change needed). |
| [x] | `agents-72-codex-belt-worker.yml` | Worker already re-validates labels, enforces token fallback order, guards concurrency, and exposes dry-run flags. |
| [x] | `agents-73-codex-belt-conveyor.yml` | Conveyor already checks Gate status, blocks bootstrap-only placeholders, mirrors token/dry-run protections, and re-dispatches the queue. |
| [x] | `agents-auto-label.yml` | Still the LangChain-based labeler; removed the redundant App mint so it runs entirely on the shared API client. |
| [x] | `agents-auto-pilot.yml` | Remains the canonical issue-to-PR pipeline and now validates `runner:*` overrides against the registry before honoring them so stray runner labels can’t misroute agent selection. |
| [x] | `agents-autofix-dispatcher.yml` | Dispatch path still needed (Gate autofix failure → loop); kept as-is and documented that it simply forwards run metadata using the App token. |
| [x] | `agents-autofix-loop.yml` | Re-added the Gate `workflow_run` trigger (alongside the dispatcher path) so Gate failures still launch repairs even in repos that haven’t adopted the new dispatch event, and updated every `withRetry` call to use the token-aware client so rate-limit rotation actually works. |
| [x] | `agents-autofix-rebase.yml` | New helper keeps PRs rebased via the App token and files `autofix:conflict` only when manual work is needed. |
| [x] | `agents-bot-comment-autolabel.yml` | Auto-labels trusted bot review comments with `autofix:bot-comments` so inline fixes run without human input. |
| [x] | `agents-belt-conveyor.yml` | Alias wrapper around the Codex conveyor; documented accordingly. |
| [x] | `agents-belt-dispatcher.yml` | Alias wrapper around the Codex dispatcher; documented accordingly. |
| [x] | `agents-belt-worker.yml` | Alias wrapper around the Codex worker; documented accordingly. |
| [x] | `agents-bot-comment-handler.yml` | Workflow now auto-runs when trusted bots comment (plus existing triggers); documented the new behavior. |
| [x] | `agents-capability-check.yml` | Still needed as the pre-agent guard; runs the LangChain capability classifier, posts a structured comment, and applies `needs-human` when tasks are blocked. |
| [x] | `agents-debug-issue-event.yml` | Kept as-is; purely dumps GitHub context for label debugging and doesn’t mutate issues. |
| [x] | `agents-decompose.yml` | Removed the redundant GitHub App mint; decomposition now runs entirely via the shared API client before posting subtasks/removing the trigger label. |
| [x] | `agents-dedup.yml` | Dropped the manual App-token mint; duplicate detection now relies on the shared API client while posting warnings for near matches. |
| [x] | `agents-guard.yml` | Removed the redundant App-token mint; guard now relies fully on the shared API client for its safety and label checks. |
| [x] | `agents-issue-optimizer.yml` | Removed the bespoke App-token mint; optimizer now relies on the shared API client for GH CLI access while keeping the analyze/apply/format flow unchanged. |
| [x] | `agents-keepalive-branch-sync.yml` | Left intact—needs the App/PAT token selection to push merges into keepalive branches, but documented the behavior. |
| [x] | `agents-keepalive-dispatch-handler.yml` | Left as-is; needs the explicit token selection to honor compat overrides when handling keepalive repository_dispatch events. |
| [x] | `agents-keepalive-loop-reporter.yml` | Removed the App-token mint; reporter only needs the shared API client to update keepalive summary comments. |
| [x] | `agents-keepalive-loop.yml` | Core keepalive orchestrator; already enforces guardrails/task appendix/agent dispatching via the shared API client, so it stayed as-is and was documented. |
| [x] | `agents-moderate-connector.yml` | Keeps connector noise off PRs by deleting deny-listed bot comments unless they contain real status updates; documented behavior, no workflow change needed. |
| [x] | `agents-pr-meta-v4.yml` | Still required until the consolidated orchestrator lands; handles @agent/Gate activations, dispatch summaries, and keepalive re-dispatch with the expected token chain. |
| [x] | `agents-verifier.yml` | Restored the GitHub App token mint so cross-repo verification checkouts succeed under the service account while still falling back to the shared installation token when App secrets are missing, and explicitly waits for `pr-00-gate.yml`, `pr-11-ci-smoke.yml`, and `selftest-ci.yml` before launching the verifier so we never race Workflows’ own CI. |
| [x] | `agents-verify-to-issue-v2.yml` | Still needed for convert-verify→issue flow; documented behavior with existing PAT/App token chain for opening follow-up issues. |
| [x] | `agents-verify-to-new-pr.yml` | Handles verify:create-new-pr end-to-end; now dispatches agents-auto-pilot directly so no bridge workflow is required. |
| [x] | `agents-weekly-metrics.yml` | Removed the redundant App-token mint; weekly metrics now uses the shared API client/installation token to download artifacts and update the tracking issue. |
| [x] | `autofix.yml` | CI autofix now treats lint/format/Ruff/mypy/pytest failures as relevant so it auto-reruns before humans intervene, and the redundant push trigger was removed to avoid spawning no-op runs on every commit. |
| [x] | `health-40-repo-selfcheck.yml` | Weekly label + branch-protection snapshot still valuable; consider deduping shared helper scripts if more health jobs need the same token plumbing. |
| [x] | `health-40-sweep.yml` | Keeps actionlint + guard coverage; manual runs can now skip guard to save API calls via `run_branch_protection=false`. |
| [x] | `health-41-repo-health.yml` | Added manual inputs to skip branch/PR scans and fixed the env wiring so dispatch overrides no longer break scheduled runs. |
| [x] | `health-42-actionlint.yml` | Removed unused GitHub App token mint so lint reruns skip an extra API call. |
| [x] | `health-43-ci-signature-guard.yml` | Signature fixtures now verified without minting an extra GitHub App token each run. |
| [x] | `health-44-gate-branch-protection.yml` | Removed redundant GitHub App token mint; enforcement already uses `BRANCH_PROTECTION_TOKEN`. |
| [x] | `health-50-security-scan.yml` | Dropped redundant GitHub App token mint; CodeQL already uses PAT fallback chain. |
| [x] | `health-67-integration-sync-check.yml` | Manual runs can toggle CI/version/input checks to avoid unnecessary clone/compare passes. |
| [x] | `health-68-consumer-sync-drift.yml` | Shared helper now lists registered repos, removing inline parsing + easing reuse. |
| [x] | `health-70-validate-sync-manifest.yml` | Switched to shared validator script (now emits summaries + reuse with Health 73). |
| [x] | `health-71-sync-health-check.yml` | Shares the consumer repo helper + no longer mints an app token; only the needed checks run per dispatch knobs. |
| [x] | `health-72-template-sync.yml` | Still needed to auto-sync/validate `.github/scripts` between Workflows and the consumer template; documented behavior (no YAML change required). |
| [x] | `health-73-template-completeness.yml` | Already uses the shared validator script; dropped the unused GitHub App token mint. |
| [x] | `health-74-template-drift.yml` | Drift mapping now includes every agents workflow; still warning-only until residual drift is cleared. |
| [x] | `health-75-api-rate-diagnostic.yml` | Hourly snapshots only; consumer repo scans + load-sharing/access probes now manual inputs to avoid constant PAT/app churn, and the alert job finally reads the correct summary keys. |
| [x] | `health-claude-cli-auth-debug.yml` | Archived under `archives/diagnostics/` so the active health roster only contains automated monitors. |
| [x] | `health-codex-auth-check.yml` | Removed the extra GitHub App token mint so the twice-daily expiry check only makes the issue list/create calls it actually needs. |
| [x] | `health-keepalive-auth-diagnostic.yml` | Archived alongside the Claude CLI diagnostic so the health roster only tracks automated monitors; manual keepalive auth drills now live under `archives/diagnostics/`. |
| [x] | `health-keepalive-e2e.yml` | Dropped the duplicate GitHub App token mints so orchestration-only runs stick to the default installation token while keeping the Codex ping path unchanged. |
| [x] | `maint-39-test-llm-providers.yml` | Manual LLM credential test no longer mints a GitHub App token or overrides checkout auth, so the diagnostic run stays lightweight. |
| [x] | `maint-45-cosmetic-repair.yml` | Dropped the App token mint and only create PRs when not in dry-run mode to save API calls. |
| [x] | `maint-46-post-ci.yml` | Only boots the helper checkout + token-balanced client when Gate's summary is missing, removing the extra app-token mint. |
| [x] | `maint-47-disable-legacy-workflows.yml` | Removed the unused App-token mint; the disable helper now relies on the default workflow token only. |
| [x] | `maint-50-tool-version-check.yml` | Dropped the app-token mint + duplicate checkout; now relies on the default token + load-balanced client for issuing updates. |
| [x] | `maint-51-dependency-refresh.yml` | Removed the extra App token mint; dependency refresh now relies on the default workflow token for checkout + PR pushes. |
| [x] | `maint-52-sync-dev-versions.yml` | Removed all App-token mints and now reuse `list_registered_consumer_repos.py` for repo discovery. |
| [x] | `maint-52-validate-workflows.yml` | Removed the App-token mint; actionlint now runs with repo-only access since it never hits the API. |
| [x] | `maint-60-release.yml` | Floating-tag update + release now uses only the default token (removed the App-token mint). |
| [x] | `maint-61-create-floating-v1-tag.yml` | Deprecated fallback—removed the redundant App-token mint; consider archiving since maint-73 owns floating tags. |
| [x] | `maint-62-integration-consumer.yml` | Removed the extra App-token mint; issue updates now rely on the reusable API client already in the job. |
| [x] | `maint-65-sync-label-docs.yml` | Reused the registered-repo helper and dropped the App-token mint for the doc sync. |
| [x] | `maint-66-monthly-audit.yml` | Dropped the App-token mint + redundant npm install; audit uses the shared API client only. |
| [x] | `maint-68-sync-consumer-repos.yml` | Removed all App-token mints; sync jobs rely on PATs + the shared API client now. |
| [x] | `maint-69-sync-integration-repo.yml` | Removed the App-token mint; integration sync now relies on the default token + PAT used for pushes. |
| [x] | `maint-69-sync-labels.yml` | Removed the App-token mint + duplicate checkout and now reuse the registered-repo helper for targets. |
| [x] | `maint-70-fix-integration-formatting.yml` | Uses the shared API client + PAT discovery; skips safely when no integration token is available. |
| [x] | `maint-71-auto-fix-integration.yml` | Uses the shared API client + PAT discovery and skips safely when no integration token exists. |
| [x] | `maint-71-merge-sync-prs.yml` | Uses the shared repo helper + PATs; no App-token mints and cleaner repo parsing. |
| [x] | `maint-72-fix-pr-body-conflicts.yml` | Uses shared repo list + PAT detection; skips safely when no push token exists. |
| [x] | `maint-73-refresh-reusable-tags.yml` | Deprecated; workflow now exits immediately with a notice instead of touching tags. |
| [x] | `maint-74-ledger-base-sync.yml` | No longer mints an App token; relies on the default token + shared client. |
| [x] | `maint-80-langsmith-metrics-dashboard.yml` | Reviewed; no changes needed—the dashboard already aggregates autopilot artifacts + refreshes docs weekly. |
| [x] | `maint-auto-update-pypi-versions.yml` | Removed the App-token mint; workflow now relies on the default token for repo operations. |
| [x] | `maint-coverage-guard.yml` | Removed rate-limit + guard job App-token mints; shared API client handles retries. |
| [x] | `maint-dependabot-auto-label.yml` | Reviewed – already minimal (gh CLI adds label via default token). |
| [x] | `maint-dependabot-auto-lock.yml` | Reviewed – regenerates requirements.lock via uv when Dependabot touches pyproject. |
| [x] | `maint-dependabot-weekly-sweep.yml` | Uses the shared repo helper instead of an inline parser for consumer roster. |
| [x] | `maint-sync-action-versions.yml` | Reviewed – already syncing template action pins via automated PRs. |
| [x] | `maint-sync-env-from-pyproject.yml` | Dropped the app-token mint; env sync now commits with the default token. |
| [x] | `pr-00-gate.yml` | Still the required PR orchestrator; ledger-validation now inherits the doc-only fast-path so README-only PRs skip the Python boot/install cycle while full runs continue to guard `.agents/**` ledgers. |
| [x] | `pr-11-ci-smoke.yml` | Keeps the YAML + scripts sanity checks on every push/PR, and now skips minting a GitHub App token since the job never leaves the repo (default token is enough). |
| [x] | `reusable-10-ci-python.yml` | Python lint/type/test reusable already supports uv caching + PAT/App fallback; the optional App token mint remains useful for repos that installed the Workflows app, so only documentation updates were needed. |
| [x] | `reusable-11-ci-node.yml` | Node lint/type/test reusable stays the JS/TS CI entry point (ESLint, Prettier, tsc, Jest/Vitest) and now relies solely on the default workflow token since it never touches other repos. |
| [x] | `reusable-12-ci-docker.yml` | Docker smoke reusable builds the repo image and curls the health endpoint; dropped the unused GitHub App mint so it runs entirely with the default token. |
| [x] | `reusable-16-agents.yml` | Shared agents toolkit invoked by orchestrator; now adds `preflight_overrides_json` plus registry-driven multi-agent preflight probes while still gating readiness, diagnostics, bootstrap, watchdog, keepalive, and verify flows with PAT/App fallbacks + `options_json` for dry-runs. |
| [x] | `reusable-18-autofix.yml` | Gate’s formatter harness already handles App/PAT/default-token fallback, writes commits for same-repo PRs, uploads patches when push is blocked, and surfaces delivery metadata—no YAML changes required. |
| [x] | `reusable-20-pr-meta.yml` | Consumer PR meta/keepalive reusable; removed GitHub App token mints so comment/gate/PR-body lanes rely on the provided PATs/default token only. |
| [x] | `reusable-70-orchestrator-init.yml` | Handles rate-limit checks, idle detection, keepalive token selection, and parameter resolution; uses GitHub App token only when needed for keepalive writes, so no changes were required. |
| [x] | `reusable-70-orchestrator-main.yml` | Runs the orchestrator stages (keepalive gate, readiness, bootstrap, keepalive, etc.) using the init outputs; App token mint is still required when PATs are absent because keepalive writes must run as `agents-workflows-bot`. |
| [x] | `reusable-agents-issue-bridge.yml` | Multi-agent issue → PR bridge already reads the agent registry; removed the unused GitHub App token mint so it runs on the provided PAT/default token chain only. |
| [x] | `reusable-agents-verifier.yml` | Verifier reusable now mints the Workflows App token up front so it can clone both the caller repo and the Workflows scripts even for private consumers, with automatic fallback to the caller token when App creds aren’t wired, and its CI wait loop tracks every configured workflow until each one has both started and completed. |
| [x] | `reusable-bot-comment-handler.yml` | Multi-agent bot comment resolver; callers now pass `GH_APP_CLIENT_ID`, the reusable records whether client-ID, legacy App ID, or no App auth was selected, and the legacy path stays warning-only until all installs migrate. |
| [x] | `reusable-claude-run.yml` | Claude CLI runner mirrors Codex parity: mints the Workflows App token for pushes, installs the shared setup-api-client/Workflows scripts with blobless-clone guards, exposes prompt/runtime/safety inputs, and reuses the repo checkout across keepalive/autofix callers. |
| [x] | `reusable-codex-run.yml` | Codex runner keeps the App-token-first auth chain so it can push commits when available; falls back to read-only runs with `GITHUB_TOKEN`, so no YAML edits were needed. |
| [x] | `reusable-pr-context.yml` | GraphQL PR context fetcher already minimizes API calls; optional App token usage is still beneficial for higher rate limits, so only documentation updates were required. |
| [x] | `selftest-ci.yml` | Removed the redundant GitHub App token mints from JS, Python, and lint jobs—selftests now run entirely on the default workflow token since they only operate on this repo. |
| [x] | `selftest-reusable-ci.yml` | Self-test harness already reuses the Python CI composite via matrix scenarios; no App tokens or extra plumbing required, so documentation-only update. |
