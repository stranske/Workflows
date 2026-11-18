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

These three workflows anchor the repository ruleset and verification checklist.
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
declares four triggers under `on:`, but `jobs.eligibility`
(`.github/actions/agent-event-eligibility`) and `jobs.init`
(`if: needs.eligibility.outputs.should_run == 'true'`, calling
[`.github/workflows/reusable-70-orchestrator-init.yml`](../.github/workflows/reusable-70-orchestrator-init.yml))
enforce the following four-event behavior:

| Event | Declared in `on:`? | `jobs.eligibility` (`expected-actions: workflow_dispatch,schedule`) | Reaches `jobs.init` / `jobs.main`? | `jobs.init` `dry_run` behavior |
| --- | --- | --- | --- | --- |
| `schedule` (`*/30 * * * *`) | Yes | **Admitted** (`should_run == 'true'`) | Yes | **Forced dry-run shadow** (`'true'` via `(github.event_name == 'schedule' \|\| github.event_name == 'workflow_run') && 'true'`) |
| `workflow_dispatch` | Yes | **Admitted** (`should_run == 'true'`) | Yes | **Input-controlled** (`github.event.inputs.dry_run`, default `'false'`; manual runs can execute live writes when `dry_run=false`) |
| `workflow_run` (`Gate` `completed`) | Yes | **Denied before `init`** (`should_run != 'true'`) | No | Not reached (`init.with.dry_run` still mentions `workflow_run`, but `eligibility` blocks the event before `init`) |
| `repository_dispatch` (`agents-orchestrator-ping`) | Yes | **Denied before `init`** (`should_run != 'true'`) | No | Not reached (`init.with` still contains `repository_dispatch` payload expressions, but `eligibility` blocks the event before `init`) |

### Shadow rationale and undecided retirement decision

