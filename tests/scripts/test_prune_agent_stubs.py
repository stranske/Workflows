"""Tests for scripts/prune_agent_stubs.py — select_prunable is pure/unit-testable."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml
from scripts import prune_agent_stubs
from scripts.prune_agent_stubs import select_prunable


def test_workflow_delivers_deletions_through_a_reviewable_pr() -> None:
    root = Path(__file__).resolve().parents[2]
    workflow = root / ".github/workflows/maint-84-prune-agent-stubs.yml"
    job = yaml.load(workflow.read_text(), Loader=yaml.BaseLoader)["jobs"]["prune"]
    assert all("git push" not in step.get("run", "") for step in job["steps"])
    delivery = next(step for step in job["steps"] if "create-pull-request@" in step.get("uses", ""))
    assert delivery["if"] == "steps.prune.outputs.changed == 'true'"
    settings = delivery["with"]
    assert settings["base"] == "${{ github.event.repository.default_branch }}"
    assert settings["branch"] != "main"
    assert settings["add-paths"] == "agents/*.md"
    assert settings.get("draft", "false") == "false"
    assert "[skip ci]" not in settings["commit-message"]


# ---------------------------------------------------------------------------
# Core acceptance-criteria test (from issue #2336)
# ---------------------------------------------------------------------------


def test_select_prunable_acceptance() -> None:
    """Closed stub pruned, open stub kept, non-stub ignored."""
    result = select_prunable(
        ["auto-pilot-100.md", "auto-pilot-200.md", "README.md"],
        {100},
    )
    assert result == ["auto-pilot-100.md"]


# ---------------------------------------------------------------------------
# Additional unit tests
# ---------------------------------------------------------------------------


def test_select_prunable_empty_inputs() -> None:
    assert select_prunable([], set()) == []


def test_select_prunable_no_closed_issues() -> None:
    """When no issue numbers are closed, nothing should be pruned."""
    stubs = ["auto-pilot-755.md", "codex-10.md"]
    assert select_prunable(stubs, set()) == []


def test_select_prunable_all_closed() -> None:
    """All matching stubs are returned when all are closed."""
    stubs = ["auto-pilot-100.md", "auto-pilot-200.md"]
    result = select_prunable(stubs, {100, 200})
    assert result == ["auto-pilot-100.md", "auto-pilot-200.md"]


def test_select_prunable_non_stub_names_ignored() -> None:
    """Files that don't match the pattern are never returned."""
    non_stubs = [
        "README.md",
        "AUTO-PILOT-100.md",  # uppercase start — does not match
        "auto-pilot.md",  # no trailing issue number
        ".hidden-1.md",  # starts with dot
        "auto_pilot-100.md",  # underscore not in pattern
    ]
    assert select_prunable(non_stubs, {100}) == []


def test_select_prunable_open_stubs_kept() -> None:
    """Stubs whose issue number is NOT in closed_issue_numbers are left alone."""
    stubs = ["auto-pilot-100.md", "auto-pilot-200.md", "codex-300.md"]
    # Only 100 is closed; 200 and 300 are open.
    result = select_prunable(stubs, {100})
    assert result == ["auto-pilot-100.md"]
    assert "auto-pilot-200.md" not in result
    assert "codex-300.md" not in result


def test_select_prunable_result_is_sorted() -> None:
    """Results come back in sorted order regardless of input order."""
    stubs = ["codex-300.md", "auto-pilot-100.md", "auto-pilot-200.md"]
    result = select_prunable(stubs, {100, 200, 300})
    assert result == sorted(result)


def test_select_prunable_multiple_agents() -> None:
    """Works correctly with stubs from different agent prefixes."""
    stubs = ["auto-pilot-10.md", "codex-10.md", "auto-pilot-20.md"]
    # Both issue-10 stubs (different agents) should be pruned; 20 kept.
    result = select_prunable(stubs, {10})
    assert "auto-pilot-10.md" in result
    assert "codex-10.md" in result
    assert "auto-pilot-20.md" not in result


def test_fetch_closed_issues_and_main_modes(tmp_path, monkeypatch, capsys) -> None:
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "codex-12.md").write_text("stub", encoding="utf-8")
    (agents / "codex-13.md").write_text("stub", encoding="utf-8")
    monkeypatch.setattr(prune_agent_stubs, "AGENTS_DIR", agents)
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        assert command == [
            "gh",
            "issue",
            "list",
            "--repo",
            "example/project",
            "--state",
            "closed",
            "--limit",
            "10000",
            "--json",
            "number",
        ]
        assert kwargs == {"check": True, "capture_output": True, "text": True}
        return subprocess.CompletedProcess(command, 0, json.dumps([{"number": 12}]), "")

    monkeypatch.setattr(prune_agent_stubs.subprocess, "run", fake_run)
    assert prune_agent_stubs.main(["--repo", "example/project", "--dry-run"]) == 0
    assert "would delete" in capsys.readouterr().out
    assert (agents / "codex-12.md").exists()
    assert prune_agent_stubs.main(["--repo", "example/project"]) == 0
    assert len(calls) == 2
    assert not (agents / "codex-12.md").exists()
    assert (agents / "codex-13.md").exists()


def test_main_rejects_missing_agents_directory(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(prune_agent_stubs, "AGENTS_DIR", tmp_path / "missing")
    assert prune_agent_stubs.main([]) == 1
    assert "directory not found" in capsys.readouterr().err


def test_main_reports_nothing_to_prune(tmp_path, monkeypatch, capsys) -> None:
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "codex-99.md").write_text("stub", encoding="utf-8")
    monkeypatch.setattr(prune_agent_stubs, "AGENTS_DIR", agents)
    monkeypatch.setattr(
        prune_agent_stubs.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, json.dumps([]), ""),
    )
    assert prune_agent_stubs.main([]) == 0
    assert "Nothing to prune." in capsys.readouterr().out
    assert (agents / "codex-99.md").exists()


def test_main_clean_checkout_without_markers_uses_no_github(tmp_path) -> None:
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = shutil.copy2(prune_agent_stubs.__file__, scripts)
    env = dict(os.environ, PATH="")
    agents = tmp_path / "agents"

    def assert_noop(*args):
        result = subprocess.run(
            [sys.executable, script, *args],
            cwd=tmp_path,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        assert "Nothing to prune." in result.stdout

    assert_noop("--dry-run")
    assert not agents.exists()
    agents.mkdir()
    (agents / "local-notes.md").write_text("local notes", encoding="utf-8")
    assert_noop()
    assert (agents / "local-notes.md").read_text(encoding="utf-8") == "local notes"


def test_main_rejects_unrelated_git_root_without_agents(tmp_path, monkeypatch, capsys) -> None:
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    monkeypatch.chdir(tmp_path)
    assert prune_agent_stubs.main([]) == 1
    assert "directory not found" in capsys.readouterr().err
