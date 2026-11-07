"""Compare the recorded shebang-rejection baseline and candidate on current inputs.

Baseline uses the twelve helper modules stored in the historical replay-validation
command. The candidate adds only the shebang-rejection module. Both phases use the
same coverage configuration, pytest options, and interpreter. Historical proof
archives are read-only.
"""

from __future__ import annotations

import hashlib
import json
import os
import runpy
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.parsers import expat

EVIDENCE = Path("docs/evidence/issue-3743/shebang-rejection")
RUN = EVIDENCE / "matched-comparison"
COVERAGE_INI = "docs/evidence/issue-3743/shebang-rejection/coverage.ini"
REPLAY = "docs/evidence/issue-3743/shebang-rejection/replay.py"
SHEBANG = "tests/scripts/test_check_deliberate_break_shebang_rejection.py"
HELPERS = (
    "scripts/check_deliberate_break.py",
    "templates/consumer-repo/scripts/check_deliberate_break.py",
)
BASELINE_MODULES = (
    "tests/scripts/test_check_deliberate_break.py",
    "tests/scripts/test_check_deliberate_break_archive.py",
    "tests/scripts/test_check_deliberate_break_fallback_target_selection.py",
    "tests/scripts/test_check_deliberate_break_head_launch.py",
    "tests/scripts/test_check_deliberate_break_launch_boundaries.py",
    "tests/scripts/test_check_deliberate_break_launcher_admission.py",
    "tests/scripts/test_check_deliberate_break_module_boundaries.py",
    "tests/scripts/test_check_deliberate_break_probe_option_boundaries.py",
    "tests/scripts/test_check_deliberate_break_repair_failures.py",
    "tests/scripts/test_check_deliberate_break_runtime_health.py",
    "tests/scripts/test_check_deliberate_break_runtime_probes.py",
    "tests/scripts/test_check_deliberate_break_uv_resolution.py",
)
CLASSNAME = "tests.scripts.test_check_deliberate_break_shebang_rejection"
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
    "scripts/check_deliberate_break.py",
    "templates/consumer-repo/scripts/check_deliberate_break.py",
    SHEBANG,
    "tests/scripts/test_shebang_rejection_replay.py",
)
INPUTS = (*HELPERS, *BASELINE_MODULES, SHEBANG, COVERAGE_INI, REPLAY)
PHASE_TIMEOUT = 900
ROLE = (
    "Current matched comparison for the input bytes in input-bindings.json. "
    "summary.json, proof.tar.gz, path-lookup/, and replay-validation/ are historical "
    "receipts for earlier bytes. They are not this comparison."
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def expected_added_nodes(root: Path) -> list[list[str]]:
    """Pytest collects each mutation once per root/template parameter."""
    mutations = runpy.run_path(str(root / REPLAY))["MUTATIONS"]
    return [[CLASSNAME, f"{name}[{case}]"] for name in mutations for case in ("root", "template")]


def candidate_modules() -> tuple[str, ...]:
    return (*BASELINE_MODULES, SHEBANG)


def parse_junit(path: Path) -> ET.Element:
    """Read JUnit without dependencies, rejecting DTDs and entity declarations."""
    data = path.read_bytes()
    parser = expat.ParserCreate()

    def reject_declaration(*_args):
        raise ValueError("JUnit must not contain DTDs or entity declarations")

    parser.StartDoctypeDeclHandler = reject_declaration
    parser.EntityDeclHandler = reject_declaration
    parser.ExternalEntityRefHandler = reject_declaration
    parser.Parse(data, True)
    return ET.fromstring(data)


def junit_nodes(path: Path) -> dict[tuple[str, str], str]:
    rows: dict[tuple[str, str], str] = {}
    for case in parse_junit(path).iter("testcase"):
        key = (case.get("classname"), case.get("name"))
        require(None not in key and key not in rows, f"invalid JUnit node {key}")
        rows[key] = next(
            (kind for kind in ("failure", "error", "skipped") if case.find(kind) is not None),
            "passed",
        )
    require(bool(rows), f"empty JUnit report: {path}")
    return rows


def _arcs(rows: list) -> set[tuple[int, int]]:
    return {tuple(row) for row in rows}


def matched_helper(path: str) -> str | None:
    """Map a coverage path to one helper. The template path also ends with the root path."""
    matches = [helper for helper in HELPERS if path == helper or path.endswith("/" + helper)]
    if not matches:
        return None
    return max(matches, key=len)


def file_views(payload: dict) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for path, info in payload["files"].items():
        helper = matched_helper(path)
        if helper is None:
            continue
        require(helper not in indexed, f"duplicate coverage file {helper}")
        indexed[helper] = {
            "statements": set(info["executed_lines"])
            | set(info["missing_lines"])
            | set(info["excluded_lines"]),
            "branches": _arcs(info["executed_branches"]) | _arcs(info["missing_branches"]),
            "executed_lines": set(info["executed_lines"]),
            "executed_branches": _arcs(info["executed_branches"]),
            "excluded_lines": set(info["excluded_lines"]),
            "summary": info["summary"],
        }
    require(set(indexed) == set(HELPERS), f"coverage files were {sorted(indexed)}")
    return indexed


def _sorted_nodes(rows: dict[tuple[str, str], str]) -> list[list[str]]:
    return [[classname, name, outcome] for (classname, name), outcome in sorted(rows.items())]


def build_comparison(
    baseline_nodes: dict[tuple[str, str], str],
    candidate_nodes: dict[tuple[str, str], str],
    baseline_cov: dict,
    candidate_cov: dict,
    expected_added: list[list[str]],
) -> dict:
    """Compute node and coverage deltas from raw JUnit and coverage JSON."""
    base_files = file_views(baseline_cov)
    cand_files = file_views(candidate_cov)
    added = sorted(candidate_nodes.keys() - baseline_nodes.keys())
    removed = sorted(baseline_nodes.keys() - candidate_nodes.keys())
    changed = [
        [classname, name, baseline_nodes[(classname, name)], candidate_nodes[(classname, name)]]
        for classname, name in sorted(set(baseline_nodes) & set(candidate_nodes))
        if baseline_nodes[(classname, name)] != candidate_nodes[(classname, name)]
    ]
    deltas = {}
    universes = {}
    identical = True
    exclusions = 0
    line_regressions = []
    branch_regressions = []
    for helper in HELPERS:
        base = base_files[helper]
        cand = cand_files[helper]
        same_statements = base["statements"] == cand["statements"]
        same_branches = base["branches"] == cand["branches"]
        identical = identical and same_statements and same_branches
        exclusions += len(base["excluded_lines"]) + len(cand["excluded_lines"])
        exclusions += base["summary"]["excluded_lines"] + cand["summary"]["excluded_lines"]
        removed_lines = sorted(base["executed_lines"] - cand["executed_lines"])
        removed_branches = sorted(base["executed_branches"] - cand["executed_branches"])
        line_regressions.extend([helper, line] for line in removed_lines)
        branch_regressions.extend([helper, list(branch)] for branch in removed_branches)
        added_branches = sorted(cand["executed_branches"] - base["executed_branches"])
        deltas[helper] = {
            "added_lines": sorted(cand["executed_lines"] - base["executed_lines"]),
            "removed_lines": removed_lines,
            "added_branches": [list(branch) for branch in added_branches],
            "removed_branches": [list(branch) for branch in removed_branches],
        }
        universes[helper] = {
            "baseline_statements": base["summary"]["num_statements"],
            "candidate_statements": cand["summary"]["num_statements"],
            "baseline_branches": base["summary"]["num_branches"],
            "candidate_branches": cand["summary"]["num_branches"],
            "statement_universe": len(base["statements"]),
            "candidate_statement_universe": len(cand["statements"]),
            "branch_universe": len(base["branches"]),
            "candidate_branch_universe": len(cand["branches"]),
            "statements_identical": same_statements,
            "branches_identical": same_branches,
        }
        identical = identical and (
            base["summary"]["num_statements"] == cand["summary"]["num_statements"]
            and base["summary"]["num_branches"] == cand["summary"]["num_branches"]
        )
    base_totals = baseline_cov["totals"]
    cand_totals = candidate_cov["totals"]
    identical = identical and (
        base_totals["num_statements"] == cand_totals["num_statements"]
        and base_totals["num_branches"] == cand_totals["num_branches"]
    )
    exclusions += base_totals["excluded_lines"] + cand_totals["excluded_lines"]
    added_rows = [list(node) for node in added]
    return {
        "baseline_nodes": len(baseline_nodes),
        "candidate_nodes": len(candidate_nodes),
        "baseline_pass": sum(item == "passed" for item in baseline_nodes.values()),
        "candidate_pass": sum(item == "passed" for item in candidate_nodes.values()),
        "added_nodes": added_rows,
        "added_outcomes": sorted(candidate_nodes[tuple(node)] for node in added),
        "removed_nodes": [list(node) for node in removed],
        "changed_old_outcomes": changed,
        "universes_identical": identical,
        "universes": universes,
        "exclusions": exclusions,
        "covered_line_regressions": line_regressions,
        "covered_branch_regressions": branch_regressions,
        "deltas": deltas,
        "baseline_totals": base_totals,
        "candidate_totals": cand_totals,
        "expected_added_nodes": expected_added,
        "node_outcomes": {
            "baseline": _sorted_nodes(baseline_nodes),
            "candidate": _sorted_nodes(candidate_nodes),
        },
    }


def contract_errors(comparison: dict) -> list[str]:
    """Return the matched-comparison acceptance failures for one computed report."""
    errors = []
    expected = comparison["expected_added_nodes"]
    if sorted(map(tuple, comparison["added_nodes"])) != sorted(map(tuple, expected)):
        errors.append(f"added nodes {comparison['added_nodes']} != expected {expected}")
    if comparison["added_outcomes"] != ["passed"] * len(expected):
        errors.append(f"added outcomes were {comparison['added_outcomes']}")
    if comparison["removed_nodes"]:
        errors.append(f"removed nodes {comparison['removed_nodes']}")
    if comparison["changed_old_outcomes"]:
        errors.append(f"changed old outcomes {comparison['changed_old_outcomes']}")
    if not comparison["universes_identical"]:
        errors.append(f"statement/branch universes differ {comparison['universes']}")
    if comparison["exclusions"] != 0:
        errors.append(f"exclusions {comparison['exclusions']}")
    if comparison["covered_line_regressions"] or comparison["covered_branch_regressions"]:
        errors.append("covered line or branch regression")
    return errors


def recorded_modules(argv: list[str]) -> tuple[list[str], list[str]]:
    """Split a coverage pytest command into module paths and the shared option tail."""
    start = argv.index("pytest") + 1
    modules: list[str] = []
    options: list[str] = []
    for arg in argv[start:]:
        if arg.startswith("-") or options:
            options.append(arg)
        else:
            modules.append(arg)
    return modules, options


def coverage_prefix(argv: list[str]) -> list[str]:
    prefix = []
    for arg in argv[: argv.index("pytest")]:
        if arg.startswith("--data-file="):
            prefix.append("--data-file=<phase>")
        else:
            prefix.append(arg)
    return prefix


def commands_match(baseline: list[str], candidate: list[str]) -> bool:
    base_modules, base_options = recorded_modules(baseline)
    cand_modules, cand_options = recorded_modules(candidate)
    base_junit = [arg for arg in base_options if arg.startswith("--junitxml=")]
    cand_junit = [arg for arg in cand_options if arg.startswith("--junitxml=")]
    return (
        coverage_prefix(baseline) == coverage_prefix(candidate)
        and base_modules == list(BASELINE_MODULES)
        and cand_modules == list(candidate_modules())
        and [arg for arg in base_options if not arg.startswith("--junitxml=")]
        == [arg for arg in cand_options if not arg.startswith("--junitxml=")]
        and len(base_junit) == len(cand_junit) == 1
        and base_junit != cand_junit
    )


def phase_argv(
    interpreter: str, modules: tuple[str, ...], data_file: Path, junit: Path
) -> list[str]:
    return [
        interpreter,
        "-m",
        "coverage",
        "run",
        f"--rcfile={COVERAGE_INI}",
        f"--data-file={data_file}",
        "-m",
        "pytest",
        *modules,
        "-q",
        "-o",
        "addopts=",
        "-m",
        "not slow",
        f"--junitxml={junit}",
    ]


def json_argv(interpreter: str, data_file: Path, output: Path) -> list[str]:
    return [
        interpreter,
        "-m",
        "coverage",
        "json",
        f"--rcfile={COVERAGE_INI}",
        f"--data-file={data_file}",
        "-o",
        str(output),
    ]


def run_command(argv: list[str], cwd: Path, timeout: int) -> dict:
    started = time.monotonic()
    env = os.environ.copy()
    for key in ("PYTEST_ADDOPTS", "COVERAGE_FILE"):
        env.pop(key, None)
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
    return {
        "argv": argv,
        "cwd": str(cwd),
        "exit": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration_seconds": round(time.monotonic() - started, 3),
        "env_overrides": {"PYTEST_ADDOPTS": None, "COVERAGE_FILE": None},
    }


def save_command(directory: Path, name: str, record: dict) -> None:
    stored = {key: value for key, value in record.items() if key not in {"stdout", "stderr"}}
    write_json(directory / f"{name}.json", stored)
    (directory / f"{name}.stdout").write_text(record["stdout"], encoding="utf-8")
    (directory / f"{name}.stderr").write_text(record["stderr"], encoding="utf-8")


def file_digest(root: Path, relative: str) -> dict:
    path = root / relative
    data = path.read_bytes()
    return {"sha256": digest(data), "bytes": len(data)}


def input_bindings(root: Path) -> dict[str, dict]:
    return {relative: file_digest(root, relative) for relative in INPUTS}


def historical_digests(root: Path) -> dict[str, dict]:
    return {relative: file_digest(root, relative) for relative in HISTORICAL}


def render_readme(summary: dict) -> str:
    comparison = summary["comparison"]
    interpreter = summary["interpreter"]
    return "\n".join(
        [
            "# Current shebang-rejection matched comparison",
            "",
            ROLE,
            "",
            f"Check date: {summary['check_date']}",
            f"cwd: `{summary['cwd']}`",
            f"Interpreter: `{interpreter['path']}` ({interpreter['version']})",
            "The literal `/opt/anaconda3/bin/python3` path is not this comparison's interpreter.",
            "",
            "Selection: the twelve modules in replay-validation `baseline-command.json`,",
            "with only `tests/scripts/test_check_deliberate_break_shebang_rejection.py`",
            "added for the candidate. Both phases use `coverage.ini`, `-q -o addopts=`,",
            "and `-m not slow`.",
            "",
            f"Baseline nodes: {comparison['baseline_nodes']} "
            f"({comparison['baseline_pass']} passed)",
            f"Candidate nodes: {comparison['candidate_nodes']} "
            f"({comparison['candidate_pass']} passed)",
            f"Added passing nodes: {len(comparison['added_nodes'])}",
            f"Removed nodes: {len(comparison['removed_nodes'])}",
            f"Changed old outcomes: {len(comparison['changed_old_outcomes'])}",
            f"Universes identical: {comparison['universes_identical']}",
            f"Exclusions: {comparison['exclusions']}",
            f"Covered-line regressions: {len(comparison['covered_line_regressions'])}",
            f"Covered-branch regressions: {len(comparison['covered_branch_regressions'])}",
            "",
            "Raw JUnit, coverage JSON, command receipts, and computed counts/deltas",
            "are in this directory and in `proof.tar.gz`. `summary.json` stays outside",
            "the archive and records the archive hash. Input SHA256 values are in",
            "`input-bindings.json`.",
            "",
        ]
    )


def pack_archive(directory: Path) -> dict:
    members = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.name not in {"proof.tar.gz", "summary.json", "manifest.json"}
    )
    manifest = {
        path.name: {"sha256": digest(path.read_bytes()), "bytes": path.stat().st_size}
        for path in members
    }
    manifest_path = directory / "manifest.json"
    write_json(manifest_path, manifest)
    archive_path = directory / "proof.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        for path in [*members, manifest_path]:
            info = tar.gettarinfo(path, path.name)
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            with path.open("rb") as handle:
                tar.addfile(info, handle)
    payload = archive_path.read_bytes()
    return {
        "path": "proof.tar.gz",
        "sha256": digest(payload),
        "bytes": len(payload),
        "verified_manifest_members": len(manifest),
        "manifest_sha256": digest(manifest_path.read_bytes()),
    }


