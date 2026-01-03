# Workflow Outputs Reference

This page documents every `workflow_call` output exposed by the reusable workflows in this
repository. Each output includes a type, description, and a short usage example. For workflows
that only emit artifacts, see the "Workflows without workflow_call outputs" section.

## Reference table of workflow outputs

<!-- OUTPUT-REFERENCE-START -->
| Workflow | Output | Type | Description | Example |
| --- | --- | --- | --- | --- |
| `reusable-16-agents.yml` | `readiness_report` | string (JSON) | JSON report emitted by the readiness probe when enabled. | `needs.agents.outputs.readiness_report` |
| `reusable-16-agents.yml` | `readiness_table` | string (Markdown) | Markdown table emitted by the readiness probe when enabled. | `needs.agents.outputs.readiness_table` |
| `reusable-20-pr-meta.yml` | `keepalive_detected` | string (boolean-like) | `true` when a keepalive comment was detected and dispatch should proceed. | `needs.pr_meta.outputs.keepalive_detected` |
| `reusable-20-pr-meta.yml` | `keepalive_reason` | string | Reason why the keepalive dispatch was triggered or skipped. | `needs.pr_meta.outputs.keepalive_reason` |
| `reusable-70-orchestrator-init.yml` | `rate_limit_safe` | string (boolean-like) | Whether the rate limit precheck allows the run to proceed. | `needs.init.outputs.rate_limit_safe` |
| `reusable-70-orchestrator-init.yml` | `has_work` | string (boolean-like) | Whether the idle precheck found work to do. | `needs.init.outputs.has_work` |
| `reusable-70-orchestrator-init.yml` | `token_source` | string | Selected token source for keepalive writes. | `needs.init.outputs.token_source` |
| `reusable-70-orchestrator-init.yml` | `enable_readiness` | string (boolean-like) | Resolved flag for the readiness probe. | `needs.init.outputs.enable_readiness` |
| `reusable-70-orchestrator-init.yml` | `readiness_agents` | string | Comma-separated agent keys for readiness. | `needs.init.outputs.readiness_agents` |
| `reusable-70-orchestrator-init.yml` | `readiness_custom_logins` | string | Comma-separated custom logins for readiness. | `needs.init.outputs.readiness_custom_logins` |
| `reusable-70-orchestrator-init.yml` | `require_all` | string (boolean-like) | Whether readiness should fail if any requested agent is missing. | `needs.init.outputs.require_all` |
| `reusable-70-orchestrator-init.yml` | `enable_preflight` | string (boolean-like) | Resolved flag for the Codex preflight probe. | `needs.init.outputs.enable_preflight` |
| `reusable-70-orchestrator-init.yml` | `codex_user` | string | Codex connector login override for preflight or bootstrap. | `needs.init.outputs.codex_user` |
| `reusable-70-orchestrator-init.yml` | `codex_command_phrase` | string | Command phrase to post when triggering Codex. | `needs.init.outputs.codex_command_phrase` |
| `reusable-70-orchestrator-init.yml` | `enable_diagnostic` | string (boolean-like) | Resolved flag for the bootstrap diagnostic job. | `needs.init.outputs.enable_diagnostic` |
| `reusable-70-orchestrator-init.yml` | `diagnostic_attempt_branch` | string (boolean-like) | Whether the diagnostic attempts to create a branch. | `needs.init.outputs.diagnostic_attempt_branch` |
| `reusable-70-orchestrator-init.yml` | `diagnostic_dry_run` | string (boolean-like) | Whether the diagnostic runs in dry-run mode. | `needs.init.outputs.diagnostic_dry_run` |
| `reusable-70-orchestrator-init.yml` | `enable_verify_issue` | string (boolean-like) | Whether the issue-verification step should run. | `needs.init.outputs.enable_verify_issue` |
| `reusable-70-orchestrator-init.yml` | `verify_issue_number` | string (number-like) | Issue number to verify when issue verification is enabled. | `needs.init.outputs.verify_issue_number` |
| `reusable-70-orchestrator-init.yml` | `enable_watchdog` | string (boolean-like) | Resolved flag for watchdog checks. | `needs.init.outputs.enable_watchdog` |
| `reusable-70-orchestrator-init.yml` | `enable_keepalive` | string (boolean-like) | Resolved flag for keepalive sweeps. | `needs.init.outputs.enable_keepalive` |
| `reusable-70-orchestrator-init.yml` | `keepalive_pause_label` | string | Label name that pauses keepalive when present. | `needs.init.outputs.keepalive_pause_label` |
| `reusable-70-orchestrator-init.yml` | `keepalive_max_retries` | string (number-like) | Maximum keepalive retries permitted for the run. | `needs.init.outputs.keepalive_max_retries` |
| `reusable-70-orchestrator-init.yml` | `enable_bootstrap` | string (boolean-like) | Resolved flag for Codex bootstrap. | `needs.init.outputs.enable_bootstrap` |
| `reusable-70-orchestrator-init.yml` | `bootstrap_issues_label` | string | Label to select issues for bootstrap. | `needs.init.outputs.bootstrap_issues_label` |
| `reusable-70-orchestrator-init.yml` | `draft_pr` | string (boolean-like) | Whether bootstrap PRs should be drafts. | `needs.init.outputs.draft_pr` |
| `reusable-70-orchestrator-init.yml` | `verify_issue_valid_assignees` | string | Comma-separated logins considered valid for issue verification. | `needs.init.outputs.verify_issue_valid_assignees` |
| `reusable-70-orchestrator-init.yml` | `dry_run` | string (boolean-like) | Global dry-run toggle for downstream jobs. | `needs.init.outputs.dry_run` |
| `reusable-70-orchestrator-init.yml` | `options_json` | string (JSON) | Resolved options JSON passed to the orchestrator. | `needs.init.outputs.options_json` |
| `reusable-70-orchestrator-init.yml` | `dispatcher_force_issue` | string (number-like) | Forced issue number for the dispatcher, when set. | `needs.init.outputs.dispatcher_force_issue` |
| `reusable-70-orchestrator-init.yml` | `worker_max_parallel` | string (number-like) | Maximum parallel worker runs to allow. | `needs.init.outputs.worker_max_parallel` |
| `reusable-70-orchestrator-init.yml` | `conveyor_max_merges` | string (number-like) | Maximum merges the conveyor should perform. | `needs.init.outputs.conveyor_max_merges` |
| `reusable-70-orchestrator-init.yml` | `keepalive_trace` | string | Keepalive trace identifier propagated to downstream runs. | `needs.init.outputs.keepalive_trace` |
| `reusable-70-orchestrator-init.yml` | `keepalive_round` | string | Keepalive round identifier. | `needs.init.outputs.keepalive_round` |
| `reusable-70-orchestrator-init.yml` | `keepalive_pr` | string (number-like) | Keepalive target PR number, when set. | `needs.init.outputs.keepalive_pr` |
| `reusable-bot-comment-handler.yml` | `comments_found` | string (boolean-like) | `true` when unresolved bot comments were found. | `needs.bot_comments.outputs.comments_found` |
| `reusable-bot-comment-handler.yml` | `comments_count` | string (number-like) | Number of unresolved bot comments. | `needs.bot_comments.outputs.comments_count` |
| `reusable-bot-comment-handler.yml` | `agent_triggered` | string (boolean-like) | `true` when the agent workflow was dispatched. | `needs.bot_comments.outputs.agent_triggered` |
| `reusable-codex-run.yml` | `final-message` | string (base64) | Base64-encoded full Codex output. | `needs.codex.outputs.final-message` |
| `reusable-codex-run.yml` | `final-message-summary` | string | First 500 chars of Codex output, safe for comments. | `needs.codex.outputs.final-message-summary` |
| `reusable-codex-run.yml` | `exit-code` | string (number-like) | Codex CLI exit code (`0` success). | `needs.codex.outputs.exit-code` |
| `reusable-codex-run.yml` | `changes-made` | string (boolean-like) | `true` when Codex modified files. | `needs.codex.outputs.changes-made` |
| `reusable-codex-run.yml` | `commit-sha` | string | Commit SHA when changes were pushed. | `needs.codex.outputs.commit-sha` |
| `reusable-codex-run.yml` | `files-changed` | string (number-like) | Number of files changed by Codex. | `needs.codex.outputs.files-changed` |
| `reusable-codex-run.yml` | `error-category` | string | Error category (`transient`, `auth`, `resource`, `logic`, `unknown`). | `needs.codex.outputs.error-category` |
| `reusable-codex-run.yml` | `error-type` | string | Error type (`codex`, `infrastructure`, `auth`, `unknown`). | `needs.codex.outputs.error-type` |
| `reusable-codex-run.yml` | `error-recovery` | string | Suggested recovery action if a failure occurred. | `needs.codex.outputs.error-recovery` |
| `reusable-codex-run.yml` | `llm-analysis-run` | string (boolean-like) | `true` when LLM analysis was performed. | `needs.codex.outputs.llm-analysis-run` |
| `reusable-codex-run.yml` | `llm-provider` | string | LLM provider used (`github-models`, `openai`, `regex-fallback`). | `needs.codex.outputs.llm-provider` |
| `reusable-codex-run.yml` | `llm-confidence` | string (number-like) | Analysis confidence level (0-1). | `needs.codex.outputs.llm-confidence` |
| `reusable-codex-run.yml` | `llm-completed-tasks` | string (JSON) | JSON array of detected task completions. | `needs.codex.outputs.llm-completed-tasks` |
| `reusable-codex-run.yml` | `llm-has-completions` | string (boolean-like) | `true` when task completions were detected. | `needs.codex.outputs.llm-has-completions` |
| `reusable-codex-run.yml` | `llm-raw-confidence` | string (number-like) | Raw confidence before BS detection adjustment (0-1). | `needs.codex.outputs.llm-raw-confidence` |
| `reusable-codex-run.yml` | `llm-effort-score` | string (number-like) | Estimated effort score based on session activity. | `needs.codex.outputs.llm-effort-score` |
| `reusable-codex-run.yml` | `llm-data-quality` | string | Session data quality level (`high`, `medium`, `low`, `minimal`). | `needs.codex.outputs.llm-data-quality` |
| `reusable-codex-run.yml` | `llm-analysis-text-length` | string (number-like) | Length of analysis text sent to LLM. | `needs.codex.outputs.llm-analysis-text-length` |
| `reusable-codex-run.yml` | `llm-quality-warnings` | string (JSON) | JSON array of quality warnings from BS detector. | `needs.codex.outputs.llm-quality-warnings` |
<!-- OUTPUT-REFERENCE-END -->

