"""Maint 39 must honor the configured provider retirement on real dispatch input."""

import ast
from pathlib import Path

import pytest
import yaml
from tools.llm_provider import check_providers

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/maint-39-test-llm-providers.yml"


def test_maint39_does_not_reference_retired_github_models_provider() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text())
    events = workflow.get("on", workflow.get(True))
    provider = events["workflow_dispatch"]["inputs"]["provider"]
    assert provider["default"] == "all"
    assert "github-models" not in provider["options"], "retired GitHub Models dispatch option"
    steps = workflow["jobs"]["test-providers"]["steps"]
    assert not any(
        step.get("name") == "Test GitHub Models" for step in steps
    ), "retired GitHub Models job step"
    assert not any("github-models" in step.get("run", "") for step in steps)
    assert "models" not in workflow["permissions"]
    assert any(step["name"] == "Test OpenAI" for step in steps)


@pytest.mark.parametrize(
    ("regression", "expected_failure"),
    [
        ("dispatch-option", "retired GitHub Models dispatch option"),
        ("job-step", "retired GitHub Models job step"),
        ("both", "retired GitHub Models dispatch option"),
    ],
)
def test_maint39_rejects_reintroduced_github_models_provider(
    regression: str, expected_failure: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_path = WORKFLOW
    original_source = original_path.read_text()
    workflow = yaml.safe_load(original_source)
    events = workflow.get("on", workflow.get(True))
    # Keep only the fields under test; do not copy credential environment mappings
    # or executable provider commands into the temporary regression fixture.
    candidate = {
        "on": events,
        "permissions": workflow["permissions"],
        "jobs": {
            "test-providers": {
                "steps": [
                    {"name": step["name"]} for step in workflow["jobs"]["test-providers"]["steps"]
                ]
            }
        },
    }
    candidate_path = tmp_path / original_path.name
    clean_source = yaml.safe_dump(candidate)
    candidate_path.write_text(clean_source)

    with monkeypatch.context() as patch:
        patch.setitem(globals(), "WORKFLOW", candidate_path)
        # Establish that the sanitized fixture passes before introducing a regression.
        test_maint39_does_not_reference_retired_github_models_provider()
        options = events["workflow_dispatch"]["inputs"]["provider"]["options"]
        if regression in {"dispatch-option", "both"}:
            options.append("github-models")
        if regression in {"job-step", "both"}:
            candidate["jobs"]["test-providers"]["steps"].append({"name": "Test GitHub Models"})
        candidate_path.write_text(yaml.safe_dump(candidate))
        with pytest.raises(AssertionError, match=expected_failure):
            test_maint39_does_not_reference_retired_github_models_provider()

        if regression == "both":
            # The first assertion must not conceal a surviving retired job step.
            options.remove("github-models")
            candidate_path.write_text(yaml.safe_dump(candidate))
            with pytest.raises(AssertionError, match="retired GitHub Models job step"):
                test_maint39_does_not_reference_retired_github_models_provider()

        candidate_path.write_text(clean_source)
        test_maint39_does_not_reference_retired_github_models_provider()

    # Restore the real workflow and prove the same named test passes unchanged.
    assert original_path == WORKFLOW
    assert original_path.read_text() == original_source
    test_maint39_does_not_reference_retired_github_models_provider()


def test_maint39_availability_smoke_uses_current_provider_registry() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text())
    step = next(
        step
        for step in workflow["jobs"]["test-providers"]["steps"]
        if step["name"] == "Check provider availability"
    )
    # Inspect the actual workflow snippet without executing YAML-supplied code.
    source = step["run"].split('python -c "', 1)[1].rsplit('"', 1)[0]
    tree = ast.parse(source)
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "tools.llm_provider"
        and any(alias.name == "check_providers" and alias.asname is None for alias in node.names)
        for node in ast.walk(tree)
    )
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "check_providers"
        and not node.args
        and not node.keywords
        for node in ast.walk(tree)
    )
    availability = check_providers()
    assert {"openai", "anthropic", "regex-fallback"} <= availability.keys()
    assert availability["regex-fallback"] is True
