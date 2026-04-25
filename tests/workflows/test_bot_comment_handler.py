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
    workflow_call_secrets = (workflow.get("on") or workflow.get(True))["workflow_call"]["secrets"]
    collect_steps = workflow["jobs"]["collect"]["steps"]
    detect_step = next(
        step for step in collect_steps if step.get("name") == "Detect App credentials"
    )
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
    assert detect_step["env"]["GH_APP_CLIENT_ID"] == "${{ secrets.gh_app_client_id }}"
    assert detect_step["env"]["GH_APP_PRIVATE_KEY"] == "${{ secrets.gh_app_private_key }}"
    assert client_step.get("if") == "steps.app-creds.outputs.use_client == 'true'"
    assert "client-id" in client_step.get("with", {})
    assert "app-id" not in client_step.get("with", {})
    assert legacy_step.get("if") == "steps.app-creds.outputs.use_legacy == 'true'"
    assert "app-id" in legacy_step.get("with", {})
    assert (
        "steps.token-client.outputs.token || steps.token-legacy.outputs.token"
        in resolve_step["env"]["TOKEN_OUTPUT"]
    )


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
