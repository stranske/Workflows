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
      python-version: '3.12'
```

2. **Commit and push** - CI will run on your next PR!

---

## Versioning Strategy

**`@main` is the single supported pin.** Reference every reusable workflow at
`@main`:

| Reference | When to use it | Behavior |
|-----------|----------------|----------|
| **Default branch (`@main`)** | The supported pin for all consumers. | Tracks the latest reusable workflow behavior used by the synced consumer templates. |
| **Pinned commit SHA** | Only for a one-off reproducible build or a controlled rollout you manage yourself. | Locked to a specific revision; **not** kept current and **unsupported** for ongoing use — the reusable's helper checkouts resolve against `main` (see below), so a SHA pin is no longer self-consistent. |

> **No floating version tags.** The repository previously published a floating
> `v1` tag (auto-refreshed to track `main`). That scheme has been **removed** —
> the `v1` tag never delivered isolation from `main` and added maintenance cost
> without benefit. Do not pin reusable workflows at the `v1` tag or any other
> tag; use `@main`.
>
> **Why `@main` is self-consistent and a SHA pin is not.** Inside
> `reusable-10-ci-python.yml`, the helper-code checkouts use `ref: main`
> intentionally (the helper layer is only validated as a unit on `main`). A
> caller pinned at `@main` therefore runs helper code that matches its pin. A
> caller pinned at an arbitrary SHA would still execute the helper scripts from
> `main`, so SHA pins are not supported for ongoing use.

Example (the supported pattern):

```yaml
jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    with:
      python-version: '3.12'
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
      python-version: '3.12'
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
- No external dependencies
- Easy customization

**Cons:**
- Manual updates needed
- Can drift from best practices

First-party registered consumers use the managed form of this method. Maint 68
coalesces copied-file changes into stable candidate/delivery PRs, and Maint 71
alone merges them after bounded reviewer settlement, an exact-head seal, a
fresh Gate, a valid GitHub-generated commit signature, and zero active review
threads. Maint 68 fails before publishing any generated head whose API-created
tree or signature does not match the staged delivery. A reviewer capacity outage
cannot require responses from every configured bot or keep the PR open indefinitely.
Maint 71 requires one substantive response when available; a successful status
whose own description says the review was skipped or not performed is recorded
as unavailable, not as reviewer quorum. Generated-branch Gate completions wake
Maint 71 immediately; the durable campaign queue supplies the timed fallback for
review windows and pending checks. Complete exact-plan candidate evidence starts
promotion automatically, while active review findings remain held until resolved
or covered by an authenticated exact-head Workflows source-fix proof.

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
| `reusable-10-ci-python.yml` | Full Python CI pipeline | `python-version`, `coverage-min` |
| `reusable-99-selftest.yml` | Run self-tests on workflow files | - |

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
| `reusable-16-agents.yml` | `readiness_report` → JSON payload from the readiness probe; `readiness_table` → Markdown table summarizing assignable agents. |
| `reusable-70-orchestrator-init.yml` | `rate_limit_safe`, `has_work`, `token_source`; keepalive/run toggles (`enable_keepalive`, `keepalive_pause_label`, `keepalive_round`, `keepalive_pr`, `keepalive_max_retries`, `keepalive_trace`); readiness/diagnostic toggles (`enable_readiness`, `readiness_agents`, `readiness_custom_logins`, `require_all`, `enable_preflight`, `enable_diagnostic`, `diagnostic_attempt_branch`, `diagnostic_dry_run`, `enable_verify_issue`, `verify_issue_number`, `verify_issue_valid_assignees`); bootstrap/worker settings (`enable_bootstrap`, `bootstrap_issues_label`, `draft_pr`, `dispatcher_force_issue`, `worker_max_parallel`, `conveyor_max_merges`); misc orchestrator options (`codex_user`, `codex_command_phrase`, `enable_watchdog`, `dry_run`, `options_json`). |
| `reusable-10-ci-python.yml` | None (artifacts only: coverage, metrics, summaries). |
| `reusable-11-ci-node.yml` | None (artifacts only: coverage + junit when enabled). |
| `reusable-12-ci-docker.yml` | None (logs only). |
| `reusable-13-cross-repo-smoke.yml` | None (logs only). |
| `reusable-18-autofix.yml` | None (patch artifacts + summaries). |
| `reusable-70-orchestrator-main.yml` | None (consumes init outputs; exports status via summaries). |
| `reusable-agents-issue-bridge.yml` | None (bridge PR creation artifacts/logs). |