def verify_archive(directory: Path, meta: dict) -> dict:
    archive_path = directory / meta["path"]
    payload = archive_path.read_bytes()
    with tarfile.open(archive_path, "r:gz") as tar:
        manifest_bytes = tar.extractfile("manifest.json").read()
        manifest = json.loads(manifest_bytes)
        names = {member.name for member in tar.getmembers() if member.isfile()}
        mismatches = []
        for member in tar.getmembers():
            if not member.isfile() or member.name == "manifest.json":
                continue
            body = tar.extractfile(member).read()
            spec = manifest[member.name]
            loose = directory / member.name
            if (
                digest(body) != spec["sha256"]
                or len(body) != spec["bytes"]
                or body != loose.read_bytes()
            ):
                mismatches.append(member.name)
    checked = {
        "sha256_matches_summary": digest(payload) == meta["sha256"],
        "bytes_match_summary": len(payload) == meta["bytes"],
        "manifest_sha256_matches_summary": digest(manifest_bytes) == meta["manifest_sha256"],
        "member_count_matches_summary": len(manifest) == meta["verified_manifest_members"],
        "manifest_covers_archive_files": names - {"manifest.json"} == set(manifest),
        "member_mismatches": mismatches,
    }
    checked["verified"] = (
        all(
            checked[key]
            for key in (
                "sha256_matches_summary",
                "bytes_match_summary",
                "manifest_sha256_matches_summary",
                "member_count_matches_summary",
                "manifest_covers_archive_files",
            )
        )
        and not mismatches
    )
    return checked


