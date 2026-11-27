#!/usr/bin/env python3
"""Maint 90 regression runner: the machine half of an independent finding verification.

Runs the verifier's test command on the fixed tree (must exit 0) and again with
the fix reverted (must exit non-zero). That pair is the `failed-before-fix`
negative control Maint 71 requires. Runs in a job with no secrets; the command
must match the allowlist and is executed without a shell.
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


def now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(argv: list[str], cwd: Path, timeout: int = TIMEOUT_SECONDS) -> dict:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": "C.UTF-8",
        "CI": "true",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
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
        steps.append([sys.executable, "-m", "pip", "install", "--quiet", "pytest"])
        for name in ("requirements-dev.txt", "requirements.txt"):
            if (repo / name).is_file():
                steps.append([sys.executable, "-m", "pip", "install", "--quiet", "-r", name])
                break
        if (repo / "pyproject.toml").is_file():
            steps.append([sys.executable, "-m", "pip", "install", "--quiet", "-e", "."])
    elif (repo / "package-lock.json").is_file():
        steps.append(["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"])
    return [{"argv": step, **run(step, repo, timeout=900)} for step in steps]


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
    args = parser.parse_args()

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
    install = install_dependencies(command, repo)
    with_fix = run(argv, repo)
    reverted = revert(fix_repo, fix_sha)
    if reverted["prepared"]:
        without_fix = {**run(argv, repo), "prepared": True}
    else:
        without_fix = {"exit_code": None, "prepared": False, "tail": reverted["tail"]}
    reason = ""
    if with_fix["exit_code"] != 0:
        reason = "regression_failed_with_fix"
    elif not without_fix["prepared"]:
        reason = "fix_revert_conflicted"
    elif without_fix["exit_code"] == 0:
        reason = "negative_control_passed_without_fix"
    return write(
        {
            "command": command,
            "fix_sha": fix_sha,
            "with_fix": with_fix,
            "without_fix": without_fix,
            "reason": reason,
            "install": install,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
