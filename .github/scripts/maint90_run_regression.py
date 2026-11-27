#!/usr/bin/env python3
"""Maint 90 regression runner: the machine half of an independent finding verification.

Runs the verifier's test command on the fixed tree (must exit 0) and again with
the fix's product code reverted (must exit 1, the "tests failed" code of pytest,
node --test and npm test). The named test files are restored from the fixed tree
after the revert, so a fix that adds its own regression test still runs that
test against the unfixed code; a missing test, a timeout (124), a start failure
(127) or a collection/usage error is not a negative control. That pair is the
`failed-before-fix` evidence Maint 71 requires.

Runs in a job with no secrets; the command must match the allowlist and is
executed without a shell. With --run-as, every command that touches the code
under test runs as that unprivileged user, which cannot write the evidence file
this supervisor writes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

COMMAND_RE = re.compile(
    r"^(?:python -m pytest|pytest|node --test|npm test --)(?: [A-Za-z0-9_./:=,@+\-\[\]]+)+$"
)
TIMEOUT_SECONDS = 600
TAIL = 4000
TEST_FAILED_EXIT = 1
TEST_SUFFIXES = (".py", ".js", ".mjs", ".cjs", ".ts")
RUN_AS: str | None = None


def now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sandbox_home() -> str:
    return f"/home/{RUN_AS}" if RUN_AS else os.environ.get("HOME", "/tmp")


def sandbox_path() -> str:
    path = os.environ.get("PATH", "")
    return f"{sandbox_home()}/venv/bin:{path}" if RUN_AS else path


def run(argv: list[str], cwd: Path, timeout: int = TIMEOUT_SECONDS) -> dict:
    env = {
        "PATH": sandbox_path(),
        "HOME": sandbox_home(),
        "LANG": "C.UTF-8",
        "CI": "true",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if RUN_AS:
        # The supervisor keeps the evidence; the code under test cannot reach it.
        argv = (
            ["sudo", "-n", "-u", RUN_AS, "--", "env", "-i"]
            + [f"{key}={value}" for key, value in env.items()]
            + argv
        )
    try:
        proc = subprocess.run(
            argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, check=False
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        return {"exit_code": proc.returncode, "tail": output[-TAIL:]}
    except subprocess.TimeoutExpired:
        return {"exit_code": 124, "tail": f"timed out after {timeout}s"}
    except OSError as error:
        return {"exit_code": 127, "tail": str(error)}


def install_dependencies(command: str, repo: Path) -> list[dict]:
    """Best effort; a failed install shows up as a failing with-fix run."""
    steps: list[list[str]] = []
    if command.startswith(("python", "pytest")):
        python = sys.executable
        if RUN_AS:
            steps.append([sys.executable, "-m", "venv", f"{sandbox_home()}/venv"])
            python = f"{sandbox_home()}/venv/bin/python"
        steps.append([python, "-m", "pip", "install", "--quiet", "pytest"])
        for name in ("requirements-dev.txt", "requirements.txt"):
            if (repo / name).is_file():
                steps.append([python, "-m", "pip", "install", "--quiet", "-r", name])
                break
        if (repo / "pyproject.toml").is_file():
            steps.append([python, "-m", "pip", "install", "--quiet", "-e", "."])
    elif (repo / "package-lock.json").is_file():
        steps.append(["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"])
    return [{"argv": step, **run(step, repo, timeout=900)} for step in steps]


def test_paths(argv: list[str]) -> list[str]:
    """The test files the command names (node ids such as path::test are trimmed)."""
    paths = []
    for arg in argv[1:]:
        if arg.startswith("-"):
            continue
        path = arg.split("::", 1)[0]
        if (
            path.endswith(TEST_SUFFIXES)
            and ".." not in Path(path).parts
            and not path.startswith("/")
        ):
            paths.append(path)
    return paths


def restore_tests(repo: Path, paths: list[str]) -> dict:
    """Put the fixed tree's test files back after reverting the fix."""
    result = run(["git", "checkout", "HEAD", "--", *paths], repo)
    return {"restored": result["exit_code"] == 0, "tail": result["tail"]}


