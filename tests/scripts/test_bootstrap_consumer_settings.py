from __future__ import annotations

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
