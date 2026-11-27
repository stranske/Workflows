#!/usr/bin/env python3
"""Maint 90 regression runner: the machine half of an independent finding verification.

The supervisor (this process) prepares two trees with trusted git before any
code under test runs: the fixed tree, and a reverted tree where the fix's code is
reverted and the named test files are restored from the fixed tree. The
verifier's test command then runs in each tree with per-test JUnit results:

* fixed tree: exit 0, at least one test passed, none failed or errored;
* reverted tree: exit 1 (tests ran and failed), no collection or setup errors,
  and at least one test that passed on the fixed tree failed here.

A missing test, a timeout (124), a start failure (127), a collection error or a
failure of some other test is not a negative control. That pair is the
`failed-before-fix` evidence Maint 71 requires.

Runs in a job with no secrets; the command must match the allowlist and is
executed without a shell. With --run-as BASE, each tree is installed and tested
by its own unprivileged user (BASE-fixed, BASE-reverted) from a copy in that
user's home; the user's processes are killed before its report is read. Git and
the evidence file stay with the supervisor, so test code cannot fake the revert,
reach the other run, or write the evidence.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from defusedxml import ElementTree as DefusedET
from defusedxml.common import DefusedXmlException

COMMAND_RE = re.compile(
    r"^(?:python -m pytest|pytest|node --test|npm test --)(?: [A-Za-z0-9_./:=,@+\-\[\]]+)+$"
)
TIMEOUT_SECONDS = 600
TAIL = 4000
TEST_FAILED_EXIT = 1
TEST_SUFFIXES = (".py", ".js", ".mjs", ".cjs", ".ts")
MAX_RESULTS_BYTES = 5_000_000
RUN_AS: str | None = None
INSTALL = True


def user_for(tree: str) -> str | None:
    return f"{RUN_AS}-{tree}" if RUN_AS else None


def now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _exec(argv: list[str], cwd: Path, env: dict, timeout: int) -> dict:
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


def supervise(argv: list[str], cwd: Path, timeout: int = TIMEOUT_SECONDS) -> dict:
    """Trusted tools (git, cp) as the supervisor, never from a test-writable PATH."""
    env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "/tmp")}
    env.update({"LANG": "C.UTF-8", "GIT_TERMINAL_PROMPT": "0"})
    return _exec(argv, cwd, env, timeout)


def sandbox_home(tree: str) -> str:
    user = user_for(tree)
    return f"/home/{user}" if user else os.environ.get("HOME", "/tmp")


def sandboxed(argv: list[str], cwd: Path, tree: str, timeout: int = TIMEOUT_SECONDS) -> dict:
    """Code under test: as that tree's own unprivileged user, with its own venv."""
    user = user_for(tree)
    path = os.environ.get("PATH", "")
    if user:
        path = f"{sandbox_home(tree)}/venv/bin:{path}"
    env = {
        "PATH": path,
        "HOME": sandbox_home(tree),
        "LANG": "C.UTF-8",
        "CI": "true",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if user:
        argv = (
            ["sudo", "-n", "-u", user, "--", "env", "-i"]
            + [f"{key}={value}" for key, value in env.items()]
            + argv
        )
    return _exec(argv, cwd, env, timeout)


def install_dependencies(command: str, repo: Path, tree: str) -> list[dict]:
    """Best effort; a failed install shows up as a failing with-fix run."""
    steps: list[list[str]] = []
    if not INSTALL:
        return []
    if command.startswith(("python", "pytest")):
        python = sys.executable
        if user_for(tree):
            steps.append([sys.executable, "-m", "venv", f"{sandbox_home(tree)}/venv"])
            python = f"{sandbox_home(tree)}/venv/bin/python"
        steps.append([python, "-m", "pip", "install", "--quiet", "pytest"])
        for name in ("requirements-dev.txt", "requirements.txt"):
            if (repo / name).is_file():
                steps.append([python, "-m", "pip", "install", "--quiet", "-r", name])
                break
        if (repo / "pyproject.toml").is_file():
            steps.append([python, "-m", "pip", "install", "--quiet", "-e", "."])
    elif (repo / "package-lock.json").is_file():
        steps.append(["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"])
    return [{"argv": step, **sandboxed(step, repo, tree, timeout=900)} for step in steps]


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


def with_results(argv: list[str], results: Path) -> list[str] | None:
    """The command with a per-test JUnit report; None when the runner has none."""
    if argv[:3] == ["python", "-m", "pytest"] or argv[:1] == ["pytest"]:
        return [*argv, f"--junitxml={results}"]
    if argv[:2] == ["node", "--test"]:
        return [
            "node",
            "--test",
            "--test-reporter=junit",
            f"--test-reporter-destination={results}",
            *argv[2:],
        ]
    return None


def read_results(path: Path) -> dict | None:
    """Per-test outcomes from a JUnit report, or None when there is no usable report."""
    try:
        if not path.is_file() or path.stat().st_size > MAX_RESULTS_BYTES:
            return None
        root = DefusedET.parse(path).getroot()
    except (OSError, DefusedET.ParseError, DefusedXmlException):
        return None
    outcome: dict[str, list[str]] = {"passed": [], "failed": [], "errors": [], "skipped": []}
    for case in root.iter("testcase"):
        ident = "::".join(
            part
            for part in (case.get("file", ""), case.get("classname", ""), case.get("name", ""))
            if part
        )
        if case.find("error") is not None:
            outcome["errors"].append(ident)
        elif case.find("failure") is not None:
            outcome["failed"].append(ident)
        elif case.find("skipped") is not None:
            outcome["skipped"].append(ident)
        else:
            outcome["passed"].append(ident)
    return outcome


def counts(results: dict | None) -> dict | None:
    return None if results is None else {key: len(value) for key, value in results.items()}


def prepare_reverted(tree: Path, sha: str, paths: list[str]) -> dict:
    """Revert the fix and restore the named test files, with trusted git."""
    parents = supervise(["git", "rev-list", "--parents", "-n", "1", sha], tree)
    if parents["exit_code"] != 0:
        return {"prepared": False, "test_present": False, "tail": parents["tail"]}
    argv = ["git", "revert", "--no-edit", "--no-commit"]
    if len(parents["tail"].split()) > 2:
        argv += ["-m", "1"]
    reverted = supervise([*argv, sha], tree)
    if reverted["exit_code"] != 0:
        return {"prepared": False, "test_present": False, "tail": reverted["tail"]}
    restored = supervise(["git", "checkout", "HEAD", "--", *paths], tree)
    present = restored["exit_code"] == 0 and all((tree / path).is_file() for path in paths)
    return {"prepared": True, "test_present": present, "tail": restored["tail"]}


def place(tree: Path, name: str) -> Path:
    """Hand a supervisor-prepared tree to that tree's own user (a copy in its home)."""
    user = user_for(name)
    if not user:
        return tree
    dest = Path(sandbox_home(name)) / "tree"
    supervise(["sudo", "-n", "rm", "-rf", str(dest)], tree.parent)
    copied = supervise(["sudo", "-n", "cp", "-a", str(tree), str(dest)], tree.parent)
    owned = supervise(["sudo", "-n", "chown", "-R", f"{user}:{user}", str(dest)], tree.parent)
    if copied["exit_code"] != 0 or owned["exit_code"] != 0:
        raise RuntimeError(f"cannot place {name} tree: {copied['tail']}{owned['tail']}")
    return dest


def stop_user(name: str, cwd: Path) -> None:
    """Kill every process the tree's user left behind, before its report is read."""
    user = user_for(name)
    if user:
        supervise(["sudo", "-n", "pkill", "-KILL", "-u", user], cwd)


def run_tree(command: str, argv: list[str], tree: Path, name: str, scratch: Path) -> dict:
    results = (Path(sandbox_home(name)) if user_for(name) else scratch) / f"results-{name}.xml"
    install = install_dependencies(command, tree, name)
    run = sandboxed(with_results(argv, results) or argv, tree, name)
    stop_user(name, scratch)
    parsed = read_results(results)
    return {**run, "tests": counts(parsed), "_results": parsed, "install": install}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assessment", required=True)
    parser.add_argument("--item", required=True, help="matrix item JSON file")
    parser.add_argument("--receiver", required=True)
    parser.add_argument("--workflows", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--run-as", default=None, help="user prefix; BASE-fixed and BASE-reverted run the tests"
    )
    parser.add_argument(
        "--no-install", action="store_true", help="use the current environment (tests only)"
    )
    args = parser.parse_args()
    global RUN_AS, INSTALL
    RUN_AS = args.run_as
    INSTALL = not args.no_install

    out = Path(args.output)
    try:
        assessment_doc = json.loads(Path(args.assessment).read_text())
    except (OSError, json.JSONDecodeError):
        assessment_doc = {}
    item = json.loads(Path(args.item).read_text())

    def write(payload: dict) -> int:
        payload.setdefault("finished_at", now())
        out.write_text(json.dumps(payload, indent=2))
        print(json.dumps(payload, indent=2)[:6000])
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
    else:
        fix_sha = fix["sha"]
    if not fix_sha or not re.fullmatch(r"[0-9a-f]{40}", fix_sha):
        return write({"reason": "fix_commit_unknown"})

    argv = command.split(" ")
    if with_results(argv, Path("results.xml")) is None:
        return write({"command": command, "reason": "test_results_unavailable_for_runner"})
    paths = test_paths(argv)
    if not paths:
        return write({"command": command, "reason": "no_test_path_named"})
    if not all((repo / path).is_file() for path in paths):
        return write(
            {"command": command, "test_paths": paths, "reason": "test_path_missing_with_fix"}
        )

    scratch = Path(tempfile.mkdtemp(prefix="maint90-"))
    fixed_src = scratch / "fixed"
    reverted_src = scratch / "reverted"
    shutil.copytree(repo, fixed_src, symlinks=True)
    shutil.copytree(repo, reverted_src, symlinks=True)
    prepared = prepare_reverted(reverted_src, fix_sha, paths)

    with_fix = run_tree(command, argv, place(fixed_src, "fixed"), "fixed", scratch)
    if prepared["prepared"] and prepared["test_present"]:
        without_fix = run_tree(command, argv, place(reverted_src, "reverted"), "reverted", scratch)
    else:
        without_fix = {"exit_code": None, "tests": None, "_results": None, "install": []}
    without_fix.update(
        prepared=prepared["prepared"],
        test_present=prepared["test_present"],
    )
    if not prepared["prepared"]:
        without_fix["tail"] = prepared["tail"]

    fixed_results = with_fix.pop("_results")
    reverted_results = without_fix.pop("_results")
    negative = sorted(
        set((reverted_results or {}).get("failed", []))
        & set((fixed_results or {}).get("passed", []))
    )
    wt, nt = with_fix["tests"], without_fix["tests"]
    reason = ""
    if with_fix["exit_code"] != 0:
        reason = "regression_failed_with_fix"
    elif wt is None:
        reason = "test_results_missing_with_fix"
    elif wt["passed"] == 0 or wt["failed"] or wt["errors"]:
        reason = "with_fix_tests_not_clean"
    elif not without_fix["prepared"]:
        reason = "fix_revert_conflicted"
    elif not without_fix["test_present"]:
        reason = "negative_control_test_missing"
    elif without_fix["exit_code"] == 0:
        reason = "negative_control_passed_without_fix"
    elif without_fix["exit_code"] != TEST_FAILED_EXIT:
        reason = f"negative_control_not_a_test_failure:{without_fix['exit_code']}"
    elif nt is None:
        reason = "test_results_missing_without_fix"
    elif nt["errors"]:
        reason = "negative_control_collection_or_setup_error"
    elif not negative:
        reason = "negative_control_no_matching_test_failed"
    install = {"fixed": with_fix.pop("install"), "reverted": without_fix.pop("install")}
    return write(
        {
            "command": command,
            "fix_sha": fix_sha,
            "test_paths": paths,
            "with_fix": with_fix,
            "without_fix": without_fix,
            "negative_failed_tests": negative[:50],
            "reason": reason,
            "install": install,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
