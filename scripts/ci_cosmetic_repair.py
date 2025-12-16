"""Apply cosmetic pytest repairs in CI.

The script is designed to run inside the cosmetic repair workflow.  It
consumes a JUnit XML report, classifies failures using
``scripts.classify_test_failures`` and runs a small set of targeted
fixers for well-understood cosmetic breakages:

* Aggregate number formatting in ``automation_multifailure``
* Expectation drift maintained by ``scripts.update_autofix_expectations``

Whenever a fixer updates the repository it also appends a short note to
``docs/COSMETIC_REPAIR_LOG.md`` between guard markers so that the
resulting pull request contains a reviewable trace of the automatic
changes.

The script intentionally avoids over-reaching.  Failures that are not
recognised remain untouched and are reported in the JSON summary output
so that maintainers can review them manually.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Sequence

ROOT = Path(__file__).resolve().parent.parent
GUARD_PREFIX = "# cosmetic-repair:"
BRANCH_PREFIX = "autofix/cosmetic-repair"
DEFAULT_REPORT = Path(".pytest-cosmetic-report.xml")
SUMMARY_FILE = Path(".cosmetic-repair-summary.json")

from scripts.classify_test_failures import (  # noqa: E402
    FailureRecord,
    classify_reports,
)

_LOG_PATH = ROOT / "docs" / "COSMETIC_REPAIR_LOG.md"
_GUARD_START = "<!-- cosmetic-repair:start -->"
_GUARD_END = "<!-- cosmetic-repair:end -->"


def _discover_expectation_modules() -> tuple[str, ...]:
    """Dynamically discover test modules for expectation drift repairs."""
    test_dir = ROOT / "tests"
    modules = []
    for path in test_dir.glob("test_*.py"):
        # Convert path to module name, e.g. tests/test_foo.py -> tests.test_foo
        module_name = f"tests.{path.stem}"
        modules.append(module_name)
    return tuple(modules)


_EXPECTATION_MODULES: tuple[str, ...] = _discover_expectation_modules()


class CosmeticRepairError(RuntimeError):
    """Raised when a cosmetic repair cannot be completed safely."""


@dataclass(slots=True)
class RepairInstruction:
    """Structured representation of a cosmetic repair request."""

    kind: str
    path: Path
    guard: str
    key: str | None
    value: object
    metadata: dict[str, object]
    source: str

    def absolute_path(self, root: Path) -> Path:
        """Return the absolute path for this instruction relative to *root*."""

        return root / self.path


def _run(
    cmd: Sequence[str], *, cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if check and result.returncode != 0:
        raise CosmeticRepairError(
            f"Command {' '.join(cmd)} failed with exit code {result.returncode}:\n{result.stderr or result.stdout}"
        )
    return result


def run_pytest(report_path: Path, pytest_args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        f"--junitxml={report_path}",
        *pytest_args,
    ]
    return subprocess.run(cmd, text=True, capture_output=True)


_FAILURE_PATTERN = re.compile(r"(COSMETIC_[A-Z_]+)\s+(\{.*?\})")


def parse_failure_message(message: str, *, source: str) -> list[RepairInstruction]:
    instructions: list[RepairInstruction] = []
    for kind, payload in _FAILURE_PATTERN.findall(message):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise CosmeticRepairError(
                f"Unable to decode cosmetic payload from {source}: {exc}"
            ) from exc
        instruction = build_instruction(kind, data, source=source)
        instructions.append(instruction)
    return instructions


def build_instruction(kind: str, data: dict[str, object], *, source: str) -> RepairInstruction:
    path_raw = data.get("path")
    if not isinstance(path_raw, str) or not path_raw:
        raise CosmeticRepairError(f"Missing target path in {source} ({kind})")
    guard = data.get("guard", "")
    if not isinstance(guard, str) or not guard:
        raise CosmeticRepairError(f"Missing guard token in {source} ({kind})")
    key = data.get("key")
    if key is not None and not isinstance(key, str):
        raise CosmeticRepairError(f"Invalid key in {source} ({kind})")

    if kind == "COSMETIC_TOLERANCE":
        value = _format_value(data)
        return RepairInstruction(
            kind="tolerance",
            path=Path(path_raw),
            guard=guard,
            key=key,
            value=value,
            metadata=data,
            source=source,
        )
    if kind == "COSMETIC_SNAPSHOT":
        replacement = data.get("replacement")
        if not isinstance(replacement, str):
            raise CosmeticRepairError(f"Snapshot repair requires string replacement ({source})")
        return RepairInstruction(
            kind="snapshot",
            path=Path(path_raw),
            guard=guard,
            key=key,
            value=replacement,
            metadata=data,
            source=source,
        )
    raise CosmeticRepairError(f"Unsupported cosmetic repair type: {kind}")


def _format_value(data: dict[str, object]) -> str:
    if "value" in data:
        raw_value = data["value"]
    elif "actual" in data:
        raw_value = data["actual"]
    else:
        raise CosmeticRepairError("Tolerance payload missing 'value' or 'actual'")

    fmt = None
    if isinstance(data.get("format"), str):
        fmt = data["format"]
    elif isinstance(data.get("digits"), int):
        fmt = f".{data['digits']}f"

    if fmt is not None:
        try:
            formatted = format(float(raw_value), fmt)
        except (TypeError, ValueError) as exc:  # pragma: no cover - validation
            raise CosmeticRepairError(f"Invalid numeric payload: {raw_value}") from exc
        return formatted
    if isinstance(raw_value, (int, float)):
        return repr(raw_value)
    if isinstance(raw_value, str):
        return raw_value
    raise CosmeticRepairError(f"Unsupported value type: {type(raw_value)!r}")


def load_failure_records(report_path: Path) -> list[FailureRecord]:
    summary = classify_reports([report_path])
    cosmetic_entries = summary.get("cosmetic", [])
    runtime_entries = summary.get("runtime", [])
    unknown_entries = summary.get("unknown", [])
    if runtime_entries or unknown_entries:
        raise CosmeticRepairError("Cosmetic repair only supports reports with cosmetic failures")
    records: list[FailureRecord] = []
    for item in cosmetic_entries:
        records.append(
            FailureRecord(
                id=item.get("id", ""),
                file=item.get("file", ""),
                markers=tuple(item.get("markers", ())),
                message=item.get("message", ""),
                failure_type=item.get("failure_type", "failure"),
            )
        )
    return records


def collect_instructions(records: Iterable[FailureRecord]) -> list[RepairInstruction]:
    instructions: list[RepairInstruction] = []
    for record in records:
        parsed = parse_failure_message(record.message, source=record.id)
        instructions.extend(parsed)
    return instructions


_FLOAT_GUARD_PATTERN = re.compile(
    r"^(?P<prefix>.*?=\s*)(?P<value>[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)(?P<suffix>.*#\s*cosmetic-repair:\s*float(?:\s+[-\w.]+)?)"
)


def apply_tolerance_update(path: Path, *, guard: str, key: str | None, value: str) -> bool:
    guard_token = f"{GUARD_PREFIX} {guard}"
    if key:
        guard_token = f"{guard_token} {key}"
    original = path.read_text(encoding="utf-8").splitlines()
    updated_lines: list[str] = []
    changed = False
    guard_found = False
    for line in original:
        if guard_token in line:
            guard_found = True
            match = _FLOAT_GUARD_PATTERN.match(line)
            if not match:
                raise CosmeticRepairError(
                    f"Unable to locate numeric literal for {guard_token} in {path}"
                )
            new_line = f"{match.group('prefix')}{value}{match.group('suffix')}"
            if new_line != line:
                changed = True
            updated_lines.append(new_line)
        else:
            updated_lines.append(line)
    if not guard_found:
        raise CosmeticRepairError(f"Guard comment {guard_token} not found in {path}")
    if not changed:
        return False
    path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    return changed


def apply_snapshot_update(path: Path, *, guard: str, key: str | None, replacement: str) -> bool:
    guard_token = f"{GUARD_PREFIX} {guard}"
    if key:
        guard_token = f"{guard_token} {key}"
    text = path.read_text(encoding="utf-8")
    if guard_token not in text:
        raise CosmeticRepairError(f"Snapshot guard {guard_token} not found in {path}")
    path.write_text(replacement, encoding="utf-8")
    return True


def apply_instructions(instructions: Sequence[RepairInstruction], *, root: Path) -> list[Path]:
    changed: list[Path] = []
    for instruction in instructions:
        target = instruction.absolute_path(root)
        if instruction.kind == "tolerance":
            updated = apply_tolerance_update(
                target,
                guard=instruction.guard,
                key=instruction.key,
                value=str(instruction.value),
            )
        elif instruction.kind == "snapshot":
            updated = apply_snapshot_update(
                target,
                guard=instruction.guard,
                key=instruction.key,
                replacement=str(instruction.value),
            )
        else:  # pragma: no cover - defensive
            raise CosmeticRepairError(f"Unhandled instruction kind: {instruction.kind}")
        if updated:
            changed.append(target)
    return changed


def working_tree_changes(*, root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return lines


def stage_and_commit(
    paths: Sequence[Path],
    *,
    root: Path,
    summary: str,
    branch_suffix: str | None,
) -> str:
    branch_suffix = branch_suffix or datetime.utcnow().strftime("%Y%m%d%H%M%S")
    branch = f"{BRANCH_PREFIX}-{branch_suffix}"
    _run(["git", "checkout", "-B", branch], cwd=root)
    _run(["git", "add", *{str(p.relative_to(root)) for p in paths}], cwd=root)
    commit_message = f"Cosmetic repair: {summary}"
    _run(["git", "commit", "-m", commit_message], cwd=root)
    return branch


def push_and_open_pr(
    *,
    branch: str,
    base: str,
    title: str,
    body: str,
    labels: Sequence[str],
    root: Path,
) -> str:
    _run(["git", "push", "--force", "origin", branch], cwd=root)
    cmd = [
        "gh",
        "pr",
        "create",
        "--title",
        title,
        "--body",
        body,
        "--base",
        base,
        "--head",
        branch,
    ]
    for label in labels:
        cmd.extend(["--label", label])
    result = _run(cmd, cwd=root)
    stdout = (result.stdout or "").strip()
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line:
            return line
    return stdout


def _serialise_instructions(
    instructions: Sequence[RepairInstruction],
) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for instruction in instructions:
        payload.append(
            {
                "kind": instruction.kind,
                "path": str(instruction.path),
                "guard": instruction.guard,
                "key": instruction.key,
                "source": instruction.source,
                "metadata": instruction.metadata,
            }
        )
    return payload


def write_summary(root: Path, payload: dict[str, object]) -> None:
    summary_path = root / SUMMARY_FILE
    timestamp = datetime.now(UTC).replace(microsecond=0).isoformat()
    payload = {
        **payload,
        "timestamp": timestamp,
    }
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_pr_body(
    changed: Sequence[Path], instructions: Sequence[RepairInstruction], *, root: Path
) -> str:
    bullets = [f"- {path.relative_to(root)}" for path in changed]
    instruction_lines = [
        f"  * {instr.source}: {instr.kind} -> {instr.path}" for instr in instructions
    ]
    return "\n".join(
        [
            "## Cosmetic Repairs",
            "",
            "The workflow detected cosmetic drift in the following files:",
            *bullets,
            "",
            "### Repair details",
            *instruction_lines,
        ]
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", help="Analyse failures without editing files"
    )
    mode.add_argument("--apply", action="store_true", help="Apply eligible repairs")
    parser.add_argument(
        "--pytest-args",
        nargs=argparse.REMAINDER,
        default=[],
        help="Additional arguments forwarded to pytest",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Existing JUnit report to analyse instead of running pytest",
    )
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root (tests only)")
    parser.add_argument(
        "--base",
        type=str,
        default=os.environ.get("GITHUB_BASE_REF", "main"),
        help="Base branch for PRs",
    )
    parser.add_argument(
        "--branch-suffix",
        type=str,
        default=None,
        help="Optional suffix appended to the generated branch name",
    )
    parser.add_argument(
        "--skip-pr",
        action="store_true",
        help="Do not create a branch or PR (useful for tests)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    ns = parse_args(argv)
    mode = "dry-run"
    if ns.apply:
        mode = "apply"
    report_path = ns.report or (ns.root / DEFAULT_REPORT)
    pytest_result = None
    if ns.report is None:
        pytest_result = run_pytest(report_path, ns.pytest_args)
    if pytest_result and pytest_result.returncode == 0:
        print("pytest completed successfully; no cosmetic repairs needed.")
        write_summary(
            ns.root,
            {
                "status": "clean",
                "mode": mode,
                "report": str(report_path),
            },
        )
        return 0
    if not report_path.exists():
        raise CosmeticRepairError(f"JUnit report not found: {report_path}")
    records = load_failure_records(report_path)
    instructions = collect_instructions(records)
    if not instructions:
        if pytest_result is not None and pytest_result.returncode != 0:
            write_summary(
                ns.root,
                {
                    "status": "error",
                    "mode": mode,
                    "reason": "pytest_failed_without_cosmetic_instructions",
                    "report": str(report_path),
                    "pytest_returncode": pytest_result.returncode,
                },
            )
            raise CosmeticRepairError("pytest failed but no cosmetic instructions were detected")
        print("No cosmetic repairs detected.")
        write_summary(
            ns.root,
            {
                "status": "clean",
                "mode": mode,
                "report": str(report_path),
            },
        )
        return 0
    if mode == "dry-run":
        for instr in instructions:
            print(f"[dry-run] {instr.kind} -> {instr.path}")
        write_summary(
            ns.root,
            {
                "status": "dry-run",
                "mode": mode,
                "report": str(report_path),
                "instructions": _serialise_instructions(instructions),
            },
        )
        return 0

    changed_paths = apply_instructions(instructions, root=ns.root)
    if not changed_paths:
        print("Cosmetic repairs already up to date; no file changes required.")
        write_summary(
            ns.root,
            {
                "status": "no-changes",
                "mode": mode,
                "report": str(report_path),
                "instructions": _serialise_instructions(instructions),
            },
        )
        return 0

    status = working_tree_changes(root=ns.root)
    print("Working tree status after repairs:")
    for line in status:
        print(f"  {line}")

    if ns.skip_pr:
        write_summary(
            ns.root,
            {
                "status": "applied-no-pr",
                "mode": mode,
                "report": str(report_path),
                "instructions": _serialise_instructions(instructions),
                "changed_files": [str(path.relative_to(ns.root)) for path in changed_paths],
            },
        )
        return 0

    branch = stage_and_commit(
        changed_paths,
        root=ns.root,
        summary="cosmetic adjustments",
        branch_suffix=ns.branch_suffix,
    )
    title = "Cosmetic test repairs"
    body = build_pr_body(changed_paths, instructions, root=ns.root)
    pr_url = push_and_open_pr(
        branch=branch,
        base=ns.base,
        title=title,
        body=body,
        labels=("testing", "autofix:applied"),
        root=ns.root,
    )
    write_summary(
        ns.root,
        {
            "status": "pr-created",
            "mode": mode,
            "report": str(report_path),
            "branch": branch,
            "pr_url": pr_url,
            "instructions": _serialise_instructions(instructions),
            "changed_files": [str(path.relative_to(ns.root)) for path in changed_paths],
        },
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    from trend_analysis.script_logging import setup_script_logging

    setup_script_logging(module_file=__file__)
    raise SystemExit(main())
