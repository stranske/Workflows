"""Exercise the actual Codex publication shell against disposable Git refs."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/reusable-codex-run.yml"
GIT = shutil.which("git")
REPO = "stranske/Workflows"


def git(cwd: Path, *args: str) -> str:
    return subprocess.check_output([GIT, *args], cwd=cwd, text=True).strip()


@pytest.fixture
def publisher(tmp_path):
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["codex"]["steps"]
    worker = next(step for step in steps if step.get("id") == "run_codex")
    final = next(step for step in steps if step.get("id") == "commit")
    prepare = next(step for step in steps if step.get("id") == "branch_publisher")
    for step in (worker, final):
        assert step["env"]["PUSH_CODEX_BRANCH"] == "${{ steps.branch_publisher.outputs.shell }}"
        assert step["env"]["CODEX_API_CLIENT"] == "${{ steps.branch_publisher.outputs.api_client }}"
    definition = tmp_path / "publisher-definition"
    subprocess.run(
        ["bash", "-e", "-c", prepare["run"]],
        env={**os.environ, "MODE": "autofix", "PR_NUM": "", "GITHUB_OUTPUT": str(definition)},
        check=True,
    )
    content = definition.read_text()
    assert content.startswith("shell<<CODEX_PUBLISHER\n")
    assert content.endswith("\nCODEX_PUBLISHER\n")
    policy = content.removeprefix("shell<<CODEX_PUBLISHER\n").removesuffix("CODEX_PUBLISHER\n")
    for step in (worker, final):
        step["env"]["PUSH_CODEX_BRANCH"] = policy
    local = tmp_path / "local"
    local.mkdir()
    bare = tmp_path / "remote"
    git(tmp_path, "init", "--bare", "-q", str(bare))
    git(local, "init", "-q", "-b", "topic")
    git(local, "config", "user.name", "Test")
    git(local, "config", "user.email", "test@example.invalid")
    patch = local / "tracked.txt"
    patch.write_text("base\n")
    git(local, "add", "tracked.txt")
    git(local, "commit", "-qm", "base")
    head = git(local, "rev-parse", "HEAD")
    git(local, "push", "-q", str(bare), "HEAD:refs/heads/topic")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stubs = {
        "git": """
            case "$1" in
              push)
                printf 'push\n' >> "$CALLS"
                if [ -n "${MOVE_AT_PUSH:-}" ]; then
                  "$REAL_GIT" --git-dir="$TEST_REMOTE" update-ref refs/heads/topic "$MOVE_AT_PUSH"
                fi
                case "$2" in
                  --porcelain) exec "$REAL_GIT" push "$2" "$3" "$TEST_REMOTE" "$5" ;;
                  *) exec "$REAL_GIT" push "$TEST_REMOTE" "$3" ;;
                esac ;;
              fetch)
                if [ "$STATE" = close-on-retry ]; then
                  printf '%s\n' "$PR_HEAD" > .git/FETCH_HEAD
                  exit 0
                fi
                exec "$REAL_GIT" fetch "$TEST_REMOTE" "$3" ;;
              pull)
                if [ "$STATE" = close-during-fallback ]; then
                  "$REAL_GIT" --git-dir="$TEST_REMOTE" update-ref -d refs/heads/topic
                fi
                exec "$REAL_GIT" pull --no-rebase "$TEST_REMOTE" "$4" --allow-unrelated-histories ;;
              *) exec "$REAL_GIT" "$@" ;;
            esac
        """,
        "sleep": "exit 0",
        "timeout": 'shift; exec "$@"',
        "python3": """
            if [ "$1" = -IS ]; then
              shift 2
              exec "$REAL_PYTHON" -IS "$HTTP_REPLAY" "$@"
            fi
            exec "$REAL_GIT" add tracked.txt
        """,
    }
    for name, body in stubs.items():
        path = bin_dir / name
        path.write_text("#!/bin/bash\n" + body)
        path.chmod(0o700)

    driver = tmp_path / "api-replay.py"
    driver.write_text(r"""