### Reusable workflow output audit

This guide now carries the issue #10 acceptance evidence directly. The audit covers every reusable workflow declaration under `.github/workflows/reusable-*.yml`; update the exhaustive catalog in [`docs/ci/WORKFLOW_OUTPUTS.md`](ci/WORKFLOW_OUTPUTS.md) first, then mirror changed rows here when adding, renaming, or removing a reusable workflow output.

Reusable workflows with caller-facing `workflow_call` outputs:

| Workflow | Output | Type | Description | Example |
| --- | --- | --- | --- | --- |
| `reusable-16-agents.yml` | `readiness_report` | string (JSON) | JSON report emitted by the readiness probe when enabled. | `needs.agents.outputs.readiness_report` |
| `reusable-16-agents.yml` | `readiness_table` | string (Markdown) | Markdown table emitted by the readiness probe when enabled. | `needs.agents.outputs.readiness_table` |
| `reusable-20-pr-meta.yml` | `keepalive_detected` | string (boolean-like) | Whether a keepalive comment was detected. | `needs.pr_meta.outputs.keepalive_detected` |
| `reusable-20-pr-meta.yml` | `keepalive_reason` | string | Reason for the keepalive dispatch decision. | `needs.pr_meta.outputs.keepalive_reason` |
| `reusable-70-orchestrator-init.yml` | `rate_limit_safe` | string (boolean-like) | Whether rate limit is safe to proceed. | `needs.orchestrator-init.outputs.rate_limit_safe` |
| `reusable-70-orchestrator-init.yml` | `has_work` | string (boolean-like) | Whether there is work to do. | `needs.orchestrator-init.outputs.has_work` |
| `reusable-70-orchestrator-init.yml` | `token_source` | string | Which token source downstream jobs should use. | `needs.orchestrator-init.outputs.token_source` |
| `reusable-70-orchestrator-init.yml` | `enable_readiness` | string (boolean-like) | Resolved flag for the readiness probe. | `needs.orchestrator-init.outputs.enable_readiness` |
| `reusable-70-orchestrator-init.yml` | `readiness_agents` | string | Comma-separated agent keys for readiness. | `needs.orchestrator-init.outputs.readiness_agents` |
| `reusable-70-orchestrator-init.yml` | `readiness_custom_logins` | string | Comma-separated custom logins for readiness. | `needs.orchestrator-init.outputs.readiness_custom_logins` |
| `reusable-70-orchestrator-init.yml` | `require_all` | string (boolean-like) | Whether readiness should fail if any requested agent is missing. | `needs.orchestrator-init.outputs.require_all` |
| `reusable-70-orchestrator-init.yml` | `enable_preflight` | string (boolean-like) | Resolved flag for the Codex preflight probe. | `needs.orchestrator-init.outputs.enable_preflight` |
| `reusable-70-orchestrator-init.yml` | `codex_user` | string | Codex connector login override for preflight or bootstrap. | `needs.orchestrator-init.outputs.codex_user` |
| `reusable-70-orchestrator-init.yml` | `codex_command_phrase` | string | Command phrase to post when triggering Codex. | `needs.orchestrator-init.outputs.codex_command_phrase` |
| `reusable-70-orchestrator-init.yml` | `enable_diagnostic` | string (boolean-like) | Resolved flag for the bootstrap diagnostic job. | `needs.orchestrator-init.outputs.enable_diagnostic` |
| `reusable-70-orchestrator-init.yml` | `diagnostic_attempt_branch` | string (boolean-like) | Whether the diagnostic attempts to create a branch. | `needs.orchestrator-init.outputs.diagnostic_attempt_branch` |
| `reusable-70-orchestrator-init.yml` | `diagnostic_dry_run` | string (boolean-like) | Whether the diagnostic runs in dry-run mode. | `needs.orchestrator-init.outputs.diagnostic_dry_run` |
| `reusable-70-orchestrator-init.yml` | `enable_verify_issue` | string (boolean-like) | Whether the issue-verification step should run. | `needs.orchestrator-init.outputs.enable_verify_issue` |
| `reusable-70-orchestrator-init.yml` | `verify_issue_number` | string (number-like) | Issue number to verify when issue verification is enabled. | `needs.orchestrator-init.outputs.verify_issue_number` |
| `reusable-70-orchestrator-init.yml` | `enable_watchdog` | string (boolean-like) | Resolved flag for watchdog checks. | `needs.orchestrator-init.outputs.enable_watchdog` |
| `reusable-70-orchestrator-init.yml` | `enable_keepalive` | string (boolean-like) | Resolved flag for keepalive sweeps. | `needs.orchestrator-init.outputs.enable_keepalive` |
| `reusable-70-orchestrator-init.yml` | `keepalive_pause_label` | string | Label name that pauses keepalive when present. | `needs.orchestrator-init.outputs.keepalive_pause_label` |
| `reusable-70-orchestrator-init.yml` | `keepalive_max_retries` | string (number-like) | Maximum keepalive retries permitted for the run. | `needs.orchestrator-init.outputs.keepalive_max_retries` |
| `reusable-70-orchestrator-init.yml` | `enable_bootstrap` | string (boolean-like) | Resolved flag for Codex bootstrap. | `needs.orchestrator-init.outputs.enable_bootstrap` |
| `reusable-70-orchestrator-init.yml` | `bootstrap_issues_label` | string | Label to select issues for bootstrap. | `needs.orchestrator-init.outputs.bootstrap_issues_label` |
| `reusable-70-orchestrator-init.yml` | `draft_pr` | string (boolean-like) | Whether bootstrap PRs should be drafts. | `needs.orchestrator-init.outputs.draft_pr` |
| `reusable-70-orchestrator-init.yml` | `verify_issue_valid_assignees` | string | Comma-separated logins considered valid for issue verification. | `needs.orchestrator-init.outputs.verify_issue_valid_assignees` |
| `reusable-70-orchestrator-init.yml` | `dry_run` | string (boolean-like) | Global dry-run toggle for downstream jobs. | `needs.orchestrator-init.outputs.dry_run` |
| `reusable-70-orchestrator-init.yml` | `options_json` | string (JSON) | Resolved options JSON passed to the orchestrator. | `needs.orchestrator-init.outputs.options_json` |
| `reusable-70-orchestrator-init.yml` | `dispatcher_force_issue` | string (number-like) | Forced issue number for the dispatcher, when set. | `needs.orchestrator-init.outputs.dispatcher_force_issue` |
| `reusable-70-orchestrator-init.yml` | `worker_max_parallel` | string (number-like) | Maximum parallel worker runs to allow. | `needs.orchestrator-init.outputs.worker_max_parallel` |
| `reusable-70-orchestrator-init.yml` | `conveyor_max_merges` | string (number-like) | Maximum merges the conveyor should perform. | `needs.orchestrator-init.outputs.conveyor_max_merges` |
| `reusable-70-orchestrator-init.yml` | `keepalive_trace` | string | Keepalive trace identifier propagated to downstream runs. | `needs.orchestrator-init.outputs.keepalive_trace` |
| `reusable-70-orchestrator-init.yml` | `keepalive_round` | string | Keepalive round identifier. | `needs.orchestrator-init.outputs.keepalive_round` |
| `reusable-70-orchestrator-init.yml` | `keepalive_pr` | string (number-like) | Keepalive target PR number, when set. | `needs.orchestrator-init.outputs.keepalive_pr` |
| `reusable-bot-comment-handler.yml` | `comments_found` | string (boolean-like) | Whether unresolved bot comments were found. | `needs.bot-comments.outputs.comments_found` |
| `reusable-bot-comment-handler.yml` | `comments_count` | string (number-like) | Number of unresolved bot comments found. | `needs.bot-comments.outputs.comments_count` |
| `reusable-bot-comment-handler.yml` | `agent_triggered` | string (boolean-like) | Whether the agent was triggered to address comments. | `needs.bot-comments.outputs.agent_triggered` |
| `reusable-bot-comment-handler.yml` | `app_auth_mode` | string enum | Selected App auth mode: client-id, legacy-app-id, or none. | `needs.bot-comments.outputs.app_auth_mode` |
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
| `reusable-codex-run.yml` | `error-summary` | string | Failure summary message from Codex output or preflight errors. | `needs.codex.outputs.error-summary` |
| `reusable-codex-run.yml` | `exit-code` | string (number-like) | Codex CLI exit code. | `needs.codex.outputs.exit-code` |
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

