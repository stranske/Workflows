#!/usr/bin/env python3
"""Finite, manual #3904 comparison; never changes production gates or source refs."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import platform
import re
import subprocess
import sys
import tarfile
import time
import tomllib
from pathlib import Path
from xml.etree.ElementTree import ParseError

BASELINE = "2f9eb2de718d1a561bce6fc0bff46fe8b9867905"
CANDIDATE = "999ffe5fa00ac9c8ae8a807447f053277032b670"
SUITES = (
    "tests/scripts/test_pr_verifier_delivery_destinations.py",
    "tests/scripts/test_pr_verifier_prompt_coverage.py",
    "tests/scripts/test_pr_verifier_body_overall_integration.py",
)
VERIFIER = "scripts/langchain/pr_verifier.py"
SOURCE_INPUTS = (*SUITES, VERIFIER, "pyproject.toml", "requirements.lock")

# External to both immutable arms; each process records only its own clock.
PHASE_PLUGIN = r"""import json
import os
import time
from pathlib import Path

import pytest

_clocks = {}
_role = None


def _mark(name):
    _clocks[name] = time.monotonic()


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_sessionstart(session):
    global _role
    _role = getattr(session.config, "workerinput", {}).get("workerid", "controller")
    _mark("session_start")
    yield


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_collection(session):
    _mark("collection_start")
    yield
    _mark("collection_end")


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtestloop(session):
    _mark("loop_start")
    yield
    _mark("loop_end")


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_sessionfinish(session, exitstatus):
    _mark("reporting_start")
    yield
    _mark("reporting_end")
    _mark("session_end")
    directory = Path(os.environ["VERIFIER_PHASE_DIR"])
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{_role}.json").write_text(json.dumps({
        "role": _role, "pid": os.getpid(), "clock": "time.monotonic",
        "boundaries": _clocks,
    }, indent=2) + "\n")
