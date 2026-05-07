from __future__ import annotations

import json
from pathlib import Path

from scripts import reusable_ci_scope


def test_full_matrix_when_no_scope_info() -> None:
    full = {"include": [{"name": "minimal"}, {"name": "full"}]}

    selected = reusable_ci_scope.select_scenarios(
        "selftest-reusable-ci",
        ["tests/test_example.py"],
        full,
        reusable_ci_scope.SelectionOptions(),
    )

    assert selected.matrix == full
    assert selected.selected_count == 2
    assert selected.reason == "no reusable CI scope metadata was provided"


def test_reduced_matrix_when_scope_detected() -> None:
    full = {
        "include": [
            {"name": "tests", "scope": {"paths": ["tests/**"]}},
            {"name": "docs", "scope": {"paths": ["docs/**"]}},
            {"name": "workflow", "scope_paths": [".github/workflows/**"]},
        ]
    }

    selected = reusable_ci_scope.select_scenarios(
        "selftest-reusable-ci",
        ["tests/test_reusable_ci_scope.py"],
        full,
        reusable_ci_scope.SelectionOptions(),
    )

    assert selected.matrix == {"include": [{"name": "tests"}]}
    assert selected.selected_count == 1
    assert selected.total_count == 3


def test_globstar_scope_matches_root_python_file() -> None:
    full = {"include": [{"name": "coverage", "scope": {"paths": ["**/*.py"]}}]}

    selected = reusable_ci_scope.select_scenarios(
        "maint-coverage-guard",
        ["main.py"],
        full,
        reusable_ci_scope.SelectionOptions(),
    )

    assert selected.matrix == {"include": [{"name": "coverage"}]}
    assert selected.selected_count == 1


def test_force_full_override_returns_full_matrix() -> None:
    full = {
        "include": [
            {"name": "tests", "scope": {"paths": ["tests/**"]}},
            {"name": "docs", "scope": {"paths": ["docs/**"]}},
        ]
    }

    selected = reusable_ci_scope.select_scenarios(
        "selftest-reusable-ci",
        ["docs/readme.md"],
        full,
        reusable_ci_scope.SelectionOptions(force_full=True),
    )

    assert selected.matrix == {"include": [{"name": "tests"}, {"name": "docs"}]}
    assert selected.force_full is True
    assert selected.selected_count == 2


def test_describe_selection_is_human_readable() -> None:
    full = {
        "include": [
            {"name": "tests", "scope": {"paths": ["tests/**"]}},
            {"name": "scripts", "scope": {"paths": ["scripts/**"]}},
            {"name": "docs", "scope": {"paths": ["docs/**"]}},
        ]
    }

    selected = reusable_ci_scope.select_scenarios(
        "reusable-10-ci-python",
        ["tests/test_reusable_ci_scope.py"],
        full,
        reusable_ci_scope.SelectionOptions(),
    )

    rationale = reusable_ci_scope.describe_selection(selected, full)

    assert rationale == "running 1/3 scenarios because only `tests/` changed"


def test_cli_outputs_matrix_and_rationale(capsys) -> None:
    full = {
        "include": [
            {"name": "tests", "scope": {"paths": ["tests/**"]}},
            {"name": "docs", "scope": {"paths": ["docs/**"]}},
        ]
    }

    exit_code = reusable_ci_scope.main(
        [
            "--workflow-name",
            "selftest-reusable-ci",
            "--changed-files-json",
            json.dumps(["tests/test_example.py"]),
            "--matrix-json",
            json.dumps(full),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["matrix"] == {"include": [{"name": "tests"}]}
    assert payload["rationale"] == "running 1/2 scenarios because only `tests/` changed"


def test_github_outputs_use_multiline_format(tmp_path: Path) -> None:
    output_path = tmp_path / "outputs.txt"

    reusable_ci_scope._write_github_outputs(
        str(output_path),
        {"rationale": "first line\nsecond=line%"},
    )

    assert output_path.read_text(encoding="utf-8") == (
        "rationale<<__REUSABLE_CI_SCOPE_RATIONALE__\n"
        "first line\nsecond=line%\n"
        "__REUSABLE_CI_SCOPE_RATIONALE__\n"
    )
