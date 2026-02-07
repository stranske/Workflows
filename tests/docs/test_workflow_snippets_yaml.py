"""Validate YAML syntax for workflow snippet files."""

from pathlib import Path

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
        assert all(isinstance(item, dict) for item in parsed), (
            f"{snippet_file} should contain a list of step maps"
        )