Reusable workflows without `workflow_call` outputs:

| Workflow | Caller-facing output status |
| --- | --- |
| `reusable-10-ci-python.yml` | No `workflow_call` outputs; publishes coverage, metrics, logs, and summaries as artifacts/job output. |
| `reusable-11-ci-node.yml` | No `workflow_call` outputs; publishes coverage and JUnit artifacts when enabled. |
| `reusable-12-ci-docker.yml` | No `workflow_call` outputs; logs Docker smoke results. |
| `reusable-13-cross-repo-smoke.yml` | No `workflow_call` outputs; logs cross-repo smoke command output. |
| `reusable-18-autofix.yml` | No `workflow_call` outputs; publishes patch artifacts and summaries. |
| `reusable-70-orchestrator-main.yml` | No `workflow_call` outputs; consumes init outputs and reports status via summaries. |
| `reusable-agents-issue-bridge.yml` | No `workflow_call` outputs; creates bridge PR artifacts and logs. |
| `reusable-agents-pr-health.yml` | No `workflow_call` outputs; reports health through checks and summaries. |
| `reusable-agents-verifier.yml` | No `workflow_call` outputs; posts verifier reports and artifacts. |

### Using outputs in dependent jobs

The examples below show the two main output-consumption patterns: gating a downstream reusable workflow from orchestrator initialization, and passing a Markdown output into a reporting job.

