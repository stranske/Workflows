#!/usr/bin/env python3
"""Run deliberate-break / restore cycles for issue #4170 PR #4172 tests.

Mutates production scripts in the repo worktree transiently; restores each file
before the next case. Writes acceptance.json and log files alongside this script.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PYTHON = "/opt/anaconda3/bin/python3"
OUT_DIR = Path(__file__).resolve().parent
TARGET_TESTS = (
    "tests/scripts/test_docs_drift_fix_agent.py",
    "tests/scripts/test_export_keepalive_durability.py",
    "tests/scripts/test_workflow_startup_failure_diagnostic.py",
)


@dataclass(frozen=True)
class Case:
    nodeid_suffix: str
    rel_path: str
    old: str
    new: str
    note: str


CASES: tuple[Case, ...] = (
    Case(
        "test_repo_detection_falls_back_when_git_is_unavailable",
        "scripts/docs_drift_fix_agent.py",
        "    return probe.resolve()",
        "    return Path(\"/nonexistent-git-root\")",
        "detect_repo_root must fall back to probe when git fails",
    ),
    Case(
        "test_config_and_scan_helpers_reject_bad_shapes_and_use_defaults",
        "scripts/docs_drift_fix_agent.py",
        '        return {"by_repo": []}',
        '        return {"by_repo": ["broken"]}',
        "load_scan_json(None) default shape",
    ),
    Case(
        "test_plan_output_writer_and_batch_limit_are_executable",
        "scripts/docs_drift_fix_agent.py",
        '        raise ValueError("max_per_batch must be positive")',
        "        return []",
        "batch_findings rejects non-positive max_per_batch",
    ),
    Case(
        "test_default_docs_from_config_accepts_null_maps_and_skips_bad_items",
        "scripts/docs_drift_fix_agent.py",
        "    if repos is None:\n        repos = {}",
        "    if repos is None:\n        raise ValueError(\"repos must be mapping\")",
        "null repos mapping normalized (PR #4172 witness mutation)",
    ),
    Case(
        "test_findings_helpers_and_scan_json_load_cover_skip_paths",
        "scripts/docs_drift_fix_agent.py",
        '    return "docs/ci/WORKFLOWS.md"',
        '    return "README.md"',
        "_doc_from_detail default doc path",
    ),
    Case(
        "test_legacy_markers_and_apply_issue_failure_paths",
        "scripts/docs_drift_fix_agent.py",
        '                raise RuntimeError(f"gh issue list failed: {list_result.stderr.strip()}")',
        '                raise RuntimeError("list failed")',
        "apply_issues surfaces gh issue list failure",
    ),
    Case(
        "test_main_validation_and_json_output",
        "scripts/docs_drift_fix_agent.py",
        '            raise FileNotFoundError(f"repo root not found: {repo_root}")',
        "            return 0",
        "main validates missing repo root",
    ),
    Case(
        "test_helpers_handle_invalid_metadata_and_reverts_before_the_merge",
        "scripts/export_keepalive_durability.py",
        '        return {"durability": "skipped", "reason": "missing_merged_pr_metadata"}',
        '        return {"durability": "skipped", "reason": "broken_reason"}',
        "classify_durability missing metadata reason",
    ),
    Case(
        "test_build_records_skips_invalid_rows_and_can_include_pending",
        "scripts/export_keepalive_durability.py",
        "            if durability == \"pending\" and not include_pending:",
        "            if durability == \"pending\":",
        "include_pending emits pending grace records",
    ),
    Case(
        "test_registry_fetch_and_ndjson_helpers_cover_error_and_success_paths",
        "scripts/export_keepalive_durability.py",
        "        if repo and repo not in seen:",
        "        if repo:",
        "registry_repos deduplicates repo slugs",
    ),
    Case(
        "test_fetch_repo_payload_requests_the_merged_and_revert_views",
        "scripts/export_keepalive_durability.py",
        '            "merged",',
        '            "open",',
        "fetch_repo_payload queries merged PR state",
    ),
    Case(
        "test_cli_rejects_invalid_numeric_limits[--days-0]",
        "scripts/export_keepalive_durability.py",
        "    if args.days <= 0:\n        parser.error(\"--days must be positive\")",
        "    if False:\n        parser.error(\"--days must be positive\")",
        "CLI rejects non-positive --days",
    ),
    Case(
        "test_helpers_cover_timezone_agent_and_closing_edge_cases",
        "scripts/export_keepalive_durability.py",
        "        parsed = parsed.replace(tzinfo=UTC)",
        "        pass  # leave naive",
        "_parse_time attaches UTC to naive timestamps",
    ),
    Case(
        "test_gh_json_filters_non_dicts_and_rejects_non_list_payloads",
        "scripts/export_keepalive_durability.py",
        '        raise RuntimeError("gh command did not return a JSON array")',
        "        return []",
        "_gh_json rejects non-list payloads (PR #4172 witness mutation)",
    ),
    Case(
        "test_build_records_skips_explicit_skipped_classifications",
        "scripts/export_keepalive_durability.py",
        '                skipped[str(classification.get("reason") or "skipped")] += 1',
        '                skipped["wrong_bucket"] += 1',
        "skipped classification tallies reason key",
    ),
    Case(
        "test_cli_human_summary_and_partial_fetch_paths",
        "scripts/export_keepalive_durability.py",
        '            f"export_keepalive_durability: wrote {summary[\'records\']} record(s) "',
        '            f"export_keepalive_durability: wrote {summary[\'records\'] + 1} record(s) "',
        "human summary record count",
    ),
    Case(
        "test_token_pacing_and_list_api_paths",
        "scripts/workflow_startup_failure_diagnostic.py",
        "    if _PACE_SECONDS > 0:\n        time.sleep(_PACE_SECONDS)",
        "    if False:\n        time.sleep(_PACE_SECONDS)",
        "_pace sleeps when _PACE_SECONDS is positive",
    ),
    Case(
        "test_sweep_helpers_dedupe_repositories_and_write_action_summary",
        "scripts/workflow_startup_failure_diagnostic.py",
        "        if repo not in seen:",
        "        if False:",
        "_sweep_repos deduplicates repository list",
    ),
    Case(
        "test_fork_inference_and_startup_classification_fallbacks",
        "scripts/workflow_startup_failure_diagnostic.py",
        '    return ("unknown", "unknown")',
        '    return ("mystery", "unknown")',
        "unknown startup classification fallback (PR #4172 witness mutation)",
    ),
    Case(
        "test_iter_paginated_and_hold_onset_edge_paths",
        "scripts/workflow_startup_failure_diagnostic.py",
        "    except ValueError:\n        return None\n    return max(0, (b - a).days)",
        "    except ValueError:\n        return 0\n    return max(0, (b - a).days)",
        "_days_between returns None for invalid timestamps",
    ),
    Case(
        "test_sweep_repository_skips_inactive_non_workflow_sparse_and_threshold",
        "scripts/workflow_startup_failure_diagnostic.py",
        "        if workflow_id is None or workflow.get(\"state\") != \"active\":\n            continue",
        "        if workflow_id is None:\n            continue",
        "sweep_repository skips inactive workflows in scan count",
    ),
    Case(
        "test_sweep_summary_step_summary_and_main_error_paths",
        "scripts/workflow_startup_failure_diagnostic.py",
        '    tail = ""\n    if oldest:',
        '    tail = " oldest"\n    if oldest:',
        "format_sweep_summary omits oldest tail when oldest_hold is absent",
    ),
)


def run_pytest(nodeid: str) -> subprocess.CompletedProcess[str]:
    cmd = [
        PYTHON,
        "-m",
        "pytest",
        *TARGET_TESTS,
        "-q",
        "--no-header",
        f"-k={nodeid.split('::')[-1].split('[')[0]}",
    ]
    if "[" in nodeid:
        cmd[-1] = f"-k={nodeid.split('::')[-1]}"
    env = {**dict(**subprocess.os.environ), "PYTHONPATH": str(REPO)}
    return subprocess.run(
        cmd,
        cwd=REPO,
        env=env,
        text=True,
        capture_output=True,
    )


def run_pytest_exact(nodeid: str) -> subprocess.CompletedProcess[str]:
    cmd = [PYTHON, "-m", "pytest", nodeid, "-q", "--no-header"]
    env = {**dict(**subprocess.os.environ), "PYTHONPATH": str(REPO)}
    return subprocess.run(cmd, cwd=REPO, env=env, text=True, capture_output=True)


def main() -> int:
    suite_cmd = [
        PYTHON,
        "-m",
        "pytest",
        *TARGET_TESTS,
        "-q",
    ]
    green = subprocess.run(
        suite_cmd,
        cwd=REPO,
        env={**dict(**subprocess.os.environ), "PYTHONPATH": str(REPO)},
        text=True,
        capture_output=True,
    )
    (OUT_DIR / "green-suite.log").write_text(green.stdout + green.stderr, encoding="utf-8")
    if green.returncode != 0:
        print(green.stdout, green.stderr, file=sys.stderr)
        return 1

    records: list[dict[str, object]] = []
    for case in CASES:
        path = REPO / case.rel_path
        original = path.read_text(encoding="utf-8")
        if case.old not in original:
            print(f"MISSING old fragment in {case.rel_path}: {case.note}", file=sys.stderr)
            return 1
        if "docs_drift" in case.rel_path:
            test_file = "tests/scripts/test_docs_drift_fix_agent.py"
        elif "export_keepalive" in case.rel_path:
            test_file = "tests/scripts/test_export_keepalive_durability.py"
        else:
            test_file = "tests/scripts/test_workflow_startup_failure_diagnostic.py"
        nodeid = f"{test_file}::{case.nodeid_suffix}"
        mutated = original.replace(case.old, case.new, 1)
        red: subprocess.CompletedProcess[str]
        try:
            path.write_text(mutated, encoding="utf-8")
            red = run_pytest_exact(nodeid)
            (OUT_DIR / "red" / f"{case.nodeid_suffix}.log").parent.mkdir(
                parents=True, exist_ok=True
            )
            (OUT_DIR / "red" / f"{case.nodeid_suffix}.log").write_text(
                red.stdout + red.stderr, encoding="utf-8"
            )
        finally:
            path.write_text(original, encoding="utf-8")
        restore = run_pytest_exact(nodeid)
        (OUT_DIR / "green" / f"{case.nodeid_suffix}.log").parent.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "green" / f"{case.nodeid_suffix}.log").write_text(
            restore.stdout + restore.stderr, encoding="utf-8"
        )
        fail_line = ""
        for line in (red.stdout + red.stderr).splitlines():
            if line.startswith("FAILED ") or "AssertionError" in line or "Error" in line:
                fail_line = line.strip()
                if line.startswith("FAILED "):
                    break
        records.append(
            {
                "nodeid": nodeid,
                "production_file": case.rel_path,
                "mutation_note": case.note,
                "red_exit_code": red.returncode,
                "red_failure_line": fail_line,
                "green_exit_code": restore.returncode,
            }
        )
        if red.returncode == 0 or restore.returncode != 0:
            print(f"unexpected red/green for {nodeid}", file=sys.stderr)
            print(red.stdout, red.stderr, file=sys.stderr)
            return 1

    acceptance = {
        "issue": "stranske/Workflows#4170",
        "merged_implementation_pr": 4172,
        "merged_commit": "cbad3c6f0f0f8e76b2dbaf382148ef4301de253d",
        "validated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "interpreter": PYTHON,
        "target_pytest_command": " ".join(suite_cmd),
        "green_suite_exit_code": green.returncode,
        "green_suite_summary": (green.stdout + green.stderr).strip().splitlines()[-1],
        "new_test_functions": 22,
        "cases": records,
    }
    (OUT_DIR / "acceptance.json").write_text(
        json.dumps(acceptance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"ok": True, "cases": len(records)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
