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

In the current topology, issue intake flows through
[`.github/workflows/agents-63-issue-intake.yml`](../.github/workflows/agents-63-issue-intake.yml),
authored Gate-completion and hourly keepalive sweeps live in
[`.github/workflows/agents-keepalive-loop.yml`](../.github/workflows/agents-keepalive-loop.yml)
and [`.github/workflows/agents-keepalive-sweep.yml`](../.github/workflows/agents-keepalive-sweep.yml),
standalone issue-to-PR queue automation runs through the Codex belt
([`.github/workflows/agents-71-codex-belt-dispatcher.yml`](../.github/workflows/agents-71-codex-belt-dispatcher.yml),
[`.github/workflows/agents-72-codex-belt-worker-dispatch.yml`](../.github/workflows/agents-72-codex-belt-worker-dispatch.yml),
[`.github/workflows/agents-72-codex-belt-worker.yml`](../.github/workflows/agents-72-codex-belt-worker.yml),
and [`.github/workflows/agents-73-codex-belt-conveyor.yml`](../.github/workflows/agents-73-codex-belt-conveyor.yml)),
and [`.github/workflows/agents-70-orchestrator.yml`](../.github/workflows/agents-70-orchestrator.yml)
remains protected while operating in scheduled dry-run shadow mode with
input-controlled manual dispatch.

## Covered files

- `.github/workflows/agents-63-issue-intake.yml`
- `.github/workflows/agents-70-orchestrator.yml`
- `.github/workflows/agents-guard.yml`

These three workflows anchor this policy and its verification checklist.
The guard workflow (`agents-guard.yml`) is co-protected because it enforces the
protected-workflow policy in CI; losing or renaming it would remove the
automated safety net. At runtime, `.github/scripts/agents-guard.js` applies
`DEFAULT_PROTECTED_PATHS = ['.github/workflows/agents-*.yml']` across the
`agents-*.yml` surface (excluding the utility workflow
`agents-64-verify-agent-assignment.yml` and allowlisted legacy or
consumer-template removals; `.github/workflows/agents-70-orchestrator.yml` and
`.github/workflows/agents-keepalive-loop.yml` are allowlisted for removal only in
consumer repositories, where `agents-80-pr-event-hub.yml` and
`agents-81-gate-followups.yml` replace them, and remain blocked from deletion in
`stranske/Workflows`). Former consumer wrappers (`agents-61-consumer-compat.yml`,
`agents-62-consumer.yml`) and `agents-63-chatgpt-issue-sync.yml` must not be
reintroduced.

## Agents 70 Orchestrator event eligibility and shadow mode

[`.github/workflows/agents-70-orchestrator.yml`](../.github/workflows/agents-70-orchestrator.yml)
declares `schedule` and `workflow_dispatch`. The eligibility action
(`expected-actions: workflow_dispatch,schedule`) checks events before
`jobs.init`, which calls
[`.github/workflows/reusable-70-orchestrator-init.yml`](../.github/workflows/reusable-70-orchestrator-init.yml).

| Event | Trigger and behavior |
| --- | --- |
| `schedule` (`*/30 * * * *`) | Runs the shadow preview with forced `dry_run=true`, including the scheduled credential-budget probe. |
| `workflow_dispatch` | Preserves operator and PR-meta calls. `inputs.dry_run` defaults to `'false'`; operators can request a preview. |
| `workflow_run` (`Gate` `completed`) | The shared `agents-keepalive-loop.yml` handles the event. The old Agents 70 registration reached only the eligibility job. |
| `repository_dispatch` (`agents-orchestrator-ping`) | The former registration was denied before `jobs.init`; callers use the `workflow_dispatch` inputs above. |

### Shadow rationale and undecided retirement decision

- **Shadow rationale (historical attribution qualified).** Inline comments at
  the original Agents 70 workflow describe scheduled `dry_run=true` as the A1
  orchestrator-retirement shadow (historically
  attributed to commit `0ecdff0f3` / PR `#2351`; this attribution is qualified to
  authored git/workflow history until runtime shadow coverage is independently
  verified). The shadow forces scheduled orchestrator runs to execute without
  writes while evaluating whether replacement workflows cover Agents 70's roles.
- **Authored replacement sources vs. observed coverage.** In workflow source,
  Gate-completion keepalive evaluations and manual retries are authored in
  [`.github/workflows/agents-keepalive-loop.yml`](../.github/workflows/agents-keepalive-loop.yml)
  (`workflow_run` on `Gate` `completed`, `pull_request` `labeled`, and
  `workflow_dispatch`), and hourly level-based stalled-PR resyncs are authored in
  [`.github/workflows/agents-keepalive-sweep.yml`](../.github/workflows/agents-keepalive-sweep.yml)
  (`schedule` `23 * * * *` and `workflow_dispatch`). Inspecting workflow YAML
  establishes only this authored configuration; it does **not** prove production
  liveness or complete runtime coverage of the replacement loop and sweep.
- **Undecided delete-versus-restore question and required evidence.** Whether to
  retire (`delete` `agents-70-orchestrator.yml` and
  `reusable-70-orchestrator-main.yml`) or `restore` live automatic execution
  remains **undecided**. Before making a delete-versus-restore decision,
  maintainers must gather:
  1. **Observed runtime coverage evidence** from production Actions runs and
     artifacts showing that `agents-keepalive-loop.yml`,
     `agents-keepalive-sweep.yml`, and the standalone `agents-71/72/73` belt
     workflows sustain keepalive progression, stalled-PR recovery, readiness /
     bootstrap / diagnostics, and belt handoffs without unrecovered stalls.
  2. **Caller and guard dependency audit** covering remaining references to
     `agents-70-orchestrator.yml` (such as
     `.github/scripts/agents_pr_meta_orchestrator.js`,
     `.github/scripts/keepalive_gate.js`, `.github/scripts/agents-guard.js`, and
     operator runbooks) so removal or restoration does not strand dispatches or
     violate guard contracts.
  3. **Explicit maintainer disposition** in a tracked issue, with the
     resulting pull request following the applicable Health 45 controls.
     Until the decision lands, `agents-70-orchestrator.yml` remains
     protected under this policy.

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
  status `Gate / gate`.
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
- **Troubleshooting a Gate or repository event.** Inspect the shared
  `agents-keepalive-loop.yml` for Gate completions and
  `agents-keepalive-sweep.yml` for scheduled recovery. Agents 70 accepts
  `workflow_dispatch` for manual and PR-meta calls, and its `schedule` runs
  with `dry_run=true` for the credential-budget probe and preview.

## Verification checklist

- The effective default-branch rules match the checked-in required contexts.
  For protected-file changes, verify the applicable authorization and
  Health 45 verdict separately.
- Record the effective branch rule types and source. For a covered-file
  change, confirm the protected-file evaluation step ran on the exact PR head
  and verify the verdict against the changed paths.
- A maintainer can describe the override procedure without referencing this
  document (spot check during ops reviews).
