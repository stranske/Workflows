#!/usr/bin/env python3
"""Compare two hosted Gate runs that used the reusable Python CI workflow.

The reader consumes downloaded ``gate-coverage-*`` artifacts and Actions job
payloads. It does not dispatch workflows, change pytest selection, or treat an
aggregate coverage percentage as branch equivalence.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from defusedxml import ElementTree as SafeET

VERIFIER = "scripts/langchain/pr_verifier.py"
SCOPED_FILES = (
    "tests/scripts/test_pr_verifier_delivery_destinations.py",
    "tests/scripts/test_pr_verifier_prompt_coverage.py",
    "tests/scripts/test_pr_verifier_body_overall_integration.py",
)
SCOPED_SUITES = tuple(path[:-3].replace("/", ".") for path in SCOPED_FILES)
PYTEST_STEP = "Pytest (unit tests with coverage)"
SUMMARY_STEP = "Record CI summary"
TARGET_SECONDS = 600
INVOCATION_START = 'args=("--junitxml=pytest-junit.xml")'
INVOCATION_END = 'pytest -p ci_test_growth "${args[@]}"'
GATE_WORKFLOW = ".github/workflows/pr-00-gate.yml"
REUSABLE_WORKFLOW = ".github/workflows/reusable-10-ci-python.yml"
IDENTITY_PATHS = (
    VERIFIER,
    "requirements.lock",
    "pyproject.toml",
    GATE_WORKFLOW,
)


def discover_runtimes(root: Path) -> dict[str, Path]:
    """Return ``version -> runtimes/<version>`` directories that hold receipts."""
    found: dict[str, Path] = {}
    for summary in root.rglob("summary.json"):
        version_dir = summary.parent
        if version_dir.parent.name != "runtimes":
            continue
        version = version_dir.name
        if version in found:
            raise ValueError(f"duplicate {version} runtime under {root}")
        found[version] = version_dir
    if not found:
        raise ValueError(f"no runtime receipts under {root}")
    return found


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} is not a JSON object")
    return value


def load_runtime(directory: Path) -> dict[str, object]:
    """Load one Python version's collection, resource, summary, and coverage receipts."""
    summary = _load(directory / "summary.json")
    growth = summary.get("test_growth") if isinstance(summary.get("test_growth"), dict) else {}
    collection_path = directory / "pytest-collection.json"
    resources_path = directory / "pytest-resources.json"
    collection = _load(collection_path) if collection_path.is_file() else growth.get("collection")
    resources = (
        _load(resources_path) if resources_path.is_file() else summary.get("worker_resources")
    )
    coverage_path = directory / "coverage.json"
    coverage = _load(coverage_path) if coverage_path.is_file() else None
    junit = directory / "pytest-junit.xml"
    return {
        "summary": summary,
        "collection": collection if isinstance(collection, dict) else None,
        "resources": resources if isinstance(resources, dict) else None,
        "reported": growth.get("reported") if isinstance(growth.get("reported"), dict) else None,
        "coverage": coverage,
        "junit": junit if junit.is_file() else None,
    }


def _stamp(record: dict, *keys: str) -> str | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value and not value.startswith("0001-"):
            return value
    return None


def seconds_between(start: str | None, end: str | None) -> float | None:
    if start is None or end is None:
        return None
    began = datetime.fromisoformat(start.replace("Z", "+00:00"))
    ended = datetime.fromisoformat(end.replace("Z", "+00:00"))
    return (ended - began).total_seconds()


def _step_seconds(step: dict) -> float | None:
    return seconds_between(
        _stamp(step, "started_at", "startedAt"),
        _stamp(step, "completed_at", "completedAt"),
    )


