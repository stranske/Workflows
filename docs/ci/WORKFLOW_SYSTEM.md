# Workflow System Overview

**Purpose.** Document what runs where, why each workflow exists, and how the
pieces interlock so contributors can land changes without tripping the
guardrails. Automation shows up in four canonical buckets that mirror what a
contributor experiences on a pull request or on the maintenance calendar:

1. **PR checks** – Gate reports CI status. [Autofix routes](WORKFLOWS.md#autofix-routes) handle eligible repairs.
2. **Maintenance & repo health** – scheduled and follow-up automation that keeps
  the repository clean (Gate summary job, Maint Coverage Guard, Maint 45, recurring health checks).
3. **Issue / agents automation** – orchestrated agent work and issue
  synchronisation (event-driven `agents-keepalive-loop.yml` and hourly
  `agents-keepalive-sweep.yml`, the [shared opener and closer](../ops/LOCAL_LANES.md#lanes-overview),
  Agents 63/64 companions, and direct PR-meta worker dispatch ([#5162](https://github.com/stranske/Workflows/pull/5162),
  [#5163](https://github.com/stranske/Workflows/pull/5163))).
4. **Error checking, linting, and testing topology** – reusable workflows that
   fan out lint, type, test, and container verification across the matrix.

Each bucket below calls out the canonical workflows, the YAML entry point, and
the policy guardrails that keep the surface safe. Keep this mental map handy:

```
PR checks ──► Gate (required summary) + Health 45 Agents Guard (eligible events)
    │                      │
    │                      └──► Reusable CI matrix
    ▼
Maintenance & repo health ──► Issue / agents automation
```

Gate opens the door, reusable CI fans out the heavy lifting, maintenance keeps
the surface polished, and the agents stack orchestrates follow-up work.

> 📌 **Where this document fits.** The [workflow catalog](WORKFLOWS.md) and
> [`docs/CONTRIBUTING.md`](../CONTRIBUTING.md) pair with this page as the
> canonical map of what runs where. Keep this guide side by side with
> [AGENTS_POLICY.md](../AGENTS_POLICY.md) whenever you are evaluating workflow
> edits—the policy spells out the guardrails, while this page traces the
> topology those guardrails protect. Both documents now call out the universal
> ruleset context **`summary`** (Gate's aggregate job), the duplicate **`Gate / gate`**
> commit status the summary job still posts, and—separately—**Health 45 Agents Guard /
> guard** on eligible events. A missing status or skipped job gives no Guard verdict.
> The guides link back to the enforcement workflow
> [`health-44-gate-branch-protection.yml`](../../.github/workflows/health-44-gate-branch-protection.yml)
> so you can verify branch protection without guessing.

> 🧾 **One-minute orientation.**
> - Glance at [Topology at a glance](#topology-at-a-glance) to map the four
>   automation buckets to their YAML entry points and understand why each
>   surface exists.
> - Use the [Bucket quick reference](#bucket-quick-reference) or
>   [Workflow summary table](#workflow-summary-table) when you need the
>   trigger/purpose/required matrix for a review or incident response.
> - Keep [How to change a workflow safely](#how-to-change-a-workflow-safely)
>   open next to [AGENTS_POLICY.md](../AGENTS_POLICY.md) before editing any
>   workflow so you never bypass the guardrails.

> 🧭 **Use this map to stay oriented.**
> - Start with the [quick orientation](#quick-orientation-for-new-contributors)
>   checklist when you are new or returning so you know which buckets will
>   react to your work.
> - Reference the [workflow summary table](#workflow-summary-table) for
>   triggers, required signals, and log links before you brief a reviewer or
>   rerun a check manually.
> - Follow [How to change a workflow safely](#how-to-change-a-workflow-safely)
>   alongside [AGENTS_POLICY.md](../AGENTS_POLICY.md) whenever you update
>   `.github/workflows/` so you never bypass the guardrails.
> - Keep the [How to verify required checks](#how-to-verify-required-checks)
>   routine handy—it mirrors the policy view and points straight to the
>   Health 44 snapshots that list the enforced contexts.

### Contents

- [Quick orientation for new contributors](#quick-orientation-for-new-contributors)
- [Onboarding checklist (save for future you)](#onboarding-checklist-save-for-future-you)
- [Scenario cheat sheet](#scenario-cheat-sheet)
- [Bucket quick reference](#bucket-quick-reference)
- [Bucket guardrails at a glance](#bucket-guardrails-at-a-glance)
- [Observability surfaces by bucket](#observability-surfaces-by-bucket)
- [Topology at a glance](#topology-at-a-glance)
- [Buckets and canonical workflows](#buckets-and-canonical-workflows)
- [Lifecycle example: from pull request to follow-up automation](#lifecycle-example-from-pull-request-to-follow-up-automation)
- [Workflow summary table](#workflow-summary-table)
- [Policy](#policy)
- [Final topology (keep vs retire)](#final-topology-keep-vs-retire)
- [How to change a workflow safely](#how-to-change-a-workflow-safely)
- [Verification checklist](#verification-checklist)
- [Branch protection playbook](#branch-protection-playbook)

### How the buckets interact in practice

- **Gate and its summary job** are the first responders on every pull request.
  Gate decides whether to fan out into the reusable CI topology, while the
  summary job runs the optional clean-up sweep when the label is applied and
  the opt-in guard passes.
- **The Gate summary job** runs after the main fan-out finishes and aggregates
  the results, while the remaining maintenance workflows keep the default
  branch protected on a schedule or by manual dispatch.
- **Agents automation** consumes labelled issues and protected workflow edits
  through shared lanes, keepalive, and intake workflows, with guards such as
  the Health 45 Agents Guard.
- **Reusable lint/test/topology workflows** execute only when called; they
  provide the shared matrix for Gate and manual reruns so contributors see the
  same results regardless of entry point.

### Quick orientation for new contributors

When you first land on the project:

1. **Skim the [Topology at a glance](#topology-at-a-glance) table and the bucket
   summaries below** to understand which workflows will react to your pull
   request or scheduled automation.
2. **Use the [workflow catalog](WORKFLOWS.md)** to find an active workflow and its definition.
   Use the [workflow summary table](#workflow-summary-table) and
   [observability surfaces](#observability-surfaces-by-bucket) to find the run
   or artifact bundle you need for a status update. If you
   need to know which rules you must follow before editing a YAML file, jump
   straight to [Bucket guardrails at a glance](#bucket-guardrails-at-a-glance)
   for the enforcement summary, then finish the deep dive in
   [How to change a workflow safely](#how-to-change-a-workflow-safely).
3. **Review [How to change a workflow safely](#how-to-change-a-workflow-safely)**
   before editing any YAML. It enumerates the guardrails, labels, and approval
   steps you must follow.
4. **Cross-reference the [Workflow Catalog](WORKFLOWS.md)** for deeper YAML
   specifics (inputs, permissions, job layout) once you know which surface you
   are touching.

### Onboarding checklist (save for future you)

Run through this sequence when you are new to the automation surface or when you
return after a break:

1. **Bookmark the [Agents Workflow Protection Policy](../AGENTS_POLICY.md)** so
   you can confirm label and review requirements before touching protected
   workflows. The checklist below assumes you have read that policy once.
2. **Open the latest [Gate run](https://github.com/stranske/Workflows/actions/workflows/pr-00-gate.yml)** and skim the
   Summary tab. It shows which reusable jobs fire for typical PRs and highlights
   the docs-only path so you know what to expect for lightweight changes.
3. **Review the most recent [Gate run](https://github.com/stranske/Workflows/actions/workflows/pr-00-gate.yml)**
   and inspect the summary job output to see how post-merge hygiene is reported.
   Treat that summary comment as the canonical “state of CI” dashboard after
   every merge.
4. **Practice finding the agents guardrails** by visiting the
  [Health 45 Agents Guard history](https://github.com/stranske/Workflows/actions/workflows/agents-guard.yml)
   and reading a recent run summary. It confirms how the label and review gates
   manifest in CI when protected files change.
5. **Walk through a dry-run change**: open this document, the Workflow Catalog,
   and the policy side by side. Trace how you would update a workflow safely and
   which checks would block an unsafe edit. Doing this once keeps the guardrails
   fresh when you work on the real issue queue.

### Scenario cheat sheet

Use these scenarios to find the right entry point for a common task.

- **Opening or updating a feature PR?** Expect the [PR checks bucket](#pr-checks-gate--autofix)
  (Gate + optional Autofix) to run automatically and to fan out into the
  reusable CI topology.
- **Gate is red on your PR?** Expand the Gate summary comment to spot the
  failing lane, then open the linked workflow run. The reusable jobs expose a
  dedicated "Reusable CI" job section; download the attached artifact when
  Gate mentions one so you can compare the logs locally before re-running the
  check.
- **Investigating a nightly or weekend regression?** Start with the
  [Maintenance & repo health](#maintenance--repo-health) workflows—they collect
  the scheduled hygiene runs and post-merge follow-ups.

### Spotlight: the six guardrails everyone touches

These six workflows are the ones every contributor encounters first. Keep the
summary below handy when you need to brief a reviewer, triage a failing run, or
explain why a particular status appears in the Checks tab.

| Workflow | Primary triggers | Merge impact | Status context / where to look | Quick rerun path |
| --- | --- | --- | --- | --- |
| **Gate** (`pr-00-gate.yml`) | Every pull request (`pull_request`), manual dispatch (`workflow_dispatch`) | ✅ Required status | Ruleset requires **`summary`** per `.github/config/required-contexts.json`; **`Gate / gate`** is the duplicate commit status the summary job still posts | Checks tab → **Gate** → **Re-run jobs** (failed or all) |
| **Gate summary job** (`pr-00-gate.yml`, job `summary`) | Runs automatically after the Gate jobs finish | ✅ Required status | **`summary`** in PR checks, plus a timeline comment and coverage/status artifacts | Re-run the Gate workflow (the summary job runs automatically) |
| **Health 41 Repo Health** (`health-41-repo-health.yml`) | Monday 07:15 UTC schedule, manual dispatch | ❌ Informational hygiene | Run log under **Actions → Health 41 Repo Health** | Actions tab → workflow → **Run workflow** |
| **Health 40 Sweep** (`health-40-sweep.yml`) | Monday 05:05 UTC schedule, workflow-file pull requests, manual dispatch | ❌ Informational hygiene | Combined Actionlint + branch-protection jobs under **Actions → Health 40 Sweep** | Actions tab → workflow → **Run workflow** |
| **Health 42 Actionlint** (`health-42-actionlint.yml`) | Manual dispatch (or via `workflow_call` from the sweep) | ❌ Informational linting | Check annotations in the associated workflow run | Actions tab → workflow → **Run workflow** (set `REPORTER` inputs if needed) |
| **Health 45 Agents Guard** (`agents-guard.yml`) | PR lifecycle and label events. The eligibility step reads the routing labels from the registry. | Policy check for eligible PRs | Commit status **`Health 45 Agents Guard / guard`** | Checks tab → **Health 45 Agents Guard** → **Re-run** after updating labels/reviews |
> ℹ️ **Merge-gating recap.**
> - Gate's **`summary`** job blocks every pull request by default. Gate also
>   publishes the duplicate **`Gate / gate`** commit status.
> - Eligible PRs publish **`Health 45 Agents Guard / guard`** for the agent-surface policy.
> - The Gate summary comment appears in the PR timeline. Repo Health, Actionlint,
>   and Agents automation workflows report under the Actions tab.
> - Cross-reference the [Agents Workflow Protection
>   Policy](../AGENTS_POLICY.md#required-checks-and-status-contexts) for the
>   enforcement rationale behind the required checks.

#### Gate (`pr-00-gate.yml`)

- **When it runs.** Every pull request, plus manual dispatch for rehearsals.
- **What it enforces.** Detects docs-only diffs, orchestrates Python 3.13/3.14
  CI and the Docker smoke test, publishes coverage bundles, and produces the
  required **`summary`** check.
- **Merge impact.** Required on every PR; branch protection blocks merges until
  the `summary` job is green (docs-only fast-pass still reports success).

#### Gate summary job (`pr-00-gate.yml`, job `summary`)

- **When it runs.** Executes after the detect/python/docker jobs complete in the
  Gate workflow. It always runs (`if: ${{ always() }}`) so even failing Gate runs
  produce diagnostics and a status update.
- **What it does.** Posts the canonical CI summary comment, uploads coverage
  rollups, resolves the failure-tracker issue, and applies small autofix patches
  when allowed. On failing Gate runs it still captures diagnostics and links the
  blocking run so triage has a single thread. When rerun after a fixed Gate, the
  summary job republishes the comment and refreshes the attached coverage bundle
  so reviewers always have the latest snapshot in one place.
- **Merge impact.** The ruleset requires the `summary` job. The job also
  publishes the duplicate `Gate / gate` commit status and the CI summary comment.

#### Health 41 Repo Health (`health-41-repo-health.yml`)

- **When it runs.** Monday 07:15 UTC on a schedule, or via manual dispatch.
- **What it does.** Audits stale branches, unassigned issues, and default-branch
  protection drift, publishing the weekly hygiene dashboard in the run summary.
  It compares `.github/config/required-contexts.json` (currently **`summary`**)
  with the union of effective branch rules and classic protection. A complete
  read with missing or unexpected contexts produces a drift failure and lists
  the differences. A read failure identifies the unreadable source. Restore
  access to that source and rerun Health 41 to determine whether protection
  needs repair.
- **Merge impact.** Informational background signal; does not gate pull requests.

#### Health 40 Sweep (`health-40-sweep.yml`)

- **When it runs.** Monday 05:05 UTC on a schedule, manual dispatch, and on any
  pull request (Actionlint runs only when workflow files change thanks to a
  `paths-filter` gate).
- **What it does.** Fan-out job that first evaluates workflow edits with
  Actionlint and then verifies default-branch protection via the Health 44
  helper on scheduled/manual runs.
- **Merge impact.** Informational; it keeps weekly enforcement evidence fresh
  without adding new required contexts.

#### Health 42 Actionlint (`health-42-actionlint.yml`)

- **When it runs.** Manual dispatch or via `workflow_call` when the sweep needs
  the Actionlint leg.
- **What it does.** Runs Actionlint with the repository allowlist and sends its
  diagnostics to Reviewdog. Fork PRs use runner annotations in place of inline
  review comments. The job fails on an Actionlint error or a reporter error.
  If both fail, the job preserves the Actionlint exit code.
  Health 42 and Maint 52 use Actionlint 1.7.3. Its [versioned manual](https://github.com/rhysd/actionlint/tree/4e683ab8014a63fafa117492a0c6053758e6d593/docs) covers checks, configuration and installation.
- **Merge impact.** Informational; use the annotations to fix workflow schema
  errors before Gate runs.

#### Health 45 Agents Guard (`agents-guard.yml`)

- **When it runs.** Every pull request (`pull_request`) plus label changes via
  `pull_request_target` (`labeled`, `unlabeled`) when the PR carries a trusted
  registry routing label from `.github/agents/registry.yml`. Protected-file
  authorization labels such as `agents:allow-change` do not start
  protected-file evaluation unless a trusted routing label is also present.
- **What it enforces.** Confirms protected workflow edits carry the
  `agents:allow-change` label, the correct guard marker, and Code Owner approval
  except for the narrow dependency-update lane. That lane allows protected
  workflow diffs that change only `uses: owner/action@ref` references to pass
  with `agents:allow-change` for Dependabot, Renovate, or repository
  owner/member/collaborator authors without a separate Code Owner approval.
  When no protected files are in scope, the job exits cleanly.
- **Fork status publication.** The trusted publisher writes fork PR-head statuses. `agents-guard-fork-status.yml` is a trusted default-branch `workflow_run` publisher that validates the exact run, current fork head, latest attempt, and completed `guard` job before publishing `Health 45 Agents Guard / guard`; it never checks out PR code.
- **Merge impact.** The effective main ruleset requires the Gate `summary`.
  Health 45 applies its protected-file policy on eligible events. Inspect the
  exact head and selected job to distinguish a pass, a failure, and a skip.
  Missing trusted evidence can also fail evaluation. [Agents Workflow
  Protection Policy](../AGENTS_POLICY.md#how-to-verify-required-checks)

### How to re-run only these workflows

- **Gate.** From the PR Checks tab choose **Gate → Re-run jobs → Re-run failed
  jobs** (or **Re-run all jobs**). CLI alternative: `gh run rerun <gate-run-id>`.
- **Gate summary job.** Re-run the Gate workflow and let the summary job
  complete. It inherits the original artifacts and cannot be dispatched
  independently; a successful rerun posts a fresh timeline summary with updated
  coverage links after Gate turns green. CLI alternative: `gh run rerun
  <gate-run-id>`.
- **Health 41 Repo Health.** Actions tab → **Health 41 Repo Health → Run
  workflow**. CLI: `gh workflow run health-41-repo-health.yml`.
- **Health 42 Actionlint.** Actions tab → **Health 42 Actionlint → Run
  workflow** (set `REPORTER` inputs via repository variables). CLI:
  `gh workflow run health-42-actionlint.yml`.
- **Agent PR promotion.** Inspect the exact-head decision in the [shared closer](../ops/LOCAL_LANES.md#lanes-overview) run.
- **Health 45 Agents Guard.** From the PR Checks tab, expand **Health 45 Agents Guard** and choose
  **Re-run** after updating labels or reviews. On `pull_request_target`
  `labeled`/`unlabeled` events, the guard re-evaluates protected-file changes
  only when the PR carries a trusted registry routing label (including when
  protected-file authorization labels such as `agents:allow-change` are toggled
  on a routing-labelled PR). CLI alternative: `gh run rerun <agents-guard-run-id>` once the
  rerun appears under **Actions → Health 45 Agents Guard**.
- **Gate summary flagged drift?** Follow the summary comment back to the
  workflow run, review the uploaded artifact bundle, and check the linked
  follow-up issue before you retry. The Gate summary job only reports success
  when both the reusable CI fan-out and the hygiene sweep succeed.
- **Working on labelled agent issues or Codex escalations?** Review the
  [Issue / agents automation](#issue--agents-automation) guardrails so you know
  which workflows dispatch work and which checks must stay green.
- **Editing YAML under `.github/workflows/`?** Read [How to change a workflow
  safely](#how-to-change-a-workflow-safely) before committing; it lists the
  approvals, labels, and verification steps Gate will enforce.
- **Need to run lint, type checking, or container tests by hand?** Use the
  [Error checking, linting, and testing topology](#error-checking-linting-and-testing-topology)
  section to find the reusable entry points and confirm which callers already
  exercise the matrix.
- **Working on JS/TS packages?** Reuse `.github/workflows/reusable-11-ci-node.yml` for lint/format/typecheck/test coverage, including multi-version Node matrices.

### Lifecycle example: from pull request to follow-up automation

This happy-path walk-through shows how the four buckets hand work to one another
and where to watch the result:

1. **Developer opens or updates a pull request.** Gate (`pr-00-gate.yml`) runs
   immediately, detects whether the diff is docs-only, and—when code changed—
   calls the reusable lint/test topology. You can watch progress in the
  [Gate workflow history](https://github.com/stranske/Workflows/actions/workflows/pr-00-gate.yml)
   and follow the linked reusable job logs from the Checks tab.
2. **Autofix (optional).** Open the [repair or formatting run](WORKFLOWS.md#autofix-routes) to inspect its outcome before merging.
3. **Merge lands on the default branch.** The Gate summary job aggregates
   artifacts and status from the CI jobs.
  Scheduled health checks (Health 40, 41, 42, 44, and 45 Agents Guard; signature-verify formerly in archived `health-43-ci-signature-guard.yml` now runs in `pr-00-gate.yml` and `selftest-ci.yml`) continue on their cadence even when no one is watching,
   keeping the repo healthy. Maint 46 summary rendering is recovery-only: it wakes up
   when Gate fails to emit its own summary so there is a single source of
   truth on green runs.
4. **Issue and agents automation picks up queued work.** Labelled issues flow
   through Agents 63 bridges into the shared opener; keepalive and PR-meta
   dispatch workers directly ([#5162](https://github.com/stranske/Workflows/pull/5162),
   [#5163](https://github.com/stranske/Workflows/pull/5163)); Health 45 Agents Guard
   still governs protected workflow edits.
5. **Manual investigations reuse the topology.** When contributors need to
   rerun linting, typing, or container checks locally, they can dispatch the
   `selftest-reusable-ci.yml` workflow or call the reusable CI entries directly,
   guaranteeing they exercise the same matrix Gate and Gate summary job rely on.

Revisit this sequence whenever you need to explain the automation lifecycle to
new contributors or track down where a particular check originated.

### Bucket quick reference

Use this cheat sheet when you need the quickest possible answer about “what
fires where” without diving into the full tables:

- **PR checks.** Open the [Gate job map](WORKFLOWS.md#gate-job-map) for required CI and the [Autofix routes](WORKFLOWS.md#autofix-routes) for repair logs and formatting artifacts.
- **Maintenance & repo health**
  - **Primary workflows.** Gate summary job inside `pr-00-gate.yml`,
    `maint-46-post-ci.yml`, `maint-coverage-guard.yml`,
    `maint-45-cosmetic-repair.yml`,
    and the health guardrails (`health-40`, `health-41`, `health-42`, `health-44`, and `agents-guard` as Health 45; `health-43-ci-signature-guard.yml` archived).
  - **Triggers.** Combination of the Gate summary job running after Gate,
    recurring schedules (health guardrails), and manual dispatch for
    Maint 45.
  - **Purpose.** Keep the default branch stable after merges, surface drift,
    and enforce branch-protection expectations without waiting for the next PR.
  - **Where to inspect logs.** Gate summary job: [Gate workflow history](https://github.com/stranske/Workflows/actions/workflows/pr-00-gate.yml).
    Maint 46: [workflow history](https://github.com/stranske/Workflows/actions/workflows/maint-46-post-ci.yml).
    Maint 45: [workflow history](https://github.com/stranske/Workflows/actions/workflows/maint-45-cosmetic-repair.yml).
    Health guardrails: the [Health 40–45 dashboards](https://github.com/stranske/Workflows/actions?query=workflow%3AHealth+40+repo+OR+workflow%3AHealth+41+repo+OR+workflow%3AHealth+42+Actionlint+OR+workflow%3AHealth+44+Gate+Branch+Protection+OR+workflow%3AHealth+45+Agents+Guard) (Health 43 retired; signature-verify fixture validation moved into `pr-00-gate.yml` and `selftest-ci.yml` after `health-43-ci-signature-guard.yml` was archived).
- **Issue / agents automation**
  - **Primary workflows.** `agents-keepalive-loop.yml`, `agents-keepalive-sweep.yml`,
    the [shared opener and closer](../ops/LOCAL_LANES.md#lanes-overview),
    the shared intake (`agents-63-issue-intake.yml`),
    `agents-64-verify-agent-assignment.yml`, `agents-pr-meta-v4.yml`, and `agents-guard.yml`.
  - **Triggers.** Gate `workflow_run` and hourly sweep schedules for keepalive;
    shared lane runs, labelled issues, and protected pull request edits.
  - **Purpose.** Convert tracked issues into automation tasks while preserving
    the immutable agents surface behind Code Owners, labels, and guard checks.
  - **Where to inspect logs.** Keepalive:
    [workflow history](https://github.com/stranske/Workflows/actions/workflows/agents-keepalive-loop.yml).
    See the [shared lane procedure](../ops/LOCAL_LANES.md#lanes-overview) for agent PR promotion.
  - **Keepalive sweeps.** Authored Gate-completion and hourly resync sweeps run in
    `agents-keepalive-loop.yml` and `agents-keepalive-sweep.yml`. PR-meta dispatches
    workers directly ([#5162](https://github.com/stranske/Workflows/pull/5162),
    [#5163](https://github.com/stranske/Workflows/pull/5163)).
  - **Agents 63 intake.** [workflow history](https://github.com/stranske/Workflows/actions/workflows/agents-63-issue-intake.yml).
  - **Health 45 Agents Guard.** [workflow history](https://github.com/stranske/Workflows/actions/workflows/agents-guard.yml).
- **Error checking, linting, and testing topology**
  - **Primary workflows.** `reusable-10-ci-python.yml`, `reusable-11-ci-node.yml`, `reusable-12-ci-docker.yml`, `reusable-13-cross-repo-smoke.yml`,
    `reusable-18-autofix.yml`, `reusable-19-dependency-repair-contract.yml`, `reusable-20-pr-meta.yml`, `reusable-agents-issue-bridge.yml`, `reusable-agents-pr-health.yml`, `reusable-agents-verifier.yml`, `reusable-backplane-conformance.yml`, `reusable-bot-comment-handler.yml`, `reusable-claude-run.yml`, `reusable-codex-run.yml`, `reusable-model-profile-trial.yml`, `reusable-cursor-run.yml`, `reusable-gemini-run.yml`, `reusable-muse-run.yml`, `reusable-pr-context.yml`, and `selftest-reusable-ci.yml`.
  - **Triggers.** Invoked via `workflow_call` by Gate, Autofix and other CI callers, including manual reruns. The [self-test catalog](WORKFLOWS.md#self-test-harness) covers the reusable CI harness.
  - **Purpose.** Provide a consistent lint/type/test/container matrix so every
    caller sees identical results.
  - **Codex entry point.** `reusable-codex-run.yml` centralizes prompt-file execution,
    default sandbox settings, and post-run commit/push handling so keepalive, autofix,
    and verifier callers share the same behavior.
  - **Claude entry point.** `reusable-claude-run.yml` provides the same prompt-file entry surface for Claude CLI runs so callers can reuse consistent preflight, output capture, and artifact handling.
  - **Cursor entry point.** `reusable-cursor-run.yml` provides the same prompt-file entry surface for `cursor-agent` CLI runs (API-key auth via `CURSOR_API_KEY`), reusing the shared preflight, output capture, commit/push, and artifact handling.
  - **Muse entry point.** `reusable-muse-run.yml` provides the same prompt-file entry surface for `muse exec` runs (auth via `META_API_KEY`, the console key from the Muse Code subscription login), keeping the Muse sandbox on and failing closed when bubblewrap cannot start.
  - **Gemini entry point.** `reusable-gemini-run.yml` provides the same prompt-file entry surface for Google Antigravity CLI (`agy`) runs (subscription sign-in file restored from `GEMINI_OAUTH_CREDS`; never an API key), reusing the shared preflight, output capture, commit/push, and artifact handling.
  - **Where to inspect logs.** Reusable Python CI:
    [workflow history](https://github.com/stranske/Workflows/actions/workflows/reusable-10-ci-python.yml).
    Docker CI:
    [workflow history](https://github.com/stranske/Workflows/actions/workflows/reusable-12-ci-docker.yml).
    Self-test workflow:
    [workflow history](https://github.com/stranske/Workflows/actions/workflows/selftest-reusable-ci.yml).

### Bucket guardrails at a glance

Use this table when you need a snapshot of the non-negotiable rules that govern
each automation surface. Every line links back to the policy or workflow that
enforces the guardrail so you know where to confirm compliance:

| Bucket | Guardrails you must respect | Where it is enforced |
| --- | --- | --- |
| PR checks | Gate is required on every PR; docs-only detection happens inside Gate; Autofix is label-gated and cancels duplicates per branch. | Gate workflow protection + [branch protection](#branch-protection-playbook) keep the check mandatory. |
| Maintenance & repo health | Gate summary job only runs after Gate succeeds; Health 40, 41, 42, 44, and 45 Agents Guard must stay enabled so the default branch keeps its heartbeat (`health-43-ci-signature-guard.yml` archived); `maint-45-cosmetic-repair.yml` is manual and should only be dispatched by maintainers. | Gate summary job summary comment, Health dashboard history, and Maint 45 run permissions. |
| Issue / agents automation | `agents:allow-change` label and Health 45 Agents Guard are mandatory before protected YAML merges; Code Owner review is mandatory except for dependency-only `uses: owner/action@ref` updates by Dependabot, Renovate, or repository owner/member/collaborator authors using the narrow label path. Belt and keepalive surfaces honour eligibility and label contracts. | [Agents Workflow Protection Policy](../AGENTS_POLICY.md), Health 45 Agents Guard, and repository label configuration. |
| Error checking, linting, and testing topology | Callers invoke the shared reusable workflows (`./.github/workflows/reusable-*.yml` in-repo, `@main` in consumer templates, or an exact commit SHA where required such as `reusable-model-profile-trial.yml`) rather than forking or bypassing them; `selftest-reusable-ci.yml` mirrors Gate’s matrix on PR path filters, nightly schedule, and manual dispatch. | `maint-52-validate-workflows.yml` / Health 42 Actionlint, `health-73-template-completeness.yml` / `health-74-template-drift.yml`, Gate’s workflow contract tests (`test_reusable_ci_no_hardcoded_ref_main.py`, `test_python_matrix_contract.py`, `test_model_profile_trial_workflows.py`), and the reusable workflow permissions blocks. (The `signature-verify` fixture test in Gate and Selftest CI verifies only failure-signature hash stability against `.github/signature-fixtures/`, not reusable workflow references.) |

### Observability surfaces by bucket

Think of these run histories, dashboards, and artifacts as the canonical places
to verify that automation worked—or to capture a permalink for post-mortems and
status updates:

- **PR checks**
  - *Gate summary comment.* Appears automatically on every pull request and is
    the first line of evidence when a contributor wants to share status.
  - *Gate workflow run.* The Checks tab links to
    [pr-00-gate.yml history](https://github.com/stranske/Workflows/actions/workflows/pr-00-gate.yml),
    which exposes reusable job logs and uploaded artifacts for failing runs.
  - *Autofix artifacts.* When the `autofix:clean` label is applied, the workflow
    uploads the formatted patch or commit diff for reviewers to inspect before
    merging.
- **Maintenance & repo health**
  - *Gate summary job comment and artifact bundle.* Each run posts a consolidated
    summary with links to artifacts, making it easy to confirm that post-merge
    hygiene completed.
  - *Health 40–45 dashboards.* The Actions list filtered by `workflow:Health`
    (40, 41, 42, 44, and 45 Agents Guard; Health 43 archived) serves as the
    heartbeat for scheduled enforcement jobs. Failures here are a red flag that
    branch protection or guardrails drifted.
- **Issue / agents automation**
  - *Keepalive loop timeline.* [agents-keepalive-loop.yml history](https://github.com/stranske/Workflows/actions/workflows/agents-keepalive-loop.yml)
    shows worker dispatch rounds and run-cap decisions per PR.
  - *Agent promotion.* Check the [shared closer](../ops/LOCAL_LANES.md#lanes-overview) decision for the exact PR head.
  - *Health 45 Agents Guard status.* Inspect
    [agents-guard.yml](https://github.com/stranske/Workflows/actions/workflows/agents-guard.yml)
    whenever a protected YAML edit lands; it should be green before merge.
  - *Agents 63 bridge logs.* These runs attach trace logs showing which issues
    were synced or bootstrapped, invaluable when debugging missed escalations.
- **Error checking, linting, and testing topology**
  - *Reusable job logs.* Because the reusable workflows emit job-level logs for
    each caller, you can open the workflow run from Gate or Gate summary job and expand
    the “Reusable CI” job to see the full lint/test output.
    - *Self-test runner nightly summary.* The scheduled run appends the
      verification table to the job summary so regressions surface without
      paging maintainers.
    - *Self-test runner history artifact.* Manual dispatch uploads the combined
      test report so local reproductions can be compared against CI output.

## Topology at a glance

| Bucket | Where it runs | YAML entry points | Why it exists |
| --- | --- | --- | --- |
| PR checks | Every pull request event (including `pull_request_target` for fork visibility) | `pr-00-gate.yml` | Keep the default branch green by running the gating matrix before reviewers waste time. |
| Maintenance & repo health | Daily/weekly schedules plus manual dispatch | Gate summary job in `pr-00-gate.yml`, `maint-46-post-ci.yml`, `maint-45-cosmetic-repair.yml`, `maint-62-integration-consumer.yml`, `maint-65-sync-label-docs.yml`, `maint-66-monthly-audit.yml`, `health-4x-*.yml` | Scrub lingering CI debt, enforce branch protection, and surface drift before it breaks contributor workflows. |
| Issue / agents automation | Gate `workflow_run` and hourly sweep; shared opener and closer; labelled issues | `agents-keepalive-loop.yml`, `agents-keepalive-sweep.yml`, `agents-63-issue-intake.yml`, `agents-64-verify-agent-assignment.yml`, `agents-pr-meta-v4.yml`, `agents-guard.yml`, and companion keepalive/autofix workflows | Translate labelled issues into automated work while keeping the protected agents surface locked behind guardrails. |
| Error checking, linting, and testing topology | Reusable fan-out invoked by Gate, Autofix and manually dispatched CI callers | `reusable-10-ci-python.yml`, `reusable-11-ci-node.yml`, `reusable-12-ci-docker.yml`, `reusable-13-cross-repo-smoke.yml`, `reusable-18-autofix.yml`, `reusable-20-pr-meta.yml`, `selftest-reusable-ci.yml` | Provide a single source of truth for lint/type/test/container jobs so every caller runs the same matrix with consistent tooling. |

Keep this table handy when you are triaging automation: it confirms which workflows wake up on which events, the YAML files to inspect, and the safety purpose each bucket serves.

## Buckets and canonical workflows

### PR checks (Gate + Autofix)
- **Gate** – `.github/workflows/pr-00-gate.yml`
  - Required on every pull request. Detects docs-only diffs (Markdown anywhere,
    the entire `docs/` tree, and `assets/`) and skips the heavier Python and
    Docker matrices when nothing executable changed. Gate logs the short skip
    notice and adds it to the step summary while publishing the final combined
    status.
  - Requests `pull-requests: write` and `statuses: write` scopes so the summary
    and status appear with the correct phrasing, and to delete any legacy
    docs-only comments left by older workflow revisions. No new PR comment is
    posted—the docs-only fast pass now lives exclusively in logs and the job
    summary.
- **Autofix.** Use the [Autofix routes](WORKFLOWS.md#autofix-routes) to locate both callers.

### Maintenance & repo health
- **Gate summary job** – the `summary` job within `pr-00-gate.yml` consolidates
  CI results and uploads the Gate artifacts.
- **Maint Coverage Guard** – `.github/workflows/maint-coverage-guard.yml`
  downloads the latest Gate coverage payload plus the trend artifact and
  compares them against `config/coverage-baseline.json`, surfacing notices when
  coverage dips outside the allowed guard band.
- **Maint Metrics Retention** – `.github/workflows/maint-metrics-retention.yml`
  runs `scripts/metrics_retention.py` by manual dispatch with
  `config/retention-policy.json`, uploads `metrics-retention.ndjson` as an
  artifact, and writes the storage reduction percentage to the step summary.
  Pull-request triggers activate `--dry-run` mode automatically. The prior
  02:00 UTC nightly cron was removed because fresh checkouts have no metrics
  artifacts to retain; fresh checkouts still produce a successful zero-file
  no-op summary for PR validation.
  - Coverage reports intentionally exclude CLI-only entry points (for example,
    `if __name__ == "__main__"` blocks marked with `# pragma: no cover`).
- **Maint 46 Post CI** – `.github/workflows/maint-46-post-ci.yml` is a recovery
  summary shim plus an independent failure-tracker job. Summary recovery skips
  when the Gate `summary` job succeeded and only downloads artifacts, rebuilds the summary
  (including coverage deltas), and refreshes the commit status when Gate failed
  to publish its own summary.
- **Maint Sync Action Versions** – `.github/workflows/maint-sync-action-versions.yml`
  syncs action version pins from `.github/workflows` into workflow templates after
  Dependabot updates land.
- **Maint 50 Tool Version Check** – `.github/workflows/maint-50-tool-version-check.yml`
  runs weekly (Mondays 8:00 AM UTC) to check PyPI for new versions of CI/autofix tools
  (black, ruff, mypy, pytest, etc.) and publishes read-only freshness evidence.
- **Maint 39 Test LLM Providers** – `.github/workflows/maint-39-test-llm-providers.yml`
  is a manual workflow that smoke-tests OpenAI credentials and reports Anthropic
  and regex fallback availability via `tools.llm_provider.check_providers()`
  (retired GitHub Models is excluded from dispatch and smoke testing). Used to test the task completion analysis fallback chain.
- **Maint Sync pyproject.toml from versions.env** – `.github/workflows/maint-sync-env-from-pyproject.yml`
  repairs source pin drift on a maintainer-selected topic branch by manual dispatch.
  It aligns `pyproject.toml`, templates, and direct `requirements.lock` pins to
  `autofix-versions.env` and pushes changes to that topic. Gate checks alignment before merge.
- **Maint 52 Validate Workflows** – `.github/workflows/maint-52-validate-workflows.yml`
  dry-parses every workflow YAML using `yq`, hydrates the shared actionlint
  allowlist, and runs `actionlint` so malformed syntax or unapproved action
  usage breaks fast before landing on the default branch (PRs and main pushes).
- **Maint 52 Sync Dev Versions** – `.github/workflows/maint-52-sync-dev-versions.yml`
  syncs dev tool versions (ruff, mypy, black, isort, pytest) from
  `autofix-versions.env` to consumer repository `pyproject.toml` files
  weekly or when version changes are detected.
- **Maint Auto-Update PyPI Versions** – `.github/workflows/maint-auto-update-pypi-versions.yml`
  is the sole Monday 03:00 UTC source-proposal lane for routine dev-tool pins,
  opening or refreshing one mutable PR and accepting an explicit security
  override outside that window before consumer propagation.
- **Maint 62 Integration Consumer** – `.github/workflows/maint-62-integration-consumer.yml`
  exercises the reusable Python CI template against the `templates/integration-repo`
  scenarios on a daily schedule (05:05 UTC), on release publication, or via
  manual dispatch, then reports the outcome in the job summary and manages the
  integration failure tracker issue when needed.
- **Maint 65 Sync Label Docs** – `.github/workflows/maint-65-sync-label-docs.yml`
  synchronizes the consumer-specific `templates/consumer-repo/docs/LABELS.md`
  to consumer `docs/LABELS.md` files when the template changes or via manual
  dispatch, ensuring consistent label conventions across the ecosystem.
- **Maint 66 Monthly Audit** – `.github/workflows/maint-66-monthly-audit.yml`
  performs a comprehensive monthly audit of workflow health (1st of each month
  at 06:00 UTC), collecting run statistics, identifying high-failure workflows,
  listing never-run workflows, and creating/updating a tracking issue with an
  actionable checklist.
- **Maint 48 Docs Drift Audit** – `.github/workflows/maint-48-docs-drift-audit.yml`
  seeds one scoped docs-drift audit issue per month (1st at 07:00 UTC, deduped)
  so the lane fleet diffs the canonical docs against the current tree and opens
  fix PRs. Doc-rot is the audit's most pervasive defect class.
- **Maint 87 Docs Drift Fix Agent** – `.github/workflows/maint-87-docs-drift-fix-agent.yml`
  runs the deterministic docs-drift detector weekly and uploads bounded repair
  plans. Explicit apply dispatches create idempotent issues in a non-cancelling
  concurrency lane; scheduled runs remain report-only.
- **Maint 45 Cosmetic Repair** – `.github/workflows/maint-45-cosmetic-repair.yml`
  is a manual workflow. It runs pytest and the guardrail fixers, then opens a
  labelled PR if changes are needed.
- **Health checks** – recurring workflows that keep the repo honest:
  - `health-40-repo-selfcheck.yml` (weekly pulse, Mondays 06:20 UTC),
  - `health-41-repo-health.yml` (weekly sweep),
  - `health-42-actionlint.yml` (actionlint enforcement),
  - `health-44-gate-branch-protection.yml` (required check enforcement; signature-verify fixture validation moved into `pr-00-gate.yml` and `selftest-ci.yml` after `health-43-ci-signature-guard.yml` was archived),
  - `health-codex-auth-check.yml` (Codex auth token expiration monitoring),
  - `health-cursor-auth-check.yml` (Cursor key presence check),
  - `health-muse-auth-check.yml` (Muse key presence, CLI and sandbox check, no model call), and
  - `agents-guard.yml` (immutable agents surface guardrail).

### Issue / agents automation
- **Retired Agents 70 stack (qualified historical).** The orchestrator init/main
  pair and `reusable-16-agents.yml` are removed from the active control plane; see
  [Agents Workflow Protection Policy](../AGENTS_POLICY.md). Agents 61/62 consumer
  shims stay retired.
- **Issue admission and PR promotion.** The [shared opener and closer](../ops/LOCAL_LANES.md#lanes-overview) claim eligible issues, open agent PRs, and verify the exact PR head before promotion.
- **Health 40 belt claim reclaim** – `.github/workflows/health-40-sweep.yml`
  removes `status:in-progress` after 24 hours only when no linked open or merged
  PR exists, and records the claim timestamp in an audit comment first.
- **Agents PR meta manager** – `.github/workflows/agents-pr-meta-v4.yml` is
  the canonical PR meta manager using external scripts to stay under GitHub
  workflow parser limits. Manages PR metadata and the Automated Status Summary
  that tracks issue acceptance criteria completion. It intentionally ignores
  PR-body edit events because it writes that surface itself; structural PR,
  comment, and Gate-completion events provide the bounded wakeups. (Legacy
  v1/v2/v3 versions archived to
  `archives/github-actions/2025-12-02-pr-meta-legacy/`.)
- **Keepalive loop (Gate workflow_run).** The `agents-keepalive-loop.yml` workflow
  evaluates PR guardrails after Gate completes, runs registry-backed agents when
  eligible, and repeats on subsequent Gate completions until tasks are done.
  PR-meta submits worker commands directly ([#5162](https://github.com/stranske/Workflows/pull/5162)).
- **Keepalive loop reporter.** The `agents-keepalive-loop-reporter.yml` workflow
  fires on keepalive completion and posts the final summary when the keepalive
  run fails or is cancelled before the summary job can execute.
- **Keepalive dispatch handler.** The workflow
  `agents-keepalive-dispatch-handler.yml` listens for keepalive
  `repository_dispatch` payloads and replays them so keepalive actions stay aligned
  with `agents-keepalive-branch-sync.yml`.
- **Keepalive pause/resume control.** Apply the `agents:paused` label on a PR
  to halt keepalive runs for that PR until the label is removed.
- **Agents 63 Issue Intake** – `.github/workflows/agents-63-issue-intake.yml`
  centralises ChatGPT imports and handles the `agent:codex` label trigger via a
  single reusable entry point.
- **Agents 64 Assignment Verifier** – `.github/workflows/agents-64-verify-agent-assignment.yml`
  audits that labelled issues retain approved assignees; callable and manual dispatch.
- **Agents Moderate Connector Comments** – `.github/workflows/agents-moderate-connector.yml`
  moderates connector-authored pull-request comments using repository allow and
  deny lists, deleting posts when necessary and tagging the configured debug label.
- **Guardrail** – The intake front and protected agent workflows are locked
  down by CODEOWNERS, branch protection, the Health 45 Agents Guard check, and a
  repository ruleset. See [Agents Workflow Protection Policy](../AGENTS_POLICY.md)
  for the change allowlist and override procedure.

#### Historical sync-core first-opportunity pilot

The pilot below documents the retired Auto-Pilot fallback. The shared opener now owns admitted issue starts.

Before retirement, operators could enroll one receiving repository after its default branch has the managed
`agents-auto-pilot.yml` gate and the shared producer and opener have been
verified together. Create the `sync:opener-first` issue label and set the
repository Actions variable `SYNC_CORE_OPENER_FIRST_ISSUER_ID` to the numeric
GitHub account ID of the controller's authenticated producer. Enable that
repository in sync-core's `opener_first_repos` configuration with the same ID.
The producer checks the receiver workflow, label, variable, and its authenticated
identity before filing a new pilot issue.

The producer's issue keeps `agents:auto-pilot`, `sync`, and `automated`. Its
`sync:opener-first` label and versioned body receipt identify the reservation.
The initial Auto-Pilot event yields only when the GitHub issue author, event
sender, receipt, and scoped labels match. The shared opener reads the producer
ledger before using the reservation. Existing human pauses, assignments, live
claims, and linked PRs take precedence.

If the opener reaches a confirmed no-start disposition, it checks current
ownership and removes only `sync:opener-first` using the configured issuer.
The native label-removal event resumes Auto-Pilot, which re-reads issue state
and existing work before dispatch. If the opener's start outcome is uncertain,
recover that operation from live claims, the issue timeline, and linked PRs
before authorizing any fallback. For an authorized manual recovery, confirm the
same no-start evidence under the shared controller's ownership, then have the
configured issuer remove the pilot label. Keep the legacy label and any owner
pause in place. An ordinary maintainer's removal does not start Auto-Pilot.
Disable new enrollments in sync-core first if withdrawing the pilot, then
resolve existing reservations before removing the receiver's issuer variable.

### Error checking, linting, and testing topology
- **Reusable Python CI** – `reusable-10-ci-python.yml` fans out ruff, mypy, and
  pytest across the interpreter matrix. It reads `python_version` (currently `"3.13"`)
  from `pyproject.toml` and pins the mypy leg accordingly.
- **Reusable Docker CI** – `reusable-12-ci-docker.yml` builds the container
  image and exercises the smoke tests Gate otherwise short-circuits for
  docs-only changes.
- For a failed [Reusable Cross-Repo Smoke](WORKFLOWS.md#reusable-cross-repo-smoke) check, open the run in the calling repository and inspect the logged dependency SHA.
- **Reusable Autofix** – See the [formatting caller and its results](WORKFLOWS.md#autofix-routes).
- **Reusable Model Profile Trial** – `reusable-model-profile-trial.yml` runs one
  immutable read-only Astra/Sol/Terra/Luna plumbing arm from a separately pinned
  helper checkout. It requires current remote `main` before auth and emits v2
  quarantine telemetry with GitHub provenance and bounded source manifests;
  `agents-model-profile-trial.yml` is its manual shim.
- **Selftest: Reusables** – Use the [dispatch options and scenario matrix](SELFTESTS.md#triggers) to run the consumer fixture or publish results on a PR. For custom run labels, use `summary_title` and `comment_title`.
  - Gate summary job now serves as the canonical Gate follow-up comment. The
    legacy wrappers `maint-43-selftest-pr-comment.yml`,
    `pr-20-selftest-pr-comment.yml`, and `selftest-pr-comment.yml` were retired
    in Issue #2720 so PR annotations flow through either Gate summary job or this
    manual workflow. See [`docs/ci/SELFTESTS.md`](SELFTESTS.md) for the scenario
    matrix and artifact expectations.
- **Selftest CI** – `selftest-ci.yml` preserves its Python Tests check with the
  nine-case slow autofix/PyPI compatibility matrix; Gate owns the full PR suite
  with its 70% guard, and Selftest
  calls the same canonical Python suite on main pushes/manual dispatches. JavaScript,
  package tests, linting and YAML validation retain their push/PR triggers.
- **Keepalive E2E** – `health-keepalive-e2e.yml` path-filtered E2E test for
  the keepalive system. Runs only when keepalive-related files change.

### Keepalive and CLI troubleshooting

- Inspect the failed [Keepalive E2E](https://github.com/stranske/Workflows/actions/workflows/health-keepalive-e2e.yml) run for orchestration evidence and the Codex ping result when that job was selected. The scheduled [Codex Auth Check](https://github.com/stranske/Workflows/actions/workflows/health-codex-auth-check.yml) checks the stored Codex token's structure and expiry.
- For a failing Claude execution, inspect **Preflight auth** and **Run Claude** in the existing caller's run. [Reusable Claude workflow](../../.github/workflows/reusable-claude-run.yml)
- [Health 75 API Rate Diagnostic](https://github.com/stranske/Workflows/actions/workflows/health-75-api-rate-diagnostic.yml) reports API credential-pool quota. For a failed App-backed push, inspect the actual [keepalive branch-sync run](https://github.com/stranske/Workflows/actions/workflows/agents-keepalive-branch-sync.yml). A successful push using a fallback credential leaves the preferred App unverified. The retired combined auth harness has no maintained one-for-one replacement.
- Historical source is available for the [Keepalive Auth Diagnostic](https://github.com/stranske/Workflows/blob/67c2558643792c08e2063bbd0c4133c561fb009e/archives/diagnostics/health-keepalive-auth-diagnostic.yml) and the [Claude CLI Auth Debug](https://github.com/stranske/Workflows/blob/67c2558643792c08e2063bbd0c4133c561fb009e/archives/diagnostics/health-claude-cli-auth-debug.yml). Both were retired from GitHub Actions in February 2026.

## Workflow summary table

**Legend.** `✅` means the workflow must succeed before the associated change can merge; `⚪` covers opt-in, scheduled, or manual automation that supplements the required guardrails.

| Workflow | Trigger | Purpose | Required? | Artifacts / logs |
| --- | --- | --- | --- | --- |
| **Gate** (`pr-00-gate.yml`, PR checks bucket) | `pull_request`, `workflow_dispatch` | Detect docs-only diffs, orchestrate CI fan-out, and publish the combined status. | ✅ Always | [Gate workflow history](https://github.com/stranske/Workflows/actions/workflows/pr-00-gate.yml) |
| **Gate summary job** (`pr-00-gate.yml`, job `summary`) | After the Gate CI jobs | Report the combined result and request follow-up for eligible failures. | ✅ Required | [Gate job map](WORKFLOWS.md#gate-job-map) |
| [PR 11 - Minimal invariant CI](WORKFLOWS.md#minimal-invariant-ci) | Push and PR to `main`, manual dispatch | Inspect workflow YAML and script syntax failures. | ⚪ Supplemental | [Workflow runs](https://github.com/stranske/Workflows/actions/workflows/pr-11-ci-smoke.yml) |
| **PR 46 Dependency Repair Contract** (`pr-46-dependency-repair-contract.yml`, PR checks bucket) | `pull_request_target` for dependency-bot and marked promotion PRs | Keep bot branches classified and verify the bot-delta first commit before agent repair commits. | ✅ Required for dependency repair lanes | [Dependency repair contract runs](https://github.com/stranske/Workflows/actions/workflows/pr-46-dependency-repair-contract.yml) |
| **Maint 50 Tool Version Check** (`maint-50-tool-version-check.yml`, maintenance bucket) | `schedule` (Mondays 8:00 AM UTC), `workflow_dispatch` | Publish read-only PyPI freshness evidence for the canonical dev-tool pin set. | ⚪ Scheduled | [Maint 50 version checks](https://github.com/stranske/Workflows/actions/workflows/maint-50-tool-version-check.yml) |
| **Auto-lock dependency PRs** (`maint-auto-lock-deps.yml`, maintenance bucket) | `pull_request_target` for opens and `pull_request` for lock-input changes to main | The trusted open event applies `agents:allow-change` to Dependabot and Renovate PRs without checking out code. The separate lock path regenerates `requirements.lock` from its recorded command and publishes only to the checked same-repository bot head. | ⚪ Supplemental | [Dependency PR runs](https://github.com/stranske/Workflows/actions/workflows/maint-auto-lock-deps.yml) |
| **Maint Sync pyproject.toml from versions.env** (`maint-sync-env-from-pyproject.yml`, maintenance bucket) | `workflow_dispatch` on a selected non-default branch | Align source files to `autofix-versions.env` and commit any repairs back to that branch. Gate checks source alignment before merge. | ⚪ Manual topic-branch repair | [Maint sync env runs](https://github.com/stranske/Workflows/actions/workflows/maint-sync-env-from-pyproject.yml) |
| **Maint 52 Validate Workflows** (`maint-52-validate-workflows.yml`, maintenance bucket) | `pull_request`, `push` (`main`) | Parse every workflow file with `yq`, honour the Actionlint allowlist, and fail fast when syntax errors or lint violations appear. | ⚪ Automatic on PR/main | [Maint 52 workflow validations](https://github.com/stranske/Workflows/actions/workflows/maint-52-validate-workflows.yml) |
| **Maint 52 Sync Dev Versions** (`maint-52-sync-dev-versions.yml`, maintenance bucket) | post-settled-source-commit `push` (`autofix-versions.env` on `main`), drift catch-up `schedule`, `workflow_dispatch` | Propagate already-validated canonical source pins from `autofix-versions.env` to consumer `pyproject.toml`/lock files; never independently proposes newer PyPI versions. | ⚪ Propagation after settled source | [Sync dev versions runs](https://github.com/stranske/Workflows/actions/workflows/maint-52-sync-dev-versions.yml) |
| **Maint Auto-Update PyPI Versions** (`maint-auto-update-pypi-versions.yml`, maintenance bucket) | `schedule` (Mondays 03:00 UTC), `workflow_dispatch` | Sole source proposal for routine dev-tool pins; opens or refreshes one weekly PR, with an explicit security override. | ⚪ Scheduled | [Auto-update PyPI versions runs](https://github.com/stranske/Workflows/actions/workflows/maint-auto-update-pypi-versions.yml) |
| **Maint Coverage Guard** (`maint-coverage-guard.yml`, maintenance bucket) | `schedule` (`45 6 * * *`), `workflow_dispatch` | Audit the latest Gate coverage trend artifact and compare it against the baseline, failing when coverage regresses beyond the guard thresholds. | ⚪ Scheduled | [Maint Coverage Guard runs](https://github.com/stranske/Workflows/actions/workflows/maint-coverage-guard.yml) |
| **Maint 46 Post CI** (`maint-46-post-ci.yml`, maintenance bucket) | `workflow_run` (Gate, `completed`) | Recovery-only: inspect the Gate run for a missing or failed `summary` job; when recovery is needed, collect the Gate artifacts, render the consolidated CI summary with coverage deltas, publish a markdown preview, and refresh the Gate commit status. Its independent trusted failure-tracker job processes both failed and healthy same-repository PR Gate runs and uploads the exact issue snapshot path. | ⚪ Automatic follow-up | [Maint 46 runs](https://github.com/stranske/Workflows/actions/workflows/maint-46-post-ci.yml) |
| **Maint 45 Cosmetic Repair** (`maint-45-cosmetic-repair.yml`, maintenance bucket) | `workflow_dispatch` | Run pytest + fixers manually and open a labelled PR when changes are required. | ⚪ Manual | [Maint 45 manual entry](https://github.com/stranske/Workflows/actions/workflows/maint-45-cosmetic-repair.yml) |
| **Health 40 Repo Selfcheck** (`health-40-repo-selfcheck.yml`, maintenance bucket) | `schedule` (weekly, Mondays 06:20 UTC), `workflow_dispatch` | Capture repository pulse metrics. | ⚪ Scheduled | [Health 40 summary](https://github.com/stranske/Workflows/actions/workflows/health-40-repo-selfcheck.yml) |
| **Health 41 Repo Health** (`health-41-repo-health.yml`, maintenance bucket) | `schedule` (weekly), `workflow_dispatch` | Perform weekly dependency and repo hygiene sweep. | ⚪ Scheduled | [Health 41 dashboard](https://github.com/stranske/Workflows/actions/workflows/health-41-repo-health.yml) |
| **Health 40 Sweep** (`health-40-sweep.yml`, maintenance bucket) | `schedule` (weekly + daily), `pull_request`, `push`, `workflow_dispatch` | Run Actionlint on workflow edits and verify branch protection during sweeps. | ⚪ Scheduled/manual | [Health 40 sweep history](https://github.com/stranske/Workflows/actions/workflows/health-40-sweep.yml) |
| **Health 42 Actionlint** (`health-42-actionlint.yml`, maintenance bucket) | `workflow_dispatch`, `workflow_call` | Provide the reusable Actionlint leg for sweeps or focused rehearsals. | ⚪ Manual/reusable | [Health 42 logs](https://github.com/stranske/Workflows/actions/workflows/health-42-actionlint.yml) |
| **Health 44 Gate Branch Protection** (`health-44-gate-branch-protection.yml`, maintenance bucket) | `pull_request`, `workflow_dispatch`, `workflow_call` | Verify the configured default-branch status contexts. | ⚪ Scheduled via sweep / manual | [Health 44 enforcement logs](https://github.com/stranske/Workflows/actions/workflows/health-44-gate-branch-protection.yml) |
| **Health 50 Security Scan** (`health-50-security-scan.yml`, maintenance bucket) | `push`, `pull_request`, `schedule` (weekly) | Run CodeQL security analysis on Python code to detect vulnerabilities. | ⚪ Automatic/scheduled | [Security scan runs](https://github.com/stranske/Workflows/actions/workflows/health-50-security-scan.yml) |
| **Health 51 Actions SAST (zizmor)** (`health-51-zizmor.yml`, maintenance bucket) | `push`, `pull_request`, `schedule` (weekly) | Static-analyze the GitHub Actions YAML shipped to consumer repos (zizmor) for injection/permission issues; upload findings to code scanning. | ⚪ Automatic/scheduled | [zizmor runs](https://github.com/stranske/Workflows/actions/workflows/health-51-zizmor.yml) |
| **Health 52 Semgrep Scan** (`health-52-semgrep.yml`, maintenance bucket) | `push`, `pull_request`, `schedule` (weekly) | Run advisory Semgrep CE analysis for Python, GitHub Actions, default, and secrets rulesets; upload SARIF to code scanning when available. | ⚪ Automatic/scheduled | [Semgrep runs](https://github.com/stranske/Workflows/actions/workflows/health-52-semgrep.yml) |
| **Health 53 Scorecard** (`health-53-scorecard.yml`, maintenance bucket) | `push` (main), `branch_protection_rule`, `schedule` (weekly), `workflow_dispatch` | Run the OpenSSF Scorecard supply-chain posture scan (report-only/advisory) and upload findings to code scanning. Published API results are consumed by the weekly repo-review Scorecard scan (`scorecard-scan.json`) as a human-gated candidate source. | ⚪ Automatic/scheduled | [Scorecard runs](https://github.com/stranske/Workflows/actions/workflows/health-53-scorecard.yml) |
| **Health 67 Integration Sync Check** (`health-67-integration-sync-check.yml`, maintenance bucket) | `workflow_run` (`Maint 69 Sync Integration Repo` on `main`), `pull_request` (templates), `repository_dispatch`, `schedule` (daily), `workflow_dispatch` | Validate that Workflows-Integration-Tests repo stays in sync with templates after `Maint 69` completes (avoiding push-to-`main` sync races). Non-PR runs create or close `integration-sync` issues as drift appears or clears; PR runs summarize differences without mutating issues. | ⚪ Automatic/scheduled | [Integration sync runs](https://github.com/stranske/Workflows/actions/workflows/health-67-integration-sync-check.yml) |
| **Health 68 Consumer Sync Drift Check** (`health-68-consumer-sync-drift.yml`, maintenance bucket) | `push` (templates + manifest + scripts), `workflow_run` (`Merge Sync PRs`), `schedule` (daily), `workflow_dispatch` | Detect template/manifest drift across registered consumer repos. Creates or refreshes a transient alert for actionable drift and closes it after a clean comparison. | ⚪ Automatic/scheduled | [Consumer drift runs](https://github.com/stranske/Workflows/actions/workflows/health-68-consumer-sync-drift.yml) |
| **Health 70 Validate Sync Manifest** (`health-70-validate-sync-manifest.yml`, maintenance bucket) | `pull_request`, `push` | Validate that sync-manifest.yml includes all sync-able files. Fails PRs that add workflows/prompts/scripts without updating manifest. | ⚪ Required on PRs | [Manifest validation runs](https://github.com/stranske/Workflows/actions/workflows/health-70-validate-sync-manifest.yml) |
| **Health 71 Sync Health Check** (`health-71-sync-health-check.yml`, maintenance bucket) | `schedule` (daily), `workflow_dispatch` | Monitor sync workflow health and create issues when all recent runs failed or sync is stale. | ⚪ Scheduled/manual | [Sync health check runs](https://github.com/stranske/Workflows/actions/workflows/health-71-sync-health-check.yml) |
| **Health 72 Template Sync** (`health-72-template-sync.yml`, maintenance bucket) | `pull_request`, `push` (exact-sync sources/templates) | Validate that manifest-declared exact template-sync files match their `templates/consumer-repo/` copies. | ⚪ Required on PRs | [Template sync validation runs](https://github.com/stranske/Workflows/actions/workflows/health-72-template-sync.yml) |
| **Health 73 Template Completeness** (`health-73-template-completeness.yml`, maintenance bucket) | `pull_request`, `push` (`.github/workflows/`, `templates/`, manifest) | Validate that consumer-intended workflows exist in template and manifest. Prevents workflows added to .github/workflows/ without being synced to consumer repos. | ⚪ Required on PRs | [Template completeness runs](https://github.com/stranske/Workflows/actions/workflows/health-73-template-completeness.yml) |
| **Health 74 Template Drift** (`health-74-template-drift.yml`, maintenance bucket) | `pull_request`, `push` (any `.github/workflows/*.yml`, templates, drift checker config) | Check normalized content drift between main workflows with consumer template counterparts and their `templates/consumer-repo/` copies. Fails on unallowlisted drift; permits only fingerprinted baseline differences in `config/template-drift-allowlist.txt`. | ⚪ Required on matching PRs | [Template drift runs](https://github.com/stranske/Workflows/actions/workflows/health-74-template-drift.yml) |
| **Health 75 API Rate Diagnostic** (`health-75-api-rate-diagnostic.yml`, maintenance bucket) | `schedule` (hourly), `workflow_dispatch` | Monitor API rate limit utilization across GITHUB_TOKEN, PATs, and GitHub Apps. Alerts when usage exceeds 85%, tracks consumer repo workflow activity, and provides load balancing analysis. | ⚪ Scheduled/manual | [API rate diagnostic runs](https://github.com/stranske/Workflows/actions/workflows/health-75-api-rate-diagnostic.yml) |
| **Health 76 Codex CLI Freshness** (`health-76-codex-cli-freshness.yml`, maintenance bucket) | `schedule` (weekly), `workflow_dispatch` | Compare the verifier `@openai/codex` install pin with the latest npm release and upload a machine-readable update-path contract for deliberate CLI upgrades. | ⚪ Scheduled/manual | [Codex CLI freshness runs](https://github.com/stranske/Workflows/actions/workflows/health-76-codex-cli-freshness.yml) |
| **Backplane Contract Integrity** (`health-78-backplane-contract.yml`, maintenance bucket) | `pull_request`, `push` (contract set: schemas, registry, validator, fixtures), `schedule` (weekly), `workflow_dispatch` | Workflows-internal gate over the run-contract/v1 contract set: asserts the three schemas load as valid draft 2020-12 JSON Schema, `config/backplane_participants.json` keeps the required shape, and the bundled valid/invalid fixtures behave (validator self-smoke). | ⚪ Required on contract PRs | [Backplane contract integrity runs](https://github.com/stranske/Workflows/actions/workflows/health-78-backplane-contract.yml) |
| **Health 83 Dependency Sync Efficiency** (`health-83-dependency-sync-efficiency.yml`, maintenance bucket) | `schedule` (weekly), `workflow_dispatch` | Publishes advisory lane, amplification, stale/replacement, agent-exception, and stable-delivery convergence evidence for dependency and generated sync work. The trailing window is fully paginated, while all-time collection remains explicitly incomplete; the durable tracker changes only on a material-evidence fingerprint change. | ⚪ Scheduled/manual | [Dependency sync efficiency runs](https://github.com/stranske/Workflows/actions/workflows/health-83-dependency-sync-efficiency.yml) |
| **Health 84 LangSmith Observability** (`health-84-langsmith-observability.yml`, maintenance bucket) | `schedule` (daily), `workflow_dispatch` | Checks weekly workflow cadence, `workflows-agents` cloud trace freshness, and pause review metadata; uploads evidence and upserts a durable issue with human-attention labels while degraded. | ⚪ Scheduled/manual | [LangSmith observability health runs](https://github.com/stranske/Workflows/actions/workflows/health-84-langsmith-observability.yml) |
| **Health 85 CI Time Budget** (`health-85-ci-time-budget.yml`, maintenance bucket) | `schedule` (daily, 11:35 UTC), `workflow_dispatch` | Publishes trailing-seven-day Gate p50/p90, exponential resource share and recovery history to `docs/reports/ci-budget.json` on the dedicated `ci-time-budget` branch and as an artifact. Files/updates budget issues while over target and closes after seven consecutive healthy daily p50s; advisory only, never a merge gate. See [CI budget control](WORKFLOWS.md#daily-ci-time-budget-health-85) for formula, report consumption and credentials. | ⚪ Scheduled/manual | [CI time budget runs](https://github.com/stranske/Workflows/actions/workflows/health-85-ci-time-budget.yml) |
| **Reusable Backplane Conformance** (`reusable-backplane-conformance.yml`, reusable bucket) | `workflow_call` | Validate a participating repo's emitted run-contract/v1 envelope (producer/bridge) or ingested satellite object (consumer) against the canonical Workflows-owned schemas plus the opt-in participant registry. The caller repo identity is bound to the registry lookup. The Inv-Man opt-in policy additionally verifies evidence-object files, manifest hashes, and two-way evidence-reference closure. No-op for non-participants. | ⚪ Reusable (opt-in) | [Backplane conformance runs](https://github.com/stranske/Workflows/actions/workflows/reusable-backplane-conformance.yml) |
| **Maint 68 Sync Consumer Repos** (`maint-68-sync-consumer-repos.yml`, maintenance bucket) | `schedule`, `workflow_dispatch` | Coalesce copied-file changes into stable ready-for-review candidate and promoted-delivery PRs. Scheduled runs use the full typed manifest; bounded repairs may select an exact base/head source delta that Maint 71 evidence preserves through promotion. Exact-plan evidence gates promotion; successful write waves dispatch the matching Maint 71 selector; staging labels and disabled auto-merge precede every head mutation without changing PR readiness; unchanged deliveries retain their review state. Explicit repo filters cannot bypass the canary boundary. | ⚪ Automatic/manual | [Consumer sync runs](https://github.com/stranske/Workflows/actions/workflows/maint-68-sync-consumer-repos.yml) |
| **Maint 69 Sync Integration Repo** (`maint-69-sync-integration-repo.yml`, maintenance bucket) | `push` (templates), `schedule` (daily 05:41 UTC), `workflow_dispatch` | Sync integration-repo templates to Workflows-Integration-Tests repository. Resolves drift detected by Health 67. Supports dry-run mode; failed-sync alerts close automatically after the next successful non-dry run. | ⚪ Automatic/manual | [Integration sync runs](https://github.com/stranske/Workflows/actions/workflows/maint-69-sync-integration-repo.yml) |
| **Maint 69 Sync Labels** (`maint-69-sync-labels.yml`, maintenance bucket) | `push` (labels-core.yml), `workflow_dispatch` | Sync core functional labels from labels-core.yml to consumer repositories. Distinguishes functional workflow labels from informational repo-specific labels. Supports dry-run mode. | ⚪ Automatic/manual | [Label sync runs](https://github.com/stranske/Workflows/actions/workflows/maint-69-sync-labels.yml) |
| **Auto-Fix Integration Test Failures** (`maint-71-auto-fix-integration.yml`, maintenance bucket) | `issues` (opened or reopened), `issue_comment` (owner failure report), `workflow_dispatch` | Checks the linked Integration-Tests run and applies Black and Ruff formatting changes when needed. | 🟢 Automated | [Auto-fix runs](https://github.com/stranske/Workflows/actions/workflows/maint-71-auto-fix-integration.yml) |
| **Merge Sync PRs** (`maint-71-merge-sync-prs.yml`, maintenance bucket) | `schedule`, `repository_dispatch`, `workflow_dispatch`, `workflow_call` | Sole merge/close reconciler for generated sync delivery. Stable PRs advance through capacity-aware bounded review settlement, exact-head sealing, and a fresh required Gate; active review threads remain hard blockers unless an authenticated proof names that exact head, thread, and a Workflows source fix contained in the delivery. A request-only dispatch can ask the originating reviewer to reassess one exact active thread on a dev-tool, `sync/workflows-candidate`, or stable `sync/workflows-delivery` branch without resolving or reconciling it. Candidate mode validates and uploads plan-bound evidence before merge, then dispatches exact-plan promotion only when every canary is terminal. | ⚪ Scheduled/manual/callable | [Merge sync runs](https://github.com/stranske/Workflows/actions/workflows/maint-71-merge-sync-prs.yml) |
| **Maint 72 Fix PR Body Conflicts** (`maint-72-fix-pr-body-conflicts.yml`, maintenance bucket) | `workflow_dispatch`, `schedule` (weekly) | Previews PR-body cleanup by default. Explicit apply repairs unprotected `main` directly and opens a reviewable cleanup PR for protected `main`. | ⚪ Manual/scheduled | [PR body fix runs](https://github.com/stranske/Workflows/actions/workflows/maint-72-fix-pr-body-conflicts.yml) |
| **Maint 74 Ledger Base Sync** (`maint-74-ledger-base-sync.yml`, maintenance bucket) | `workflow_dispatch`, `schedule` (Mondays 06:00 UTC) | Align `.agents` ledger base entries to the repository default branch. | ⚪ Manual/scheduled | [Ledger base sync runs](https://github.com/stranske/Workflows/actions/workflows/maint-74-ledger-base-sync.yml) |
| **Maint 77 Model Registry Freshness** (`maint-77-model-registry-freshness.yml`, maintenance bucket) | `schedule` (Mondays 05:20 UTC), `workflow_dispatch`, `pull_request` (registry/slot/policy/checker paths) | Validates explicit model decisions, evidence, lifecycle, and profile slots offline. Scheduled/manual runs add credential-gated provider-catalog drift and refresh one review issue; catalog changes never auto-select a model. | ⚪ Scheduled/manual + PR gate | [Model registry freshness runs](https://github.com/stranske/Workflows/actions/workflows/maint-77-model-registry-freshness.yml) |
| **Maint 78 Verifier Model Cost and Quality** (`maint-78-model-evaluation-pilot.yml`, maintenance bucket) | Catalog dispatch, relevant push, or manual dispatch | Automatic runs publish a no-spend plan. The current historical labels and screen inputs are misaligned, so model runs are blocked until a separate eight-case set of captured verifier inputs is independently adjudicated. A manual zero-model-call capture can replay merged PR context across repos immediately, marked retrospective. Then a balanced Codex subscription screen can identify finalists; a separate paired API confirmation is capped at two models, eight cases, no retries, and a $5 worst-case standard-rate estimate. The larger Wilson sample is a long-term statistical approval target. Separate `verify-paired` mode supplies a source-held, read-only two-case native API screen; see [its fixed packet and proposed caps](../ops/VERIFY_PAIRED_API_SCREEN.md). | ⚪ No-spend plan / capture / gated screen and confirmation | [Model evaluation runs](https://github.com/stranske/Workflows/actions/workflows/maint-78-model-evaluation-pilot.yml) |
| **Maint 79 Verifier Corpus Harvest** (`maint-79-verifier-corpus-harvest.yml`, maintenance bucket) | `schedule` (weekly), `workflow_dispatch` | Grows the frozen verifier evaluation corpus from realized PR outcomes. High-confidence cases auto-promote only after an unchanged-head seven-minute review window, passing required checks, and zero active review threads; ambiguous cases stage FYI-only and auto-expire. The exact Workflows-local `verifier-corpus-harvest/auto` PR with controlled `automation` and `model-selection` labels skips post-merge issue-acceptance verification because this recurring data job is governed by those Maint 79 gates and must not verify itself. Never changes a selection. | 🟢 Scheduled | [Verifier corpus harvest runs](https://github.com/stranske/Workflows/actions/workflows/maint-79-verifier-corpus-harvest.yml) |
| **Maint 86 Model Promotion Prepare** (`maint-86-model-promotion-prepare.yml`, maintenance bucket) | `workflow_dispatch` | Evaluates a benchmark and, for a passing candidate (preferring same-family cost≤ changes; riskier swaps require explicit approval) (or a gate-breach rollback), opens a registry-change PR. Not auto-merged — a human merges to approve. Dispatch-only until a trustworthy approval benchmark exists. | ⚪ Manual/prepared | [Model promotion prepare runs](https://github.com/stranske/Workflows/actions/workflows/maint-86-model-promotion-prepare.yml) |
| **LangSmith Metrics Dashboard** (`maint-80-langsmith-metrics-dashboard.yml`, maintenance bucket) | `workflow_dispatch`, `schedule` (Mondays 09:00 UTC) | Generates weekly LangSmith trace coverage dashboard by downloading metrics from autopilot artifacts, computing coverage, and creating issue reports. | ⚪ Manual/scheduled | [LangSmith metrics runs](https://github.com/stranske/Workflows/actions/workflows/maint-80-langsmith-metrics-dashboard.yml) |
| **Sync/Dependency Campaign** (`maint-82-sync-dependency-campaign.yml`, maintenance bucket) | `schedule` (10-minute continuation sweep), `workflow_dispatch`, `repository_dispatch` | Refreshes the GitHub-visible campaign issue and persists Maint 71 handoffs as a durable queue. Due transient review/check holds dispatch at most one candidate, delivery, and dev-tool lane; actionable review or source failures remain assigned rather than retried as timers. | ⚪ Scheduled/manual | [Sync/Dependency campaign runs](https://github.com/stranske/Workflows/actions/workflows/maint-82-sync-dependency-campaign.yml) |
| **Maint 83 Bootstrap Consumer** (`maint-83-bootstrap-consumer.yml`, maintenance bucket) | `schedule` (Mondays 06:17 UTC), `workflow_dispatch` | Runs weekly read-only settings verification across registered consumers and applies the manual GitHub-settings bootstrap a freshly-registered consumer needs: workflow permissions, required variables, the automation-bot collaborator invite, and the load-bearing `priority:high` / `priority:normal` / `priority:low` opener-routing labels. Manual dispatch is dry-run by default; execute mode performs cross-repository settings and label writes through `scripts/bootstrap_consumer_settings.py`. | ⚪ Scheduled/manual | [Bootstrap consumer runs](https://github.com/stranske/Workflows/actions/workflows/maint-83-bootstrap-consumer.yml) |
| **Maint 84 Prune Agent Stubs** (`maint-84-prune-agent-stubs.yml`, maintenance bucket) | `schedule` (Mondays 08:00 UTC), `workflow_dispatch` | Garbage-collects `agents/<agent>-<N>.md` bootstrap stubs whose issue `#N` is closed via `scripts/prune_agent_stubs.py`, preventing unbounded accumulation; dry-run by default on manual dispatch. | ⚪ Scheduled/manual | [Prune agent stubs runs](https://github.com/stranske/Workflows/actions/workflows/maint-84-prune-agent-stubs.yml) |
| **Maint 85 Keepalive Durability Export** (`maint-85-keepalive-durability-export.yml`, maintenance bucket) | `schedule` (Mondays 09:45 UTC), `workflow_dispatch` | Classifies merged keepalive PRs after a grace period and emits Workflows-owned `langsmith-fleet/v1` durability records for Orchestrator outcome ingest. | ⚪ Scheduled/manual | [Keepalive durability export runs](https://github.com/stranske/Workflows/actions/workflows/maint-85-keepalive-durability-export.yml) |
| **Maint 60 Release** (`maint-60-release.yml`, maintenance bucket) | `push` (tags `v*`) | Create GitHub releases automatically when version tags are pushed. | ⚪ Tag-triggered | [Release workflow runs](https://github.com/stranske/Workflows/actions/workflows/maint-60-release.yml) |
| **Maint 61 Release Please** (`maint-61-release-please.yml`, maintenance bucket) | `push` (`main`) | Open or update the release-please Release PR from Conventional Commits using the manifest seeded at `1.1.2`; merges create changelog updates, tags, and GitHub releases. | ⚪ Automatic on main | [Release Please runs](https://github.com/stranske/Workflows/actions/workflows/maint-61-release-please.yml) |
| **Agents Guard** (`agents-guard.yml`, agents bucket) | `pull_request` (`opened`, `reopened`, `synchronize`, `ready_for_review`); `pull_request_target` (`labeled`, `unlabeled`) when the PR carries a trusted registry routing label from `.github/agents/registry.yml` (protected-file authorization labels such as `agents:allow-change` do not start evaluation unless a routing label is also present) | Evaluate protected-file policy on eligible events. Inspect failures for missing policy requirements or trusted registry evidence. | Policy status **`Health 45 Agents Guard / guard`** | [Agents Guard run history](https://github.com/stranske/Workflows/actions/workflows/agents-guard.yml) |
| **Agents Auto-Label** (`agents-auto-label.yml`, agents bucket) | `issues` (`opened`) | Automatically apply semantic labels to new issues based on content analysis using label_matcher.py. | ⚪ Event-driven | [Auto-label runs](https://github.com/stranske/Workflows/actions/workflows/agents-auto-label.yml) |
| **Agents Autofix Dispatch** (`agents-autofix-dispatcher.yml`, agents bucket) | `repository_dispatch` (`autofix_gate_failure`) | Forwards Gate failure notifications with PR context to `agents-autofix-loop.yml`. | ⚪ Event-driven | [Autofix dispatch runs](https://github.com/stranske/Workflows/actions/workflows/agents-autofix-dispatcher.yml) |
| **Agents Issue Format Guard** (`agents-issue-format-guard.yml`, agents bucket) | `issues`, `workflow_dispatch` | Validates non-exempt issues against `AGENT_ISSUE_FORMAT` and dispatches `agents-issue-optimizer.yml` format passes within a bounded retry budget. | ⚪ Event-driven | [Issue format guard runs](https://github.com/stranske/Workflows/actions/workflows/agents-issue-format-guard.yml) |
| **Agents Issue Optimizer** (`agents-issue-optimizer.yml`, agents bucket) | `issues` (labeled), `workflow_dispatch` | Runs issue `analyze`, `apply`, or `format` passes for `agents:optimize`, `agents:apply-suggestions`, and `agents:format`. | ⚪ Event-driven | [Issue optimizer runs](https://github.com/stranske/Workflows/actions/workflows/agents-issue-optimizer.yml) |
| **Capability Check** (`agents-capability-check.yml`, agents bucket) | `issues` (labeled `agents:capability-check`) | Pre-flight check before agent assignment to identify blockers like ambiguous scope or missing context. | ⚪ Event-driven | [Capability check runs](https://github.com/stranske/Workflows/actions/workflows/agents-capability-check.yml) |
| **Duplicate Detection** (`agents-dedup.yml`, agents bucket) | `issues` (labeled `agents:dedup`) | Detects duplicate issues using semantic similarity analysis and posts findings as a comment. | ⚪ Event-driven | [Duplicate detection runs](https://github.com/stranske/Workflows/actions/workflows/agents-dedup.yml) |
| **Agents Verify to Issue v2** (`agents-verify-to-issue-v2.yml`, agents bucket) | `pull_request_target` (labeled `verify:create-issue`) | Enhanced follow-up issue creation using LangChain LLM for multi-round analysis. | ⚪ Event-driven | [Verify-to-issue v2 runs](https://github.com/stranske/Workflows/actions/workflows/agents-verify-to-issue-v2.yml) |
| **Agents Verify to New PR** (`agents-verify-to-new-pr.yml`, agents bucket) | `pull_request_target` (labeled `verify:create-new-pr`), `workflow_dispatch` | Create a follow-up issue from verification feedback and trigger auto-pilot to prepare a new PR. | ⚪ Event-driven | [Verify-to-new-pr runs](https://github.com/stranske/Workflows/actions/workflows/agents-verify-to-new-pr.yml) |
| **Agents Bot Comment Handler** (`agents-bot-comment-handler.yml`, agents bucket) | `pull_request` (labeled), `workflow_run` (Gate, `completed`), `workflow_dispatch` | Dispatch the reusable bot-comment handler to resolve automated review comments after Gate or manual triggers. | ⚪ Event-driven | [Bot comment handler runs](https://github.com/stranske/Workflows/actions/workflows/agents-bot-comment-handler.yml) |
| **Agents Verifier** (`agents-verifier.yml`, agents bucket) | `pull_request_target` (labeled `verify:*`), `workflow_dispatch` | Build acceptance-context prompt (PR + linked issues), execute the requested verifier mode (`checkbox`, `evaluate`, or `compare`), and post a verdict; follow-up issues/PRs remain label-triggered via `verify:create-issue` / `verify:create-new-pr`. | ⚪ Event-driven / manual | [Agents verifier runs](https://github.com/stranske/Workflows/actions/workflows/agents-verifier.yml) |
| **agents-weekly-metrics** (`agents-weekly-metrics.yml`, agents bucket) | `schedule` (weekly), `workflow_dispatch` | Aggregate agent metrics (keepalive, autofix, verifier) and generate markdown summary. | ⚪ Scheduled weekly | [Weekly metrics runs](https://github.com/stranske/Workflows/actions/workflows/agents-weekly-metrics.yml) |
| **Agents Model Profile Trial** (`agents-model-profile-trial.yml`, agents bucket) | `workflow_dispatch` | Dispatch exactly one pinned, read-only Astra/Sol/Terra/Luna instrumentation arm with a frozen packet/source identity. | ⚪ Manual canary | [Model profile trial runs](https://github.com/stranske/Workflows/actions/workflows/agents-model-profile-trial.yml) |
| **Agents 63 Issue Intake** (`agents-63-issue-intake.yml`, agents bucket) | `issues`, `workflow_call`, `workflow_dispatch` | Canonical front door for agent issue intake. Listens for `agent:codex` labels and services ChatGPT sync requests through the shared normalization pipeline. | ⚪ Critical surface (automation intake) | [Issue intake runs](https://github.com/stranske/Workflows/actions/workflows/agents-63-issue-intake.yml) |
| **Agents 64 Verify Agent Assignment** (`agents-64-verify-agent-assignment.yml`, agents bucket) | `workflow_call`, `workflow_dispatch` | Audit orchestrated assignments and alert on drift. | ⚪ Reusable/manual | [Agents 64 audit history](https://github.com/stranske/Workflows/actions/workflows/agents-64-verify-agent-assignment.yml) |
| **Agents Moderate Connector Comments** (`agents-moderate-connector.yml`, agents bucket) | `issue_comment` (`created`) | Guard connector-authored comments on PR threads using allow/deny lists and optional debug labelling. | ⚪ Event-driven | [Moderation workflow runs](https://github.com/stranske/Workflows/actions/workflows/agents-moderate-connector.yml) |
| **CI Autofix Loop** (`autofix.yml`, agents bucket) | `workflow_run`, `pull_request_target` (`labeled`) | Detect CI failures in agent PRs and apply automated formatting fixes when the `autofix` label is present. | ⚪ Triggered by Gate failures / label | [Autofix workflow runs](https://github.com/stranske/Workflows/actions/workflows/autofix.yml) |
| **Reusable Python CI** (`reusable-10-ci-python.yml`, error-checking bucket) | `workflow_call` | Provide shared lint/type/test matrix for Gate and manual callers. | ✅ When invoked | [Reusable Python CI runs](https://github.com/stranske/Workflows/actions/workflows/reusable-10-ci-python.yml) |
| **Reusable Node CI** (`reusable-11-ci-node.yml`, error-checking bucket) | `workflow_call`, `workflow_dispatch` | Provide shared Node.js/TypeScript lint/format/typecheck/test matrix for JS/TS callers. | ✅ When invoked | [Reusable Node CI runs](https://github.com/stranske/Workflows/actions/workflows/reusable-11-ci-node.yml) |
| **Reusable Docker CI** (`reusable-12-ci-docker.yml`, error-checking bucket) | `workflow_call` | Build and smoke-test container images. | ✅ When invoked | [Reusable Docker runs](https://github.com/stranske/Workflows/actions/workflows/reusable-12-ci-docker.yml) |
| **Reusable Cross-Repo Smoke** (`reusable-13-cross-repo-smoke.yml`, error-checking bucket) | `workflow_call` | Check out host repository plus a pinned dependency ref and run a caller-supplied cross-repo smoke command. | ✅ When invoked | [Reusable Cross-Repo Smoke runs](https://github.com/stranske/Workflows/actions/workflows/reusable-13-cross-repo-smoke.yml) |
| **Reusable Autofix** (`reusable-18-autofix.yml`, error-checking bucket) | `workflow_call` | Centralise formatter + fixer execution. | ✅ When invoked | [Reusable Autofix runs](https://github.com/stranske/Workflows/actions/workflows/reusable-18-autofix.yml) |
| **Reusable Dependency Repair Contract** (`reusable-19-dependency-repair-contract.yml`, error-checking bucket) | `workflow_call` | Validate dependency repair provenance without executing pull-request code. | ✅ When invoked | [Dependency repair contract runs](https://github.com/stranske/Workflows/actions/workflows/reusable-19-dependency-repair-contract.yml) |
| **Reusable Model Profile Trial** (`reusable-model-profile-trial.yml`, agents bucket) | `workflow_call` | Execute one immutable read-only Codex trial arm and upload a strict quarantine artifact. | ✅ When invoked | [Reusable model profile trial runs](https://github.com/stranske/Workflows/actions/workflows/reusable-model-profile-trial.yml) |
| **Maint 88 Verifier Runtime Comparison** (`maint-88-verifier-runtime-comparison.yml`, maintenance bucket) | `workflow_dispatch` | Finite #3904 baseline/candidate experiment with immutable inputs, common dependencies, explicit cold application caches, raw JUnit/coverage and source hashes. Retains ordinary Gate acceptance. | ⚪ Manual | [Comparison runs](https://github.com/stranske/Workflows/actions/workflows/maint-88-verifier-runtime-comparison.yml) |
| **Maint 89 Verifier Shadow Report** (`maint-89-verifier-shadow-report.yml`, maintenance bucket) | `schedule`, `workflow_dispatch` | Daily FYI report on shadow-run candidate verifier judges: collects `verifier-shadow.json` from fleet `comparison-results-*` artifacts into a 90-day ledger, applies the pre-registered criteria, updates one issue. Records only; no gate, no promotion. | ⚪ Scheduled/manual | [Verifier shadow report runs](https://github.com/stranske/Workflows/actions/workflows/maint-89-verifier-shadow-report.yml) |
| **Maint 90 Sync Finding Assessment** (`maint-90-sync-finding-assessment.yml`, maintenance bucket) | `schedule`, `workflow_dispatch` | Automatic producer for the Maint 71 finding-verification fallback: a sync-PR finding left unanswered past the policy window gets an independent Codex assessment plus a regression run with a negative control; a PASS is published on the durable issue and Maint 71 is dispatched with the resolution proof, anything else is handed to the owner once per finding and head. Never resolves or merges itself. | ⚪ Scheduled/manual | [Finding assessment runs](https://github.com/stranske/Workflows/actions/workflows/maint-90-sync-finding-assessment.yml) |
| [Selftest: Reusables](WORKFLOWS.md#self-test-harness) | [Triggers and modes](SELFTESTS.md#triggers) | Exercise shared CI against a consumer fixture. | ⚪ Supplemental | [Workflow runs](https://github.com/stranske/Workflows/actions/workflows/selftest-reusable-ci.yml) |

**PR body conflict guard.** `pr_body.md` is PR-specific. It must stay out of `main` and be ignored in consumer repos (`.gitignore` + `merge=ours` in `.gitattributes`). The Codex runner unstages the file before committing. If the file reaches `main`, use Maint 72 with the registered `target_repo` to preview the repair. The weekly run and the default manual run only preview. An explicit manual `dry_run=false` applies the repair directly on confirmed unprotected `main`. On protected `main` it opens a ready-for-review cleanup PR and reports its link. Follow that PR through the consumer repository's normal checks, review, and merge. Verify that `pr_body.md` is absent from the merged default and the ignore rule is present.

## Policy

- **Required checks (universal ruleset).** The default-branch ruleset requires the
  **`summary`** job context on every pull request per
  `.github/config/required-contexts.json`. That job aggregates every other Gate job,
  so requiring `summary` gates the full Gate fan-out. The same job also publishes the
  duplicate **`Gate / gate`** commit status; that duplicate is not listed in the JSON
  file and must not replace `summary` in branch protection.
- **Agents Guard (agents-surface, separate from the ruleset list).** **Health 45 Agents
  Guard / guard** is published for eligible pull requests; it is not part of the universal
  `required_contexts` list in `.github/config/required-contexts.json`. GitHub may
  surface it under **Required** when branch protection or rulesets include that
  context name.

### Required status contexts (default branch)

Keep this table handy when you need the canonical strings for reviews or branch
protection audits—it mirrors the
[Agents Workflow Protection Policy](../AGENTS_POLICY.md#required-checks-and-status-contexts)
list and references the Health 44 enforcement workflow that captures the JSON
snapshots for audit trails.

| Check | Status context | Where to verify |
| --- | --- | --- |
| **Gate summary job (ruleset)** | `summary` | [Health 44 enforcement logs](https://github.com/stranske/Workflows/actions/workflows/health-44-gate-branch-protection.yml), Checks tab → **summary** under **Required**, `.github/config/required-contexts.json`, [Policy quick reference](../AGENTS_POLICY.md#required-checks-and-status-contexts) |
| **Gate (duplicate commit status)** | `Gate / gate` | Checks tab (posted by the summary job; not a substitute for the `summary` ruleset context) |
| **Health 45 Agents Guard (agents-surface)** | `Health 45 Agents Guard / guard` | Checks tab for an eligible event, [Policy quick reference](../AGENTS_POLICY.md#required-checks-and-status-contexts) |

- **Docs-only detection.** Lives exclusively inside Gate—there is no separate
  docs-only workflow.
- **Autofix.** Follow the [Autofix routes](WORKFLOWS.md#autofix-routes) to the repair run or patch artifact.
- **Branch protection.** The default-branch ruleset must require **`summary`** only
  (see `.github/config/required-contexts.json`). Health 44 resolves the current
  default branch via the REST API and either enforces or verifies the rule (requires
  a `BRANCH_PROTECTION_TOKEN` secret with admin scope for enforcement). The Gate
  `summary` job also posts the duplicate **`Gate / gate`** commit status and a
  timeline comment; those surfaces support triage but the ruleset blocks merges on
  **`summary`**, not on the duplicate context alone. **Health 45 Agents Guard /
  guard** is enforced separately on pull requests that touch protected agents
  workflow files.
- **Code Owner reviews.** CODEOWNERS routes notifications. The Workflows main
  ruleset requires zero approvals. Health 45 separately evaluates its own
  protected-file requirements on eligible changes.
- **Types.** When mypy is pinned, run it in the pinned interpreter only to avoid
  stdlib stub drift. `reusable-10-ci-python.yml` reads the desired version from
  `pyproject.toml` and guards the mypy step with
  `matrix.python-version == steps.mypy-pin.outputs.python-version`. Ruff and
  pytest still execute across the full matrix.
- **Automation labels.** Keep the labels used by automation available:
  `workflows`, `ci`, `devops`, `docs`, `refactor`, `enhancement`, `autofix:clean`,
  `priority:high|normal|low`, `risk:low`, `status:ready|in-progress`,
  `agents`, and `agent:codex`.

## Final topology (keep vs retire)

- **Keep.** `pr-00-gate.yml`, `maint-45-cosmetic-repair.yml`,
  the Gate summary job (inline),
  `maint-coverage-guard.yml`, health 40/41/42/44,
  agents 63/64, `agents-moderate-connector.yml`, `agents-debug-issue-event.yml`, `agents-guard.yml`, reusable 10/12/18, and
  `maint-auto-lock-deps.yml`, and `selftest-reusable-ci.yml`.
- **Retire.** `pr-14-docs-only.yml`, `health-43-ci-signature-guard.yml`, `maint-47-check-failure-tracker.yml`, `maint-47-disable-legacy-workflows.yml`, the
  removed Agents 61/62 consumer workflows, `agents-64-pr-comment-commands.yml`, `agents-70-orchestrator.yml`, `reusable-16-agents.yml`, `reusable-70-orchestrator-init.yml`, `reusable-70-orchestrator-main.yml`, `agents-74-pr-body-writer.yml`, and the legacy `selftest-*` wrappers
  superseded by `selftest-reusable-ci.yml`.
- **Retired environment provisioning.** Maint 63 was retired in December 2025
  after environment-management requests returned HTTP 403.
  [Original workflow](https://github.com/stranske/Workflows/blob/31cf87f533482e4a01937457e66a3ee62f3ec192/.github/workflows/maint-63-ensure-environments.yml) · [Final archived revision](https://github.com/stranske/Workflows/blob/0277001ab1894663ecd736faab52a8d827bd98fe/.github/workflows/archived/maint-63-ensure-environments.yml)
  [Gate](../../.github/workflows/pr-00-gate.yml) selects `agent-high-privilege`
  when it detects workflow changes and `agent-standard` otherwise.
  [Keepalive](../../.github/workflows/agents-keepalive-loop.yml) and
  [Autofix](../../.github/workflows/agents-autofix-loop.yml) also use these
  environments. Check the repository's environment settings for the current
  protection rules and required reviewers.

## How to change a workflow safely

1. Start with the [Agents Workflow Protection Policy](../AGENTS_POLICY.md) to
   confirm the change fits the allowlist and review the guardrails.
2. File or link the incident/maintenance issue describing the need for the
   change. Capture the risk assessment and expected blast radius in that issue.
3. Secure the required `agents:allow-change` label (maintainers only) before
   pushing edits to protected workflows. Health 45 Agents Guard will block the
   PR without it when protected files are in scope.
4. Keep Code Owner review enabled so workflow logic edits land only with
   explicit maintainer approval. Dependency-only action reference updates may
   satisfy Health 45 with `agents:allow-change` when authored by Dependabot,
   Renovate, or a repository owner/member/collaborator; branch protection can
   still require review.
5. After merge, remove the label, check any [formatting or repair outcome](WORKFLOWS.md#autofix-routes), and verify Agents Guard reports green.
6. Update the entry in the [workflow catalog](WORKFLOWS.md). Update this overview
   when a change affects the relationships, operator procedures or guardrails it describes.

## Verification checklist

The existing Agents Verifier caller and reusable expose a fixed `standard` or
`expanded` evidence profile for inspected input-limit recovery. Consumer callers
fingerprint that profile, and comparison input manifests retain the selected
profile and actual limits. Expanded does not weaken completeness or CI floors.

- PR checks and the default-branch ruleset both require **`summary`**.
- New pull requests list **`summary`** under **Required checks**; missing it is an
  incident that requires running the branch-protection playbook.
- The duplicate **`Gate / gate`** commit status may also appear (posted by the summary
  job); verify it is not the only configured ruleset requirement.
- On an eligible event, inspect the exact-head Health 45 result against the
  [protected-file policy](../AGENTS_POLICY.md#how-to-verify-required-checks).
- Maintainers can point to the most recent [Workflow System Overview](../ci/WORKFLOW_SYSTEM.md) update in pull-request history, demonstrating that contributors can discover the guardrails without escalation.
- Gate runs and passes on docs-only PRs; the **`summary`** job reports success and
  satisfies the ruleset requirement.
- Health 41 and Health 44 confirm the effective default-branch ruleset requires
  **`summary`** (per `.github/config/required-contexts.json`).
- Gate publishes the consolidated summary. Find formatter commits and artifacts in the [Autofix caller](WORKFLOWS.md#autofix-routes).

### Required vs informational checks on `main`

| Context | What to inspect |
| --- | --- |
| `summary` | Gate’s aggregate job. The effective Workflows main ruleset requires this context. |
| `Gate / gate` | Compatibility status posted by the Gate summary job. |
| `Health 45 Agents Guard / guard` | On an eligible event, read the protected-file policy result for the exact head. A skip or absent status gives no Guard verdict. |

#### UI reference: verifying new pull requests

Open the PR's **Checks** tab. Locate `summary` under **Required**. For a
protected-file edit, open the selected Guard job and check which rule it
evaluated. Fork status publication is a separate trusted workflow.

### How to verify required checks

Read the effective rules for `main` with `gh api repos/stranske/Workflows/rules/branches/main`.
Compare the `required_status_checks` rule with
[`required-contexts.json`](../../.github/config/required-contexts.json).
The [policy verification procedure](../AGENTS_POLICY.md#how-to-verify-required-checks)
also covers a skipped Guard evaluation and a Health 44 run without an artifact.

## Branch protection playbook

Use the [Agents Workflow Protection Policy](../AGENTS_POLICY.md#how-to-verify-required-checks)
for the operator commands and expected contexts. Preserve the single required
`summary` context when repairing the Workflows main ruleset. Read its strictness
and PR approval settings from the same effective rules. The presence of a Guard
result in the Checks tab shows that an event was evaluated.

### Recovery scenarios

- **Required check missing.** Check the effective rules and the Gate summary for
  the current PR head. Inspect Health 44’s job and any uploaded evidence using the
  [policy procedure](../AGENTS_POLICY.md#how-to-verify-required-checks).
- **Gate summary missing or stale.** Open the originating Gate run and re-run its
  failed jobs to regenerate the summary. Confirm the new attempt and head in the PR.
- **Guard status missing.** Check the event, its eligibility, and the publisher
  for the current head. Inspect the [trusted fork Guard publisher](../../.github/workflows/agents-guard-fork-status.yml) for a fork PR.

### Verifier corpus provenance

The reusable verifier publishes `verifier-corpus-decision/v1` beside comparison
reports using the exact PR head and evaluated target captured in its context.
Maint 79 joins this bot-published evidence (run/attempt and report URL included)
to current merged-PR outcomes; missing identities and clean merges with NON_PASS
decisions cannot create PASS benchmark cases. Staging-only PRs do not change
approval metrics. See `docs/MODEL_SELECTION_POLICY.md` for the evidence contract.

The harvester's own recurring PR is not input evidence. `source_context.js`
recognizes it only when the head branch is `verifier-corpus-harvest/auto`, both
repositories are `stranske/Workflows`, and the `automation` plus
`model-selection` labels are present. `agents_verifier_context.js` then exits
before CI polling or issue-acceptance collection, preventing a self-review loop
and preventing the historical design link in the PR body from becoming a
closing-issue claim.
# Fork Gate status publication

`.github/workflows/pr-00-gate-fork-status.yml` is the trusted default-branch
publisher for the duplicate `Gate / gate` commit status on fork pull requests
while the ruleset requires **`summary`**. It binds
the Gate run to the current PR head and latest run attempt, rejects changes to
the Gate control surface, and treats every non-explicit-success outcome as
blocking. The full threat model, live context audit, staged consumer rollout,
and rollback contract are in
[`docs/keepalive/FORK_GATE_STATUS_PUBLICATION.md`](../keepalive/FORK_GATE_STATUS_PUBLICATION.md).


### Maint46 issue and snapshot lifecycle

The summary-recovery early exit does not gate the independent `failure-tracker`
job. That job owns `issues: write`, executes trusted base helpers, validates the
monitored Gate run/attempt/current PR head and paginated job evidence, then
tracks failure or recovery and uploads `artifacts/ci_failures_snapshot.json`.
The [tracker contract](../ci-failure-tracker.md) documents replay and receipt limits.
