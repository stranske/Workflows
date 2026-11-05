#!/usr/bin/env python3
"""Run break-and-revert proofs for issue #4170 tests added in PR #4172."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from defusedxml import ElementTree as SafeET

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
INTERPRETER = sys.executable

THREE_PATHS = [
    "tests/scripts/test_docs_drift_fix_agent.py",
    "tests/scripts/test_export_keepalive_durability.py",
    "tests/scripts/test_workflow_startup_failure_diagnostic.py",
]


@dataclass(frozen=True)
class Mutation:
    node_id: str
    production_file: str
    behavior: str
    before: str
    after: str


MUTATIONS: list[Mutation] = [
    Mutation(
        "tests/scripts/test_docs_drift_fix_agent.py::test_repo_detection_falls_back_when_git_is_unavailable",
        "scripts/docs_drift_fix_agent.py",
        "detect_repo_root falls back to cwd when git is unavailable",
        "    return probe.resolve()",
        "    return Path('/nonexistent-repo-root')",
    ),
    Mutation(
        "tests/scripts/test_docs_drift_fix_agent.py::test_config_and_scan_helpers_reject_bad_shapes_and_use_defaults",
        "scripts/docs_drift_fix_agent.py",
        "load_scan_json(None) returns empty by_repo scan",
        '        return {"by_repo": []}',
        '        return {"by_repo": ["bad"]}',
    ),
    Mutation(
        "tests/scripts/test_docs_drift_fix_agent.py::test_plan_output_writer_and_batch_limit_are_executable",
        "scripts/docs_drift_fix_agent.py",
        "batch_findings rejects non-positive max_per_batch",
        '    if max_per_batch <= 0:\n        raise ValueError("max_per_batch must be positive")',
        '    if max_per_batch < 0:\n        raise ValueError("max_per_batch must be positive")',
    ),
    Mutation(
        "tests/scripts/test_docs_drift_fix_agent.py::test_default_docs_from_config_accepts_null_maps_and_skips_bad_items",
        "scripts/docs_drift_fix_agent.py",
        "default_docs_from_config treats repos: null as empty mapping",
        "    if repos is None:\n        repos = {}",
        "    if repos is None:\n        repos = None",
    ),
    Mutation(
        "tests/scripts/test_docs_drift_fix_agent.py::test_findings_helpers_and_scan_json_load_cover_skip_paths",
        "scripts/docs_drift_fix_agent.py",
        "_doc_from_detail default doc path when detail lacks marker",
        '    return "docs/ci/WORKFLOWS.md"',
        '    return "README.md"',
    ),
    Mutation(
        "tests/scripts/test_docs_drift_fix_agent.py::test_legacy_markers_and_apply_issue_failure_paths",
        "scripts/docs_drift_fix_agent.py",
        "apply_issues surfaces gh issue list failures as RuntimeError",
        '                raise RuntimeError(f"gh issue list failed: {list_result.stderr.strip()}")',
        '                raise RuntimeError(f"gh issue list broke: {list_result.stderr.strip()}")',
    ),
    Mutation(
        "tests/scripts/test_docs_drift_fix_agent.py::test_main_validation_and_json_output",
        "scripts/docs_drift_fix_agent.py",
        "main returns exit 2 when repo root is missing",
        '    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:\n        print(f"error: {exc}", file=sys.stderr)\n        return 2',
        '    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:\n        print(f"error: {exc}", file=sys.stderr)\n        return 0',
    ),
    Mutation(
        "tests/scripts/test_export_keepalive_durability.py::test_helpers_handle_invalid_metadata_and_reverts_before_the_merge",
        "scripts/export_keepalive_durability.py",
        "_parse_time rejects non-string timestamps",
        "    if not isinstance(value, str) or not value.strip():\n        return None",
        "    if not isinstance(value, str) or not value.strip():\n        return datetime.now(UTC)",
    ),
    Mutation(
        "tests/scripts/test_export_keepalive_durability.py::test_build_records_skips_invalid_rows_and_can_include_pending",
        "scripts/export_keepalive_durability.py",
        "build_records skips payloads with missing repo",
        '            skipped["missing_repo"] += 1\n            continue',
        '            skipped["missing_repo"] += 1\n            records.append({"repo": repo, "status": "bad"})',
    ),
    Mutation(
        "tests/scripts/test_export_keepalive_durability.py::test_registry_fetch_and_ndjson_helpers_cover_error_and_success_paths",
        "scripts/export_keepalive_durability.py",
        "registry_repos deduplicates repo entries",
        "        if repo and repo not in seen:",
        "        if repo:",
    ),
    Mutation(
        "tests/scripts/test_export_keepalive_durability.py::test_fetch_repo_payload_requests_the_merged_and_revert_views",
        "scripts/export_keepalive_durability.py",
        "fetch_repo_payload queries revert PRs by title",
        '            f"Revert in:title merged:>={since}",',
        '            f"Revert merged:>={since}",',
    ),
    Mutation(
        "tests/scripts/test_export_keepalive_durability.py::test_cli_rejects_invalid_numeric_limits[--days-0]",
        "scripts/export_keepalive_durability.py",
        "CLI rejects non-positive --days",
        '    if args.days <= 0:\n        parser.error("--days must be positive")',
        '    if args.days < 0:\n        parser.error("--days must be positive")',
    ),
    Mutation(
        "tests/scripts/test_export_keepalive_durability.py::test_cli_rejects_invalid_numeric_limits[--grace-days--1]",
        "scripts/export_keepalive_durability.py",
        "CLI rejects negative --grace-days",
        '    if args.grace_days < 0:\n        parser.error("--grace-days must be non-negative")',
        '    if args.grace_days < -1:\n        parser.error("--grace-days must be non-negative")',
    ),
    Mutation(
        "tests/scripts/test_export_keepalive_durability.py::test_cli_rejects_invalid_numeric_limits[--limit-0]",
        "scripts/export_keepalive_durability.py",
        "CLI rejects non-positive --limit",
        '    if args.limit <= 0:\n        parser.error("--limit must be positive")',
        '    if args.limit < 0:\n        parser.error("--limit must be positive")',
    ),
    Mutation(
        "tests/scripts/test_export_keepalive_durability.py::test_helpers_cover_timezone_agent_and_closing_edge_cases",
        "scripts/export_keepalive_durability.py",
        "infer_agent returns unknown when no agent signal is present",
        '    return "unknown"',
        '    return "codex"',
    ),
    Mutation(
        "tests/scripts/test_export_keepalive_durability.py::test_gh_json_filters_non_dicts_and_rejects_non_list_payloads",
        "scripts/export_keepalive_durability.py",
        "_gh_json keeps only dict rows from gh JSON arrays",
        "    return [item for item in data if isinstance(item, dict)]",
        "    return list(data)",
    ),
    Mutation(
        "tests/scripts/test_export_keepalive_durability.py::test_build_records_skips_explicit_skipped_classifications",
        "scripts/export_keepalive_durability.py",
        "classify_durability skips PRs without merged metadata",
        '        return {"durability": "skipped", "reason": "missing_merged_pr_metadata"}',
        '        return {"durability": "pending", "reason": "missing_merged_pr_metadata"}',
    ),
    Mutation(
        "tests/scripts/test_export_keepalive_durability.py::test_cli_human_summary_and_partial_fetch_paths",
        "scripts/export_keepalive_durability.py",
        "CLI human summary reports record count",
        "            f\"export_keepalive_durability: wrote {summary['records']} record(s) \"",
        "            f\"export_keepalive_durability: wrote {summary['records'] + 1} record(s) \"",
    ),
    Mutation(
        "tests/scripts/test_workflow_startup_failure_diagnostic.py::test_token_pacing_and_list_api_paths",
        "scripts/workflow_startup_failure_diagnostic.py",
        "_pace skips sleeping when pace seconds is zero",
        "    if _PACE_SECONDS > 0:\n        time.sleep(_PACE_SECONDS)",
        "    if _PACE_SECONDS >= 0:\n        time.sleep(_PACE_SECONDS)",
    ),
    Mutation(
        "tests/scripts/test_workflow_startup_failure_diagnostic.py::test_sweep_helpers_dedupe_repositories_and_write_action_summary",
        "scripts/workflow_startup_failure_diagnostic.py",
        "_sweep_repos deduplicates repeated repo arguments",
        "        if repo not in seen:\n            seen.add(repo)\n            ordered.append(repo)",
        "        ordered.append(repo)",
    ),
    Mutation(
        "tests/scripts/test_workflow_startup_failure_diagnostic.py::test_fork_inference_and_startup_classification_fallbacks",
        "scripts/workflow_startup_failure_diagnostic.py",
        "_classify_startup_failure unknown fallback tuple",
        '    return ("unknown", "unknown")',
        '    return ("mystery", "unknown")',
    ),
    Mutation(
        "tests/scripts/test_workflow_startup_failure_diagnostic.py::test_iter_paginated_and_hold_onset_edge_paths",
        "scripts/workflow_startup_failure_diagnostic.py",
        "_iter_paginated keeps only dict rows from paginated payloads",
        "        items.extend(x for x in batch if isinstance(x, dict))",
        "        items.extend(batch)",
    ),
    Mutation(
        "tests/scripts/test_workflow_startup_failure_diagnostic.py::test_sweep_repository_skips_inactive_non_workflow_sparse_and_threshold",
        "scripts/workflow_startup_failure_diagnostic.py",
        "sweep_repository ignores held workflows below threshold share",
        "        if threshold and len(held_runs) / len(runs) < threshold:\n            continue",
        "        if False and len(held_runs) / len(runs) < threshold:\n            continue",
    ),
    Mutation(
        "tests/scripts/test_workflow_startup_failure_diagnostic.py::test_sweep_summary_step_summary_and_main_error_paths",
        "scripts/workflow_startup_failure_diagnostic.py",
        "format_sweep_summary omits oldest tail when oldest_hold is absent",
        "    if oldest:",
        "    if oldest or True:",
    ),
]


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_pytest(node_id: str, *, junit_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [INTERPRETER, "-m", "pytest", node_id, "-q"]
    if junit_path is not None:
        cmd.append(f"--junitxml={junit_path}")
    return subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def validate_red_junit(junit_path: Path, node_id: str) -> None:
    if not junit_path.is_file():
        raise RuntimeError(f"{node_id}: missing JUnit report at {junit_path}")
    root = SafeET.parse(junit_path).getroot()
    failures = 0
    errors = 0
    for case in root.iter("testcase"):
        failures += len(case.findall("failure"))
        errors += len(case.findall("error"))
    if failures != 1 or errors != 0:
        raise RuntimeError(
            f"{node_id}: red proof requires exactly one test failure and zero errors "
            f"(JUnit: failures={failures}, errors={errors})"
        )


def apply_patch(path: Path, before: str, after: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(before)
    if count != 1:
        raise RuntimeError(
            f"{path}: expected exactly one occurrence of mutation anchor, found {count}"
        )
    path.write_text(text.replace(before, after, 1), encoding="utf-8")


def restore_patch(path: Path, before: str, after: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(after)
    if count != 1:
        raise RuntimeError(
            f"{path}: expected exactly one mutant occurrence to restore, found {count}"
        )
    path.write_text(text.replace(after, before, 1), encoding="utf-8")


def summarize_output(proc: subprocess.CompletedProcess[str]) -> str:
    lines = (proc.stdout + proc.stderr).strip().splitlines()
    for line in reversed(lines):
        if "passed" in line or "failed" in line or "error" in line:
            return line.strip()
    return f"exit={proc.returncode}"


def main() -> int:
    production_hashes = {
        str(path.relative_to(ROOT)): sha256_path(path)
        for path in sorted({ROOT / mutation.production_file for mutation in MUTATIONS})
    }
    proofs: list[dict[str, object]] = []
    for mutation in MUTATIONS:
        target = ROOT / mutation.production_file
        original = target.read_text(encoding="utf-8")
        try:
            apply_patch(target, mutation.before, mutation.after)
            with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as handle:
                red_junit = Path(handle.name)
            try:
                red = run_pytest(mutation.node_id, junit_path=red_junit)
                if red.returncode != 1:
                    raise RuntimeError(
                        f"{mutation.node_id}: expected pytest exit 1 under mutation, got {red.returncode}"
                    )
                validate_red_junit(red_junit, mutation.node_id)
            finally:
                red_junit.unlink(missing_ok=True)
            restore_patch(target, mutation.before, mutation.after)
            green = run_pytest(mutation.node_id)
            if green.returncode != 0:
                raise RuntimeError(f"{mutation.node_id}: expected passing pytest after restore")
            proofs.append(
                {
                    "node_id": mutation.node_id,
                    "production_file": mutation.production_file,
                    "behavior_broken": mutation.behavior,
                    "mutation_before": mutation.before,
                    "mutation_after": mutation.after,
                    "red_exit": red.returncode,
                    "red_summary": summarize_output(red),
                    "green_exit": green.returncode,
                    "green_summary": summarize_output(green),
                    "failure_excerpt": (red.stdout + red.stderr)[-500:].strip(),
                }
            )
        finally:
            target.write_text(original, encoding="utf-8")

    manifest = {
        "issue": "stranske/Workflows#4170",
        "merged_pr": "#4172",
        "interpreter": INTERPRETER,
        "restored_production_sha256": production_hashes,
        "proof_command_template": f"{INTERPRETER} -m pytest '<node_id>' -q",
        "proofs": proofs,
    }
    (EVIDENCE / "break-and-revert-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"proofs": len(proofs), "manifest": str(EVIDENCE / "break-and-revert-manifest.json")}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
