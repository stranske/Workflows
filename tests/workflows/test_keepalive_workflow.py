import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "keepalive"
HARNESS = FIXTURES_DIR / "harness.js"


def _require_node() -> None:
    if shutil.which("node") is None:
        pytest.skip("Node.js is required for keepalive harness tests")


def _run_scenario(name: str) -> dict:
    _require_node()
    scenario_path = FIXTURES_DIR / f"{name}.json"
    assert scenario_path.exists(), f"Scenario fixture missing: {scenario_path}"
    command = ["node", str(HARNESS), str(scenario_path)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        pytest.fail(
            "Harness failed with code %s:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (result.returncode, result.stdout, result.stderr)
        )
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        pytest.fail(f"Invalid harness output: {exc}: {result.stdout}")


def _raw_entries(summary: dict) -> list[str]:
    return [entry["text"] for entry in summary["entries"] if entry.get("type") == "raw"]


def _details(summary: dict, title_prefix: str) -> dict | None:
    for entry in summary["entries"]:
        if entry.get("type") == "details" and entry.get("title", "").startswith(title_prefix):
            return entry
    return None


def _assignee_entries(summary: dict) -> list[str]:
    details = _details(summary, "Assignee enforcement")
    if not details:
        return []
    items = details.get("items", [])
    if not isinstance(items, list):
        return []
    return [str(item) for item in items]


def _extract_marked_values(line: str) -> list[str]:
    return re.findall(r"\*\*([^*]+)\*\*", line)


def _dispatch_events(data: dict) -> list[dict]:
    return list(data.get("dispatch_events") or [])


def _dispatch_lines(summary: dict) -> list[str]:
    return [line for line in _raw_entries(summary) if line.startswith("DISPATCH: ")]


def _assert_no_dispatch(data: dict) -> None:
    assert _dispatch_events(data) == []


# First line of the keepalive instruction from .github/templates/keepalive-instruction.md
# The full instruction is multi-line; tests check that the instruction starts correctly.
DEFAULT_COMMAND_PREFIX = (
    "@codex Your objective is to satisfy the **Acceptance Criteria** by completing each "
    "**Task** within the defined **Scope**."
)


def _assert_scope_block(body: str) -> None:
    assert "#### Scope" in body
    assert (
        "For every keepalive round, create a new instruction comment (do not edit any prior bot comment)."
        in body
    )
    assert "Always include hidden markers at the top of the comment body:" in body
    assert any(
        heading in body for heading in ("#### Tasks", "#### Task List")
    ), "Missing Tasks heading"
    assert "- [ ] Generate a unique KEEPALIVE_TRACE" in body
    assert (
        "- [ ] Use peter-evans/create-issue-comment@v3 (or Octokit issues.createComment) to create a new comment with body:"
        in body
    )
    assert "- [ ] Write Round = N and TRACE = … into the step summary for correlation." in body
    assert "#### Acceptance Criteria" in body
    assert (
        "- [ ] Each keepalive cycle adds exactly one new bot comment (no edits) whose body starts with the three hidden markers"
        in body
    )
    assert "- [ ] The posted comment contains the current Scope/Tasks/Acceptance block." in body


def _assert_single_dispatch(data: dict, issue: int, *, round_expected: int | None = None) -> dict:
    dispatches = _dispatch_events(data)
    assert len(dispatches) == 1
    event = dispatches[0]
    assert event["event_type"] == "codex-pr-comment-command"
    payload = event["client_payload"]
    assert payload["issue"] == issue
    assert payload["agent"] == "codex"
    assert payload["base"] == "main"
    assert payload["head"]
    # Check nested meta structure (comment_id, comment_url, round, trace nested under meta)
    meta = payload.get("meta", {})
    assert meta.get("comment_id"), "Dispatch payload meta must include comment_id"
    assert meta.get("comment_url", "").startswith("https://example.test/")
    assert meta.get("trace"), "Dispatch payload meta must include keepalive trace"
    assert isinstance(meta.get("trace"), str)
    assert payload.get("quiet") is True
    assert payload.get("reply") == "none"
    instruction_body = payload.get("instruction_body")
    assert isinstance(instruction_body, str) and instruction_body
    assert "Head SHA" not in instruction_body
    assert "Workflow / Job" not in instruction_body
    if round_expected is not None:
        assert meta.get("round") == round_expected
    else:
        assert isinstance(meta.get("round"), int) and meta.get("round") >= 1
    return payload


def _assert_keepalive_authors(comments: list[dict], expected_login: str = "stranske") -> None:
    for comment in comments:
        assert comment["user"]["login"] == expected_login


def test_keepalive_skip_requested() -> None:
    data = _run_scenario("skip_opt_out")
    summary = data["summary"]
    raw = _raw_entries(summary)
    assert "Skip requested via options_json." in raw
    assert "Skipped 0 paused PRs." in raw
    assert data["created_comments"] == []
    assert data["updated_comments"] == []
    _assert_no_dispatch(data)


def test_keepalive_idle_threshold_logic() -> None:
    data = _run_scenario("idle_threshold")
    summary = data["summary"]
    created = data["created_comments"]
    _assert_keepalive_authors(created)
    assert [item["issue_number"] for item in created] == [101]
    body_lines = created[0]["body"].splitlines()
    assert body_lines[0] == "<!-- keepalive-round: 1 -->"
    assert body_lines[1] == "<!-- keepalive-attempt: 1 -->"
    assert body_lines[2] == "<!-- codex-keepalive-marker -->"
    assert "<!-- keepalive-trace:" in created[0]["body"]
    assert body_lines[4].startswith(DEFAULT_COMMAND_PREFIX)
    _assert_scope_block(created[0]["body"])
    assert "**Keepalive Round" not in created[0]["body"]
    assert "<!-- keepalive-round: 1 -->" in created[0]["body"]
    assert "<!-- keepalive-attempt: 1 -->" in created[0]["body"]
    assert data["updated_comments"] == []
    payload = _assert_single_dispatch(data, 101, round_expected=1)
    assert payload.get("meta", {}).get("comment_id") == created[0]["id"]
    assert payload.get("meta", {}).get("comment_url", "").endswith(f"#comment-{created[0]['id']}")

    reactions = data.get("instruction_reactions", [])
    assert reactions == [{"comment_id": created[0]["id"], "content": "hooray"}]

    details = _details(summary, "Triggered keepalive comments")
    assert details is not None and len(details["items"]) == 1

    raw = _raw_entries(summary)
    assert "Triggered keepalive count: 1" in raw
    assert "Refreshed keepalive count: 0" in raw
    assert "Evaluated pull requests: 3" in raw
    assert "Skipped 0 paused PRs." in raw

    dispatch_lines = _dispatch_lines(summary)
    assert any("reason=ok" in line for line in dispatch_lines)
    assert any("agent=codex" in line for line in dispatch_lines)

    assignee_entries = _assignee_entries(summary)
    assert any(
        entry.startswith("#101 – assignment skipped (no human assignees)")
        for entry in assignee_entries
    )


def test_keepalive_dry_run_records_previews() -> None:
    data = _run_scenario("dry_run")
    summary = data["summary"]
    assert data["created_comments"] == []
    assert data["updated_comments"] == []
    _assert_no_dispatch(data)

    preview = _details(summary, "Previewed keepalive comments")
    assert preview is not None and len(preview["items"]) == 1

    raw = _raw_entries(summary)
    assert "Previewed keepalive count: 1" in raw
    assert "Skipped 0 paused PRs." in raw

    assignee_entries = _assignee_entries(summary)
    assert any(
        entry.startswith("#404 – assignment skipped (no human assignees)")
        for entry in assignee_entries
    )


def test_keepalive_dedupes_configuration() -> None:
    data = _run_scenario("dedupe")
    summary = data["summary"]

    raw = _raw_entries(summary)
    labels_line = next(line for line in raw if line.startswith("Target labels:"))
    logins_line = next(line for line in raw if line.startswith("Agent logins:"))
    assert _extract_marked_values(labels_line) == ["agent:codex", "agent:triage"]
    assert _extract_marked_values(logins_line) == [
        "chatgpt-codex-connector",
        "helper-bot",
    ]

    created = data["created_comments"]
    _assert_keepalive_authors(created)
    assert [item["issue_number"] for item in created] == [505]
    assert "<!-- codex-keepalive-marker -->" in created[0]["body"]
    assert "<!-- keepalive-round: 1 -->" in created[0]["body"]
    assert "<!-- keepalive-attempt: 1 -->" in created[0]["body"]
    assert "<!-- keepalive-trace:" in created[0]["body"]
    assert DEFAULT_COMMAND_PREFIX in created[0]["body"]
    _assert_scope_block(created[0]["body"])
    assert "Codex, 1/1 checklist item" not in created[0]["body"]
    assert data["updated_comments"] == []
    payload = _assert_single_dispatch(data, 505, round_expected=1)
    assert payload.get("meta", {}).get("comment_id") == created[0]["id"]

    details = _details(summary, "Triggered keepalive comments")
    assert details is not None and any("#505" in entry for entry in details["items"])

    assignee_entries = _assignee_entries(summary)
    assert any(
        "#505 – ensured assignees:" in entry and "Helper-Bot" in entry for entry in assignee_entries
    )


def test_keepalive_waits_for_recent_command() -> None:
    data = _run_scenario("command_pending")
    summary = data["summary"]

    created = data["created_comments"]
    _assert_keepalive_authors(created)
    assert [item["issue_number"] for item in created] == [707]
    assert DEFAULT_COMMAND_PREFIX in created[0]["body"]
    _assert_scope_block(created[0]["body"])
    assert "Codex, 1/2 checklist item" not in created[0]["body"]
    assert "<!-- keepalive-trace:" in created[0]["body"]
    assert data["updated_comments"] == []
    payload = _assert_single_dispatch(data, 707, round_expected=1)
    assert payload.get("meta", {}).get("comment_id") == created[0]["id"]

    raw = _raw_entries(summary)
    assert "Triggered keepalive count: 1" in raw
    assert "Refreshed keepalive count: 0" in raw
    assert "Evaluated pull requests: 2" in raw
    assert "Skipped 0 paused PRs." in raw

    assignee_entries = _assignee_entries(summary)
    assert any(
        entry.startswith("#707 – assignment skipped (no human assignees)")
        for entry in assignee_entries
    )


def test_keepalive_respects_paused_label() -> None:
    data = _run_scenario("paused")
    summary = data["summary"]
    raw = _raw_entries(summary)
    assert "Skipped 1 paused PR." in raw
    details = _details(summary, "Paused pull requests")
    assert details is not None and any("#404" in item for item in details["items"])
    created = data["created_comments"]
    _assert_keepalive_authors(created)
    assert [item["issue_number"] for item in created] == [505]
    assert "<!-- codex-keepalive-marker -->" in created[0]["body"]
    assert "<!-- keepalive-round: 1 -->" in created[0]["body"]
    assert "<!-- keepalive-attempt: 1 -->" in created[0]["body"]
    assert "<!-- keepalive-trace:" in created[0]["body"]
    assert "Codex, 1/1 checklist item" not in created[0]["body"]
    assert data["updated_comments"] == []
    payload = _assert_single_dispatch(data, 505, round_expected=1)
    assert payload.get("meta", {}).get("comment_id") == created[0]["id"]


def test_keepalive_skips_unapproved_comment_author() -> None:
    data = _run_scenario("unauthorised_author")

    created = data["created_comments"]
    _assert_keepalive_authors(created, "helper-bot")
    assert len(created) == 1
    assert created[0]["issue_number"] == 313
    assert DEFAULT_COMMAND_PREFIX in created[0]["body"]
    _assert_scope_block(created[0]["body"])
    assert "<!-- keepalive-trace:" in created[0]["body"]

    _assert_no_dispatch(data)

    warnings = data["logs"]["warnings"]
    assert any("not in dispatch allow list" in warning for warning in warnings)

    summary = data["summary"]
    assignee_entries = _assignee_entries(summary)
    assert any(
        entry.startswith("#313 – assignment skipped (no human assignees)")
        for entry in assignee_entries
    )


def test_keepalive_handles_paged_comments() -> None:
    data = _run_scenario("paged_comments")
    created = data["created_comments"]
    _assert_keepalive_authors(created)
    assert [item["issue_number"] for item in created] == [808]
    body_lines = created[0]["body"].splitlines()
    assert body_lines[0] == "<!-- keepalive-round: 1 -->"
    assert body_lines[1] == "<!-- keepalive-attempt: 1 -->"
    assert body_lines[2] == "<!-- codex-keepalive-marker -->"
    assert "<!-- keepalive-trace:" in created[0]["body"]
    assert body_lines[4].startswith(DEFAULT_COMMAND_PREFIX)
    _assert_scope_block(created[0]["body"])
    assert "<!-- keepalive-round: 1 -->" in created[0]["body"]
    assert "<!-- keepalive-attempt: 1 -->" in created[0]["body"]
    assert data["updated_comments"] == []
    payload = _assert_single_dispatch(data, 808, round_expected=1)
    assert payload.get("meta", {}).get("comment_id") == created[0]["id"]
    summary = data["summary"]
    raw = _raw_entries(summary)
    assert "Triggered keepalive count: 1" in raw
    assert "Refreshed keepalive count: 0" in raw

    assignee_entries = _assignee_entries(summary)
    assert any(
        entry.startswith("#808 – assignment skipped (no human assignees)")
        for entry in assignee_entries
    )


def test_keepalive_posts_new_comment_for_next_round() -> None:
    data = _run_scenario("refresh")
    created = data["created_comments"]
    _assert_keepalive_authors(created)
    assert len(created) == 1
    body = created[0]["body"]
    assert "<!-- keepalive-round: 2 -->" in body
    assert "<!-- keepalive-attempt: 2 -->" in body
    assert "<!-- codex-keepalive-marker -->" in body
    assert "<!-- keepalive-trace:" in body
    assert DEFAULT_COMMAND_PREFIX in body
    _assert_scope_block(body)
    assert created[0]["issue_number"] == 909
    assert data["updated_comments"] == []
    payload = _assert_single_dispatch(data, 909, round_expected=2)
    assert payload.get("meta", {}).get("comment_id") == created[0]["id"]

    summary = data["summary"]
    raw = _raw_entries(summary)
    assert "Triggered keepalive count: 1" in raw
    assert "Refreshed keepalive count: 0" in raw

    assignee_entries = _assignee_entries(summary)
    assert any(
        entry.startswith("#909 – assignment skipped (no human assignees)")
        for entry in assignee_entries
    )


def test_keepalive_upgrades_legacy_comment() -> None:
    data = _run_scenario("legacy_keepalive")
    created = data["created_comments"]
    _assert_keepalive_authors(created)
    assert len(created) == 1
    body = created[0]["body"]
    assert "<!-- keepalive-round: 2 -->" in body
    assert "<!-- keepalive-attempt: 2 -->" in body
    assert "<!-- codex-keepalive-marker -->" in body
    assert "<!-- keepalive-trace:" in body
    assert DEFAULT_COMMAND_PREFIX in body
    _assert_scope_block(body)
    assert created[0]["issue_number"] == 909
    assert data["updated_comments"] == []
    payload = _assert_single_dispatch(data, 909, round_expected=2)
    assert payload.get("meta", {}).get("comment_id") == created[0]["id"]

    summary = data["summary"]
    raw = _raw_entries(summary)
    assert "Triggered keepalive count: 1" in raw
    assert "Refreshed keepalive count: 0" in raw


def test_keepalive_skips_non_codex_branches() -> None:
    """Keepalive now works on any branch with the agent:codex label.

    This test previously expected keepalive to skip non-codex/issue-* branches,
    but that restriction was removed to make keepalive more flexible.
    Now keepalive triggers based on labels and checklist presence, not branch names.
    """
    data = _run_scenario("non_codex_branch")
    created = data["created_comments"]
    # Keepalive should now trigger because:
    # - PR has agent:codex label
    # - Has @codex command
    # - Has Codex comment with unchecked checklist item
    # - Enough idle time has passed
    assert len(created) == 1
    _assert_keepalive_authors(created)
    assert DEFAULT_COMMAND_PREFIX in created[0]["body"]
    _assert_scope_block(created[0]["body"])
    assert "<!-- keepalive-trace:" in created[0]["body"]

    summary = data["summary"]
    raw = _raw_entries(summary)
    assert "Triggered keepalive count: 1" in raw
    payload = _assert_single_dispatch(data, 111, round_expected=1)
    assert payload.get("meta", {}).get("comment_id") == created[0]["id"]
    assert payload["head"] == "feature/non-codex-update"


def test_keepalive_gate_trigger_bypasses_idle_check() -> None:
    """When triggered by Gate completion, keepalive should bypass idle check.

    This tests that triggered_by_gate option sets effectiveIdleMinutes to 0,
    allowing immediate keepalive even if last Codex activity was < idle_minutes ago.
    """
    data = _run_scenario("gate_trigger")

    # The PR has a Codex comment from 2 minutes ago (11:58 AM, now is 12:00 PM)
    # Normal idle threshold is 10 minutes, so this would usually be skipped
    # But triggered_by_gate=true should bypass the idle check
    created = data["created_comments"]
    _assert_keepalive_authors(created)
    assert len(created) == 1
    assert created[0]["issue_number"] == 101
    assert DEFAULT_COMMAND_PREFIX in created[0]["body"]
    _assert_scope_block(created[0]["body"])
    assert "<!-- keepalive-trace:" in created[0]["body"]

    summary = data["summary"]
    raw = _raw_entries(summary)
    assert "Triggered keepalive count: 1" in raw
    payload = _assert_single_dispatch(data, 101, round_expected=1)
    assert payload.get("meta", {}).get("comment_id") == created[0]["id"]


def test_keepalive_fails_when_required_labels_missing() -> None:
    data = _run_scenario("missing_label")

    assert data["created_comments"] == []
    assert data["dispatch_events"] == []

    failed = data["logs"].get("failedMessage")
    assert failed == (
        "Keepalive guardrail violated: required labels missing on opted-in pull request(s)."
    )

    summary = data["summary"]
    guardrail_details = _details(summary, "Guardrail violations")
    assert guardrail_details is not None
    items = guardrail_details.get("items", [])
    assert any("#612" in item and "agents:keepalive" in item for item in items)


def test_keepalive_requires_dispatch_token() -> None:
    _require_node()
    scenario_path = FIXTURES_DIR / "missing_dispatch_token.json"
    assert scenario_path.exists(), "Scenario fixture missing"
    command = ["node", str(HARNESS), str(scenario_path)]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode != 0, "Expected harness to fail without dispatch token"
    combined_output = (result.stderr or "") + (result.stdout or "")
    assert "ACTIONS_BOT_PAT is required" in combined_output