def job_phases(job: dict) -> dict[str, object]:
    """Split a python job into startup, the pytest step, and later reporting steps.

    Actions step timestamps are one-second resolution. Collection and worker
    execution stay inside the pytest step and are read from the receipts.
    """
    steps = job.get("steps") if isinstance(job.get("steps"), list) else []
    parsed = [
        {"name": step.get("name"), "seconds": _step_seconds(step)}
        for step in steps
        if isinstance(step, dict)
    ]
    pytest_index = next(
        (index for index, step in enumerate(parsed) if step["name"] == PYTEST_STEP), None
    )
    before = parsed[:pytest_index] if pytest_index is not None else []
    after = parsed[pytest_index + 1 :] if pytest_index is not None else []
    pytest_step = parsed[pytest_index] if pytest_index is not None else None
    summary = next((step for step in parsed if step["name"] == SUMMARY_STEP), None)

    def total(rows: list[dict]) -> float | None:
        if not rows or any(row["seconds"] is None for row in rows):
            return None
        return float(sum(row["seconds"] for row in rows))

    return {
        "conclusion": job.get("conclusion"),
        "runner_name": job.get("runner_name") or job.get("runnerName"),
        "job_wall_seconds": seconds_between(
            _stamp(job, "started_at", "startedAt"),
            _stamp(job, "completed_at", "completedAt"),
        ),
        "startup_seconds": total(before),
        "pytest_step_seconds": None if pytest_step is None else pytest_step["seconds"],
        "record_summary_seconds": None if summary is None else summary["seconds"],
        "after_pytest_seconds": total(after),
        "step_resolution_seconds": 1,
    }


def execution_split(resources: dict | None, collection: dict | None) -> dict[str, object]:
    """Expose collection, worker execution, and in-pytest reporting from receipts."""
    controller = (resources or {}).get("controller")
    controller = controller if isinstance(controller, dict) else {}
    workers = (resources or {}).get("workers")
    workers = workers if isinstance(workers, list) else []
    elapsed = [
        worker.get("elapsed_seconds")
        for worker in workers
        if isinstance(worker, dict) and isinstance(worker.get("elapsed_seconds"), (int, float))
    ]
    context = (resources or {}).get("context")
    context = context if isinstance(context, dict) else {}
    coverage = controller.get("coverage") if isinstance(controller.get("coverage"), dict) else {}
    collection_seconds = (collection or {}).get("collection_seconds")
    controller_elapsed = controller.get("elapsed_seconds")
    reporting = None
    if (
        isinstance(controller_elapsed, (int, float))
        and isinstance(collection_seconds, (int, float))
        and elapsed
    ):
        reporting = float(controller_elapsed) - float(collection_seconds) - max(elapsed)
        # A negative remainder is clock overlap, not a measured reporting interval.
        if reporting < 0:
            reporting = None
    return {
        "collection_seconds": collection_seconds,
        "controller_elapsed_seconds": controller_elapsed,
        "worker_elapsed_max_seconds": max(elapsed) if elapsed else None,
        "worker_elapsed_min_seconds": min(elapsed) if elapsed else None,
        "in_pytest_reporting_seconds": reporting,
        "expected_workers": (resources or {}).get("expected_workers"),
        "worker_count": len(workers),
        "python": controller.get("python"),
        "coverage": coverage,
        "cpu_model": context.get("cpu_model"),
        "cache": context.get("cache") if isinstance(context.get("cache"), dict) else None,
        "tested_sha": context.get("tested_sha"),
        "resource_status": (resources or {}).get("status"),
        "missing_workers": (resources or {}).get("missing_workers"),
    }


def scoped_counts(collection: dict | None) -> dict[str, object]:
    per_file = (collection or {}).get("per_file")
    per_file = per_file if isinstance(per_file, dict) else {}
    files: dict[str, int | None] = {}
    for name in SCOPED_FILES:
        value = per_file.get(name)
        files[name] = value if isinstance(value, int) and not isinstance(value, bool) else None
    complete = all(isinstance(value, int) for value in files.values())
    return {
        "files": files,
        "total": sum(files.values()) if complete else None,
        "suite_total": (
            (collection or {}).get("total")
            if isinstance((collection or {}).get("total"), int)
            else None
        ),
    }


