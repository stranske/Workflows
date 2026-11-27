import subprocess
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
    monkeypatch.setattr(validator, "LEGACY_SKIP_WORKFLOWS", {"legacy.yml"})
    workflow = _write_workflow(
        tmp_path / "legacy.yml",
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


def test_main_validates_git_changed_workflows_when_no_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = _write_workflow(
        tmp_path / "sample.yml",
        [
            "name: Sample",
            "on: workflow_dispatch",
            "jobs:",
            "  build:",
            "    runs-on: ubuntu-latest",
            "    steps:",
            "      - run: echo ok",
        ],
    )
    monkeypatch.setattr(
        validator,
        "discover_changed_workflows",
        lambda _base="origin/main": [workflow],
    )
    monkeypatch.setattr(sys, "argv", ["validate_workflow_yaml.py"])
    with pytest.raises(SystemExit) as ok:
        validator.main()

    assert ok.value.code == 0
    assert "validated successfully" in capsys.readouterr().out


def test_main_skips_deleted_workflow_only_during_discovery(tmp_path: Path) -> None:
    validator_script = Path(validator.__file__).resolve()

    def git(*args: str) -> None:
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Workflow Test",
                "-c",
                "user.email=workflow-test@example.com",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "core.hooksPath=/dev/null",
                *args,
            ],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

    git("init")
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    retired = _write_workflow(workflows / "retired.yml", ["name: Retired"])
    git("add", ".github/workflows")
    git("commit", "-m", "Add workflow")
    git("update-ref", "refs/remotes/origin/main", "HEAD")

    retired.unlink()
    git("add", "-u")
    git("commit", "-m", "Retire workflow")

    automatic = subprocess.run(
        [sys.executable, str(validator_script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert automatic.returncode == 0, automatic.stdout + automatic.stderr
    assert "No changed workflow files to validate" in automatic.stdout

    explicit = subprocess.run(
        [sys.executable, str(validator_script), str(retired.relative_to(tmp_path))],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert explicit.returncode == 1
    assert ".github/workflows/retired.yml: File not found" in explicit.stdout


def test_discover_changed_workflows_does_not_fallback_past_valid_base_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def git(*args: str) -> None:
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Workflow Test",
                "-c",
                "user.email=workflow-test@example.com",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "core.hooksPath=/dev/null",
                *args,
            ],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

    git("init")
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    stale = _write_workflow(workflows / "stale.yml", ["name: Stale"])
    git("add", ".github/workflows")
    git("commit", "-m", "Base commit")
    git("branch", "-M", "main")

    git("checkout", "-b", "feature")
    _write_workflow(stale, ["name: Stale", "# " + "x" * 120])
    retired = _write_workflow(workflows / "retired.yml", ["name: Retired"])
    git("add", ".github/workflows")
    git("commit", "-m", "Advance origin/main")
    git("update-ref", "refs/remotes/origin/main", "HEAD")

    monkeypatch.chdir(tmp_path)
    assert validator.discover_changed_workflows("origin/main") == []

    retired.unlink()
    git("add", "-u")
    git("commit", "-m", "Retire workflow")

    assert validator.discover_changed_workflows("origin/main") == []

    _write_workflow(workflows / "renamed.yml", ["name: Renamed"])
    git("add", ".github/workflows/renamed.yml")
    git("commit", "-m", "Add replacement workflow")

    assert validator.discover_changed_workflows("origin/main") == [
        Path(".github/workflows/renamed.yml")
    ]