def revert(repo: Path, sha: str) -> dict:
    parents = run(["git", "rev-list", "--parents", "-n", "1", sha], repo)
    if parents["exit_code"] != 0:
        return {"prepared": False, "tail": parents["tail"]}
    argv = ["git", "revert", "--no-edit", "--no-commit"]
    if len(parents["tail"].split()) > 2:
        argv += ["-m", "1"]
    result = run([*argv, sha], repo)
    return {"prepared": result["exit_code"] == 0, "tail": result["tail"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assessment", required=True)
    parser.add_argument("--item", required=True, help="matrix item JSON file")
    parser.add_argument("--receiver", required=True)
    parser.add_argument("--workflows", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-as", default=None, help="unprivileged user for the code under test")
    args = parser.parse_args()
    global RUN_AS
    RUN_AS = args.run_as

    out = Path(args.output)
    try:
        assessment_doc = json.loads(Path(args.assessment).read_text())
    except (OSError, json.JSONDecodeError):
        assessment_doc = {}
    item = json.loads(Path(args.item).read_text())

    def write(payload: dict) -> int:
        payload.setdefault("finished_at", now())
        out.write_text(json.dumps(payload, indent=2))
        print(json.dumps({k: v for k, v in payload.items() if k != "install"}, indent=2)[:6000])
        return 0

    assessment = assessment_doc.get("assessment") if assessment_doc.get("ok") else None
    if not assessment or assessment.get("verdict") != "PASS":
        return write({"reason": "no_pass_assessment"})
    command = assessment["validation"]["command"]
    if not COMMAND_RE.match(command):
        return write({"reason": "command_not_allowed"})
    fix = assessment["fix"]
    if assessment["validation"]["repository"] == "receiver":
        repo = Path(args.receiver)
    else:
        repo = Path(args.workflows)
    if fix["kind"] == "receiver":
        offered = {p["number"]: p["merge_commit_sha"] for p in item.get("receiver_pulls", [])}
        fix_sha = offered.get(fix["pr"])
        fix_repo = Path(args.receiver)
    else:
        fix_sha = fix["sha"]
        fix_repo = Path(args.workflows)
    if not fix_sha or not re.fullmatch(r"[0-9a-f]{40}", fix_sha):
        return write({"reason": "fix_commit_unknown"})

    argv = command.split(" ")
    paths = test_paths(argv)
    if not paths:
        return write({"command": command, "reason": "no_test_path_named"})
    if not all((repo / path).is_file() for path in paths):
        return write(
            {"command": command, "test_paths": paths, "reason": "test_path_missing_with_fix"}
        )
    install = install_dependencies(command, repo)
    with_fix = run(argv, repo)
    reverted = revert(fix_repo, fix_sha)
    if reverted["prepared"]:
        restored = restore_tests(repo, paths)
        present = restored["restored"] and all((repo / path).is_file() for path in paths)
        without_fix = {**run(argv, repo), "prepared": True, "test_present": present}
    else:
        without_fix = {
            "exit_code": None,
            "prepared": False,
            "test_present": False,
            "tail": reverted["tail"],
        }
    reason = ""
    if with_fix["exit_code"] != 0:
        reason = "regression_failed_with_fix"
    elif not without_fix["prepared"]:
        reason = "fix_revert_conflicted"
    elif not without_fix["test_present"]:
        reason = "negative_control_test_missing"
    elif without_fix["exit_code"] == 0:
        reason = "negative_control_passed_without_fix"
    elif without_fix["exit_code"] != TEST_FAILED_EXIT:
        reason = f"negative_control_not_a_test_failure:{without_fix['exit_code']}"
    return write(
        {
            "command": command,
            "fix_sha": fix_sha,
            "test_paths": paths,
            "with_fix": with_fix,
            "without_fix": without_fix,
            "reason": reason,
            "install": install,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
