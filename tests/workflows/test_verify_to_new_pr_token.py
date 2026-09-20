"""Guard token routing for verifier follow-up issues and dispatches."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(".github/workflows/agents-verify-to-new-pr.yml")
TEMPLATE = Path("templates/consumer-repo/.github/workflows/agents-verify-to-new-pr.yml")
APP_ACTION = "actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1"


def test_app_token_is_scoped_and_template_matches_source():
    assert ROOT.read_bytes() == TEMPLATE.read_bytes()
    workflow = yaml.safe_load(ROOT.read_text(encoding="utf-8"))
    job = workflow["jobs"]["create-new-pr"]
    assert set(job["env"]) == {"HAS_WORKFLOWS_APP_CREDS"}
    steps = {step.get("id"): step for step in job["steps"]}

    mint = steps["app_token"]
    assert mint["uses"] == APP_ACTION
    assert mint["continue-on-error"] is True
    assert mint["with"]["owner"] == "${{ github.repository_owner }}"
    assert mint["with"]["repositories"].splitlines() == [
        "${{ github.event.repository.name }}",
        "Workflows",
    ]
    assert {key: value for key, value in mint["with"].items() if key.startswith("permission-")} == {
        "permission-contents": "read",
        "permission-issues": "write",
        "permission-pull-requests": "write",
        "permission-actions": "write",
    }
    assert job["env"]["HAS_WORKFLOWS_APP_CREDS"].startswith("${{")
    assert "createWorkflowDispatch" in steps["dispatch-autopilot"]["with"]["script"]


@pytest.mark.parametrize(
    ("tokens", "expected_source", "warn"),
    [
        (("app", "owner", "service", "workflow", "success"), "workflows-app", False),
        (("", "owner", "service", "workflow", "skipped"), "owner-pat", False),
        (("", "", "service", "workflow", "skipped"), "service-bot", False),
        (("", "", "", "workflow", "skipped"), "github-token", True),
        (("", "owner", "service", "workflow", "failure"), "owner-pat", True),
    ],
)
def test_token_selection_preserves_dispatch_fallback(tmp_path, tokens, expected_source, warn):
    workflow = yaml.safe_load(ROOT.read_text(encoding="utf-8"))
    select = next(
        step
        for step in workflow["jobs"]["create-new-pr"]["steps"]
        if step.get("id") == "select-token"
    )
    output = tmp_path / "github-output"
    app, owner, service, workflow_token, outcome = tokens
    env = os.environ.copy()
    env.update(
        APP_TOKEN=app,
        APP_TOKEN_OUTCOME=outcome,
        OWNER_PR_PAT=owner,
        SERVICE_BOT_PAT=service,
        GITHUB_TOKEN=workflow_token,
        GITHUB_OUTPUT=str(output),
    )
    result = subprocess.run(
        ["bash", "-e", "-c", select["run"]],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert values == {
        "token": {
            "workflows-app": app,
            "owner-pat": owner,
            "service-bot": service,
            "github-token": workflow_token,
        }[expected_source],
        "source": expected_source,
    }
    assert ("::warning::" in result.stdout) is warn