"""


def _write_phase_plugin(tmpdir: Path) -> Path:
    plugin_dir = tmpdir / "phase_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "verifier_phase_probe.py").write_text(PHASE_PLUGIN)
    return plugin_dir


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args])


def extract_source(archive: bytes, target: Path) -> None:
    """Materialize regular Git source files only; refuse links and path escapes."""
    root = target.resolve()
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar:
            path = (root / member.name).resolve()
            if not path.is_relative_to(root):
                raise ValueError("Archive member escapes its source arm")
            if member.isdir():
                path.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                path.parent.mkdir(parents=True, exist_ok=True)
                stream = tar.extractfile(member)
                if stream is None:
                    raise ValueError("Archive regular file has no content")
                with stream:
                    path.write_bytes(stream.read())
                path.chmod(member.mode & 0o777)
            else:
                raise ValueError("Archive source links and special files are unsupported")


def prepare(
    repo: Path, output: Path, *, baseline: str | None = None, candidate: str | None = None
) -> None:
    refs = (
        ("baseline", BASELINE if baseline is None else baseline),
        ("candidate", CANDIDATE if candidate is None else candidate),
    )
    # Validate both inputs before Git or output creation. A branch, abbreviation,
    # tag object or revision expression cannot identify an immutable source arm.
    if any(re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", ref) is None for _, ref in refs):
        raise ValueError("Source selection requires full lowercase hexadecimal commit IDs")
    for _, ref in refs:
        if git(repo, "cat-file", "-t", ref).strip() != b"commit":
            raise ValueError("Source object must be a commit")
    # Refuse reuse: neither pytest caches nor outputs from a prior run are admissible.
    output.mkdir(parents=True, exist_ok=False)
    arms = {}
    for arm, ref in refs:
        target = output / arm
        target.mkdir()
        archive = git(repo, "archive", ref)
        extract_source(archive, target)
        arms[arm] = {
            "commit": git(repo, "rev-parse", ref).decode().strip(),
            "tree": git(repo, "rev-parse", f"{ref}^{{tree}}").decode().strip(),
            "sha256": {name: sha(target / name) for name in SOURCE_INPUTS},
        }
    baseline, candidate = output / "baseline", output / "candidate"
    if (baseline / VERIFIER).read_bytes() != (candidate / VERIFIER).read_bytes():
        raise ValueError("Production verifier bytes differ; line/arc comparison is not admissible")
    for section in ("coverage", "pytest"):
        before = tomllib.loads((baseline / "pyproject.toml").read_text())["tool"][section]
        after = tomllib.loads((candidate / "pyproject.toml").read_text())["tool"][section]
        if before != after:
            raise ValueError(f"{section} configurations differ")
    manifest = {
        "arms": arms,
        "harness_sha256": sha(Path(__file__)),
        "workflow_sha": os.environ.get("GITHUB_SHA"),
        "workflow_sha256": sha(repo / ".github/workflows/maint-88-verifier-runtime-comparison.yml"),
        "dependency_lock": "candidate/requirements.lock",
        "cache_policy": "No actions/cache or artifact restore; fresh arm directories, pytest cache provider disabled, bytecode writes disabled. OS page cache is uncontrolled; arm order is recorded in result.json (baseline first on Python 3.12, candidate first otherwise), not within-version replicated.",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def command() -> list[str]:
    return [
        sys.executable,
        "-m",
        "pytest",
        *SUITES,
        "-m",
        "not quarantine and not slow",
        "-n",
        "4",
        "--dist=loadgroup",
        "-p",
        "no:cacheprovider",
        "-p",
        "no:rerunfailures",
        "-p",
        "verifier_phase_probe",
        "--cov",
        "--cov-config=pyproject.toml",
        "--cov-report=json:coverage.json",
        "--cov-report=xml:coverage.xml",
        "--cov-report=term-missing",
        "--junitxml=pytest-junit.xml",
        "--durations=25",
        "-q",
    ]


def junit(path: Path) -> dict:
    """Retain outcomes independently of complete, finite JUnit worker timings."""
    from defusedxml import ElementTree as ET

    root = ET.parse(path).getroot()
    suites = list(root.iter("testsuite"))
    by_file = {}
    for case in root.iter("testcase"):
        key = case.get("classname", "")
        row = by_file.setdefault(
            key,
            {
                "cases": 0,
                "worker_seconds": 0.0,
                "timed_cases": 0,
                "untimed_cases": 0,
                "passed": 0,
                "failures": 0,
                "errors": 0,
                "skipped": 0,
            },
        )
        row["cases"] += 1
        raw = case.get("time")
        try:
            seconds = float(raw) if raw is not None else None
        except ValueError:
            seconds = None
        if seconds is None or not math.isfinite(seconds) or seconds < 0:
            row["untimed_cases"] += 1
        else:
            row["timed_cases"] += 1
            row["worker_seconds"] += seconds
        outcomes = [
            label
            for tag, label in (("failure", "failures"), ("error", "errors"), ("skipped", "skipped"))
            if case.find(tag) is not None
        ]
        if len(outcomes) > 1:
            raise ValueError("JUnit case has conflicting outcomes")
        row[outcomes[0] if outcomes else "passed"] += 1
    for row in by_file.values():
        complete = row["untimed_cases"] == 0 and math.isfinite(row["worker_seconds"])
        row["timing_status"] = "KNOWN" if complete else "UNKNOWN"
        if not complete:
            row["worker_seconds"] = None
    # A well-formed but truncated XML document can still contain passing cases
    # in all three scoped suites. Reconcile every declared container total with
    # its descendant cases before accepting either outcomes or worker time.
    for container in root.iter():
        if container.tag not in ("testsuite", "testsuites"):
            continue
        cases = list(container.iter("testcase"))
        observed = {"tests": len(cases)}
        observed.update(
            (attribute, sum(case.find(tag) is not None for case in cases))
            for attribute, tag in (
                ("failures", "failure"),
                ("errors", "error"),
                ("skipped", "skipped"),
            )
        )
        for attribute, count in observed.items():
            declared = container.get(attribute)
            if declared is None:
                continue
            if not declared.isascii() or not declared.isdecimal() or int(declared) != count:
                raise ValueError(f"JUnit {container.tag} {attribute} total disagrees with cases")
    return {"suites": [s.attrib for s in suites], "per_file": by_file}


def outcome_comparison(arms: dict) -> dict:
    """Require actual passing cases in all scoped suites, independently of exit status.

    Case totals may differ because this experiment reduces parametrized rows.
    Missing receipts, skipped checks and reported failures cannot certify that
    both arms successfully exercised the three suites.
    """
    gaps = []
    for arm in ("baseline", "candidate"):
        receipt = arms[arm].get("junit")
        if receipt is None:
            gaps.append(f"{arm} JUnit outcomes UNKNOWN")
            continue
        for suite in SUITES:
            row = receipt["per_file"].get(suite[:-3].replace("/", "."))
            if row is None or row["cases"] == 0:
                gaps.append(f"{arm} {suite} has no observed cases")
            elif row["failures"] or row["errors"] or row["skipped"]:
                gaps.append(f"{arm} {suite} has non-passing outcomes")
    return {"successful": not gaps, "gaps": gaps}


def timing_comparison(arms: dict) -> dict:
    """Require measured scoped worker time without inferring hosted phase control."""
    gaps = []
    for arm in ("baseline", "candidate"):
        receipt = arms[arm].get("junit")
        if receipt is None:
            gaps.append(f"{arm} JUnit timing UNKNOWN")
            continue
        for suite in SUITES:
            row = receipt["per_file"].get(suite[:-3].replace("/", "."))
            if row is None or row["cases"] == 0 or row["timing_status"] != "KNOWN":
                gaps.append(f"{arm} {suite} JUnit worker time UNKNOWN")
    return {"available": not gaps, "gaps": gaps}


def _coverage_entry(report: dict, arm: str) -> dict:
    meta = report.get("meta") if isinstance(report, dict) else None
    if not isinstance(meta, dict) or meta.get("branch_coverage") is not True:
        raise ValueError(f"{arm} branch coverage is not explicitly enabled in the receipt")
    files = report.get("files") if isinstance(report, dict) else None
    entry = files.get(VERIFIER) if isinstance(files, dict) else None
    if isinstance(entry, dict):
        lines, branches = entry.get("executed_lines"), entry.get("executed_branches")
        if (
            isinstance(lines, list)
            and all(type(line) is int and line > 0 for line in lines)
            and isinstance(branches, list)
            and all(
                isinstance(pair, list)
                and len(pair) == 2
                and all(type(node) is int and node != 0 for node in pair)
                for pair in branches
            )
        ):
            return entry
    raise ValueError(f"{arm} verifier coverage has missing or invalid executed-line/branch lists")


def coverage_comparison(before: dict, after: dict) -> dict:
    a, b = _coverage_entry(before, "baseline"), _coverage_entry(after, "candidate")
    return {
        "lost_lines": sorted(set(a["executed_lines"]) - set(b["executed_lines"])),
        "lost_branches": sorted(
            set(map(tuple, a["executed_branches"])) - set(map(tuple, b["executed_branches"]))
        ),
        "baseline_lines": len(a["executed_lines"]),
        "candidate_lines": len(b["executed_lines"]),
        "baseline_branches": len(a["executed_branches"]),
        "candidate_branches": len(b["executed_branches"]),
    }


def execution_phases(arm: Path) -> dict:
    """Read local process intervals, never subtract overlapping process clocks."""
    processes, gaps = {}, []
    for role in ("controller", "gw0", "gw1", "gw2", "gw3"):
        try:
            receipt = json.loads((arm / "phase-clocks" / f"{role}.json").read_text())
            if receipt["role"] != role or receipt["clock"] != "time.monotonic":
                raise ValueError("clock identity mismatch")
            clocks = receipt["boundaries"]
            if not isinstance(clocks, dict):
                raise ValueError("missing boundaries")
        except (OSError, ValueError, KeyError, TypeError):
            clocks = {}
        intervals = {}
        for label, prefix in (
            ("session", "session"),
            ("collection", "collection"),
            ("controller_worker_loop", "loop"),
            ("reporting", "reporting"),
        ):
            start, end = clocks.get(f"{prefix}_start"), clocks.get(f"{prefix}_end")
            valid = all(
                type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in (start, end)
            )
            if valid and end >= start:
                intervals[label] = {"start": start, "end": end, "seconds": end - start}
            else:
                intervals[label] = None
                gaps.append(f"{role} {label} UNKNOWN")
        processes[role] = intervals
    return {
        "available": not gaps,
        "gaps": gaps,
        "processes": processes,
        "overlap_note": "Controller session and loop overlap worker sessions and collection; "
        "worker intervals overlap each other. Session includes reporting. "
        "Reporting measures pytest_sessionfinish hooks (coverage/JUnit/terminal), "
        "not all per-test report handling. No intervals are additive across "
        "processes; startup, teardown outside hooks and exclusive overhead are UNKNOWN.",
    }


def packages() -> list[dict]:
    return json.loads(
        subprocess.check_output([sys.executable, "-m", "pip", "list", "--format=json"])
    )


def source_integrity(output: Path, manifest: dict) -> dict:
    """Recheck the prepared inputs; neither stale hashes nor missing inputs prove identity."""
    gaps, observed = [], {}
    arms = manifest.get("arms")
    arms = arms if isinstance(arms, dict) else {}
    for arm in ("baseline", "candidate"):
        record = arms.get(arm)
        expected = record.get("sha256") if isinstance(record, dict) else None
        expected = expected if isinstance(expected, dict) else {}
        observed[arm] = {}
        for name in SOURCE_INPUTS:
            try:
                digest = sha(output / arm / name)
            except OSError:
                digest = None
            observed[arm][name] = digest
            if digest is None:
                gaps.append(f"{arm} {name} source bytes UNKNOWN")
            elif name not in expected:
                gaps.append(f"{arm} {name} prepared hash UNKNOWN")
            elif digest != expected[name]:
                gaps.append(f"{arm} {name} differs from prepared source")
    return {"verified": not gaps, "gaps": gaps, "sha256": observed}


def run(output: Path) -> int:
    from defusedxml.common import DefusedXmlException

    manifest = json.loads((output / "manifest.json").read_text())
    integrity = {"before": source_integrity(output, manifest)}
    integrity["verified"] = integrity["before"]["verified"]
    if not integrity["verified"]:
        result = {
            "manifest": manifest,
            "source_integrity": integrity,
            "arms": {},
            "verifier_coverage": None,
            "outcome_comparison": {"successful": False, "gaps": ["source integrity not verified"]},
            "timing_comparison": {"available": False, "gaps": ["source integrity not verified"]},
        }
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({"result": str(output / "result.json"), "source_integrity": integrity}))
        return 1
    initial_packages = packages()
    order = ["baseline", "candidate"] if sys.version_info.minor == 12 else ["candidate", "baseline"]
    result = {
        "manifest": manifest,
        "python": sys.version,
        "platform": platform.platform(),
        "packages": initial_packages,
        "order": order,
        "arms": {},
        "source_integrity": integrity,
        "phase_plugin_sha256": hashlib.sha256(PHASE_PLUGIN.encode()).hexdigest(),
    }
    for name in order:
        arm = output / name
        # Keep the same environment and absolute interpreter; only source checkout differs.
        env = os.environ.copy()
        env.pop("PYTEST_ADDOPTS", None)
        env["PYTHONPATH"] = str(arm)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["TMPDIR"] = str(output / f"tmp-{name}")
        Path(env["TMPDIR"]).mkdir(exist_ok=False)
        plugin_dir = _write_phase_plugin(output / f"tmp-{name}")
        env["PYTHONPATH"] = f"{plugin_dir}:{arm}"
        env["VERIFIER_PHASE_DIR"] = str(arm / "phase-clocks")
        started = time.perf_counter()
        with (output / f"{name}.log").open("w") as console:
            proc = subprocess.run(
                command(),
                cwd=arm,
                env=env,
                stdout=console,
                stderr=subprocess.STDOUT,
                check=False,
            )
        row = {
            "command": command(),
            "exit_code": proc.returncode,
            "wall_seconds": time.perf_counter() - started,
        }
        row["phases"] = execution_phases(arm)
        if (arm / "pytest-junit.xml").is_file():
            try:
                row["junit"] = junit(arm / "pytest-junit.xml")
            except (OSError, ValueError, ParseError, DefusedXmlException) as exc:
                row["junit_error"] = f"JUnit outcomes UNKNOWN: {type(exc).__name__}"
        result["arms"][name] = row
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    integrity["after"] = source_integrity(output, manifest)
    integrity["verified"] = integrity["before"]["verified"] and integrity["after"]["verified"]
    result["packages_unchanged"] = initial_packages == packages()
    result["outcome_comparison"] = outcome_comparison(result["arms"])
    result["timing_comparison"] = timing_comparison(result["arms"])
    coverage_files = [output / name / "coverage.json" for name in ("baseline", "candidate")]
    result["verifier_coverage"] = None
    try:
        if not integrity["verified"]:
            raise ValueError("prepared source integrity changed")
        result["verifier_coverage"] = coverage_comparison(
            *(json.loads(p.read_text()) for p in coverage_files)
        )
    except (OSError, ValueError) as exc:
        result["coverage_error"] = f"Verifier coverage UNKNOWN: {type(exc).__name__}"
        if not integrity["verified"]:
            result["coverage_error"] += "; prepared source integrity changed"
    result["artifact_sha256"] = {
        str(p.relative_to(output)): sha(p)
        for p in output.rglob("*")
        if p.is_file()
        and p.name
        in {
            "coverage.json",
            "coverage.xml",
            "pytest-junit.xml",
            "baseline.log",
            "candidate.log",
            "controller.json",
            "gw0.json",
            "gw1.json",
            "gw2.json",
            "gw3.json",
        }
        and not any(part.startswith("tmp-") for part in p.relative_to(output).parts)
    }
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "result": str(output / "result.json"),
                "order": order,
                "exit_codes": {k: v["exit_code"] for k, v in result["arms"].items()},
                "coverage": result.get("verifier_coverage"),
                "outcomes": result["outcome_comparison"],
                "timing": result["timing_comparison"],
                "source_integrity_verified": integrity["verified"],
            },
            indent=2,
        )
    )
    coverage = result.get("verifier_coverage")
    return int(
        any(row["exit_code"] for row in result["arms"].values())
        or not result["outcome_comparison"]["successful"]
        or not result["timing_comparison"]["available"]
        or not result["packages_unchanged"]
        or not integrity["verified"]
        or coverage is None
        or bool(coverage["lost_lines"] or coverage["lost_branches"])
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "run"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", help="Full immutable baseline commit ID (prepare only)")
    parser.add_argument("--candidate", help="Full immutable candidate commit ID (prepare only)")
    args = parser.parse_args()
    if (args.baseline is not None or args.candidate is not None) and (
        args.mode != "prepare" or args.baseline is None or args.candidate is None
    ):
        parser.error("source selection requires prepare and both --baseline and --candidate")
    output = args.output.resolve()
    if args.mode == "prepare":
        prepare(Path.cwd(), output, baseline=args.baseline, candidate=args.candidate)
        return 0
    return run(output)


if __name__ == "__main__":
    raise SystemExit(main())