import importlib.util
import io
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import urllib.response

assert importlib.util.find_spec("requests") is None
repo, number = sys.argv[1:]
assert repo == "stranske/Workflows" and number == "5232"

def https_open(self, request):
    assert request.method == "GET"
    assert request.full_url == "https://api.github.com/repos/stranske/Workflows/pulls/5232"
    assert request.get_header("Authorization") == "Bearer test-app"
    with open(os.environ["CALLS"], "a") as file:
        file.write("read\n")
    state = os.environ["STATE"]
    if state == "unavailable":
        raise urllib.error.URLError("unavailable")
    if state == "unauthorized":
        raise urllib.error.HTTPError(request.full_url, 403, "auth", {}, None)
    if state == "redirect":
        # Returning a redirect exercises urllib's actual handler chain and the workflow's refusal.
        response = urllib.response.addinfourl(
            io.BytesIO(b""), {"location": "https://other.invalid/pull"}, request.full_url, 302
        )
        response.msg = "Temporary redirect"
        return response
    if state == "close-on-retry":
        with open(os.environ["CALLS"]) as file:
            state = "closed" if "push" in file.read().splitlines() else "open"
    if state == "close-during-fallback":
        ref = subprocess.run(
            [os.environ["REAL_GIT"], f"--git-dir={os.environ['TEST_REMOTE']}",
             "show-ref", "--verify", "--quiet", "refs/heads/topic"],
        )
        state = "closed" if ref.returncode else "open"
    payload = {
        "number": int(number),
        "state": state,
        "head": {"repo": {"full_name": os.environ["HEAD_REPO"]},
                 "ref": os.environ["HEAD_REF"], "sha": os.environ["PR_HEAD"]},
        "base": {"repo": {"full_name": repo}},
    }
    response = urllib.response.addinfourl(
        io.BytesIO(json.dumps(payload).encode()), {}, request.full_url, 200
    )
    response.msg = "OK"
    return response