Orchestrator chaining example:

```yaml
jobs:
  orchestrator-init:
    uses: stranske/Workflows/.github/workflows/reusable-70-orchestrator-init.yml@main

  orchestrator-main:
    needs: orchestrator-init
    if: needs.orchestrator-init.outputs.has_work == 'true' && needs.orchestrator-init.outputs.rate_limit_safe == 'true'
    uses: stranske/Workflows/.github/workflows/reusable-70-orchestrator-main.yml@main
    with:
      init_success: ${{ needs.orchestrator-init.result }}
      enable_keepalive: ${{ needs.orchestrator-init.outputs.enable_keepalive }}
      keepalive_pause_label: ${{ needs.orchestrator-init.outputs.keepalive_pause_label }}
      keepalive_round: ${{ needs.orchestrator-init.outputs.keepalive_round }}
      keepalive_pr: ${{ needs.orchestrator-init.outputs.keepalive_pr }}
      options_json: ${{ needs.orchestrator-init.outputs.options_json }}
      token_source: ${{ needs.orchestrator-init.outputs.token_source }}
```

Agent readiness example (posting the Markdown table):

```yaml
jobs:
  agents-readiness:
    uses: stranske/Workflows/.github/workflows/reusable-16-agents.yml@main
    with:
      enable_readiness: 'true'

  comment-readiness:
    needs: agents-readiness
    if: needs.agents-readiness.outputs.readiness_table != ''
    runs-on: ubuntu-latest
    steps:
      - name: Post readiness table
        uses: actions/github-script@v7
        with:
          script: |
            const table = `## Agent Readiness\n\n${{ toJSON(needs.agents-readiness.outputs.readiness_table) }}`;
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: table,
            });
```


### Agent Workflows

| Workflow | Purpose | Required Secrets |
|----------|---------|------------------|
| `reusable-agents-issue-bridge.yml` | Convert issues to PRs via agents | `service_bot_pat`, `owner_pr_pat` |

### Example: Full CI

```yaml
name: CI

on: [push, pull_request]

jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    with:
      python-version: '3.12'
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
| `dependency-refresh.yml` | Keep `requirements.lock` updated |
| `cosmetic-repair.yml` | Auto-fix formatting issues |

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
| `OWNER_PR_PAT` | Agent PR creation | Create PAT with `repo` scope |
| `PYPI_TOKEN` | Publishing packages | From pypi.org |

### Branch Protection

For the gate pattern to work:

1. Go to Settings → Branches → Add rule
2. Set branch pattern: `main`
3. Enable "Require status checks"
4. Add required checks: `CI Gate`, `Lint`, `Test`


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

The reusable `reusable-10-ci-python.yml` workflow runs two scripts from the
consumer repository. Add these files to your repo or CI will fail:

- `scripts/sync_test_dependencies.py` (validates test imports vs. dev deps)
- `tools/resolve_mypy_pin.py` (selects the Python version used by mypy)

You can copy the reference implementations from:

- `templates/integration-repo/scripts/sync_test_dependencies.py`
- `templates/integration-repo/tools/resolve_mypy_pin.py`

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
  "coverage": 80.0,
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
        python-version: ['3.12', '3.13']
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

