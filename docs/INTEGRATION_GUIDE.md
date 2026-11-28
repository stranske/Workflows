# Integration Guide: Using Workflows in Your Repository

This guide explains how to integrate the stranske/Workflows workflow library into your Python project.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Integration Methods](#integration-methods)
3. [Reusable Workflows](#reusable-workflows)
4. [Template Workflows](#template-workflows)
5. [Required Setup](#required-setup)
6. [Common Patterns](#common-patterns)
7. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Minimal Setup (5 minutes)

1. **Create `.github/workflows/ci.yml`** in your repo:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    with:
      python-version: '3.14'
```

2. **Commit and push** - CI will run on your next PR!

---

## Versioning Strategy

**`@main` is the single supported pin.** Reference every reusable workflow at
`@main`:

| Reference | When to use it | Behavior |
|-----------|----------------|----------|
| **Default branch (`@main`)** | The supported pin for all consumers. | Tracks the latest reusable workflow behavior used by the synced consumer templates. |
| **Pinned commit SHA** | Only for a one-off reproducible build or a controlled rollout you manage yourself. | Pins the reusable workflow definition. Standard consumers omit `workflows_ref`, so their helpers still come from `main`. Use `@main` for ongoing consumer configurations. |

> **No floating version tags for consumers.** The repository previously guided
> consumers to a floating `v1` tag, and [`maint-60-release.yml`](../.github/workflows/maint-60-release.yml)
> still updates the legacy `v1` tag on `v1.*` releases for historical compatibility,
> but `@v1` is **not** a supported consumer pin — it never delivered isolation from
> `main`. Do not pin reusable workflows at the `v1` tag or any other tag; use `@main`.
>
> **Why `@main` is the supported consumer pin.** Inside
> `reusable-10-ci-python.yml`, helper-code checkouts use
> `inputs.workflows_ref || 'main'`. Standard callers omit `workflows_ref`, so an
> `@main` caller uses helpers from `main`. Maint 62 explicitly passes
> `github.sha` for its local same-commit integration check; that internal test
> arrangement does not make arbitrary SHA pins supported for consumers.

Example (the supported pattern):

```yaml
jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    with:
      python-version: '3.14'
```

---

## Integration Methods

### Method 1: Reusable Workflows (Recommended)

Call workflows directly from this library. Changes propagate automatically.

```yaml
jobs:
  python-ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    with:
      python-version: '3.14'
    secrets: inherit
```

**Pros:**
- Always up-to-date
- No maintenance needed
- Consistent across repos

**Cons:**
- Less customizable
- Depends on external repo

### Method 2: Template Workflows

Copy templates from `/templates/` and customize for your project.

```bash
# Copy template to your repo
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/ci-basic.yml \
  -o .github/workflows/ci.yml
```

**Pros:**
- Full control
- The standalone Python templates define their jobs locally. The Node starter calls the shared Node workflow at `@main`.
- Easy customization

**Cons:**
- Manual updates needed
- Can drift from best practices

For the cosmetic repair workflow, follow the
[standalone maintenance copy instructions](../templates/README.md#standalone-maintenance-copies).
Your repository owns and updates its copy. See the
[dependency lock preview](../templates/README.md#dependency-lock-preview) for
the managed refresh route, local command, and archived workflow.

For files selected by the [consumer sync manifest](../.github/sync-manifest.yml),
registered first-party consumers use managed delivery. Maint 68
coalesces copied-file changes into stable candidate/delivery PRs, and Maint 71
is the sole merger of those sync PRs. Maint 68 fails before publishing any
generated head whose API-created tree or signature does not match the staged
delivery.

The review path is selected by `generated_delivery_review` in
[`config/consumer_sync_review_policy.json`](../config/consumer_sync_review_policy.json).
The active value is `integration-only`: Maint 71 proceeds to consumer CI and Gate
checks without requesting another general review or waiting through a synthetic
review interval, and records `integration_checks_required` instead of a reviewer
PASS. It merges only after an exact-head seal, required CI and a fresh Gate, a valid
GitHub-generated commit signature, and an explicit owner disposition for every active
review finding, with the merge bound to the exact head, source, and plan.
Generated-branch Gate completions wake Maint 71 immediately; the durable campaign
queue supplies the timed fallback for pending checks. Complete exact-plan candidate
evidence starts promotion automatically while the stable candidate PRs remain open.
Promotion prepares the non-canary stable PRs; Maint 71 merges candidate and delivery
heads only after one fleet-wide exact-head authorization. Active review findings
remain held until resolved, dispositioned by the owner, or covered by an
authenticated exact-head Workflows source-fix proof.

The legacy reviewer-settlement path applies only when `generated_delivery_review`
is absent. In that mode Maint 71 additionally waits for bounded reviewer settlement:
it requires one substantive response when available and never waits for all
configured reviewers, so a reviewer capacity outage cannot keep the PR open
indefinitely. A successful status whose own description says the review was
skipped or not performed is recorded as unavailable, not as reviewer quorum.

### Method 3: Hybrid Approach

Use reusable workflows for standard CI, templates for custom needs.

```yaml
jobs:
  # Standard CI via reusable workflow
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main

  # Custom job specific to your project
  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./run-integration-tests.sh
```

---

## Reusable Workflows

### CI Workflows

| Workflow | Purpose | Inputs |
|----------|---------|--------|
| `reusable-10-ci-python.yml` | Full Python CI pipeline | `python-version`, `python-versions`, `coverage-min`, `enable-soft-gate`, `lint`, `typecheck` (see `docs/USAGE.md`) |
| `reusable-11-ci-node.yml` | Node.js / TypeScript CI pipeline | `node-version`, `node-versions`, `package-manager`, `lint`, `format_check`, `typecheck`, `tests`, `test-runner`, `coverage` |
| `reusable-12-ci-docker.yml` | Container build and smoke test | `debug-build` |
| `reusable-13-cross-repo-smoke.yml` | Host + pinned dependency smoke test | `dependency_repo`, `dependency_ref`, `setup_node`, `node_version`, `host_install_command`, `dependency_install_command`, `run_command` |

## Workflow Outputs

Caller-facing outputs are available only from a subset of reusable workflows. The quick index below highlights the most common `workflow_call` outputs and artifact-only reusable workflows; consult the exhaustive catalog before assuming an unlisted workflow has no caller-facing outputs.

All registry-backed agent runners expose the optional provider-neutral
capability evidence outputs `capability-id`, `effect-fingerprint`,
`evidence-artifact-ref`, `supervision-mode`,
`capability-evidence-status`, and `terminal-disposition`. They are empty by
default and are accepted only as one complete validated record; callers must
not derive them from free-form agent output.

The exhaustive output reference is [`docs/ci/WORKFLOW_OUTPUTS.md`](ci/WORKFLOW_OUTPUTS.md). It documents each exported `workflow_call` output with its type, description, and usage expression, and it also lists reusable workflows that intentionally publish artifacts or logs without job outputs. Use that page as the source of truth when wiring dependent jobs; the table below is a quick index for the most common chaining surfaces.

Coverage evidence: `tests/workflows/test_reusable_workflow_outputs_doc.py` loads every `.github/workflows/reusable-*.yml` declaration, compares each `on.workflow_call.outputs` key and description against the catalog table, and verifies reusable workflows with no caller-facing outputs appear in the no-output list. That test is the audit guard for the acceptance requirement that all reusable workflow outputs are documented.

| Workflow | Outputs (name → description) |
|----------|-----------------------------|
| `reusable-10-ci-python.yml` | None (artifacts only: coverage, metrics, summaries). |
| `reusable-11-ci-node.yml` | None (artifacts only: coverage + junit when enabled). |
| `reusable-12-ci-docker.yml` | None (logs only). |
| `reusable-13-cross-repo-smoke.yml` | None (logs only). |
| `reusable-18-autofix.yml` | None (patch artifacts + summaries). |
| `reusable-agents-issue-bridge.yml` | None (bridge PR creation artifacts/logs). |

### Reusable workflow output audit

This guide now carries the issue #10 acceptance evidence directly. The audit covers every reusable workflow declaration under `.github/workflows/reusable-*.yml`; update the exhaustive catalog in [`docs/ci/WORKFLOW_OUTPUTS.md`](ci/WORKFLOW_OUTPUTS.md) first, then mirror changed rows here when adding, renaming, or removing a reusable workflow output.

Reusable workflows with caller-facing `workflow_call` outputs:

| Workflow | Output | Type | Description | Example |
| --- | --- | --- | --- | --- |
| `reusable-bot-comment-handler.yml` | `comments_found` | string (boolean-like) | Whether unresolved bot comments were found. | `needs.bot-comments.outputs.comments_found` |
| `reusable-bot-comment-handler.yml` | `comments_count` | string (number-like) | Number of unresolved bot comments found. | `needs.bot-comments.outputs.comments_count` |
| `reusable-bot-comment-handler.yml` | `agent_triggered` | string (boolean-like) | Whether the agent was triggered to address comments. | `needs.bot-comments.outputs.agent_triggered` |
| `reusable-bot-comment-handler.yml` | `app_auth_mode` | string enum | Selected App auth mode: client-id, legacy-app-id, or none. | `needs.bot-comments.outputs.app_auth_mode` |
| `reusable-backplane-conformance.yml` | `conformant` | string (boolean-like) | true if the envelope conformed (or repo is not a participant). | `needs.conformance.outputs.conformant` |
| `reusable-pr-context.yml` | `pr_number` | string (number-like) | PR number. | `needs.pr-context.outputs.pr_number` |
| `reusable-pr-context.yml` | `pr_title` | string | PR title. | `needs.pr-context.outputs.pr_title` |
| `reusable-pr-context.yml` | `pr_body` | string | PR body, possibly truncated for very long bodies. | `needs.pr-context.outputs.pr_body` |
| `reusable-pr-context.yml` | `pr_state` | string | PR state: OPEN, CLOSED, or MERGED. | `needs.pr-context.outputs.pr_state` |
| `reusable-pr-context.yml` | `pr_is_draft` | string (boolean-like) | Whether the PR is a draft. | `needs.pr-context.outputs.pr_is_draft` |
| `reusable-pr-context.yml` | `pr_merged` | string (boolean-like) | Whether the PR is merged. | `needs.pr-context.outputs.pr_merged` |
| `reusable-pr-context.yml` | `pr_author` | string | PR author login. | `needs.pr-context.outputs.pr_author` |
| `reusable-pr-context.yml` | `head_ref` | string | Head branch name. | `needs.pr-context.outputs.head_ref` |
| `reusable-pr-context.yml` | `base_ref` | string | Base branch name. | `needs.pr-context.outputs.base_ref` |
| `reusable-pr-context.yml` | `head_sha` | string | Head commit SHA. | `needs.pr-context.outputs.head_sha` |
| `reusable-pr-context.yml` | `labels_json` | string (JSON array) | JSON array of label names. | `needs.pr-context.outputs.labels_json` |
| `reusable-pr-context.yml` | `has_agent_label` | string (boolean-like) | Whether the PR has any `agent:*` label. | `needs.pr-context.outputs.has_agent_label` |
| `reusable-pr-context.yml` | `has_keepalive_label` | string (boolean-like) | Whether the PR has the `agents:keepalive` label. | `needs.pr-context.outputs.has_keepalive_label` |
| `reusable-pr-context.yml` | `files_count` | string (number-like) | Number of changed files. | `needs.pr-context.outputs.files_count` |
| `reusable-pr-context.yml` | `files_json` | string (JSON array) | JSON array of changed file paths. | `needs.pr-context.outputs.files_json` |
| `reusable-pr-context.yml` | `has_src_changes` | string (boolean-like) | Whether changes include source files. | `needs.pr-context.outputs.has_src_changes` |
| `reusable-pr-context.yml` | `has_test_changes` | string (boolean-like) | Whether changes include test files. | `needs.pr-context.outputs.has_test_changes` |
| `reusable-pr-context.yml` | `has_workflow_changes` | string (boolean-like) | Whether changes include `.github/workflows/`. | `needs.pr-context.outputs.has_workflow_changes` |
| `reusable-pr-context.yml` | `ci_status` | string | Overall CI status, such as SUCCESS, FAILURE, or PENDING. | `needs.pr-context.outputs.ci_status` |
| `reusable-pr-context.yml` | `checks_json` | string (JSON array) | JSON array of check results. | `needs.pr-context.outputs.checks_json` |
| `reusable-pr-context.yml` | `full_context_json` | string (JSON) | Full PR context as JSON; use sparingly because it can be large. | `needs.pr-context.outputs.full_context_json` |
| `reusable-codex-run.yml` | `final-message` | string (base64) | Full Codex output message, base64 encoded. | `needs.codex.outputs.final-message` |
| `reusable-codex-run.yml` | `final-message-summary` | string | First 500 characters of Codex output, safe for PR comments. | `needs.codex.outputs.final-message-summary` |
| `reusable-codex-run.yml` | `e2e-ping-reply-matched` | string (boolean-like) | Whether the raw Codex reply matches the expected ping in e2e-test mode | `needs.codex.outputs.e2e-ping-reply-matched` |
| `reusable-codex-run.yml` | `error-summary` | string | Failure summary message from Codex output or preflight errors. | `needs.codex.outputs.error-summary` |
| `reusable-codex-run.yml` | `exit-code` | string (number-like) | Codex CLI exit code. | `needs.codex.outputs.exit-code` |
| `reusable-codex-run.yml` | `requested-model` | string | Model the runner asked the Codex CLI for (empty when unpinned). | `needs.codex.outputs.requested-model` |
| `reusable-codex-run.yml` | `reported-model` | string | Model the Codex CLI recorded it ran on (empty when undeterminable). | `needs.codex.outputs.reported-model` |
| `reusable-codex-run.yml` | `changes-made` | string (boolean-like) | Whether Codex made file changes. | `needs.codex.outputs.changes-made` |
| `reusable-codex-run.yml` | `commit-sha` | string | SHA of the commit if changes were pushed. | `needs.codex.outputs.commit-sha` |
| `reusable-codex-run.yml` | `files-changed` | string (number-like) | Number of files changed by Codex. | `needs.codex.outputs.files-changed` |
| `reusable-codex-run.yml` | `agent-execution-started` | string (boolean-like) | Whether the Run Codex step started. | `needs.codex.outputs.agent-execution-started` |
| `reusable-codex-run.yml` | `capability-id` | string | Validated existing capability identifier; empty when evidence is absent. | `needs.codex.outputs.capability-id` |
| `reusable-codex-run.yml` | `effect-fingerprint` | string | Validated lowercase sha256 fingerprint of the bounded effect. | `needs.codex.outputs.effect-fingerprint` |
| `reusable-codex-run.yml` | `evidence-artifact-ref` | string | Validated durable logical reference to supporting evidence. | `needs.codex.outputs.evidence-artifact-ref` |
| `reusable-codex-run.yml` | `supervision-mode` | string enum | Validated supervision mode for this result. | `needs.codex.outputs.supervision-mode` |
| `reusable-codex-run.yml` | `capability-evidence-status` | string enum | Validated capability evidence status. | `needs.codex.outputs.capability-evidence-status` |
| `reusable-codex-run.yml` | `terminal-disposition` | string enum | Validated terminal disposition for the result. | `needs.codex.outputs.terminal-disposition` |
| `reusable-codex-run.yml` | `worker-profile-id` | string | Registry execution profile ID supplied by caller. | `needs.codex.outputs.worker-profile-id` |
| `reusable-codex-run.yml` | `worker-requested-model` | string | Model requested through the registry execution profile. | `needs.codex.outputs.worker-requested-model` |
| `reusable-codex-run.yml` | `worker-selected-model` | string | Actual Codex model selected after runner fallback. | `needs.codex.outputs.worker-selected-model` |
| `reusable-codex-run.yml` | `worker-reasoning-effort` | string | Reasoning effort supplied by the registry execution profile. | `needs.codex.outputs.worker-reasoning-effort` |
| `reusable-codex-run.yml` | `worker-model-selection-reason` | string | Reason for the selected worker model. | `needs.codex.outputs.worker-model-selection-reason` |
| `reusable-codex-run.yml` | `error-category` | string | Error category if failure occurred. | `needs.codex.outputs.error-category` |
| `reusable-codex-run.yml` | `error-type` | string | Error type if failure occurred. | `needs.codex.outputs.error-type` |
| `reusable-codex-run.yml` | `error-recovery` | string | Suggested recovery action if failure occurred. | `needs.codex.outputs.error-recovery` |
| `reusable-codex-run.yml` | `watchdog-saved` | string (boolean-like) | Whether the pre-timeout watchdog saved uncommitted work. | `needs.codex.outputs.watchdog-saved` |
| `reusable-codex-run.yml` | `llm-analysis-run` | string (boolean-like) | Whether LLM analysis was performed. | `needs.codex.outputs.llm-analysis-run` |
| `reusable-codex-run.yml` | `llm-provider` | string | LLM provider used for analysis. | `needs.codex.outputs.llm-provider` |
| `reusable-codex-run.yml` | `llm-model` | string | Specific model used for analysis. | `needs.codex.outputs.llm-model` |
| `reusable-codex-run.yml` | `llm-confidence` | string (number-like) | Confidence level of LLM analysis. | `needs.codex.outputs.llm-confidence` |
| `reusable-codex-run.yml` | `llm-completed-tasks` | string (JSON) | JSON array of completed task descriptions. | `needs.codex.outputs.llm-completed-tasks` |
| `reusable-codex-run.yml` | `llm-has-completions` | string (boolean-like) | Whether any task completions were detected. | `needs.codex.outputs.llm-has-completions` |
| `reusable-codex-run.yml` | `llm-raw-confidence` | string (number-like) | Raw confidence before BS detection adjustment. | `needs.codex.outputs.llm-raw-confidence` |
| `reusable-codex-run.yml` | `llm-effort-score` | string (number-like) | Estimated effort score based on session activity. | `needs.codex.outputs.llm-effort-score` |
| `reusable-codex-run.yml` | `llm-data-quality` | string | Session data quality level. | `needs.codex.outputs.llm-data-quality` |
| `reusable-codex-run.yml` | `llm-analysis-text-length` | string (number-like) | Length of analysis text sent to LLM. | `needs.codex.outputs.llm-analysis-text-length` |
| `reusable-codex-run.yml` | `llm-quality-warnings` | string (JSON) | JSON array of quality warnings from the BS detector. | `needs.codex.outputs.llm-quality-warnings` |
| `reusable-claude-run.yml` | `final-message` | string (base64) | Full Claude output message, base64 encoded. | `needs.claude.outputs.final-message` |
| `reusable-claude-run.yml` | `final-message-summary` | string | First 500 characters of Claude output, safe for PR comments. | `needs.claude.outputs.final-message-summary` |
| `reusable-claude-run.yml` | `error-summary` | string | Failure summary message from Claude output or preflight errors. | `needs.claude.outputs.error-summary` |
| `reusable-claude-run.yml` | `exit-code` | string (number-like) | Claude CLI exit code. | `needs.claude.outputs.exit-code` |
| `reusable-claude-run.yml` | `requested-model` | string | Model the runner asked the Claude CLI for (empty when unpinned). | `needs.claude.outputs.requested-model` |
| `reusable-claude-run.yml` | `reported-model` | string | Model the Claude CLI recorded it ran on (empty when undeterminable). | `needs.claude.outputs.reported-model` |
| `reusable-claude-run.yml` | `changes-made` | string (boolean-like) | Whether Claude made file changes. | `needs.claude.outputs.changes-made` |
| `reusable-claude-run.yml` | `commit-sha` | string | SHA of the commit if changes were pushed. | `needs.claude.outputs.commit-sha` |
| `reusable-claude-run.yml` | `files-changed` | string (number-like) | Number of files changed by Claude. | `needs.claude.outputs.files-changed` |
| `reusable-claude-run.yml` | `agent-execution-started` | string (boolean-like) | Whether the Run Claude step started. | `needs.claude.outputs.agent-execution-started` |
| `reusable-claude-run.yml` | `capability-id` | string | Validated existing capability identifier; empty when evidence is absent. | `needs.claude.outputs.capability-id` |
| `reusable-claude-run.yml` | `effect-fingerprint` | string | Validated lowercase sha256 fingerprint of the bounded effect. | `needs.claude.outputs.effect-fingerprint` |
| `reusable-claude-run.yml` | `evidence-artifact-ref` | string | Validated durable logical reference to supporting evidence. | `needs.claude.outputs.evidence-artifact-ref` |
| `reusable-claude-run.yml` | `supervision-mode` | string enum | Validated supervision mode for this result. | `needs.claude.outputs.supervision-mode` |
| `reusable-claude-run.yml` | `capability-evidence-status` | string enum | Validated capability evidence status. | `needs.claude.outputs.capability-evidence-status` |
| `reusable-claude-run.yml` | `terminal-disposition` | string enum | Validated terminal disposition for the result. | `needs.claude.outputs.terminal-disposition` |
| `reusable-claude-run.yml` | `llm-analysis-run` | string (boolean-like) | Whether LLM analysis was performed. | `needs.claude.outputs.llm-analysis-run` |
| `reusable-claude-run.yml` | `llm-provider` | string | LLM provider used for analysis. | `needs.claude.outputs.llm-provider` |
| `reusable-claude-run.yml` | `llm-model` | string | Specific model used for analysis. | `needs.claude.outputs.llm-model` |
| `reusable-claude-run.yml` | `llm-confidence` | string (number-like) | Confidence level of LLM analysis. | `needs.claude.outputs.llm-confidence` |
| `reusable-claude-run.yml` | `llm-completed-tasks` | string (JSON) | JSON array of completed task descriptions. | `needs.claude.outputs.llm-completed-tasks` |
| `reusable-claude-run.yml` | `llm-has-completions` | string (boolean-like) | Whether any task completions were detected. | `needs.claude.outputs.llm-has-completions` |
| `reusable-claude-run.yml` | `error-category` | string | Error category if failure occurred. | `needs.claude.outputs.error-category` |
| `reusable-claude-run.yml` | `error-type` | string | Error type if failure occurred. | `needs.claude.outputs.error-type` |
| `reusable-claude-run.yml` | `error-recovery` | string | Suggested recovery action if failure occurred. | `needs.claude.outputs.error-recovery` |
| `reusable-cursor-run.yml` | `final-message` .. `error-recovery` (24 outputs) | string / enum | Same standard runner, capability-evidence, LLM-analysis, and error outputs as `reusable-claude-run.yml` (without `reported-model`); see [`docs/ci/WORKFLOW_OUTPUTS.md`](ci/WORKFLOW_OUTPUTS.md) for the full per-key table. | `needs.cursor.outputs.final-message-summary` |
| `reusable-muse-run.yml` | `final-message` .. `duration-seconds` (25 outputs) | string / enum | Same standard runner, capability-evidence, LLM-analysis, and error outputs as `reusable-cursor-run.yml` plus `duration-seconds`; see [`docs/ci/WORKFLOW_OUTPUTS.md`](ci/WORKFLOW_OUTPUTS.md). | `needs.muse.outputs.duration-seconds` |
| `reusable-gemini-run.yml` | `final-message` .. `error-recovery` (24 outputs) | string / enum | Same standard runner, capability-evidence, LLM-analysis, and error outputs as `reusable-cursor-run.yml`; see [`docs/ci/WORKFLOW_OUTPUTS.md`](ci/WORKFLOW_OUTPUTS.md). | `needs.gemini.outputs.final-message-summary` |
| `reusable-agents-verifier.yml` | `verdict` | string | Trusted verifier verdict for caller-owned source closure. | `needs.verifier.outputs.verdict` |
| `reusable-agents-verifier.yml` | `target_sha` | string | Trusted verifier target_sha for caller-owned source closure. | `needs.verifier.outputs.target_sha` |
| `reusable-agents-verifier.yml` | `pr_number` | string | Trusted verifier pr_number for caller-owned source closure. | `needs.verifier.outputs.pr_number` |
| `reusable-agents-verifier.yml` | `event_complete` | string | An authenticated production event terminal was posted. | `needs.verifier.outputs.event_complete` |
| `reusable-agents-verifier.yml` | `should_run` | string | Trusted verifier should_run for caller-owned source closure. | `needs.verifier.outputs.should_run` |
| `reusable-agents-verifier.yml` | `workflows_ref` | string | Trusted verifier workflows_ref for caller-owned source closure. | `needs.verifier.outputs.workflows_ref` |

Reusable workflows without `workflow_call` outputs:

| Workflow | Caller-facing output status |
| --- | --- |
| `reusable-10-ci-python.yml` | No `workflow_call` outputs; publishes coverage, metrics, logs, and summaries as artifacts/job output. |
| `reusable-11-ci-node.yml` | No `workflow_call` outputs; publishes coverage and JUnit artifacts when enabled. |
| `reusable-12-ci-docker.yml` | No `workflow_call` outputs; logs Docker smoke results. |
| `reusable-13-cross-repo-smoke.yml` | No `workflow_call` outputs; logs cross-repo smoke command output. |
| `reusable-18-autofix.yml` | No `workflow_call` outputs; publishes patch artifacts and summaries. |
| `reusable-19-dependency-repair-contract.yml` | No `workflow_call` outputs; logs dependency-repair provenance validation results. |
| `reusable-20-pr-meta.yml` | No `workflow_call` outputs; updates PR body sections. |
| `reusable-agents-issue-bridge.yml` | No `workflow_call` outputs; creates bridge PR artifacts and logs. |
| `reusable-agents-pr-health.yml` | No `workflow_call` outputs; reports health through checks and summaries. |
| `reusable-model-profile-trial.yml` | No `workflow_call` outputs; publishes strict v2 quarantine telemetry artifacts. |

### Using outputs in dependent jobs

The examples below show output-consumption patterns for registry-backed agent runners.

### Agent Workflows

| Workflow | Purpose | Optional Secrets |
|----------|---------|------------------|
| `reusable-agents-issue-bridge.yml` | Convert issues to PRs via agents | `service_bot_pat`, `owner_pr_pat`, `workflows_app_id`, `workflows_app_private_key` |

### Example: Full CI

```yaml
name: CI

on: [push, pull_request]

jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    with:
      python-version: '3.14'
      lint: true
      typecheck: true
      coverage-min: '70'
    secrets:
      pypi-token: ${{ secrets.PYPI_TOKEN }}  # Optional, for publishing
```

---

## Template Workflows

Copy from `/templates/` and customize:

| Template | Use Case |
|----------|----------|
| `ci-basic.yml` | Simple projects: lint + test |
| `ci-full.yml` | Production projects: full pipeline with gate |
| [ci-node-basic.yml](../templates/ci-node-basic.yml) | Run shared Node.js and TypeScript CI with npm and Jest by default |
| [cosmetic-repair.yml](../templates/cosmetic-repair.yml) | Auto-fix formatting issues |

> **Consuming a `packages/` monorepo dependency (e.g. `app-baseline-kit`)?**
> Exclude it from `requirements.lock` with `[tool.uv.pip] no-emit-package` so a
> frozen SHA in the lock cannot conflict with the unpinned `@main` URL when
> Workflows `main` advances. See
> [Monorepo Package Dependencies](ops/CONSUMER_REPO_MAINTENANCE.md#monorepo-package-dependencies-app-baseline-kit),
> and [Declaring the `app-baseline-kit` Dependency](guides/BASELINE_KIT_DEPENDENCY.md)
> for the catalog of accepted patterns and how to choose one.

### Customization Checklist

After copying a template:

- [ ] Replace `YOUR_PACKAGE_NAME` with your package
- [ ] Update test paths (`tests/`)
- [ ] Update source paths (`src/`)
- [ ] Set Python version(s)
- [ ] Configure coverage threshold
- [ ] Add required secrets

---

## Required Setup

### Repository Secrets

Set these in your repo's Settings → Secrets → Actions:

| Secret | When Needed | How to Create |
|--------|-------------|---------------|
| `GITHUB_TOKEN` | Always | Automatic |
| `SERVICE_BOT_PAT` | Agent workflows | Create PAT with `repo` scope |
| `OWNER_PR_PAT` | Agent PR creation and workflow-file source proposals | Create classic PAT with `repo` and `workflow` scopes |
| `PYPI_TOKEN` | Publishing packages | From pypi.org |

> **This table is a starting point, not the full set.** A first-party consumer
> actually carries ~20 secrets (App IDs and private keys for the Workflows,
> keepalive and bot-comment Apps; agent CLI credentials; provider API keys).
> `templates/consumer-repo/docs/SETUP_CHECKLIST.md` §3.2 is the authoritative list.
> Corrected 2026-08-21: onboarding `stranske/Orchestrator` against this table alone
> produced a repo with 4 of the then-15 secrets and no indication anything was missing.

### Branch Protection

For the gate pattern to work:

1. Go to Settings → Branches → Add rule
2. Set branch pattern: `main`
3. Enable "Require status checks"
4. Add the required check: `summary` (for the standard `pr-00-gate.yml` Gate template, or `CI Gate` if using the standalone `ci-full.yml` template)


### Workflow Permissions

**Critical for reusable workflows:** The repository must have write permissions enabled.

1. Go to Settings → Actions → General
2. Scroll to "Workflow permissions"
3. Select **"Read and write permissions"**
4. Check **"Allow GitHub Actions to create and approve pull requests"**
5. Click Save

Without these settings, workflows calling reusable workflows from this repo will fail
with `startup_failure` status and no useful error message.

**Via API (for automation):**
```bash
gh api repos/OWNER/REPO/actions/permissions/workflow -X PUT --input - << 'EOF'
{"default_workflow_permissions": "write", "can_approve_pull_request_reviews": true}
EOF
```

### Consumer Repo Setup: Required Scripts

Reusable Python CI loads its dependency checker and mypy version resolver from
the consumer checkout. Follow the [consumer script installation instructions](../templates/consumer-repo/README.md#required-scripts-for-consumer-repos)
to copy both files into their expected locations. To check the installation,
run these commands from the consumer repository root.

```sh
python scripts/sync_test_dependencies.py --verify
python tools/resolve_mypy_pin.py
```

The first command reports undeclared test dependencies. The second prints the
Python version selected for mypy.

### Consumer Repo Setup: .gitignore Entries

**Critical for keepalive/codex workflows:** Add these entries to your `.gitignore`
to prevent merge conflicts when multiple PRs run concurrently:

```gitignore
# Codex working files (preserved via workflow artifacts, not git)
# CRITICAL: These must be gitignored to prevent merge conflicts when
# multiple PRs run keepalive simultaneously. Each run rebuilds these files.
# Generic names (legacy)
codex-prompt.md
codex-output.md
# PR-specific names (used by reusable-codex-run.yml to avoid conflicts)
codex-prompt-*.md
codex-output-*.md
verifier-context.md
```

**Why this matters:** When multiple PRs run keepalive concurrently, each workflow
generates these working files. The workflow uses PR-specific filenames (e.g.,
`codex-output-123.md`) and explicitly excludes them from commits, but the
`.gitignore` provides defense-in-depth. Historical data is preserved in:
- PR comments (completion summaries)
- Workflow artifacts (full outputs)
- Commit messages (change descriptions)

Post-merge verification loads a bounded evidence record from the selected PR.
It inspects only that PR's comments and workflow runs explicitly referenced by
the PR body, linked issue bodies, or those bounded comments. Comment count and
rendered characters, referenced runs, artifact count and archive size, text
entries, and rendered artifact characters all have finite limits. The context
reports each source as `present`, `absent`, or `unavailable`: a complete empty
lookup is `absent`, while API failure, unreadable content, or any limit that
prevents complete inspection is `unavailable`. An unavailable source can never
be used to claim that a required transcript is absent or to justify PASS for an
otherwise unverifiable required deliverable. Artifact archives are read without
extracting paths into the checkout, and only allowlisted text entry types are
included as untrusted evidence rather than instructions. Directory records are
harmless archive structure, but any non-directory payload entry excluded by the
allowlist makes the artifact evidence unavailable even if other text was read.
Evaluate/compare accept only a complete Git patch as code: a diff summary,
garbled `--diff-file`, malformed quoted path, or budget-truncated patch floors
the verdict at CONCERNS rather than treating zero parsed files as no change.
Binary-only descriptors (`Binary files ... differ` or `GIT binary patch`) are
omitted code coverage, not inspectable contents. Evidence-delivery requirements
such as "Include an artifact" remain required; mentioning an API/UI change
before a delivery instruction does not turn that instruction into product behavior.
Artifacts included in a product response or payload are not workflow evidence,
regardless of the actor's name; explicit PR delivery remains required.
The same rule applies to transcript/command-output fields in response contracts;
an additional required PR-comment delivery in the clause is preserved.
Declarative return/display/render/emit/expose behavior is identified without a
product-actor name list; explicit reviewer/author obligations and imperative
evidence requests remain requirements. Artifact/output/transcript pronouns can
refer to objects in the same acceptance item, including plural object groups,
in either active or passive delivery wording,
but never inherit objects from another checklist item. Optional or prohibited
delivery remains local to its clause, and artifact plus output delivery retains
both retrieval channels rather than downgrading the artifact to generic evidence.
Response-field operations include `provide`; an API response providing output
does not imply a review deliverable, while a separate PR-delivery clause and
explicit author obligation remain evidence requirements.
Product auxiliary wording is shared across response grouping and filtering,
artifact behavior and output predicates: `must`, `is required to`, `is needed
to`, and equivalent deontic forms do not change a product field into evidence.
An explicitly required workflow-run link is an evidence deliverable; only a
standalone workflow status/success criterion is exempt from evidence retrieval.
An unavailable required link prevents a coverage PASS.
Workflow-run antecedents also survive separate active/passive PR-link clauses;
qualified status forms such as passing on Linux or finishing successfully stay
exempt when they do not separately require link delivery.
Cross-repository full-diff recovery fetches and verifies both the recorded base
and PR head from the target repository before reconstructing the range.
Git's tab delimiter in `---`/`+++` metadata is not part of the changed pathname.
Diff summaries preserve literal ` b/` path components instead of choosing the
last header delimiter. Ambiguous rename/copy headers require authoritative
pre-hunk path metadata; unresolved or malformed paths fail closed.
Acceptance and evidence section scanners share fence-closing validation: a
marker with trailing non-space/tab content cannot expose literal headings.
Root fences cannot close at four spaces, while indented source snippets retain
their opening indentation so literal examples remain inert.

### Consumer Repo Setup: Coverage Soft Gate

Enable coverage tracking with automatic issue creation when coverage drops:

**1. Enable soft-gate in your Gate workflow:**

```yaml
jobs:
  python-ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    with:
      coverage-min: "80"           # Minimum threshold
      enable-soft-gate: true       # Enable trend tracking & hotspot reporting
      artifact-prefix: "gate-"     # Required for coverage guard
```

**2. Create a coverage baseline file (`config/coverage-baseline.json`):**

```json
{
  "line": 80.0,
  "warn_drop": 1.0,
  "recovery_days": 3,
  "updated": "2025-12-30",
  "notes": "Initial baseline - adjust based on project maturity"
}
```

**3. Add the coverage guard workflow (`.github/workflows/maint-coverage-guard.yml`):**

Copy from `templates/consumer-repo/.github/workflows/maint-coverage-guard.yml`

**What you get:**

| Feature | Description |
|---------|-------------|
| **Coverage Summary** | Table in workflow run summary showing current vs baseline |
| **Hotspot Report** | List of files with lowest coverage (candidates for new tests) |
| **Low Coverage Alert** | Files below 50% threshold highlighted separately |
| **Baseline Issue** | Auto-created/updated issue when coverage drops below baseline |
| **Trend Artifacts** | `coverage-trend.json` and `coverage-trend-history.ndjson` for analysis |

**Guard tolerance and recovery:** `warn_drop` is a percentage-point allowance below
the baseline (default `1.0` if omitted). A run creates or updates a breach issue only
when `current < baseline - warn_drop`; a smaller drop is an intentional no-op. An open
breach issue closes only after coverage reaches `baseline - warn_drop` for the
configured `recovery_days` consecutive samples (default `3`). The warning allowance
changes the recovery threshold, not the default confirmation window.

The guard restores repository-scoped recovery history, appends the current producer
run (replacing a repeated run identity), and retains the configured recovery window
(at least 30 records). It saves a
new immutable cache after each guard run; a repository restore prefix carries the
records across different Gate producers. An incomplete recovery reports how many
of the required records meet the threshold. Dry runs do not persist history.

**Soft vs Hard Gate:**

- **Soft gate** (`enable-soft-gate: true`): Reports coverage but doesn't fail the build
- **Hard gate** (`coverage-min: "80"`): Fails build if coverage below threshold

Use both together for maximum visibility: soft gate shows trends while hard gate
enforces the minimum.

---

## Common Patterns

### Pattern 1: PR Gate

Use a gate job that branch protection requires:

```yaml
jobs:
  lint:
    # ...
  test:
    # ...
  
  gate:
    name: CI Gate
    needs: [lint, test]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - name: Check results
        run: |
          if [[ "${{ needs.lint.result }}" != "success" ]] || \
             [[ "${{ needs.test.result }}" != "success" ]]; then
            exit 1
          fi
```

### Pattern 2: Matrix Testing

Test across Python versions:

```yaml
jobs:
  test:
    strategy:
      matrix:
        python-version: ['3.13', '3.14']
    steps:
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
```

### Pattern 3: Conditional Jobs

Skip expensive jobs for draft PRs:

```yaml
jobs:
  full-test:
    if: github.event.pull_request.draft == false
    # ...
```

---

## Debouncing High-Frequency Workflows

Consumer repos can reduce redundant runs by adding workflow-level concurrency groups
with cancellation. Apply this to workflows that trigger on rapid push, label, or
comment activity.

Example patterns:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.run_id }}
  cancel-in-progress: true
```

```yaml
concurrency:
  group: ${{ github.workflow }}-issue-${{ github.event.issue.number }}
  cancel-in-progress: true
```

Use `github.ref` for push workflows, PR numbers for pull_request workflows, and
issue numbers for issue_comment workflows. Avoid cancellation when a workflow
must run to completion (for example, long-running migrations).

---

## Troubleshooting

### "Workflow file issue" Error

**Cause:** YAML syntax error or invalid workflow structure.

**Fix:** Validate your workflow:
```bash
# In the Workflows repo, this runs actionlint as part of the fast checks.
./scripts/dev_check.sh

# Or, if you already have actionlint installed in your environment:
actionlint .github/workflows/your-workflow.yml
```

### "Resource not accessible" Error

**Cause:** Missing permissions or secrets.

**Fix:** Add permissions block:
```yaml
permissions:
  contents: read
  pull-requests: write
```

### Reusable Workflow Not Found

**Cause:** Wrong path or ref.

**Fix:** Use full path with `@ref`:
```yaml
uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
```

### Jobs Not Running

**Cause:** `if` condition evaluating to false.

**Fix:** Check concurrency groups and conditions. For `workflow_dispatch`, ensure fallbacks:
```yaml
concurrency:
  group: ci-${{ github.event.pull_request.number || github.run_id }}
```


### Startup Failure (No Error Message)

**Cause:** Repository workflow permissions set to "Read" instead of "Read and write".

**Symptoms:**
- Workflow shows `startup_failure` status
- No error message or logs available
- Same workflow works in other repositories
- Only affects workflows calling reusable workflows

**Fix:** Update repository workflow permissions:
1. Go to Settings → Actions → General
2. Set "Workflow permissions" to **"Read and write permissions"**
3. Enable **"Allow GitHub Actions to create and approve pull requests"**

**Capture the hidden startup error (file-parse / job-graph phase):**
```bash
python scripts/workflow_startup_failure_diagnostic.py --repo OWNER/REPO --run-id RUN_ID
```

This inspects check-runs for the same head SHA/run ID and prints the parser error
title/summary text that is not visible in `actions/runs/<id>/jobs`.

The same diagnostic also recognizes `action_required` runs with zero jobs.
When the run event is a public-fork `pull_request` and `head_repository.fork`
is true, classify it as a fork contributor approval hold (REST
`/actions/runs/{id}/approve` can recover it). Otherwise treat it as GitHub's
unproven-workflow protection: review the workflow file and use **Approve and
run** from an authenticated GitHub web session; the fork-PR REST approval
endpoint does not cover that class of hold. If the event is `pull_request` but
fork status cannot be determined, report an unspecified approval hold and
inspect `event` + `head_repository` before choosing remediation.

**Find every held workflow, not just one run:**
```bash
python scripts/workflow_startup_failure_diagnostic.py --sweep --repo OWNER/REPO
```

The sweep walks every active workflow, flags those whose recent runs are
dominated by zero-job `action_required`, and prints the blocking quantity
alongside the drainable one:

```
workflow liveness: 11 held / 0 clearable by API - web approval required; oldest 22d (...)
```

`11 held` on its own reads as a backlog to work through; `11 held, 0 clearable by
API` reads as a deadlock, which is what it is. The drainable count is measured
per run rather than assumed - fork-PR holds accept the REST approval endpoint and
unproven-workflow holds do not, so `POST .../approve` answers
`403 "This run is not from a fork pull request or queued by the Actions bot"`.

Onset is found by paginating back to the last run that executed, not from the
sample page: a workflow triggered hourly discards 20 runs in under a day, so a
single page reports a three-week outage as hours old.

The sweep reports and fails. It never approves a run - auto-clearing a hold
GitHub raised on suspicion of malice would make the protection a rubber stamp.
Add `--repos a/b,c/d` to cover consumer repositories, whose synced copies of
these workflows are held independently.


### Startup Failure (Caller Workflow Permissions)

**Cause:** Caller workflow has a top-level `permissions:` block when calling a reusable workflow.

**Symptoms:**
- Same as above: `startup_failure`, no logs, zero jobs started
- The reusable workflow also specifies permissions

**Fix:** Remove the `permissions:` block from the caller workflow:
```yaml
# WRONG - causes startup_failure
permissions:
  contents: read
  pull-requests: write

jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main

# CORRECT - let the reusable workflow handle permissions
jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
```

---

## Consumer Repo Setup (Full Automation)

The synced model-selection policy is documentation for consumer operators,
not a local MAINT-78 tool install. Run its `capture`, `screen`, `confirm`, and
snapshot commands from a matching `stranske/Workflows` checkout; the
`maint-78-model-evaluation-pilot.yml` workflow and snapshot helper remain
Workflows-owned. The synced `tools/langchain_client.py` preserves an outbound
`openai/` model ID while omitting unsupported temperature for prefixed GPT-5.6
and o-series reasoning models.

For repositories that want full CI + agent automation (Codex keepalive, autofix, etc.):

### Quick Setup

Prefer the managed consumer sync workflow for registered repos. For manual
bootstrap, copy the current default entry points from `templates/consumer-repo/`
and keep the root agent guidance files aligned with the same template source:

```bash
# Current default workflow surface
mkdir -p .github/workflows
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/ci.yml -o .github/workflows/ci.yml
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/autofix-versions.env -o .github/workflows/autofix-versions.env
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/agents-issue-intake.yml -o .github/workflows/agents-issue-intake.yml
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/agents-80-pr-event-hub.yml -o .github/workflows/agents-80-pr-event-hub.yml
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml -o .github/workflows/agents-81-gate-followups.yml
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/agents-verifier.yml -o .github/workflows/agents-verifier.yml
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/autofix.yml -o .github/workflows/autofix.yml
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/pr-00-gate.yml -o .github/workflows/pr-00-gate.yml

# Install Gate's repository path policy from the same source as managed delivery.
curl -fsSL https://raw.githubusercontent.com/stranske/Workflows/main/.github/path-classification.yml -o .github/path-classification.yml

# Root agent guidance and target-environment contract synced through .github/sync-manifest.yml
mkdir -p docs
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/AGENTS.md -o AGENTS.md
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/CLAUDE.md -o CLAUDE.md
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/docs/TARGET_WORK_ENVIRONMENT.md -o docs/TARGET_WORK_ENVIRONMENT.md

# These examples track the live Workflows source via /main/, which is the
# supported pin. For a one-off reproducible bootstrap you may replace /main/
# with a commit SHA in each URL, but @main is the supported reference for
# ongoing use (there is no floating version tag).
```

### Workflow Summary

| Workflow | Purpose | Triggers |
|----------|---------|----------|
| `ci.yml` | Python CI (lint, format, tests, typecheck) | push, PR |
| `agents-issue-intake.yml` | Routes issues to registry-backed agents or runs ChatGPT topic sync | `issues` (`opened`, `reopened`, `labeled`, `unlabeled` with `agent:*`/`agents:*`), `workflow_dispatch` |
| `agents-80-pr-event-hub.yml` | Handles PR event routing, keepalive metadata, bot comments, and verification follow-ups | PR events and comments |
| `agents-81-gate-followups.yml` | Coordinates Gate follow-ups, keepalive/autofix recovery, and generated-delivery wakeups | Gate completion and follow-up events |
| `agents-verifier.yml` | Runs label-driven post-merge verification | manual dispatch, `verify:*` labels |
| `autofix.yml` | Auto-fixes lint/format issues | `workflow_run` (`Gate`/`CI`/`Python CI` completed), `pull_request_target` (`autofix` / `autofix:clean` label) |
| `pr-00-gate.yml` | Required PR gate and summary status | PR |
| `cross-repo-smoke.yml` | Optional cross-repo integration smoke (host + pinned dependency checkout) | push, PR, manual (opt-in via `CROSS_REPO_SMOKE_*` vars) |
| `autofix-versions.env` | Pins tool versions | N/A |
| `AGENTS.md` / `CLAUDE.md` / `<consumer-root>/docs/TARGET_WORK_ENVIRONMENT.md` | Agent guidance and delivery constraints synced from Workflows into the receiving repository | N/A |

### Consolidated Workflow Migration (Notice Period)

To reduce duplicate PR context fetches, consumer repos should use the consolidated
event hubs. Legacy workflow files may still exist during migrations or for
backward compatibility, but new manual setup should prefer the current defaults.

| Legacy Workflow | Replacement |
|-----------------|-------------|
| `agents-pr-meta.yml` | `agents-80-pr-event-hub.yml` |
| `agents-bot-comment-handler.yml` | `agents-80-pr-event-hub.yml` |
| `agents-verify-to-issue-v2.yml` | `agents-80-pr-event-hub.yml` |
| `agents-keepalive-loop.yml` | `agents-81-gate-followups.yml` |
| `agents-autofix-loop.yml` | `agents-81-gate-followups.yml` |

### Required Secrets

| Secret | Purpose | Required For |
|--------|---------|--------------|
| `SERVICE_BOT_PAT` | Bot account for comments/labels (stranske-automation-bot); fallback credential for cross-repository label sync | agents, autofix, Maint 69 label sync |
| `ACTIONS_BOT_PAT` | Workflow dispatch triggers | event-hub/follow-up automation (`agents-80-pr-event-hub.yml`, `agents-81-gate-followups.yml`); legacy orchestrator/pr-meta only when intentionally retained |
| `OWNER_PR_PAT` | Create PRs on behalf of user; required owner-scoped credential for generated-delivery mutations | issue-intake, Maint 69 label sync, Maint 71 sync reconciliation |
| `CROSS_REPO_TOKEN` | Read access to the dependency checkout | Cross-repo smoke with a private dependency in another repository |

### Cross-Repo Smoke (opt-in)

The [consumer caller](../templates/consumer-repo/.github/workflows/cross-repo-smoke.yml)
is installed when the file is missing. Sync preserves an existing customized caller.
The generic caller registers main pushes, PRs targeting main, and manual dispatches.
Its job skips before runner allocation unless the three variables below select it.
Pull requests whose head repository is a fork also skip.
GitHub can still require approval before it evaluates the job.

For a public dependency, the checkout uses the read-only `GITHUB_TOKEN` supplied by GitHub.
For a private dependency in another repository, configure `CROSS_REPO_TOKEN` with read access
to that repository. A configured `CROSS_REPO_TOKEN` takes precedence for either checkout.
The repository variables below control which runs select the job.

Required repository variables when enabling:

| Variable | Purpose |
|----------|---------|
| `CROSS_REPO_SMOKE_ENABLED` | Set to `true` to run the workflow |
| `CROSS_REPO_SMOKE_DEPENDENCY_REPO` | Dependency slug (`owner/repo`) |
| `CROSS_REPO_SMOKE_RUN_COMMAND` | Shell command executed from the host workspace root |

Optional repository variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `CROSS_REPO_SMOKE_DEPENDENCY_REF` | `main` | Branch, tag, or SHA for the dependency checkout |
| `CROSS_REPO_SMOKE_SETUP_NODE` | `false` | Set to `true` to run `actions/setup-node` before installs |
| `CROSS_REPO_SMOKE_NODE_VERSION` | `20` | Node.js version when setup is enabled |
| `CROSS_REPO_SMOKE_HOST_INSTALL_COMMAND` | *(empty)* | Host install command (workspace root) |
| `CROSS_REPO_SMOKE_DEPENDENCY_INSTALL_COMMAND` | *(empty)* | Dependency install command (dependency checkout path) |

For a manual installation, copy the complete [caller](../templates/consumer-repo/.github/workflows/cross-repo-smoke.yml)
to `.github/workflows/cross-repo-smoke.yml` in the receiving repository. Check for an
existing project-specific workflow at that path first.

The reusable workflow exports `DEPENDENCY_PATH` (basename of `dependency_repo`)
to the smoke command environment so scripts can reference the sibling checkout.

### Dual Checkout Architecture

Consumer repo workflows use the **dual checkout pattern**:

1. **Consumer repo** is checked out for your code
2. **Workflows repo** is checked out (sparse) for scripts

This means:
- ✅ Consumer repos still provide CI helper scripts in `scripts/` and `tools/`
- ✅ Automation scripts under `.github/scripts/` stay **up-to-date** from Workflows
- ✅ **No sync required** when Workflows scripts change
- ✅ Only **thin caller workflows** (~50-100 lines each) in your repo

### Drift Guardrails

Workflows runs a daily **Health 68 Consumer Sync Drift Check** to compare the
consumer repos against the templates/manifest. This guard excludes files marked
with `sync_mode: create_only`. The integration repo is validated separately via
Health 67.

### What Each Workflow Does

#### `agents-80-pr-event-hub.yml` (Critical for PR Events)

This is the current PR-event hub for Codex keepalive metadata, bot comments,
and verification follow-ups. When Codex completes a round of work, it posts a
comment with a keepalive marker. This workflow:

1. Detects the keepalive marker in PR comments
2. Validates the comment is from an authorized user
3. Dispatches the follow-up path that can continue work
4. Updates PR body with status sections

Without this workflow, Codex PRs will stall after the first round.

#### `agents-81-gate-followups.yml`

This is the current Gate follow-up hub. It coordinates keepalive continuation,
autofix recovery, and post-Gate actions after `pr-00-gate.yml` completes. A Gate
completion on a stable consumer-sync or dev-tool-sync branch also dispatches the
matching central Maint 71 lane; it never merges the generated PR locally.

#### `autofix.yml`

When a PR has lint/format issues:

1. Autofix runs Black and Ruff with `--fix`
2. Commits fixes directly to the PR branch
3. Labels PR with `autofix:applied`
4. Posts a summary comment

This eliminates manual formatting work and ensures consistent style.

##### Dynamic Target Detection

Autofix automatically detects Python directories by finding all `.py` files in the repository. Standard non-source directories are excluded by default:

- `.git`, `.venv`, `venv`, `.env`, `env`
- `__pycache__`, `node_modules`
- `build`, `dist`, `.eggs`, `*.egg-info`
- `.tox`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`
- `htmlcov`, `.coverage`

##### Custom Exclusions (`.autofix-exclude`)

To exclude additional directories from autofix (e.g., generated code, vendor packages, legacy modules), create a `.autofix-exclude` file in your repository root:

```
# .autofix-exclude
# Comments start with #

# Exclude generated migrations
migrations/

# Exclude vendored code
vendor/
third_party/

# Exclude legacy modules being deprecated
legacy_api/
```

Each line specifies a directory to exclude. This file is optional - if not present, only standard exclusions apply.

---

## Getting Help

- **Documentation:** See `docs/ci/WORKFLOWS.md` for detailed workflow descriptions
- **Issues:** Open an issue in stranske/Workflows for bugs or feature requests
- **Templates:** Check `/templates/` for copy-paste solutions
- **Consumer templates:** See `/templates/consumer-repo/` for full automation setup

---

## CI Failure Routing

The keepalive system intelligently routes CI failures to the appropriate fix mechanism:

### Decision Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                     Gate Workflow Result                         │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  Gate Passed?   │
                    └─────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │ Yes                           │ No
              ▼                               ▼
    ┌─────────────────┐  ┌─────────────────┐
    │  Normal Work    │  │ Classify Failure│
    │  (run action)   │  └─────────────────┘
    │                 │           │
    │  Prompt:        │     ┌─────┴─────┐
    │  keepalive_     │     │           │
    │  next_task.md   │     ▼           ▼
    └─────────────────┘  ┌───────┐  ┌──────────────┐
                         │ Lint/ │  │ Tests/Mypy/  │
                         │Format │  │ Unknown      │
                         └───┬───┘  └──────┬───────┘
                             │             │
                             ▼             ▼
                     ┌────────────┐  ┌─────────────────┐
                     │  Autofix   │  │   Fix Mode      │
                     │  Workflow  │  │  (fix action)   │
                     │            │  │                 │
                     │  Black +   │  │  Prompt:        │
                     │  Ruff      │  │  fix_ci_        │
                     └────────────┘  │  failures.md    │
                                     └─────────────────┘
```

### How It Works

1. **Gate Evaluation**: When the keepalive loop evaluates, it checks the gate workflow status

2. **Failure Classification**: If the gate failed, the system inspects which jobs failed:
   - **Test failures**: Jobs with names containing `test`, `pytest`, `unittest`
   - **Mypy failures**: Jobs with names containing `mypy`, `type`, `typecheck`
   - **Lint failures**: Jobs with names containing `lint`, `ruff`, `black`, `format`

3. **Routing Decision**:
   - **Lint/Format failures** → Route to **Autofix** (Black + Ruff can fix these automatically)
   - **Test/Mypy failures** → Route to **Codex with fix_ci_failures.md prompt** (requires code changes)
   - **Unknown failures** → Route to **Codex with fix_ci_failures.md prompt** (needs investigation)

### Prompt Files

| Prompt | Purpose | When Used |
|--------|---------|-----------|
| `keepalive_next_task.md` | Normal task work | Gate passed, tasks remaining |
| `fix_ci_failures.md` | Focus on fixing CI | Test/mypy failures detected |

### Output Variables

The `evaluate` job outputs these new fields:

| Output | Description | Values |
|--------|-------------|--------|
| `prompt_mode` | Which prompt mode to use | `normal`, `fix_ci` |
| `prompt_file` | Full path to prompt file | Path to `.md` file |
| `reason` | Why this action was chosen | `fix-test`, `fix-mypy`, `fix-unknown`, etc. |

### Action Types

| Action | Description | Triggers |
|--------|-------------|----------|
| `run` | Normal Codex run | Gate passed, tasks remaining |
| `fix` | CI fix mode | Test/mypy failure detected |
| `wait` | Wait for gate | Gate pending or lint failure (autofix handles) |
| `stop` | Stop iteration | Tasks complete or max iterations |
| `skip` | Skip entirely | Keepalive disabled |

### Example Scenarios

**Scenario 1: Tests Failing**
```
Gate Status: failure
Failed Jobs: [test (3.13), test (3.14)]
Classification: test failure
Action: fix
Reason: fix-test
Prompt: fix_ci_failures.md
```

**Scenario 2: Mypy Errors**
```
Gate Status: failure
Failed Jobs: [mypy]
Classification: mypy failure
Action: fix
Reason: fix-mypy
Prompt: fix_ci_failures.md
```

**Scenario 3: Black Formatting**
```
Gate Status: failure
Failed Jobs: [lint (black)]
Classification: lint failure
Action: wait
Reason: gate-not-success
→ Autofix workflow handles this separately
```

**Scenario 4: All Passing**
```
Gate Status: success
Action: run
Reason: ready
Prompt: keepalive_next_task.md
```

### Consumer Setup

No additional configuration needed. The CI failure routing is built into the keepalive system and works automatically when you have:

1. `agents-81-gate-followups.yml` workflow (or `agents-keepalive-loop.yml` in Workflows / non-consolidated setups)
2. `pr-00-gate.yml` workflow (for gate status)
3. `fix_ci_failures.md` prompt (in `.github/codex/prompts/`)

Ensure `fix_ci_failures.md` exists in `.github/codex/prompts/` for fix mode to work properly.

### Python CI default migration

Omitting both reusable Python runtime inputs selects Python 3.13 and 3.14 in
parallel. An explicit `python-version` remains a single-runtime override; a nonempty `python-versions` array still takes precedence. The primary artifact
runtime defaults to shared `CI_PYTHON_VERSION` when selected, otherwise the first
selected runtime. Gate requests coverage on 3.14 only through
`coverage-python-version`; both runtimes retain identical test selection. Consumers should set
`coverage-python-version` equal to `primary-python-version`, and `COVERAGE_REFERENCE_RUNTIME` in the Gate
coverage stats step must match that same runtime. The non-reference leg (for example Python 3.13 when
3.14 is primary) still runs the full test matrix but without coverage instrumentation. Measured on the
Workflows repo (748 tests, four workers, 2026-10-25), enabling branch coverage on a second runtime added
36% wall time on Python 3.13 and 0% on 3.14 versus single-runtime coverage. `pytest-workers` accepts `auto`
(the backward-compatible reusable default) or a positive integer; the first-party
Gate and new Gate template request `4`.

The supported Python standard is 3.14 first and 3.13 as backup (owner decision 2026-10-28);
the package minimum is `>=3.13`, and Python 3.12 is retired. The universal lock compiles
against the 3.13 floor. Consumer Gates are create-only, so the sync does not rewrite their
runtime overrides; each consumer moves its own pins to 3.13/3.14.