urllib.request.HTTPSHandler.https_open = https_open
exec(compile(sys.stdin.read(), "<publisher>", "exec"))
""")
    calls = tmp_path / "calls"
    calls.touch()
    outputs = tmp_path / "outputs"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "REAL_GIT": GIT,
        "REAL_PYTHON": str(Path(sys.executable).resolve()),
        "CODEX_API_CLIENT": base64.b64encode(
            (ROOT / "scripts/api_client.py").read_bytes()
        ).decode(),
        "HTTP_REPLAY": str(driver),
        "TEST_REMOTE": str(bare),
        "CALLS": str(calls),
        "GITHUB_OUTPUT": str(outputs),
        "GITHUB_REPOSITORY": REPO,
        "PUSH_ALLOWED": "true",
        "PUSH_TOKEN": "test-app",
        "PR_NUMBER": "5232",
        "PR_REF": "refs/heads/topic",
        "MODE": "keepalive",
        "STATE": "open",
        "HEAD_REF": "topic",
        "HEAD_REPO": REPO,
        "PR_HEAD": head,
    }
    return worker, final, local, bare, patch, env, calls, outputs


def run_final(publisher):
    _, final, local, _, _, env, calls, outputs = publisher
    script = final["run"].replace("${{ github.repository }}", REPO)
    script = script.replace("${{ github.ref_name }}", "topic")
    result = subprocess.run(
        ["bash", "-c", script], cwd=local, env=env, capture_output=True, text=True
    )
    return (
        result,
        calls.read_text().splitlines(),
        dict(line.split("=", 1) for line in outputs.read_text().splitlines()),
    )


@pytest.mark.parametrize("work", ["staged-work", "existing-commit", "artifact-and-commit"])
def test_closed_pr_refuses_final_publication(publisher, work):
    _, final, local, bare, patch, env, _, _ = publisher
    env["PUSH_CODEX_BRANCH"] = final["env"].get("PUSH_CODEX_BRANCH", "")
    env["STATE"] = "closed"
    if work != "artifact-and-commit":
        git(bare, "update-ref", "-d", "refs/heads/topic")
    patch.write_text("new work\n")
    if work != "staged-work":
        git(local, "commit", "-qam", "worker commit")
    if work == "artifact-and-commit":
        (local / "codex-session.jsonl").write_text("local artifact")
    result, calls, outputs = run_final(publisher)
    assert result.returncode == 0, result.stderr
    assert calls == ["read"], "closed PR must make zero Git push attempts"
    assert outputs["changes-made"] == "false"
    assert outputs["commit-sha"] == ""


@pytest.mark.parametrize(
    ("state", "head_repo", "mode", "pr_number", "expected"),
    [
        ("open", REPO, "keepalive", "5232", ["read", "push"]),
        ("open", "another/fork", "keepalive", "5232", ["read"]),
        ("unavailable", REPO, "keepalive", "5232", ["read"]),
        ("unauthorized", REPO, "keepalive", "5232", ["read"]),
        ("redirect", REPO, "keepalive", "5232", ["read"]),
        ("unknown", REPO, "keepalive", "5232", ["read"]),
        ("closed", REPO, "autofix", "5232", ["push"]),
        ("closed", REPO, "keepalive", "", ["push"]),
    ],
    ids=[
        "open",
        "wrong-repo",
        "unavailable",
        "unauthorized",
        "redirect",
        "unknown",
        "autofix",
        "no-pr",
    ],
)
def test_publication_matches_open_target(publisher, state, head_repo, mode, pr_number, expected):
    _, final, local, bare, patch, env, _, _ = publisher
    env["PUSH_CODEX_BRANCH"] = final["env"].get("PUSH_CODEX_BRANCH", "")
    env.update(STATE=state, HEAD_REPO=head_repo, MODE=mode, PR_NUMBER=pr_number)
    patch.write_text("new work\n")
    result, calls, outputs = run_final(publisher)
    assert calls == expected
    published = "push" in calls
    assert result.returncode == (0 if published else 1), result.stderr
    assert outputs["changes-made"] == str(published).lower()
    expected_sha = git(local, "rev-parse", "HEAD") if published else ""
    assert outputs["commit-sha"] == expected_sha
    assert git(bare, "rev-parse", "refs/heads/topic") == (expected_sha or env["PR_HEAD"])


def test_open_pr_accepts_concurrent_work_after_normal_rebase(publisher):
    _, final, local, bare, patch, env, _, _ = publisher
    env["PUSH_CODEX_BRANCH"] = final["env"]["PUSH_CODEX_BRANCH"]
    (local / "teammate.txt").write_text("concurrent change")
    git(local, "add", "teammate.txt")
    git(local, "commit", "-qm", "concurrent change")
    head = git(local, "rev-parse", "HEAD")
    git(local, "push", "-q", str(bare), "HEAD:refs/heads/topic")
    git(local, "checkout", "-q", "--detach", env["PR_HEAD"])
    patch.write_text("worker change")
    env["PR_HEAD"] = head
    result, calls, outputs = run_final(publisher)
    assert result.returncode == 0, result.stderr
    assert calls == ["read", "push"]
    assert outputs["changes-made"] == "true"
    accepted = git(bare, "rev-parse", "refs/heads/topic")
    assert accepted == outputs["commit-sha"]
    assert git(bare, "rev-parse", accepted + "^") == head


@pytest.mark.parametrize("state", ["closed", "close-during-fallback"])
def test_closed_pr_with_conflicting_existing_commit_skips_publication(publisher, state):
    _, final, local, bare, patch, env, _, _ = publisher
    env["PUSH_CODEX_BRANCH"] = final["env"]["PUSH_CODEX_BRANCH"]
    env["STATE"] = state
    patch.write_text("concurrent change")
    git(local, "commit", "-qam", "concurrent change")
    git(local, "push", "-q", str(bare), "HEAD:refs/heads/topic")
    env["PR_HEAD"] = git(local, "rev-parse", "HEAD")
    git(local, "checkout", "-q", "--detach", env["PR_HEAD"] + "^")
    patch.write_text("worker conflict")
    git(local, "commit", "-qam", "worker change")
    result, calls, outputs = run_final(publisher)
    assert result.returncode == 0, result.stderr
    assert calls == ["read"]
    assert outputs["changes-made"] == "false"
    assert outputs["commit-sha"] == ""


@pytest.mark.parametrize(
    ("race", "expected_attempts"),
    [
        ("new-branch-head", ["read", "push"]),
        ("already-published", ["read", "push"]),
        ("divergent-local", ["read"]),
    ],
)
def test_watchdog_publisher_distinguishes_stale_and_no_op(publisher, race, expected_attempts):
    worker, _, local, bare, patch, env, calls, _ = publisher
    policy = worker["env"]["PUSH_CODEX_BRANCH"]
    patch.write_text("another writer's change")
    git(local, "commit", "-qam", "concurrent change")
    other_head = git(local, "rev-parse", "HEAD")
    git(local, "push", "-q", str(bare), "HEAD:refs/heads/other")
    git(local, "checkout", "-q", "--detach", env["PR_HEAD"])
    patch.write_text("worker change")
    git(local, "commit", "-qam", "worker change")
    candidate = git(local, "rev-parse", "HEAD")

    # Share the candidate with the private remote without changing the target branch yet.
    git(local, "push", "-q", str(bare), "HEAD:refs/heads/candidate")
    if race == "already-published":
        env["MOVE_AT_PUSH"] = candidate
    elif race == "new-branch-head":
        env["MOVE_AT_PUSH"] = other_head
    else:
        git(bare, "update-ref", "refs/heads/topic", other_head)
        env["PR_HEAD"] = other_head

    result = subprocess.run(
        ["bash", "-c", policy, "--", "keepalive", "5232", "topic", "unused"],
        cwd=local,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == (78 if race == "already-published" else 1)
    assert result.stdout == ""
    assert calls.read_text().splitlines() == expected_attempts
    expected_head = candidate if race == "already-published" else other_head
    assert git(bare, "rev-parse", "refs/heads/topic") == expected_head


def test_watchdog_refuses_closed_and_missing_branch(publisher):
    worker, final, local, bare, patch, env, calls, _ = publisher
    policy = worker["env"]["PUSH_CODEX_BRANCH"]
    assert policy == final["env"]["PUSH_CODEX_BRANCH"]
    assert worker["run"].count("watchdog_publish || push_status=$?") == 2
    patch.write_text("new work\n")
    git(local, "commit", "-qam", "watchdog checkpoint")
    git(bare, "update-ref", "-d", "refs/heads/topic")
    command = ["bash", "-c", policy, "--", "keepalive", "5232", "topic", "unused"]
    closed = subprocess.run(command, cwd=local, env={**env, "STATE": "closed"}, capture_output=True)
    assert closed.returncode == 78
    assert calls.read_text().splitlines() == ["read"]
    missing = subprocess.run(command, cwd=local, env=env, capture_output=True)
    assert missing.returncode != 0
    assert calls.read_text().splitlines() == ["read", "read", "push"]
    assert (
        subprocess.run(
            [GIT, "show-ref", "--verify", "refs/heads/topic"], cwd=bare, capture_output=True
        ).returncode
        != 0
    )


def test_watchdog_retry_rereads_pr_and_reports_no_saved_work(publisher):
    worker, _, local, bare, patch, env, calls, outputs = publisher
    patch.write_text("watchdog checkpoint")
    git(local, "commit", "-qam", "checkpoint")
    # Delete the branch before the first Git attempt, then close the PR before retry.
    git(bare, "update-ref", "-d", "refs/heads/topic")
    run = worker["run"]
    start = run.index("GRACE_MIN=5")
    end = run.index("# Run codex exec", start)
    script = run[start:end].replace("${{ steps.run_base.outputs.push_token }}", "test-app")
    script = script.replace("${{ github.repository }}", REPO)
    script = script.replace('"/tmp/.watchdog-fired-$$"', '"$GITHUB_OUTPUT.watchdog-fired"')
    env.update(
        PR_NUM="5232",
        TARGET_BRANCH="refs/heads/topic",
        STATE="close-on-retry",
        MAX_RUNTIME_MIN="7",
        PUSH_CODEX_BRANCH=worker["env"]["PUSH_CODEX_BRANCH"],
    )
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script + '\nwait "$WATCHDOG_PID"'],
        cwd=local,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert calls.read_text().splitlines() == ["read", "push", "read"]
    assert outputs.read_text() == "watchdog-saved=false\n"


@pytest.mark.parametrize("old_script_pin", [False, True], ids=["present", "legacy-pin"])
def test_publisher_captures_trusted_wrapper_from_git(tmp_path, old_script_pin):
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["codex"]["steps"]
    prepare = next(step for step in steps if step.get("id") == "branch_publisher")
    assert prepare["env"]["WORKFLOW_JOB_CONTEXT"] == "${{ toJSON(job) }}"
    library = tmp_path / ".workflows-lib"
    origin = tmp_path / "origin" if old_script_pin else library
    module = origin / "scripts/api_client.py"
    module.parent.mkdir(parents=True)
    canonical = (ROOT / "scripts/api_client.py").read_bytes()
    git(origin, "init", "-q", "-b", "legacy")
    git(origin, "config", "user.name", "Test")
    git(origin, "config", "user.email", "test@example.invalid")
    module.write_text("import requests  # older local script pin")
    git(origin, "add", "scripts/api_client.py")
    git(origin, "commit", "-qm", "legacy")
    old_sha = git(origin, "rev-parse", "HEAD")
    git(origin, "switch", "-qc", "publisher")
    module.write_bytes(canonical)
    git(origin, "commit", "-qam", "publisher source")
    source_sha = git(origin, "rev-parse", "HEAD")
    if old_script_pin:
        git(tmp_path, "clone", "-q", "--depth=1", "-b", "legacy", origin.as_uri(), str(library))
        assert (
            subprocess.run(
                [GIT, "cat-file", "-e", source_sha], cwd=library, capture_output=True
            ).returncode
            != 0
        )
    local_sha = git(library, "rev-parse", "HEAD")
    assert local_sha == (old_sha if old_script_pin else source_sha)
    (library / "scripts/api_client.py").write_text("mutated after checkout")
    output = tmp_path / "publisher"
    subprocess.run(
        ["bash", "-e", "-c", prepare["run"]],
        cwd=tmp_path,
        env={
            **os.environ,
            "MODE": "keepalive",
            "PR_NUM": "5232",
            "GITHUB_OUTPUT": str(output),
            "WORKFLOW_JOB_CONTEXT": json.dumps(
                {"workflow_repository": REPO, "workflow_sha": source_sha}
            ),
        },
        check=True,
    )
    assert (
        base64.b64decode(output.read_text().splitlines()[0].removeprefix("api_client="))
        == canonical
    )
    assert git(library, "rev-parse", "HEAD") == local_sha
    assert (library / "scripts/api_client.py").read_text() == "mutated after checkout"
    assert not (library / ".git/FETCH_HEAD").exists()


@pytest.mark.parametrize("broken_policy", ["", "exit 0"])
def test_final_publisher_definition_or_result_missing_fails_closed(publisher, broken_policy):
    _, _, _, _, patch, env, _, _ = publisher
    env["PUSH_CODEX_BRANCH"] = broken_policy
    patch.write_text("worker change")
    result, calls, outputs = run_final(publisher)
    assert result.returncode == 1
    assert not calls
    assert outputs["changes-made"] == "false"
    assert outputs["commit-sha"] == ""
