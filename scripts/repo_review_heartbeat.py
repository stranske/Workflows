"""Heartbeat-aware subprocess runner for round-1 + round-2 + body-writer agents.

The hard-timeout-only model (90-min wall) hid two problems in the pilot:

1. The Claude subagent sometimes vanished without writing anything or returning
   an error code; the runner only learned about it at the 90-min wall.
2. Agents that were genuinely stuck (waiting on a hung shell, deadlocked) ate
   their full timeout budget and blocked the whole repo's flow.

Heartbeat polling addresses both: while the agent is running, periodically
check whether the log file's mtime is advancing. If nothing has been written
for `stall_threshold` seconds, declare the agent stuck and terminate it. The
caller's retry budget then has a chance to fire on a fresh process instead of
waiting for the wall.

Heartbeat status is also written to a per-agent sentinel JSON next to the log,
which lets a separate observer (the per-repo state.json watcher) surface
progress to the human-decision-packet without re-tailing logs.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class HeartbeatResult:
    """Outcome of a heartbeat-supervised subprocess run."""

    succeeded: bool
    returncode: int | None
    elapsed_seconds: float
    stuck: bool
    timed_out: bool
    last_log_mtime: float | None
    note: str
    sentinel_path: Path


def _sentinel_path_for_log(log_file: Path) -> Path:
    return log_file.with_suffix(log_file.suffix + ".heartbeat.json")


def _write_sentinel(
    sentinel_path: Path,
    *,
    state: str,
    pid: int | None,
    started_at: float,
    last_check: float,
    last_log_mtime: float | None,
    elapsed: float,
    stall_for: float | None,
    note: str = "",
) -> None:
    payload: dict[str, Any] = {
        "state": state,
        "pid": pid,
        "started_at": started_at,
        "last_check": last_check,
        "last_log_mtime": last_log_mtime,
        "elapsed_seconds": round(elapsed, 1),
        "stall_seconds": round(stall_for, 1) if stall_for is not None else None,
        "note": note,
    }
    sentinel_path.parent.mkdir(parents=True, exist_ok=True)
    sentinel_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _safe_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except (FileNotFoundError, OSError):
        return None


def run_with_heartbeat(
    cmd: list[str],
    *,
    prompt: str | None,
    cwd: Path,
    env: dict[str, str] | None,
    log_file: Path,
    timeout: int,
    heartbeat_interval: int = 60,
    stall_threshold: int = 600,
    label: str = "agent",
) -> HeartbeatResult:
    """Spawn cmd with stdout/stderr → log_file, supervised by a heartbeat loop.

    - `heartbeat_interval`: seconds between mtime checks. Default 60s.
    - `stall_threshold`: seconds the log can go without growing before we declare
      the agent stuck and SIGTERM it. Default 600s (10 min). Set to a value
      ≥ timeout to disable stall detection.
    - `timeout`: hard wall. The agent is SIGTERM'd at this point regardless.

    The first `stall_threshold` seconds are NOT checked for stalls — agents
    legitimately can think silently for several minutes before producing
    output. Only stalls AFTER the agent has shown initial signs of life count.
    """
    log_file.parent.mkdir(parents=True, exist_ok=True)
    sentinel_path = _sentinel_path_for_log(log_file)
    started_at = time.time()
    last_log_mtime: float | None = None
    last_growth_time: float = started_at

    _write_sentinel(
        sentinel_path,
        state="starting",
        pid=None,
        started_at=started_at,
        last_check=started_at,
        last_log_mtime=None,
        elapsed=0.0,
        stall_for=None,
        note=f"{label}: spawning",
    )

    log_handle = log_file.open("w", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=env or os.environ.copy(),
            stdin=subprocess.PIPE if prompt is not None else None,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
    except OSError as exc:
        log_handle.close()
        _write_sentinel(
            sentinel_path,
            state="spawn_failed",
            pid=None,
            started_at=started_at,
            last_check=time.time(),
            last_log_mtime=None,
            elapsed=time.time() - started_at,
            stall_for=None,
            note=f"OSError: {exc}",
        )
        return HeartbeatResult(
            succeeded=False,
            returncode=None,
            elapsed_seconds=time.time() - started_at,
            stuck=False,
            timed_out=False,
            last_log_mtime=None,
            note=f"spawn failed: {exc}",
            sentinel_path=sentinel_path,
        )

    pid = proc.pid

    # Send the prompt non-blockingly via stdin if we have one. We close stdin
    # afterward so the agent sees EOF and proceeds.
    if prompt is not None and proc.stdin is not None:
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass  # agent already crashed; we'll catch it in the poll loop.

    stuck = False
    timed_out = False
    note = ""
    try:
        while True:
            rc = proc.poll()
            now = time.time()
            elapsed = now - started_at
            current_mtime = _safe_mtime(log_file)
            if current_mtime is not None and (
                last_log_mtime is None or current_mtime > last_log_mtime
            ):
                last_log_mtime = current_mtime
                last_growth_time = now
            stall_for = now - last_growth_time

            if rc is not None:
                # Process exited.
                _write_sentinel(
                    sentinel_path,
                    state="exited",
                    pid=pid,
                    started_at=started_at,
                    last_check=now,
                    last_log_mtime=last_log_mtime,
                    elapsed=elapsed,
                    stall_for=stall_for,
                    note=f"exited rc={rc}",
                )
                return HeartbeatResult(
                    succeeded=(rc == 0),
                    returncode=rc,
                    elapsed_seconds=elapsed,
                    stuck=False,
                    timed_out=False,
                    last_log_mtime=last_log_mtime,
                    note=f"exited rc={rc}",
                    sentinel_path=sentinel_path,
                )

            if elapsed >= timeout:
                timed_out = True
                note = f"hard timeout after {timeout}s (log mtime advanced {stall_for:.0f}s ago)"
                break

            # Stall detection: only after the initial stall_threshold seconds
            # have elapsed since spawn — agents can legitimately spend several
            # minutes thinking before producing any output.
            if (
                elapsed > stall_threshold
                and stall_for > stall_threshold
                and stall_threshold < timeout
            ):
                stuck = True
                note = (
                    f"stuck: log mtime has not advanced for {stall_for:.0f}s "
                    f"(threshold {stall_threshold}s, elapsed {elapsed:.0f}s)"
                )
                break

            _write_sentinel(
                sentinel_path,
                state="running",
                pid=pid,
                started_at=started_at,
                last_check=now,
                last_log_mtime=last_log_mtime,
                elapsed=elapsed,
                stall_for=stall_for,
                note=f"{label}: alive, log {'growing' if stall_for < heartbeat_interval else f'idle for {stall_for:.0f}s'}",
            )
            time.sleep(heartbeat_interval)

        # Reached only on stuck or timed_out. Terminate.
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=5)
        except ProcessLookupError:
            pass
        elapsed = time.time() - started_at
        _write_sentinel(
            sentinel_path,
            state="stuck" if stuck else "timed_out",
            pid=pid,
            started_at=started_at,
            last_check=time.time(),
            last_log_mtime=last_log_mtime,
            elapsed=elapsed,
            stall_for=time.time() - last_growth_time,
            note=note,
        )
        return HeartbeatResult(
            succeeded=False,
            returncode=proc.returncode,
            elapsed_seconds=elapsed,
            stuck=stuck,
            timed_out=timed_out,
            last_log_mtime=last_log_mtime,
            note=note,
            sentinel_path=sentinel_path,
        )
    finally:
        with contextlib.suppress(OSError):
            log_handle.close()
