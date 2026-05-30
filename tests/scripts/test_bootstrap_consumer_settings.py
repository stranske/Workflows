from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from scripts import bootstrap_consumer_settings as bcs


def test_split_repo_parses_owner_and_name() -> None:
    assert bcs._split_repo("stranske/Foo") == ("stranske", "Foo")


@pytest.mark.parametrize("bad", ["", "foo", "owner/", "/name", "a/b/c"])
def test_split_repo_rejects_malformed(bad: str) -> None:
    with pytest.raises(SystemExit, match="owner/name"):
        bcs._split_repo(bad)


def test_default_keepalive_logins_is_owner() -> None:
    assert bcs._default_keepalive_logins("stranske/Bar") == "stranske"


def test_plan_has_all_four_bootstrap_operations_in_order() -> None:
    plan = bcs.build_bootstrap_plan("stranske/Foo")
    assert [op["id"] for op in plan] == [
        "workflow_permissions",
        "var_use_consolidated_workflows",
        "var_allowed_keepalive_logins",
        "bot_collaborator",
    ]


def test_plan_workflow_permissions_command_matches_checklist() -> None:
    plan = bcs.build_bootstrap_plan("stranske/Foo")
    cmd = plan[0]["command"]
    # SETUP_CHECKLIST.md 3.3.1: gh api -X PUT .../actions/permissions/workflow
    assert cmd == [
        "gh",
        "api",
        "--method",
        "PUT",
        "/repos/stranske/Foo/actions/permissions/workflow",
        "-F",
        "default_workflow_permissions=write",
        "-F",
        "can_approve_pull_request_reviews=true",
    ]


def test_plan_sets_use_consolidated_workflows_true() -> None:
    plan = bcs.build_bootstrap_plan("stranske/Foo")
    cmd = plan[1]["command"]
    assert cmd[:3] == ["gh", "variable", "set"]
    assert cmd[3] == "USE_CONSOLIDATED_WORKFLOWS"
    assert "--body" in cmd and cmd[cmd.index("--body") + 1] == "true"
    assert "--repo" in cmd and cmd[cmd.index("--repo") + 1] == "stranske/Foo"


def test_plan_defaults_allowed_keepalive_logins_to_owner() -> None:
    plan = bcs.build_bootstrap_plan("stranske/Foo")
    cmd = plan[2]["command"]
    assert cmd[3] == "ALLOWED_KEEPALIVE_LOGINS"
    assert cmd[cmd.index("--body") + 1] == "stranske"


def test_plan_keepalive_logins_override_is_honored() -> None:
    plan = bcs.build_bootstrap_plan("stranske/Foo", keepalive_logins="stranske,octocat")
    cmd = plan[2]["command"]
    assert cmd[cmd.index("--body") + 1] == "stranske,octocat"


def test_plan_collaborator_command_uses_default_bot_and_push() -> None:
    plan = bcs.build_bootstrap_plan("stranske/Foo")
    cmd = plan[3]["command"]
    assert cmd == [
        "gh",
        "api",
        "--method",
        "PUT",
        f"/repos/stranske/Foo/collaborators/{bcs.DEFAULT_BOT}",
        "-f",
        "permission=push",
    ]


def test_plan_collaborator_bot_override_is_honored() -> None:
    plan = bcs.build_bootstrap_plan("stranske/Foo", bot="other-bot")
    cmd = plan[3]["command"]
    assert cmd[4] == "/repos/stranske/Foo/collaborators/other-bot"


def test_build_plan_rejects_malformed_repo() -> None:
    with pytest.raises(SystemExit, match="owner/name"):
        bcs.build_bootstrap_plan("not-a-repo")


def test_format_command_quotes_parts() -> None:
    formatted = bcs._format_command(["gh", "variable", "set", "X", "--body", "a b"])
    assert formatted == "gh variable set X --body 'a b'"


# ---------------------------------------------------------------------------
# main() tests
# ---------------------------------------------------------------------------


def test_main_dry_run_prints_commands(capsys: pytest.CaptureFixture[str]) -> None:
    """Default (no --execute) prints commands without running them."""
    with patch("sys.argv", ["bcs", "--repo", "stranske/Foo"]):
        rc = bcs.main()
    assert rc == 0
    out = capsys.readouterr().out
    # All four operation descriptions should appear
    assert "default_workflow_permissions=write" in out
    assert "USE_CONSOLIDATED_WORKFLOWS" in out
    assert "ALLOWED_KEEPALIVE_LOGINS" in out
    assert bcs.DEFAULT_BOT in out
    # Commands should be printed as shell-escaped strings, not executed
    assert "gh api" in out
    assert "gh variable set" in out