def scoped_junit(path: Path | None) -> dict[str, object] | None:
    """Sum worker-seconds for the three scoped modules. This is not wall time."""
    if path is None:
        return None
    rows = {
        name: {"cases": 0, "worker_seconds": 0.0, "timing_known": True} for name in SCOPED_SUITES
    }
    for case in SafeET.parse(path).getroot().iter("testcase"):
        classname = case.get("classname") or ""
        if classname not in rows:
            continue
        rows[classname]["cases"] += 1
        raw = case.get("time")
        try:
            seconds = float(raw) if raw is not None else None
        except ValueError:
            seconds = None
        if seconds is None or not math.isfinite(seconds) or seconds < 0:
            rows[classname]["timing_known"] = False
            continue
        rows[classname]["worker_seconds"] += seconds
    for row in rows.values():
        row["worker_seconds"] = round(float(row["worker_seconds"]), 6)
    known = all(row["timing_known"] for row in rows.values())
    return {
        "suites": rows,
        "timing_known": known,
        "worker_seconds": (
            round(sum(row["worker_seconds"] for row in rows.values()), 6) if known else None
        ),
        "source": "JUnit summed worker-seconds for the three scoped files; not wall time",
    }


def verifier_entry(coverage: dict | None) -> dict | None:
    if not isinstance(coverage, dict):
        return None
    files = coverage.get("files")
    if not isinstance(files, dict):
        return None
    if isinstance(files.get(VERIFIER), dict):
        return files[VERIFIER]
    matches = [key for key in files if key.endswith(VERIFIER) and isinstance(files[key], dict)]
    if len(matches) == 1:
        return files[matches[0]]
    return None


def coverage_delta(before: dict | None, after: dict | None) -> dict[str, object]:
    """Compare executed verifier lines and branches. Percentages are not the result."""
    before_entry = verifier_entry(before)
    after_entry = verifier_entry(after)
    if before_entry is None or after_entry is None:
        return {"available": False, "lost_lines": None, "lost_branches": None}
    before_lines = set(before_entry.get("executed_lines") or [])
    after_lines = set(after_entry.get("executed_lines") or [])
    before_branches = {tuple(pair) for pair in before_entry.get("executed_branches") or []}
    after_branches = {tuple(pair) for pair in after_entry.get("executed_branches") or []}
    return {
        "available": True,
        "lost_lines": sorted(before_lines - after_lines),
        "gained_lines": sorted(after_lines - before_lines),
        "lost_branches": [list(pair) for pair in sorted(before_branches - after_branches)],
        "gained_branches": [list(pair) for pair in sorted(after_branches - before_branches)],
        "before": before_entry.get("summary"),
        "after": after_entry.get("summary"),
    }


def _dominant(reported: dict | None, key: str, limit: int = 5) -> list:
    rows = (reported or {}).get(key)
    if not isinstance(rows, list):
        return []
    return rows[:limit]


def compare_runtime(before: dict, after: dict) -> dict[str, object]:
    """Compare one Python version's receipts, including coverage only when active."""
    before_exec = execution_split(before.get("resources"), before.get("collection"))
    after_exec = execution_split(after.get("resources"), after.get("collection"))
    before_coverage = before_exec["coverage"]
    after_coverage = after_exec["coverage"]
    coverage_required = (
        isinstance(before_coverage, dict)
        and before_coverage.get("status") == "ACTIVE"
        and isinstance(after_coverage, dict)
        and after_coverage.get("status") == "ACTIVE"
    )
    delta = (
        coverage_delta(before.get("coverage"), after.get("coverage"))
        if coverage_required
        else {
            "available": False,
            "reason": "coverage is not active on this Python version",
        }
    )
    return {
        "before": before_exec,
        "after": after_exec,
        "counts": {
            "before": scoped_counts(before.get("collection")),
            "after": scoped_counts(after.get("collection")),
        },
        "junit": {"before": before.get("scoped_junit"), "after": after.get("scoped_junit")},
        "checks": {
            "before": (before.get("summary") or {}).get("checks"),
            "after": (after.get("summary") or {}).get("checks"),
        },
        "coverage_percent": {
            "before": ((before.get("summary") or {}).get("coverage") or {}).get("percent"),
            "after": ((after.get("summary") or {}).get("coverage") or {}).get("percent"),
        },
        "verifier_coverage": delta,
        "dominant_functions_before": _dominant(
            before.get("reported"), "dominant_functions_worker_seconds"
        ),
        "dominant_functions_after": _dominant(
            after.get("reported"), "dominant_functions_worker_seconds"
        ),
        "dominant_suites_before": _dominant(
            before.get("reported"), "dominant_suites_worker_seconds"
        ),
        "dominant_suites_after": _dominant(after.get("reported"), "dominant_suites_worker_seconds"),
    }


