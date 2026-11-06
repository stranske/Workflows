"""Retain full-repository Black, focused Ruff, and strict template receipts.

The recorded Black command is the repository gate
``black --check --line-length 100 --exclude '(\\.workflows-lib|node_modules)' .``.
``BLACK_NUM_WORKERS=1`` keeps that command on Black's thread pool. Strict template
validation uses the arguments documented by Health 70. Historical shebang-rejection
archives and the acceptance-run receipts are inputs, not outputs of this run.
"""

from __future__ import annotations

import hashlib
import os
import re
import runpy
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

EVIDENCE = Path("docs/evidence/issue-3743/shebang-rejection")
RUN = EVIDENCE / "validation-run"
HELPERS = (
    "scripts/check_deliberate_break.py",
    "templates/consumer-repo/scripts/check_deliberate_break.py",
)
TEMPLATE_SCRIPT = "scripts/validate_template_completeness.py"
BLACK_EXCLUDE = r"(\.workflows-lib|node_modules)"
BLACK_CACHE = "/tmp/shebang-rejection-validation-black-cache"
TEMPLATE_SUMMARY = "/tmp/shebang-rejection-validation/template-summary.md"
BLACK_TIMEOUT = 600
COMMAND_TIMEOUT = 180
FOCUSED_RUFF = (
    "docs/evidence/issue-3743/shebang-rejection/capture_acceptance_run.py",
    "docs/evidence/issue-3743/shebang-rejection/capture_validation_run.py",
    "docs/evidence/issue-3743/shebang-rejection/compare_matched.py",
    "docs/evidence/issue-3743/shebang-rejection/inspect_main_acceptance.py",
    "docs/evidence/issue-3743/shebang-rejection/replay.py",
    "docs/evidence/issue-3743/shebang-rejection/verify_archives.py",
    "scripts/check_deliberate_break.py",
    "templates/consumer-repo/scripts/check_deliberate_break.py",
    "tests/scripts/test_check_deliberate_break_shebang_rejection.py",
    "tests/scripts/test_shebang_rejection_acceptance_inspection.py",
    "tests/scripts/test_shebang_rejection_acceptance_run.py",
    "tests/scripts/test_shebang_rejection_archive_bindings.py",
    "tests/scripts/test_shebang_rejection_matched_comparison.py",
    "tests/scripts/test_shebang_rejection_replay.py",
    "tests/scripts/test_shebang_rejection_validation_run.py",
)
HISTORICAL_PATHS = (
    "docs/evidence/issue-3743/shebang-rejection/README.md",
    "docs/evidence/issue-3743/shebang-rejection/coverage.ini",
    "docs/evidence/issue-3743/shebang-rejection/replay.py",
    "docs/evidence/issue-3743/shebang-rejection/summary.json",
    "docs/evidence/issue-3743/shebang-rejection/proof.tar.gz",
    "docs/evidence/issue-3743/shebang-rejection/path-lookup",
    "docs/evidence/issue-3743/shebang-rejection/replay-validation",
    "docs/evidence/issue-3743/shebang-rejection/pre-change-record.json",
    "docs/evidence/issue-3743/shebang-rejection/main-acceptance-map.json",
    "docs/evidence/issue-3743/shebang-rejection/inspect_main_acceptance.py",
    "docs/evidence/issue-3743/shebang-rejection/capture_acceptance_run.py",
    "docs/evidence/issue-3743/shebang-rejection/acceptance-run",
    *HELPERS,
    "tests/scripts/test_check_deliberate_break_shebang_rejection.py",
    "tests/scripts/test_shebang_rejection_replay.py",
    "tests/scripts/test_shebang_rejection_acceptance_run.py",
    "tests/scripts/test_shebang_rejection_acceptance_inspection.py",
)
TEMPLATE_DOCUMENTATION = (
    "Health 70 (.github/workflows/health-70-validate-sync-manifest.yml) documents "
    "scripts/validate_template_completeness.py --workflows-dir .github/workflows "
    "--template-dir templates/consumer-repo/.github/workflows "
    "--manifest .github/sync-manifest.yml --source sync-manifest --strict. "
    "docs/orchestrator/consumer-sync-contract-map.md also documents "
    "--strict --source sync-manifest. Health 73 documents --strict with the "
    "script defaults for those paths."
)
ROLE = (
    "Current validation receipts for full-repository Black, focused Ruff, strict "
    "template completeness, and git diff --check. Historical README.md, summary.json, "
    "proof.tar.gz, path-lookup/, and replay-validation/ are earlier receipts. "
    "acceptance-run/ retains the eight-case pytest and replay commands."
)
BLACK_UNCHANGED = re.compile(r"(\d+) files? would be left unchanged")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def black_argv(executable: Path) -> list[str]:
    return [
        str(executable),
        "--check",
        "--line-length",
        "100",
        "--exclude",
        BLACK_EXCLUDE,
        ".",
    ]