def validate_retained(root: Path) -> dict:
    """Recompute the comparison from retained raw inputs and check the contract."""
    run_dir = root / RUN
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    baseline_command = json.loads((run_dir / "baseline-command.json").read_text(encoding="utf-8"))
    candidate_command = json.loads((run_dir / "candidate-command.json").read_text(encoding="utf-8"))
    require(baseline_command["exit"] == 0, "baseline exit")
    require(candidate_command["exit"] == 0, "candidate exit")
    require(baseline_command["cwd"] == candidate_command["cwd"] == summary["cwd"], "cwd")
    require(commands_match(baseline_command["argv"], candidate_command["argv"]), "phase settings")
    expected = expected_added_nodes(root)
    comparison = build_comparison(
        junit_nodes(run_dir / "baseline.xml"),
        junit_nodes(run_dir / "candidate.xml"),
        json.loads((run_dir / "baseline.json").read_text(encoding="utf-8")),
        json.loads((run_dir / "candidate.json").read_text(encoding="utf-8")),
        expected,
    )
    stored = json.loads((run_dir / "comparison.json").read_text(encoding="utf-8"))
    require(stored == comparison, "stored comparison drifted from raw inputs")
    problems = contract_errors(comparison)
    require(not problems, "; ".join(problems))
    require(summary["comparison"] == comparison, "summary comparison drifted")
    bindings = json.loads((run_dir / "input-bindings.json").read_text(encoding="utf-8"))
    require(bindings == summary["input_sha256"], "summary bindings drifted")
    archive = verify_archive(run_dir, summary["archive"])
    require(archive["verified"], f"archive verification failed: {archive}")
    readme = (run_dir / "README.md").read_text(encoding="utf-8")
    require(summary["interpreter"]["path"] in readme, "readme omits the interpreter")
    require("historical" in readme.lower(), "readme does not distinguish historical receipts")
    require(summary["role"] == ROLE, "summary role")
    return summary