def configuration_differences(compared: dict) -> list[str]:
    """Workflow-shaped differences. CPU and cache hits are confounders, not inputs."""
    reasons: list[str] = []
    for version, row in sorted(compared.items()):
        left, right = row["before"], row["after"]
        if (
            left["expected_workers"] != right["expected_workers"]
            or left["worker_count"] != right["worker_count"]
        ):
            reasons.append(f"{version} worker configuration differs")
        if left["coverage"] != right["coverage"]:
            reasons.append(f"{version} coverage probe differs")
        if left["resource_status"] != "COMPLETE" or right["resource_status"] != "COMPLETE":
            reasons.append(f"{version} worker resource receipt is incomplete")
        if left["missing_workers"] or right["missing_workers"]:
            reasons.append(f"{version} is missing workers")
    return reasons


def timing_confounders(compared: dict[str, dict]) -> list[str]:
    reasons: list[str] = []
    for version, row in sorted(compared.items()):
        left, right = row["before"], row["after"]
        if left.get("cpu_model") != right.get("cpu_model"):
            reasons.append(
                f"{version} CPU model differs ({left.get('cpu_model')} vs {right.get('cpu_model')})"
            )
        if left.get("cache") != right.get("cache"):
            reasons.append(f"{version} dependency/pytest/artifact cache state differs")
    return reasons


def job_for_version(jobs: list[dict], version: str) -> dict:
    names = {f"python ci / python {version}", f"python {version}"}
    matches = [job for job in jobs if job.get("name") in names]
    if len(matches) != 1:
        raise ValueError(f"expected one job for Python {version}, found {len(matches)}")
    return matches[0]


def assemble_side(root: Path, jobs: list[dict]) -> dict[str, dict]:
    assembled: dict[str, dict] = {}
    for version, directory in sorted(discover_runtimes(root).items()):
        runtime = load_runtime(directory)
        runtime["scoped_junit"] = scoped_junit(runtime.get("junit"))
        runtime["job"] = job_phases(job_for_version(jobs, version))
        assembled[version] = runtime
    return assembled


def pytest_invocation(workflow_text: str) -> str:
    """Return the reusable workflow's pytest argv assembly, excluding the summary recorder."""
    start = workflow_text.index(INVOCATION_START)
    end = workflow_text.index(INVOCATION_END)
    if end < start:
        raise ValueError("pytest invocation markers are out of order")
    return workflow_text[start:end]


def git_show(repo: Path, sha: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo), "show", f"{sha}:{path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def source_identity(repo: Path, before_sha: str, after_sha: str) -> dict[str, object]:
    """Confirm the gate inputs, lock, and pytest invocation used by the two tested SHAs."""
    paths: dict[str, str] = {}
    missing: list[str] = []
    for path in IDENTITY_PATHS:
        before = git_show(repo, before_sha, path)
        after = git_show(repo, after_sha, path)
        if before is None or after is None:
            missing.append(path)
            paths[path] = "missing"
        else:
            paths[path] = "identical" if before == after else "differs"
    before_workflow = git_show(repo, before_sha, REUSABLE_WORKFLOW)
    after_workflow = git_show(repo, after_sha, REUSABLE_WORKFLOW)
    invocation = "missing"
    if before_workflow is not None and after_workflow is not None:
        invocation = (
            "identical"
            if pytest_invocation(before_workflow) == pytest_invocation(after_workflow)
            else "differs"
        )
    identical = (
        not missing
        and all(value == "identical" for value in paths.values())
        and invocation == "identical"
    )
    return {
        "before_sha": before_sha,
        "after_sha": after_sha,
        "paths": paths,
        "pytest_invocation": invocation,
        "identical": identical,
        "missing": missing,
    }


def _tested_shas(side: dict[str, dict]) -> list[str]:
    shas = []
    for runtime in side.values():
        resources = runtime.get("resources") if isinstance(runtime.get("resources"), dict) else {}
        context = resources.get("context") if isinstance(resources.get("context"), dict) else {}
        sha = context.get("tested_sha")
        if isinstance(sha, str):
            shas.append(sha)
    return shas


