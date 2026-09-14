"""The codex sandbox-startup detection must fire on stderr and never on the agent's prose.

Background (#3438): codex's workspace-write sandbox shells out to bubblewrap, which cannot
bring up loopback on Ubuntu 24.04+ runners. Every shell command dies before it runs and codex
reports the turn as a SUCCESS, so the workflow has to detect the failure itself.

The detection reads the capture file that holds BOTH codex's ``--json`` event stream and its
stderr. That is the trap: an unanchored ``bwrap:`` match would also fire on an ``agent_message``
that merely quotes the error — including an agent working on this very incident — which would
retry a healthy run with a weakened sandbox and then force it to exit 1. These tests run the
workflow's own pattern against both shapes.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "reusable-codex-run.yml"

REAL_STDERR_LINE = "bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted"
AGENT_MESSAGE_QUOTING_THE_ERROR = (
    '{"type":"item.completed","item":{"id":"item_1","type":"agent_message","text":'
    '"I fixed the sandbox repair: bwrap: loopback: Failed RTM_NEWADDR no longer blocks us."}}'
)


def _codex_run_step_body() -> str:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    bodies = [
        step["run"]
        for job in document["jobs"].values()
        for step in job.get("steps", [])
        if isinstance(step.get("run"), str) and "codex exec" in step["run"]
    ]
    assert len(bodies) == 1, f"expected exactly one codex exec step, found {len(bodies)}"
    return bodies[0]


@pytest.fixture(scope="module")
def sandbox_failure_pattern() -> str:
    """The regex the workflow actually uses, read out of the workflow itself."""
    match = re.search(
        r"^\s*SANDBOX_STARTUP_FAILURE_RE='([^']+)'", _codex_run_step_body(), re.MULTILINE
    )
    assert match, "SANDBOX_STARTUP_FAILURE_RE is not defined in the codex exec step"
    return match.group(1)


def _matches(pattern: str, text: str) -> bool:
    """Run the pattern exactly as the workflow does: grep -Eq over the capture file."""
    result = subprocess.run(
        ["grep", "-Eq", pattern],
        input=text,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def test_detects_a_real_sandbox_startup_failure(sandbox_failure_pattern: str) -> None:
    capture = "Reading additional input from stdin...\n" + REAL_STDERR_LINE + "\n"

    assert _matches(sandbox_failure_pattern, capture)


def test_does_not_fire_on_an_agent_message_that_quotes_the_error(
    sandbox_failure_pattern: str,
) -> None:
    """A successful run that merely discusses bubblewrap must not be treated as blocked."""
    capture = (
        '{"type":"thread.started","thread_id":"abc"}\n'
        + AGENT_MESSAGE_QUOTING_THE_ERROR
        + "\n"
        + '{"type":"turn.completed","usage":{"output_tokens":42}}\n'
    )

    assert not _matches(sandbox_failure_pattern, capture)


def test_does_not_fire_on_a_clean_session(sandbox_failure_pattern: str) -> None:
    capture = (
        '{"type":"thread.started","thread_id":"abc"}\n'
        '{"type":"item.completed","item":{"type":"agent_message","text":"Added the loader."}}\n'
    )

    assert not _matches(sandbox_failure_pattern, capture)


def test_the_pattern_is_anchored(sandbox_failure_pattern: str) -> None:
    """Pin the property, not just the behaviour.

    Dropping the anchor is the single edit that reintroduces the false positive, and it would
    still pass a test that only checked the real stderr line.
    """
    assert sandbox_failure_pattern.startswith("^"), sandbox_failure_pattern


def test_sandbox_repair_is_scoped_to_workspace_write() -> None:
    """A read-only run must not disable a host-wide kernel mitigation it cannot benefit from."""
    body = _codex_run_step_body()
    guard = re.search(
        r'if \[ "\$SANDBOX" = "workspace-write" \] &&\s*\n'
        r'\s*\[ "\$\(cat /proc/sys/kernel/apparmor_restrict_unprivileged_userns',
        body,
    )
    assert guard, "the apparmor relaxation is not gated on SANDBOX = workspace-write"


def test_network_fallback_is_bounded_and_scoped() -> None:
    body = _codex_run_step_body()
    assert "SANDBOX_NETWORK_FALLBACK_USED:-no" in body, "the retry is not guarded by a flag"
    assert body.count('SANDBOX_NETWORK_FALLBACK_USED="yes"') == 1, "the guard is never set"
    assert "sandbox_workspace_write.network_access=true" in body


def test_a_failed_sandbox_cannot_report_success() -> None:
    """codex exits 0 when its sandbox dies; that is what let a dead run look healthy."""
    body = _codex_run_step_body()
    forced = re.search(
        r'if grep -Eq "\$SANDBOX_STARTUP_FAILURE_RE" "\$attempt_session" 2>/dev/null; then'
        r"(?:.|\n)*?CODEX_EXIT=1",
        body,
    )
    assert forced, "a detected sandbox startup failure does not force a non-zero exit"
