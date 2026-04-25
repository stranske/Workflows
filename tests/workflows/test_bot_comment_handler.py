from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def test_reusable_bot_comment_handler_ignores_agents_paths() -> None:
    workflow = _load_yaml(ROOT / ".github/workflows/reusable-bot-comment-handler.yml")
    triggers = workflow.get("on") or workflow.get(True) or {}
    inputs = triggers.get("workflow_call", {}).get("inputs", {})

    ignored_paths = inputs.get("ignored_paths", {}).get("default")
    assert ignored_paths is not None
    assert ".agents/" in ignored_paths.split(",")

    bot_authors = inputs.get("bot_authors", {}).get("default", "")
    assert "chatgpt-codex-connector[bot]" in bot_authors


def test_reusable_bot_comment_handler_has_manual_terminal_probe() -> None:
    workflow = _load_yaml(ROOT / ".github/workflows/reusable-bot-comment-handler.yml")
    triggers = workflow.get("on") or workflow.get(True) or {}
    call_inputs = triggers.get("workflow_call", {}).get("inputs", {})
    dispatch_inputs = triggers.get("workflow_dispatch", {}).get("inputs", {})

    for name in (
        "pr_number",
        "dry_run",
        "bot_authors",
        "skip_if_human_replied",
        "ignored_paths",
    ):
        assert name in dispatch_inputs, f"workflow_dispatch must expose {name}"
        assert name in call_inputs, f"workflow_call must expose {name}"

    assert dispatch_inputs["pr_number"].get("required") is True
    assert dispatch_inputs["dry_run"].get("default") is True
    assert dispatch_inputs["ignored_paths"].get("default") == call_inputs["ignored_paths"].get(
        "default"
    )


def test_reusable_bot_comment_handler_uploads_terminal_disposition_artifact() -> None:
    workflow = _load_yaml(ROOT / ".github/workflows/reusable-bot-comment-handler.yml")
    collect_steps = workflow["jobs"]["collect"]["steps"]
    upload_step = next(
        step
        for step in collect_steps
        if step.get("name") == "Upload review-thread disposition artifact"
    )
    upload_with = upload_step.get("with", {})

    assert upload_step.get("if") == "always()"
    assert upload_step.get("uses") == "actions/upload-artifact@v7"
    assert upload_with.get("name") == "review-thread-terminal-disposition-${{ github.run_id }}"
    assert "agent-metrics/review-thread-terminal-disposition.ndjson" in upload_with.get("path", "")
    assert upload_with.get("if-no-files-found") == "ignore"
    assert upload_with.get("retention-days") == 14


def test_reusable_bot_comment_handler_prefers_app_client_id() -> None:
    workflow = _load_yaml(ROOT / ".github/workflows/reusable-bot-comment-handler.yml")
    workflow_call = (workflow.get("on") or workflow.get(True))["workflow_call"]
    workflow_call_secrets = workflow_call["secrets"]
    collect_steps = workflow["jobs"]["collect"]["steps"]
    dispatch_steps = workflow["jobs"]["dispatch"]["steps"]
    detect_steps = [
        next(step for step in steps if step.get("name") == "Detect App credentials")
        for steps in (collect_steps, dispatch_steps)
    ]
    detect_step = detect_steps[0]
    client_step = next(
        step
        for step in collect_steps
        if step.get("name") == "Generate token (if App client ID configured)"
    )
    legacy_step = next(
        step
        for step in collect_steps
        if step.get("name") == "Generate token (if legacy App ID configured)"
    )
    resolve_step = next(step for step in collect_steps if step.get("name") == "Resolve token")

    assert "gh_app_client_id" in workflow_call_secrets
    assert "prefer gh_app_client_id" in workflow_call_secrets["gh_app_id"]["description"]
    assert workflow_call["outputs"]["app_auth_mode"]["value"] == (
        "${{ jobs.collect.outputs.app_auth_mode }}"
    )
    assert workflow["jobs"]["collect"]["outputs"]["app_auth_mode"] == (
        "${{ steps.app-creds.outputs.app_auth_mode }}"
    )
    assert detect_step["env"]["GH_APP_CLIENT_ID"] == "${{ secrets.gh_app_client_id }}"
    assert detect_step["env"]["GH_APP_PRIVATE_KEY"] == "${{ secrets.gh_app_private_key }}"
    for detect_step in detect_steps:
        detect_script = detect_step["run"]
        assert detect_step["env"]["GH_APP_CLIENT_ID"] == "${{ secrets.gh_app_client_id }}"
        assert detect_step["env"]["GH_APP_PRIVATE_KEY"] == "${{ secrets.gh_app_private_key }}"
        assert "client_id_configured=true" in detect_script
        assert "legacy_app_id_configured=true" in detect_script
        assert "private_key_configured=true" in detect_script
        assert "app_auth_mode=client-id" in detect_script
        assert "app_auth_mode=legacy-app-id" in detect_script
        assert "app_auth_mode=none" in detect_script
        assert "Legacy GitHub App ID fallback" in detect_script
    assert client_step.get("if") == "steps.app-creds.outputs.use_client == 'true'"
    assert "client-id" in client_step.get("with", {})
    assert "app-id" not in client_step.get("with", {})
    assert legacy_step.get("if") == "steps.app-creds.outputs.use_legacy == 'true'"
    assert "app-id" in legacy_step.get("with", {})
    assert (
        "steps.token-client.outputs.token || steps.token-legacy.outputs.token"
        in resolve_step["env"]["TOKEN_OUTPUT"]
    )