def capture(root: Path) -> dict:
    run_dir = root / RUN
    if run_dir.exists():
        for child in sorted(run_dir.iterdir(), reverse=True):
            if child.is_file():
                child.unlink()
            else:
                raise RuntimeError(f"unexpected directory in {run_dir}: {child}")
    else:
        run_dir.mkdir(parents=True)
    before = historical_digests(root)
    bindings = input_bindings(root)
    interpreter = sys.executable
    with tempfile.TemporaryDirectory(prefix="shebang-matched-comparison-") as temporary:
        work = Path(temporary)
        phases = {}
        for phase, modules in (("baseline", BASELINE_MODULES), ("candidate", candidate_modules())):
            data_file = work / f"{phase}.coverage"
            junit = run_dir / f"{phase}.xml"
            record = run_command(
                phase_argv(interpreter, modules, data_file, junit),
                root,
                PHASE_TIMEOUT,
            )
            save_command(run_dir, f"{phase}-command", record)
            require(record["exit"] == 0, f"{phase} pytest exited {record['exit']}")
            json_record = run_command(
                json_argv(interpreter, data_file, run_dir / f"{phase}.json"),
                root,
                120,
            )
            save_command(run_dir, f"{phase}-json-command", json_record)
            require(json_record["exit"] == 0, f"{phase} coverage json exited {json_record['exit']}")
            phases[phase] = record
    comparison = build_comparison(
        junit_nodes(run_dir / "baseline.xml"),
        junit_nodes(run_dir / "candidate.xml"),
        json.loads((run_dir / "baseline.json").read_text(encoding="utf-8")),
        json.loads((run_dir / "candidate.json").read_text(encoding="utf-8")),
        expected_added_nodes(root),
    )
    write_json(run_dir / "comparison.json", comparison)
    write_json(run_dir / "input-bindings.json", bindings)
    readme = render_readme(
        {
            "check_date": datetime.now(UTC).date().isoformat(),
            "cwd": str(root),
            "interpreter": {"path": interpreter, "version": sys.version},
            "comparison": comparison,
        }
    )
    (run_dir / "README.md").write_text(readme, encoding="utf-8")
    archive = pack_archive(run_dir)
    after = historical_digests(root)
    summary = {
        "role": ROLE,
        "check_date": datetime.now(UTC).date().isoformat(),
        "cwd": str(root),
        "interpreter": {
            "path": interpreter,
            "version": sys.version,
            "literal_anaconda_available": Path("/opt/anaconda3/bin/python3").is_file(),
        },
        "commands": {
            "baseline": {
                "exit": phases["baseline"]["exit"],
                "duration_seconds": phases["baseline"]["duration_seconds"],
            },
            "candidate": {
                "exit": phases["candidate"]["exit"],
                "duration_seconds": phases["candidate"]["duration_seconds"],
            },
        },
        "comparison": comparison,
        "input_sha256": bindings,
        "historical_unchanged": before == after,
        "historical_sha256": after,
        "archive": archive,
    }
    require(summary["historical_unchanged"], "historical evidence changed during comparison")
    write_json(run_dir / "summary.json", summary)
    problems = contract_errors(comparison)
    require(not problems, "; ".join(problems))
    validate_retained(root)
    return summary


def main() -> int:
    summary = capture(repo_root())
    comparison = summary["comparison"]
    print(
        json.dumps(
            {
                "baseline_nodes": comparison["baseline_nodes"],
                "candidate_nodes": comparison["candidate_nodes"],
                "added_nodes": len(comparison["added_nodes"]),
                "removed_nodes": len(comparison["removed_nodes"]),
                "changed_old_outcomes": len(comparison["changed_old_outcomes"]),
                "universes_identical": comparison["universes_identical"],
                "exclusions": comparison["exclusions"],
                "covered_line_regressions": len(comparison["covered_line_regressions"]),
                "covered_branch_regressions": len(comparison["covered_branch_regressions"]),
                "interpreter": summary["interpreter"]["path"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
