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
import tempfile
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

# Growth plugin source embedded for phase timing measurement
GROWTH_PLUGIN = '''# Phase timing plugin - identical to reusable workflow ci_test_growth hooks
if True:
    import json
    import os
    import re
    import sys
    import time
    from collections import Counter
    from pathlib import Path

    import pytest

    _started = time.monotonic()
    _ids = None
    _collection_failed = False
    _collection_seconds = None
    _resources = None
    _expected_workers = 0

    def _resource_start(config):
        global _resources
        try:
            import platform
            import resource
            import subprocess

            directory = os.environ.get("CI_TEST_RESOURCE_DIR")
            if not directory:
                return
            usage = resource.getrusage(resource.RUSAGE_SELF)
            worker = getattr(config, "workerinput", {}).get("workerid", "controller")
            if not isinstance(worker, str) or re.fullmatch(r"controller|gw[0-9]+", worker) is None:
                _resources = None
                return
            owner_path = Path(directory) / "owner.json"
            if worker == "controller":
                import uuid
                owner_token = uuid.uuid4().hex
                try:
                    owner_path.write_text(json.dumps({"token": owner_token, "pid": os.getpid()}), encoding="utf-8")
                except OSError:
                    _resources = None
                    return
                _resources = {
                    "controller": {
                        "workerid": "controller",
                        "python": sys.version,
                        "start": time.monotonic(),
                        "pid": os.getpid(),
                        "cpu_model": _cpu_model(),
                        "cache": _cache_info(),
                        "elapsed_seconds": None,
                        "coverage": {},
                    },
                    "workers": [],
                    "status": "started",
                    "expected_workers": 0,
                    "missing_workers": [],
                    "context": {
                        "tested_sha": _git_sha(),
                    },
                    "source": "pytest xdist controller",
                }
            else:
                try:
                    owner = json.loads(owner_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError, ValueError):
                    _resources = None
                    return
                _resources = {
                    "controller": None,
                    "workers": [],
                    "status": "worker",
                    "expected_workers": 0,
                    "missing_workers": [],
                    "context": {},
                    "source": "pytest xdist worker",
                }
        except Exception:
            _resources = None

    def _cpu_model():
        try:
            if platform.system() == "Linux":
                with open("/proc/cpuinfo", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("model name"):
                            return line.split(":", 1)[1].strip()
            return platform.processor() or ""
        except Exception:
            return ""

    def _cache_info():
        try:
            lines = subprocess.check_output(["free", "-b"]).decode().splitlines()
            mem = None
            swap = None
            for line in lines:
                if line.startswith("Mem:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        mem = int(parts[1])
                elif line.startswith("Swap:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        swap = int(parts[1])
            if mem is not None or swap is not None:
                return {"memory_bytes": mem, "swap_bytes": swap}
        except Exception:
            pass
        return {}

    def _git_sha():
        try:
            return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path.cwd()).decode().strip()
        except Exception:
            return ""

    def _resource_coverage(config):
        if _resources is None or not isinstance(_resources, dict):
            return
        try:
            controller = _resources.get("controller")
            if controller is None or not isinstance(controller, dict):
                return
            coverage = controller.get("coverage")
            if not isinstance(coverage, dict):
                return
            cov_path = Path(config.getini("addopts")).parent / "coverage.json"
            if not cov_path.is_file():
                for prefix in [Path.cwd(), Path.cwd().parent]:
                    candidate = prefix / "coverage.json"
                    if candidate.is_file():
                        cov_path = candidate
                        break
            if not cov_path.is_file():
                return
            try:
                cov_data = json.loads(cov_path.read_text(encoding="utf-8"))
                files = cov_data.get("files") if isinstance(cov_data, dict) else None
                if not isinstance(files, dict):
                    return
                for verifier in ["scripts/langchain/pr_verifier.py", "scripts/langchain/pr_verifier.py"]:
                    if verifier in files:
                        controller["coverage"] = {
                            "verifier_lines": len(files[verifier].get("executed_lines", [])),
                            "verifier_branches": len(files[verifier].get("executed_branches", [])),
                        }
                        return
                controller["coverage"] = {"status": "verifier not found in coverage"}
            except Exception:
                controller["coverage"] = {"error": "coverage read failure"}
        except Exception:
            pass

    def _resource_finish():
        if _resources is None or not isinstance(_resources, dict):
            return
        try:
            controller = _resources.get("controller")
            if controller is not None and isinstance(controller, dict):
                controller["elapsed_seconds"] = round(time.monotonic() - controller.get("start", time.monotonic()), 3)
                _resources["status"] = "finished"
                directory = os.environ.get("CI_TEST_RESOURCE_DIR")
                if directory:
                    path = Path(directory) / "pytest-resources.json"
                    try:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(json.dumps(_resources, indent=2), encoding="utf-8")
                    except OSError:
                        pass
        except Exception:
            pass

    def _record(ids):
        paths = Counter(node.split("::", 1)[0] for node in ids)
        functions = Counter(node.split("[", 1)[0] for node in ids)
        Path("pytest-collection.json").write_text(
            json.dumps({
                "total": len(ids),
                "per_file": dict(paths),
                "largest_functions": functions.most_common(10),
                "collection_seconds": _collection_seconds,
                "complete": True,
                "source": "selected pytest node IDs; controller collection",
            }, indent=2),
            encoding="utf-8",
        )

    @pytest.hookimpl(wrapper=True, tryfirst=True)
    def pytest_sessionstart(session):
        _resource_start(session.config)
        if not hasattr(session.config, "workerinput"):
            Path("pytest-collection.json").unlink(missing_ok=True)
        yield
        _resource_coverage(session.config)

    def pytest_collectreport(report):
        global _collection_failed
        if report.failed:
            _collection_failed = True

    @pytest.hookimpl(optionalhook=True)
    def pytest_xdist_node_collection_finished(node, ids):
        global _ids, _collection_failed, _collection_seconds
        if _ids is None:
            _ids = tuple(ids)
            _collection_seconds = round(time.monotonic() - _started, 3)
        elif _ids != tuple(ids):
            _collection_failed = True

    def pytest_collection_finish(session):
        global _collection_seconds
        _resource_coverage(session.config)
        if hasattr(session.config, "workerinput") or getattr(session.config.option, "numprocesses", 0):
            return
        if not _collection_failed and not session.testsfailed:
            _collection_seconds = round(time.monotonic() - _started, 3)
            _record([item.nodeid for item in session.items])

    def pytest_sessionfinish(session, exitstatus):
        _resource_finish()
        if hasattr(session.config, "workerinput"):
            return
        if exitstatus in (pytest.ExitCode.INTERRUPTED, pytest.ExitCode.INTERNAL_ERROR, pytest.ExitCode.USAGE_ERROR):
            Path("pytest-collection.json").unlink(missing_ok=True)
        elif _ids is not None and not _collection_failed:
            _record(_ids)
'''


