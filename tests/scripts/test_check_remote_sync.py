"""Pre-push remote checks distinguish verified absence from failed transport."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / "scripts/check_remote_sync.sh"


@pytest.fixture
def remote_checkout(tmp_path):
    git = shutil.which("git")
    assert git
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Hook scenario",
        "GIT_AUTHOR_EMAIL": "hook@example.invalid",
        "GIT_COMMITTER_NAME": "Hook scenario",
        "GIT_COMMITTER_EMAIL": "hook@example.invalid",
    }

    def call(*args, cwd=tmp_path):
        return subprocess.check_output([git, *args], cwd=cwd, env=env, text=True).strip()

    upstream = tmp_path / "upstream"
    call("init", "--quiet", "--initial-branch=main", str(upstream))
    call("commit", "--quiet", "--allow-empty", "-m", "root", cwd=upstream)
    first = call("rev-parse", "HEAD", cwd=upstream)
    call("branch", "stale", cwd=upstream)
    call("commit", "--quiet", "--allow-empty", "-m", "main advanced", cwd=upstream)
    call("branch", "namespace/subonly", cwd=upstream)
    call("switch", "--quiet", "-c", "diverged", cwd=upstream)
    call("commit", "--quiet", "--allow-empty", "-m", "remote-only topic", cwd=upstream)
    call("switch", "--quiet", "main", cwd=upstream)
    reader = tmp_path / "reader"
    call("clone", "--quiet", str(upstream), str(reader))
    # Existing named branch, even when it is already synchronized.
    call("branch", "same", cwd=upstream)
    call("switch", "--quiet", "-c", "same", cwd=reader)
    missing = tmp_path / "unreachable"
    call("remote", "add", "missing", str(missing), cwd=reader)
    call("remote", "add", "other", str(upstream), cwd=reader)

    shim = tmp_path / "git"
    shim.write_text(
        """#!/bin/bash
if [[ "$1" == fetch && -n "${TEST_FAIL_REF:-}" ]]; then
    for argument in "$@"; do
        if [[ "$argument" == "$TEST_FAIL_REF" || "$argument" == "refs/heads/$TEST_FAIL_REF" ]]; then
            exec "$REAL_GIT" fetch --quiet "$TEST_MISSING_REMOTE" "refs/heads/$TEST_FAIL_REF"
        fi
    done
fi
exec "$REAL_GIT" "$@"
""",
        encoding="utf-8",
    )
    shim.chmod(0o755)

    def replay(*args, fail_ref="", override=False):
        return subprocess.run(
            ["bash", str(HOOK), *args],
            cwd=reader,
            env={
                **env,
                "PATH": f"{tmp_path}{os.pathsep}{env['PATH']}",
                "REAL_GIT": git,
                "TEST_FAIL_REF": fail_ref,
                "TEST_MISSING_REMOTE": str(missing),
                "ALLOW_NON_FAST_FORWARD_PUSH": "1" if override else "0",
            },
            capture_output=True,
            text=True,
            check=False,
        )

    return call, reader, first, replay


@pytest.mark.parametrize(
    ("remote", "fail_ref", "error"),
    [
        ("missing", "", "Could not inspect missing/same"),
        ("origin", "same", "Could not fetch origin/same"),
        ("origin", "main", "Could not fetch origin/main"),
    ],
)
def test_remote_transport_failure_cannot_pass(remote_checkout, remote, fail_ref, error):
    *_, replay = remote_checkout
    result = replay(remote, fail_ref=fail_ref, override=True)
    assert result.returncode == 128
    assert error in result.stderr
    assert "New branch" not in result.stdout
    assert "Branch includes latest" not in result.stdout
    assert "Branch is in sync" not in result.stdout


def test_absent_and_detached_branches_keep_the_optional_hook_contract(remote_checkout):
    call, reader, first, replay = remote_checkout
    assert replay().returncode == replay("other").returncode == 0
    # The remote contains namespace/subonly, not this exact branch.
    call("switch", "--quiet", "-c", "subonly", cwd=reader)
    absent = replay()
    assert absent.returncode == 0
    assert "New branch" in absent.stdout

    call("switch", "--quiet", "--detach", first, cwd=reader)
    detached = replay("missing")
    assert detached.returncode == 0
    assert "Detached HEAD" in detached.stdout
    assert "New branch" not in detached.stdout


def test_stale_and_divergent_branches_remain_distinct(remote_checkout):
    call, reader, first, replay = remote_checkout
    call("switch", "--quiet", "-c", "stale", first, cwd=reader)
    stale = replay()
    assert stale.returncode == 1
    assert "does not include the latest origin/main" in stale.stdout

    call("switch", "--quiet", "-c", "diverged", "main", cwd=reader)
    # This narrower fetch map intentionally leaves origin/diverged stale/unavailable.
    call("config", "remote.origin.fetch", "+refs/heads/main:refs/remotes/origin/main", cwd=reader)
    call("update-ref", "-d", "refs/remotes/origin/diverged", cwd=reader)
    diverged = replay()
    assert diverged.returncode == 1
    assert "missing 1 commit(s) from origin/diverged" in diverged.stdout
    assert "Override enabled" in replay(override=True).stdout
