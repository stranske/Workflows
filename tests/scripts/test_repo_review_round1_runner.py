"""Focused tests for repo_review_round1_runner path helpers and sync logic."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from scripts import repo_review_round1_runner as runner

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


class TestRound1FindingsPath:
    """Tests for round1_findings_path()."""

    def test_builds_correct_path_structure(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"
        repo = "stranske/Example"
        agent = "codex"

        result = runner.round1_findings_path(output_dir, agent, repo)

        assert result == output_dir / "round1" / agent / "stranske__Example" / "findings.json"


def test_invoke_round1_reuses_findings_only_for_exact_source_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    findings = runner.round1_findings_path(tmp_path / "out", "codex", "stranske/Example")
    findings.parent.mkdir(parents=True)
    findings.write_text("{}\n", encoding="utf-8")
    runner.write_findings_provenance(
        findings,
        repo="stranske/Example",
        agent="codex",
        source_commit="abc123",
    )
    monkeypatch.setattr(runner, "_validate_findings_file", lambda *_args, **_kwargs: [])

    def unexpected_invoke(*_args, **_kwargs):
        raise AssertionError("exact-head findings should be reused")

    monkeypatch.setattr(runner, "invoke_agent", unexpected_invoke)
    result = runner.invoke_round1_agent(
        agent="codex",
        repo="stranske/Example",
        repo_path=tmp_path / "repo",
        output_dir=tmp_path / "out",
        workspace_root=tmp_path,
        template_path=tmp_path / "prompt.md",
        log_dir=tmp_path / "logs",
        timeout=30,
        retries=0,
        workflows_steward_root=tmp_path,
        source_commit="abc123",
    )

    assert result.succeeded is True
    assert result.spawned is False


def test_invoke_round1_preserves_and_replaces_stale_commit_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    findings = runner.round1_findings_path(tmp_path / "out", "claude", "stranske/Example")
    findings.parent.mkdir(parents=True)
    findings.write_text('{"old": true}\n', encoding="utf-8")
    runner.write_findings_provenance(
        findings,
        repo="stranske/Example",
        agent="claude",
        source_commit="old123",
    )
    monkeypatch.setattr(runner, "_validate_findings_file", lambda *_args, **_kwargs: [])

    def fake_invoke(*_args, **_kwargs):
        findings.write_text('{"new": true}\n', encoding="utf-8")
        return True, "ok"

    monkeypatch.setattr(runner, "invoke_agent", fake_invoke)
    result = runner.invoke_round1_agent(
        agent="claude",
        repo="stranske/Example",
        repo_path=tmp_path / "repo",
        output_dir=tmp_path / "out",
        workspace_root=tmp_path,
        template_path=tmp_path / "prompt.md",
        log_dir=tmp_path / "logs",
        timeout=30,
        retries=0,
        workflows_steward_root=tmp_path,
        source_commit="new456",
    )

    assert result.succeeded is True
    assert result.spawned is True
    provenance = json.loads(runner.findings_provenance_path(findings).read_text(encoding="utf-8"))
    assert provenance["source_commit"] == "new456"
    assert list(findings.parent.glob("findings.stale-*.json"))
    assert list(findings.parent.glob("findings.provenance.stale-*.json"))


def test_invoke_round1_tracks_findings_as_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    findings = runner.round1_findings_path(tmp_path / "out", "codex", "stranske/Example")
    captured: dict[str, object] = {}
    monkeypatch.setattr(runner, "_validate_findings_file", lambda *_args, **_kwargs: [])

    def fake_invoke(*_args, **kwargs):
        captured.update(kwargs)
        findings.parent.mkdir(parents=True, exist_ok=True)
        findings.write_text("{}\n", encoding="utf-8")
        return True, "ok"

    monkeypatch.setattr(runner, "invoke_agent", fake_invoke)
    result = runner.invoke_round1_agent(
        agent="codex",
        repo="stranske/Example",
        repo_path=tmp_path / "repo",
        output_dir=tmp_path / "out",
        workspace_root=tmp_path,
        template_path=tmp_path / "prompt.md",
        log_dir=tmp_path / "logs",
        timeout=30,
        retries=0,
        workflows_steward_root=tmp_path,
        source_commit="abc123",
    )

    assert result.succeeded is True
    assert captured["progress_files"] == (findings,)


def test_findings_provenance_requires_current_schema(tmp_path: Path) -> None:
    findings = tmp_path / "findings.json"
    provenance = runner.findings_provenance_path(findings)
    provenance.write_text(
        json.dumps(
            {
                "schema": "repo-review-round1-provenance/v0",
                "repo": "stranske/Example",
                "agent": "codex",
                "source_commit": "abc123",
            }
        ),
        encoding="utf-8",
    )

    errors = runner.validate_findings_provenance(
        findings,
        repo="stranske/Example",
        agent="codex",
        source_commit="abc123",
    )

    assert any("provenance schema" in error for error in errors)


def test_invoke_round1_attests_valid_defensive_output_after_agent_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    findings = runner.round1_findings_path(tmp_path / "out", "codex", "stranske/Example")
    monkeypatch.setattr(runner, "_validate_findings_file", lambda *_args, **_kwargs: [])

    def failed_after_write(*_args, **_kwargs):
        findings.parent.mkdir(parents=True, exist_ok=True)
        findings.write_text('{"defensive": true}\n', encoding="utf-8")
        return False, "timed out"

    monkeypatch.setattr(runner, "invoke_agent", failed_after_write)
    result = runner.invoke_round1_agent(
        agent="codex",
        repo="stranske/Example",
        repo_path=tmp_path / "repo",
        output_dir=tmp_path / "out",
        workspace_root=tmp_path,
        template_path=tmp_path / "prompt.md",
        log_dir=tmp_path / "logs",
        timeout=30,
        retries=0,
        workflows_steward_root=tmp_path,
        source_commit="abc123",
    )

    assert result.succeeded is True
    assert result.spawned is True
    provenance = json.loads(runner.findings_provenance_path(findings).read_text(encoding="utf-8"))
    assert provenance["source_commit"] == "abc123"


def test_invoke_round1_preserves_invalid_agent_output_before_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    findings = runner.round1_findings_path(tmp_path / "out", "codex", "stranske/Example")
    invocations = 0

    def fake_validate(path: Path, **_kwargs) -> list[str]:
        return [] if '"valid"' in path.read_text(encoding="utf-8") else ["invalid"]

    def fake_invoke(*_args, **_kwargs):
        nonlocal invocations
        invocations += 1
        findings.parent.mkdir(parents=True, exist_ok=True)
        findings.write_text(
            '{"invalid": true}\n' if invocations == 1 else '{"valid": true}\n',
            encoding="utf-8",
        )
        return True, "ok"

    monkeypatch.setattr(runner, "_validate_findings_file", fake_validate)
    monkeypatch.setattr(runner, "invoke_agent", fake_invoke)
    result = runner.invoke_round1_agent(
        agent="codex",
        repo="stranske/Example",
        repo_path=tmp_path / "repo",
        output_dir=tmp_path / "out",
        workspace_root=tmp_path,
        template_path=tmp_path / "prompt.md",
        log_dir=tmp_path / "logs",
        timeout=30,
        retries=1,
        workflows_steward_root=tmp_path,
        source_commit="abc123",
    )

    assert result.succeeded is True
    assert invocations == 2
    stale = list(findings.parent.glob("findings.stale-*.json"))
    assert len(stale) == 1
    assert stale[0].read_text(encoding="utf-8") == '{"invalid": true}\n'
    assert findings.read_text(encoding="utf-8") == '{"valid": true}\n'


def test_findings_path_handles_repo_names_with_multiple_slashes(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    result = runner.round1_findings_path(output_dir, "claude", "org/suborg/project")
    assert result == output_dir / "round1" / "claude" / "org__suborg__project" / "findings.json"


def test_findings_path_handles_empty_agent_name(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    result = runner.round1_findings_path(output_dir, "", "stranske/Test")
    assert result == output_dir / "round1" / "" / "stranske__Test" / "findings.json"


def test_findings_path_preserves_existing_path_content(tmp_path: Path) -> None:
    output_dir = tmp_path / "existing" / "output"
    output_dir.mkdir(parents=True)
    result = runner.round1_findings_path(output_dir, "codex", "stranske/Example")
    assert result == output_dir / "round1" / "codex" / "stranske__Example" / "findings.json"


@pytest.mark.parametrize("failure", ["nonzero", "timeout"])
def test_run_fails_closed_when_source_commit_cannot_be_resolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    repo = "stranske/Example"
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    output_dir = tmp_path / "out"
    review_inputs = runner.review_inputs_path(output_dir, repo)
    review_inputs.parent.mkdir(parents=True)
    review_inputs.write_text("review input\n", encoding="utf-8")
    registry_path = tmp_path / "Workflows-steward" / "config" / "registry.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        runner,
        "load_registry",
        lambda _path: (
            tmp_path,
            [],
            [SimpleNamespace(repo=repo, local_path="repo")],
            [],
        ),
    )
    invoked = False

    def unexpected_agent(**_kwargs):
        nonlocal invoked
        invoked = True
        raise AssertionError("agent must not run without a source commit")

    monkeypatch.setattr(runner, "invoke_round1_agent", unexpected_agent)
    if failure == "timeout":

        def fake_run(*_args, **_kwargs):
            raise subprocess.TimeoutExpired(["git", "rev-parse", "HEAD"], 30)

    else:

        def fake_run(*_args, **_kwargs):
            return subprocess.CompletedProcess(
                args=["git"], returncode=1, stdout="", stderr="bad revision"
            )

    monkeypatch.setattr(subprocess, "run", fake_run)
    args = SimpleNamespace(
        output_dir=str(output_dir),
        registry=str(registry_path),
        repo=repo,
        skip_local_sync=True,
        skip_map_refresh=True,
        agents=["codex", "claude"],
        turn_timeout=30,
        retries=1,
        gitnexus_bin="gitnexus",
        map_refresh_timeout=30,
    )

    assert runner.run(args) == 1
    assert invoked is False
    state = runner.load_state(output_dir, repo)
    assert state.status == "round1-failed"
    assert "cannot resolve review source commit" in state.notes


class TestReviewInputsPath:
    """Tests for review_inputs_path()."""

    def test_builds_correct_path_structure(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"
        repo = "stranske/Example"

        result = runner.review_inputs_path(output_dir, repo)

        assert result == output_dir / "repos" / "stranske__Example" / "review-inputs.md"

    def test_handles_repo_names_with_slashes(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"
        repo = "org/suborg/project"

        result = runner.review_inputs_path(output_dir, repo)

        assert result == output_dir / "repos" / "org__suborg__project" / "review-inputs.md"

    def test_handles_simple_repo_name(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"
        repo = "simple"

        result = runner.review_inputs_path(output_dir, repo)

        assert result == output_dir / "repos" / "simple" / "review-inputs.md"


class TestRound1PromptTemplatePath:
    """Tests for round1_prompt_template_path() with env var and fallback paths."""

    def test_returns_path_from_env_var_when_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        prompt_dir = tmp_path / "custom_prompts"
        prompt_dir.mkdir()
        prompt_file = prompt_dir / "REPO_REVIEW_ROUND1_PROMPT.md"
        prompt_file.write_text("# Custom prompt", encoding="utf-8")

        monkeypatch.setenv("REPO_REVIEW_PROMPT_DIR", str(prompt_dir))

        result = runner.round1_prompt_template_path()

        assert result == prompt_file

    def test_falls_back_to_repo_relative_docs_ops(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Clear env var
        monkeypatch.delenv("REPO_REVIEW_PROMPT_DIR", raising=False)

        # Create the expected fallback path
        docs_ops_dir = tmp_path / "docs" / "ops"
        docs_ops_dir.mkdir(parents=True)
        prompt_file = docs_ops_dir / "REPO_REVIEW_ROUND1_PROMPT.md"
        prompt_file.write_text("# Repo relative prompt", encoding="utf-8")

        # Mock the module's __file__ to point to our tmp_path
        monkeypatch.setattr(
            runner, "__file__", str(tmp_path / "scripts" / "repo_review_round1_runner.py")
        )

        result = runner.round1_prompt_template_path()

        assert result == prompt_file

    def test_falls_back_to_cwd_docs_ops(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Clear env var
        monkeypatch.delenv("REPO_REVIEW_PROMPT_DIR", raising=False)

        # Change to tmp_path and create the expected fallback path there
        original_cwd = Path.cwd()
        monkeypatch.chdir(tmp_path)

        try:
            docs_ops_dir = tmp_path / "docs" / "ops"
            docs_ops_dir.mkdir(parents=True)
            prompt_file = docs_ops_dir / "REPO_REVIEW_ROUND1_PROMPT.md"
            prompt_file.write_text("# CWD prompt", encoding="utf-8")

            # Mock the module's __file__ to point somewhere without the prompt
            monkeypatch.setattr(runner, "__file__", str(tmp_path / "other" / "module.py"))

            result = runner.round1_prompt_template_path()

            assert result == prompt_file
        finally:
            monkeypatch.chdir(original_cwd)

    def test_returns_first_candidate_when_no_files_exist(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        prompt_dir = tmp_path / "custom_prompts"
        prompt_dir.mkdir()

        monkeypatch.setenv("REPO_REVIEW_PROMPT_DIR", str(prompt_dir))

        # Create a mock function that returns False for is_file()
        original_is_file = Path.is_file

        def mock_is_file(self):
            # Return False for all paths to simulate no files exist
            return False

        monkeypatch.setattr(Path, "is_file", mock_is_file)

        try:
            result = runner.round1_prompt_template_path()

            # Should return the first candidate path even if it doesn't exist
            expected = Path(prompt_dir) / "REPO_REVIEW_ROUND1_PROMPT.md"
            assert result == expected
        finally:
            # Restore original method
            Path.is_file = original_is_file

    def test_env_var_takes_precedence_over_fallbacks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Create both env var path and fallback path
        env_dir = tmp_path / "env_prompts"
        env_dir.mkdir()
        env_prompt = env_dir / "REPO_REVIEW_ROUND1_PROMPT.md"
        env_prompt.write_text("# ENV prompt", encoding="utf-8")

        fallback_dir = tmp_path / "docs" / "ops"
        fallback_dir.mkdir(parents=True)
        fallback_prompt = fallback_dir / "REPO_REVIEW_ROUND1_PROMPT.md"
        fallback_prompt.write_text("# Fallback prompt", encoding="utf-8")

        monkeypatch.setenv("REPO_REVIEW_PROMPT_DIR", str(env_dir))
        monkeypatch.setattr(
            runner, "__file__", str(tmp_path / "scripts" / "repo_review_round1_runner.py")
        )

        result = runner.round1_prompt_template_path()

        # Should prefer env var path
        assert result == env_prompt


# ---------------------------------------------------------------------------
# sync_repo_to_origin
# ---------------------------------------------------------------------------


class TestSyncRepoToOrigin:
    """Tests for sync_repo_to_origin() using monkeypatched subprocess."""

    def _make_result(
        self, returncode: int = 0, stdout: str = "", stderr: str = ""
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["git", "test"], returncode=returncode, stdout=stdout, stderr=stderr
        )

    def _create_mock_subprocess(self, fake_run_func):
        """Create a mock subprocess module with the given run function."""
        mock_subprocess = MagicMock()
        mock_subprocess.run = fake_run_func
        mock_subprocess.TimeoutExpired = subprocess.TimeoutExpired
        return mock_subprocess

    def test_successful_sync_all_steps(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        def fake_run(
            args: list[str],
            *,
            check: bool = False,
            capture_output: bool = True,
            text: bool = True,
            timeout: int = 120,
        ) -> subprocess.CompletedProcess[str]:
            # Simple mock: return success for all operations
            if "fetch" in args:
                return self._make_result(0)
            elif "ls-files" in args:
                return self._make_result(1, "")  # file not tracked
            elif "cat-file" in args:
                return self._make_result(1, "")  # file not in origin
            elif "status" in args:
                return self._make_result(0, "")  # clean working tree
            elif "rev-parse" in args:
                if "--verify" in args and "origin/main" in args:
                    return self._make_result(0, "abc123")
                elif "--abbrev-ref" in args and "HEAD" in args:
                    return self._make_result(0, "main")
                elif "--short" in args:
                    return self._make_result(0, "abc1234")
                elif args[-2:] == ["rev-parse", "HEAD"]:
                    return self._make_result(0, "abc123")
            elif "pull" in args or "checkout" in args:
                return self._make_result(0)

            return self._make_result(0)

        mock_subprocess = self._create_mock_subprocess(fake_run)

        with (
            patch("subprocess.run", mock_subprocess.run),
            patch("subprocess.TimeoutExpired", subprocess.TimeoutExpired),
        ):
            ok, message = runner.sync_repo_to_origin(repo_path)

        assert ok is True
        assert "HEAD now abc1234 on main" in message

    def test_failure_on_fetch_error(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        def fake_run(
            args: list[str],
            *,
            check: bool = False,
            capture_output: bool = True,
            text: bool = True,
            timeout: int = 120,
        ) -> subprocess.CompletedProcess[str]:
            if "fetch" in args:
                return self._make_result(1, stderr="fetch failed: network error")
            return self._make_result(0)

        mock_subprocess = self._create_mock_subprocess(fake_run)

        with (
            patch("subprocess.run", mock_subprocess.run),
            patch("subprocess.TimeoutExpired", subprocess.TimeoutExpired),
        ):
            ok, message = runner.sync_repo_to_origin(repo_path)

        assert ok is False
        assert "git fetch failed" in message
        assert "network error" in message

    def test_failure_on_missing_main(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        def fake_run(
            args: list[str],
            *,
            check: bool = False,
            capture_output: bool = True,
            text: bool = True,
            timeout: int = 120,
        ) -> subprocess.CompletedProcess[str]:
            if "fetch" in args:
                return self._make_result(0)
            elif "status" in args:
                return self._make_result(0, "")  # clean
            elif "--verify" in args:
                # The canonical main branch does not exist.
                return self._make_result(1, "")
            return self._make_result(0)

        mock_subprocess = self._create_mock_subprocess(fake_run)

        with (
            patch("subprocess.run", mock_subprocess.run),
            patch("subprocess.TimeoutExpired", subprocess.TimeoutExpired),
        ):
            ok, message = runner.sync_repo_to_origin(repo_path)

        assert ok is False
        assert "origin/main does not exist" in message

    def test_failure_on_checkout_error(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        def fake_run(
            args: list[str],
            *,
            check: bool = False,
            capture_output: bool = True,
            text: bool = True,
            timeout: int = 120,
        ) -> subprocess.CompletedProcess[str]:
            if "fetch" in args:
                return self._make_result(0)
            elif "status" in args:
                return self._make_result(0, "")  # clean
            elif "--verify" in args and "origin/main" in args:
                return self._make_result(0, "abc123")
            elif "--abbrev-ref" in args and "HEAD" in args:
                return self._make_result(0, "develop")  # on develop, need to checkout main
            elif "checkout" in args:
                return self._make_result(1, stderr="checkout failed: pathspec error")
            return self._make_result(0)

        mock_subprocess = self._create_mock_subprocess(fake_run)

        with (
            patch("subprocess.run", mock_subprocess.run),
            patch("subprocess.TimeoutExpired", subprocess.TimeoutExpired),
        ):
            ok, message = runner.sync_repo_to_origin(repo_path)

        assert ok is False
        assert "checkout --detach origin/main failed" in message
        assert "pathspec error" in message

    def test_stale_main_detaches_at_origin_without_pull(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        calls: list[list[str]] = []

        def fake_run(
            args: list[str],
            *,
            check: bool = False,
            capture_output: bool = True,
            text: bool = True,
            timeout: int = 120,
        ) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            if "fetch" in args:
                return self._make_result(0)
            elif "status" in args:
                return self._make_result(0, "")  # clean
            elif "--verify" in args and "origin/main" in args:
                return self._make_result(0, "abc123")
            elif "--abbrev-ref" in args and "HEAD" in args:
                return self._make_result(0, "main")  # already on main
            elif args[-2:] == ["rev-parse", "HEAD"]:
                return self._make_result(0, "old123")
            elif "checkout" in args:
                return self._make_result(0)
            elif "--short" in args:
                return self._make_result(0, "abc123")
            return self._make_result(0)

        mock_subprocess = self._create_mock_subprocess(fake_run)

        with (
            patch("subprocess.run", mock_subprocess.run),
            patch("subprocess.TimeoutExpired", subprocess.TimeoutExpired),
        ):
            ok, message = runner.sync_repo_to_origin(repo_path)

        assert ok is True
        assert "detached at origin/main (was main)" in message
        assert "HEAD now abc123 on origin/main" in message
        assert not any("pull" in call for call in calls)
        assert any(call[-3:] == ["checkout", "--detach", "origin/main"] for call in calls)

    def test_preserves_executing_steward_checkout(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        calls: list[list[str]] = []

        def fake_run(
            args: list[str],
            *,
            check: bool = False,
            capture_output: bool = True,
            text: bool = True,
            timeout: int = 120,
        ) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            if "fetch" in args:
                return self._make_result(0, "")
            if "status" in args:
                return self._make_result(0, " M scripts/repo_review_coordinator.py\n")
            if "--verify" in args and "origin/main" in args:
                return self._make_result(0, "origin123")
            if "--abbrev-ref" in args:
                return self._make_result(0, "HEAD")
            if args[-2:] == ["rev-parse", "HEAD"]:
                return self._make_result(0, "repair456")
            return self._make_result(0)

        with patch("subprocess.run", fake_run):
            ok, message = runner.sync_repo_to_origin(repo_path, preserve_checkout=True)

        assert ok is True
        assert "preserved executing steward checkout at repair456" in message
        assert not any("checkout" in call or "pull" in call for call in calls)
        assert not any("stash" in call for call in calls)

    def test_stash_failure_stops_before_checkout(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        calls: list[list[str]] = []

        def fake_run(args: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            if "fetch" in args:
                return self._make_result(0)
            if "--verify" in args:
                return self._make_result(0, "origin123")
            if "--abbrev-ref" in args:
                return self._make_result(0, "feature")
            if args[-2:] == ["rev-parse", "HEAD"]:
                return self._make_result(0, "local456")
            if "status" in args:
                return self._make_result(0, " M local.txt\n")
            if "stash" in args:
                return self._make_result(1, stderr="unable to write index")
            return self._make_result(0)

        with patch("subprocess.run", fake_run):
            ok, message = runner.sync_repo_to_origin(repo_path)

        assert ok is False
        assert "git stash failed" in message
        assert "unable to write index" in message
        assert not any("checkout" in call for call in calls)

    def test_timeout_handling(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        def fake_run(
            args: list[str],
            *,
            check: bool = False,
            capture_output: bool = True,
            text: bool = True,
            timeout: int = 120,
        ) -> subprocess.CompletedProcess[str]:
            # This will trigger the timeout
            raise subprocess.TimeoutExpired(["git", "fetch"], timeout)

        mock_subprocess = self._create_mock_subprocess(fake_run)

        with (
            patch("subprocess.run", mock_subprocess.run),
            patch("subprocess.TimeoutExpired", subprocess.TimeoutExpired),
        ):
            ok, message = runner.sync_repo_to_origin(repo_path, timeout=30)

        assert ok is False
        assert "sync timed out after 30s" in message

    def test_stashes_dirty_changes(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        def fake_run(
            args: list[str],
            *,
            check: bool = False,
            capture_output: bool = True,
            text: bool = True,
            timeout: int = 120,
        ) -> subprocess.CompletedProcess[str]:
            if "fetch" in args:
                return self._make_result(0)
            elif "status" in args:
                return self._make_result(0, " M file1.txt\n?? file2.txt")  # dirty
            elif "stash" in args:
                return self._make_result(0)  # stash succeeded
            elif "--verify" in args and "origin/main" in args:
                return self._make_result(0, "abc123")
            elif "--abbrev-ref" in args and "HEAD" in args:
                return self._make_result(0, "main")  # already on main
            elif "pull" in args:
                return self._make_result(0)
            elif "--short" in args:
                return self._make_result(0, "abc123")
            return self._make_result(0)

        mock_subprocess = self._create_mock_subprocess(fake_run)

        with (
            patch("subprocess.run", mock_subprocess.run),
            patch("subprocess.TimeoutExpired", subprocess.TimeoutExpired),
        ):
            ok, message = runner.sync_repo_to_origin(repo_path)

        assert ok is True
        assert "stashed dirty changes" in message

    def test_removes_untracked_workloop_state(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        # Create the untracked workloop-state.md file
        workloop_file = repo_path / "workloop-state.md"
        workloop_file.write_text("# Untracked state", encoding="utf-8")

        def fake_run(
            args: list[str],
            *,
            check: bool = False,
            capture_output: bool = True,
            text: bool = True,
            timeout: int = 120,
        ) -> subprocess.CompletedProcess[str]:
            if "fetch" in args:
                return self._make_result(0)
            elif "status" in args:
                return self._make_result(0, "")  # clean except for untracked
            elif "ls-files" in args:
                return self._make_result(1, "")  # file not tracked locally
            elif "cat-file" in args:
                return self._make_result(0, "abc123")  # file exists in origin
            elif "--verify" in args and "origin/main" in args:
                return self._make_result(0, "abc123")
            elif "--abbrev-ref" in args and "HEAD" in args:
                return self._make_result(0, "main")  # already on main
            elif "pull" in args:
                return self._make_result(0)
            elif "--short" in args:
                return self._make_result(0, "abc123")
            return self._make_result(0)

        mock_subprocess = self._create_mock_subprocess(fake_run)

        with (
            patch("subprocess.run", mock_subprocess.run),
            patch("subprocess.TimeoutExpired", subprocess.TimeoutExpired),
        ):
            ok, message = runner.sync_repo_to_origin(repo_path)

        assert ok is True
        assert "removed untracked workloop-state.md" in message
        assert not workloop_file.exists()

    def test_force_checkout_when_not_on_target_branch(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        def fake_run(
            args: list[str],
            *,
            check: bool = False,
            capture_output: bool = True,
            text: bool = True,
            timeout: int = 120,
        ) -> subprocess.CompletedProcess[str]:
            if "fetch" in args:
                return self._make_result(0)
            elif "status" in args:
                return self._make_result(0, "")  # clean
            elif "--verify" in args and "origin/main" in args:
                return self._make_result(0, "abc123")
            elif "--abbrev-ref" in args and "HEAD" in args:
                return self._make_result(0, "develop")  # on develop
            elif "checkout" in args:
                return self._make_result(0)  # checkout succeeded
            elif "pull" in args:
                return self._make_result(0)
            elif "--short" in args:
                return self._make_result(0, "def456")
            return self._make_result(0)

        mock_subprocess = self._create_mock_subprocess(fake_run)

        with (
            patch("subprocess.run", mock_subprocess.run),
            patch("subprocess.TimeoutExpired", subprocess.TimeoutExpired),
        ):
            ok, message = runner.sync_repo_to_origin(repo_path)

        assert ok is True
        assert "detached at origin/main (was develop)" in message
        assert "HEAD now def456 on origin/main" in message


def test_refresh_map_quarantines_conflicted_wal_and_verifies_rebuild(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_path = tmp_path / "repo"
    cache_dir = repo_path / ".gitnexus"
    cache_dir.mkdir(parents=True)
    (cache_dir / "lbug (Tim's conflicted copy 2026-09-03).wal").write_text("", encoding="utf-8")

    def fake_analyze(*_args, **_kwargs):
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "meta.json").write_text(
            json.dumps({"lastCommit": "abc123", "stats": {"embeddings": 12}}),
            encoding="utf-8",
        )
        return True, "GitNexus Analyzer complete"

    monkeypatch.setattr(runner, "run_gitnexus_analyze", fake_analyze)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=["git"], returncode=0, stdout="abc123\n", stderr=""
        ),
    )

    ok, message = runner.refresh_map_blocking(
        repo_path,
        gitnexus_bin="gitnexus",
        repair_root=tmp_path / "repairs",
    )

    assert ok is True
    assert "quarantined GitNexus cache" in message
    assert (cache_dir / "meta.json").is_file()
    quarantined = list((tmp_path / "repairs").glob("repo/*/.gitnexus/*conflicted copy*"))
    assert len(quarantined) == 1


def test_refresh_map_returns_failure_when_quarantine_move_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_path = tmp_path / "repo"
    cache_dir = repo_path / ".gitnexus"
    cache_dir.mkdir(parents=True)
    (cache_dir / "lbug (conflicted copy).wal").write_text("broken", encoding="utf-8")

    def fail_move(*_args, **_kwargs):
        raise OSError("Dropbox lock")

    monkeypatch.setattr(runner.shutil, "move", fail_move)

    ok, message = runner.refresh_map_blocking(
        repo_path,
        gitnexus_bin="gitnexus",
        repair_root=tmp_path / "repairs",
    )

    assert ok is False
    assert "quarantine failed" in message
    assert "Dropbox lock" in message


def test_refresh_map_rebuilds_after_analyzer_reports_corruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_path = tmp_path / "repo"
    cache_dir = repo_path / ".gitnexus"
    cache_dir.mkdir(parents=True)
    (cache_dir / "lbug").write_bytes(b"broken")
    calls = 0

    def fake_analyze(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return False, "GitNexus corruption detected (corrupted wal file)"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "meta.json").write_text(
            json.dumps({"lastCommit": "abc123", "stats": {"embeddings": 8}}),
            encoding="utf-8",
        )
        return True, "rebuilt"

    monkeypatch.setattr(runner, "run_gitnexus_analyze", fake_analyze)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=["git"], returncode=0, stdout="abc123\n", stderr=""
        ),
    )

    ok, message = runner.refresh_map_blocking(
        repo_path,
        gitnexus_bin="gitnexus",
        repair_root=tmp_path / "repairs",
    )

    assert ok is True
    assert calls == 2
    assert "analyzer reported database corruption" in message


@pytest.mark.parametrize(
    "meta", [[], {"lastCommit": "abc123", "stats": []}, {"lastCommit": "abc123", "stats": "bad"}]
)
def test_refresh_map_rejects_non_object_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, meta: object
) -> None:
    repo_path = tmp_path / "repo"
    cache_dir = repo_path / ".gitnexus"
    cache_dir.mkdir(parents=True)
    (cache_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    monkeypatch.setattr(runner, "run_gitnexus_analyze", lambda *_args, **_kwargs: (True, "rebuilt"))

    ok, message = runner.refresh_map_blocking(repo_path, gitnexus_bin="gitnexus")

    assert ok is False
    assert "meta.json is invalid" in message


def test_refresh_map_allows_structural_index_without_embeddings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_path = tmp_path / "repo"
    cache_dir = repo_path / ".gitnexus"
    cache_dir.mkdir(parents=True)
    (cache_dir / "meta.json").write_text(
        json.dumps({"lastCommit": "abc123", "stats": {"embeddings": 0}}), encoding="utf-8"
    )
    monkeypatch.setattr(runner, "run_gitnexus_analyze", lambda *_args, **_kwargs: (True, "rebuilt"))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=["git"], returncode=0, stdout="abc123\n", stderr=""
        ),
    )

    ok, message = runner.refresh_map_blocking(repo_path, gitnexus_bin="gitnexus")

    assert ok is True
    assert "rebuilt" in message


def test_refresh_map_returns_failed_result_when_head_check_times_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_path = tmp_path / "repo"
    cache_dir = repo_path / ".gitnexus"
    cache_dir.mkdir(parents=True)
    (cache_dir / "meta.json").write_text(
        json.dumps({"lastCommit": "abc123", "stats": {"embeddings": 1}}), encoding="utf-8"
    )
    monkeypatch.setattr(runner, "run_gitnexus_analyze", lambda *_args, **_kwargs: (True, "rebuilt"))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired(["git"], 1)),
    )

    ok, message = runner.refresh_map_blocking(repo_path, gitnexus_bin="gitnexus")

    assert ok is False
    assert "HEAD verification timed out" in message


def test_refresh_map_quarantines_conflicted_wal_created_during_rebuild(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_path = tmp_path / "repo"
    cache_dir = repo_path / ".gitnexus"
    cache_dir.mkdir(parents=True)

    def fake_analyze(*_args, **_kwargs):
        (cache_dir / "meta.json").write_text(
            json.dumps({"lastCommit": "abc123", "stats": {"embeddings": 12}}),
            encoding="utf-8",
        )
        (cache_dir / "lbug (Tim's conflicted copy 2026-09-03).wal").write_text("", encoding="utf-8")
        return True, "GitNexus Analyzer complete"

    monkeypatch.setattr(runner, "run_gitnexus_analyze", fake_analyze)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=["git"], returncode=0, stdout="abc123\n", stderr=""
        ),
    )

    ok, message = runner.refresh_map_blocking(
        repo_path, gitnexus_bin="gitnexus", repair_root=tmp_path / "repairs"
    )

    assert ok is True
    assert "created during analyzer rebuild" in message
    assert not list(cache_dir.glob("**/*conflicted copy*"))
    quarantined = list((tmp_path / "repairs").glob("repo/*/conflicted-artifacts/*conflicted copy*"))
    assert len(quarantined) == 1
