from __future__ import annotations

import io
import json
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "agents_pr_meta"
HARNESS = FIXTURES_DIR / "harness.js"


def _require_node() -> None:
    if shutil.which("node") is None:
        pytest.skip("Node.js is required for agents-pr-meta keepalive tests")


def _run_scenario(name: str) -> dict:
    _require_node()
    command = ["node", str(HARNESS), str(FIXTURES_DIR / "scenarios.json"), name]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        pytest.fail(
            f"Harness failed with code {result.returncode}:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    try:
        return json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:  # pragma: no cover - harness should return valid JSON
        pytest.fail(f"Invalid harness output: {exc}: {result.stdout}")


@pytest.mark.parametrize(
    ("event", "branch", "head_matches", "same_repo", "associated_pr", "expected_skip"),
    [
        ("pull_request", "release-please--branches--main", True, True, None, True),
        ("workflow_run", "release-please--branches--main", True, True, 23, True),
        ("workflow_run", "release-please--branches--main", True, True, 24, False),
        ("workflow_run", "release-please--branches--main", True, True, None, False),
        ("pull_request", "release-please--branches--main", False, True, None, False),
        ("pull_request", "release-please--branches--main", True, False, None, False),
        ("pull_request", "codex/issue-21", True, True, None, False),
    ],
)
def test_hosted_body_fingerprint_skips_only_verified_release_prs(
    event, branch, head_matches, same_repo, associated_pr, expected_skip, monkeypatch, capsys
):
    _require_node()
    repo = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(repo)
    workflow = yaml.safe_load((repo / ".github/workflows/agents-pr-meta-v4.yml").read_text())
    steps = workflow["jobs"]["update_body"]["steps"]
    step = next(step for step in steps if step.get("id") == "fingerprint")
    prepare = (
        step["run"]
        .split("<<'PY' > /tmp/state-fingerprint-inputs.json\n", 1)[1]
        .split("\nPY\n", 1)[0]
    )
    head = "a" * 40
    monkeypatch.setenv("EXPECTED_PR_HEAD", head if head_matches else "b" * 40)
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/repo")
    monkeypatch.setenv("PR_NUMBER", "23")
    monkeypatch.delenv("WORKFLOW_RUN_PR_HEAD", raising=False)
    pr = {
        "number": 23,
        "state": "open",
        "body": "Work on release-please automation.",
        "head": {
            "ref": branch,
            "sha": head,
            "repo": {"full_name": "example/repo" if same_repo else "fork/repo"},
        },
    }
    denied_response = io.BytesIO()

    def api(request, *, timeout):
        assert request.get_method() == "GET"
        if request.selector.endswith("/pulls/23"):
            payload = pr
        elif request.selector.endswith("/labels"):
            payload = []
        else:
            assert request.selector.endswith(f"/commits/{head}/pulls")
            if associated_pr is None:
                raise urllib.error.HTTPError(
                    request.full_url, 403, "Forbidden", {}, denied_response
                )
            payload = [{"number": associated_pr}]
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(urllib.request, "urlopen", api)
    try:
        exec(compile(prepare, "<hosted fingerprint step>", "exec"), {})  # noqa: S102
    except SystemExit as ended:
        assert expected_skip and ended.code == 0
    output = capsys.readouterr().out.strip()
    if expected_skip:
        assert output == "skip-release-pr"
        assert "reason=release-please-pr" in step["run"]
    else:
        assert json.loads(output)["head_sha"] == head
    if event == "workflow_run" and associated_pr is None:
        assert denied_response.closed


def test_keepalive_detection_dispatches_orchestrator() -> None:
    data = _run_scenario("dispatch")
    outputs = data["outputs"]
    assert outputs["dispatch"] == "true"
    assert outputs["reason"] == "keepalive-detected"
    assert outputs["issue"] == "3227"
    assert outputs["round"] == "3"
    assert outputs["branch"] == "codex/issue-3227-keepalive"
    assert outputs["base"] == "phase-2-dev"
    assert outputs["trace"] == "manual-resend"
    assert outputs["pr"] == "3230"
    assert outputs["comment_id"] == "987654321"
    assert (
        outputs["comment_url"]
        == "https://github.com/stranske/Workflows/pull/3230#issuecomment-987654321"
    )

    calls = data.get("calls", {})
    created = calls.get("reactionsCreated", [])
    assert created == [
        {"comment_id": 987654321, "content": "hooray"},
        {"comment_id": 987654321, "content": "rocket"},
    ]


def test_keepalive_detection_ignores_sanitised_after_markers() -> None:
    data = _run_scenario("after_markers")
    outputs = data["outputs"]
    assert outputs["dispatch"] == "false"
    assert outputs["reason"] == "missing-round"


def test_keepalive_detection_ignores_html_entities() -> None:
    data = _run_scenario("html_entities")
    outputs = data["outputs"]
    assert outputs["dispatch"] == "false"
    assert outputs["reason"] == "missing-round"


def test_keepalive_detection_requires_marker() -> None:
    data = _run_scenario("missing_marker")
    outputs = data["outputs"]
    assert outputs["dispatch"] == "false"
    assert outputs["reason"] == "missing-sentinel"
    assert outputs["comment_id"] == "4001001"


def test_keepalive_detection_requires_round_marker() -> None:
    data = _run_scenario("missing_round")
    outputs = data["outputs"]
    assert outputs["dispatch"] == "false"
    assert outputs["reason"] == "missing-round"
    assert outputs["comment_id"] == "1122334455"


def test_keepalive_detection_validates_author() -> None:
    data = _run_scenario("unauthorised")
    outputs = data["outputs"]
    assert outputs["dispatch"] == "false"
    assert outputs["reason"] == "unauthorised-author"


def test_keepalive_detection_requires_all_markers_on_instruction() -> None:
    data = _run_scenario("autofix_instruction")
    outputs = data["outputs"]
    assert outputs["dispatch"] == "false"
    assert outputs["reason"] == "missing-round"

    calls = data.get("calls", {})
    updates = calls.get("commentsUpdated", [])
    assert updates == []


def test_keepalive_detection_ignores_autofix_status_comment() -> None:
    data = _run_scenario("automation_autofix")
    outputs = data["outputs"]
    assert outputs["dispatch"] == "false"
    assert outputs["reason"] == "automation-comment"
    assert outputs["comment_id"] == "3492705833"


def test_keepalive_detection_rejects_manual_round_without_markers() -> None:
    data = _run_scenario("manual_round")
    outputs = data["outputs"]
    assert outputs["dispatch"] == "false"
    assert outputs["reason"] == "missing-round"
    calls = data.get("calls", {})
    updates = calls.get("commentsUpdated", [])
    assert updates == []


def test_keepalive_detection_rejects_manual_repeat_without_markers() -> None:
    data = _run_scenario("manual_repeat")
    outputs = data["outputs"]
    assert outputs["dispatch"] == "false"
    assert outputs["reason"] == "missing-round"

    calls = data.get("calls", {})
    updates = calls.get("commentsUpdated", [])
    assert updates == []