def ruff_argv(executable: Path) -> list[str]:
    return [str(executable), "check", *FOCUSED_RUFF]


def template_argv(executable: Path) -> list[str]:
    return [
        str(executable),
        TEMPLATE_SCRIPT,
        "--workflows-dir",
        ".github/workflows",
        "--template-dir",
        "templates/consumer-repo/.github/workflows",
        "--manifest",
        ".github/sync-manifest.yml",
        "--source",
        "sync-manifest",
        "--strict",
    ]


def diff_argv() -> list[str]:
    return ["git", "diff", "--check"]


def black_file_count(report: str) -> int | None:
    """Return Black's unchanged-file count from a combined console report.

    Black 26 writes ``N files would be left unchanged`` to stderr.
    """
    match = BLACK_UNCHANGED.search(report)
    if match is None:
        return None
    return int(match.group(1))


def command_report(record: dict) -> str:
    return f"{record['stdout']}\n{record['stderr']}"


def resolved_tool(name: str) -> Path:
    found = shutil.which(name)
    if found is None:
        raise FileNotFoundError(name)
    return Path(found).resolve()


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json_text(payload), encoding="utf-8")


def json_text(payload: dict) -> str:
    import json

    return json.dumps(payload, indent=2) + "\n"


def read_json(path: Path) -> dict:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def run_command(
    argv: list[str],
    cwd: Path,
    timeout: int,
    env_overrides: dict[str, str] | None = None,
) -> dict:
    """Run one command and keep its cwd, exit, environment overrides, and console."""
    started = time.monotonic()
    overrides = dict(env_overrides or {})
    record = {
        "argv": argv,
        "cwd": str(cwd),
        "attempt": 1,
        "limit_seconds": timeout,
        "env_overrides": overrides,
    }
    env = os.environ.copy()
    env.update(overrides)
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        record.update(
            {
                "exit": 127,
                "stdout": "",
                "stderr": f"{argv[0]}: No such file or directory\n",
                "stopped": "interpreter-absent",
                "duration_seconds": round(time.monotonic() - started, 3),
            }
        )
        return record
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", "replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        record.update(
            {
                "exit": 124,
                "stdout": stdout,
                "stderr": stderr,
                "stopped": "time-limit",
                "duration_seconds": round(time.monotonic() - started, 3),
            }
        )
        return record
    record.update(
        {
            "exit": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "stopped": None,
            "duration_seconds": round(time.monotonic() - started, 3),
        }
    )
    return record


def save_command(directory: Path, name: str, record: dict) -> None:
    write_json(directory / f"{name}.json", record)
    (directory / f"{name}.stdout").write_text(record["stdout"], encoding="utf-8")
    (directory / f"{name}.stderr").write_text(record["stderr"], encoding="utf-8")


def tool_version(executable: Path) -> dict:
    record = run_command([str(executable), "--version"], Path.cwd(), 30)
    return {
        "path": str(executable),
        "exit": record["exit"],
        "stdout": record["stdout"],
        "stderr": record["stderr"],
    }


def digest_path(root: Path, relative: str) -> dict:
    path = root / relative
    if path.is_file():
        data = path.read_bytes()
        return {"kind": "file", "sha256": digest(data), "bytes": len(data), "files": 1}
    files = sorted(item for item in path.rglob("*") if item.is_file())
    hasher = hashlib.sha256()
    total = 0
    for item in files:
        data = item.read_bytes()
        hasher.update(item.relative_to(root).as_posix().encode())
        hasher.update(b"\0")
        hasher.update(data)
        hasher.update(b"\0")
        total += len(data)
    return {"kind": "tree", "sha256": hasher.hexdigest(), "bytes": total, "files": len(files)}


