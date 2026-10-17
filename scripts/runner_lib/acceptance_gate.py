"""Extract and execute the named gates in acceptance checkboxes, without a shell."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

COMMAND_PREFIX = re.compile(r"^(?:pytest|python -m pytest|npm test|npm run|ruff|mypy|make)(?:\s|$)")
TIMEOUT_SECONDS = 300
OUTPUT_BYTES = 2048
TOTAL_OUTPUT_BYTES = 8192


@dataclasses.dataclass(frozen=True)
class Command:
    criterion: int
    command: str


@dataclasses.dataclass(frozen=True)
class Result:
    criterion: int
    command: str
    exit_code: int
    output: str


def extract_commands(markdown: str) -> list[Command]:
    """Read inline backticks and fenced command lines belonging to AC checkboxes."""
    commands = []
    in_acceptance = False
    heading_level = 0
    criterion = -1
    active_checkbox = False
    fence = None
    for line in markdown.splitlines():
        if fence:
            # Markdown closes a fence only with the same marker, at least the
            # opening length, and no trailing info string. Interior markers
            # remain code rather than changing which criteria are visible.
            if re.fullmatch(rf"\s*{re.escape(fence[0])}{{{len(fence)},}}\s*", line):
                fence = None
                continue
        else:
            fence_match = re.match(r"^\s*(`{3,}|~{3,})", line)
            if fence_match:
                fence = fence_match[1]
                continue
        if not fence:
            heading = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
            if heading:
                if heading[2].strip().lower() == "acceptance criteria":
                    in_acceptance = True
                    heading_level = len(heading[1])
                    criterion = -1
                    active_checkbox = False
                elif in_acceptance and len(heading[1]) <= heading_level:
                    in_acceptance = False
                continue
        if not in_acceptance:
            continue
        checkbox = re.match(r"^\s*(?:[-*+]|\d+[.)])\s+\[[ xX]\]\s+(.*)", line)
        if checkbox and not fence:
            criterion += 1
            active_checkbox = True
            line = checkbox[1]
        elif not fence and line.strip() and not line[0].isspace():
            # A separate paragraph is not part of the previous checkbox.
            active_checkbox = False
            continue
        if not active_checkbox:
            continue
        candidates = [line.strip()] if fence else re.findall(r"(?<!`)`([^`\n]+)`(?!`)", line)
        for candidate in candidates:
            if COMMAND_PREFIX.match(candidate):
                command = Command(criterion, candidate)
                if command not in commands:
                    commands.append(command)
    return commands


def run(commands: list[Command], cwd: str | Path) -> list[Result]:
    """Run each gate with a bounded lifetime, retaining its last 40 output lines."""
    results = []
    # Gate commands execute PR code. Do not inherit workflow credentials or command files.
    allowed = {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "CI", "PYTHONPATH", "VIRTUAL_ENV"}
    env = {key: value for key, value in os.environ.items() if key in allowed}
    remaining_bytes = TOTAL_OUTPUT_BYTES
    for command in commands:
        with tempfile.TemporaryFile() as output:
            try:
                process = subprocess.Popen(
                    shlex.split(command.command),
                    cwd=cwd,
                    env=env,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                try:
                    exit_code = process.wait(timeout=TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    exit_code = 124
                    output.write(b"\nGate timed out.\n")
            except (OSError, ValueError) as error:
                exit_code = 127
                output.write(str(error).encode())
            # Seek from the end: even a single huge line cannot allocate an
            # unbounded buffer. Bound aggregate output for persisted state too.
            size = output.seek(0, os.SEEK_END)
            limit = min(OUTPUT_BYTES, remaining_bytes)
            output.seek(max(0, size - limit))
            tail = b"\n".join(output.read(limit).split(b"\n")[-41:]).decode(errors="ignore")
            tail = "".join(tail.splitlines(keepends=True)[-40:])
            remaining_bytes -= len(tail.encode())
        results.append(Result(command.criterion, command.command, exit_code, tail))
    return results


def prepare(commands: list[Command], cwd: Path) -> list[Result]:
    """Provision the same conventional requirements files as the agent runners."""
    setup = []
    if any(
        command.command.startswith(("pytest", "python -m pytest", "ruff", "mypy"))
        for command in commands
    ):
        setup.append(f"{shlex.quote(sys.executable)} -m pip install pytest ruff mypy")
        for name in (
            "requirements.txt",
            "requirements-dev.txt",
            "tools/requirements.txt",
            "scripts/requirements.txt",
        ):
            if (cwd / name).is_file():
                setup.append(f"{shlex.quote(sys.executable)} -m pip install -r {name}")
    if any(command.command.startswith("npm ") for command in commands):
        setup.append("npm ci" if (cwd / "package-lock.json").is_file() else "npm install")
    for step in setup:
        result = run([Command(-1, step)], cwd)[0]
        if result.exit_code != 0:
            failures = []
            remaining_bytes = TOTAL_OUTPUT_BYTES
            for command in commands:
                details = f"Gate environment setup failed: {step}\n{result.output}"
                tail = details.encode()[: min(OUTPUT_BYTES, remaining_bytes)].decode(
                    errors="ignore"
                )
                remaining_bytes -= len(tail.encode())
                failures.append(Result(command.criterion, command.command, result.exit_code, tail))
            return failures
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--cwd", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--appendix", type=Path)
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    if args.extract:
        print(
            json.dumps(
                [dataclasses.asdict(command) for command in extract_commands(sys.stdin.read())]
            )
        )
        return
    plan = json.loads(args.plan.read_text())
    commands = extract_commands(plan["markdown"])
    results = prepare(commands, args.cwd) if args.prepare else []
    if not results:
        results = run(commands, args.cwd)
    plan["results"] = [dataclasses.asdict(result) for result in results]
    args.output.write_text(json.dumps(plan))
    failures = [result for result in results if result.exit_code != 0]
    if failures and args.appendix:
        original = args.appendix.read_text()
        details = "\n\n".join(
            f"{result.command} (exit {result.exit_code})\n{result.output}" for result in failures
        )
        args.appendix.write_text(f"Deterministic acceptance gates failed:\n{details}\n\n{original}")


if __name__ == "__main__":
    main()
