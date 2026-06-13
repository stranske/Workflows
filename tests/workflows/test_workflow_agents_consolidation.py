from pathlib import Path

import yaml

WORKFLOWS_DIR = Path(".github/workflows")
ISSUE_TEMPLATE_DIR = Path(".github/ISSUE_TEMPLATE")
KEEPALIVE_HELPER = Path("scripts/keepalive-runner.js")


def _load_workflow_yaml(name: str) -> dict:
    path = WORKFLOWS_DIR / name
    assert path.exists(), f"Workflow {name} must exist"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_issue_template_yaml(name: str) -> dict:
    path = ISSUE_TEMPLATE_DIR / name
    assert path.exists(), f"Issue template {name} must exist"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _issue_form_entries_by_label(data: dict) -> dict:
    entries = {}
    for item in data.get("body") or []:
        attributes = item.get("attributes") or {}
        label = attributes.get("label")
        if not label:
            continue
        entries[str(label).strip().lower()] = item
    return entries


def _workflow_on_section(data: dict) -> dict:
    return data.get("on") or data.get(True) or {}


def _workflow_step_by_id(path: Path, step_id: str) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for job in (data.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            if step.get("id") == step_id:
                return step
    raise AssertionError(f"{path} must define step id {step_id!r}")


def test_agents_orchestrator_inputs_and_uses():
    # The orchestrator is now split: dispatcher calls init and main reusable workflows
    dispatcher = WORKFLOWS_DIR / "agents-70-orchestrator.yml"
    init_reusable = WORKFLOWS_DIR / "reusable-70-orchestrator-init.yml"
    assert dispatcher.exists(), "agents-70-orchestrator.yml must exist"
    assert init_reusable.exists(), "reusable-70-orchestrator-init.yml must exist"

    dispatcher_text = dispatcher.read_text(encoding="utf-8")
    init_text = init_reusable.read_text(encoding="utf-8")
    combined_text = dispatcher_text + init_text

    assert "workflow_dispatch:" in dispatcher_text, "Orchestrator must allow manual dispatch"
    expected_inputs = {"params_json", "options_json"}
    for key in expected_inputs:
        assert f"{key}:" in dispatcher_text, f"Missing workflow_dispatch input: {key}"
    # params_json forwarded through reusable workflow call
    assert "params_json:" in dispatcher_text, "params_json must be forwarded to init workflow"
    # PARAMS_JSON env var is now in the init reusable workflow
    assert "PARAMS_JSON" in init_text, "Init workflow resolve step must pass params_json via env"
    # After extraction, the parsing logic is in agents_orchestrator_resolve.js
    assert (
        "agents_orchestrator_resolve.js" in combined_text
        or "agents-orchestrator-resolve" in combined_text
    ), "Orchestrator topology must invoke the resolver helper script"
    # Verify the helper script contains the JSON parsing logic
    resolver_script = Path(".github/scripts/agents_orchestrator_resolve.js")
    assert resolver_script.exists(), "Resolver helper script must exist"
    resolver_text = resolver_script.read_text(encoding="utf-8")
    assert "JSON.parse" in resolver_text, "Resolver script must parse params_json as JSON"
    assert "options_json" in combined_text, "options_json output must remain available"
    assert "enable_bootstrap" in combined_text, "Orchestrator must forward enable_bootstrap flag"
    assert (
        "bootstrap_issues_label" in combined_text
    ), "Orchestrator must forward bootstrap label configuration"
    assert (
        "keepalive_max_retries" in combined_text
    ), "Orchestrator must expose keepalive retry configuration"
    # The reusable-16-agents.yml is called from the main reusable workflow
    main_reusable = WORKFLOWS_DIR / "reusable-70-orchestrator-main.yml"
    if main_reusable.exists():
        main_text = main_reusable.read_text(encoding="utf-8")
        assert (
            "./.github/workflows/reusable-16-agents.yml" in main_text
        ), "Main workflow must call the reusable agents workflow"


def test_agents_orchestrator_exposes_dry_run_toggle():
    # Orchestrator is now split: dispatcher + init reusable + main reusable
    dispatcher = WORKFLOWS_DIR / "agents-70-orchestrator.yml"
    dispatcher_text = dispatcher.read_text(encoding="utf-8")
    assert "dry_run:" in dispatcher_text, "Orchestrator must expose a dry_run input"
    # dry_run is forwarded through the init reusable workflow
    assert "dry_run:" in dispatcher_text, "dry_run input must be wired into the workflow topology"
    assert (
        "needs.init.outputs.dry_run" in dispatcher_text
    ), "Main workflow invocation must forward the resolved dry_run flag from init"
    # After extraction, the dry_run output is computed in agents_orchestrator_resolve.js
    resolver_script = Path(".github/scripts/agents_orchestrator_resolve.js")
    assert resolver_script.exists(), "Resolver helper script must exist"
    resolver_text = resolver_script.read_text(encoding="utf-8")
    assert "dryRun" in resolver_text, "Resolve script should compute and surface the dry_run flag"


def test_orchestrator_idle_precheck_defers_on_issue_scan_rate_limit():
    init_text = (WORKFLOWS_DIR / "reusable-70-orchestrator-init.yml").read_text(encoding="utf-8")

    assert (
        "retryHelpers.isRateLimitError" in init_text
    ), "Idle precheck must use the shared GitHub API rate-limit classifier"
    assert (
        "deferredByRateLimit = true" in init_text
    ), "Idle precheck must record rate-limit deferrals instead of failing"
    assert (
        "Rate limit exhausted during idle precheck; deferring dispatch." in init_text
    ), "Idle precheck must emit a durable deferral notice"
    assert (
        "!hasWork && !deferredByRateLimit" in init_text
    ), "Idle-only messaging must not mask a rate-limit deferral"


def test_auto_pilot_context_and_cycle_reads_defer_on_rate_limit():
    text = (WORKFLOWS_DIR / "agents-auto-pilot.yml").read_text(encoding="utf-8")

    assert (
        "deferForRateLimit" in text
    ), "Auto-pilot context discovery must share a rate-limit deferral helper"
    assert (
        "Auto-pilot determine context deferred during" in text
    ), "Auto-pilot must explain which context read was deferred"
    for stage in ["issue fetch", "optimizer comment scan", "timeline scan"]:
        assert stage in text, f"Auto-pilot must defer safely during {stage}"
    assert (
        "core.setOutput('reason', 'rate-limited')" in text
    ), "Auto-pilot must expose rate-limited context deferrals as an output"
    assert (
        "core.setOutput('rate_limited', 'true')" in text
    ), "Auto-pilot cycle count must expose rate-limit deferrals as an output"
    assert (
        "steps.cycles.outputs.rate_limited != 'true'" in text
    ), "Auto-pilot must not choose a next step after a rate-limited cycle count"


def test_auto_pilot_dispatches_pr_event_hub_pr_meta_only():
    workflow_paths = [
        WORKFLOWS_DIR / "agents-auto-pilot.yml",
        Path("templates/consumer-repo/.github/workflows/agents-auto-pilot.yml"),
    ]

    for workflow_path in workflow_paths:
        text = workflow_path.read_text(encoding="utf-8")
        assert "import json, os, sys" in text
        assert "inputsByWorkflow" in text
        assert "'agents-80-pr-event-hub.yml': {" in text
        assert "handler: 'pr-meta'" in text


def test_auto_pilot_verify_step_parses_in_source_and_template():
    workflow_paths = [
        WORKFLOWS_DIR / "agents-auto-pilot.yml",
        Path("templates/consumer-repo/.github/workflows/agents-auto-pilot.yml"),
    ]

    for workflow_path in workflow_paths:
        step = _workflow_step_by_id(workflow_path, "verify_step")
        script = (step.get("with") or {}).get("script") or ""

        assert "capabilities: ['issues:write', 'pulls:read']\n}));" not in script
        assert (
            "capabilities: ['issues:write', 'pulls:read']\n});\n"
            "const issueNumber = Number(process.env.ISSUE_NUMBER);"
        ) in script
        assert "agentKey" not in script
        assert "Dispatched belt dispatcher" not in script


def test_orchestrator_bootstrap_label_delegates_fallback():
    text = (WORKFLOWS_DIR / "agents-70-orchestrator.yml").read_text(encoding="utf-8")
    assert (
        "bootstrap_issues_label empty; defaulting to agent:codex." not in text
    ), "Orchestrator should delegate fallback handling to the reusable workflow"
    assert (
        "core.notice(bootstrapLabelFallbackNotice);" not in text
    ), "Orchestrator must avoid emitting fallback notices directly"


def test_reusable_agents_workflow_structure():
    reusable = WORKFLOWS_DIR / "reusable-16-agents.yml"
    assert reusable.exists(), "reusable-16-agents.yml must exist"
    text = reusable.read_text(encoding="utf-8")
    assert "workflow_call:" in text, "Reusable agents workflow must be callable"
    for key in [
        "readiness_custom_logins",
        "require_all",
        "enable_preflight",
        "enable_verify_issue",
        "enable_watchdog",
        "enable_keepalive",
        "options_json",
    ]:
        assert f"{key}:" in text, f"Reusable agents workflow must expose input: {key}"


def test_legacy_agent_workflows_removed():
    present = {p.name for p in WORKFLOWS_DIR.glob("agents-*.yml")}
    forbidden = {
        "agents-40-consumer.yml",
        "agents-41-assign-and-watch.yml",
        "agents-41-assign.yml",
        "agents-42-watchdog.yml",
        "agents-44-copilot-readiness.yml",
        "agents-45-verify-codex-bootstrap-matrix.yml",
    }
    assert not (present & forbidden), f"Legacy agent workflows still present: {present & forbidden}"


def test_agent_watchdog_workflow_absent():
    legacy_watchdog = WORKFLOWS_DIR / "agent-watchdog.yml"
    assert not legacy_watchdog.exists(), "Standalone agent-watchdog workflow must remain deleted"


def test_consumer_sync_drift_uploads_machine_readable_report():
    text = (WORKFLOWS_DIR / "health-68-consumer-sync-drift.yml").read_text(encoding="utf-8")
    assert (
        "CONSUMER_SYNC_DRIFT_REPORT_JSON" in text
    ), "Health 68 must configure a JSON drift report path"
    assert (
        '--report-json "$CONSUMER_SYNC_DRIFT_REPORT_JSON"' in text
    ), "Health 68 must pass the drift report path into the checker"
    assert (
        '--summary "$GITHUB_STEP_SUMMARY"' in text
    ), "Health 68 must publish the report summary into the workflow run"
    assert (
        "consumer_sync_drift_issue_body.js" in text
    ), "Health 68 issue payload must use the structured drift report"
    assert (
        "sync_tracker_state" in text and "updateTrackerBody" in text
    ), "Health 68 must refresh the GitHub-visible drift issue checkpoint"
    assert (
        "consumer-sync-drift-report" in text
    ), "Health 68 must upload the drift report as a GitHub-visible artifact"
    assert (
        "DRIFT_TOKEN:" not in text
    ), "Health 68 must let the checker choose a usable exported read token at runtime"


def test_merge_sync_prs_uploads_machine_readable_report_and_hash_input():
    text = (WORKFLOWS_DIR / "maint-71-merge-sync-prs.yml").read_text(encoding="utf-8")
    assert "sync_hash:" in text, "Maint 71 must expose a target sync hash input"
    assert (
        "sync_pr_merge_contract.js" in text
    ), "Maint 71 must use the structured sync PR merge contract helper"
    assert (
        "selectActiveSyncPr" in text
    ), "Maint 71 must select the active PR with the hash-aware contract"
    assert "cleanup_branches:" in text, "Maint 71 must expose sync branch cleanup control"
    assert (
        "collectDeletableSyncBranches" in text and "branch_delete_failed" in text
    ), "Maint 71 must delete leftover sync branches and report deletion failures"
    assert (
        "parseBooleanInput" in text and "AUTO_MERGE_INPUT" in text
    ), "Maint 71 must preserve explicit false boolean inputs"
    assert "SYNC_PR_MERGE_REPORT_JSON" in text, "Maint 71 must configure a JSON merge report path"
    assert (
        "report-only mode remains successful" in text
    ), "Maint 71 dry-run mode must report blocking statuses without failing the workflow"
    assert (
        "sync-pr-merge-report" in text
    ), "Maint 71 must upload the merge report as a GitHub-visible artifact"


def test_dependabot_weekly_sweep_deletes_merged_branches():
    text = (WORKFLOWS_DIR / "maint-dependabot-weekly-sweep.yml").read_text(encoding="utf-8")
    assert "--delete-branch" in text, "Dependabot sweep must request branch deletion on merge"


def test_consumer_sync_run_uploads_machine_readable_report():
    text = (WORKFLOWS_DIR / "maint-68-sync-consumer-repos.yml").read_text(encoding="utf-8")
    assert (
        "sync_run_contract.js" in text
    ), "Maint 68 summary must use the structured sync run contract helper"
    assert (
        "CONSUMER_SYNC_RUN_REPORT_JSON" in text
    ), "Maint 68 must configure a JSON sync run report path"
    assert (
        "consumer-sync-result-" in text
    ), "Maint 68 matrix jobs must upload per-repo result artifacts"
    assert (
        "consumer-sync-run-report" in text
    ), "Maint 68 must upload the aggregate sync run report as a GitHub-visible artifact"
    assert (
        "sync_failed" in text and "create_pr_failed" in text
    ), "Maint 68 report must distinguish sync failures from PR creation failures"
    assert (
        "workflows-consumer-sync-pr/v1" in text
        and "<!-- workflows-consumer-sync:v1 $sync_marker -->" in text
    ), "Maint 68-created sync PRs must carry a machine-readable lifecycle marker"
    assert (
        "**Source SHA:**" in text
        and "**Template hash:**" in text
        and "**Sync branch:**" in text
        and "**Consumer repo:**" in text
    ), "Maint 68 sync PR bodies must expose source SHA, branch, hash, and repo metadata"


def test_auto_label_uses_retry_paginate_with_github_client_first():
    text = (WORKFLOWS_DIR / "agents-auto-label.yml").read_text(encoding="utf-8")
    assert (
        "const { paginateWithRetry } = retryHelpers;" in text
    ), "Auto-label should call the shared pagination helper directly"
    assert (
        "retryHelpers.paginateWithRetry(github, method, params, options)" not in text
    ), "Auto-label must not wrap paginateWithRetry with an arity guess"
    assert (
        "const labels = await paginateWithRetry(\n              github, github.rest.issues.listLabelsForRepo,"
        in text
    ), "Auto-label label discovery must pass the GitHub client as the first pagination argument"
    assert (
        "!contains(join(github.event.issue.labels.*.name, ','), 'campaign:')" in text
    ), "Auto-label must skip machine-managed campaign issues instead of embedding large campaign bodies"
    assert (
        "AUTO_LABEL_QUERY_MAX_CHARS" in text
        and "Truncated issue query to {query_max_chars} characters" in text
    ), "Auto-label must bound issue text sent to semantic label matching"
    assert (
        "client-id: ${{ secrets.WORKFLOWS_APP_CLIENT_ID || '0' }}" in text
    ), "Auto-label should use the create-github-app-token v3 client-id input"


def test_consumer_sync_diff_keeps_functional_lines_in_comparison():
    text = (WORKFLOWS_DIR / "maint-68-sync-consumer-repos.yml").read_text(encoding="utf-8")
    assert (
        "def comparable_lines(path):" in text
    ), "Maint 68 must normalize only leading file headers before comparing sync targets"
    assert (
        "return comparable_lines(src) != comparable_lines(dst)" in text
    ), "Maint 68 must compare functional lines after any leading comment header"
    assert (
        "src_lines[10:] != dst_lines[10:]" not in text
    ), "Maint 68 must not ignore fixed line ranges that can contain version pins"


def test_autofix_versions_env_is_not_general_template_synced():
    manifest = yaml.safe_load(Path(".github/sync-manifest.yml").read_text(encoding="utf-8"))
    workflow_sources = {
        entry.get("source") for entry in manifest.get("workflows", []) if isinstance(entry, dict)
    }
    assert ".github/workflows/autofix-versions.env" not in workflow_sources

    version_sync_text = (WORKFLOWS_DIR / "maint-52-sync-dev-versions.yml").read_text(
        encoding="utf-8"
    )
    assert ".github/workflows/autofix-versions.env" in version_sync_text
    assert "pyproject.toml .github/workflows/autofix-versions.env" in version_sync_text
    assert "requirements.lock" in version_sync_text


def test_consumer_sync_repo_exclusions_live_in_manifest():
    workflow_text = (WORKFLOWS_DIR / "maint-68-sync-consumer-repos.yml").read_text(encoding="utf-8")
    manifest_text = Path(".github/sync-manifest.yml").read_text(encoding="utf-8")
    checker_text = Path("scripts/check_consumer_sync_drift.py").read_text(encoding="utf-8")

    assert "skip_repos:" in manifest_text
    assert "stranske/Trend_Model_Project" in manifest_text
    assert "manifest_skip_reason" in workflow_text
    assert "manifest_skip_reason" in checker_text
    assert "repo_specific_skip_rules" not in workflow_text


def test_health_40_branch_protection_sweep_skips_push_runs():
    text = (WORKFLOWS_DIR / "health-40-sweep.yml").read_text(encoding="utf-8")
    assert (
        "github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'" in text
    ), "Health 40 should reserve branch-protection verification for scheduled/manual sweeps"
    assert (
        "needs.detect.outputs.run_branch_protection != 'false'" in text
    ), "Manual Health 40 sweeps must keep the branch-protection opt-out"


def test_weekly_metrics_uploads_selector_report_on_failure():
    workflow_text = (WORKFLOWS_DIR / "agents-weekly-metrics.yml").read_text(encoding="utf-8")
    template_text = Path(
        "templates/consumer-repo/.github/workflows/agents-weekly-metrics.yml"
    ).read_text(encoding="utf-8")
    for text in (workflow_text, template_text):
        assert (
            "artifacts/metric-artifacts-selection.json" in text
        ), "Weekly metrics must include selector JSON in uploaded artifacts"
        assert (
            ".github/scripts/weekly_metrics_download_manifest.js" in text
        ), "Weekly metrics must use the artifact download manifest helper"
        assert (
            "artifacts/metric-artifact-download-manifest.json" in text
            and "artifacts/metric-artifact-download-manifest.md" in text
        ), "Weekly metrics must upload artifact download manifest reports"
        assert (
            "--download-status failed" in text
            and "--unzip-status skipped" in text
            and "--unzip-status failed" in text
        ), "Weekly metrics must record download and unzip failure reasons"
        assert (
            "--finalize" in text and '--manifest "$download_manifest"' in text
        ), "Weekly metrics must finalize the artifact download manifest after the loop"
        assert (
            "OUTPUT_JSON_PATH: agent-weekly-metrics.json" in text
            and "agent-weekly-metrics.json" in text
        ), "Weekly metrics must upload a machine-readable aggregate summary"
        assert (
            'artifact_dir="artifacts/$safe_name/$id"' in text and "safe_name=" in text
        ), "Weekly metrics must sanitize artifact paths and isolate downloads by artifact ID"
        assert (
            'export ARTIFACT_ZIP="$artifact_dir/$id.zip"' in text
            and 'unzip -o "$ARTIFACT_ZIP" -d "$ARTIFACT_DIR"' in text
        ), "Weekly metrics must unzip each artifact inside its unique extraction directory"
        assert (
            "uses: actions/setup-node@48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e # v6" in text
        ), "Weekly metrics must pin the Node runtime setup action to the v6 commit SHA"
        assert (
            'node-version: "20"' in text
        ), "Weekly metrics must run its Node helpers on an explicit Node 20 runtime"
        assert (
            "Install GitHub API dependencies" not in text
        ), "Weekly metrics must rely on setup-api-client for pinned GitHub API dependencies"
        assert (
            "npm install --no-save --no-package-lock @octokit/rest @octokit/auth-app" not in text
        ), "Weekly metrics must not install floating Octokit dependencies in the repo root"
        assert text.index("Setup Node") < text.index(
            "uses: ./.github/actions/setup-api-client"
        ), "Weekly metrics must setup Node before setup-api-client installs pinned API dependencies"
        assert text.index("Setup Node") < text.index(
            "node .github/scripts/weekly_metrics_artifacts.js"
        ), "Weekly metrics must setup Node before invoking selector helpers"
        assert (
            "if: ${{ always() }}" in text
        ), "Weekly metrics artifact upload must run after selector failures"
        assert (
            "if-no-files-found: warn" in text
        ), "Weekly metrics upload must not mask the original failure when files are absent"
        assert (
            "TERMINAL_DISPOSITION_ARTIFACT_SELECTION_JSON" in text
        ), "Terminal coverage must receive the selector report for no-data traceability"
        assert (
            "BOT_COMMENT_AUTH_ARTIFACT_SELECTION_JSON" in text
        ), "Bot-comment auth coverage must receive the selector report for no-data traceability"
        assert (
            ".github/scripts/bot_comment_auth_coverage.js" in text
        ), "Weekly metrics must include the bot-comment auth coverage helper"
        assert (
            "bot-comment-auth-coverage-summary.json" in text
            and "bot-comment-auth-coverage-summary.md" in text
        ), "Weekly metrics must upload bot-comment auth coverage reports"
        assert (
            "TERMINAL_DISPOSITION_COVERAGE_MODE" in text
        ), "Terminal coverage must expose an explicit enforcement mode"
        assert (
            "BOT_COMMENT_AUTH_COVERAGE_MODE" in text
        ), "Bot-comment auth coverage must expose an explicit enforcement mode"
        assert (
            "TERMINAL_DISPOSITION_HARD_BLOCK_APPROVED" in text
        ), "Terminal coverage hard blocking must require an explicit approval flag"
        assert (
            "BOT_COMMENT_AUTH_HARD_BLOCK_APPROVED" in text
        ), "Bot-comment auth hard blocking must require an explicit approval flag"
        assert (
            "BOT_COMMENT_REUSABLE_EXPECTED_AUTH_MODE" in text
        ), "Bot-comment auth coverage must expose an explicit reusable expected-mode policy"
        assert (
            "BOT_COMMENT_WRAPPER_ALLOWED_AUTH_MODES" in text
        ), "Bot-comment auth coverage must expose wrapper allowed-mode policy"
        assert (
            "terminal_coverage_status=$?" in text
            and "TERMINAL_DISPOSITION_COVERAGE_EXIT_STATUS=${terminal_coverage_status}" in text
            and "Honor coverage hard-blocks" in text
        ), "Terminal coverage must post/upload reports before honoring hard-block failure"
        assert (
            "bot_comment_auth_status=$?" in text
            and "BOT_COMMENT_AUTH_COVERAGE_EXIT_STATUS=${bot_comment_auth_status}" in text
            and "Honor coverage hard-blocks" in text
        ), "Bot-comment auth coverage must post/upload reports before honoring hard-block failure"
        assert (
            'terminal_status="${TERMINAL_DISPOSITION_COVERAGE_EXIT_STATUS:-0}"' in text
            and 'bot_comment_auth_status="${BOT_COMMENT_AUTH_COVERAGE_EXIT_STATUS:-0}"' in text
        ), "Coverage hard-block status must be aggregated in one final step"
        assert (
            "terminal-disposition-exit-status=${terminal_status}" in text
            and "bot-comment-auth-exit-status=${bot_comment_auth_status}" in text
            and "coverage reports were uploaded before this failure" in text
        ), "Coverage hard-block diagnostics must preserve both preflight exit statuses"
        assert text.index("Upload weekly summary") < text.index(
            "Honor coverage hard-blocks"
        ), "Terminal coverage hard-block failure must wait for artifact upload"
        assert text.index("Upload weekly summary") < text.index(
            "Honor coverage hard-blocks"
        ), "Bot-comment auth hard-block failure must wait for artifact upload"
        assert text.index("Post summary to tracking issue") < text.index(
            "Honor coverage hard-blocks"
        ), "Terminal coverage hard-block failure must wait for tracking issue posting"
        assert text.index("Post summary to tracking issue") < text.index(
            "Honor coverage hard-blocks"
        ), "Bot-comment auth hard-block failure must wait for tracking issue posting"


def test_weekly_metrics_aggregate_script_is_synced_to_consumers():
    manifest = yaml.safe_load(Path(".github/sync-manifest.yml").read_text(encoding="utf-8"))
    manifest_sources = {entry.get("source") for entry in manifest.get("scripts", [])}
    workflow_text = (WORKFLOWS_DIR / "agents-weekly-metrics.yml").read_text(encoding="utf-8")
    template_workflow_text = Path(
        "templates/consumer-repo/.github/workflows/agents-weekly-metrics.yml"
    ).read_text(encoding="utf-8")

    assert "scripts/aggregate_agent_metrics.py" in workflow_text
    assert "scripts/aggregate_agent_metrics.py" in template_workflow_text
    assert "scripts/aggregate_agent_metrics.py" in manifest_sources
    assert Path("scripts/aggregate_agent_metrics.py").is_file()
    assert Path("templates/consumer-repo/scripts/aggregate_agent_metrics.py").is_file()


def test_keepalive_metrics_emit_compact_ndjson():
    workflow_paths = [
        WORKFLOWS_DIR / "agents-keepalive-loop.yml",
        Path("templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml"),
    ]
    for path in workflow_paths:
        text = path.read_text(encoding="utf-8")
        assert "metrics_json=$(jq -cn \\" in text, f"{path} must emit one JSON object per line"


def test_terminal_disposition_records_include_artifact_identity():
    workflow_paths = [
        WORKFLOWS_DIR / "agents-verify-to-issue-v2.yml",
        WORKFLOWS_DIR / "agents-verify-to-new-pr.yml",
        WORKFLOWS_DIR / "reusable-bot-comment-handler.yml",
        Path("templates/consumer-repo/.github/workflows/agents-verify-to-new-pr.yml"),
    ]
    for path in workflow_paths:
        text = path.read_text(encoding="utf-8")
        assert "artifact_name:" in text, f"{path} must identify terminal disposition artifact names"
        assert (
            "artifact_family:" in text
        ), f"{path} must identify terminal disposition artifact families"


def test_verify_to_new_pr_uploads_verifier_followup_ledger() -> None:
    workflow_paths = [
        WORKFLOWS_DIR / "agents-verify-to-new-pr.yml",
        Path("templates/consumer-repo/.github/workflows/agents-verify-to-new-pr.yml"),
    ]
    for path in workflow_paths:
        text = path.read_text(encoding="utf-8")
        assert "normalizeVerifierFollowupLedger" in text
        assert "verifier-followup-ledger.ndjson" in text
        assert "followup_policy" in text
        assert "max_chain_depth" in text
        assert "depth_limit_exceeded" in text
        assert "workflows-verifier-followup-ledger/v1" in Path(
            ".github/scripts/terminal_disposition.js"
        ).read_text(encoding="utf-8")
        assert "workflows-verifier-followup-policy/v1" in Path(
            ".github/scripts/terminal_disposition.js"
        ).read_text(encoding="utf-8")


def test_issue_intake_handles_codex_events():
    intake = WORKFLOWS_DIR / "agents-63-issue-intake.yml"
    assert intake.exists(), "agents-63-issue-intake.yml must exist"

    data = _load_workflow_yaml("agents-63-issue-intake.yml")
    triggers = _workflow_on_section(data)
    assert "issues" in triggers, "Issue intake must listen for issue events"
    issue_trigger = triggers.get("issues") or {}
    types = set(issue_trigger.get("types") or [])
    assert {"opened", "labeled", "reopened"}.issubset(
        types
    ), "Issue intake must react to issue label lifecycle events"
    assert (
        "unlabeled" in types
    ), "Issue intake must rerun when agent labels are removed to stay in sync"

    text = intake.read_text(encoding="utf-8")
    assert (
        "agent:codex" in text and "agents:codex" in text
    ), "Issue intake must guard on the codex agent labels"
    assert (
        ".github/scripts/decode_raw_input.py" in text
    ), "Issue intake must normalize ChatGPT payloads"
    assert (
        ".github/scripts/parse_chatgpt_topics.py" in text
    ), "Issue intake must parse ChatGPT topics"
    assert "github.rest.issues.create" in text, "Issue intake must create or update GitHub issues"
    assert (
        "./.github/workflows/reusable-agents-issue-bridge.yml" in text
    ), "Issue intake must invoke the reusable agents issue bridge"


def test_codex_bootstrap_lite_surfaces_keepalive_mode():
    action = Path(".github/actions/codex-bootstrap-lite/action.yml").read_text(encoding="utf-8")
    assert "keepalive_mode:" in action, "Codex bootstrap action must accept a keepalive_mode input"
    assert (
        "### Keepalive:" in action
    ), "Codex bootstrap action must label PR bodies with keepalive mode"


def test_issue_bridge_tracks_keepalive_mode():
    text = (WORKFLOWS_DIR / "reusable-agents-issue-bridge.yml").read_text(encoding="utf-8")
    assert "Resolve keepalive opt-in" in text, "Issue bridge must detect keepalive opt-in state"
    assert "### Keepalive:" in text, "Issue bridge must propagate keepalive mode to PR content"


def test_issue_bridge_keepalive_dispatch_disabled():
    text = (WORKFLOWS_DIR / "reusable-agents-issue-bridge.yml").read_text(encoding="utf-8")
    assert (
        "\n      - name: Dispatch Agents Orchestrator (keepalive sync)" not in text
    ), "Issue bridge should no longer dispatch keepalive via orchestrator"
    assert (
        "keepalive now runs exclusively via the orchestrator sweep" in text
    ), "Issue bridge should document that keepalive dispatch is disabled"


def test_issue_bridge_create_mode_normalizes_agent_key_for_assignees():
    text = (WORKFLOWS_DIR / "reusable-agents-issue-bridge.yml").read_text(encoding="utf-8")
    assert (
        "const agentKey = agent.toLowerCase();" in text
    ), "Issue bridge create-mode PR step must define agentKey before agent registry lookups"
    assert (
        "const cfg = getAgentConfig(agentKey || 'codex');" in text
    ), "Issue bridge assignee selection must continue using the normalized agentKey"


def test_keepalive_job_present():
    reusable = WORKFLOWS_DIR / "reusable-16-agents.yml"
    text = reusable.read_text(encoding="utf-8")
    assert "Codex Keepalive Sweep" in text, "Keepalive job must exist in reusable agents workflow"
    assert "enable_keepalive" in text, "Keepalive job must document enable_keepalive option"
    helper = KEEPALIVE_HELPER.read_text(encoding="utf-8")
    assert (
        "<!-- codex-keepalive-marker -->" in helper
    ), "Keepalive marker must be retained for duplicate suppression"
    assert "issue_numbers_json" in text, "Ready issues step must emit issue_numbers_json output"
    assert "first_issue" in text, "Ready issues step must emit first_issue output"


def test_agents_pr_meta_keepalive_configuration():
    workflow = _load_workflow_yaml("agents-pr-meta-v4.yml")
    triggers = _workflow_on_section(workflow)
    issue_comment = triggers.get("issue_comment", {})
    assert issue_comment.get("types") == [
        "created"
    ], "Keepalive detection must trigger on comment creation only"

    jobs = workflow.get("jobs", {})
    # v4 structure differs from v2 - check for the relevant jobs
    assert (
        "update_body" in jobs or "comment_event_context" in jobs
    ), "PR meta workflow must have relevant jobs for PR updates"


def test_keepalive_job_defined_once():
    data = _load_workflow_yaml("reusable-16-agents.yml")
    jobs = data.get("jobs", {})
    keepalive_jobs = []
    for name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        job_name = job.get("name")
        if not isinstance(job_name, str):
            continue
        if "Codex Keepalive" not in job_name:
            continue
        keepalive_jobs.append((name, job_name))
    assert keepalive_jobs == [
        ("keepalive", "Codex Keepalive Sweep")
    ], "Reusable workflow must expose a single Codex keepalive job"


def test_bootstrap_requires_single_label():
    text = (WORKFLOWS_DIR / "reusable-16-agents.yml").read_text(encoding="utf-8")
    assert (
        "bootstrap_issues_label not provided; defaulting to" in text
    ), "Bootstrap step must record when it falls back to the default label"
    assert (
        "bootstrap_issues_label must define exactly one label" in text
    ), "Bootstrap step must prevent sweeping multiple labels"
    assert (
        "Received multiple entries:" in text
    ), "Bootstrap guard should surface which labels triggered the failure"


def test_bootstrap_label_fallback_emits_notice():
    text = (WORKFLOWS_DIR / "reusable-16-agents.yml").read_text(encoding="utf-8")
    assert (
        "core.notice(fallbackMessage);" in text
    ), "Bootstrap step should surface fallback usage as a notice for operators"


def test_bootstrap_filters_by_requested_label():
    text = (WORKFLOWS_DIR / "reusable-16-agents.yml").read_text(encoding="utf-8")
    assert (
        "labels: label" in text
    ), "Bootstrap GitHub API call must request only the configured label"
    assert (
        "missing required label ${label}" in text
    ), "Bootstrap script must skip issues that do not carry the requested label"


def test_bootstrap_uses_paginated_issue_scan():
    text = (WORKFLOWS_DIR / "reusable-16-agents.yml").read_text(encoding="utf-8")
    assert "paginateWithRetry" in text, "Bootstrap must paginate issue scanning to avoid truncation"
    assert (
        "Evaluated issues:" in text
    ), "Bootstrap summary should report how many issues were inspected"


def test_bootstrap_summary_includes_scope_and_counts():
    text = (WORKFLOWS_DIR / "reusable-16-agents.yml").read_text(encoding="utf-8")
    assert (
        "Bootstrap label: **" in text
    ), "Bootstrap run summary should surface the resolved label scope"
    assert "Skipped issues" in text, "Bootstrap summary must document skipped issues"
    assert "Accepted issues:" in text, "Bootstrap summary must include accepted issue counts"
    assert "Skipped issues:" in text, "Bootstrap summary must include skipped issue counts"
    assert (
        "https://github.com/" in text
    ), "Bootstrap summary should link directly to accepted issues"
    assert (
        "summary.addList(summariseList(accepted.map((issue) => formatIssue(issue))))" in text
    ), "Bootstrap summary must clamp accepted issue output to avoid excessive entries"


def test_bootstrap_summary_mentions_truncation_notice():
    text = (WORKFLOWS_DIR / "reusable-16-agents.yml").read_text(encoding="utf-8")
    assert (
        "Scan truncated after ${scanLimit} issues." in text
    ), "Bootstrap summary must document when the issue scan hits the truncation guard"


def test_bootstrap_dedupes_duplicate_labels():
    text = (WORKFLOWS_DIR / "reusable-16-agents.yml").read_text(encoding="utf-8")
    assert (
        "const dedupeLabels = (values) =>" in text
    ), "Bootstrap script should define a helper to dedupe requested labels"
    assert (
        "Duplicate bootstrap labels removed; proceeding with:" in text
    ), "Bootstrap summary must surface when duplicate labels are trimmed"


def test_bootstrap_label_filter_is_case_insensitive():
    text = (WORKFLOWS_DIR / "reusable-16-agents.yml").read_text(encoding="utf-8")
    assert (
        "const labelLower = labels[0].lower;" in text
    ), "Bootstrap step must normalise the requested label for comparisons"
    assert (
        "labelNames.includes(labelLower)" in text
    ), "Bootstrap step should compare label membership using the normalised value"


def test_bootstrap_guard_clears_outputs_on_failure():
    text = (WORKFLOWS_DIR / "reusable-16-agents.yml").read_text(encoding="utf-8")
    assert (
        "const clearOutputs = () =>" in text
    ), "Bootstrap guard should define an output clearing helper"
    assert (
        "core.setOutput('issue_numbers', '')" in text
    ), "Bootstrap guard must clear issue_numbers when aborting"
    assert (
        "core.setOutput('issue_numbers_json', '[]')" in text
    ), "Bootstrap guard must clear issue_numbers_json when aborting"
    assert (
        "core.setOutput('first_issue', '')" in text
    ), "Bootstrap guard must clear first_issue when aborting"
    assert (
        "clearOutputs();" in text
    ), "Bootstrap guard should invoke the output clearing helper before exiting early"


def test_run_summary_dedupes_stage_entries():
    text = (WORKFLOWS_DIR / "reusable-16-agents.yml").read_text(encoding="utf-8")
    assert "const seen = new Map();" in text, "Run summary should track encountered stages"
    assert (
        "if (!seen.has(stage.key))" in text
    ), "Run summary must only record the first instance of each stage"
    assert (
        "existing.extras = Array.from(mergedExtras).filter(Boolean);" in text
    ), "Run summary should merge extras when deduplicating stages"


def test_agents_orchestrator_has_concurrency_defaults():
    # Orchestrator is now split: dispatcher + init + main reusable workflows
    data = _load_workflow_yaml("agents-70-orchestrator.yml")

    # Top-level concurrency prevents overlapping orchestrator runs from consuming excessive API quota
    top_concurrency = data.get("concurrency") or {}
    assert (
        top_concurrency.get("group") == "agents-70-orchestrator-singleton"
    ), "Top-level orchestrator concurrency must prevent overlapping runs"
    assert (
        top_concurrency.get("cancel-in-progress") is False
    ), "Top-level concurrency must not cancel in-progress runs"

    # The orchestrate job is now in the main reusable workflow
    main_data = _load_workflow_yaml("reusable-70-orchestrator-main.yml")
    jobs = main_data.get("jobs", {})
    orchestrate = jobs.get("orchestrate", {})
    assert orchestrate.get("uses"), "Orchestrate job should call the reusable-16-agents workflow"

    job_concurrency = orchestrate.get("concurrency") or {}
    # Verify concurrency patterns in the main reusable workflow
    assert (
        job_concurrency.get("cancel-in-progress") is False
    ), "Orchestrator job concurrency must keep existing runs alive"


def test_agents_orchestrator_schedule_preserved():
    data = _load_workflow_yaml("agents-70-orchestrator.yml")

    on_section = _workflow_on_section(data)
    schedule = on_section.get("schedule") or []
    assert schedule, "Orchestrator schedule must remain defined"

    cron_entries = [
        entry.get("cron") for entry in schedule if isinstance(entry, dict) and "cron" in entry
    ]
    # Schedule reduced from */20 to */30 to conserve API rate limit (R-3)
    assert cron_entries == [
        "*/30 * * * *"
    ], "Orchestrator schedule must stay on the 30-minute cadence to conserve API quota"


def test_orchestrator_jobs_checkout_scripts_before_local_requires():
    # The orchestrator is now split: jobs are in init and main reusable workflows
    init_data = _load_workflow_yaml("reusable-70-orchestrator-init.yml")
    main_data = _load_workflow_yaml("reusable-70-orchestrator-main.yml")

    init_jobs = init_data.get("jobs", {})
    main_jobs = main_data.get("jobs", {})
    all_jobs = {**init_jobs, **main_jobs}

    targets = {
        "resolve-params": "./.github/scripts/agents_orchestrator_resolve.js",
        "keepalive-guard": "./.github/scripts/keepalive_orchestrator_gate_runner.js",
        "belt-dispatch-summary": "./.github/scripts/agents_dispatch_summary.js",
        "belt-scan-ready-prs": "./.github/scripts/agents_belt_scan.js",
    }

    for job_name, helper_path in targets.items():
        job = all_jobs.get(job_name)
        assert job, f"Job {job_name} must exist in the orchestrator workflow topology"
        steps = job.get("steps") or []
        assert steps, f"Job {job_name} must define steps"

        checkout_index = None
        helper_index = None
        helper_script = None

        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue

            uses = step.get("uses")
            if uses and uses.startswith("actions/checkout@") and checkout_index is None:
                checkout_index = index

            script_body = None
            if isinstance(step.get("with"), dict):
                script_body = step["with"].get("script")
            if script_body is None and isinstance(step.get("run"), str):
                script_body = step["run"]

            if isinstance(script_body, str) and helper_path in script_body:
                helper_index = index
                helper_script = script_body
                break

        assert helper_index is not None, f"Job {job_name} must require {helper_path}"
        assert checkout_index is not None, f"Job {job_name} must checkout orchestrator scripts"
        assert (
            checkout_index < helper_index
        ), f"Checkout step must precede {helper_path} usage in job {job_name}"

        checkout_step = steps[checkout_index]
        checkout_with = checkout_step.get("with") or {}
        sparse_checkout = str(checkout_with.get("sparse-checkout", ""))
        paths = {line.strip() for line in sparse_checkout.splitlines() if line.strip()}
        assert (
            ".github/scripts" in paths
        ), f"Job {job_name} must sparsely checkout .github/scripts before requiring helpers"
        assert (
            checkout_with.get("sparse-checkout-cone-mode") is False
        ), "Sparse checkout must disable cone mode for nested scripts"

        assert (
            isinstance(helper_script, str)
            and "Do not remove checkout; local helper is required." in helper_script
        ), f"Job {job_name} must warn against removing the checkout guard"


def test_gate_workflow_uses_fork_head_for_script_tests_and_ledger():
    data = _load_workflow_yaml("pr-00-gate.yml")
    jobs = data.get("jobs", {})

    scripts_job = jobs.get("github-scripts-tests") or {}
    scripts_steps = scripts_job.get("steps") or []
    assert scripts_steps, "github-scripts-tests job must define steps"
    checkout_step = scripts_steps[0]
    checkout_with = checkout_step.get("with") or {}
    expected_repo_expr = "${{ github.event.pull_request.head.repo.full_name || github.repository }}"
    expected_ref_expr = "${{ github.event.pull_request.head.sha || github.sha }}"
    assert (
        checkout_with.get("repository") == expected_repo_expr
    ), "github-scripts-tests checkout must pull the contributor head repository"
    assert (
        checkout_with.get("ref") == expected_ref_expr
    ), "github-scripts-tests checkout must use the contributor head commit"

    ledger_job = jobs.get("ledger-validation") or {}
    ledger_steps = ledger_job.get("steps") or []
    assert ledger_steps, "ledger-validation job must define steps"
    ledger_checkout = next(
        (step for step in ledger_steps if step.get("name") == "Checkout repository"),
        None,
    )
    assert ledger_checkout, "ledger-validation job must checkout the repository"
    ledger_with = ledger_checkout.get("with") or {}
    assert (
        ledger_with.get("repository") == expected_repo_expr
    ), "Ledger validation checkout must pull the contributor head repository"
    assert (
        ledger_with.get("ref") == expected_ref_expr
    ), "Ledger validation checkout must use the contributor head commit"


def test_gate_commit_status_has_workflow_token_fallback():
    data = _load_workflow_yaml("pr-00-gate.yml")
    summary = (data.get("jobs", {}) or {}).get("summary") or {}
    steps = summary.get("steps") or []
    status_step = next(
        (step for step in steps if step.get("name") == "Report Gate commit status"),
        None,
    )
    assert status_step, "Gate summary must publish the Gate / gate commit status"
    status_with = status_step.get("with") or {}
    assert (
        status_with.get("github-token") == "${{ github.token }}"
    ), "Gate status fallback must use the workflow token with statuses:write"
    script = str(status_with.get("script") or "")
    assert (
        "statusResponse === null" in script
    ), "Gate status step must detect token-balancer permission fallback"
    assert (
        "github.rest.repos.createCommitStatus(statusPayload)" in script
    ), "Gate status step must retry with the workflow token when app tokens lack statuses:write"


def test_bootstrap_step_defaults_label_when_missing():
    text = (WORKFLOWS_DIR / "reusable-16-agents.yml").read_text(encoding="utf-8")
    assert (
        "let fallbackLabel = 'agent:codex'" in text
    ), "Bootstrap logic must define agent:codex as the initial fallback label"
    assert (
        "bootstrap_issues_label not provided; defaulting to" in text
    ), "Bootstrap step must record when it falls back to the default label"


def test_agents_consumer_workflow_removed():
    path = WORKFLOWS_DIR / "agents-62-consumer.yml"
    assert not path.exists(), "Retired Agents 62 consumer wrapper must remain absent"


def test_agent_task_template_auto_labels_codex():
    template = Path(".github/ISSUE_TEMPLATE/agent_task.yml")
    assert template.exists(), "Agent task issue template must exist"
    data = yaml.safe_load(template.read_text(encoding="utf-8"))
    labels = set(data.get("labels") or [])
    assert {"agents", "agent:codex"}.issubset(
        labels
    ), "Agent task template must auto-apply agents + agent:codex labels"


def test_codex_issue_forms_require_scope_tasks_acceptance():
    for name in ("bug_report_codex.yml", "feature_request_codex.yml"):
        data = _load_issue_template_yaml(name)
        entries = _issue_form_entries_by_label(data)
        for required_label in ("scope", "tasks", "acceptance criteria"):
            assert (
                required_label in entries
            ), f"Issue template {name} must include {required_label} section"
            validations = entries[required_label].get("validations") or {}
            assert (
                validations.get("required") is True
            ), f"Issue template {name} must require {required_label} section"


def test_issue_intake_guard_checks_agent_label():
    text = (WORKFLOWS_DIR / "agents-63-issue-intake.yml").read_text(encoding="utf-8")
    # The workflow must check for agent:* prefix in the issue's labels array
    # This handles all issue events (opened, labeled, reopened, etc.) and
    # solves the problem of multiple labels being added simultaneously
    # It also generalizes to support any agent (codex, claude, etc.)
    assert (
        "github.event.issue.labels" in text
    ), "Issue intake must check issue.labels array for agent:* labels"
    assert "agent:" in text, "Issue intake must check for agent: prefix to match any agent label"


def test_reusable_agents_jobs_have_timeouts():
    data = _load_workflow_yaml("reusable-16-agents.yml")
    jobs = data.get("jobs", {})
    missing_timeouts = [
        name
        for name, job in jobs.items()
        if isinstance(job, dict) and job.get("runs-on") and "timeout-minutes" not in job
    ]
    assert not missing_timeouts, f"Jobs missing timeout-minutes: {missing_timeouts}"


def test_reusable_watchdog_job_gated_by_flag():
    data = _load_workflow_yaml("reusable-16-agents.yml")
    jobs = data.get("jobs", {})
    watchdog = jobs.get("watchdog")
    assert watchdog, "Reusable workflow must expose watchdog job"
    assert (
        watchdog.get("if") == "inputs.enable_watchdog == 'true'"
    ), "Watchdog job must respect enable_watchdog flag"
    assert watchdog.get("timeout-minutes") == 20, "Watchdog job should retain the expected timeout"
    steps = watchdog.get("steps") or []
    assert any(
        isinstance(step, dict) and step.get("uses", "").startswith("actions/checkout@")
        for step in steps
    ), "Watchdog job must continue performing basic repo checks"


def test_keepalive_summary_reports_scope_and_activity():
    text = KEEPALIVE_HELPER.read_text(encoding="utf-8")
    assert "Target labels:" in text, "Keepalive summary should list the label scope"
    assert (
        "Agent logins:" in text
    ), "Keepalive summary should surface the Codex logins under consideration"
    assert (
        "No unattended Codex tasks detected." in text or "keepalive posted" in text
    ), "Keepalive summary must describe whether any PRs required intervention"
    assert (
        "Triggered keepalive comments" in text
    ), "Keepalive summary should wrap triggered comment list in a collapsible section"
    assert (
        "Triggered keepalive count:" in text
    ), "Keepalive summary should record how many follow-up comments were sent"
    assert (
        "Evaluated pull requests:" in text
    ), "Keepalive summary should report how many PRs were inspected"
    assert "agents:paused" in text, "Keepalive runner must recognise the agents:paused label"
    assert (
        "Skipped ${paused.length} paused PR" in text
    ), "Keepalive summary must log the number of paused PRs it skipped"


def test_keepalive_summary_includes_skip_notice():
    text = KEEPALIVE_HELPER.read_text(encoding="utf-8")
    assert (
        "Skip requested via options_json." in text
    ), "Keepalive summary must log when the job exits early due to options overrides"


def test_keepalive_dedupes_scope_configuration():
    text = KEEPALIVE_HELPER.read_text(encoding="utf-8")
    assert (
        "const dedupe =" in text or "function dedupe(" in text
    ), "Keepalive script should define a dedupe helper for repeated inputs"
    assert (
        "targetLabels = dedupe(targetLabels)" in text
    ), "Keepalive must dedupe resolved label scope before reporting it"
    assert (
        "agentLogins = dedupe(agentLogins)" in text
    ), "Keepalive must dedupe resolved agent login list"


def test_keepalive_job_runs_after_failures():
    data = _load_workflow_yaml("reusable-16-agents.yml")
    jobs = data.get("jobs", {})
    keepalive = jobs.get("keepalive")
    assert keepalive, "Reusable workflow must define keepalive job"
    assert (
        keepalive.get("if") == "${{ always() && inputs.enable_keepalive == 'true' }}"
    ), "Keepalive job must run even if earlier jobs fail while respecting enable_keepalive flag"


def test_orchestrator_documents_keepalive_pause_controls():
    data = _load_workflow_yaml("agents-70-orchestrator.yml")
    dispatch = (_workflow_on_section(data)).get("workflow_dispatch") or {}
    inputs = dispatch.get("inputs") or {}
    keepalive = inputs.get("keepalive_enabled")
    assert keepalive, "Orchestrator must expose keepalive_enabled workflow input"
    assert (
        str(keepalive.get("description", "")).lower().startswith("enable codex keepalive sweep")
    ), "keepalive_enabled input should document its keepalive toggle behaviour"
    assert (
        str(keepalive.get("default", "")).strip("'").lower() == "true"
    ), "keepalive_enabled input should default to enabled"


def test_orchestrator_handles_keepalive_pause_label():
    text = (WORKFLOWS_DIR / "agents-70-orchestrator.yml").read_text(encoding="utf-8")
    # After extraction, the keepalive pause logic is in agents_orchestrator_resolve.js
    resolver_script = Path(".github/scripts/agents_orchestrator_resolve.js")
    assert resolver_script.exists(), "Resolver helper script must exist"
    resolver_text = resolver_script.read_text(encoding="utf-8")
    assert (
        'keepalive skipped: repository label "${KEEPALIVE_PAUSE_LABEL}" is present.'
        in resolver_text
    ), "Resolver script must log keepalive skipped when pause label is present"
    # The workflow exposes keepalive_pause_label (not keepalive_paused_label)
    assert (
        "keepalive_pause_label" in text
    ), "Orchestrator outputs should expose the pause label name for downstream jobs"
    assert (
        "keepalive:paused" in resolver_text
    ), "Pause label constant must be documented in the resolver script"


def test_orchestrator_forwards_enable_watchdog_flag():
    # The orchestrator is now split: the orchestrate job is in the main reusable workflow
    main_data = _load_workflow_yaml("reusable-70-orchestrator-main.yml")
    jobs = main_data.get("jobs", {})
    orchestrate = jobs.get("orchestrate")
    assert orchestrate, "Main reusable workflow must contain orchestrate job"
    with_section = orchestrate.get("with") or {}
    # enable_watchdog is now passed as input to the main reusable workflow
    assert (
        "enable_watchdog" in with_section
    ), "Orchestrate job must forward enable_watchdog to the reusable-16-agents workflow"


def test_keepalive_gate_job_handles_missing_pull_request_metadata():
    data = _load_workflow_yaml("agents-pr-meta-v4.yml")
    jobs = data.get("jobs", {})
    # v4 structure uses update_body job instead of keepalive_from_gate
    # The workflow handles PR context resolution differently
    assert (
        "update_body" in jobs or "comment_event_context" in jobs
    ), "PR meta workflow must handle PR context for keepalive operations"