def build_report(
    before_root: Path,
    after_root: Path,
    before_jobs: list[dict],
    after_jobs: list[dict],
    *,
    before_run: dict,
    after_run: dict,
    identity: dict | None = None,
) -> dict[str, object]:
    before = assemble_side(before_root, before_jobs)
    after = assemble_side(after_root, after_jobs)
    compared = {
        version: compare_runtime(before[version], after[version])
        for version in sorted(set(before) & set(after))
    }
    for version in compared:
        compared[version]["job"] = {
            "before": before[version]["job"],
            "after": after[version]["job"],
        }
    config_gaps = configuration_differences(compared)
    if set(before) != set(after):
        config_gaps.append(f"python versions differ: {sorted(before)} vs {sorted(after)}")
    confounders = timing_confounders(compared)
    before_shas = _tested_shas(before)
    after_shas = _tested_shas(after)
    if len(before_shas) != len(before) or len(set(before_shas)) != 1:
        config_gaps.append("before python jobs disagree on the tested SHA")
    if len(after_shas) != len(after) or len(set(after_shas)) != 1:
        config_gaps.append("after python jobs disagree on the tested SHA")
    if identity is not None and not identity.get("identical"):
        config_gaps.append("tested-source gate inputs, lock, verifier, or pytest invocation differ")
    after_walls = [
        row["job"]["after"].get("job_wall_seconds")
        for row in compared.values()
        if isinstance(row["job"]["after"].get("job_wall_seconds"), (int, float))
    ]
    coverage_rows = [
        row["verifier_coverage"]
        for row in compared.values()
        if row["verifier_coverage"].get("available")
    ]
    lost = [row for row in coverage_rows if row.get("lost_lines") or row.get("lost_branches")]
    green = set(before) == set(after) and all(
        (row["job"][arm].get("conclusion") in {None, "success"})
        and ((row["checks"][arm] or {}).get("tests") or {}).get("outcome") == "success"
        for row in compared.values()
        for arm in ("before", "after")
    )
    return {
        "command": {
            "gate_workflow": GATE_WORKFLOW,
            "reusable_workflow": REUSABLE_WORKFLOW,
            "runner": "ubuntu-latest",
            "marker": "not quarantine and not slow",
            "pytest_workers": "4",
            "pytest_args_then_effective": (
                '-m "not quarantine and not slow" --junitxml=pytest-junit.xml '
                "[--cov --cov-config=pyproject.toml --cov-report=xml --cov-report=term-missing "
                "--cov-report=json on the coverage Python only] "
                "-n auto --dist load -n 4 --dist=loadgroup -p ci_test_growth"
            ),
            "effective_scheduler": "The later -n 4 --dist=loadgroup wins over pytest_args.",
            "coverage_python": "3.14",
            "python_versions": ["3.13", "3.14"],
            "note": (
                "Required Gate no longer schedules Python 3.12. "
                "Run 38938420079 used 3.12/3.13 and failed, so it is not this pair."
            ),
        },
        "runs": {"before": before_run, "after": after_run},
        "tested_shas": {"before": _tested_shas(before), "after": _tested_shas(after)},
        "source_identity": identity,
        "configuration_identical": not config_gaps,
        "configuration_gaps": config_gaps,
        "timing_confounders": confounders,
        "timing_controlled": not config_gaps and not confounders,
        "runtimes": compared,
        "verifier_branch_loss": bool(lost),
        "gates_green": green,
        "ten_minute_target_seconds": TARGET_SECONDS,
        "ten_minute_target_met": bool(after_walls) and max(after_walls) < TARGET_SECONDS,
        "slowest_job_wall_seconds": max(after_walls) if after_walls else None,
    }


def _shown_sha(value: object) -> str:
    if isinstance(value, list):
        unique = list(dict.fromkeys(value))
        return unique[0] if len(unique) == 1 else ", ".join(str(item) for item in unique)
    return str(value)


def _seconds(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, float):
        return f"{value:.3f}s"
    return f"{value}s"