- **Shadow rationale (historical attribution qualified).** Inline comments at
  `.github/workflows/agents-70-orchestrator.yml:108-112` describe the `schedule`
  `dry_run=true` clause as the A1 orchestrator-retirement shadow (historically
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
  3. **Explicit maintainer disposition** via a tracked issue and Code
     Owner-approved pull request carrying `agents:allow-change`. Until that
     decision lands, `agents-70-orchestrator.yml` remains protected under this
     policy.

## Protection layers

1. **CODEOWNERS gate** – the files above are owned by `@stranske` in
   `.github/CODEOWNERS`. Pull requests cannot merge changes to them without Code
   Owner approval. In the default branch protection rule, enable **Require review
   from Code Owners** so GitHub enforces the restriction automatically.
2. **Repository ruleset** – create (or update) a ruleset that targets the
   default branch (`Tests Pass to Merge`, ruleset ID `7880490`) and blocks
   deletions or renames of the covered workflows (`restrict_file_updates` with
   **Block deletions** and **Block renames** enabled). Use the protected file
   patterns listed above and set the bypass mode to *Maintainers only* so
   emergencies still require a deliberate maintainer action. Administrators can
   provision the ruleset through the repository settings (**Settings → Code
   security and analysis → Rulesets → New ruleset → Branch**). Capture
   screenshots or API verification output in the incident log so auditors can
   confirm the guardrail is in place.
3. **CI guardrail** – the `Health 45 Agents Guard` check (see
   `.github/workflows/agents-guard.yml`) fails any pull request that modifies,
   deletes, or renames a protected file without the required label and
   approvals. The only guard-level review exception is for dependency-only
   `uses: owner/action@ref` updates on protected workflows when the PR has
   `agents:allow-change` and is authored by Dependabot, Renovate, or a
   repository owner/member/collaborator. The check documents override steps and
   prevents merges unless a maintainer explicitly bypasses the branch protection
   rule. Mark this status check as **required** on the default branch so the
   enforcement cannot be skipped accidentally.
4. **Branch protection** – the default branch requires Gate and Health 45 Agents
   Guard to report success, plus **Require review from Code Owners**. This
   combination prevents force pushes or merges that sidestep the protections
   above. See
   [Workflow System Overview](ci/WORKFLOW_SYSTEM.md#how-to-verify-required-checks)
   for the verification flow and recovery playbook.

## Required checks and status contexts

> 📚 **Cross-reference.** The
> [Workflow System Overview](ci/WORKFLOW_SYSTEM.md#required-status-contexts-default-branch)
> publishes the same status-context table from the topology perspective so both
> documents stay synchronized when you audit branch protection.

- **Gate** surfaces the status context `gate` (**Gate / gate**) and blocks every
  pull request until it reports ✅. The check bundles docs-only detection and
  kicks off the reusable CI matrix.
- **Health 45 Agents Guard** surfaces the required status check **Health 45
  Agents Guard / Enforce agents workflow protections** (also referenced as
  **Agents Guard / Enforce agents workflow protections**). Branch protection
  enforces it alongside Gate; GitHub attaches the check automatically whenever a
  pull request touches `agents-*.yml`, enforcing the label and Code Owner
  guardrails.
- **Health 44 Gate Branch Protection** (workflow file:
  [`.github/workflows/health-44-gate-branch-protection.yml`](../.github/workflows/health-44-gate-branch-protection.yml))
  provides the enforcement audit trail. Its run history exposes
  `enforcement.json` and `verification.json` artifacts that list the contexts
  currently enforced on the default branch. Use the Health 44 snapshots to
  confirm **Gate / gate** and **Health 45 Agents Guard / Enforce agents workflow
  protections** stay protected, then cross-check against the
  [Workflow System Overview](ci/WORKFLOW_SYSTEM.md#how-to-verify-required-checks)
  UI routine for the pull-request view.

## How to verify required checks

Follow this routine whenever you need to prove the protections are active:

1. Visit the latest
   [Health 44 Gate Branch Protection run](https://github.com/stranske/Workflows/actions/workflows/health-44-gate-branch-protection.yml)
   and download the `enforcement.json` / `verification.json` artifacts. They
   enumerate the contexts branch protection enforces—expect **Gate / gate** and
   **Health 45 Agents Guard / Enforce agents workflow protections**.
2. Open a fresh pull request (or refresh an existing one) and confirm the Checks
   tab lists **Gate / gate** under **Required checks**. When the diff touches
   `agents-*.yml`, the UI adds **Health 45 Agents Guard / Enforce agents workflow
   protections** to the same list automatically. Use the
   [Workflow System Overview](ci/WORKFLOW_SYSTEM.md#how-to-verify-required-checks)
   walkthrough for the matching verification language.
3. If either context disappears, follow the
   [branch protection playbook](ci/WORKFLOW_SYSTEM.md#branch-protection-playbook)
   from the Workflow System Overview, then re-run Health 44 to capture the fixed
   snapshot.

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
4. Secure Code Owner review before merge for workflow logic edits. A narrow
   dependency-update exception lets the guard pass without Code Owner approval
   when all protected workflow changes are limited to `uses: owner/action@ref`
   reference updates, the PR has `agents:allow-change`, and the author is
   Dependabot, Renovate, or a repository owner/member/collaborator. Repository
   branch protection may still require review even when the guard passes.
5. Remove the label once merged so the guardrail resumes full enforcement on
   future PRs.

## Emergency override procedure

1. Confirm the incident really requires editing or temporarily removing one of
   the protected workflows.
2. A maintainer with admin access temporarily adjusts the repository ruleset
   (or applies a bypass) via **Settings → Code security and analysis → Rulesets**
   and, if required, toggles the `Health 45 Agents Guard` status check in branch
   protection.
3. Apply and review the change in a dedicated pull request. Code Owner approval
   remains required even when a maintainer performs the edits.
4. Re-enable the ruleset block and restore the CI guard immediately after the
   change merges. Document the incident and restoration steps in the associated
   issue or runbook entry.

## Troubleshooting

- **Guard check failing for “missing agents:allow-change label”.** Add the label
  (maintainers only) or revert the workflow edits. The check re-evaluates once
  the label is present.
- **CODEOWNERS review still required.** For non-dependency workflow edits, ping
  the maintainer listed in `.github/CODEOWNERS` (`@stranske`). Draft reviews do
  not satisfy branch protection. For dependency-only action reference updates,
  confirm the PR has `agents:allow-change`, the protected file diff changes only
  `uses:` lines, and the author is Dependabot, Renovate, or a repository
  owner/member/collaborator.
- **Ruleset rejection on push.** Confirm you are operating on a maintainer-owned
  branch or request a maintainer to apply a temporary bypass while they assist
  with the change.
- **Unexpected orchestrator no-op on `workflow_run` or `repository_dispatch`.**
  `agents-70-orchestrator.yml` admits only `workflow_dispatch` and `schedule` in
  `jobs.eligibility`; `workflow_run` and `repository_dispatch` are denied before
  `jobs.init`, and `schedule` runs force `dry_run=true`. Use manual
  `workflow_dispatch` (with `dry_run=false` when live writes are intended) or
  inspect `agents-keepalive-loop.yml` / `agents-keepalive-sweep.yml` for
  keepalive progression.

## Verification checklist

- The default branch protection lists **Require review from Code Owners** and
   includes the files above. The `Health 45 Agents Guard` status check is marked as
   required.
- The repository ruleset shows the three workflows in its “Protected file
  patterns section (`agents-63-issue-intake.yml`,
  `agents-70-orchestrator.yml`, and `agents-guard.yml`) with
  **Block deletion** and **Block rename** enabled.
- A maintainer can describe the override procedure without referencing this
  document (spot check during ops reviews).
