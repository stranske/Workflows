from __future__ import annotations

import ast
import json

# Add parent directory to path for imports
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts import cli_handler
from scripts.cli_handler import (
    _confirm_issue_creation,
    _load_allowed_scopes,
    _load_allowlist,
    _load_config,
    _parse_allowlist,
    _parse_labels,
    _parse_scopes,
    main,
)


def _main_args(*extra: str) -> list[str]:
    return ["--repo", "owner/repo", "--allowlist", "owner/repo", *extra]


def _with_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "token")


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        pytest.param(["--repo", "owner/repo"], "allowlist is empty", id="empty-allowlist"),
        pytest.param(
            ["--repo", "owner/repo", "--allowlist", "someone/else"],
            "is not in the allowlist",
            id="repository-not-allowlisted",
        ),
        pytest.param(_main_args("--title", "demo"), "Missing GitHub token", id="missing-token"),
    ],
)
def test_main_rejects_invalid_repository_or_token_configuration(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    message: str,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    assert main(argv) == 1
    assert message in capsys.readouterr().err


def test_main_validates_option_combinations_before_network_calls(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _with_token(monkeypatch)
    assert main(_main_args("--check-issue", "1", "--check-unique", "2")) == 1
    assert "Choose only one" in capsys.readouterr().err
    assert main(_main_args("--expected-issue-number", "1", "--title", "demo")) == 1
    assert "requires --check-issue" in capsys.readouterr().err
    assert main(_main_args("--show-source", "--confirm-source", "--title", "demo")) == 1
    assert "Choose only one" in capsys.readouterr().err


def test_main_supports_duplicate_unique_list_and_dry_run_modes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _with_token(monkeypatch)
    monkeypatch.setattr(cli_handler, "check_issue_for_duplicate", lambda *args, **kwargs: None)
    assert main(_main_args("--check-issue", "7")) == 1
    assert "Duplicate detection comment not found" in capsys.readouterr().out

    monkeypatch.setattr(cli_handler, "check_issue_for_no_duplicate", lambda *args, **kwargs: True)
    assert main(_main_args("--check-unique", "7")) == 0
    assert "Unique issue accepted" in capsys.readouterr().out

    match = MagicMock(number=9, title="Matching", url=None)
    monkeypatch.setattr(cli_handler, "collect_matching_issues", lambda *args, **kwargs: [match])
    assert main(_main_args("--list-issues", "--find-issue", "match")) == 0
    assert "#9 Matching (unknown)" in capsys.readouterr().out

    assert main(_main_args("--title", "Demo", "--body", "Body", "--dry-run")) == 0
    assert ast.literal_eval(capsys.readouterr().out.strip()) == {"title": "Demo", "body": "Body"}


def test_main_creates_issue_after_confirmation_with_the_requested_arguments(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _with_token(monkeypatch)
    monkeypatch.setattr(cli_handler, "_confirm_issue_creation", lambda *args, **kwargs: True)
    create_issue = MagicMock(return_value={"html_url": "https://example.test/issues/1"})
    monkeypatch.setattr(cli_handler.api_client, "create_issue", create_issue)

    argv = _main_args(
        "--title",
        "Demo",
        "--body",
        "Body text",
        "--labels",
        "bug, docs",
        "--retry-attempts",
        "4",
        "--retry-backoff",
        "0.5",
        "--yes",
    )
    assert main(argv) == 0

    assert "Issue created: https://example.test/issues/1" in capsys.readouterr().out
    create_issue.assert_called_once_with(
        "owner/repo",
        "token",
        "Demo",
        "Body text",
        ["bug", "docs"],
        retry_attempts=4,
        retry_backoff=0.5,
    )


def test_main_does_not_create_an_issue_when_confirmation_is_declined(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _with_token(monkeypatch)
    create_issue = MagicMock()
    monkeypatch.setattr(cli_handler, "_confirm_issue_creation", lambda *args, **kwargs: False)
    monkeypatch.setattr(cli_handler.api_client, "create_issue", create_issue)

    assert main(_main_args("--title", "Demo")) == 1

    assert "Issue creation cancelled." in capsys.readouterr().err
    create_issue.assert_not_called()


def test_main_requires_a_title_or_a_source_issue(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _with_token(monkeypatch)

    assert main(_main_args()) == 1

    assert "Either --source-issue/--find-issue or --title is required." in capsys.readouterr().err


def test_main_check_issue_requires_the_expected_duplicate_link(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _with_token(monkeypatch)
    comment = {
        "body": "Possible duplicates:\n- #5 - Other issue (https://github.com/owner/repo/issues/5)",
        "html_url": "https://example.test/comments/1",
    }
    monkeypatch.setattr(cli_handler, "check_issue_for_duplicate", lambda *args, **kwargs: comment)

    assert main(_main_args("--check-issue", "7", "--expected-issue-number", "9")) == 1
    assert "Expected duplicate link not found." in capsys.readouterr().err

    assert main(_main_args("--check-issue", "7", "--expected-issue-number", "5")) == 0
    assert "Duplicate detection comment found: https://example.test/comments/1" in (
        capsys.readouterr().out
    )


def test_main_check_unique_fails_when_a_duplicate_comment_exists(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _with_token(monkeypatch)
    monkeypatch.setattr(cli_handler, "check_issue_for_no_duplicate", lambda *args, **kwargs: False)

    assert main(_main_args("--check-unique", "7")) == 1

    assert "unique check failed" in capsys.readouterr().out


def test_main_list_issues_fails_when_nothing_matches(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _with_token(monkeypatch)
    monkeypatch.setattr(cli_handler, "collect_matching_issues", lambda *args, **kwargs: [])

    assert main(_main_args("--list-issues", "--find-issue", "nothing")) == 1

    assert "No matching source issue found." in capsys.readouterr().err


# =============================================================================
# _parse_labels tests
# =============================================================================


class TestParseLabels:
    """Tests for _parse_labels()."""

    def test_parse_labels_none(self) -> None:
        """None input returns None."""
        assert _parse_labels(None) is None

    def test_parse_labels_empty_string(self) -> None:
        """Empty string returns None."""
        assert _parse_labels("") is None

    def test_parse_labels_whitespace_only(self) -> None:
        """Whitespace-only string returns None."""
        assert _parse_labels("   ") is None

    def test_parse_labels_single_label(self) -> None:
        """Single label is returned as list."""
        result = _parse_labels("bug")
        assert result == ["bug"]

    def test_parse_labels_multiple_labels(self) -> None:
        """Multiple comma-separated labels are parsed."""
        result = _parse_labels("bug,enhancement,critical")
        assert result == ["bug", "enhancement", "critical"]

    def test_parse_labels_with_whitespace(self) -> None:
        """Labels with surrounding whitespace are trimmed."""
        result = _parse_labels("  bug  ,  enhancement  ,  critical  ")
        assert result == ["bug", "enhancement", "critical"]

    def test_parse_labels_skips_empty_entries(self) -> None:
        """Empty entries from consecutive commas are skipped."""
        result = _parse_labels("bug,,enhancement,,,critical,")
        assert result == ["bug", "enhancement", "critical"]

    def test_parse_labels_skips_whitespace_only_entries(self) -> None:
        """Entries with only whitespace are skipped."""
        result = _parse_labels("bug,   ,enhancement,  ,critical")
        assert result == ["bug", "enhancement", "critical"]


# =============================================================================
# _parse_allowlist tests
# =============================================================================


class TestParseAllowlist:
    """Tests for _parse_allowlist()."""

    def test_parse_allowlist_none(self) -> None:
        """None input returns empty set."""
        assert _parse_allowlist(None) == set()

    def test_parse_allowlist_empty_string(self) -> None:
        """Empty string returns empty set."""
        assert _parse_allowlist("") == set()

    def test_parse_allowlist_whitespace_only(self) -> None:
        """Whitespace-only string returns empty set."""
        assert _parse_allowlist("   ") == set()

    def test_parse_allowlist_single_entry(self) -> None:
        """Single entry is returned as set."""
        result = _parse_allowlist("owner/repo")
        assert result == {"owner/repo"}

    def test_parse_allowlist_multiple_entries(self) -> None:
        """Multiple comma-separated entries are parsed."""
        result = _parse_allowlist("owner1/repo1,owner2/repo2,owner3/repo3")
        assert result == {"owner1/repo1", "owner2/repo2", "owner3/repo3"}

    def test_parse_allowlist_with_whitespace(self) -> None:
        """Entries with surrounding whitespace are trimmed."""
        result = _parse_allowlist("  owner1/repo1  ,  owner2/repo2  ")
        assert result == {"owner1/repo1", "owner2/repo2"}

    def test_parse_allowlist_skips_empty_entries(self) -> None:
        """Empty entries from consecutive commas are skipped."""
        result = _parse_allowlist("owner1/repo1,,owner2/repo2,,,owner3/repo3,")
        assert result == {"owner1/repo1", "owner2/repo2", "owner3/repo3"}

    def test_parse_allowlist_skips_whitespace_only_entries(self) -> None:
        """Entries with only whitespace are skipped."""
        result = _parse_allowlist("owner1/repo1,   ,owner2/repo2,  ,owner3/repo3")
        assert result == {"owner1/repo1", "owner2/repo2", "owner3/repo3"}


# =============================================================================
# _parse_scopes tests
# =============================================================================


class TestParseScopes:
    """Tests for _parse_scopes()."""

    def test_parse_scopes_none(self) -> None:
        """None input returns empty set."""
        assert _parse_scopes(None) == set()

    def test_parse_scopes_empty_string(self) -> None:
        """Empty string returns empty set."""
        assert _parse_scopes("") == set()

    def test_parse_scopes_whitespace_only(self) -> None:
        """Whitespace-only string returns empty set."""
        assert _parse_scopes("   ") == set()

    def test_parse_scopes_single_scope(self) -> None:
        """Single scope is returned as set."""
        result = _parse_scopes("repo")
        assert result == {"repo"}

    def test_parse_scopes_multiple_scopes(self) -> None:
        """Multiple comma-separated scopes are parsed."""
        result = _parse_scopes("repo,workflow,read:org")
        assert result == {"repo", "workflow", "read:org"}

    def test_parse_scopes_with_whitespace(self) -> None:
        """Scopes with surrounding whitespace are trimmed."""
        result = _parse_scopes("  repo  ,  workflow  ,  read:org  ")
        assert result == {"repo", "workflow", "read:org"}

    def test_parse_scopes_skips_empty_entries(self) -> None:
        """Empty entries from consecutive commas are skipped."""
        result = _parse_scopes("repo,,workflow,,,read:org,")
        assert result == {"repo", "workflow", "read:org"}

    def test_parse_scopes_skips_whitespace_only_entries(self) -> None:
        """Entries with only whitespace are skipped."""
        result = _parse_scopes("repo,   ,workflow,  ,read:org")
        assert result == {"repo", "workflow", "read:org"}


# =============================================================================
# _load_config tests
# =============================================================================


class TestLoadConfig:
    """Tests for _load_config()."""

    def test_load_config_missing_path_and_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns empty dict when both path and env var are missing."""
        monkeypatch.delenv("ISSUE_DEDUP_SMOKE_CONFIG", raising=False)
        result = _load_config(None, "ISSUE_DEDUP_SMOKE_CONFIG")
        assert result == {}

    def test_load_config_missing_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Returns empty dict when config file doesn't exist."""
        nonexistent = tmp_path / "nonexistent.json"
        monkeypatch.setenv("ISSUE_DEDUP_SMOKE_CONFIG", str(nonexistent))
        result = _load_config(None, "ISSUE_DEDUP_SMOKE_CONFIG")
        assert result == {}

    def test_load_config_invalid_json(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Returns empty dict for invalid JSON, prints error."""
        config_file = tmp_path / "config.json"
        config_file.write_text("{ invalid json }")
        monkeypatch.setenv("ISSUE_DEDUP_SMOKE_CONFIG", str(config_file))
        result = _load_config(None, "ISSUE_DEDUP_SMOKE_CONFIG")
        assert result == {}
        captured = capsys.readouterr()
        assert "Invalid config JSON" in captured.err

    def test_load_config_non_object_json(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Returns empty dict for non-object JSON, prints error."""
        config_file = tmp_path / "config.json"
        config_file.write_text('["not", "an", "object"]')
        monkeypatch.setenv("ISSUE_DEDUP_SMOKE_CONFIG", str(config_file))
        result = _load_config(None, "ISSUE_DEDUP_SMOKE_CONFIG")
        assert result == {}
        captured = capsys.readouterr()
        assert "Config must be a JSON object" in captured.err

    def test_load_config_valid_object_json(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Returns parsed dict for valid object JSON."""
        config_file = tmp_path / "config.json"
        config_data = {"allowlist": ["owner/repo"], "allowed_scopes": ["repo", "workflow"]}
        config_file.write_text(json.dumps(config_data))
        monkeypatch.setenv("ISSUE_DEDUP_SMOKE_CONFIG", str(config_file))
        result = _load_config(None, "ISSUE_DEDUP_SMOKE_CONFIG")
        assert result == config_data

    def test_load_config_explicit_path(self, tmp_path: Path) -> None:
        """Uses explicit path when provided."""
        config_file = tmp_path / "config.json"
        config_data = {"allowlist": ["owner/repo"]}
        config_file.write_text(json.dumps(config_data))
        result = _load_config(str(config_file), "ISSUE_DEDUP_SMOKE_CONFIG")
        assert result == config_data

    def test_load_config_path_takes_precedence(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Explicit path takes precedence over env var."""
        config_file1 = tmp_path / "config1.json"
        config_file2 = tmp_path / "config2.json"
        config_file1.write_text(json.dumps({"key": "from_path"}))
        config_file2.write_text(json.dumps({"key": "from_env"}))
        monkeypatch.setenv("ISSUE_DEDUP_SMOKE_CONFIG", str(config_file2))
        result = _load_config(str(config_file1), "ISSUE_DEDUP_SMOKE_CONFIG")
        assert result == {"key": "from_path"}


# =============================================================================
# _load_allowlist tests
# =============================================================================


class TestLoadAllowlist:
    """Tests for _load_allowlist()."""

    def test_load_allowlist_cli_value_precedence(self) -> None:
        """CLI value takes precedence over env and config."""
        config = {"allowlist": ["from_config"]}
        result = _load_allowlist("cli_value", "ALLOWLIST_ENV", config)
        assert result == {"cli_value"}

    def test_load_allowlist_env_value_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Env var value takes precedence over config when CLI is None."""
        monkeypatch.setenv("ALLOWLIST_ENV", "env_value")
        config = {"allowlist": ["from_config"]}
        result = _load_allowlist(None, "ALLOWLIST_ENV", config)
        assert result == {"env_value"}

    def test_load_allowlist_list_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """List config is used when CLI and env are None."""
        monkeypatch.delenv("ALLOWLIST_ENV", raising=False)
        config = {"allowlist": ["repo1", "repo2", "repo3"]}
        result = _load_allowlist(None, "ALLOWLIST_ENV", config)
        assert result == {"repo1", "repo2", "repo3"}

    def test_load_allowlist_string_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """String config is parsed when CLI and env are None."""
        monkeypatch.delenv("ALLOWLIST_ENV", raising=False)
        config = {"allowlist": "repo1,repo2,repo3"}
        result = _load_allowlist(None, "ALLOWLIST_ENV", config)
        assert result == {"repo1", "repo2", "repo3"}

    def test_load_allowlist_empty_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns empty set when all sources are missing."""
        monkeypatch.delenv("ALLOWLIST_ENV", raising=False)
        config = {}
        result = _load_allowlist(None, "ALLOWLIST_ENV", config)
        assert result == set()

    def test_load_allowlist_list_config_with_empty_strings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """List config with empty strings is filtered."""
        monkeypatch.delenv("ALLOWLIST_ENV", raising=False)
        config = {"allowlist": ["repo1", "", "  ", "repo2"]}
        result = _load_allowlist(None, "ALLOWLIST_ENV", config)
        assert result == {"repo1", "repo2"}

    def test_load_allowlist_list_config_with_non_strings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """List config with non-string entries is converted to strings."""
        monkeypatch.delenv("ALLOWLIST_ENV", raising=False)
        config = {"allowlist": ["repo1", 123, None, "repo2"]}
        result = _load_allowlist(None, "ALLOWLIST_ENV", config)
        # None becomes "None" as string, which is not empty
        assert result == {"repo1", "123", "None", "repo2"}

    def test_load_allowlist_cli_empty_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty string CLI value falls through to env."""
        monkeypatch.setenv("ALLOWLIST_ENV", "from_env")
        config = {}
        # Empty string is falsy in _parse_allowlist
        result = _load_allowlist("", "ALLOWLIST_ENV", config)
        assert result == {"from_env"}


# =============================================================================
# _load_allowed_scopes tests
# =============================================================================


class TestLoadAllowedScopes:
    """Tests for _load_allowed_scopes()."""

    def test_load_allowed_scopes_cli_value_precedence(self) -> None:
        """CLI value takes precedence over env and config."""
        config = {"allowed_scopes": ["from_config"]}
        result = _load_allowed_scopes("cli_value", "SCOPES_ENV", config)
        assert result == {"cli_value"}

    def test_load_allowed_scopes_env_value_precedence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Env var value takes precedence over config when CLI is None."""
        monkeypatch.setenv("SCOPES_ENV", "env_value")
        config = {"allowed_scopes": ["from_config"]}
        result = _load_allowed_scopes(None, "SCOPES_ENV", config)
        assert result == {"env_value"}

    def test_load_allowed_scopes_list_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """List config is used when CLI and env are None."""
        monkeypatch.delenv("SCOPES_ENV", raising=False)
        config = {"allowed_scopes": ["scope1", "scope2", "scope3"]}
        result = _load_allowed_scopes(None, "SCOPES_ENV", config)
        assert result == {"scope1", "scope2", "scope3"}

    def test_load_allowed_scopes_string_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """String config is parsed when CLI and env are None."""
        monkeypatch.delenv("SCOPES_ENV", raising=False)
        config = {"allowed_scopes": "scope1,scope2,scope3"}
        result = _load_allowed_scopes(None, "SCOPES_ENV", config)
        assert result == {"scope1", "scope2", "scope3"}

    def test_load_allowed_scopes_empty_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns empty set when all sources are missing."""
        monkeypatch.delenv("SCOPES_ENV", raising=False)
        config = {}
        result = _load_allowed_scopes(None, "SCOPES_ENV", config)
        assert result == set()

    def test_load_allowed_scopes_list_config_with_empty_strings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """List config with empty strings is filtered."""
        monkeypatch.delenv("SCOPES_ENV", raising=False)
        config = {"allowed_scopes": ["scope1", "", "  ", "scope2"]}
        result = _load_allowed_scopes(None, "SCOPES_ENV", config)
        assert result == {"scope1", "scope2"}

    def test_load_allowed_scopes_list_config_with_non_strings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """List config with non-string entries is converted to strings."""
        monkeypatch.delenv("SCOPES_ENV", raising=False)
        config = {"allowed_scopes": ["scope1", 123, None, "scope2"]}
        result = _load_allowed_scopes(None, "SCOPES_ENV", config)
        # None becomes "None" as string, which is not empty
        assert result == {"scope1", "123", "None", "scope2"}


# =============================================================================
# _confirm_issue_creation tests
# =============================================================================


class TestConfirmIssueCreation:
    """Tests for _confirm_issue_creation()."""

    def test_confirm_issue_creation_assume_yes(self) -> None:
        """Returns True immediately when assume_yes is True."""
        result = _confirm_issue_creation("owner/repo", "Test title", assume_yes=True)
        assert result is True

    def test_confirm_issue_creation_non_tty_refusal(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Returns False and prints message when not a TTY."""
        # Create a mock stdin that is not a tty
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False

        with patch.object(sys, "stdin", mock_stdin):
            result = _confirm_issue_creation("owner/repo", "Test title", assume_yes=False)
            assert result is False
            captured = capsys.readouterr()
            assert "Confirmation required" in captured.err

    def test_confirm_issue_creation_tty_yes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns True when user responds 'y' on TTY."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True

        with patch.object(sys, "stdin", mock_stdin), patch("builtins.input", return_value="y"):
            result = _confirm_issue_creation("owner/repo", "Test title", assume_yes=False)
            assert result is True

    def test_confirm_issue_creation_tty_yes_uppercase(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns True when user responds 'Y' on TTY."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True

        with patch.object(sys, "stdin", mock_stdin), patch("builtins.input", return_value="Y"):
            result = _confirm_issue_creation("owner/repo", "Test title", assume_yes=False)
            assert result is True

    def test_confirm_issue_creation_tty_yes_full(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns True when user responds 'yes' on TTY."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True

        with patch.object(sys, "stdin", mock_stdin), patch("builtins.input", return_value="yes"):
            result = _confirm_issue_creation("owner/repo", "Test title", assume_yes=False)
            assert result is True

    def test_confirm_issue_creation_tty_no(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns False when user responds 'n' on TTY."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True

        with patch.object(sys, "stdin", mock_stdin), patch("builtins.input", return_value="n"):
            result = _confirm_issue_creation("owner/repo", "Test title", assume_yes=False)
            assert result is False

    def test_confirm_issue_creation_tty_no_full(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns False when user responds 'no' on TTY."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True

        with patch.object(sys, "stdin", mock_stdin), patch("builtins.input", return_value="no"):
            result = _confirm_issue_creation("owner/repo", "Test title", assume_yes=False)
            assert result is False

    def test_confirm_issue_creation_tty_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns False when user responds empty string on TTY."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True

        with patch.object(sys, "stdin", mock_stdin), patch("builtins.input", return_value=""):
            result = _confirm_issue_creation("owner/repo", "Test title", assume_yes=False)
            assert result is False

    def test_confirm_issue_creation_tty_random_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns False when user responds with non-yes text on TTY."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True

        with patch.object(sys, "stdin", mock_stdin), patch("builtins.input", return_value="maybe"):
            result = _confirm_issue_creation("owner/repo", "Test title", assume_yes=False)
            assert result is False

    def test_confirm_issue_creation_tty_whitespace_yes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns True when user responds with whitespace-padded 'y' on TTY."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True

        with patch.object(sys, "stdin", mock_stdin), patch("builtins.input", return_value="  y  "):
            result = _confirm_issue_creation("owner/repo", "Test title", assume_yes=False)
            assert result is True
