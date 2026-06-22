#!/usr/bin/env python3
"""Opt-in execution check for deliberate-break acceptance criteria."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

VERDICT_PASS = "PASS"
VERDICT_HOLLOW = "FAIL_HOLLOW"
VERDICT_BROKEN = "FAIL_BROKEN"
VERDICT_SKIPPED = "SKIPPED"

MARKER_RE = re.compile(
    r"(?:<!--\s*)?deliberate-break:\s*(?P<body>.*?)(?:\s*-->)?$",
    re.IGNORECASE,
)
SECTION_HEADER_RE = re.compile(r"^#{2,6}\s+(.+?)\s*$", re.MULTILINE)
ASSERTION_DIFF_RE = re.compile(
    r"\b(assert|expect\(|pytest\.raises\(|assert\.)\b",
)
DEFAULT_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class DeliberateBreakSpec:
    test_id: str
    test_file: str
    break_file: str
    command: tuple[str, ...]


def _json_result(verdict: str, **fields: object) -> dict[str, object]:
    return {"verdict": verdict, **fields}


def _write_github_output(**fields: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        for key, value in fields.items():
            handle.write(f"{key}={value}\n")


def _acceptance_criteria(markdown: str) -> str:
    headers = list(SECTION_HEADER_RE.finditer(markdown))
    for index, match in enumerate(headers):
        if match.group(1).strip().lower() != "acceptance criteria":
            continue
        start = match.end()
        end = headers[index + 1].start() if index + 1 < len(headers) else len(markdown)
        return markdown[start:end].strip()
    return markdown


def _parse_key_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for token in shlex.split(text):
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        values[key.strip().replace("_", "-").lower()] = value.strip()
    return values


def _explicit_marker(section: str) -> DeliberateBreakSpec | None:
    for line in section.splitlines():
        match = MARKER_RE.search(line.strip())
        if not match:
            continue
        values = _parse_key_values(match.group("body"))
        test_id = values.get("test") or values.get("test-id")
        test_file = values.get("test-file") or values.get("file")
        break_file = values.get("break-file") or values.get("revert-file")
        command_text = values.get("command")
        if not test_id or not test_file or not break_file:
            raise ValueError("deliberate-break marker requires test, test-file, and break-file")
        command = tuple(shlex.split(command_text)) if command_text else _pytest_command(test_id)
        return DeliberateBreakSpec(test_id, test_file, break_file, command)
    return None


def _fallback_marker(section: str) -> DeliberateBreakSpec | None:
    named_line = next(
        (line for line in section.splitlines() if "named test:" in line.lower()),
        "",
    )
    break_line = next(
        (
            line
            for line in section.splitlines()
            if "deliberate-break" in line.lower() or "deliberate break" in line.lower()
        ),
        "",
    )
    if not named_line or not break_line:
        return None

    test_file_match = re.search(r"`([^`]*(?:test|tests)[^`]*\.py)`", named_line)
    test_name_match = re.search(r"\bwith\s+`?([A-Za-z_][A-Za-z0-9_]*)`?", named_line)
    break_file_match = re.search(r"`([^`]+)`", break_line)
    if not test_file_match or not test_name_match or not break_file_match:
        return None

    test_file = test_file_match.group(1)
    test_id = f"{test_file}::{test_name_match.group(1)}"
    break_file = break_file_match.group(1)
    return DeliberateBreakSpec(test_id, test_file, break_file, _pytest_command(test_id))


def parse_deliberate_break_spec(markdown: str) -> DeliberateBreakSpec | None:
    section = _acceptance_criteria(markdown)
    return _explicit_marker(section) or _fallback_marker(section)


def _pytest_command(test_id: str) -> tuple[str, ...]:
    return (sys.executable, "-m", "pytest", test_id, "-q")


def _run(
    command: tuple[str, ...],
    cwd: Path,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    pythonpath = str(cwd)
    if env.get("PYTHONPATH"):
        pythonpath = pythonpath + os.pathsep + env["PYTHONPATH"]
    env["PYTHONPATH"] = pythonpath
    return subprocess.run(
        list(command),
        cwd=cwd,
        text=True,
        capture_output=True,
        env=env,
        timeout=timeout,
    )


def _git(
    args: list[str],
    cwd: Path,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def _assertion_diff_lines(diff_text: str) -> Iterator[str]:
    """Yield removed assertion lines; adding a new assertion is valid test growth."""
    for line in diff_text.splitlines():
        if not line.startswith("-") or line.startswith("---"):
            continue
        if ASSERTION_DIFF_RE.search(line):
            yield line[:240]


def _changed_assertions(base: str, head: str, test_file: str, cwd: Path) -> list[str]:
    status = _git(["diff", "--name-status", f"{base}...{head}", "--", test_file], cwd)
    if any(line.split("\t", 1)[0] == "A" for line in status.stdout.splitlines()):
        return []
    completed = _git(
        ["diff", "--no-ext-diff", "--unified=0", f"{base}...{head}", "--", test_file],
        cwd,
    )
    return list(_assertion_diff_lines(completed.stdout))


def _archive_ref(base: str, target: Path, cwd: Path) -> None:
    archive = subprocess.run(
        ["git", "archive", "--format=tar", base],
        cwd=cwd,
        check=True,
        capture_output=True,
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    target_root = target.resolve()
    with tarfile.open(fileobj=BytesIO(archive.stdout), mode="r:") as tar:
        for member in tar:
            member_path = target_root / member.name
            resolved = member_path.resolve()
            if not resolved.is_relative_to(target_root):
                raise ValueError(f"unsafe archive path: {member.name}")
            if member.isdir():
                resolved.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue
            resolved.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                continue
            with source, resolved.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            resolved.chmod(member.mode & 0o777)


def verify_spec(
    spec: DeliberateBreakSpec,
    *,
    base: str,
    head: str = "HEAD",
    cwd: Path | None = None,
    enforce_tamper: bool = True,
) -> dict[str, object]:
    repo = cwd or Path.cwd()
    test_path = repo / spec.test_file
    if not test_path.is_file():
        return _json_result(
            VERDICT_BROKEN,
            reason="test-file-missing",
            test_file=spec.test_file,
        )

    try:
        if enforce_tamper:
            tampered = _changed_assertions(base, head, spec.test_file, repo)
            if tampered:
                return _json_result(
                    VERDICT_BROKEN,
                    reason="test-assertion-tamper",
                    test_file=spec.test_file,
                    changed_assertions=tampered,
                )

        head_run = _run(spec.command, repo)
    except subprocess.TimeoutExpired as exc:
        return _json_result(
            VERDICT_BROKEN,
            reason="command-timeout",
            command=list(exc.cmd) if isinstance(exc.cmd, (tuple, list)) else str(exc.cmd),
            timeout=exc.timeout,
        )

    if head_run.returncode != 0:
        return _json_result(
            VERDICT_BROKEN,
            reason="head-test-failed",
            test_id=spec.test_id,
            command=list(spec.command),
            stdout=head_run.stdout,
            stderr=head_run.stderr,
        )

    try:
        with tempfile.TemporaryDirectory(prefix="deliberate-break-base-") as tmp:
            base_dir = Path(tmp)
            _archive_ref(base, base_dir, repo)
            base_test = base_dir / spec.test_file
            base_test.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(test_path, base_test)
            base_run = _run(spec.command, base_dir)
    except subprocess.TimeoutExpired as exc:
        return _json_result(
            VERDICT_BROKEN,
            reason="command-timeout",
            command=list(exc.cmd) if isinstance(exc.cmd, (tuple, list)) else str(exc.cmd),
            timeout=exc.timeout,
        )
    except ValueError as exc:
        return _json_result(
            VERDICT_BROKEN,
            reason="archive-extract-failed",
            detail=str(exc),
        )

    if base_run.returncode == 0:
        return _json_result(
            VERDICT_HOLLOW,
            reason="test-passed-on-base-with-candidate-test",
            test_id=spec.test_id,
            test_file=spec.test_file,
            break_file=spec.break_file,
            command=list(spec.command),
            stdout=base_run.stdout,
            stderr=base_run.stderr,
        )

    return _json_result(
        VERDICT_PASS,
        reason="head-passed-base-failed",
        test_id=spec.test_id,
        test_file=spec.test_file,
        break_file=spec.break_file,
        command=list(spec.command),
        base_stdout=base_run.stdout,
        base_stderr=base_run.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--pr-body-file")
    parser.add_argument("--pr-body-env", default="PR_BODY")
    parser.add_argument("--no-tamper-check", action="store_true")
    args = parser.parse_args(argv)

    body = ""
    if args.pr_body_file:
        body = Path(args.pr_body_file).read_text(encoding="utf-8")
    else:
        body = os.environ.get(args.pr_body_env, "")

    spec = parse_deliberate_break_spec(body)
    if spec is None:
        _write_github_output(has_marker="false", verdict=VERDICT_SKIPPED)
        print(json.dumps(_json_result(VERDICT_SKIPPED, reason="no deliberate-break marker")))
        print("skipped: no deliberate-break marker")
        return 0

    _write_github_output(has_marker="true")
    result = verify_spec(
        spec,
        base=args.base,
        head=args.head,
        enforce_tamper=not args.no_tamper_check,
    )
    _write_github_output(verdict=str(result["verdict"]))
    print(json.dumps(result, sort_keys=True))
    return 0 if result["verdict"] == VERDICT_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