def _write_growth_plugin(tmpdir: Path) -> Path:
    """Write the growth plugin to a temp directory and return the plugin path."""
    plugin_dir = tmpdir / "growth_plugin"
    plugin_dir.mkdir(exist_ok=True)
    plugin_path = plugin_dir / "ci_test_growth.py"
    plugin_path.write_text(GROWTH_PLUGIN)
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
        "ci_test_growth",
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
    """Measure collection, controller/worker and reporting phase boundaries.

    Returns per-arm phase timing from growth plugin outputs, or null values
    for missing/unavailable measurements. Overlap between controller and
    workers is explicit: the controller elapsed time includes both collection
    and reporting, and worker times are independent concurrent measurements.
    """
    collection_path = arm / "pytest-collection.json"
    resources_path = arm / "pytest-resources.json"

    collection = None
    resources = None

    if collection_path.is_file():
        try:
            with collection_path.open() as f:
                collection = json.load(f)
        except (OSError, json.JSONDecodeError, ValueError):
            collection = None

    if resources_path.is_file():
        try:
            with resources_path.open() as f:
                resources = json.load(f)
        except (OSError, json.JSONDecodeError, ValueError):
            resources = None

    if not isinstance(collection, dict):
        collection = None
    if not isinstance(resources, dict):
        resources = None

    collection_seconds = collection.get("collection_seconds") if collection else None
    if collection_seconds is not None:
        try:
            collection_seconds = float(collection_seconds)
            if not math.isfinite(collection_seconds) or collection_seconds < 0:
                collection_seconds = None
        except (TypeError, ValueError):
            collection_seconds = None

    controller = resources.get("controller") if resources else None
    controller = controller if isinstance(controller, dict) else None
    controller_elapsed = controller.get("elapsed_seconds") if controller else None
    if controller_elapsed is not None:
        try:
            controller_elapsed = float(controller_elapsed)
            if not math.isfinite(controller_elapsed) or controller_elapsed < 0:
                controller_elapsed = None
        except (TypeError, ValueError):
            controller_elapsed = None

    workers = resources.get("workers") if resources else None
    workers = workers if isinstance(workers, list) else []
    worker_times = []
    for worker in workers:
        if isinstance(worker, dict):
            elapsed = worker.get("elapsed_seconds")
            if elapsed is not None:
                try:
                    elapsed = float(elapsed)
                    if math.isfinite(elapsed) and elapsed >= 0:
                        worker_times.append(elapsed)
                except (TypeError, ValueError):
                    pass

    worker_max = max(worker_times) if worker_times else None
    worker_min = min(worker_times) if worker_times else None

    reporting_seconds = None
    if (
        controller_elapsed is not None
        and collection_seconds is not None
        and worker_max is not None
    ):
        reporting_seconds = float(controller_elapsed) - float(collection_seconds) - float(worker_max)
        if reporting_seconds < 0:
            reporting_seconds = None

    return {
        "collection_seconds": collection_seconds,
        "controller_elapsed_seconds": controller_elapsed,
        "worker_elapsed_max_seconds": worker_max,
        "worker_elapsed_min_seconds": worker_min,
        "in_pytest_reporting_seconds": reporting_seconds,
        "overlap_note": "Controller elapsed spans collection + reporting; workers run concurrently. A negative remainder indicates measured clock overlap, not a valid reporting interval.",
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
        plugin_dir = _write_growth_plugin(output / f"tmp-{name}")
        env["PYTHONPATH"] = f"{plugin_dir}:{arm}"
        env["CI_TEST_RESOURCE_DIR"] = str(output / f"tmp-{name}")
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
        tmpdir_path = output / f"tmp-{name}"
        resources_src = tmpdir_path / "pytest-resources.json"
        resources_dst = arm / "pytest-resources.json"
        if resources_src.is_file():
            try:
                resources_dst.write_bytes(resources_src.read_bytes())
            except OSError:
                pass
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
            "pytest-collection.json",
            "pytest-resources.json",
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