def render_markdown(report: dict) -> str:
    """Publish the comparison without treating a percentage or a confounded delta as proof."""
    lines = [
        "# Hosted Gate before/after for issue 3904",
        "",
        "Required jobs come from `.github/workflows/pr-00-gate.yml` calling",
        "`.github/workflows/reusable-10-ci-python.yml`. Step times use Actions'",
        "one-second timestamps. Collection, worker execution, and in-pytest reporting",
        "come from the uploaded receipts. JUnit figures are summed worker-seconds,",
        "not wall time.",
        "",
        "## Commands",
        "",
        f"- Runner class: `{report['command']['runner']}`",
        f"- Python versions: {', '.join(report['command']['python_versions'])}",
        f"- Coverage Python: `{report['command']['coverage_python']}`",
        f"- Marker: `{report['command']['marker']}`",
        f"- Workers input: `{report['command']['pytest_workers']}`",
        f"- Effective argv: `{report['command']['pytest_args_then_effective']}`",
        f"- {report['command']['effective_scheduler']}",
        f"- {report['command']['note']}",
        "",
        "## Runs and SHAs",
        "",
    ]
    for arm in ("before", "after"):
        run = report["runs"][arm]
        lines.append(
            f"- {arm}: [{run.get('id')}]({run.get('url')}) head `{run.get('head_sha')}` "
            f"tested `{_shown_sha(report['tested_shas'][arm])}`"
        )
    identity = report.get("source_identity") or {}
    lines.extend(
        [
            f"- Source identity: `{identity.get('identical')}` "
            f"(pytest invocation `{identity.get('pytest_invocation')}`).",
            "",
            "## Configuration",
            "",
            f"- Workflow configuration identical: `{report['configuration_identical']}`.",
            f"- Timing controlled (no CPU or cache confounder): `{report['timing_controlled']}`.",
        ]
    )
    for gap in report["configuration_gaps"]:
        lines.append(f"- Configuration gap: {gap}")
    for item in report["timing_confounders"]:
        lines.append(f"- Timing confounder: {item}")
    if not report["configuration_gaps"] and not report["timing_confounders"]:
        lines.append("- No workflow, worker, coverage, CPU, or cache differences recorded.")
    lines.extend(["", "## Counts", ""])
    for version, row in report["runtimes"].items():
        before_counts = row["counts"]["before"]
        after_counts = row["counts"]["after"]
        lines.append(
            f"- Python {version} full collection: {before_counts['suite_total']} -> "
            f"{after_counts['suite_total']}"
        )
        lines.append(
            f"- Python {version} scoped three files: {before_counts['total']} -> {after_counts['total']}"
        )
    lines.extend(["", "## Branch coverage", ""])
    if not any(row["verifier_coverage"].get("available") for row in report["runtimes"].values()):
        lines.append("- Verifier branch comparison was not available.")
    for version, row in report["runtimes"].items():
        delta = row["verifier_coverage"]
        if not delta.get("available"):
            continue
        lines.append(
            f"- Python {version} `{VERIFIER}` lost lines {len(delta['lost_lines'])}, "
            f"lost branches {len(delta['lost_branches'])}, "
            f"gained lines {len(delta['gained_lines'])}, "
            f"gained branches {len(delta['gained_branches'])}."
        )
        percent = row["coverage_percent"]
        lines.append(
            f"- Aggregate percent {percent['before']} -> {percent['after']} "
            "is not the equivalence result."
        )
        before_summary = delta.get("before") or {}
        after_summary = delta.get("after") or {}
        lines.append(
            f"- Executed verifier lines {before_summary.get('covered_lines')} -> "
            f"{after_summary.get('covered_lines')}; branches "
            f"{before_summary.get('covered_branches')} -> {after_summary.get('covered_branches')}."
        )
        if delta["lost_lines"] or delta["lost_branches"]:
            lines.append(f"- Unresolved lost lines: `{delta['lost_lines']}`")
            lines.append(f"- Unresolved lost branches: `{delta['lost_branches']}`")
    lines.extend(["", "## Timings", ""])
    for version, row in report["runtimes"].items():
        for arm in ("before", "after"):
            job = row["job"][arm]
            execution = row[arm]
            junit = (row.get("junit") or {}).get(arm) or {}
            lines.append(
                "- Python "
                f"{version} {arm}: job wall {_seconds(job.get('job_wall_seconds'))}, "
                f"startup {_seconds(job.get('startup_seconds'))}, "
                f"pytest step {_seconds(job.get('pytest_step_seconds'))}, "
                f"collection {_seconds(execution.get('collection_seconds'))}, "
                f"max worker {_seconds(execution.get('worker_elapsed_max_seconds'))}, "
                f"controller {_seconds(execution.get('controller_elapsed_seconds'))}, "
                f"in-pytest reporting {_seconds(execution.get('in_pytest_reporting_seconds'))}, "
                f"record-summary {_seconds(job.get('record_summary_seconds'))}, "
                f"scoped JUnit worker-seconds {_seconds(junit.get('worker_seconds'))}."
            )
    lines.append(
        "- xdist collection overlaps worker execution, so collection and worker "
        "clocks are not added together. A null in-pytest reporting value means the "
        "controller clock does not leave a nonnegative remainder after both."
    )
    lines.extend(
        [
            "",
            "## Ten-minute target and residual cost",
            "",
            f"- Slowest after python-job wall: {_seconds(report['slowest_job_wall_seconds'])}.",
            f"- Target met (<{TARGET_SECONDS}s job wall): `{report['ten_minute_target_met']}`.",
        ]
    )
    if not report["ten_minute_target_met"]:
        gap = None
        if isinstance(report["slowest_job_wall_seconds"], (int, float)):
            gap = report["slowest_job_wall_seconds"] - TARGET_SECONDS
        lines.append(
            f"- Residual gap: {_seconds(gap)} above the job-wall target. "
            "This does not claim the target is met."
        )
    if not report["timing_controlled"]:
        lines.append("- Wall-time deltas are not a same-machine controlled speedup.")
    lines.extend(["", "Dominant JUnit suites after the change:", ""])
    for version, row in report["runtimes"].items():
        for name, seconds in row["dominant_suites_after"][:3]:
            lines.append(f"- Python {version}: `{name}` {_seconds(seconds)} worker-seconds")
    lines.extend(["", "Dominant JUnit functions after the change:", ""])
    for version, row in report["runtimes"].items():
        for name, seconds in row["dominant_functions_after"]:
            lines.append(f"- Python {version}: `{name}` {_seconds(seconds)} worker-seconds")
    lines.append("")
    return "\n".join(lines)


