import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "keepalive_post_work"
HARNESS = FIXTURES_DIR / "harness.js"
STATE_COMMENT_PREFIX = "<!-- keepalive-state:v1"


def _require_node() -> None:
    if shutil.which("node") is None:
        pytest.skip("Node.js is required for keepalive post-work tests")


def _run_scenario(name: str) -> Dict[str, Any]:
    _require_node()
    scenario_path = FIXTURES_DIR / f"{name}.json"
    assert scenario_path.exists(), f"Missing scenario fixture: {scenario_path}"
    result = subprocess.run(
        ["node", str(HARNESS), str(scenario_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            "Harness failed with code %s:\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (result.returncode, result.stdout, result.stderr)
        )
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:  # pragma: no cover - harness should emit JSON
        raise AssertionError(f"Invalid harness output: {exc}: {result.stdout}") from exc


def _summary_table(data: dict) -> list[list[str]]:
    for entry in data.get("summary", []):
        if entry.get("type") == "table":
            return entry.get("rows", [])
    return []


def _partition_comments(
    events: Dict[str, List[Dict[str, str]]],
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    comments: List[Dict[str, str]] = events.get("comments", [])  # type: ignore[assignment]
    state_comments = [
        entry for entry in comments if entry.get("body", "").startswith(STATE_COMMENT_PREFIX)
    ]
    other_comments = [entry for entry in comments if entry not in state_comments]
    return state_comments, other_comments


def test_keepalive_sync_detects_head_change_without_actions() -> None:
    data = _run_scenario("head_change")
    events = data["events"]
    outputs = data["outputs"]
    assert events["dispatches"] == []
    state_comments, other_comments = _partition_comments(events)
    assert len(state_comments) == 1
    assert other_comments == []
    table = _summary_table(data)
    assert any(row[0] == "Initial poll" and "Branch advanced" in row[1] for row in table)
    assert any(row[0] == "Result" and "mode=already-synced" in row[1] for row in table)
    assert outputs["action"] == "skip"
    assert outputs["changed"] == "true"
    assert outputs["mode"] == "already-synced"
    assert outputs["success"] == "true"
    assert outputs["status"] == "in_sync"
    assert outputs["link"] == "https://example.test/comment"
    raw_entries = [
        entry.get("text", "") for entry in data.get("summary", []) if entry.get("type") == "raw"
    ]
    assert any(text.startswith("SYNC: status=in_sync") for text in raw_entries)
    assert any(text.startswith("SYNC: action=skip") and "link=" in text for text in raw_entries)


def test_keepalive_sync_update_branch_success() -> None:
    data = _run_scenario("update_branch")
    events = data["events"]
    outputs = data["outputs"]
    assert events["dispatches"] == []
    assert events["updateBranch"] == [{"pull_number": 402, "expected_head_sha": "sha0"}]
    assert events["labelsRemoved"] == ["agents:sync-required"]
    state_comments, other_comments = _partition_comments(events)
    assert len(state_comments) == 1
    assert other_comments == []
    table = _summary_table(data)
    assert any(row[0] == "Update-branch API" and "advanced to" in row[1] for row in table)
    assert any(row[0] == "Result" and "mode=update-branch-api" in row[1] for row in table)
    assert outputs["action"] == "update-branch"
    assert outputs["changed"] == "true"
    assert outputs["mode"] == "update-branch-api"
    assert outputs["success"] == "true"
    assert outputs["status"] == "in_sync"
    assert outputs["link"] == "https://example.test/comment"
    raw_entries = [
        entry.get("text", "") for entry in data.get("summary", []) if entry.get("type") == "raw"
    ]
    assert any(
        text.startswith("Remediation:") and "update-branch:advanced" in text for text in raw_entries
    )
    assert any(text.startswith("SYNC: status=in_sync") for text in raw_entries)
    assert any(
        text.startswith("SYNC: action=update-branch") and "link=" in text for text in raw_entries
    )


def test_keepalive_sync_create_pr_flow() -> None:
    data = _run_scenario("create_pr")
    events = data["events"]
    outputs = data["outputs"]
    assert len(events["updateBranch"]) == 1
    assert events["updateBranch"][0]["expected_head_sha"] == "sha0"
    assert len(events["workflowDispatches"]) == 1
    dispatch = events["workflowDispatches"][0]
    assert dispatch["workflow_id"] == "agents-keepalive-branch-sync.yml"
    state_comments, other_comments = _partition_comments(events)
    assert len(state_comments) == 1
    assert other_comments == []
    table = _summary_table(data)
    assert any(row[0] == "Helper sync result" and "Branch advanced" in row[1] for row in table)
    assert any(row[0] == "Result" and "mode=helper-sync" in row[1] for row in table)
    assert outputs["action"] == "create-pr"
    assert outputs["changed"] == "true"
    assert outputs["mode"] == "helper-sync"
    assert outputs["success"] == "true"
    assert outputs["status"] == "in_sync"
    assert outputs["link"] == "https://example.test/comment"
    raw_entries = [
        entry.get("text", "") for entry in data.get("summary", []) if entry.get("type") == "raw"
    ]
    assert any(
        text.startswith("Remediation:")
        and "update-branch:failed:Update branch blocked" in text
        and "branch-sync:run=https://example.test/run/987654" in text
        for text in raw_entries
    )
    assert any(text.startswith("SYNC: status=in_sync") for text in raw_entries)
    assert any(
        text.startswith("SYNC: action=create-pr") and "link=" in text for text in raw_entries
    )


def test_keepalive_sync_escalation_adds_label_and_comment() -> None:
    data = _run_scenario("escalation")
    events = data["events"]
    outputs = data["outputs"]
    assert len(events["updateBranch"]) == 1
    assert len(events["workflowDispatches"]) == 1
    assert events["labelsAdded"] == [["agents:sync-required"]]
    state_comments, other_comments = _partition_comments(events)
    assert len(state_comments) == 1
    assert len(other_comments) == 1
    assert other_comments[0]["body"].startswith(
        "Keepalive: manual action needed — use update-branch/create-pr controls"
    )
    table = _summary_table(data)
    assert any(row[0] == "Result" and "mode=sync-timeout" in row[1] for row in table)
    assert outputs["action"] == "escalate"
    assert outputs["changed"] == "false"
    assert outputs["mode"] == "sync-timeout"
    assert outputs["success"] == "false"
    assert outputs["status"] == "needs_update"
    assert outputs["link"] == "https://example.test/comment"
    raw_entries = [
        entry.get("text", "") for entry in data.get("summary", []) if entry.get("type") == "raw"
    ]
    assert any(text.startswith("SYNC: status=needs_update") for text in raw_entries)
    assert any(text.startswith("SYNC: action=escalate") and "link=" in text for text in raw_entries)


def test_keepalive_sync_dispatches_head_repo_for_fork() -> None:
    data = _run_scenario("fork_sync")
    dispatches = data["events"]["workflowDispatches"]
    outputs = data["outputs"]

    assert len(dispatches) == 1
    inputs = dispatches[0]["inputs"]
    assert inputs["head_repository"] == "fork-owner/Trend_Model_Project"
    assert inputs["head_is_fork"] == "true"

    assert outputs["action"] == "create-pr"
    assert outputs["mode"] == "helper-sync"
    assert outputs["success"] == "true"
    assert outputs["status"] == "in_sync"

    table = _summary_table(data)
    assert any(row[0] == "Helper sync result" and "Branch advanced" in row[1] for row in table)


def test_keepalive_sync_skips_fork_without_head_repo() -> None:
    data = _run_scenario("fork_missing_head_repo")
    outputs = data["outputs"]

    assert data["events"]["workflowDispatches"] == []
    assert outputs["action"] == "skip"
    assert outputs["mode"] == "fork-head-repo-missing"
    assert outputs["success"] == "false"
    assert outputs["status"] == "conflict"

    table = _summary_table(data)
    assert any(
        row[0] == "Initialisation" and "Forked PR missing head repository" in row[1]
        for row in table
    )