# Root agent guidance files synced through .github/sync-manifest.yml
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/AGENTS.md -o AGENTS.md
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/CLAUDE.md -o CLAUDE.md

# These examples track the live Workflows source via /main/, which is the
# supported pin. For a one-off reproducible bootstrap you may replace /main/
# with a commit SHA in each URL, but @main is the supported reference for
# ongoing use (there is no floating version tag).
```

### Workflow Summary

| Workflow | Purpose | Triggers |
|----------|---------|----------|
| `ci.yml` | Python CI (lint, format, tests, typecheck) | push, PR |
| `agents-issue-intake.yml` | Assigns Codex/Copilot to issues | issue labeled `agent:codex` |
| `agents-80-pr-event-hub.yml` | Handles PR event routing, keepalive metadata, bot comments, and verification follow-ups | PR events and comments |
| `agents-81-gate-followups.yml` | Coordinates Gate follow-ups, keepalive/autofix recovery, and generated-delivery wakeups | Gate completion and follow-up events |
| `agents-verifier.yml` | Runs label-driven post-merge verification | manual dispatch, `verify:*` labels |
| `autofix.yml` | Auto-fixes lint/format issues | PR sync, `autofix` label |
| `pr-00-gate.yml` | Required PR gate and summary status | PR |
| `cross-repo-smoke.yml` | Optional cross-repo integration smoke (host + pinned dependency checkout) | push, PR, manual (opt-in via `CROSS_REPO_SMOKE_*` vars) |
| `autofix-versions.env` | Pins tool versions | N/A |
| `AGENTS.md` / `CLAUDE.md` | Repo-local agent guidance synced from Workflows | N/A |

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
| `OWNER_PR_PAT` | Create PRs on behalf of user; preferred credential for cross-repository label sync | issue-intake, Maint 69 label sync |
| `CROSS_REPO_TOKEN` | Read access to a dependency repository for cross-repo smoke | `cross-repo-smoke.yml` when `CROSS_REPO_SMOKE_ENABLED=true` |

### Cross-Repo Smoke (opt-in)

The synced `cross-repo-smoke.yml` caller is safe to ship to every consumer repo.
It remains a no-op until you set repository variables and the `CROSS_REPO_TOKEN`
secret. When enabled, it delegates to
`stranske/Workflows/.github/workflows/reusable-13-cross-repo-smoke.yml@main`.

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

Example caller wiring (already present in the synced template):

```yaml
jobs:
  cross-repo-smoke:
    if: >-
      vars.CROSS_REPO_SMOKE_ENABLED == 'true' &&
      vars.CROSS_REPO_SMOKE_DEPENDENCY_REPO != '' &&
      vars.CROSS_REPO_SMOKE_RUN_COMMAND != '' &&
      (github.event_name != 'pull_request' || github.event.pull_request.head.repo.fork == false)
    uses: stranske/Workflows/.github/workflows/reusable-13-cross-repo-smoke.yml@main
    with:
      dependency_repo: ${{ vars.CROSS_REPO_SMOKE_DEPENDENCY_REPO }}
      dependency_ref: ${{ vars.CROSS_REPO_SMOKE_DEPENDENCY_REF || 'main' }}
      setup_node: ${{ vars.CROSS_REPO_SMOKE_SETUP_NODE == 'true' }}
      node_version: ${{ vars.CROSS_REPO_SMOKE_NODE_VERSION || '20' }}
      host_install_command: ${{ vars.CROSS_REPO_SMOKE_HOST_INSTALL_COMMAND || '' }}
      dependency_install_command: ${{ vars.CROSS_REPO_SMOKE_DEPENDENCY_INSTALL_COMMAND || '' }}
      run_command: ${{ vars.CROSS_REPO_SMOKE_RUN_COMMAND }}
    secrets:
      CROSS_REPO_TOKEN: ${{ secrets.CROSS_REPO_TOKEN }}
```

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
Failed Jobs: [test (3.12), test (3.12)]
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

1. `agents-keepalive-loop.yml` workflow
2. `pr-00-gate.yml` workflow (for gate status)
3. `fix_ci_failures.md` prompt (in `.github/codex/prompts/`)

Ensure `fix_ci_failures.md` exists in `.github/codex/prompts/` for fix mode to work properly.
