import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import validate_workflow_yaml as validator

REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_SCRIPT = REPO_ROOT / "scripts/validate_workflow_yaml.py"


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


def test_line_length_does_not_globally_exempt_audit_doc_links(tmp_path: Path) -> None:
    workflow = _write_workflow(
        tmp_path / "audit-links.yml",
        [
            "name: Audit links",
            (
                "          [Monthly workflow audit procedure]"
                "(https://github.com/stranske/Workflows/blob/main/docs/ci/WORKFLOW_AUDIT_PROCEDURE.md)"
            ),
            (
                "          [archived audit reports]"
                "(https://github.com/stranske/Workflows/blob/main/docs/archive/ARCHIVE_PLANS.md#workflow-audit-reports)"
            ),
        ],
    )

    issues = validator.check_line_length(workflow)

    assert issues == [
        (2, "Line exceeds 100 characters"),
        (3, "Line exceeds 100 characters"),
    ]


def test_discover_stops_on_first_successful_empty_comparison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(validator.subprocess, "run", fake_run)

    assert validator.discover_changed_workflows() == []
    assert len(calls) == 1
    assert "origin/main...HEAD" in calls[0]


def test_discover_honors_explicit_base_ref_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append(cmd)
        if "custom/base...HEAD" in cmd:
            return SimpleNamespace(returncode=128, stdout="", stderr="unknown revision")
        return SimpleNamespace(
            returncode=0,
            stdout=".github/workflows/should-not-be-used.yml\n",
            stderr="",
        )

    monkeypatch.setattr(validator.subprocess, "run", fake_run)

    with pytest.raises(validator.WorkflowDiscoveryError, match="custom/base"):
        validator.discover_changed_workflows("custom/base")
    assert len(calls) == 1
    assert "custom/base...HEAD" in calls[0]


def test_main_exits_nonzero_when_discovery_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def boom(_base: str | None = None) -> list[Path]:
        raise validator.WorkflowDiscoveryError("git diff unavailable")

    monkeypatch.setattr(validator, "discover_changed_workflows", boom)
    monkeypatch.setattr(sys, "argv", ["validate_workflow_yaml.py"])

    with pytest.raises(SystemExit) as exc:
        validator.main()

    assert exc.value.code == 1
    assert "git diff unavailable" in capsys.readouterr().err

    # Also prove real CLI invocation outside a git repo exits nonzero.
    non_git = tmp_path / "not-a-repo"
    non_git.mkdir()
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR_SCRIPT)],
        cwd=non_git,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "Failed to discover changed workflow files" in proc.stderr


def _init_temp_git_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    for cmd in (
        ["git", "init", "-b", "main"],
        ["git", "config", "user.email", "test@example.com"],
        ["git", "config", "user.name", "Test User"],
    ):
        subprocess.run(cmd, cwd=repo, check=True, capture_output=True, text=True)


def test_bare_validator_validates_known_workflow_change_in_git_repo(tmp_path: Path) -> None:
    """Known-change case must run actual validation rather than reporting no changes."""
    repo = tmp_path / "repo"
    _init_temp_git_repo(repo)
    workflows = repo / ".github/workflows"
    workflows.mkdir(parents=True)
    _write_workflow(
        workflows / "sample.yml",
        [
            "name: Sample",
            "on: workflow_dispatch",
            "jobs:",
            "  build:",
            "    runs-on: ubuntu-latest",
            "    steps:",
            "      - run: echo base",
        ],
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "feature"], cwd=repo, check=True, capture_output=True)

    # Valid workflow change must actually validate (not report empty diff).
    _write_workflow(
        workflows / "sample.yml",
        [
            "name: Sample",
            "on: workflow_dispatch",
            "jobs:",
            "  build:",
            "    runs-on: ubuntu-latest",
            "    steps:",
            "      - run: echo updated",
        ],
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "valid edit"], cwd=repo, check=True, capture_output=True)

    ok = subprocess.run(
        [sys.executable, str(VALIDATOR_SCRIPT)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ok.returncode == 0, (ok.stdout, ok.stderr)
    assert "All 1 workflow file(s) validated successfully" in ok.stdout
    assert "No changed workflow files" not in ok.stdout

    # Explicit invalid --base-ref must fail rather than falling back to main.
    bad_base = subprocess.run(
        [sys.executable, str(VALIDATOR_SCRIPT), "--base-ref", "nonexistent-ref"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad_base.returncode == 1
    assert "nonexistent-ref" in bad_base.stderr

    # Invalid workflow change must be caught and fail bare validation.
    _write_workflow(
        workflows / "sample.yml",
        [
            "name: Sample",
            "on: workflow_dispatch",
            "jobs:",
            "  build:",
            "    runs-on: ubuntu-latest",
            "    steps:",
            "      - run: echo " + "x" * 110,
        ],
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "invalid edit"], cwd=repo, check=True, capture_output=True
    )

    bad = subprocess.run(
        [sys.executable, str(VALIDATOR_SCRIPT)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert bad.returncode == 1
    assert "Line exceeds 100 characters" in bad.stdout


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
        lambda _base=None: [workflow],
    )
    monkeypatch.setattr(sys, "argv", ["validate_workflow_yaml.py"])
    with pytest.raises(SystemExit) as ok:
        validator.main()

    assert ok.value.code == 0
    assert "validated successfully" in capsys.readouterr().out
