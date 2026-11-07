"""Retain shebang-rejection acceptance receipts without touching historical proof.

The two literal ``/opt/anaconda3/bin/python3`` commands are attempted once. When
that interpreter is absent, their exits are recorded and
``/tmp/fresh-shebang-rejection-proof`` is left untouched. Pytest console/JUnit
and the eight mutation pairs then come from the installed interpreter. Any such
additional replay uses a fresh directory; the specified directory stays reserved
for the literal command and its reuse check.
"""

from __future__ import annotations

import hashlib
import json
import runpy
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from defusedxml import ElementTree as ET

TEST = "tests/scripts/test_check_deliberate_break_shebang_rejection.py"
REPLAY = "docs/evidence/issue-3743/shebang-rejection/replay.py"
EVIDENCE = Path("docs/evidence/issue-3743/shebang-rejection")
SPECIFIED_OUTPUT = Path("/tmp/fresh-shebang-rejection-proof")
LITERAL_INTERPRETER = "/opt/anaconda3/bin/python3"
LIMIT_SECONDS = 120
REPLAY_LIMIT_SECONDS = 600
HISTORICAL = (
    "docs/evidence/issue-3743/shebang-rejection/README.md",
    "docs/evidence/issue-3743/shebang-rejection/coverage.ini",
    "docs/evidence/issue-3743/shebang-rejection/replay.py",
    "docs/evidence/issue-3743/shebang-rejection/summary.json",
    "docs/evidence/issue-3743/shebang-rejection/proof.tar.gz",
    "docs/evidence/issue-3743/shebang-rejection/path-lookup/summary.json",
    "docs/evidence/issue-3743/shebang-rejection/path-lookup/proof.tar.gz",
    "docs/evidence/issue-3743/shebang-rejection/replay-validation/summary.json",
    "docs/evidence/issue-3743/shebang-rejection/replay-validation/proof.tar.gz",
    "docs/evidence/issue-3743/shebang-rejection/replay-validation/task-reconciliation.md",
    "docs/evidence/issue-3743/shebang-rejection/pre-change-record.json",
    "docs/evidence/issue-3743/shebang-rejection/main-acceptance-map.json",
    "docs/evidence/issue-3743/shebang-rejection/inspect_main_acceptance.py",
    "scripts/check_deliberate_break.py",
    "templates/consumer-repo/scripts/check_deliberate_break.py",
    TEST,
)
HELPERS = (
    "scripts/check_deliberate_break.py",
    "templates/consumer-repo/scripts/check_deliberate_break.py",
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def literal_pytest_argv() -> list[str]:
    return [LITERAL_INTERPRETER, "-m", "pytest", TEST, "-q", "-o", "addopts="]


def literal_replay_argv() -> list[str]:
    return [LITERAL_INTERPRETER, REPLAY, "--output", str(SPECIFIED_OUTPUT)]


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run_command(argv: list[str], cwd: Path, timeout: int) -> dict:
    """Run one command and keep its cwd, exit, and raw console."""
    started = time.monotonic()
    record = {"argv": argv, "cwd": str(cwd), "attempt": 1, "limit_seconds": timeout}
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
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


def additional_replay_output(specified: Path = SPECIFIED_OUTPUT) -> Path:
    """Create a parent for a replay that must not claim the reserved directory."""
    parent = Path(tempfile.mkdtemp(prefix="shebang-rejection-additional-"))
    destination = parent / "proof"
    if destination.resolve() == specified.resolve():
        raise RuntimeError("additional replay must not use the specified destination")
    return destination


def file_hashes(root: Path) -> dict[str, dict[str, int | str]]:
    hashes = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        data = path.read_bytes()
        hashes[path.relative_to(root).as_posix()] = {"sha256": digest(data), "bytes": len(data)}
    return hashes


def tree_digests(root: Path, relatives: tuple[str, ...]) -> dict[str, str]:
    return {relative: digest((root / relative).read_bytes()) for relative in relatives}


def pytest_argv(interpreter: str, junit: Path | None = None) -> list[str]:
    argv = [interpreter, "-m", "pytest", TEST, "-q", "-o", "addopts="]
    if junit is not None:
        argv.append(f"--junitxml={junit}")
    return argv


def junit_report(path: Path) -> dict:
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    failure_text = []
    for case in cases:
        for child in list(case):
            if child.tag in {"failure", "error"}:
                failure_text.append("".join(child.itertext()))
    return {
        "tests": len(cases),
        "failures": sum(1 for case in cases if case.find("failure") is not None),
        "errors": sum(1 for case in cases if case.find("error") is not None),
        "skipped": sum(1 for case in cases if case.find("skipped") is not None),
        "cases": [{"name": case.get("name"), "classname": case.get("classname")} for case in cases],
        "failure_text": "\n".join(failure_text),
    }


def expected_nodes(root: Path) -> set[str]:
    replay = runpy.run_path(str(root / REPLAY))
    return {
        f"{replay['TEST']}::{name}[{case}]"
        for name in replay["MUTATIONS"]
        for case in ("root", "template")
    }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_pairs(root: Path, proof: Path) -> list[dict]:
    summary = json.loads((proof / "summary.json").read_text(encoding="utf-8"))
    pairs = summary["pairs"]
    _require(summary["pair_count"] == len(pairs) == 8, "replay must retain eight pairs")
    _require({pair["node"] for pair in pairs} == expected_nodes(root), "pair nodes mismatch")
    for pair in pairs:
        case = "root" if pair["source"] == HELPERS[0] else "template"
        name = pair["node"].split("::", 1)[1].split("[", 1)[0]
        directory = proof / f"{case}-{name}"
        original = (directory / "original.py").read_bytes()
        mutant = (directory / "mutant.py").read_bytes()
        restored = (directory / "restored.py").read_bytes()
        _require(original == restored, f"{directory.name} restoration is not byte-identical")
        _require(original != mutant, f"{directory.name} mutant matches the original")
        _require(original == (root / pair["source"]).read_bytes(), f"{pair['source']} drifted")
        _require(digest(original) == pair["original_sha256"], "original hash mismatch")
        _require(digest(mutant) == pair["mutant_sha256"], "mutant hash mismatch")
        _require(digest(restored) == pair["restored_sha256"], "restored hash mismatch")
        for phase, exit_code in (("red", 1), ("green", 0)):
            stored = json.loads((directory / f"{phase}.json").read_text(encoding="utf-8"))
            _require(stored == pair[phase], f"{directory.name} {phase} receipt drifted")
            _require(stored["exit"] == exit_code, f"{directory.name} {phase} exit {stored['exit']}")
            report = junit_report(directory / f"{phase}.xml")
            _require(report["tests"] == 1, f"{directory.name} {phase} test count")
            _require(report["errors"] == 0 and report["skipped"] == 0, f"{directory.name} {phase}")
            _require(report["cases"][0]["name"] == pair["node"].split("::", 1)[1], "node name")
            if phase == "red":
                _require(report["failures"] == 1, f"{directory.name} red failures")
                _require("AssertionError" in report["failure_text"], f"{directory.name} red text")
            else:
                _require(report["failures"] == 0, f"{directory.name} green failures")
    return pairs


def validate_retained(root: Path, run_dir: Path | None = None) -> dict:
    """Check the retained acceptance-run tree against the command contract."""
    run_dir = run_dir if run_dir is not None else root / EVIDENCE / "acceptance-run"
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    literal_pytest = json.loads((run_dir / "literal-pytest.json").read_text(encoding="utf-8"))
    literal_replay = json.loads((run_dir / "literal-replay.json").read_text(encoding="utf-8"))
    _require(literal_pytest["argv"] == literal_pytest_argv(), "literal pytest argv")
    _require(literal_replay["argv"] == literal_replay_argv(), "literal replay argv")
    _require(literal_pytest["cwd"] == literal_replay["cwd"] == summary["cwd"], "literal cwd")
    for name, record in (("literal-pytest", literal_pytest), ("literal-replay", literal_replay)):
        _require(
            (run_dir / f"{name}.stdout").read_text(encoding="utf-8") == record["stdout"],
            f"{name} stdout",
        )
        _require(
            (run_dir / f"{name}.stderr").read_text(encoding="utf-8") == record["stderr"],
            f"{name} stderr",
        )
    operational = json.loads((run_dir / "operational-pytest.json").read_text(encoding="utf-8"))
    junit_command = json.loads((run_dir / "focused-junit.json").read_text(encoding="utf-8"))
    _require(operational["cwd"] == summary["cwd"], "operational cwd")
    _require(junit_command["cwd"] == summary["cwd"], "junit cwd")
    _require(operational["exit"] == 0, "operational pytest exit")
    _require("8 passed" in operational["stdout"], "operational pytest summary")
    _require("failed" not in operational["stdout"], "operational pytest failures")
    _require("skipped" not in operational["stdout"], "operational pytest skips")
    _require(operational["argv"] == pytest_argv(operational["argv"][0]), "operational argv shape")
    _require(junit_command["exit"] == 0, "junit pytest exit")
    report = junit_report(run_dir / "focused.xml")
    _require(report["tests"] == 8, "focused junit tests")
    _require(report["failures"] == report["errors"] == report["skipped"] == 0, "focused junit")
    _require(
        {case["name"] for case in report["cases"]}
        == {node.split("::", 1)[1] for node in expected_nodes(root)},
        "focused junit nodes",
    )
    proof = run_dir / "mutation-proof"
    validate_pairs(root, proof)
    reuse = json.loads((run_dir / "reuse-audit.json").read_text(encoding="utf-8"))
    _require(reuse["exit"] != 0, "reuse must be rejected")
    _require(reuse["all_bytes_unchanged"] is True, "reuse changed proof bytes")
    _require(reuse["file_count"] == 93, "reuse file count")
    _require("File exists" in reuse["stderr"], "reuse must fail before mutation")
    _require(file_hashes(proof) == reuse["files"], "retained proof hashes drifted")
    _require(reuse["argv"][2:] == ["--output", reuse["output"]], "reuse argv")
    _require(
        junit_command["argv"]
        == pytest_argv(
            junit_command["argv"][0],
            Path(
                summary.get(
                    "receipt_directory", str(Path(summary["cwd"]) / EVIDENCE / "acceptance-run")
                )
            )
            / "focused.xml",
        ),
        "focused junit argv",
    )
    specified = json.loads((run_dir / "specified-destination.json").read_text(encoding="utf-8"))
    _require(specified["path"] == str(SPECIFIED_OUTPUT), "specified path")
    reserved = Path(reuse["output"]).resolve() == SPECIFIED_OUTPUT.resolve()
    _require(reserved is (literal_replay["exit"] == 0), "destination role")
    if literal_replay["exit"] == 0:
        _require(specified["created_by_this_run"] is True, "literal replay did not retain output")
        _require(specified["explicit_reuse_checked"] is True, "explicit reuse was not checked")
        _require(Path(reuse["output"]).resolve() == SPECIFIED_OUTPUT.resolve(), "reuse path")
    else:
        _require(specified["created_by_this_run"] is False, "absent interpreter created output")
        _require(specified["explicit_reuse_checked"] is False, "uncreated output was reused")
        _require(specified["exists_after"] is specified["existed_before"], "specified path changed")
        _require(Path(reuse["output"]).resolve() != SPECIFIED_OUTPUT.resolve(), "fresh destination")
    _require(summary["historical_unchanged"] is True, "historical bytes changed during capture")
    return summary


def _capture_staged(root: Path, run_dir: Path) -> dict:
    run_dir.mkdir(parents=True)
    historical_before = tree_digests(root, HISTORICAL)
    existed_before = SPECIFIED_OUTPUT.exists()
    literal_pytest = run_command(literal_pytest_argv(), root, LIMIT_SECONDS)
    save_command(run_dir, "literal-pytest", literal_pytest)
    literal_replay = run_command(literal_replay_argv(), root, REPLAY_LIMIT_SECONDS)
    save_command(run_dir, "literal-replay", literal_replay)

    if literal_pytest["stopped"] == "interpreter-absent":
        interpreter = sys.executable
    else:
        interpreter = LITERAL_INTERPRETER
    operational = run_command(pytest_argv(interpreter), root, LIMIT_SECONDS)
    save_command(run_dir, "operational-pytest", operational)
    junit_path = run_dir / "focused.xml"
    junit_record = run_command(pytest_argv(interpreter, junit_path), root, LIMIT_SECONDS)
    save_command(run_dir, "focused-junit", junit_record)

    if literal_replay["exit"] == 0:
        replay_output = SPECIFIED_OUTPUT
        replay_record = literal_replay
        created_by_this_run = not existed_before and SPECIFIED_OUTPUT.exists()
    else:
        replay_output = additional_replay_output()
        replay_interpreter = (
            sys.executable
            if literal_replay["stopped"] == "interpreter-absent"
            else LITERAL_INTERPRETER
        )
        replay_argv = [replay_interpreter, str(root / REPLAY), "--output", str(replay_output)]
        replay_record = run_command(replay_argv, root, REPLAY_LIMIT_SECONDS)
        save_command(run_dir, "additional-replay", replay_record)
        created_by_this_run = False
    if replay_record["exit"] != 0 or not replay_output.is_dir():
        raise RuntimeError(
            f"replay failed before receipts could be retained: exit {replay_record['exit']}"
        )
    before = file_hashes(replay_output)
    reuse = run_command(replay_record["argv"], root, LIMIT_SECONDS)
    after = file_hashes(replay_output)
    reuse_audit = {
        "argv": replay_record["argv"],
        "cwd": str(root),
        "output": str(replay_output),
        "exit": reuse["exit"],
        "stdout": reuse["stdout"],
        "stderr": reuse["stderr"],
        "file_count": len(before),
        "all_bytes_unchanged": before == after,
        "files": before,
        "preserves_proof_before_mutation": before == after and reuse["exit"] != 0,
    }
    write_json(run_dir / "reuse-audit.json", reuse_audit)
    (run_dir / "reuse.stdout").write_text(reuse["stdout"], encoding="utf-8")
    (run_dir / "reuse.stderr").write_text(reuse["stderr"], encoding="utf-8")
    shutil.copytree(replay_output, run_dir / "mutation-proof")
    specified = {
        "path": str(SPECIFIED_OUTPUT),
        "role": (
            "Reserved for the literal acceptance command and its explicit reuse check. "
            "Additional replays use a fresh directory."
        ),
        "existed_before": existed_before,
        "created_by_this_run": created_by_this_run and literal_replay["exit"] == 0,
        "exists_after": SPECIFIED_OUTPUT.exists(),
        "explicit_reuse_checked": literal_replay["exit"] == 0,
        "additional_output": None if literal_replay["exit"] == 0 else str(replay_output),
    }
    write_json(run_dir / "specified-destination.json", specified)
    historical_after = tree_digests(root, HISTORICAL)
    summary = {
        "role": (
            "Current acceptance-run receipts. Historical README, summary.json, proof.tar.gz, "
            "path-lookup/, and replay-validation/ are not acceptance for this run."
        ),
        "check_date": datetime.now(UTC).date().isoformat(),
        "cwd": str(root),
        "receipt_directory": str(run_dir),
        "literal_interpreter": LITERAL_INTERPRETER,
        "receipt_interpreter": interpreter,
        "pair_count": json.loads(
            (run_dir / "mutation-proof" / "summary.json").read_text(encoding="utf-8")
        )["pair_count"],
        "satisfies_literal_acceptance": literal_pytest["exit"] == 0 and literal_replay["exit"] == 0,
        "literal_pytest_exit": literal_pytest["exit"],
        "literal_replay_exit": literal_replay["exit"],
        "operational_pytest_exit": operational["exit"],
        "focused_junit_exit": junit_record["exit"],
        "replay_exit": replay_record["exit"],
        "reuse_exit": reuse["exit"],
        "historical_unchanged": historical_before == historical_after,
        "historical_sha256": historical_after,
        "production_sha256": {helper: historical_after[helper] for helper in HELPERS},
    }
    write_json(run_dir / "summary.json", summary)
    validate_retained(root, run_dir)
    return summary


def capture(root: Path) -> dict:
    """Validate a separate attempt before replacing the last complete receipt tree."""
    run_dir = root / EVIDENCE / "acceptance-run"
    attempt = Path(tempfile.mkdtemp(prefix=".acceptance-attempt-", dir=run_dir.parent))
    staged = attempt / "acceptance-run"
    previous = attempt / "previous"
    try:
        summary = _capture_staged(root, staged)
        if run_dir.exists():
            run_dir.rename(previous)
        try:
            staged.rename(run_dir)
        except BaseException:
            if previous.exists():
                previous.rename(run_dir)
            raise
    except BaseException as exc:
        write_json(attempt / "failure.json", {"error": str(exc), "type": type(exc).__name__})
        raise
    shutil.rmtree(attempt)
    return summary


def main() -> int:
    root = repo_root()
    summary = capture(root)
    print(
        json.dumps(
            {
                "cwd": summary["cwd"],
                "literal_pytest_exit": summary["literal_pytest_exit"],
                "literal_replay_exit": summary["literal_replay_exit"],
                "operational_pytest_exit": summary["operational_pytest_exit"],
                "reuse_exit": summary["reuse_exit"],
                "satisfies_literal_acceptance": summary["satisfies_literal_acceptance"],
                "receipt_interpreter": summary["receipt_interpreter"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
