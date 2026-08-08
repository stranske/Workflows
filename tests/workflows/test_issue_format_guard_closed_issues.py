"""The format guard must not process closed issues.

These tests execute the guard's real "Resolve issue" step, lifted straight out of
the workflow YAML, against a fixture issue payload. A closed issue routed to the
optimizer produces a body edit, that edit re-fires the guard, and the pair loops
against already-delivered work: Fine-Art-Archive#464 kept formatting for 17.5
hours after it was closed.
"""

from __future__ import annotations

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