def test_main_dry_run_does_not_call_subprocess(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch("sys.argv", ["bcs", "--repo", "stranske/Foo"]),
        patch("subprocess.run") as mock_run,
    ):
        bcs.main()
        mock_run.assert_not_called()


def test_main_execute_runs_all_four_commands() -> None:
    """--execute calls subprocess.run for each of the four bootstrap operations."""
    with (
        patch("sys.argv", ["bcs", "--repo", "stranske/Foo", "--execute"]),
        patch("subprocess.run") as mock_run,
    ):
        rc = bcs.main()
    assert rc == 0
    assert mock_run.call_count == 4


def test_main_execute_workflow_permissions_command() -> None:
    """--execute first call sets workflow permissions."""
    with (
        patch("sys.argv", ["bcs", "--repo", "stranske/Foo", "--execute"]),
        patch("subprocess.run") as mock_run,
    ):
        bcs.main()
    first_cmd = mock_run.call_args_list[0][0][0]
    assert first_cmd[3] == "PUT"
    assert "/repos/stranske/Foo/actions/permissions/workflow" in first_cmd[4]
    assert "default_workflow_permissions=write" in first_cmd


def test_main_execute_sets_use_consolidated_workflows() -> None:
    """--execute second call sets USE_CONSOLIDATED_WORKFLOWS=true."""
    with (
        patch("sys.argv", ["bcs", "--repo", "stranske/Foo", "--execute"]),
        patch("subprocess.run") as mock_run,
    ):
        bcs.main()
    second_cmd = mock_run.call_args_list[1][0][0]
    assert "USE_CONSOLIDATED_WORKFLOWS" in second_cmd
    assert "true" in second_cmd


def test_main_execute_sets_allowed_keepalive_logins() -> None:
    """--execute third call sets ALLOWED_KEEPALIVE_LOGINS to repo owner."""
    with (
        patch("sys.argv", ["bcs", "--repo", "stranske/Foo", "--execute"]),
        patch("subprocess.run") as mock_run,
    ):
        bcs.main()
    third_cmd = mock_run.call_args_list[2][0][0]
    assert "ALLOWED_KEEPALIVE_LOGINS" in third_cmd
    assert "stranske" in third_cmd


def test_main_execute_keepalive_logins_override() -> None:
    """--keepalive-logins overrides the default owner-derived value."""
    with (
        patch(
            "sys.argv",
            ["bcs", "--repo", "stranske/Foo", "--execute", "--keepalive-logins", "alice,bob"],
        ),
        patch("subprocess.run") as mock_run,
    ):
        bcs.main()
    third_cmd = mock_run.call_args_list[2][0][0]
    assert "alice,bob" in third_cmd


def test_main_execute_sends_bot_collaborator_invite() -> None:
    """--execute fourth call invites the bot as push collaborator."""
    with (
        patch("sys.argv", ["bcs", "--repo", "stranske/Foo", "--execute"]),
        patch("subprocess.run") as mock_run,
    ):
        bcs.main()
    fourth_cmd = mock_run.call_args_list[3][0][0]
    assert bcs.DEFAULT_BOT in fourth_cmd[4]
    assert "permission=push" in fourth_cmd


def test_main_execute_bot_override() -> None:
    """--bot overrides DEFAULT_BOT in the collaborator invite."""
    with (
        patch("sys.argv", ["bcs", "--repo", "stranske/Foo", "--execute", "--bot", "other-bot"]),
        patch("subprocess.run") as mock_run,
    ):
        bcs.main()
    fourth_cmd = mock_run.call_args_list[3][0][0]
    assert "other-bot" in fourth_cmd[4]


def test_main_check_reads_workflow_permissions(capsys: pytest.CaptureFixture[str]) -> None:
    """--check calls the read endpoint and prints the result."""
    fake_result = MagicMock()
    fake_result.stdout = (
        '{"default_workflow_permissions":"write","can_approve_pull_request_reviews":true}'
    )
    with (
        patch("sys.argv", ["bcs", "--repo", "stranske/Foo", "--check"]),
        patch("subprocess.run", return_value=fake_result) as mock_run,
    ):
        rc = bcs.main()
    assert rc == 0
    mock_run.assert_called_once()
    called_cmd = mock_run.call_args[0][0]
    assert "/repos/stranske/Foo/actions/permissions/workflow" in called_cmd
    out = capsys.readouterr().out
    assert "default_workflow_permissions" in out