def _common_sha(shas: list[str]) -> str | None:
    unique = list(dict.fromkeys(shas))
    if len(unique) == 1:
        return unique[0]
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before-root", type=Path, required=True)
    parser.add_argument("--after-root", type=Path, required=True)
    parser.add_argument("--before-jobs", type=Path, required=True)
    parser.add_argument("--after-jobs", type=Path, required=True)
    parser.add_argument("--before-run-id", required=True)
    parser.add_argument("--after-run-id", required=True)
    parser.add_argument("--before-url", required=True)
    parser.add_argument("--after-url", required=True)
    parser.add_argument("--before-head", required=True)
    parser.add_argument("--after-head", required=True)
    parser.add_argument("--repo", type=Path, default=None)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args(argv)
    before_jobs = json.loads(args.before_jobs.read_text(encoding="utf-8"))
    after_jobs = json.loads(args.after_jobs.read_text(encoding="utf-8"))
    report = build_report(
        args.before_root,
        args.after_root,
        before_jobs,
        after_jobs,
        before_run={"id": args.before_run_id, "url": args.before_url, "head_sha": args.before_head},
        after_run={"id": args.after_run_id, "url": args.after_url, "head_sha": args.after_head},
        identity=None,
    )
    before_sha = _common_sha(report["tested_shas"]["before"])
    after_sha = _common_sha(report["tested_shas"]["after"])
    if args.repo is not None and before_sha and after_sha:
        report["source_identity"] = source_identity(args.repo, before_sha, after_sha)
        if not report["source_identity"]["identical"]:
            report["configuration_gaps"].append(
                "tested-source gate inputs, lock, verifier, or pytest invocation differ"
            )
            report["configuration_identical"] = False
            report["timing_controlled"] = False
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "configuration_identical": report["configuration_identical"],
                "timing_controlled": report["timing_controlled"],
                "verifier_branch_loss": report["verifier_branch_loss"],
                "ten_minute_target_met": report["ten_minute_target_met"],
                "gates_green": report["gates_green"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