def historical_digests(root: Path) -> dict[str, dict]:
    return {relative: digest_path(root, relative) for relative in HISTORICAL_PATHS}


def _ensure_origin_main(root: Path) -> None:
    """Fetch origin/main when a depth-1 checkout has no remote-tracking main."""
    ref = "refs/remotes/origin/main"

    def present() -> bool:
        probe = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", ref],
            cwd=root,
            capture_output=True,
            check=False,
        )
        return probe.returncode == 0

    if present():
        return
    last = subprocess.CompletedProcess(["git", "fetch"], 128, b"", b"")
    for _attempt in range(6):
        last = subprocess.run(
            [
                "git",
                "fetch",
                "--depth=1",
                "origin",
                "+refs/heads/main:refs/remotes/origin/main",
            ],
            cwd=root,
            capture_output=True,
            check=False,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        if present():
            return
        if b"lock" not in last.stderr.lower():
            break
        time.sleep(0.5)
    raise subprocess.CalledProcessError(
        last.returncode, last.args, output=last.stdout, stderr=last.stderr
    )


def production_helpers(root: Path) -> dict:
    root_bytes = (root / HELPERS[0]).read_bytes()
    template_bytes = (root / HELPERS[1]).read_bytes()
    _ensure_origin_main(root)
    base_root = subprocess.check_output(["git", "show", f"origin/main:{HELPERS[0]}"], cwd=root)
    base_template = subprocess.check_output(["git", "show", f"origin/main:{HELPERS[1]}"], cwd=root)
    return {
        "equal_each_other": root_bytes == template_bytes,
        "root_equals_origin_main": root_bytes == base_root,
        "template_equals_origin_main": template_bytes == base_template,
        "sha256": digest(root_bytes),
        "bytes": len(root_bytes),
    }


def template_file_counts(root: Path) -> dict[str, int]:
    module = runpy.run_path(str(root / TEMPLATE_SCRIPT))
    workflows = module["get_workflows"](root / ".github/workflows")
    template = module["get_workflows"](root / "templates/consumer-repo/.github/workflows")
    manifest = module["get_manifest_workflows"](root / ".github/sync-manifest.yml")
    return {
        "workflows_directory_yml": len(workflows),
        "template_directory_yml": len(template),
        "manifest_workflow_targets": len(manifest),
        "strict_validation_inputs": len(workflows) + len(template) + 1,
    }


def render_readme(summary: dict) -> str:
    counts = summary["measured_file_counts"]
    interpreters = summary["interpreters"]
    python_version = interpreters["python"]["version"].splitlines()[0]
    lines = [
        "# Current shebang-rejection validation receipts",
        "",
        summary["role"],
        "",
        f"Check date: {summary['check_date']}",
        f"cwd: `{summary['cwd']}`",
        f"Python: `{interpreters['python']['path']}` ({python_version})",
        f"Black: `{interpreters['black']['path']}`",
        f"Ruff: `{interpreters['ruff']['path']}`",
        "",
        "Measured file counts:",
        f"- Black files left unchanged: {counts['black_files']}",
        f"- Focused Ruff paths: {counts['ruff_files']}",
        f"- Workflow directory YAML files: {counts['workflows_directory_yml']}",
        f"- Template workflow YAML files: {counts['template_directory_yml']}",
        f"- Manifest workflow targets: {counts['manifest_workflow_targets']}",
        f"- Strict validation input files: {counts['strict_validation_inputs']}",
        "",
        "Commands and exits:",
    ]
    for name in ("black", "ruff", "template", "diffcheck"):
        command = summary["commands"][name]
        rendered = " ".join(command["argv"])
        lines.append(f"- `{rendered}` exit {command['exit']}")
    lines.extend(["", summary["template_documentation"], ""])
    return "\n".join(lines)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def command_view(record: dict) -> dict:
    return {
        "argv": record["argv"],
        "cwd": record["cwd"],
        "exit": record["exit"],
        "stopped": record["stopped"],
        "duration_seconds": record["duration_seconds"],
        "env_overrides": record["env_overrides"],
        "stdout": record["stdout"],
        "stderr": record["stderr"],
    }


def validate_retained(root: Path) -> dict:
    """Check the retained validation receipts against the command contract."""
    run_dir = root / RUN
    summary = read_json(run_dir / "summary.json")
    black = read_json(run_dir / "black.json")
    ruff = read_json(run_dir / "ruff.json")
    template = read_json(run_dir / "template.json")
    diffcheck = read_json(run_dir / "diffcheck.json")
    _require(black["argv"] == black_argv(Path(black["argv"][0])), "black argv")
    _require(black["argv"][1:] == black_argv(Path("black"))[1:], "black flags")
    _require(ruff["argv"] == ruff_argv(Path(ruff["argv"][0])), "ruff argv")
    _require(template["argv"] == template_argv(Path(template["argv"][0])), "template argv")
    _require(diffcheck["argv"] == diff_argv(), "diff argv")
    for name, record in (
        ("black", black),
        ("ruff", ruff),
        ("template", template),
        ("diffcheck", diffcheck),
    ):
        _require(record["cwd"] == str(root), f"{name} cwd")
        _require(record["exit"] == 0, f"{name} exit {record['exit']}")
        _require(record["stopped"] is None, f"{name} stopped")
        _require(
            (run_dir / f"{name}.stdout").read_text(encoding="utf-8") == record["stdout"],
            f"{name} stdout",
        )
        _require(
            (run_dir / f"{name}.stderr").read_text(encoding="utf-8") == record["stderr"],
            f"{name} stderr",
        )
        _require(summary["commands"][name] == command_view(record), f"{name} summary")
    file_count = black_file_count(command_report(black))
    _require(file_count is not None and file_count > 0, "black file count")
    counts = template_file_counts(root)
    counts["black_files"] = file_count
    counts["ruff_files"] = len(FOCUSED_RUFF)
    _require(summary["measured_file_counts"] == counts, "measured file counts")
    _require(len(ruff["argv"][2:]) == len(FOCUSED_RUFF), "ruff file count")
    _require(
        "All consumer workflows are properly templated and manifested" in template["stdout"],
        "template success",
    )
    _require(summary["interpreters"]["python"]["path"] == template["argv"][0], "python path")
    _require(summary["interpreters"]["black"]["path"] == black["argv"][0], "black path")
    _require(summary["interpreters"]["ruff"]["path"] == ruff["argv"][0], "ruff path")
    _require(Path(template["argv"][0]).is_file(), "python executable")
    _require(summary["historical_unchanged"] is True, "historical flag")
    _require(historical_digests(root) == summary["historical_sha256"], "historical digests")
    helpers = production_helpers(root)
    _require(helpers == summary["production_helpers"], "production helpers")
    _require(helpers["equal_each_other"] is True, "helpers differ")
    _require(helpers["root_equals_origin_main"] is True, "root helper drifted")
    _require(helpers["template_equals_origin_main"] is True, "template helper drifted")
    _require(summary["role"] == ROLE, "role")
    _require("Historical" in (run_dir / "README.md").read_text(encoding="utf-8"), "readme")
    copied = (run_dir / "template-summary.md").read_text(encoding="utf-8")
    _require(copied.count("Issues Found:") == 1, "template summary copies")
    _require("**Issues Found:** 0" in copied, "template summary issues")
    return summary


def capture(root: Path) -> dict:
    run_dir = root / RUN
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    before = historical_digests(root)
    black_path = resolved_tool("black")
    ruff_path = resolved_tool("ruff")
    black_env = {"BLACK_NUM_WORKERS": "1", "BLACK_CACHE_DIR": BLACK_CACHE}
    Path(BLACK_CACHE).mkdir(parents=True, exist_ok=True)
    summary_path = Path(TEMPLATE_SUMMARY)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.unlink(missing_ok=True)
    black = run_command(black_argv(black_path), root, BLACK_TIMEOUT, black_env)
    ruff = run_command(ruff_argv(ruff_path), root, COMMAND_TIMEOUT)
    template = run_command(
        template_argv(Path(sys.executable)),
        root,
        COMMAND_TIMEOUT,
        {"GITHUB_STEP_SUMMARY": TEMPLATE_SUMMARY},
    )
    save_command(run_dir, "black", black)
    save_command(run_dir, "ruff", ruff)
    save_command(run_dir, "template", template)
    summary_source = Path(TEMPLATE_SUMMARY)
    if summary_source.is_file():
        # The validator ends the step summary with a blank line. Drop that line so
        # the retained copy does not trip git diff --check.
        text = summary_source.read_text(encoding="utf-8").rstrip("\n") + "\n"
        (run_dir / "template-summary.md").write_text(text, encoding="utf-8")
    else:
        (run_dir / "template-summary.md").write_text("", encoding="utf-8")
    first_diff = run_command(diff_argv(), root, COMMAND_TIMEOUT)
    interpreters = {
        "python": {"path": sys.executable, "version": sys.version},
        "black": tool_version(black_path),
        "ruff": tool_version(ruff_path),
    }
    file_count = black_file_count(command_report(black))
    counts = template_file_counts(root)
    counts["black_files"] = file_count
    counts["ruff_files"] = len(FOCUSED_RUFF)
    after_commands = historical_digests(root)
    helpers = production_helpers(root)
    summary = {
        "role": ROLE,
        "check_date": datetime.now(UTC).date().isoformat(),
        "cwd": str(root),
        "interpreters": interpreters,
        "measured_file_counts": counts,
        "commands": {
            "black": command_view(black),
            "ruff": command_view(ruff),
            "template": command_view(template),
            "diffcheck": command_view(first_diff),
        },
        "historical_unchanged": before == after_commands,
        "historical_sha256": after_commands,
        "production_helpers": helpers,
        "template_documentation": TEMPLATE_DOCUMENTATION,
        "runner_adaptations": [
            "BLACK_NUM_WORKERS=1 selects Black's thread-pool scheduler so the full-repository check completes.",
            "Black writes the unchanged-file count to stderr; the measured count reads both streams.",
            "BLACK_CACHE_DIR is under /tmp because the default user cache may be unwritable.",
            "GITHUB_STEP_SUMMARY points at /tmp because the inherited runner summary path may be read-only.",
            "The copied step summary drops the validator's trailing blank line so git diff --check accepts it.",
        ],
    }
    readme = render_readme(summary)
    (run_dir / "README.md").write_text(readme, encoding="utf-8")
    write_json(run_dir / "summary.json", summary)
    second_diff = run_command(diff_argv(), root, COMMAND_TIMEOUT)
    same_console = (
        second_diff["exit"] == first_diff["exit"]
        and second_diff["stdout"] == first_diff["stdout"]
        and second_diff["stderr"] == first_diff["stderr"]
    )
    if same_console:
        save_command(run_dir, "diffcheck", second_diff)
        summary["commands"]["diffcheck"] = command_view(second_diff)
        write_json(run_dir / "summary.json", summary)
        final_diff = run_command(diff_argv(), root, COMMAND_TIMEOUT)
        _require(
            final_diff["exit"] == second_diff["exit"]
            and final_diff["stdout"] == second_diff["stdout"]
            and final_diff["stderr"] == second_diff["stderr"],
            "git diff --check changed after the summary was written",
        )
    else:
        save_command(run_dir, "diffcheck", first_diff)
        _require(False, "git diff --check changed after README and summary were written")
    _require(historical_digests(root) == summary["historical_sha256"], "capture mutated history")
    validate_retained(root)
    return summary


def main() -> int:
    root = repo_root()
    summary = capture(root)
    exits = {name: command["exit"] for name, command in summary["commands"].items()}
    print(
        json_text(
            {
                "cwd": summary["cwd"],
                "exits": exits,
                "measured_file_counts": summary["measured_file_counts"],
                "python": summary["interpreters"]["python"]["path"],
                "historical_unchanged": summary["historical_unchanged"],
            }
        )
    )
    return 0 if all(code == 0 for code in exits.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
