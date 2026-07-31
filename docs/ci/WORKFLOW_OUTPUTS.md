# Workflow Outputs Reference

This page documents every `workflow_call` output exposed by the reusable workflows in this
repository. Each output includes a type, description, and a short usage example. The catalog is
audited against the reusable workflow declarations under `.github/workflows/reusable-*.yml`; for
workflows that only emit artifacts, see the "Workflows without workflow_call outputs" section.

Audit guard: `tests/workflows/test_reusable_workflow_outputs_doc.py` parses every
`.github/workflows/reusable-*.yml` file and fails when this catalog omits a declared
`workflow_call` output, carries a stale output description, or fails to list an output-free
reusable workflow in the no-output section.

## Reference table of workflow outputs

<!-- OUTPUT-REFERENCE-START -->
| Workflow | Output | Type | Description | Example |
| --- | --- | --- | --- | --- |
| `reusable-16-agents.yml` | `readiness_report` | string (JSON) | JSON report emitted by the readiness probe when enabled | `needs.agents.outputs.readiness_report` |
| `reusable-16-agents.yml` | `readiness_table` | string (Markdown) | Markdown table emitted by the readiness probe when enabled | `needs.agents.outputs.readiness_table` |
| `reusable-20-pr-meta.yml` | `keepalive_detected` | string (boolean-like) | Whether a keepalive comment was detected | `needs.pr_meta.outputs.keepalive_detected` |
| `reusable-20-pr-meta.yml` | `keepalive_reason` | string | Reason for keepalive dispatch decision | `needs.pr_meta.outputs.keepalive_reason` |
| `reusable-70-orchestrator-init.yml` | `rate_limit_safe` | string (boolean-like) | Whether rate limit is safe to proceed | `needs.init.outputs.rate_limit_safe` |
| `reusable-70-orchestrator-init.yml` | `has_work` | string (boolean-like) | Whether there is work to do | `needs.init.outputs.has_work` |
| `reusable-70-orchestrator-init.yml` | `token_source` | string | Which token to use for keepalive | `needs.init.outputs.token_source` |
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
| `reusable-bot-comment-handler.yml` | `comments_found` | string (boolean-like) | Whether unresolved bot comments were found | `needs.bot_comments.outputs.comments_found` |
| `reusable-bot-comment-handler.yml` | `comments_count` | string (number-like) | Number of unresolved bot comments found | `needs.bot_comments.outputs.comments_count` |
| `reusable-bot-comment-handler.yml` | `agent_triggered` | string (boolean-like) | Whether the agent was triggered to address comments | `needs.bot_comments.outputs.agent_triggered` |
| `reusable-bot-comment-handler.yml` | `app_auth_mode` | string enum | Selected App auth mode: client-id, legacy-app-id, or none | `needs.bot_comments.outputs.app_auth_mode` |
| `reusable-backplane-conformance.yml` | `conformant` | string (boolean-like) | true if the envelope conformed (or repo is not a participant) | `needs.conformance.outputs.conformant` |
| `reusable-pr-context.yml` | `pr_number` | string (number-like) | PR number | `needs.context.outputs.pr_number` |
| `reusable-pr-context.yml` | `pr_title` | string | PR title | `needs.context.outputs.pr_title` |
| `reusable-pr-context.yml` | `pr_body` | string | PR body (may be truncated for very long bodies) | `needs.context.outputs.pr_body` |
| `reusable-pr-context.yml` | `pr_state` | string | PR state (OPEN, CLOSED, MERGED) | `needs.context.outputs.pr_state` |
| `reusable-pr-context.yml` | `pr_is_draft` | string (boolean-like) | Whether PR is a draft | `needs.context.outputs.pr_is_draft` |
| `reusable-pr-context.yml` | `pr_merged` | string (boolean-like) | Whether PR is merged | `needs.context.outputs.pr_merged` |
| `reusable-pr-context.yml` | `pr_author` | string | PR author login | `needs.context.outputs.pr_author` |
| `reusable-pr-context.yml` | `head_ref` | string | Head branch name | `needs.context.outputs.head_ref` |
| `reusable-pr-context.yml` | `base_ref` | string | Base branch name | `needs.context.outputs.base_ref` |
| `reusable-pr-context.yml` | `head_sha` | string | Head commit SHA | `needs.context.outputs.head_sha` |
| `reusable-pr-context.yml` | `labels_json` | string (JSON array) | JSON array of label names | `needs.context.outputs.labels_json` |
| `reusable-pr-context.yml` | `has_agent_label` | string (boolean-like) | Whether PR has any agent:* label | `needs.context.outputs.has_agent_label` |
| `reusable-pr-context.yml` | `has_keepalive_label` | string (boolean-like) | Whether PR has agents:keepalive label | `needs.context.outputs.has_keepalive_label` |
| `reusable-pr-context.yml` | `files_count` | string (number-like) | Number of changed files | `needs.context.outputs.files_count` |
| `reusable-pr-context.yml` | `files_json` | string (JSON array) | JSON array of changed file paths | `needs.context.outputs.files_json` |
| `reusable-pr-context.yml` | `has_src_changes` | string (boolean-like) | Whether changes include src/ files | `needs.context.outputs.has_src_changes` |
| `reusable-pr-context.yml` | `has_test_changes` | string (boolean-like) | Whether changes include test files | `needs.context.outputs.has_test_changes` |
| `reusable-pr-context.yml` | `has_workflow_changes` | string (boolean-like) | Whether changes include .github/workflows/ | `needs.context.outputs.has_workflow_changes` |
| `reusable-pr-context.yml` | `ci_status` | string | Overall CI status (SUCCESS, FAILURE, PENDING, etc.) | `needs.context.outputs.ci_status` |
| `reusable-pr-context.yml` | `checks_json` | string (JSON array) | JSON array of check results | `needs.context.outputs.checks_json` |
| `reusable-pr-context.yml` | `full_context_json` | string (JSON) | Full PR context as JSON (use sparingly - large) | `needs.context.outputs.full_context_json` |
| `reusable-codex-run.yml` | `final-message` | string (base64) | Full Codex output message (base64 encoded) | `needs.codex.outputs.final-message` |
| `reusable-codex-run.yml` | `final-message-summary` | string | First 500 chars of Codex output (safe for PR comments) | `needs.codex.outputs.final-message-summary` |
| `reusable-codex-run.yml` | `error-summary` | string | Failure summary message (prefers Codex output, falls back to preflight errors) | `needs.codex.outputs.error-summary` |
| `reusable-codex-run.yml` | `exit-code` | string (number-like) | Codex CLI exit code (0=success) | `needs.codex.outputs.exit-code` |
| `reusable-codex-run.yml` | `changes-made` | string (boolean-like) | Whether Codex made file changes (true/false) | `needs.codex.outputs.changes-made` |
| `reusable-codex-run.yml` | `commit-sha` | string | SHA of the commit if changes were pushed | `needs.codex.outputs.commit-sha` |
| `reusable-codex-run.yml` | `files-changed` | string (number-like) | Number of files changed by Codex | `needs.codex.outputs.files-changed` |
| `reusable-codex-run.yml` | `capability-id` | string | Validated existing capability identifier; empty when evidence is absent. | `needs.codex.outputs.capability-id` |
| `reusable-codex-run.yml` | `effect-fingerprint` | string | Validated lowercase sha256 fingerprint of the bounded effect. | `needs.codex.outputs.effect-fingerprint` |
| `reusable-codex-run.yml` | `evidence-artifact-ref` | string | Validated durable logical reference to supporting evidence. | `needs.codex.outputs.evidence-artifact-ref` |
| `reusable-codex-run.yml` | `supervision-mode` | string enum | Validated supervision mode for this result. | `needs.codex.outputs.supervision-mode` |
| `reusable-codex-run.yml` | `capability-evidence-status` | string enum | Validated capability evidence status. | `needs.codex.outputs.capability-evidence-status` |
| `reusable-codex-run.yml` | `terminal-disposition` | string enum | Validated terminal disposition for the result. | `needs.codex.outputs.terminal-disposition` |
| `reusable-codex-run.yml` | `worker-profile-id` | string | Registry execution profile ID supplied by caller | `needs.codex.outputs.worker-profile-id` |
| `reusable-codex-run.yml` | `worker-requested-model` | string | Model requested through the registry execution profile | `needs.codex.outputs.worker-requested-model` |
| `reusable-codex-run.yml` | `worker-selected-model` | string | Actual Codex model selected after runner fallback | `needs.codex.outputs.worker-selected-model` |
| `reusable-codex-run.yml` | `worker-model-selection-reason` | string | Reason for the selected worker model | `needs.codex.outputs.worker-model-selection-reason` |
| `reusable-codex-run.yml` | `error-category` | string | Error category if failure occurred (transient/auth/resource/logic/unknown) | `needs.codex.outputs.error-category` |
| `reusable-codex-run.yml` | `error-type` | string | Error type if failure occurred (codex/infrastructure/auth/unknown) | `needs.codex.outputs.error-type` |
| `reusable-codex-run.yml` | `error-recovery` | string | Suggested recovery action if failure occurred | `needs.codex.outputs.error-recovery` |
| `reusable-codex-run.yml` | `watchdog-saved` | string (boolean-like) | Whether the pre-timeout watchdog saved uncommitted work (true/false) | `needs.codex.outputs.watchdog-saved` |
| `reusable-codex-run.yml` | `llm-analysis-run` | string (boolean-like) | Whether LLM analysis was performed | `needs.codex.outputs.llm-analysis-run` |
| `reusable-codex-run.yml` | `llm-provider` | string | LLM provider used for analysis (github-models, openai, regex-fallback) | `needs.codex.outputs.llm-provider` |
| `reusable-codex-run.yml` | `llm-model` | string | Specific model used for analysis (e.g., gpt-4o, claude-3-5-sonnet) | `needs.codex.outputs.llm-model` |
| `reusable-codex-run.yml` | `llm-confidence` | string (number-like) | Confidence level of LLM analysis (0-1) | `needs.codex.outputs.llm-confidence` |
| `reusable-codex-run.yml` | `llm-completed-tasks` | string (JSON) | JSON array of completed task descriptions | `needs.codex.outputs.llm-completed-tasks` |
| `reusable-codex-run.yml` | `llm-has-completions` | string (boolean-like) | Whether any task completions were detected | `needs.codex.outputs.llm-has-completions` |
| `reusable-codex-run.yml` | `llm-raw-confidence` | string (number-like) | Raw confidence before BS detection adjustment (0-1) | `needs.codex.outputs.llm-raw-confidence` |
| `reusable-codex-run.yml` | `llm-effort-score` | string (number-like) | Estimated effort score based on session activity | `needs.codex.outputs.llm-effort-score` |
| `reusable-codex-run.yml` | `llm-data-quality` | string | Session data quality level (high, medium, low, minimal) | `needs.codex.outputs.llm-data-quality` |
| `reusable-codex-run.yml` | `llm-analysis-text-length` | string (number-like) | Length of analysis text sent to LLM | `needs.codex.outputs.llm-analysis-text-length` |
| `reusable-codex-run.yml` | `llm-quality-warnings` | string (JSON) | JSON array of quality warnings from BS detector | `needs.codex.outputs.llm-quality-warnings` |
| `reusable-claude-run.yml` | `final-message` | string (base64) | Full Claude output message (base64 encoded) | `needs.claude.outputs.final-message` |
| `reusable-claude-run.yml` | `final-message-summary` | string | First 500 chars of Claude output (safe for PR comments) | `needs.claude.outputs.final-message-summary` |
| `reusable-claude-run.yml` | `error-summary` | string | Failure summary message (prefers Claude output, falls back to preflight errors) | `needs.claude.outputs.error-summary` |
| `reusable-claude-run.yml` | `exit-code` | string (number-like) | Claude CLI exit code (0=success) | `needs.claude.outputs.exit-code` |
| `reusable-claude-run.yml` | `changes-made` | string (boolean-like) | Whether Claude made file changes (true/false) | `needs.claude.outputs.changes-made` |
| `reusable-claude-run.yml` | `commit-sha` | string | SHA of the commit if changes were pushed | `needs.claude.outputs.commit-sha` |
| `reusable-claude-run.yml` | `files-changed` | string (number-like) | Number of files changed by Claude | `needs.claude.outputs.files-changed` |
| `reusable-claude-run.yml` | `capability-id` | string | Validated existing capability identifier; empty when evidence is absent. | `needs.claude.outputs.capability-id` |
| `reusable-claude-run.yml` | `effect-fingerprint` | string | Validated lowercase sha256 fingerprint of the bounded effect. | `needs.claude.outputs.effect-fingerprint` |
| `reusable-claude-run.yml` | `evidence-artifact-ref` | string | Validated durable logical reference to supporting evidence. | `needs.claude.outputs.evidence-artifact-ref` |
| `reusable-claude-run.yml` | `supervision-mode` | string enum | Validated supervision mode for this result. | `needs.claude.outputs.supervision-mode` |
| `reusable-claude-run.yml` | `capability-evidence-status` | string enum | Validated capability evidence status. | `needs.claude.outputs.capability-evidence-status` |
| `reusable-claude-run.yml` | `terminal-disposition` | string enum | Validated terminal disposition for the result. | `needs.claude.outputs.terminal-disposition` |
| `reusable-claude-run.yml` | `llm-analysis-run` | string (boolean-like) | Whether LLM analysis was performed | `needs.claude.outputs.llm-analysis-run` |
| `reusable-claude-run.yml` | `llm-provider` | string | LLM provider used for analysis (placeholder for compatibility) | `needs.claude.outputs.llm-provider` |
| `reusable-claude-run.yml` | `llm-model` | string | Specific model used for analysis (placeholder for compatibility) | `needs.claude.outputs.llm-model` |
| `reusable-claude-run.yml` | `llm-confidence` | string (number-like) | Confidence level of LLM analysis (placeholder for compatibility) | `needs.claude.outputs.llm-confidence` |
| `reusable-claude-run.yml` | `llm-completed-tasks` | string (JSON) | JSON array of completed task descriptions (placeholder for compatibility) | `needs.claude.outputs.llm-completed-tasks` |
| `reusable-claude-run.yml` | `llm-has-completions` | string (boolean-like) | Whether any task completions were detected (placeholder for compatibility) | `needs.claude.outputs.llm-has-completions` |
| `reusable-claude-run.yml` | `error-category` | string | Error category (transient/auth/resource/logic/unknown) | `needs.claude.outputs.error-category` |
| `reusable-claude-run.yml` | `error-type` | string | Error type (claude/infrastructure/auth/unknown) | `needs.claude.outputs.error-type` |
| `reusable-claude-run.yml` | `error-recovery` | string | Suggested recovery action | `needs.claude.outputs.error-recovery` |
| `reusable-cursor-run.yml` | `final-message` | string (base64) | Full Cursor output message (base64 encoded) | `needs.cursor.outputs.final-message` |
| `reusable-cursor-run.yml` | `final-message-summary` | string | First 500 chars of Cursor output (safe for PR comments) | `needs.cursor.outputs.final-message-summary` |
| `reusable-cursor-run.yml` | `error-summary` | string | Failure summary message (prefers Cursor output, falls back to preflight errors) | `needs.cursor.outputs.error-summary` |
| `reusable-cursor-run.yml` | `exit-code` | string (number-like) | Cursor CLI exit code (0=success) | `needs.cursor.outputs.exit-code` |
| `reusable-cursor-run.yml` | `changes-made` | string (boolean-like) | Whether Cursor made file changes (true/false) | `needs.cursor.outputs.changes-made` |
| `reusable-cursor-run.yml` | `commit-sha` | string | SHA of the commit if changes were pushed | `needs.cursor.outputs.commit-sha` |
| `reusable-cursor-run.yml` | `files-changed` | string (number-like) | Number of files changed by Cursor | `needs.cursor.outputs.files-changed` |
| `reusable-cursor-run.yml` | `capability-id` | string | Validated existing capability identifier; empty when evidence is absent. | `needs.cursor.outputs.capability-id` |
| `reusable-cursor-run.yml` | `effect-fingerprint` | string | Validated lowercase sha256 fingerprint of the bounded effect. | `needs.cursor.outputs.effect-fingerprint` |
| `reusable-cursor-run.yml` | `evidence-artifact-ref` | string | Validated durable logical reference to supporting evidence. | `needs.cursor.outputs.evidence-artifact-ref` |
| `reusable-cursor-run.yml` | `supervision-mode` | string enum | Validated supervision mode for this result. | `needs.cursor.outputs.supervision-mode` |
| `reusable-cursor-run.yml` | `capability-evidence-status` | string enum | Validated capability evidence status. | `needs.cursor.outputs.capability-evidence-status` |
| `reusable-cursor-run.yml` | `terminal-disposition` | string enum | Validated terminal disposition for the result. | `needs.cursor.outputs.terminal-disposition` |
| `reusable-cursor-run.yml` | `llm-analysis-run` | string (boolean-like) | Whether LLM analysis was performed | `needs.cursor.outputs.llm-analysis-run` |
| `reusable-cursor-run.yml` | `llm-provider` | string | LLM provider used for analysis (placeholder for compatibility) | `needs.cursor.outputs.llm-provider` |
| `reusable-cursor-run.yml` | `llm-model` | string | Specific model used for analysis (placeholder for compatibility) | `needs.cursor.outputs.llm-model` |
| `reusable-cursor-run.yml` | `llm-confidence` | string (number-like) | Confidence level of LLM analysis (placeholder for compatibility) | `needs.cursor.outputs.llm-confidence` |
| `reusable-cursor-run.yml` | `llm-completed-tasks` | string (JSON) | JSON array of completed task descriptions (placeholder for compatibility) | `needs.cursor.outputs.llm-completed-tasks` |
| `reusable-cursor-run.yml` | `llm-has-completions` | string (boolean-like) | Whether any task completions were detected (placeholder for compatibility) | `needs.cursor.outputs.llm-has-completions` |
| `reusable-cursor-run.yml` | `error-category` | string | Error category (transient/auth/resource/logic/unknown) | `needs.cursor.outputs.error-category` |
| `reusable-cursor-run.yml` | `error-type` | string | Error type (cursor/infrastructure/auth/unknown) | `needs.cursor.outputs.error-type` |
| `reusable-cursor-run.yml` | `error-recovery` | string | Suggested recovery action | `needs.cursor.outputs.error-recovery` |
| `reusable-gemini-run.yml` | `final-message` | string (base64) | Full Gemini output message (base64 encoded) | `needs.gemini.outputs.final-message` |
| `reusable-gemini-run.yml` | `final-message-summary` | string | First 500 chars of Gemini output (safe for PR comments) | `needs.gemini.outputs.final-message-summary` |
| `reusable-gemini-run.yml` | `error-summary` | string | Failure summary message (prefers Gemini output, falls back to preflight errors) | `needs.gemini.outputs.error-summary` |
| `reusable-gemini-run.yml` | `exit-code` | string (number-like) | Gemini CLI exit code (0=success) | `needs.gemini.outputs.exit-code` |
| `reusable-gemini-run.yml` | `changes-made` | string (boolean-like) | Whether Gemini made file changes (true/false) | `needs.gemini.outputs.changes-made` |
| `reusable-gemini-run.yml` | `commit-sha` | string | SHA of the commit if changes were pushed | `needs.gemini.outputs.commit-sha` |
| `reusable-gemini-run.yml` | `files-changed` | string (number-like) | Number of files changed by Gemini | `needs.gemini.outputs.files-changed` |
| `reusable-gemini-run.yml` | `capability-id` | string | Validated existing capability identifier; empty when evidence is absent. | `needs.gemini.outputs.capability-id` |
| `reusable-gemini-run.yml` | `effect-fingerprint` | string | Validated lowercase sha256 fingerprint of the bounded effect. | `needs.gemini.outputs.effect-fingerprint` |
| `reusable-gemini-run.yml` | `evidence-artifact-ref` | string | Validated durable logical reference to supporting evidence. | `needs.gemini.outputs.evidence-artifact-ref` |
| `reusable-gemini-run.yml` | `supervision-mode` | string enum | Validated supervision mode for this result. | `needs.gemini.outputs.supervision-mode` |
| `reusable-gemini-run.yml` | `capability-evidence-status` | string enum | Validated capability evidence status. | `needs.gemini.outputs.capability-evidence-status` |
| `reusable-gemini-run.yml` | `terminal-disposition` | string enum | Validated terminal disposition for the result. | `needs.gemini.outputs.terminal-disposition` |
| `reusable-gemini-run.yml` | `llm-analysis-run` | string (boolean-like) | Whether LLM analysis was performed | `needs.gemini.outputs.llm-analysis-run` |
| `reusable-gemini-run.yml` | `llm-provider` | string | LLM provider used for analysis (placeholder for compatibility) | `needs.gemini.outputs.llm-provider` |
| `reusable-gemini-run.yml` | `llm-model` | string | Specific model used for analysis (placeholder for compatibility) | `needs.gemini.outputs.llm-model` |
| `reusable-gemini-run.yml` | `llm-confidence` | string (number-like) | Confidence level of LLM analysis (placeholder for compatibility) | `needs.gemini.outputs.llm-confidence` |
| `reusable-gemini-run.yml` | `llm-completed-tasks` | string (JSON) | JSON array of completed task descriptions (placeholder for compatibility) | `needs.gemini.outputs.llm-completed-tasks` |
| `reusable-gemini-run.yml` | `llm-has-completions` | string (boolean-like) | Whether any task completions were detected (placeholder for compatibility) | `needs.gemini.outputs.llm-has-completions` |
| `reusable-gemini-run.yml` | `error-category` | string | Error category (transient/auth/resource/logic/unknown) | `needs.gemini.outputs.error-category` |
| `reusable-gemini-run.yml` | `error-type` | string | Error type (gemini/infrastructure/auth/unknown) | `needs.gemini.outputs.error-type` |
| `reusable-gemini-run.yml` | `error-recovery` | string | Suggested recovery action | `needs.gemini.outputs.error-recovery` |
<!-- OUTPUT-REFERENCE-END -->

