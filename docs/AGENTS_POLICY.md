# Agents Workflow Protection Policy

> **Authoritative policy.** This document (`docs/AGENTS_POLICY.md`) is the single
> authoritative Agents Workflow Protection Policy for `stranske/Workflows`.
> [`docs/ci/AGENTS_POLICY.md`](ci/AGENTS_POLICY.md) is a pointer to this file.

The agents orchestration, intake, keepalive, and guard workflows are
contract-critical automation. They must remain protected unless a maintainer
deliberately follows the allowlisted change or emergency override procedures
described below. Legacy consumer shims (`agents-61-consumer-compat.yml`,
`agents-62-consumer.yml`) and the standalone ChatGPT wrapper
(`agents-63-chatgpt-issue-sync.yml`) are retired and must not be reintroduced.

[Agents 63 Issue Intake](../.github/workflows/agents-63-issue-intake.yml)
handles manual intake and ChatGPT import in Workflows.
[Agents Issue Intake](../templates/consumer-repo/.github/workflows/agents-issue-intake.yml)
is the corresponding consumer workflow. The
[shared opener and closer](ops/LOCAL_LANES.md#lanes-overview) own ordinary
issue-to-PR claims and guarded promotion.

Gate completion and hourly sweep dispatches reach the
[Workflows keepalive loop](../.github/workflows/agents-keepalive-loop.yml)
or [consumer Gate Followups](../templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml).
The [Workflows PR-meta comment path](keepalive/Observability_Contract.md#comment-activation)
checks dispatch occupancy and submits a separate remediation command.

## Covered files

- `.github/workflows/agents-63-issue-intake.yml`
- `.github/workflows/agents-guard.yml`

These workflows anchor this policy and its verification checklist.
The guard workflow (`agents-guard.yml`) is co-protected because it enforces the
protected-workflow policy in CI; losing or renaming it would remove the
automated safety net. At runtime, `.github/scripts/agents-guard.js` applies
`DEFAULT_PROTECTED_PATHS = ['.github/workflows/agents-*.yml']` across the
`agents-*.yml` surface (excluding the utility workflow
`agents-64-verify-agent-assignment.yml` and allowlisted legacy or
consumer-template removals). Workflows listed in `CONSUMER_ONLY_ALLOW_REMOVED_PATHS`
may be removed only in consumer repositories (not in `stranske/Workflows`):

- `.github/workflows/agents-keepalive-loop.yml`
- `.github/workflows/agents-autofix-loop.yml`
- `.github/workflows/agents-bot-comment-handler.yml`
- `.github/workflows/agents-verify-to-issue-v2.yml`
- `.github/workflows/agents-verify-to-new-pr-autopilot.yml`
- `.github/workflows/agents-orchestrator.yml`

In consumers, `agents-80-pr-event-hub.yml` and `agents-81-gate-followups.yml`
replace those workflows. The guard evaluates other protected workflow deletions
against its executable allowlists. Former consumer wrappers (`agents-61-consumer-compat.yml`,
`agents-62-consumer.yml`) and `agents-63-chatgpt-issue-sync.yml` must not be
reintroduced.

## Retired Agents 70 orchestrator stack (qualified historical)

The following Workflows-local workflows were retired from the active control
plane: `agents-70-orchestrator.yml`, `reusable-70-orchestrator-init.yml`,
`reusable-70-orchestrator-main.yml`, and `reusable-16-agents.yml`. Consumer sync
tombstones and archive entries for the former consumer-facing orchestrator
shim remain authoritative for receiver repos; local versus hosted consumer seat
cutover is unchanged by this retirement.

- **Shadow mode (historical, qualified).** Until retirement, scheduled Agents 70
  runs forced `dry_run=true` as an A1 orchestrator-retirement shadow (historically
  attributed to commit `0ecdff0f3` / PR `#2351`; qualified to authored git/workflow
  history). That shadow is no longer an active operator surface.
- **Replacement surfaces (current).** Gate-completion keepalive runs in
  [`.github/workflows/agents-keepalive-loop.yml`](../.github/workflows/agents-keepalive-loop.yml);
  hourly stalled-PR resync runs in
  [`.github/workflows/agents-keepalive-sweep.yml`](../.github/workflows/agents-keepalive-sweep.yml);
  the [shared opener and closer](ops/LOCAL_LANES.md#lanes-overview) own issue-to-PR claims and exact-head promotion;
  ad-hoc issue verification uses
  [`.github/workflows/agents-64-verify-agent-assignment.yml`](../.github/workflows/agents-64-verify-agent-assignment.yml).
- **PR-meta dispatch (#5162).** `agents-pr-meta-v4.yml` submits the
  `codex-pr-comment-command` event to the Workflows dispatch handler.
  The comment admission path measures worker occupancy as documented in
  [#5163](https://github.com/stranske/Workflows/pull/5163).
- **Agent PR promotion.** The [shared closer](ops/LOCAL_LANES.md#lanes-overview) checks the current PR head, required checks, and review clearance before merging.

## Protection layers

1. **CODEOWNERS notifications** – GitHub uses
   [`.github/CODEOWNERS`](../.github/CODEOWNERS) to notify listed owners.
   Workflows requires zero approving reviews and has no GitHub Code Owner
   review requirement on `main`. The guard can read the same file for its
   own authorization decisions on eligible protected-file changes. For
   a receiving repository, verify its own effective review rules.
2. **Repository branch rules** – the effective rules for `main` include branch
   deletion and non-fast-forward protection. The live branch readback below
   shows which ruleset supplied each rule. A branch deletion rule applies to
   the branch ref. File-level delete and rename enforcement for the covered
   workflows is the job of the CI guard and this policy.
3. **CI guardrail** – the `Health 45 Agents Guard` check (see
   `.github/workflows/agents-guard.yml`) applies its file and authorization
   controls to eligible pull requests. For protected modifications, it accepts
   Code Owner authorship or approval. It also accepts dependency-only
   `uses: owner/action@ref` updates carrying `agents:allow-change` when the
   author is Dependabot, Renovate, or a repository owner, member, or
   collaborator. A label alone cannot authorize other protected edits.
   The guard separately reports prohibited deletions or renames.
4. **GitHub required status checks** – the active default-branch ruleset
   requires the Gate aggregate job `summary`. GitHub reports strict
   required-status-check enforcement disabled. GitHub's separate pull-request
   rule currently reports `require_code_owner_review: false` and
   `required_approving_review_count: 0`. Evaluate protected changes using
   the applicable Health 45 controls above.

## Required checks and status contexts

- **Gate** runs the CI matrix or docs checks and aggregates their results in
  the required `summary` job. The same job publishes the compatibility commit
  status `Gate / gate` on same-repository PRs. The
  [trusted Gate fork publisher](../.github/workflows/pr-00-gate-fork-status.yml)
  publishes the exact-head status for eligible fork PRs.
- **Health 45 Agents Guard** evaluates protected-file changes on eligible pull
  requests. It publishes the separate commit status
  `Health 45 Agents Guard / guard` for eligible agent-labelled PRs. For forks,
  the [trusted status publisher](../.github/workflows/agents-guard-fork-status.yml)
  publishes the verdict for the exact head after the canonical guard run.
- **Health 44 Gate Branch Protection** audits the required configuration and
  records its results in `enforcement.json` and `verification.json` when those
  steps run. The expected GitHub list lives in
  [`.github/config/required-contexts.json`](../.github/config/required-contexts.json).
  The two commit statuses above are outside that list.

## How to verify required checks

1. Read the effective rules for `main` and identify each source ruleset.

   ```bash
   gh api repos/stranske/Workflows/rules/branches/main \
     --jq '[.[] | {type, ruleset_id, ruleset_source, ruleset_source_type, parameters}]'
   ```

   The `required_status_checks` rule should list `summary` with
   `strict_required_status_checks_policy: false`. The `pull_request` rule
   shows GitHub's current review enforcement. If the legacy
   `branches/main/protection` endpoint returns HTTP 404, use this effective
   branch readback. Record rule types and sources before attributing
   enforcement to a particular ruleset.
2. Compare the configured requirements with the checked-in list. These
   read-only commands work when
   [Health 44](https://github.com/stranske/Workflows/actions/workflows/health-44-gate-branch-protection.yml)
   produces no artifact.

   ```bash
   main_sha=$(gh api repos/stranske/Workflows/git/ref/heads/main --jq .object.sha)
   gh api "repos/stranske/Workflows/contents/.github/config/required-contexts.json?ref=$main_sha" \
     --jq '.content | @base64d | fromjson | .required_contexts | sort'
   gh api repos/stranske/Workflows/rules/branches/main \
     --jq '[.[] | select(.type == "required_status_checks") | .parameters.required_status_checks[].context] | unique'
   ```

   Both lists should be `["summary"]`. Record the main SHA, rule output, and
   the latest Health 44 run with any available artifacts if the lists differ.
   Record absent artifacts explicitly. Ask a repository maintainer to
   reconcile the discrepancy and repeat the readback.
3. On the PR, confirm that `summary` succeeded on its current head. For a
   protected-file change, verify the applicable Health 45 authorization
   and verdict on that head. Open the `guard` job from the
   canonical [Health 45 run](https://github.com/stranske/Workflows/actions/workflows/agents-guard.yml).
   Set `guard_job_id` and `guard_run_id` from the job URL and `pr_number`
   from the pull request URL.

   ```bash
   gh api "repos/stranske/Workflows/actions/jobs/$guard_job_id" \
     --jq '{head_sha, run_id, run_attempt, conclusion, evaluation: [.steps[] | select(.name == "Evaluate protected file changes") | .conclusion]}'
   gh api "repos/stranske/Workflows/actions/runs/$guard_run_id" \
     --jq '{path, head_sha, run_attempt}'
   gh api "repos/stranske/Workflows/pulls/$pr_number" --jq .head.sha
   gh api --paginate "repos/stranske/Workflows/pulls/$pr_number/files" \
     --jq '.[] | {filename, previous_filename}'
   ```

   Match the job and canonical run to the PR head, and match the job's run
   ID and attempt to the current run. A successful job with
   `evaluation: ["skipped"]` is a green no-op. An empty
   evaluation list is missing evidence. An evaluated pass requires both
   `evaluation: ["success"]` and a successful job conclusion. Check the PR's
   file list at the same head to establish whether the selected step examined
   a protected-file change, including the previous path for a rename. Read
   the PR head again after listing files. If the head or policy labels
   changed, use the current verdict. For forks, inspect
   the canonical guard run supplying the trusted publisher's exact-head
   status. Check any documented guard-level exception against the actual diff.

## Allowlisted change reasons and label process

Only the following scenarios justify edits to protected workflows. If your
proposal does not fit, open an ops discussion before touching the files.

- **Security response** – rotating a compromised secret, pinning a patched
  Action version, or patching a supply-chain CVE that affects execution.
- **Reliability fix** – addressing a regression that stops intake, eligibility,
  branch creation, keepalive routing, or orchestrator execution.
- **Policy maintenance** – updating links, documentation pointers, or metadata
  to keep references accurate after broader restructuring.
- **Platform migration** – adapting to a GitHub Actions deprecation announced by
  GitHub (for example, new runner images or permissions requirements).

When one of these scenarios applies:

1. File or link to the tracking issue describing the incident and expected fix.
2. A maintainer adds the `agents:allow-change` label to the pull request
   **after** confirming the change reason fits the allowlist.
3. Ensure the PR body includes the incident or policy context plus rollback
   steps.
4. Verify the Health 45 result when its protected-file evaluation applies.
   Act on any remaining guard finding using the controls above.
5. Remove the label once merged so the guardrail resumes full enforcement on
   future PRs.

## Emergency override procedure

1. Confirm the incident really requires editing or temporarily removing one of
   the protected workflows.
2. Use the effective rules readback to identify which GitHub rule, if any,
   blocks the required action. Only a maintainer with admin access may
   temporarily adjust that rule or apply a bypass. Handle the independent
   Health 45 verdict through its documented policy.
3. Apply the change in a dedicated pull request and verify the applicable
   Health 45 and Gate results.
4. Restore any controls changed for the override immediately after the change
   merges. Document the incident and restoration steps in the associated issue
   or runbook entry.

## Troubleshooting

- **Guard check failing for “missing agents:allow-change label”.** Add the label
  (maintainers only) or revert the workflow edits. The check re-evaluates once
  the label is present.
- **Health 45 blocks a protected edit.** Read the exact-head evaluation
  and follow the applicable authorization or file-restoration path in the
  verdict. If the change cannot be made within that path, record the
  guard failure and leave the protected change unmerged.
- **Ruleset rejection on push.** Confirm you are operating on a maintainer-owned
  branch or request a maintainer to apply a temporary bypass while they assist
  with the change.
- **Troubleshooting a Gate or repository event.** Inspect
  `agents-keepalive-loop.yml` in Workflows or `agents-81-gate-followups.yml` in
  a consumer. Use the [sweep path for that repository](keepalive/GoalsAndPlumbing.md#periodic-re-evaluation-keepalive-sweep)
  to trace a scheduled recheck.

## Verification checklist

- The effective default-branch rules match the checked-in required contexts.
  For protected-file changes, verify the applicable authorization and
  Health 45 verdict separately.
- Record the effective branch rule types and source. For a covered-file
  change, confirm the protected-file evaluation step ran on the exact PR head
  and verify the verdict against the changed paths.
- A maintainer can describe the override procedure without referencing this
  document (spot check during ops reviews).
