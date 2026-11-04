"""The format guard must not process closed issues.

These tests execute the guard's real "Resolve issue" step, lifted straight out of
the workflow YAML, against a fixture issue payload. A closed issue routed to the
optimizer produces a body edit, that edit re-fires the guard, and the pair loops
against already-delivered work: Fine-Art-Archive#464 kept formatting for 17.5
hours after it was closed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_PATH = REPO_ROOT / ".github/workflows/agents-issue-format-guard.yml"
CONSUMER_GUARD_PATH = (
    REPO_ROOT / "templates/consumer-repo/.github/workflows/agents-issue-format-guard.yml"
)
GUARD_PATHS = (GUARD_PATH, CONSUMER_GUARD_PATH)

JQ_AVAILABLE = shutil.which("jq") is not None
skip_if_no_jq = pytest.mark.skipif(not JQ_AVAILABLE, reason="jq required by the guard step")


def _resolve_step_script(path: Path) -> str:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    for step in workflow["jobs"]["check"]["steps"]:
        if step.get("name") == "Resolve issue":
            return step["run"]
    raise AssertionError(f"'Resolve issue' step not found in {path}")


def _cleanup_step_script(path: Path) -> str:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    for step in workflow["jobs"]["check"]["steps"]:
        if step.get("name") == "Clear stale format lease from exempt issues":
            return step["run"]
    raise AssertionError(f"'Clear stale format lease from exempt issues' step not found in {path}")


def _run_resolve_step(tmp_path: Path, script: str, issue_json: str) -> dict[str, str]:
    """Run the real step with `gh` stubbed to return the fixture payload."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fixture = tmp_path / "fixture.json"
    fixture.write_text(issue_json, encoding="utf-8")

    # The step's only external call is `gh issue view … > issue.json`.
    gh_stub = bin_dir / "gh"
    gh_stub.write_text(f'#!/usr/bin/env bash\ncat "{fixture}"\n', encoding="utf-8")
    gh_stub.chmod(0o755)

    github_output = tmp_path / "github_output"
    github_output.touch()

    completed = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        env={
            "PATH": f"{bin_dir}:{shutil.os.environ['PATH']}",
            "GITHUB_OUTPUT": str(github_output),
            "GITHUB_REPOSITORY": "stranske/Fine-Art-Archive",
            "NUMBER": "464",
            "GH_TOKEN": "stub",
        },
    )
    assert completed.returncode == 0, f"step failed: {completed.stderr}"

    outputs: dict[str, str] = {}
    for line in github_output.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            outputs[key] = value
    return outputs


def _run_cleanup_step(tmp_path: Path, script: str, initial_issue: str, current_issue: str) -> str:
    """Run cleanup with a fresh issue read that may differ from event-time state."""
    bin_dir = tmp_path / "cleanup-bin"
    bin_dir.mkdir(exist_ok=True)
    (tmp_path / "issue.json").write_text(initial_issue, encoding="utf-8")
    current = tmp_path / "current.json"
    current.write_text(current_issue, encoding="utf-8")
    calls = tmp_path / "gh-calls.txt"
    gh_stub = bin_dir / "gh"
    gh_stub.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [[ "$1 $2" == "issue view" ]]; then\n'
        f"  cat '{current}'\n"
        "else\n"
        f"  printf '%s\\n' \"$*\" >> '{calls}'\n"
        "fi\n",
        encoding="utf-8",
    )
    gh_stub.chmod(0o755)
    completed = subprocess.run(
        ["bash", "-c", script],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        env={
            "PATH": f"{bin_dir}:{shutil.os.environ['PATH']}",
            "GITHUB_REPOSITORY": "stranske/Fine-Art-Archive",
            "NUMBER": "464",
            "GH_TOKEN": "stub",
        },
    )
    assert completed.returncode == 0, f"cleanup failed: {completed.stderr}"
    return calls.read_text(encoding="utf-8") if calls.exists() else ""


# The #464 shape: closed, and carrying none of the pre-existing exemption signals.
CLOSED_ISSUE = """
{
  "number": 464,
  "state": "CLOSED",
  "body": "## Tasks\\n- [ ] do a thing\\n\\n## Acceptance Criteria\\n- [ ] it is done\\n",
  "labels": [{"name": "agents:format"}, {"name": "agents:formatted"}],
  "author": {"login": "stranske"}
}
"""

