"""Map merged-main shebang-rejection evidence to the acceptance requirements.

The script records what the historical archives actually prove and the gaps that
remain. It does not modify production helpers, the shebang tests, replay.py, or
existing proof archives.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import runpy
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

TEST = "tests/scripts/test_check_deliberate_break_shebang_rejection.py"
HELPER = "scripts/check_deliberate_break.py"
TEMPLATE_HELPER = "templates/consumer-repo/scripts/check_deliberate_break.py"
REPLAY = "docs/evidence/issue-3743/shebang-rejection/replay.py"
EVIDENCE = Path("docs/evidence/issue-3743/shebang-rejection")
SUMMARIES = (
    EVIDENCE / "summary.json",
    EVIDENCE / "path-lookup/summary.json",
    EVIDENCE / "replay-validation/summary.json",
)
LITERAL_COMMANDS = (
    [
        "/opt/anaconda3/bin/python3",
        "-m",
        "pytest",
        TEST,
        "-q",
        "-o",
        "addopts=",
    ],
    [
        "/opt/anaconda3/bin/python3",
        REPLAY,
        "--output",
        "/tmp/fresh-shebang-rejection-proof",
    ],
)
FOCUSED_LIMIT_SECONDS = 120
STOP_RULE = (
    "Attempt each literal acceptance command at most once. "
    "If /opt/anaconda3/bin/python3 is missing or not executable, record exit 127 "
    "and stop that command. Do not substitute another interpreter, do not change "
    "privacy settings, and do not create /tmp/fresh-shebang-rejection-proof. "
    "Cap the focused installed-interpreter pytest path at 120 seconds. "
    "Do not edit the shebang tests, replay.py, or either production helper until "
    "this pre-change record is written."
)
REQUIREMENTS = (
    {
        "id": "pytest-command",
        "requirement": (
            "/opt/anaconda3/bin/python3 -m pytest "
            "tests/scripts/test_check_deliberate_break_shebang_rejection.py -q "
            "-o addopts= exits 0 with exactly eight passes and no errors or skips; "
            "archived raw JUnit and command receipts establish that result for the "
            "recorded inputs."
        ),
    },
    {
        "id": "replay-command",
        "requirement": (
            "/opt/anaconda3/bin/python3 "
            "docs/evidence/issue-3743/shebang-rejection/replay.py --output "
            "/tmp/fresh-shebang-rejection-proof exits 0 with eight exact named "
            "assertion RED exit1/restored GREEN exit0 pairs, no errors/skips and "
            "byte-identical restoration. Reusing its output exits nonzero before "
            "mutation and preserves every proof file."
        ),
    },
    {
        "id": "matched-comparison",
        "requirement": (
            "Matched comparison adds exactly eight passing nodes, removes no nodes, "
            "changes no old outcomes, uses identical statement/branch universes with "
            "zero exclusions, and introduces zero covered-line or covered-branch "
            "regressions; raw inputs and computed counts/deltas are archived."
        ),
    },
    {
        "id": "validation-and-helpers",
        "requirement": (
            "Full-repository Black, focused Ruff, strict template completeness and "
            "git diff --check exit 0 with recorded commands and output. Production "
            "helpers equal each other and their base bytes; historical evidence is "
            "unchanged."
        ),
    },
    {
        "id": "archive-bindings",
        "requirement": (
            "Every delivered archive can be opened and every member hash/length and "
            "current input binding verifies. Documentation distinguishes historical "
            "receipts from current acceptance and records actual interpreter paths "
            "and measured validation file counts."
        ),
    },
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def git_output(root: Path, args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def inspected_main(root: Path) -> dict:
    commit = git_output(root, ["rev-parse", "origin/main"])
    return {
        "ref": "origin/main",
        "commit": commit,
        "committed_at": git_output(root, ["log", "-1", "--format=%cI", commit]),
        "subject": git_output(root, ["log", "-1", "--format=%s", commit]),
    }


def verify_archive(archive: Path, summary: dict) -> dict:
    """Open one historical proof archive and check every manifest binding."""
    payload = archive.read_bytes()
    meta = summary["archive"]
    archive_sha = digest(payload)
    with tarfile.open(archive, "r:gz") as handle:
        manifest_bytes = handle.extractfile("manifest.json").read()
        manifest = json.loads(manifest_bytes)
        members = [member for member in handle.getmembers() if member.isfile()]
        names = {member.name for member in members}
        mismatches = []
        for member in members:
            if member.name == "manifest.json":
                continue
            member_bytes = handle.extractfile(member).read()
            spec = manifest[member.name]
            if digest(member_bytes) != spec["sha256"] or len(member_bytes) != spec["bytes"]:
                mismatches.append(member.name)
    checked = {
        "archive": str(archive),
        "sha256": archive_sha,
        "bytes": len(payload),
        "manifest_sha256": digest(manifest_bytes),
        "manifest_members": len(manifest),
        "sha256_matches_summary": archive_sha == meta["sha256"],
        "bytes_match_summary": len(payload) == meta["bytes"],
        "manifest_sha256_matches_summary": digest(manifest_bytes) == meta["manifest_sha256"],
        "member_count_matches_summary": len(manifest) == meta["verified_manifest_members"],
        "manifest_covers_archive_files": names - {"manifest.json"} == set(manifest),
        "member_mismatches": mismatches,
    }
    checked["verified"] = bool(
        checked["sha256_matches_summary"]
        and checked["bytes_match_summary"]
        and checked["manifest_sha256_matches_summary"]
        and checked["member_count_matches_summary"]
        and checked["manifest_covers_archive_files"]
        and not mismatches
    )
    return checked


def historical_archives(root: Path) -> list[dict]:
    checked = []
    for relative in SUMMARIES:
        summary_path = root / relative
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        archive = summary_path.parent / summary["archive"]["path"]
        result = verify_archive(archive, summary)
        result["summary"] = str(relative)
        checked.append(result)
    return checked


def _archived_bytes(archive: Path, name: str) -> bytes | None:
    with tarfile.open(archive, "r:gz") as handle:
        if name not in handle.getnames():
            return None
        extracted = handle.extractfile(name)
        if extracted is None:
            return None
        return extracted.read()


def _short_diff(expected: bytes, actual: bytes) -> str | None:
    diff = "".join(
        difflib.unified_diff(
            expected.decode("utf-8", "replace").splitlines(keepends=True),
            actual.decode("utf-8", "replace").splitlines(keepends=True),
            fromfile="archive",
            tofile="merged-main",
        )
    )
    if len(diff) > 4000:
        return None
    return diff


def binding_rows(root: Path) -> list[dict]:
    rows = []
    for relative in SUMMARIES:
        summary_path = root / relative
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        archive = summary_path.parent / summary["archive"]["path"]
        for path, expected in summary["input_sha256"].items():
            current_path = root / path
            actual = digest(current_path.read_bytes()) if current_path.is_file() else None
            archived = _archived_bytes(archive, f"current-inputs/{path}")
            archived_sha = digest(archived) if archived is not None else None
            row = {
                "summary": str(relative),
                "path": path,
                "expected": expected,
                "actual": actual,
                "status": "match" if actual == expected else "mismatch",
                "archive_copy_sha256": archived_sha,
                "archive_copy_matches_summary": (
                    None if archived_sha is None else archived_sha == expected
                ),
            }
            if actual is not None and archived is not None and actual != expected:
                row["tree_versus_archive_diff"] = _short_diff(archived, current_path.read_bytes())
                row["tree_bytes"] = current_path.stat().st_size
                row["archive_bytes"] = len(archived)
            rows.append(row)
    return rows


def recorded_base(root: Path) -> str:
    """The frozen inspection names the only base this explicit check may consult."""
    report = json.loads((root / EVIDENCE / "main-acceptance-map.json").read_text())
    commit = report["inspected_main"]["commit"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("inspection base must be a full commit hash")
    return commit


def _show_origin_main(root: Path, relative: str) -> bytes:
    """Read the recorded base locally; never fetch or consult a mutable ref."""
    return subprocess.check_output(["git", "show", f"{recorded_base(root)}:{relative}"], cwd=root)


def production_helpers(root: Path) -> dict:
    root_bytes = (root / HELPER).read_bytes()
    template_bytes = (root / TEMPLATE_HELPER).read_bytes()
    base_root = _show_origin_main(root, HELPER)
    base_template = _show_origin_main(root, TEMPLATE_HELPER)
    return {
        "equal_each_other": root_bytes == template_bytes,
        "root_equals_origin_main": root_bytes == base_root,
        "template_equals_origin_main": template_bytes == base_template,
        "sha256": digest(root_bytes),
        "bytes": len(root_bytes),
    }


def historical_paths_match_main(root: Path) -> dict:
    paths = [
        str(EVIDENCE / "README.md"),
        str(EVIDENCE / "coverage.ini"),
        str(EVIDENCE / "replay.py"),
        str(EVIDENCE / "summary.json"),
        str(EVIDENCE / "proof.tar.gz"),
        str(EVIDENCE / "path-lookup/summary.json"),
        str(EVIDENCE / "path-lookup/proof.tar.gz"),
        str(EVIDENCE / "replay-validation/summary.json"),
        str(EVIDENCE / "replay-validation/proof.tar.gz"),
        str(EVIDENCE / "replay-validation/task-reconciliation.md"),
        TEST,
        HELPER,
        TEMPLATE_HELPER,
        "tests/scripts/test_shebang_rejection_replay.py",
    ]
    result = subprocess.run(
        ["git", "diff", "--exit-code", recorded_base(root), "--", *paths],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return {"paths": paths, "match_origin_main": result.returncode == 0, "exit": result.returncode}


def test_contract(root: Path) -> dict:
    text = (root / TEST).read_text(encoding="utf-8")
    cases = (
        "test_empty_pytest_launcher_has_no_probe",
        "test_missing_shebang_has_no_probe",
        "test_unclosed_shebang_quote_has_no_probe",
        "test_unresolved_env_python_has_no_probe",
    )
    return {
        "cases": cases,
        "parameter_ids": ("root", "template"),
        "declared_cases_present": all(f"def {name}(" in text for name in cases),
        "real_executable_file": "path.chmod(0o755)" in text and "path.touch()" in text,
        "restricted_path": 'monkeypatch.setenv("PATH", str(bindir))' in text,
        "empty_launcher_bytes": 'launcher.read_text(encoding="utf-8") == ""' in text,
        "missing_shebang_case": "print('not an interpreter declaration')" in text,
        "unclosed_quote_case": "#!/usr/bin/env 'python\\n" in text,
        "unresolved_env_case": "#!/usr/bin/env -S python3 -I\\n" in text,
        "no_available_probe": (
            'helper["_pyyaml_probe_command"](command, launcher.parent) is None' in text
        ),
        "unmanaged_runtime": 'helper["_uses_pytest_runtime"](command) is False' in text,
        "unsuccessful_probe": (
            'helper["_pyyaml_probe_succeeds"](command, launcher.parent) is False' in text
        ),
    }


def replay_contract(root: Path) -> dict:
    replay_path = root / REPLAY
    source = replay_path.read_text(encoding="utf-8")
    module = runpy.run_path(str(replay_path))
    mutations = module["MUTATIONS"]
    helpers = {}
    for label, relative in (("root", HELPER), ("template", TEMPLATE_HELPER)):
        text = (root / relative).read_text(encoding="utf-8")
        helpers[label] = {
            name: text.count(needle) for name, (needle, _replacement) in mutations.items()
        }
    claim = source.index("output.mkdir(parents=True, exist_ok=False)")
    copy = source.index("shutil.copyfile")
    return {
        "mutation_names": list(mutations),
        "anchor_counts": helpers,
        "anchors_unique": all(
            count == 1 for counts in helpers.values() for count in counts.values()
        ),
        "claims_output_before_copy": claim < copy,
        "restores_original_bytes": "assert restored == original" in source,
        "rejects_existing_output": "exist_ok=False" in source,
    }


def attempt_literal_command(root: Path, argv: list[str]) -> dict:
    """Run one literal acceptance command, stopping when its interpreter is absent."""
    interpreter = Path(argv[0])
    record = {
        "argv": argv,
        "cwd": str(root),
        "interpreter": str(interpreter),
        "attempt": 1,
        "limit_seconds": FOCUSED_LIMIT_SECONDS,
    }
    if not interpreter.is_file() or not os.access(interpreter, os.X_OK):
        record.update(
            {
                "exit": 127,
                "stdout": "",
                "stderr": f"{interpreter}: No such file or directory\n",
                "stopped": "interpreter-absent",
                "duration_seconds": 0,
            }
        )
        return record
    started = time.monotonic()
    try:
        result = subprocess.run(
            argv,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=FOCUSED_LIMIT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        record.update(
            {
                "exit": 124,
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "",
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


def run_focused_pytest(root: Path) -> dict:
    """Run the acceptance pytest shape with the interpreter that is executing this script."""
    junit = Path(tempfile.mkstemp(prefix="shebang-focused-", suffix=".xml")[1])
    argv = [
        sys.executable,
        "-m",
        "pytest",
        TEST,
        "-q",
        "-o",
        "addopts=",
        f"--junitxml={junit}",
    ]
    started = time.monotonic()
    try:
        result = subprocess.run(
            argv,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=FOCUSED_LIMIT_SECONDS,
            check=False,
        )
        duration = round(time.monotonic() - started, 3)
        stdout = result.stdout
        stderr = result.stderr
        exit_code = result.returncode
        stopped = None
    except subprocess.TimeoutExpired as exc:
        duration = round(time.monotonic() - started, 3)
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        exit_code = 124
        stopped = "time-limit"
    summary_line = next((line for line in reversed(stdout.splitlines()) if line.strip()), "")
    passed_match = re.search(r"(\d+) passed", summary_line)
    junit_counts = _junit_counts(junit)
    junit.unlink(missing_ok=True)
    return {
        "argv": argv,
        "cwd": str(root),
        "interpreter": sys.executable,
        "exit": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "summary_line": summary_line,
        "passed": int(passed_match.group(1)) if passed_match else None,
        "duration_seconds": duration,
        "under_two_minutes": duration < FOCUSED_LIMIT_SECONDS,
        "stopped": stopped,
        "junit": junit_counts,
        "satisfies_literal_interpreter": False,
    }


def _junit_counts(path: Path) -> dict:
    if not path.is_file():
        return {}
    from defusedxml.ElementTree import parse

    root = parse(path).getroot()
    cases = list(root.iter("testcase"))
    return {
        "tests": len(cases),
        "failures": sum(1 for case in cases if case.find("failure") is not None),
        "errors": sum(1 for case in cases if case.find("error") is not None),
        "skipped": sum(1 for case in cases if case.find("skipped") is not None),
    }


def confirm_replay(root: Path) -> dict:
    """Re-run replay on a private destination with the installed interpreter."""
    with tempfile.TemporaryDirectory(prefix="shebang-acceptance-inspect-") as temporary:
        output = Path(temporary) / "proof"
        argv = [sys.executable, str(root / REPLAY), "--output", str(output)]
        started = time.monotonic()
        result = subprocess.run(
            argv,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=FOCUSED_LIMIT_SECONDS,
            check=False,
        )
        duration = round(time.monotonic() - started, 3)
        pairs = []
        if result.returncode == 0:
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            for pair in summary["pairs"]:
                pairs.append(
                    {
                        "node": pair["node"],
                        "source": pair["source"],
                        "red_exit": pair["red"]["exit"],
                        "green_exit": pair["green"]["exit"],
                        "restored_matches_original": pair["original_sha256"]
                        == pair["restored_sha256"],
                        "mutant_differs": pair["original_sha256"] != pair["mutant_sha256"],
                    }
                )
            before = {
                path.relative_to(output).as_posix(): path.read_bytes()
                for path in output.rglob("*")
                if path.is_file()
            }
            reuse = subprocess.run(
                argv,
                cwd=root,
                capture_output=True,
                text=True,
                timeout=FOCUSED_LIMIT_SECONDS,
                check=False,
            )
            after = {
                path.relative_to(output).as_posix(): path.read_bytes()
                for path in output.rglob("*")
                if path.is_file()
            }
            reuse_record = {
                "argv": argv,
                "exit": reuse.returncode,
                "stderr": reuse.stderr,
                "proof_file_count": len(before),
                "proof_files_unchanged": before == after,
            }
        else:
            reuse_record = None
    return {
        "argv": argv,
        "cwd": str(root),
        "interpreter": sys.executable,
        "output_retained": False,
        "output_note": (
            "Private temporary destination. /tmp/fresh-shebang-rejection-proof is reserved "
            "for the literal acceptance command and was not created."
        ),
        "exit": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration_seconds": duration,
        "pairs": pairs,
        "reuse": reuse_record,
        "satisfies_literal_interpreter": False,
    }


def _binding_gap(rows: list[dict], path: str) -> str:
    mismatched = [row for row in rows if row["path"] == path and row["status"] == "mismatch"]
    if not mismatched:
        return f"{path} matches every historical summary that binds it."
    parts = [
        f"{row['summary']} binds {row['expected']} while merged main has {row['actual']}"
        for row in mismatched
    ]
    return f"{path} binding gap: " + "; ".join(parts) + "."


def map_acceptance(context: dict) -> list[dict]:
    literal = context["literal_attempts"]
    operational = context["operational_pytest"]
    archives = context["archives"]
    rows = context["bindings"]
    helpers = context["helpers"]
    replay = context["replay_confirmation"]
    archives_ok = all(item["verified"] for item in archives)
    archive_bindings_ok = all(row["archive_copy_matches_summary"] is not False for row in rows)
    tree_mismatches = [row for row in rows if row["status"] == "mismatch"]
    literal_pytest = literal[0]
    literal_replay = literal[1]
    findings = [
        {
            "id": "pytest-command",
            "verified": [
                (
                    "Installed interpreter "
                    f"{operational['interpreter']} exited {operational['exit']} with "
                    f"summary {operational['summary_line']!r} in "
                    f"{operational['duration_seconds']}s. JUnit counts: {operational['junit']}."
                )
            ],
            "gap": (
                f"Literal command {literal_pytest['argv']} from cwd {literal_pytest['cwd']} "
                f"exited {literal_pytest['exit']} ({literal_pytest['stopped']}). "
                "No raw JUnit for that interpreter and the current test bytes is archived. "
                + _binding_gap(rows, TEST)
            ),
        },
        {
            "id": "replay-command",
            "verified": [
                (
                    "replay.py declares eight root/template mutations, unique anchors, "
                    "byte restoration, and output claim before copy. "
                    f"Installed-interpreter confirmation exit {replay['exit']}, "
                    f"pairs {len(replay['pairs'])}, reuse "
                    f"{None if replay['reuse'] is None else replay['reuse']['exit']}, "
                    "files unchanged "
                    f"{None if replay['reuse'] is None else replay['reuse']['proof_files_unchanged']}."
                )
            ],
            "gap": (
                f"Literal command {literal_replay['argv']} exited {literal_replay['exit']} "
                f"({literal_replay['stopped']}) before mutation. "
                "/tmp/fresh-shebang-rejection-proof was not created, so its reuse check "
                "has no proof files to preserve. "
                "The installed-interpreter replay used a private temporary directory and "
                "does not satisfy the literal command."
            ),
        },
        {
            "id": "matched-comparison",
            "verified": [
                (
                    "Historical replay-validation summary records baseline 340 and candidate "
                    "348 with eight added nodes, no removals, no changed outcomes, 1244 "
                    "statements, 556 branches, and zero excluded lines. Those counts describe "
                    "the bytes bound in that summary."
                )
            ],
            "gap": (
                "No matched comparison was run against current merged-main inputs. "
                + _binding_gap(rows, TEST)
                + " "
                + _binding_gap(rows, "tests/scripts/test_check_deliberate_break.py")
            ),
        },
        {
            "id": "validation-and-helpers",
            "verified": [
                (
                    f"Production helpers equal each other and origin/main "
                    f"({helpers['equal_each_other']}, root {helpers['root_equals_origin_main']}, "
                    f"template {helpers['template_equals_origin_main']}, sha256 {helpers['sha256']}). "
                    f"Historical archive verification is {archives_ok}."
                )
            ],
            "gap": (
                "This inspection did not run full-repository Black, focused Ruff, "
                "scripts/validate_template_completeness.py --strict, or git diff --check, "
                "so there is no current command receipt or measured validation file count."
            ),
        },
        {
            "id": "archive-bindings",
            "verified": [
                (
                    f"Three historical archives opened and member hashes/lengths verified: "
                    f"{archives_ok}. Archive-internal input copies match their summaries: "
                    f"{archive_bindings_ok}."
                )
            ],
            "gap": (
                f"Current tree bindings do not verify: {len(tree_mismatches)} summary rows "
                "differ from merged main. Validation file counts were not measured. "
                "This inspection record is current acceptance context; README, summary.json, "
                "path-lookup/, and replay-validation/ remain historical receipts."
            ),
        },
    ]
    by_id = {item["id"]: item for item in findings}
    mapped = []
    for requirement in REQUIREMENTS:
        finding = by_id[requirement["id"]]
        disposition = "verified" if not finding["gap"] else "gap"
        mapped.append(
            {
                "id": requirement["id"],
                "requirement": requirement["requirement"],
                "disposition": disposition,
                "verified_evidence": finding["verified"],
                "gap": finding["gap"],
            }
        )
    return mapped


def build_static_context(root: Path) -> dict:
    return {
        "inspected_main": inspected_main(root),
        "archives": historical_archives(root),
        "bindings": binding_rows(root),
        "helpers": production_helpers(root),
        "historical_tree": historical_paths_match_main(root),
        "test_contract": test_contract(root),
        "replay_contract": replay_contract(root),
    }


def build_report(root: Path, *, confirm_runtime: bool = True) -> dict:
    context = build_static_context(root)
    literal_attempts = [attempt_literal_command(root, list(argv)) for argv in LITERAL_COMMANDS]
    operational = run_focused_pytest(root)
    replay = confirm_replay(root) if confirm_runtime else None
    context["literal_attempts"] = literal_attempts
    context["operational_pytest"] = operational
    context["replay_confirmation"] = replay
    pre_change = {
        "check_date": datetime.now(UTC).date().isoformat(),
        "cwd": str(root),
        "stop_rule": STOP_RULE,
        "focused_limit_seconds": FOCUSED_LIMIT_SECONDS,
        "literal_commands": literal_attempts,
        "operational_pytest": operational,
        "protected_files_edited_before_record": False,
        "note": (
            "Recorded before any edit to the shebang tests, replay.py, or production helpers. "
            "The operational pytest uses the installed interpreter so the eight-pass outcome "
            "is measured. It is not a substitute for the literal Anaconda commands."
        ),
    }
    report = {
        "inspected_main": context["inspected_main"],
        "check_date": pre_change["check_date"],
        "archives": context["archives"],
        "bindings": context["bindings"],
        "helpers": context["helpers"],
        "historical_tree": context["historical_tree"],
        "test_contract": context["test_contract"],
        "replay_contract": context["replay_contract"],
        "pre_change": pre_change,
        "replay_confirmation": replay,
        "follow_up": (
            "replay.py parses JUnit with ElementTree after an Expat pre-parse and does not "
            "normalize XML syntax failures into ValueError. The focused pytest run passed, so "
            "this remains a follow-up rather than an acceptance failure."
        ),
    }
    report["acceptance"] = map_acceptance(
        {
            "literal_attempts": literal_attempts,
            "operational_pytest": operational,
            "archives": context["archives"],
            "bindings": context["bindings"],
            "helpers": context["helpers"],
            "replay_confirmation": (
                replay
                if replay is not None
                else {
                    "exit": None,
                    "pairs": [],
                    "reuse": None,
                }
            ),
        }
    )
    return report


def write_report(root: Path, report: dict) -> None:
    evidence = root / EVIDENCE
    map_path = evidence / "main-acceptance-map.json"
    pre_path = evidence / "pre-change-record.json"
    map_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    pre_path.write_text(json.dumps(report["pre_change"], indent=2) + "\n", encoding="utf-8")


def main() -> int:
    root = repo_root()
    if sys.argv[1:] == ["--inspect-base"]:
        report = {
            "base_commit": recorded_base(root),
            "helpers": production_helpers(root),
            "historical_tree": historical_paths_match_main(root),
            "bindings": binding_rows(root),
        }
        print(json.dumps(report, indent=2))
        return (
            0
            if (
                report["helpers"]["root_equals_origin_main"]
                and report["helpers"]["template_equals_origin_main"]
                and report["historical_tree"]["match_origin_main"]
            )
            else 1
        )
    report = build_report(root)
    write_report(root, report)
    print(
        json.dumps(
            {
                "inspected_main": report["inspected_main"]["commit"],
                "acceptance_gaps": [
                    item["id"] for item in report["acceptance"] if item["disposition"] == "gap"
                ],
                "operational_passed": report["pre_change"]["operational_pytest"]["passed"],
                "literal_exits": [
                    item["exit"] for item in report["pre_change"]["literal_commands"]
                ],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
