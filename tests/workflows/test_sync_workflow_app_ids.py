"""Keep numeric App IDs distinct from client IDs in synced token actions."""

import re
from pathlib import Path

import pytest
import yaml

WORKFLOW_NAMES = (
    "agents-71-codex-belt-dispatcher.yml",
    "agents-72-codex-belt-worker.yml",
    "agents-73-codex-belt-conveyor.yml",
    "agents-81-gate-followups.yml",
    "agents-auto-pilot.yml",
    "agents-autofix-dispatcher.yml",
    "agents-guard.yml",
    "agents-issue-optimizer.yml",
    "agents-keepalive-loop-reporter.yml",
    "agents-weekly-metrics.yml",
    "maint-coverage-guard.yml",
    "reusable-pr-context.yml",
)
TEMPLATE_ROOT = Path("templates/consumer-repo/.github/workflows")
SOURCE_ROOT = Path(".github/workflows")
NUMERIC_APP_ID = re.compile(r"\b(?:WORKFLOWS|KEEPALIVE)_APP_ID\b")


def _assert_app_id_inputs(path: Path) -> int:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    numeric_inputs = 0
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if not step.get("uses", "").startswith("actions/create-github-app-token@"):
                continue
            inputs = step.get("with", {})
            client_id = str(inputs.get("client-id", ""))
            assert not NUMERIC_APP_ID.search(client_id), (
                f"{path}: {step.get('id', step.get('name'))} passes a numeric "
                f"App ID through client-id: {client_id}"
            )
            if NUMERIC_APP_ID.search(str(inputs.get("app-id", ""))):
                numeric_inputs += 1
                assert "client-id" not in inputs, f"{path}: ambiguous App identity inputs"
                assert inputs.get("private-key"), f"{path}: missing App private key"
    return numeric_inputs


@pytest.mark.parametrize("name", WORKFLOW_NAMES)
def test_consumer_token_actions_use_numeric_app_id_input(name: str) -> None:
    """Each affected template must retain its existing numeric-ID token path."""
    assert _assert_app_id_inputs(TEMPLATE_ROOT / name) > 0


@pytest.mark.parametrize("name", [name for name in WORKFLOW_NAMES if (SOURCE_ROOT / name).exists()])
def test_source_token_actions_do_not_mislabel_numeric_app_ids(name: str) -> None:
    # Some root workflows already use explicit CLIENT_ID credentials; preserve them.
    _assert_app_id_inputs(SOURCE_ROOT / name)