## Workflows without workflow_call outputs

The workflows below do not expose `workflow_call` outputs. They publish artifacts or logs only.

<!-- OUTPUT-NONE-START -->
- `reusable-10-ci-python.yml`
- `reusable-11-ci-node.yml`
- `reusable-12-ci-docker.yml`
- `reusable-13-cross-repo-smoke.yml`
- `reusable-18-autofix.yml`
- `reusable-19-dependency-repair-contract.yml`
- `reusable-70-orchestrator-main.yml`
- `reusable-agents-issue-bridge.yml`
- `reusable-agents-pr-health.yml`
- `reusable-agents-verifier.yml`
- `reusable-model-profile-trial.yml`
<!-- OUTPUT-NONE-END -->

## Example usage in dependent jobs

### Gate keepalive dispatch using `reusable-20-pr-meta.yml`

```yaml
jobs:
  pr_meta:
    uses: stranske/Workflows/.github/workflows/reusable-20-pr-meta.yml@v1
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
    uses: stranske/Workflows/.github/workflows/reusable-70-orchestrator-init.yml@v1

  main:
    needs: init
    if: needs.init.outputs.rate_limit_safe == 'true' && needs.init.outputs.has_work == 'true'
    uses: stranske/Workflows/.github/workflows/reusable-70-orchestrator-main.yml@v1
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
    uses: stranske/Workflows/.github/workflows/reusable-codex-run.yml@v1
    with:
      prompt_file: .github/codex/prompts/keepalive.md

  report:
    needs: codex
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ needs.codex.outputs.final-message-summary }}"
```
## Provider-neutral optional capability evidence

All four registry-backed runners (`reusable-codex-run.yml`,
`reusable-claude-run.yml`, `reusable-cursor-run.yml`, and
`reusable-gemini-run.yml`) expose the same optional outputs:
`capability-id`, `effect-fingerprint`, `evidence-artifact-ref`,
`supervision-mode`, `capability-evidence-status`, and
`terminal-disposition`. Values are empty unless the caller supplies a complete
record accepted by `scripts.runner_lib normalize-evidence`; partial or invalid
records fail before agent execution.
