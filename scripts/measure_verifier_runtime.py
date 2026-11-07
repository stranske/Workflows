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


def prepare(repo: Path, output: Path) -> None:
    # Refuse reuse: neither pytest caches nor outputs from a prior run are admissible.
    output.mkdir(parents=True, exist_ok=False)
    arms = {}
    for arm, ref in (("baseline", BASELINE), ("candidate", CANDIDATE)):
        target = output / arm
        target.mkdir()
        archive = git(repo, "archive", ref)
        extract_source(archive, target)
        arms[arm] = {
            "commit": git(repo, "rev-parse", ref).decode().strip(),
            "tree": git(repo, "rev-parse", f"{ref}^{{tree}}").decode().strip(),
            "sha256": {
                name: sha(target / name)
                for name in (*SUITES, VERIFIER, "pyproject.toml", "requirements.lock")
            },
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


def packages() -> list[dict]:
    return json.loads(
        subprocess.check_output([sys.executable, "-m", "pip", "list", "--format=json"])
    )


def run(output: Path) -> int:
    from defusedxml.common import DefusedXmlException

    manifest = json.loads((output / "manifest.json").read_text())
    initial_packages = packages()
    order = ["baseline", "candidate"] if sys.version_info.minor == 12 else ["candidate", "baseline"]
    result = {
        "manifest": manifest,
        "python": sys.version,
        "platform": platform.platform(),
        "packages": initial_packages,
        "order": order,
        "arms": {},
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
        if (arm / "pytest-junit.xml").is_file():
            try:
                row["junit"] = junit(arm / "pytest-junit.xml")
            except (OSError, ValueError, ParseError, DefusedXmlException) as exc:
                row["junit_error"] = f"JUnit outcomes UNKNOWN: {type(exc).__name__}"
        result["arms"][name] = row
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    result["packages_unchanged"] = initial_packages == packages()
    result["outcome_comparison"] = outcome_comparison(result["arms"])
    result["timing_comparison"] = timing_comparison(result["arms"])
    coverage_files = [output / name / "coverage.json" for name in ("baseline", "candidate")]
    result["verifier_coverage"] = None
    try:
        result["verifier_coverage"] = coverage_comparison(
            *(json.loads(p.read_text()) for p in coverage_files)
        )
    except (OSError, ValueError) as exc:
        result["coverage_error"] = f"Verifier coverage UNKNOWN: {type(exc).__name__}"
    result["artifact_sha256"] = {
        str(p.relative_to(output)): sha(p)
        for p in output.rglob("*")
        if p.is_file()
        and p.name in {"coverage.json", "pytest-junit.xml", "baseline.log", "candidate.log"}
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
        or coverage is None
        or bool(coverage["lost_lines"] or coverage["lost_branches"])
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "run"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if args.mode == "prepare":
        prepare(Path.cwd(), output)
        return 0
    return run(output)


if __name__ == "__main__":
    raise SystemExit(main())
