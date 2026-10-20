from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from scripts import bootstrap_consumer_settings as bcs


@pytest.mark.parametrize(
    ("repo", "expected"),
    [
        ("stranske/Foo", ("stranske", "Foo")),
        ("  stranske/Foo  ", ("stranske", "Foo")),
    ],
)
def test_split_repo_parses_owner_and_name(repo: str, expected: tuple[str, str]) -> None:
    assert bcs._split_repo(repo) == expected


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "foo",
        "owner/",
        "/name",
        "a/b/c",
        "owner/repo;touch-pwned",
        "owner/repo name",
        "owner/repo\n--help",
    ],
)
def test_split_repo_rejects_malformed(bad: str) -> None:
    with pytest.raises(SystemExit, match="owner/name"):
        bcs._split_repo(bad)


def test_default_keepalive_logins_is_owner() -> None:
    assert bcs._default_keepalive_logins("stranske/Bar") == "stranske"


def test_workflow_permissions_command_matches_checklist() -> None:
    assert bcs._workflow_permissions_command("stranske/Foo") == [
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


def test_variable_command_sets_repo_variable_without_shell_execution() -> None:
    assert bcs._variable_command("stranske/Foo", "ALLOWED_KEEPALIVE_LOGINS", "alice,bob") == [
        "gh",
        "variable",
        "set",
        "ALLOWED_KEEPALIVE_LOGINS",
        "--repo",
        "stranske/Foo",
        "--body",
        "alice,bob",
    ]


def test_collaborator_command_invites_push_collaborator() -> None:
    assert bcs._collaborator_command("stranske/Foo", "custom-bot") == [
        "gh",
        "api",
        "--method",
        "PUT",
        "/repos/stranske/Foo/collaborators/custom-bot",
        "-f",
        "permission=push",
    ]


def test_plan_has_settings_then_priority_labels_in_order() -> None:
    plan = bcs.build_bootstrap_plan("stranske/Foo")
    assert [op["id"] for op in plan] == [
        "workflow_permissions",
        "var_use_consolidated_workflows",
        "var_allowed_keepalive_logins",
        "bot_collaborator",
        "label_high",
        "label_normal",
        "label_low",
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


def test_main_execute_runs_settings_then_applies_priority_labels() -> None:
    """--execute preserves the four settings operations before label reconciliation."""
    with (
        patch("sys.argv", ["bcs", "--repo", "stranske/Foo", "--execute"]),
        patch("subprocess.run") as mock_run,
        patch("scripts.bootstrap_consumer_settings.apply_priority_labels") as mock_labels,
    ):
        rc = bcs.main()
    assert rc == 0
    assert mock_run.call_count == 4
    mock_labels.assert_called_once_with("stranske/Foo")


def test_main_execute_workflow_permissions_command() -> None:
    """--execute first call sets workflow permissions."""
    with (
        patch("sys.argv", ["bcs", "--repo", "stranske/Foo", "--execute"]),
        patch("subprocess.run") as mock_run,
        patch("scripts.bootstrap_consumer_settings.apply_priority_labels"),
    ):
        bcs.main()
    first_cmd = mock_run.call_args_list[0][0][0]
    assert first_cmd[3] == "PUT"
    assert "/repos/stranske/Foo/actions/permissions/workflow" in first_cmd[4]
    assert "default_workflow_permissions=write" in first_cmd


@pytest.mark.parametrize(
    "argv",
    [
        ["bcs"],
        ["bcs", "--repo", "x/y", "--check", "--verify"],
        ["bcs", "--repo", "x/y", "--labels-only", "--verify"],
    ],
)
def test_main_rejects_invalid_mode_combinations(argv: list[str]) -> None:
    with patch("sys.argv", argv), pytest.raises(SystemExit):
        bcs.main()


def test_main_check_verify_and_health_check(monkeypatch, tmp_path, capsys) -> None:
    result = MagicMock(stdout='{"default_workflow_permissions": "write"}')
    with (
        patch("sys.argv", ["bcs", "--repo", "x/y", "--check"]),
        patch("subprocess.run", return_value=result),
    ):
        assert bcs.main() == 0
    with (
        patch("sys.argv", ["bcs", "--repo", "x/y", "--verify"]),
        patch(
            "scripts.bootstrap_consumer_settings.verify_bootstrap_settings",
            return_value={"a": True, "b": False},
        ),
    ):
        assert bcs.main() == 1
    manifest = tmp_path / "manifest.yml"
    manifest.write_text("x", encoding="utf-8")
    with (
        patch("sys.argv", ["bcs", "--health-check", "--manifest", str(manifest)]),
        patch("scripts.bootstrap_consumer_settings.extract_repos", return_value=["x/y"]),
        patch(
            "scripts.bootstrap_consumer_settings.check_consumer_health",
            return_value=(
                [
                    {
                        "repository": "x/y",
                        "status": "OK",
                        "missing": [],
                        "metadata_mismatch": [],
                        "implementation_count": 0,
                        "priority_labelled_count": 0,
                        "unprioritized_count": 0,
                        "excluded": {},
                        "error": None,
                    }
                ],
                0,
            ),
        ),
    ):
        assert bcs.main() == 0
    assert "[FAIL] b" in capsys.readouterr().out


def test_main_execute_sets_use_consolidated_workflows() -> None:
    """--execute second call sets USE_CONSOLIDATED_WORKFLOWS=true."""
    with (
        patch("sys.argv", ["bcs", "--repo", "stranske/Foo", "--execute"]),
        patch("subprocess.run") as mock_run,
        patch("scripts.bootstrap_consumer_settings.apply_priority_labels"),
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
        patch("scripts.bootstrap_consumer_settings.apply_priority_labels"),
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
        patch("scripts.bootstrap_consumer_settings.apply_priority_labels"),
    ):
        bcs.main()
    third_cmd = mock_run.call_args_list[2][0][0]
    assert "alice,bob" in third_cmd


def test_main_execute_sends_bot_collaborator_invite() -> None:
    """--execute fourth call invites the bot as push collaborator."""
    with (
        patch("sys.argv", ["bcs", "--repo", "stranske/Foo", "--execute"]),
        patch("subprocess.run") as mock_run,
        patch("scripts.bootstrap_consumer_settings.apply_priority_labels"),
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
        patch("scripts.bootstrap_consumer_settings.apply_priority_labels"),
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


def test_verify_missing_variables_from_successful_list() -> None:
    """A successful variable-list call still fails settings absent from the payload."""

    def side_effect(*args, **kwargs):
        cmd_str = " ".join(args[0])
        if "actions/permissions/workflow" in cmd_str and "variable" not in cmd_str:
            return _make_proc(_perms_json())
        if "variable list" in cmd_str:
            return _make_proc("[]")
        return _make_proc("")

    with patch("subprocess.run", side_effect=side_effect) as mock_run:
        result = bcs.verify_bootstrap_settings("stranske/Foo")
    assert result == {
        "workflow_permissions": True,
        "var_use_consolidated_workflows": False,
        "var_allowed_keepalive_logins": False,
        "bot_collaborator": True,
    }
    assert mock_run.call_count == 3


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


@pytest.mark.parametrize(
    ("raw", "match"),
    [
        ("'unclosed", "invalid quoted label value"),
        ('"unterminated', "invalid quoted label value"),
        ("true", "label value must be text"),
        ("''", "label value is empty"),
    ],
)
def test_decode_simple_yaml_scalar_rejects_invalid_forms(
    tmp_path: Path, raw: str, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        bcs._decode_simple_yaml_scalar(raw, path=tmp_path / "labels.yml", line_number=1)


def test_decode_simple_yaml_scalar_rejects_non_text_json(tmp_path: Path) -> None:
    with (
        patch("scripts.bootstrap_consumer_settings.json.loads", return_value=123),
        pytest.raises(ValueError, match="label value must be text"),
    ):
        bcs._decode_simple_yaml_scalar('"ignored"', path=tmp_path / "labels.yml", line_number=1)


def test_load_core_label_entries_rejects_unsupported_syntax(tmp_path: Path) -> None:
    labels = tmp_path / "labels-core.yml"
    labels.write_text("- name: priority:high\n  nested:\n    bad: 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported label YAML syntax"):
        bcs._load_core_label_entries(labels)


@pytest.mark.parametrize(
    "payload",
    [
        '{"not":"a-list"}',
        '[{"number": 1}, "mixed"]',
        '[[{"number": 1}], {"number": 2}]',
        "[[1, 2]]",
    ],
)
def test_read_paginated_collection_rejects_malformed_payloads(payload: str) -> None:
    result = MagicMock(stdout=payload)
    with patch("subprocess.run", return_value=result), pytest.raises(ValueError):
        bcs._read_paginated_collection("/repos/x/y/labels")


def test_read_paginated_collection_accepts_empty_and_flat_pages() -> None:
    empty = MagicMock(stdout="[]")
    flat = MagicMock(stdout=json.dumps([{"name": "priority:high"}]))
    with patch("subprocess.run", side_effect=[empty, flat]):
        assert bcs._read_paginated_collection("/repos/x/y/labels") == []
        assert bcs._read_paginated_collection("/repos/x/y/labels") == [{"name": "priority:high"}]


def test_priority_label_inventory_rejects_malformed_names() -> None:
    with (
        patch(
            "scripts.bootstrap_consumer_settings._read_paginated_collection",
            return_value=[{"name": ""}, {"name": "ok"}],
        ),
        pytest.raises(ValueError, match="Malformed label payload"),
    ):
        bcs._priority_label_inventory("x/y")


@pytest.mark.parametrize(
    ("issue", "match"),
    [
        ({"labels": "not-a-list"}, "Issue labels must be a list"),
        ({"labels": [None]}, "Issue label entry is malformed"),
        ({"labels": [{}]}, "Issue label entry is malformed"),
    ],
)
def test_issue_labels_rejects_malformed_entries(issue: dict, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        bcs._issue_labels(issue)


def test_non_implementation_reason_covers_remaining_holders() -> None:
    with pytest.raises(ValueError, match="Issue title is missing"):
        bcs._non_implementation_reason({"labels": []})
    assert (
        bcs._non_implementation_reason(
            {
                "title": "Weekly agent metrics rollup",
                "labels": [{"name": "agent-metrics"}],
                "user": {"login": "bot"},
            }
        )
        == "agent_metrics_holder"
    )
    assert (
        bcs._non_implementation_reason(
            {
                "title": "Sync bookkeeping",
                "labels": [{"name": "sync-generated"}],
                "user": {"login": "bot"},
            }
        )
        == "sync_bookkeeping"
    )
    assert bcs._issue_labels({"labels": ["Priority:High", {"name": "bug"}]}) == {
        "priority:high",
        "bug",
    }


def test_check_consumer_health_empty_repos_and_issue_systemic_failure() -> None:
    with pytest.raises(SystemExit, match="Registered consumer list is empty"):
        bcs.check_consumer_health([])
    issue_error = subprocess.CalledProcessError(
        1, ["gh", "api"], stderr="API rate limit exceeded for installation"
    )
    with (
        patch(
            "scripts.bootstrap_consumer_settings._priority_label_inventory",
            return_value={
                name: {"color": defn["color"], "description": defn["description"]}
                for name, defn in bcs.PRIORITY_LABELS.items()
            },
        ),
        patch(
            "scripts.bootstrap_consumer_settings._read_paginated_collection",
            side_effect=issue_error,
        ),
    ):
        rows, code = bcs.check_consumer_health(["stranske/One", "stranske/Two"])
    assert code == 2
    assert [row["status"] for row in rows] == ["ERROR", "ERROR"]
    assert "issue read failed" in (rows[0]["error"] or "")


def test_check_consumer_health_all_ok_and_render_details() -> None:
    inventory = {
        name: {"color": definition["color"], "description": definition["description"]}
        for name, definition in bcs.PRIORITY_LABELS.items()
    }
    with (
        patch(
            "scripts.bootstrap_consumer_settings._priority_label_inventory",
            return_value=inventory,
        ),
        patch(
            "scripts.bootstrap_consumer_settings._read_paginated_collection",
            return_value=[],
        ),
    ):
        rows, code = bcs.check_consumer_health(["stranske/Ok"])
    assert code == 0 and rows[0]["status"] == "OK"
    rendered = bcs._render_health_row(
        {
            **rows[0],
            "excluded": {"pull_request": 2},
            "error": "partial failure",
            "status": "ERROR",
        }
    )
    assert "excluded=pull_request:2" in rendered
    assert "error=partial failure" in rendered


def test_main_health_check_rejects_repo_and_missing_manifest(tmp_path: Path) -> None:
    with (
        patch("sys.argv", ["bcs", "--health-check", "--repo", "x/y"]),
        pytest.raises(SystemExit, match="do not pass --repo"),
    ):
        bcs.main()
    missing = tmp_path / "missing-manifest.yml"
    with (
        patch("sys.argv", ["bcs", "--health-check", "--manifest", str(missing)]),
        pytest.raises(SystemExit, match="Manifest not found"),
    ):
        bcs.main()
