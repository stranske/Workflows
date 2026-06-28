import sys
from pathlib import Path

import pytest
from scripts import validate_workflow_yaml as validator


def _write_workflow(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_line_length_allows_pinned_setup_api_client_reference(tmp_path: Path) -> None:
    workflow = _write_workflow(
        tmp_path / "line-length.yml",
        [
            "name: Line length",
            ("      uses: stranske/Workflows/.github/actions/setup-api-client@" + "a" * 80),
            "      run: echo " + "x" * 110,
        ],
    )

    issues = validator.check_line_length(workflow)

    assert issues == [(3, "Line exceeds 100 characters")]


def test_runs_on_placement_flags_inline_mapping(tmp_path: Path) -> None:
    workflow = _write_workflow(
        tmp_path / "bad-runs-on.yml",
        [
            "jobs:",
            "  build: { runs-on: ubuntu-latest, steps: [] }",
        ],
    )

    issues = validator.check_runs_on_placement(workflow)

    assert issues == [
        (2, "runs-on should be on its own line (found text before it)"),
    ]


def test_long_single_line_if_requires_multiline_condition(tmp_path: Path) -> None:
    workflow = _write_workflow(
        tmp_path / "long-if.yml",
        [
            "jobs:",
            "  build:",
            (
                "    if: ${{ github.event_name == 'pull_request' && "
                "github.actor != 'dependabot[bot]' && "
                "contains(github.event.pull_request.labels.*.name, 'agent:codex') }}"
            ),
            "    runs-on: ubuntu-latest",
        ],
    )

    issues = validator.check_multiline_conditions(workflow)

    assert issues == [
        (3, "Very long 'if' condition should use multiline format (| or >)"),
    ]


def test_legacy_workflow_is_skipped_unless_no_skip_is_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = _write_workflow(
        tmp_path / "agents-71-codex-belt-dispatcher.yml",
        [
            "name: Legacy",
            "on: push",
            "jobs:",
            "  build:",
            "    runs-on: ubuntu-latest",
            "    steps:",
            "      - run: echo " + "x" * 120,
        ],
    )

    monkeypatch.setattr(sys, "argv", ["validate_workflow_yaml.py", str(workflow), "--verbose"])
    with pytest.raises(SystemExit) as skipped:
        validator.main()

    assert skipped.value.code == 0
    skipped_output = capsys.readouterr().out
    assert "Skipped (known legacy workflow)" in skipped_output
    assert "legacy workflow(s) skipped" in skipped_output

    monkeypatch.setattr(
        sys,
        "argv",
        ["validate_workflow_yaml.py", str(workflow), "--verbose", "--no-skip"],
    )
    with pytest.raises(SystemExit) as failed:
        validator.main()

    assert failed.value.code == 1
    failed_output = capsys.readouterr().out
    assert "Length: Line exceeds 100 characters" in failed_output
    assert "Validation failed" in failed_output
