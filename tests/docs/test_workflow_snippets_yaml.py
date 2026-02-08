"""Validate YAML syntax for workflow snippet files."""

from pathlib import Path

import pytest
import yaml


def test_workflow_snippets_are_valid_yaml() -> None:
    snippets_dir = Path("docs/workflow-snippets")
    snippet_files = sorted(snippets_dir.glob("*.yml"))

    assert snippet_files, "Expected workflow snippet YAML files to exist"

    for snippet_file in snippet_files:
        contents = snippet_file.read_text(encoding="utf-8")
        parsed = yaml.safe_load(contents)

        assert parsed is not None, f"{snippet_file} parsed to None"
        assert isinstance(parsed, list), f"{snippet_file} should contain a YAML list"
        assert all(
            isinstance(item, dict) for item in parsed
        ), f"{snippet_file} should contain a list of step maps"


def test_pip_cache_step_uses_requirements_llm_hash() -> None:
    snippet_path = Path("docs/workflow-snippets/pip-cache-step.yml")
    contents = snippet_path.read_text(encoding="utf-8")
    expected = (
        "pip-${{ runner.os }}-${{ matrix.python-version }}-"
        "${{ hashFiles('tools/requirements-llm.txt') }}"
    )
    assert expected in contents
    parsed = yaml.safe_load(contents)

    assert isinstance(parsed, list), "Expected pip-cache snippet to be a list"
    assert any(
        isinstance(step, dict)
        and isinstance(step.get("with"), dict)
        and step["with"].get("key") == expected
        for step in parsed
    ), "Expected a cache step key matching the requirements hash"


@pytest.mark.parametrize(
    "snippet_path",
    [
        Path("docs/workflow-snippets/agents-auto-pilot-install.yml"),
        Path("docs/workflow-snippets/reusable-agents-verifier-install.yml"),
        Path("docs/workflow-snippets/agents-verify-to-new-pr-install.yml"),
    ],
)
def test_install_snippets_reference_requirements_llm(snippet_path: Path) -> None:
    contents = snippet_path.read_text(encoding="utf-8")
    assert "tools/requirements-llm.txt" in contents
    assert ".workflows-lib/tools/requirements-llm.txt" not in contents

    parsed = yaml.safe_load(contents)
    assert isinstance(parsed, list), f"{snippet_path} should contain a YAML list"
    assert any(
        isinstance(step, dict)
        and isinstance(step.get("run"), str)
        and any(
            line.strip() == "pip install -r tools/requirements-llm.txt"
            for line in step["run"].splitlines()
        )
        for step in parsed
    ), "Expected install snippet to include pip install for tools/requirements-llm.txt"


def test_pip_freeze_step_runs_python_module() -> None:
    snippet_path = Path("docs/workflow-snippets/pip-freeze-step.yml")
    parsed = yaml.safe_load(snippet_path.read_text(encoding="utf-8"))

    assert isinstance(parsed, list), "Expected pip-freeze snippet to be a list"
    assert any(
        isinstance(step, dict)
        and isinstance(step.get("run"), str)
        and [line.strip() for line in step["run"].splitlines() if line.strip()]
        == ["python -m pip freeze"]
        for step in parsed
    ), "Expected a step with run command 'python -m pip freeze'"


def test_pip_freeze_step_contains_python_module_command() -> None:
    snippet_path = Path("docs/workflow-snippets/pip-freeze-step.yml")
    contents = snippet_path.read_text(encoding="utf-8")

    assert "python -m pip freeze" in contents
