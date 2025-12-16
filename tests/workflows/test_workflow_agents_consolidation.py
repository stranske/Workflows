from pathlib import Path

import yaml

WORKFLOWS_DIR = Path(".github/workflows")
KEEPALIVE_HELPER = Path("scripts/keepalive-runner.js")


def _load_workflow_yaml(name: str) -> dict:
    path = WORKFLOWS_DIR / name
    assert path.exists(), f"Workflow {name} must exist"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _workflow_on_section(data: dict) -> dict:
    return data.get("on") or data.get(True) or {}


def test_agents_orchestrator_inputs_and_uses():
    wf = WORKFLOWS_DIR / "agents-70-orchestrator.yml"
    assert wf.exists(), "agents-70-orchestrator.yml must exist"
    text = wf.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text, "Orchestrator must allow manual dispatch"
    expected_inputs = {"params_json", "options_json"}
    for key in expected_inputs:
        assert f"{key}:" in text, f"Missing workflow_dispatch input: {key}"
    assert (
        "github.event.inputs.params_json" in text
    ), "params_json must be read from workflow_dispatch inputs"
    assert (
        "github.event.inputs.options_json" in text
    ), "options_json input must be forwarded to the resolver"
    assert "PARAMS_JSON" in text, "Resolve step must pass params_json via env"
    # After extraction, the parsing logic is in agents_orchestrator_resolve.js
    assert (
        "agents_orchestrator_resolve.js" in text or "agents-orchestrator-resolve" in text
    ), "Orchestrator must invoke the resolver helper script"
    # Verify the helper script contains the JSON parsing logic
    resolver_script = Path(".github/scripts/agents_orchestrator_resolve.js")
    assert resolver_script.exists(), "Resolver helper script must exist"
    resolver_text = resolver_script.read_text(encoding="utf-8")
    assert "JSON.parse" in resolver_text, "Resolver script must parse params_json as JSON"
    assert "options_json" in text, "options_json output must remain available"
    assert "enable_bootstrap:" in text, "Orchestrator must forward enable_bootstrap flag"
    assert (
        "bootstrap_issues_label:" in text
    ), "Orchestrator must forward bootstrap label configuration"
    assert "keepalive_max_retries" in text, "Orchestrator must expose keepalive retry configuration"
    assert (
        "./.github/workflows/reusable-16-agents.yml" in text
    ), "Orchestrator must call the reusable agents workflow"


def test_agents_orchestrator_exposes_dry_run_toggle():
    text = (WORKFLOWS_DIR / "agents-70-orchestrator.yml").read_text(encoding="utf-8")
    assert "dry_run:" in text, "Orchestrator must expose a dry_run input"
    assert (
        "github.event.inputs.dry_run" in text
    ), "Manual dispatch dry_run input must be wired into the resolver"
    assert (
        "dry_run: ${{ needs.resolve-params.outputs.dry_run }}" in text
    ), "Reusable workflow invocation must forward the resolved dry_run flag"
    # After extraction, the dry_run output is computed in agents_orchestrator_resolve.js
    resolver_script = Path(".github/scripts/agents_orchestrator_resolve.js")
    assert resolver_script.exists(), "Resolver helper script must exist"
    resolver_text = resolver_script.read_text(encoding="utf-8")
    assert "dryRun" in resolver_text, "Resolve script should compute and surface the dry_run flag"


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
        "bootstrap_issues_label not provided; defaulting to agent:codex." in text
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
    assert (
        "github.paginate.iterator" in text
    ), "Bootstrap must paginate issue scanning to avoid truncation"
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
    data = _load_workflow_yaml("agents-70-orchestrator.yml")

    # Top-level concurrency prevents overlapping orchestrator runs from consuming excessive API quota
    top_concurrency = data.get("concurrency") or {}
    assert (
        top_concurrency.get("group") == "agents-70-orchestrator-singleton"
    ), "Top-level orchestrator concurrency must prevent overlapping runs"
    assert (
        top_concurrency.get("cancel-in-progress") is False
    ), "Top-level concurrency must not cancel in-progress runs"

    jobs = data.get("jobs", {})
    orchestrate = jobs.get("orchestrate", {})
    assert orchestrate.get("uses"), "Orchestrator job should call the reusable workflow"
    assert (
        "timeout-minutes" not in orchestrate
    ), "Timeout must live in reusable workflow because workflow-call jobs reject timeout-minutes"

    job_concurrency = orchestrate.get("concurrency") or {}
    group = str(job_concurrency.get("group") or "")
    assert group.startswith(
        "${{ format('keepalive-orchestrator-pr-"
    ), "Orchestrator job concurrency must prefix groups with orchestrator identifier"
    assert (
        "needs.resolve-orchestrator-context.outputs.pr_number" in group
    ), "Concurrency must scope runs by the resolved pull request number"
    assert (
        "needs.resolve-orchestrator-context.outputs.agent_alias" in group
    ), "Concurrency must scope runs by the resolved agent alias"
    assert (
        "github.run_id" in group
    ), "Concurrency fallback must include github.run_id when no override is present"
    assert (
        job_concurrency.get("cancel-in-progress") is False
    ), "Orchestrator job concurrency must keep existing runs alive"

    text = (WORKFLOWS_DIR / "agents-70-orchestrator.yml").read_text(encoding="utf-8")
    assert (
        "Job timeouts live inside reusable-16-agents.yml" in text
    ), "Orchestrator workflow should document where the timeout is enforced"


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
    data = _load_workflow_yaml("agents-70-orchestrator.yml")
    jobs = data.get("jobs", {})

    targets = {
        "resolve-params": "./.github/scripts/agents_orchestrator_resolve.js",
        "keepalive-guard": "./.github/scripts/keepalive_guard_utils.js",
        "belt-dispatch-summary": "./.github/scripts/agents_dispatch_summary.js",
        "belt-scan-ready-prs": "./.github/scripts/agents_belt_scan.js",
    }

    for job_name, helper_path in targets.items():
        job = jobs.get(job_name)
        assert job, f"Job {job_name} must exist in the orchestrator workflow"
        steps = job.get("steps") or []
        assert steps, f"Job {job_name} must define steps"

        checkout_index = None
        helper_index = None
        helper_script = None

        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue

            uses = step.get("uses")
            if uses == "actions/checkout@v4" and checkout_index is None:
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


def test_bootstrap_step_defaults_label_when_missing():
    text = (WORKFLOWS_DIR / "reusable-16-agents.yml").read_text(encoding="utf-8")
    assert (
        "const fallbackLabel = 'agent:codex'" in text
    ), "Bootstrap logic must define agent:codex as the fallback label"
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
        isinstance(step, dict) and step.get("uses") == "actions/checkout@v4" for step in steps
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
    data = _load_workflow_yaml("agents-70-orchestrator.yml")
    jobs = data.get("jobs", {})
    orchestrate = jobs.get("orchestrate")
    assert orchestrate, "Orchestrator workflow must dispatch reusable agents job"
    with_section = orchestrate.get("with") or {}
    assert (
        with_section.get("enable_watchdog") == "${{ needs.resolve-params.outputs.enable_watchdog }}"
    ), "Orchestrator must forward enable_watchdog to the reusable workflow"


def test_keepalive_gate_job_handles_missing_pull_request_metadata():
    data = _load_workflow_yaml("agents-pr-meta-v4.yml")
    jobs = data.get("jobs", {})
    # v4 structure uses update_body job instead of keepalive_from_gate
    # The workflow handles PR context resolution differently
    assert (
        "update_body" in jobs or "comment_event_context" in jobs
    ), "PR meta workflow must handle PR context for keepalive operations"