def test_main_execute_and_check_are_mutually_exclusive() -> None:
    """Passing both --execute and --check raises SystemExit."""
    with (
        patch("sys.argv", ["bcs", "--repo", "stranske/Foo", "--execute", "--check"]),
        pytest.raises(SystemExit, match="Choose only one"),
    ):
        bcs.main()


def test_main_missing_repo_raises_system_exit() -> None:
    """Missing --repo causes argparse to exit."""
    with patch("sys.argv", ["bcs"]), pytest.raises(SystemExit):
        bcs.main()


def test_main_execute_check_and_verify_are_mutually_exclusive() -> None:
    """Combining any two of --execute, --check, --verify raises SystemExit."""
    for combo in [
        ["--execute", "--check"],
        ["--execute", "--verify"],
        ["--check", "--verify"],
    ]:
        with (
            patch("sys.argv", ["bcs", "--repo", "stranske/Foo"] + combo),
            pytest.raises(SystemExit, match="Choose only one"),
        ):
            bcs.main()


# ---------------------------------------------------------------------------
# verify_bootstrap_settings() tests
# ---------------------------------------------------------------------------


def _make_proc(stdout: str = "", returncode: int = 0) -> object:
    """Build a minimal mock subprocess result."""
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    return m


def _perms_json(write: bool = True, approve: bool = True) -> str:
    import json

    return json.dumps(
        {
            "default_workflow_permissions": "write" if write else "read",
            "can_approve_pull_request_reviews": approve,
        }
    )


def _vars_json(
    consolidated: str = "true",
    keepalive: str = "stranske",
) -> str:
    import json

    return json.dumps(
        [
            {"name": "USE_CONSOLIDATED_WORKFLOWS", "value": consolidated},
            {"name": "ALLOWED_KEEPALIVE_LOGINS", "value": keepalive},
        ]
    )


def _all_ok_side_effect(*args, **kwargs):
    """Return a successful mock result for any subprocess call."""
    cmd = args[0]
    cmd_str = " ".join(cmd)
    if "actions/permissions/workflow" in cmd_str and "variable" not in cmd_str:
        return _make_proc(_perms_json())
    if "variable list" in cmd_str:
        return _make_proc(_vars_json())
    # collaborator check
    return _make_proc("")


def test_verify_all_settings_ok() -> None:
    with patch("subprocess.run", side_effect=_all_ok_side_effect):
        result = bcs.verify_bootstrap_settings("stranske/Foo")
    assert result == {
        "workflow_permissions": True,
        "var_use_consolidated_workflows": True,
        "var_allowed_keepalive_logins": True,
        "bot_collaborator": True,
    }


def test_verify_workflow_permissions_wrong_value() -> None:
    def side_effect(*args, **kwargs):
        cmd_str = " ".join(args[0])
        if "actions/permissions/workflow" in cmd_str and "variable" not in cmd_str:
            return _make_proc(_perms_json(write=False))
        if "variable list" in cmd_str:
            return _make_proc(_vars_json())
        return _make_proc("")

    with patch("subprocess.run", side_effect=side_effect):
        result = bcs.verify_bootstrap_settings("stranske/Foo")
    assert result["workflow_permissions"] is False
    assert result["var_use_consolidated_workflows"] is True


def test_verify_workflow_permissions_api_failure() -> None:
    """When the permissions endpoint returns non-zero, workflow_permissions is False."""

    def side_effect(*args, **kwargs):
        cmd_str = " ".join(args[0])
        if "actions/permissions/workflow" in cmd_str and "variable" not in cmd_str:
            raise subprocess.CalledProcessError(1, args[0])
        if "variable list" in cmd_str:
            return _make_proc(_vars_json())
        return _make_proc("")

    with patch("subprocess.run", side_effect=side_effect):
        result = bcs.verify_bootstrap_settings("stranske/Foo")
    assert result["workflow_permissions"] is False
    assert result["var_use_consolidated_workflows"] is True