## Workflows without workflow_call outputs

The workflows below do not expose `workflow_call` outputs. They publish artifacts or logs only.

<!-- OUTPUT-NONE-START -->
- `reusable-10-ci-python.yml`
- `reusable-11-ci-node.yml`
- `reusable-12-ci-docker.yml`
- `reusable-18-autofix.yml`
- `reusable-70-orchestrator-main.yml`
- `reusable-agents-issue-bridge.yml`
- `reusable-agents-verifier.yml`
<!-- OUTPUT-NONE-END -->

## Example usage in dependent jobs

### Gate keepalive dispatch using `reusable-20-pr-meta.yml`

```yaml
jobs:
  pr_meta:
    uses: stranske/Workflows/.github/workflows/reusable-20-pr-meta.yml@main
    with:
      pr_number: ${{ github.event.pull_request.number }}
      event_name: issue_comment
      event_action: created

  keepalive_notice:
    needs: pr_meta
    if: needs.pr_meta.outputs.keepalive_detected == 'true'
    runs-on: ubuntu-latest
    steps:
      - run: echo "Keepalive reason: ${{ needs.pr_meta.outputs.keepalive_reason }}"
```

### Orchestrator chaining with `reusable-70-orchestrator-init.yml`

```yaml
jobs:
  init:
    uses: stranske/Workflows/.github/workflows/reusable-70-orchestrator-init.yml@main

  main:
    needs: init
    if: needs.init.outputs.rate_limit_safe == 'true' && needs.init.outputs.has_work == 'true'
    uses: stranske/Workflows/.github/workflows/reusable-70-orchestrator-main.yml@main
    with:
      init_success: ${{ needs.init.result }}
      enable_readiness: ${{ needs.init.outputs.enable_readiness }}
      options_json: ${{ needs.init.outputs.options_json }}
      token_source: ${{ needs.init.outputs.token_source }}
```

### Summarize Codex output from `reusable-codex-run.yml`

```yaml
jobs:
  codex:
    uses: stranske/Workflows/.github/workflows/reusable-codex-run.yml@main
    with:
      prompt_file: .github/codex/prompts/keepalive.md

  report:
    needs: codex
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ needs.codex.outputs.final-message-summary }}"
```