def test_reusable_bot_comment_handler_uploads_auth_coverage_artifact() -> None:
    workflow = _load_yaml(ROOT / ".github/workflows/reusable-bot-comment-handler.yml")
    collect_steps = workflow["jobs"]["collect"]["steps"]
    write_step = next(
        step for step in collect_steps if step.get("name") == "Write App auth coverage"
    )
    upload_step = next(
        step for step in collect_steps if step.get("name") == "Upload App auth coverage"
    )

    assert write_step.get("if") == "always()"
    assert write_step["env"]["APP_AUTH_MODE"] == "${{ steps.app-creds.outputs.app_auth_mode }}"
    assert "workflows-bot-comment-auth-coverage/v1" in write_step["run"]
    assert "client_id_configured" in write_step["run"]
    assert "fallback_warning_active" in write_step["run"]
    assert upload_step.get("if") == "always()"
    assert upload_step.get("uses") == "actions/upload-artifact@v7"
    assert upload_step["with"]["name"] == "bot-comment-auth-coverage-reusable-${{ github.run_id }}"
    assert upload_step["with"]["path"] == "bot-comment-auth-coverage/reusable.json"
    assert upload_step["with"]["if-no-files-found"] == "error"


def test_bot_comment_handler_callers_pass_app_client_id() -> None:
    caller_paths = {
        ROOT
        / ".github/workflows/agents-bot-comment-handler.yml": {
            "gh_app_client_id": "${{ secrets.WORKFLOWS_APP_CLIENT_ID }}",
            "gh_app_id": "${{ secrets.WORKFLOWS_APP_ID }}",
            "gh_app_private_key": "${{ secrets.WORKFLOWS_APP_PRIVATE_KEY }}",
        },
        ROOT
        / "templates/consumer-repo/.github/workflows/agents-80-pr-event-hub.yml": {
            "gh_app_client_id": "${{ secrets.GH_APP_CLIENT_ID }}",
            "gh_app_id": "${{ secrets.GH_APP_ID }}",
            "gh_app_private_key": "${{ secrets.GH_APP_PRIVATE_KEY }}",
        },
        ROOT
        / "templates/consumer-repo/.github/workflows/agents-bot-comment-handler.yml": {
            "gh_app_client_id": "${{ secrets.GH_APP_CLIENT_ID }}",
            "gh_app_id": "${{ secrets.GH_APP_ID }}",
            "gh_app_private_key": "${{ secrets.GH_APP_PRIVATE_KEY }}",
        },
    }

    for caller_path, expected_secrets in caller_paths.items():
        workflow = _load_yaml(caller_path)
        reusable_jobs = [
            job
            for job in workflow.get("jobs", {}).values()
            if job.get("uses")
            == "stranske/Workflows/.github/workflows/reusable-bot-comment-handler.yml@main"
        ]
        assert reusable_jobs, f"{caller_path} must call reusable-bot-comment-handler"

        for job in reusable_jobs:
            secrets = job.get("secrets", {})
            assert secrets.get("gh_app_client_id") == expected_secrets["gh_app_client_id"]
            assert secrets.get("gh_app_id") == expected_secrets["gh_app_id"]
            assert secrets.get("gh_app_private_key") == expected_secrets["gh_app_private_key"]