def test_verify_collaborator_not_yet_accepted() -> None:
    """Collaborator check returns False when gh api returns non-zero (invite pending)."""

    def side_effect(*args, **kwargs):
        cmd_str = " ".join(args[0])
        if "collaborators" in cmd_str:
            raise subprocess.CalledProcessError(1, args[0])
        if "actions/permissions/workflow" in cmd_str:
            return _make_proc(_perms_json())
        if "variable list" in cmd_str:
            return _make_proc(_vars_json())
        return _make_proc("")

    with patch("subprocess.run", side_effect=side_effect):
        result = bcs.verify_bootstrap_settings("stranske/Foo")
    assert result["bot_collaborator"] is False


def test_verify_variable_api_failure() -> None:
    """When variable list fails, both variable checks return False."""

    def side_effect(*args, **kwargs):
        cmd_str = " ".join(args[0])
        if "variable" in cmd_str:
            raise subprocess.CalledProcessError(1, args[0])
        if "actions/permissions/workflow" in cmd_str:
            return _make_proc(_perms_json())
        return _make_proc("")

    with patch("subprocess.run", side_effect=side_effect):
        result = bcs.verify_bootstrap_settings("stranske/Foo")
    assert result["var_use_consolidated_workflows"] is False
    assert result["var_allowed_keepalive_logins"] is False


def test_verify_keepalive_logins_override() -> None:
    """--keepalive-logins override is passed through to verify comparison."""

    def side_effect(*args, **kwargs):
        cmd_str = " ".join(args[0])
        if "actions/permissions/workflow" in cmd_str and "variable" not in cmd_str:
            return _make_proc(_perms_json())
        if "variable list" in cmd_str:
            return _make_proc(_vars_json(keepalive="alice,bob"))
        return _make_proc("")

    with patch("subprocess.run", side_effect=side_effect):
        result = bcs.verify_bootstrap_settings("stranske/Foo", keepalive_logins="alice,bob")
    assert result["var_allowed_keepalive_logins"] is True


def test_verify_bot_override() -> None:
    """--bot override reaches the collaborator check command."""
    calls = []

    def side_effect(*args, **kwargs):
        calls.append(args[0])
        cmd_str = " ".join(args[0])
        if "actions/permissions/workflow" in cmd_str and "variable" not in cmd_str:
            return _make_proc(_perms_json())
        if "variable list" in cmd_str:
            return _make_proc(_vars_json())
        return _make_proc("")

    with patch("subprocess.run", side_effect=side_effect):
        bcs.verify_bootstrap_settings("stranske/Foo", bot="custom-bot")
    collab_calls = [c for c in calls if "collaborators" in " ".join(c)]
    assert len(collab_calls) == 1
    assert "custom-bot" in collab_calls[0][-1]


# ---------------------------------------------------------------------------
# main() --verify flag tests
# ---------------------------------------------------------------------------


def test_main_verify_all_ok_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch("sys.argv", ["bcs", "--repo", "stranske/Foo", "--verify"]),
        patch(
            "scripts.bootstrap_consumer_settings.verify_bootstrap_settings",
            return_value={
                "workflow_permissions": True,
                "var_use_consolidated_workflows": True,
                "var_allowed_keepalive_logins": True,
                "bot_collaborator": True,
            },
        ),
    ):
        rc = bcs.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "[OK]" in out
    assert "bot_collaborator" in out


def test_main_verify_partial_failure_exits_one(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch("sys.argv", ["bcs", "--repo", "stranske/Foo", "--verify"]),
        patch(
            "scripts.bootstrap_consumer_settings.verify_bootstrap_settings",
            return_value={
                "workflow_permissions": True,
                "var_use_consolidated_workflows": True,
                "var_allowed_keepalive_logins": True,
                "bot_collaborator": False,
            },
        ),
    ):
        rc = bcs.main()
    assert rc == 1
    out = capsys.readouterr().out
    assert "[FAIL]" in out
    assert "bot_collaborator" in out


def test_main_verify_passes_bot_and_keepalive_overrides() -> None:
    with (
        patch(
            "sys.argv",
            [
                "bcs",
                "--repo",
                "stranske/Foo",
                "--verify",
                "--bot",
                "custom-bot",
                "--keepalive-logins",
                "alice",
            ],
        ),
        patch(
            "scripts.bootstrap_consumer_settings.verify_bootstrap_settings",
            return_value={
                "workflow_permissions": True,
                "var_use_consolidated_workflows": True,
                "var_allowed_keepalive_logins": True,
                "bot_collaborator": True,
            },
        ) as mock_verify,
    ):
        bcs.main()
    mock_verify.assert_called_once_with(
        "stranske/Foo",
        bot="custom-bot",
        keepalive_logins="alice",
    )
