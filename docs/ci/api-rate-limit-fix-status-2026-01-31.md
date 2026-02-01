# API rate limit fixes (week ending 2026-01-31)

## Diagnostic run
- Workflow: Health 75 API Rate Diagnostic
- Run: https://github.com/stranske/Workflows/actions/runs/21548256856
- Status: success

## Recent PRs that targeted rate limit issues

> Scope: PRs merged since 2026-01-24 that explicitly address API rate limits, token load balancing, or keepalive/autofix reliability tied to rate limits.

### #1135 — fix: add rate-limit-aware retry to high-frequency scripts (#1136)
- URL: https://github.com/stranske/Workflows/pull/1135
- Intended fix: Add token-aware retry wrappers to high-frequency scripts (keepalive/post-CI).
- Progress: ✅ Introduced retry wrapper and applied to core scripts.
- Why not fully resolved: Some workflows still call GitHub APIs directly without the wrapper (e.g., PR Meta default-branch lookup).
- Remaining work: Apply token-aware retry (or avoid the API call entirely) in reusable PR meta.

### #1139 — fix(#1136): add paginate.iterator support to rate-limit wrapper
- URL: https://github.com/stranske/Workflows/pull/1139
- Intended fix: Ensure pagination uses the same retry strategy to avoid secondary rate limit failures.
- Progress: ✅ Wrapper now supports paginate.iterator.
- Why not fully resolved: Does not affect API calls that bypass the wrapper.
- Remaining work: Ensure all PR Meta calls use the wrapper or avoid API calls.

### #1151 — fix: fall back when resolving Workflows ref
- URL: https://github.com/stranske/Workflows/pull/1151
- Intended fix: Avoid hard failures when default branch lookup is rate-limited (fallback to main).
- Progress: ✅ Added fallback.
- Why not fully resolved: Applied to Autofix ref resolution only, not to PR Meta default-branch lookup.
- Remaining work: Mirror fallback logic (or eliminate lookup) in PR Meta.

### #1142 — feat: standardize token export for retry helpers (#1142)
- URL: https://github.com/stranske/Workflows/pull/1142
- Intended fix: Make token rotation data available to retry helpers.
- Progress: ✅ Standardized token export and updated helpers.
- Why not fully resolved: Workflows must still install node deps and actually use token-aware clients.
- Remaining work: Ensure PR Meta uses token-aware retry and has deps available.

### #1161 — fix: stabilize keepalive load balancing
- URL: https://github.com/stranske/Workflows/pull/1161
- Intended fix: Improve keepalive token load balancing and reporting.
- Progress: ✅ Keepalive load balancing stabilized.
- Why not fully resolved: Missing Node deps caused load balancer imports to fail until #1170.
- Remaining work: None for keepalive, but PR Meta still lacks token-aware flow.

### #1162 — fix: export load balancer tokens in keepalive
- URL: https://github.com/stranske/Workflows/pull/1162
- Intended fix: Export token rotation secrets so keepalive can choose tokens with capacity.
- Progress: ✅ Tokens exported in keepalive jobs.
- Why not fully resolved: PR Meta uses a separate reusable workflow path without those exports.
- Remaining work: Align PR Meta workflow with token export + retry logic.

### #1148 — Sync export-load-balancer-tokens action to consumer repos (#1143)
- URL: https://github.com/stranske/Workflows/pull/1148
- Intended fix: Ensure consumer repos get the token export action updates.
- Progress: ✅ Synced to consumers.
- Why not fully resolved: PR Meta still hits rate limits during default-branch lookup.
- Remaining work: Update reusable PR meta workflow.

### #1154 — fix: issue-4160 install diagnostic deps in workspace
- URL: https://github.com/stranske/Workflows/pull/1154
- Intended fix: Install @octokit deps for the API rate diagnostic workflow.
- Progress: ✅ Diagnostic workflow now has required deps.
- Why not fully resolved: Diagnostic workflow is separate from PR Meta execution path.
- Remaining work: Install deps where PR Meta uses token load balancer (if adopted there).

### #1168 — fix(autofix): include guard dependency
- URL: https://github.com/stranske/Workflows/pull/1168
- Intended fix: Add missing dependency to sparse checkout for autofix security gate.
- Progress: ✅ Autofix security gate now loads dependencies.
- Why not fully resolved: Autofix only; PR Meta still calls GitHub API directly.
- Remaining work: Update PR Meta path.

### #1169 — fix(autofix): include token load balancer
- URL: https://github.com/stranske/Workflows/pull/1169
- Intended fix: Ensure token load balancer is available for autofix security gate.
- Progress: ✅ Autofix now loads token load balancer.
- Why not fully resolved: Does not affect PR Meta.
- Remaining work: Update PR Meta path.

### #1170 — fix(keepalive): install octokit deps
- URL: https://github.com/stranske/Workflows/pull/1170
- Intended fix: Install @octokit/rest and @octokit/auth-app so keepalive can mint app tokens and check rate limits.
- Progress: ✅ Keepalive now installs deps.
- Why not fully resolved: PR Meta still uses API calls without retry/fallback and without explicit token rotation.
- Remaining work: Update PR Meta workflow logic.

## What still needs to be done

1. **Eliminate rate-limit API calls in PR Meta default-branch lookup.**
   - In reusable-20-pr-meta.yml, the "Resolve Workflows default branch" step uses `repos.get` and fails when installation tokens are rate-limited (seen in Trend_Model_Project PR #4613). 
   - Prefer `context.payload.repository.default_branch` when available, and fall back to `main` (similar to #1151), or cache the result to avoid repeated API calls.

2. **Apply token-aware retry to PR Meta GitHub calls.**
   - Wrap PR Meta GitHub calls with the rate-limited wrapper or token-aware retry helpers from #1135/#1139.

3. **Ensure PR Meta has the same dependency setup as keepalive.**
   - If PR Meta adopts token load balancer logic, it must install @octokit/rest and @octokit/auth-app (mirroring keepalive).

## Evidence of remaining issue
- Trend_Model_Project PR #4613 failing check: `pr_meta_pr / Update PR body sections`.
- Error: API rate limit exceeded while resolving Workflows default branch via `github.rest.repos.get`.

## 2026-02-01 update

### Audit result
- Verified all workflows using `createTokenAwareRetry` / `ensureRateLimitWrapped` now export load balancer tokens earlier in the same job.
- Fixed missing export steps in these workflows:
   - `selftest-reusable-ci.yml`
   - `health-75-api-rate-diagnostic.yml`
   - `reusable-18-autofix.yml`
   - `agents-63-issue-intake.yml`
   - `reusable-16-agents.yml`
   - `agents-keepalive-loop.yml`

### Post-merge verification plan
1. Run **Agents 70 Keepalive Loop** once in the Workflows repo with a valid PR number and high-privilege environment.
2. Confirm logs show `Token registry initialized with N tokens` where **N > 0** and multiple sources are listed.
3. Confirm at least one retry log entry shows token rotation/switching for the `keepalive-loop` task.
4. Run **Health 75 API Rate Diagnostic** and confirm the `Load-sharing switch verified` step passes.
5. Spot-check a consumer repo keepalive job to confirm the export step precedes any token-aware retry usage.

If any step fails, stop and fix before declaring success.