def test_canonical_bot_comment_handler_direct_app_tokens_prefer_client_id() -> None:
    workflow = _load_yaml(ROOT / ".github/workflows/agents-bot-comment-handler.yml")
    resolve_job = workflow["jobs"]["resolve"]

    assert resolve_job["outputs"]["workflow_app_auth_mode"] == (
        "${{ steps.workflow-app-creds.outputs.workflow_app_auth_mode }}"
    )

    for job_name in ("resolve", "cleanup"):
        steps = workflow["jobs"][job_name]["steps"]
        detect_step = next(
            step for step in steps if step.get("name") == "Detect workflow App credentials"
        )
        client_step = next(
            step for step in steps if step.get("name") == "Mint GitHub App Token (client ID)"
        )
        legacy_step = next(
            step for step in steps if step.get("name") == "Mint GitHub App Token (legacy App ID)"
        )
        checkout_step = next(step for step in steps if step.get("uses") == "actions/checkout@v6")

        assert detect_step["env"]["WORKFLOWS_APP_CLIENT_ID"] == (
            "${{ secrets.WORKFLOWS_APP_CLIENT_ID }}"
        )
        assert "client_id_configured=true" in detect_step["run"]
        assert "legacy_app_id_configured=true" in detect_step["run"]
        assert "private_key_configured=true" in detect_step["run"]
        assert "workflow_app_auth_mode=client-id" in detect_step["run"]
        assert "workflow_app_auth_mode=legacy-app-id" in detect_step["run"]
        assert "workflow_app_auth_mode=none" in detect_step["run"]
        assert "Legacy Workflows App ID fallback" in detect_step["run"]
        assert client_step.get("if") == "steps.workflow-app-creds.outputs.use_client == 'true'"
        assert "client-id" in client_step.get("with", {})
        assert "app-id" not in client_step.get("with", {})
        assert legacy_step.get("if") == "steps.workflow-app-creds.outputs.use_legacy == 'true'"
        assert "app-id" in legacy_step.get("with", {})
        assert (
            "steps.app_token_client.outputs.token || steps.app_token_legacy.outputs.token"
            in checkout_step["with"]["token"]
        )

    serialized_workflow = yaml.safe_dump(workflow)
    assert "steps.app_token.outputs.token" not in serialized_workflow


def test_canonical_bot_comment_handler_uploads_wrapper_auth_coverage_artifact() -> None:
    workflow = _load_yaml(ROOT / ".github/workflows/agents-bot-comment-handler.yml")
    resolve_steps = workflow["jobs"]["resolve"]["steps"]
    write_step = next(
        step for step in resolve_steps if step.get("name") == "Write wrapper App auth coverage"
    )
    upload_step = next(
        step for step in resolve_steps if step.get("name") == "Upload wrapper App auth coverage"
    )

    assert write_step.get("if") == "always()"
    assert write_step["env"]["WORKFLOW_APP_AUTH_MODE"] == (
        "${{ steps.workflow-app-creds.outputs.workflow_app_auth_mode }}"
    )
    assert "workflows-bot-comment-auth-coverage/v1" in write_step["run"]
    assert "agents-bot-comment-handler-wrapper" in write_step["run"]
    assert "direct_jobs_covered" in write_step["run"]
    assert upload_step.get("if") == "always()"
    assert upload_step.get("uses") == "actions/upload-artifact@v7"
    assert upload_step["with"]["name"] == "bot-comment-auth-coverage-wrapper-${{ github.run_id }}"
    assert upload_step["with"]["path"] == "bot-comment-auth-coverage/wrapper.json"
    assert upload_step["with"]["if-no-files-found"] == "error"


def test_template_bot_comment_handler_passes_agents_ignore() -> None:
    workflow = _load_yaml(
        ROOT / "templates/consumer-repo/.github/workflows/agents-bot-comment-handler.yml"
    )
    handle_job = workflow.get("jobs", {}).get("handle", {})
    inputs = handle_job.get("with", {})
    ignored_paths = inputs.get("ignored_paths", "")

    assert ".agents/" in ignored_paths.split(",")


def test_template_bot_comment_handler_dismisses_ignored_reviews() -> None:
    workflow = _load_yaml(
        ROOT / "templates/consumer-repo/.github/workflows/agents-bot-comment-handler.yml"
    )
    dismiss_job = workflow.get("jobs", {}).get("dismiss_ignored", {})
    assert dismiss_job, "dismiss_ignored job is missing"

    steps = dismiss_job.get("steps", [])
    github_script_steps = [
        step for step in steps if step.get("uses", "").startswith("actions/github-script")
    ]
    assert github_script_steps, "dismiss_ignored job should run actions/github-script"

    script = github_script_steps[-1].get("with", {}).get("script", "")
    assert "dismissReview" in script
