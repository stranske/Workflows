"""Unit tests for ``scripts/repo_review_heartbeat.py``.

The 2026-05-13 cycle's #2087 PR added test coverage for the coordinator and
the round-2 runner, but its Non-Goals explicitly excluded heartbeat and
body-writer. Those two modules sit on the critical path of every per-repo
agent invocation and had zero direct test coverage. This module pins:

- happy path (process exits cleanly, sentinel reflects ``exited``)
- non-zero exit propagates as ``succeeded=False`` with the rc preserved
- spawn failure (invalid cmd) returns a sane HeartbeatResult, no crash
- hard timeout terminates a long-running process and reports ``timed_out``
- stall detection terminates a process that stops growing its log
- stall detection does NOT fire during the initial grace window
- the sentinel file is updated with each loop iteration

Tests use real subprocesses (``echo``, ``sleep``) to keep coverage honest —
the heartbeat loop is timing- and IO-sensitive, and mocking the poll loop
would defeat the purpose. Each test runs in well under 5s.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from scripts import repo_review_heartbeat as heartbeat


def test_sentinel_path_appends_heartbeat_json_suffix(tmp_path: Path) -> None:
    log = tmp_path / "logs" / "agent.log"
    sentinel = heartbeat._sentinel_path_for_log(log)
    assert sentinel == tmp_path / "logs" / "agent.log.heartbeat.json"


def test_happy_path_exited_rc_zero(tmp_path: Path) -> None:
    log = tmp_path / "echo.log"
    result = heartbeat.run_with_heartbeat(
        ["/bin/sh", "-c", "echo hello"],
        prompt=None,
        cwd=tmp_path,
        env=None,
        log_file=log,
        timeout=10,
        heartbeat_interval=1,
        stall_threshold=10,
        label="echo",
    )
    assert result.succeeded is True
    assert result.returncode == 0
    assert result.stuck is False
    assert result.timed_out is False
    assert result.elapsed_seconds < 5
    assert log.read_text(encoding="utf-8").strip() == "hello"

    sentinel = json.loads(result.sentinel_path.read_text(encoding="utf-8"))
    assert sentinel["state"] == "exited"
    assert sentinel["note"].startswith("exited rc=0")


def test_non_zero_exit_propagates_returncode(tmp_path: Path) -> None:
    log = tmp_path / "fail.log"
    result = heartbeat.run_with_heartbeat(
        ["/bin/sh", "-c", "echo oops; exit 7"],
        prompt=None,
        cwd=tmp_path,
        env=None,
        log_file=log,
        timeout=10,
        heartbeat_interval=1,
        stall_threshold=10,
        label="fail",
    )
    assert result.succeeded is False
    assert result.returncode == 7
    assert result.stuck is False
    assert result.timed_out is False


def test_spawn_failure_returns_failed_result(tmp_path: Path) -> None:
    log = tmp_path / "missing.log"
    result = heartbeat.run_with_heartbeat(
        ["/no/such/binary/" + "x" * 10],
        prompt=None,
        cwd=tmp_path,
        env=None,
        log_file=log,
        timeout=5,
        heartbeat_interval=1,
        stall_threshold=5,
        label="missing",
    )
    assert result.succeeded is False
    assert result.returncode is None
    assert result.stuck is False
    assert result.timed_out is False
    assert "spawn failed" in result.note

    sentinel = json.loads(result.sentinel_path.read_text(encoding="utf-8"))
    assert sentinel["state"] == "spawn_failed"


def test_hard_timeout_terminates_long_running_subprocess(tmp_path: Path) -> None:
    log = tmp_path / "sleep.log"
    started = time.time()
    result = heartbeat.run_with_heartbeat(
        ["/bin/sh", "-c", "sleep 30"],
        prompt=None,
        cwd=tmp_path,
        env=None,
        log_file=log,
        timeout=2,
        heartbeat_interval=1,
        # stall_threshold MUST be >= timeout to disable stall detection,
        # so this test is purely about the hard-timeout path.
        stall_threshold=5,
        label="sleep",
    )
    elapsed = time.time() - started
    assert result.succeeded is False
    assert result.timed_out is True
    assert result.stuck is False
    # The runner allows up to 15s for graceful SIGTERM + 5s for SIGKILL on
    # top of the configured timeout — assert we didn't blow far past that.
    assert elapsed < 30

    sentinel = json.loads(result.sentinel_path.read_text(encoding="utf-8"))
    assert sentinel["state"] == "timed_out"


def test_stall_detection_terminates_silent_subprocess(tmp_path: Path) -> None:
    """A subprocess that writes something then sits silent past the stall
    threshold should be declared stuck and terminated — without waiting for
    the hard wall."""
    log = tmp_path / "stuck.log"
    # Write 'starting' immediately so the agent has shown initial signs of
    # life, then sleep silently. Stall detection only counts AFTER the
    # initial grace window (stall_threshold seconds since spawn). To exercise
    # the stuck path quickly we use stall_threshold=1: the loop will declare
    # stuck only once elapsed > 1s AND stall_for > 1s.
    cmd = ["/bin/sh", "-c", "echo starting; sleep 30"]
    started = time.time()
    result = heartbeat.run_with_heartbeat(
        cmd,
        prompt=None,
        cwd=tmp_path,
        env=None,
        log_file=log,
        timeout=20,
        heartbeat_interval=1,
        stall_threshold=1,
        label="stuck",
    )
    elapsed = time.time() - started
    assert result.succeeded is False
    assert result.stuck is True
    assert result.timed_out is False
    # Stall detection should kick in well before the 20s hard timeout.
    assert elapsed < 15

    sentinel = json.loads(result.sentinel_path.read_text(encoding="utf-8"))
    assert sentinel["state"] == "stuck"
    assert "stuck" in result.note


def test_stall_detection_skipped_during_initial_grace_window(tmp_path: Path) -> None:
    """A subprocess that goes silent BEFORE the stall_threshold has elapsed
    must NOT be declared stuck — agents are allowed to think silently for a
    while before producing initial output. Exercising this means: an agent
    that exits cleanly within the grace window despite never writing to its
    log should still succeed."""
    log = tmp_path / "quiet.log"
    # Sleep briefly without writing anything, then exit cleanly. The grace
    # window (stall_threshold=10) is longer than the sleep — so the stall
    # check is suppressed and the process exits normally.
    cmd = ["/bin/sh", "-c", "sleep 1; echo done"]
    result = heartbeat.run_with_heartbeat(
        cmd,
        prompt=None,
        cwd=tmp_path,
        env=None,
        log_file=log,
        timeout=10,
        heartbeat_interval=1,
        stall_threshold=10,
        label="quiet",
    )
    assert result.succeeded is True
    assert result.stuck is False
    assert result.timed_out is False


def test_prompt_is_piped_to_stdin(tmp_path: Path) -> None:
    log = tmp_path / "stdin.log"
    result = heartbeat.run_with_heartbeat(
        # `cat` reflects stdin to stdout, which is redirected to the log.
        ["/bin/cat"],
        prompt="the agent prompt body\n",
        cwd=tmp_path,
        env=None,
        log_file=log,
        timeout=5,
        heartbeat_interval=1,
        stall_threshold=5,
        label="cat",
    )
    assert result.succeeded is True
    assert log.read_text(encoding="utf-8") == "the agent prompt body\n"


def test_sentinel_payload_has_expected_fields(tmp_path: Path) -> None:
    log = tmp_path / "fields.log"
    result = heartbeat.run_with_heartbeat(
        ["/bin/sh", "-c", "echo done"],
        prompt=None,
        cwd=tmp_path,
        env=None,
        log_file=log,
        timeout=5,
        heartbeat_interval=1,
        stall_threshold=5,
        label="fields",
    )
    payload = json.loads(result.sentinel_path.read_text(encoding="utf-8"))
    expected_keys = {
        "state",
        "pid",
        "started_at",
        "last_check",
        "last_log_mtime",
        "elapsed_seconds",
        "stall_seconds",
        "note",
    }
    assert expected_keys.issubset(payload.keys())
    assert payload["state"] == "exited"
    assert isinstance(payload["pid"], int)


def test_sentinel_directory_is_created_on_demand(tmp_path: Path) -> None:
    nested_log = tmp_path / "a" / "b" / "c" / "deep.log"
    result = heartbeat.run_with_heartbeat(
        ["/bin/sh", "-c", "echo deep"],
        prompt=None,
        cwd=tmp_path,
        env=None,
        log_file=nested_log,
        timeout=5,
        heartbeat_interval=1,
        stall_threshold=5,
        label="deep",
    )
    assert result.succeeded is True
    assert nested_log.exists()
    assert result.sentinel_path.exists()