OPEN_ISSUE = CLOSED_ISSUE.replace('"state": "CLOSED"', '"state": "OPEN"')


@skip_if_no_jq
@pytest.mark.parametrize("guard_path", GUARD_PATHS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_closed_issue_is_exempt(tmp_path: Path, guard_path: Path) -> None:
    outputs = _run_resolve_step(tmp_path, _resolve_step_script(guard_path), CLOSED_ISSUE)
    assert outputs["exempt"] == "true", (
        "a closed issue must be exempt; otherwise the guard keeps routing it to the "
        "optimizer and the pair loops against delivered work"
    )


@skip_if_no_jq
@pytest.mark.parametrize("guard_path", GUARD_PATHS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_open_issue_is_still_processed(tmp_path: Path, guard_path: Path) -> None:
    """The exemption must be narrow: an equivalent open issue still gets validated."""
    outputs = _run_resolve_step(tmp_path, _resolve_step_script(guard_path), OPEN_ISSUE)
    assert outputs["exempt"] == "false"
    assert outputs["held"] == "false"


@skip_if_no_jq
@pytest.mark.parametrize("guard_path", GUARD_PATHS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_closed_state_is_matched_case_insensitively(tmp_path: Path, guard_path: Path) -> None:
    """`gh` returns CLOSED; the REST API returns closed. Both must exempt."""
    lowercase = CLOSED_ISSUE.replace('"state": "CLOSED"', '"state": "closed"')
    outputs = _run_resolve_step(tmp_path, _resolve_step_script(guard_path), lowercase)
    assert outputs["exempt"] == "true"


def test_both_guard_copies_carry_the_closed_check() -> None:
    """Root and consumer template must not drift on this check."""
    for path in GUARD_PATHS:
        assert "ascii_downcase" in _resolve_step_script(
            path
        ), f"{path} lacks the closed-state check"


def test_closed_issue_cleanup_removes_format_and_pause_labels() -> None:
    """Closed cleanup may release a stale pause; open held issues remain untouched."""
    for path in GUARD_PATHS:
        cleanup = _cleanup_step_script(path)
        assert '--remove-label "agents:format"' in cleanup
        assert '--remove-label "agents:auto-pilot-pause"' in cleanup
        assert "ascii_downcase" in cleanup
        assert '== "closed"' in cleanup


@skip_if_no_jq
@pytest.mark.parametrize("guard_path", GUARD_PATHS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_closed_cleanup_rechecks_state_before_removing_pause_label(
    tmp_path: Path, guard_path: Path
) -> None:
    initial = CLOSED_ISSUE.replace(
        '{"name": "agents:format"}, {"name": "agents:formatted"}',
        '{"name": "agents:format"}, {"name": "agents:auto-pilot-pause"}',
    )
    reopened = initial.replace('"state": "CLOSED"', '"state": "OPEN"')
    calls = _run_cleanup_step(tmp_path, _cleanup_step_script(guard_path), initial, reopened)
    assert "--remove-label agents:format" in calls
    assert "--remove-label agents:auto-pilot-pause" not in calls

    calls = _run_cleanup_step(tmp_path, _cleanup_step_script(guard_path), initial, initial)
    assert "--remove-label agents:auto-pilot-pause" in calls


# --- Budget accounting: real rewrite attempts vs optimizer crashes ------------
#
# These run the guard's real "Route non-conforming issue to the optimizer" step
# (bash + the embedded node counter) with `gh` stubbed and the two node modules
# the counter requires replaced by fakes that serve a fixture comment list.

NODE_AVAILABLE = shutil.which("node") is not None
SHA_AVAILABLE = shutil.which("sha256sum") is not None
skip_if_no_route_tools = pytest.mark.skipif(
    not (JQ_AVAILABLE and NODE_AVAILABLE and SHA_AVAILABLE),
    reason="jq, node and sha256sum required by the guard's routing step",
)

INVALID_BODY = "Fix the crash in scripts/langchain/issue_formatter.py."
BOT = {"login": "github-actions[bot]", "id": 41898282}
APP_BOT = {"login": "stranske-workflows[bot]", "id": 1}
HUMAN = {"login": "stranske", "id": 2}
REWRITE_FAILED = "<!-- issue-optimizer:rewrite-failed -->\nreport"
CRASH = "⚠️ **Workflow failed**\n\n" "The agents-issue-optimizer workflow encountered an error.\n"
CAP = "<!-- format-guard:attempt-cap -->\npaused"

_NODE_FAKES = """
const Module = require('module');
const fs = require('fs');
const original = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === '@octokit/rest') {
    return { Octokit: class { constructor() { this.rest = { issues: {} }; } } };
  }
  if (request.endsWith('github-api-with-retry.js')) {
    return {
      createTokenAwareRetry: async () => ({
        paginateWithRetry: async () =>
          JSON.parse(fs.readFileSync(process.env.FIXTURE_COMMENTS, 'utf8')),
      }),
    };
  }
  return original.apply(this, arguments);
};
"""


def _route_step_script(path: Path) -> str:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    for step in workflow["jobs"]["check"]["steps"]:
        if step.get("name") == "Route non-conforming issue to the optimizer":
            return step["run"]
    raise AssertionError(f"routing step not found in {path}")


def _fingerprint(body: str) -> str:
    import hashlib

    # `jq -r '.body'` appends one newline before sha256sum hashes body.md.
    return hashlib.sha256((body + "\n").encode()).hexdigest()[:12]


def _run_route_step(
    tmp_path: Path, guard_path: Path, comments: list[tuple[dict, str]]
) -> tuple[str, str]:
    """Return (gh calls, stdout) after the real routing step runs."""
    (tmp_path / ".github/scripts").mkdir(parents=True)
    shutil.copy(REPO_ROOT / ".github/scripts/issue_format.py", tmp_path / ".github/scripts")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    issue = tmp_path / "issue.json"
    issue.write_text(
        json.dumps(
            {
                "number": 7,
                "state": "OPEN",
                "body": INVALID_BODY,
                "labels": [],
                "author": {"login": "stranske"},
            }
        ),
        encoding="utf-8",
    )
    fixture = tmp_path / "comments.json"
    fixture.write_text(
        json.dumps([{"user": user, "body": body} for user, body in comments]), encoding="utf-8"
    )
    preload = tmp_path / "fakes.js"
    preload.write_text(_NODE_FAKES, encoding="utf-8")
    calls = tmp_path / "gh-calls.txt"
    gh_stub = bin_dir / "gh"
    gh_stub.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [[ "$1 $2" == "issue view" ]]; then\n'
        f"  cat '{issue}'\n"
        "  exit 0\n"
        "fi\n"
        f"printf '%s\\n' \"$*\" >> '{calls}'\n"
        'if [[ "$1 $2" == "issue comment" ]]; then\n'
        f"  cat >> '{calls}'\n"
        "fi\n",
        encoding="utf-8",
    )
    gh_stub.chmod(0o755)
    completed = subprocess.run(
        ["bash", "-c", _route_step_script(guard_path)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        env={
            "PATH": f"{bin_dir}:{shutil.os.environ['PATH']}",
            "GITHUB_REPOSITORY": "stranske/Workflows",
            "NUMBER": "7",
            "GH_TOKEN": "stub",
            "FIXTURE_COMMENTS": str(fixture),
            "NODE_OPTIONS": f"--require {preload}",
        },
    )
    assert completed.returncode == 0, f"route step failed: {completed.stderr}"
    return (calls.read_text(encoding="utf-8") if calls.exists() else ""), completed.stdout


def _foreign_dispatch(n: int) -> str:
    fp = _fingerprint("some other invalid body")
    return f"<!-- format-guard:{fp} -->" if n == 1 else f"<!-- format-guard:{fp}:attempt:{n} -->"


@skip_if_no_route_tools
@pytest.mark.parametrize("guard_path", GUARD_PATHS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_outcomes_of_another_body_are_never_charged_to_this_body(
    tmp_path: Path, guard_path: Path
) -> None:
    # Body A failed once, the issue was edited to body B (which failed twice
    # and crashed once), then restored to A: only A's one failure counts.
    comments = [
        (BOT, _dispatch(1)),
        (BOT, REWRITE_FAILED),
        (BOT, _foreign_dispatch(1)),
        (BOT, REWRITE_FAILED),
        (BOT, _foreign_dispatch(2)),
        (BOT, REWRITE_FAILED),
        (APP_BOT, CRASH),
    ]
    calls, stdout = _run_route_step(tmp_path, guard_path, comments)

    assert "real rewrite attempts 1/3, optimizer crashes 0/3, dispatches 1/6" in stdout
    assert "agents:auto-pilot-pause" not in calls
    assert "workflow run agents-issue-optimizer.yml" in calls


def _dispatch(n: int) -> str:
    fp = _fingerprint(INVALID_BODY)
    return f"<!-- format-guard:{fp} -->" if n == 1 else f"<!-- format-guard:{fp}:attempt:{n} -->"


@skip_if_no_route_tools
@pytest.mark.parametrize("guard_path", GUARD_PATHS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_crash_comments_do_not_consume_real_attempt_budget(
    tmp_path: Path, guard_path: Path
) -> None:
    # Three dispatches already happened — the old cap — but only one of them was
    # a real rewrite attempt; the other two crashed (one reported by an app bot).
    comments = [
        (BOT, _dispatch(1)),
        (BOT, REWRITE_FAILED),
        (BOT, _dispatch(2)),
        (BOT, CRASH),
        (BOT, _dispatch(3)),
        (APP_BOT, CRASH),
        # Untrusted copies of the marker never count as attempts.
        (HUMAN, REWRITE_FAILED),
        (HUMAN, REWRITE_FAILED),
    ]
    calls, stdout = _run_route_step(tmp_path, guard_path, comments)

    assert "real rewrite attempts 1/3, optimizer crashes 2/3, dispatches 3/6" in stdout
    assert "workflow run agents-issue-optimizer.yml" in calls
    assert "agents:auto-pilot-pause" not in calls
    assert "real rewrite attempts so far: 1 of 3; optimizer crashes: 2 of 3" in calls


@skip_if_no_route_tools
@pytest.mark.parametrize("guard_path", GUARD_PATHS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
@pytest.mark.parametrize("outcome", ["rewrite_failed", "crash"])
def test_three_real_attempts_or_three_crashes_pause_for_the_opener_lane(
    tmp_path: Path, guard_path: Path, outcome: str
) -> None:
    result = REWRITE_FAILED if outcome == "rewrite_failed" else CRASH
    comments = []
    for n in (1, 2, 3):
        comments += [(BOT, _dispatch(n)), (BOT, result)]
    calls, stdout = _run_route_step(tmp_path, guard_path, comments)

    assert "workflow run agents-issue-optimizer.yml" not in calls
    assert "--add-label agents:auto-pilot-pause" in calls
    assert "--remove-label agents:format" in calls
    assert "<!-- format-guard:attempt-cap -->" in calls
    assert "No human action is required" in calls
    assert "opener lane (opener-core) rewrites and re-validates paused issues" in calls
    assert "Fix the issue body manually" not in calls


@skip_if_no_route_tools
@pytest.mark.parametrize("guard_path", GUARD_PATHS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_lifting_the_pause_restarts_the_budget(tmp_path: Path, guard_path: Path) -> None:
    comments = []
    for n in (1, 2, 3):
        comments += [(BOT, _dispatch(n)), (BOT, REWRITE_FAILED)]
    comments.append((BOT, CAP))
    calls, stdout = _run_route_step(tmp_path, guard_path, comments)

    assert "real rewrite attempts 0/3, optimizer crashes 0/3, dispatches 0/6" in stdout
    assert "workflow run agents-issue-optimizer.yml" in calls
    assert "agents:auto-pilot-pause" not in calls


@skip_if_no_route_tools
@pytest.mark.parametrize("guard_path", GUARD_PATHS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_dispatch_backstop_bounds_runs_with_no_recorded_outcome(
    tmp_path: Path, guard_path: Path
) -> None:
    comments = [(BOT, _dispatch(n)) for n in range(1, 7)]
    calls, stdout = _run_route_step(tmp_path, guard_path, comments)

    assert "dispatches 6/6" in stdout
    assert "workflow run agents-issue-optimizer.yml" not in calls
    assert "--add-label agents:auto-pilot-pause" in calls
