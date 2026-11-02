"""Maint 39 must honor the configured provider retirement on real dispatch input."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/maint-39-test-llm-providers.yml"


def test_maint39_does_not_reference_retired_github_models_provider() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text())
    events = workflow.get("on", workflow.get(True))
    provider = events["workflow_dispatch"]["inputs"]["provider"]
    assert provider["default"] == "all"
    assert "github-models" not in provider["options"]
    steps = workflow["jobs"]["test-providers"]["steps"]
    assert not any(step["name"] == "Test GitHub Models" for step in steps)
    assert not any("github-models" in step.get("run", "") for step in steps)
    assert "models" not in workflow["permissions"]
    assert any(step["name"] == "Test OpenAI" for step in steps)


def test_maint39_availability_smoke_uses_current_provider_registry(capsys) -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text())
    step = next(
        step
        for step in workflow["jobs"]["test-providers"]["steps"]
        if step["name"] == "Check provider availability"
    )
    # Run the actual workflow's read-only availability check; no paid analysis.
    source = step["run"].split('python -c "', 1)[1].rsplit('"', 1)[0]
    exec(source, {})
    assert "Provider availability:" in capsys.readouterr().out
