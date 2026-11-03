#!/usr/bin/env python3
"""Run deliberate-break proofs for #4013 added tests; writes JSON evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PY = "/opt/anaconda3/bin/python3"


@dataclass(frozen=True)
class MutationSpec:
    mutation_id: str
    rel_path: str
    old: str
    new: str
    node_ids: tuple[str, ...]


MUTATIONS: tuple[MutationSpec, ...] = (
    MutationSpec(
        "ci-scope-select-metadata",
        "scripts/reusable_ci_scope.py",
        "            matched_reasons.append(f\"`{_scenario_name(scenario)}` is unscoped\")",
        "            matched_reasons.append(f\"`{_scenario_name(scenario)}` is broken\")",
        (
            "tests/scripts/test_reusable_ci_scope.py::test_scope_selection_preserves_requested_metadata_and_includes_unscoped_scenarios",
        ),
    ),
    MutationSpec(
        "ci-scope-path-matches-docs-slash",
        "scripts/reusable_ci_scope.py",
        "    if not has_glob:\n        return normalized_path == normalized_pattern or normalized_path.startswith(\n            f\"{normalized_pattern}/\"\n        )",
        "    if not has_glob:\n        return False",
        (
            "tests/scripts/test_reusable_ci_scope.py::test_path_matching_normalizes_common_scope_forms[docs/guide.md-docs/-True]",
            "tests/scripts/test_reusable_ci_scope.py::test_path_matching_normalizes_common_scope_forms[docs/guide.md-docs-True]",
        ),
    ),
    MutationSpec(
        "ci-scope-path-matches-glob",
        "scripts/reusable_ci_scope.py",
        "    if fnmatch.fnmatchcase(normalized_path, normalized_pattern):\n        return True\n    if normalized_pattern.startswith(\"**/\"):\n        return fnmatch.fnmatchcase(normalized_path, normalized_pattern[3:])",
        "    if fnmatch.fnmatchcase(normalized_path, normalized_pattern):\n        return False\n    if normalized_pattern.startswith(\"**/\"):\n        return False",
        (
            "tests/scripts/test_reusable_ci_scope.py::test_path_matching_normalizes_common_scope_forms[nested/a.py-**/*.py-True]",
            "tests/scripts/test_reusable_ci_scope.py::test_path_matching_normalizes_common_scope_forms[a.py-**/*.py-True]",
        ),
    ),
    MutationSpec(
        "ci-scope-path-matches-false",
        "scripts/reusable_ci_scope.py",
        "    if fnmatch.fnmatchcase(normalized_path, normalized_pattern):\n        return True",
        "    if fnmatch.fnmatchcase(normalized_path, normalized_pattern):\n        return True\n    return True",
        (
            "tests/scripts/test_reusable_ci_scope.py::test_path_matching_normalizes_common_scope_forms[src/a.py-src/*.js-False]",
        ),
    ),
    MutationSpec(
        "ci-scope-cli-main",
        "scripts/reusable_ci_scope.py",
        "    print(json.dumps({**outputs, \"matrix\": selected.matrix}, sort_keys=True))\n    return 0",
        "    print(json.dumps({**outputs, \"matrix\": selected.matrix}, sort_keys=True))\n    return 1",
        (
            "tests/scripts/test_reusable_ci_scope.py::test_cli_reads_changed_files_and_matrix_files_and_writes_outputs",
        ),
    ),
    MutationSpec(
        "ci-scope-cli-json-error",
        "scripts/reusable_ci_scope.py",
        '        raise SystemExit("matrix must be a JSON list or object")',
        '        raise SystemExit("broken matrix message")',
        (
            "tests/scripts/test_reusable_ci_scope.py::test_cli_rejects_invalid_input[argv1-matrix must be]",
        ),
    ),
    MutationSpec(
        "ci-scope-cli-not-json",
        "scripts/reusable_ci_scope.py",
        "        raise SystemExit(f\"{label} must be valid JSON: {exc}\") from exc",
        '        raise SystemExit("broken json message") from exc',
        (
            "tests/scripts/test_reusable_ci_scope.py::test_cli_rejects_invalid_input[argv0-must be valid JSON]",
        ),
    ),
    MutationSpec(
        "ci-scope-cli-array",
        "scripts/reusable_ci_scope.py",
        '            raise SystemExit("--changed-files-json must be a JSON array")',
        '            raise SystemExit("broken array message")',
        (
            "tests/scripts/test_reusable_ci_scope.py::test_cli_rejects_invalid_input[argv2-JSON array]",
        ),
    ),
    MutationSpec(
        "ci-scope-receipt-schema",
        "scripts/reusable_ci_scope.py",
        '        "schema": "scenario-matrix-producer/v1",',
        '        "schema": "broken/v0",',
        (
            "tests/scripts/test_reusable_ci_scope.py::test_scenario_matrix_receipt_binds_environment_and_source",
        ),
    ),
    MutationSpec(
        "ci-scope-normalize-path",
        "scripts/reusable_ci_scope.py",
        '        return list(full_matrix), "list"',
        '        return list(full_matrix), "broken"',
        (
            "tests/scripts/test_reusable_ci_scope.py::test_internal_normalization_and_option_helpers_cover_supported_shapes",
        ),
    ),
    MutationSpec(
        "ci-scope-scope-for",
        "scripts/reusable_ci_scope.py",
        '        scope_paths = [str(path) for path in paths if str(path).strip()]',
        "        scope_paths = []",
        (
            "tests/scripts/test_reusable_ci_scope.py::test_scope_extraction_and_selection_reason_cover_legacy_forms",
        ),
    ),
    MutationSpec(
        "ci-scope-empty-fallback",
        "scripts/reusable_ci_scope.py",
        '            reason="changed files were unavailable",',
        '            reason="broken unavailable",',
        (
            "tests/scripts/test_reusable_ci_scope.py::test_selection_falls_back_for_empty_changes_and_unknown_paths",
        ),
    ),
    MutationSpec(
        "ci-scope-delimiter",
        "scripts/reusable_ci_scope.py",
        "            while delimiter in value:\n                delimiter = f\"_{delimiter}_\"",
        "            while False and delimiter in value:\n                delimiter = f\"_{delimiter}_\"",
        (
            "tests/scripts/test_reusable_ci_scope.py::test_changed_files_environment_and_delimiter_collision",
        ),
    ),
    MutationSpec(
        "verifier-empty-input",
        "scripts/langchain/verifier_config.py",
        "    if not raw:\n        return artifact",
        '    if not raw:\n        return {"raw_present": True, "verdict": "PASS"}',
        (
            "tests/scripts/test_verifier_config.py::test_artifact_from_verification_text_keeps_empty_input_as_nonterminal",
        ),
    ),
    MutationSpec(
        "summary-badge-none",
        "tools/post_ci_summary.py",
        '        return "⏳"',
        '        return "broken"',
        (
            "tests/test_post_ci_summary.py::test_display_helpers_prioritize_and_render_all_state_families",
        ),
    ),
    MutationSpec(
        "summary-required-groups",
        "tools/post_ci_summary.py",
        '            groups.append({"label": matches[0], "patterns": patterns})',
        '            groups.append({"label": "Broken", "patterns": patterns})',
        (
            "tests/test_post_ci_summary.py::test_required_group_loading_handles_invalid_and_valid_configurations",
        ),
    ),
    MutationSpec(
        "summary-junit",
        "tools/post_ci_summary.py",
        '                _append_line(failures, f\'File "{file_attr}"{line_suffix}\', limit)',
        '                _append_line(failures, "broken junit", limit)',
        (
            "tests/test_post_ci_summary.py::test_collect_junit_failures_and_triage_limits",
        ),
    ),
    MutationSpec(
        "summary-docs-only",
        "tools/post_ci_summary.py",
        "    return seen_skipped",
        "    return False",
        (
            "tests/test_post_ci_summary.py::test_summary_helpers_render_empty_and_docs_only_paths",
        ),
    ),
    MutationSpec(
        "summary-format-percent",
        "tools/post_ci_summary.py",
        "    except (TypeError, ValueError):\n        return None",
        "    except (TypeError, ValueError):\n        return \"broken\"",
        (
            "tests/test_post_ci_summary.py::test_format_helpers_and_main_stdout_handle_non_json_environment",
        ),
    ),
    MutationSpec(
        "summary-load-json-env",
        "tools/post_ci_summary.py",
        "    return parsed if isinstance(parsed, Mapping) else None",
        "    return None",
        (
            "tests/test_post_ci_summary.py::test_loading_helpers_tolerate_missing_malformed_and_alternate_shapes",
        ),
    ),
    MutationSpec(
        "summary-check-failures",
        "tools/post_ci_summary.py",
        '            lines.append("mypy type check failed")',
        '            lines.append("broken type check")',
        (
            "tests/test_post_ci_summary.py::test_artifact_failure_collection_handles_invalid_files_and_all_failure_outcomes",
        ),
    ),
    MutationSpec(
        "summary-xml-strip",
        "tools/post_ci_summary.py",
        "    return unescape(re.sub(r\"<[^>]+>\", \"\", xml_text))",
        "    return \"broken\"",
        (
            "tests/test_post_ci_summary.py::test_xml_helpers_cache_patterns_decode_attributes_and_strip_tags",
        ),
    ),
    MutationSpec(
        "summary-dedupe",
        "tools/post_ci_summary.py",
        '            parts.append(f"{badge} {state_display} — {display}")',
        '            parts.append("broken absent")',
        (
            "tests/test_post_ci_summary.py::test_run_rendering_and_deduplication_cover_missing_and_jobless_records",
        ),
    ),
    MutationSpec(
        "summary-required-segments",
        "tools/post_ci_summary.py",
        '        segments.append(f"{display_label}: {_badge(state)} {_display_state(state)}")',
        '        segments.append("broken segment")',
        (
            "tests/test_post_ci_summary.py::test_required_segments_skip_bad_patterns_and_render_canonical_match",
        ),
    ),
    MutationSpec(
        "summary-playbook-unavailable",
        "tools/post_ci_summary.py",
        '    invalid = "unavailable playbook URL"',
        '    invalid = "broken playbook URL"',
        (
            "tests/test_post_ci_summary.py::test_triage_and_playbook_helpers_reject_unusable_inputs",
        ),
    ),
    MutationSpec(
        "summary-derive-groups",
        "tools/post_ci_summary.py",
        '            label = f"{display} / {name}" if display else name',
        '            label = "broken / label"',
        (
            "tests/test_post_ci_summary.py::test_job_group_derivation_and_category_collection_ignore_malformed_records",
        ),
    ),
    MutationSpec(
        "summary-fallback-groups",
        "tools/post_ci_summary.py",
        '        "label": "core tests (3.13)",',
        '        "label": "broken core tests",',
        (
            "tests/test_post_ci_summary.py::test_required_group_configuration_falls_back_when_no_usable_groups[{}]",
            "tests/test_post_ci_summary.py::test_required_group_configuration_falls_back_when_no_usable_groups[[null]]",
            "tests/test_post_ci_summary.py::test_required_group_configuration_falls_back_when_no_usable_groups[[{\"label\": \"\", \"patterns\": [\"x\"]}]]",
        ),
    ),
    MutationSpec(
        "summary-required-contexts",
        "tools/post_ci_summary.py",
        "                if value:\n                    contexts.append(value)",
        "                if False and value:\n                    contexts.append(value)",
        (
            "tests/test_post_ci_summary.py::test_required_contexts_accepts_list_and_filters_blank_values",
        ),
    ),
    MutationSpec(
        "summary-format-coverage-lines",
        "tools/post_ci_summary.py",
        '        lines.append(f"- Coverage (jobs): {\' | \'.join(avg_parts)}")',
        '        lines.append("broken coverage line")',
        (
            "tests/test_post_ci_summary.py::test_formatting_helpers_render_complete_coverage_and_run_variants",
        ),
    ),
    MutationSpec(
        "summary-main-output",
        "tools/post_ci_summary.py",
        '            handle.write(f"body<<EOF\\n{body}\\nEOF\\n")',
        '            handle.write(f"broken<<EOF\\n{body}\\nEOF\\n")',
        (
            "tests/test_post_ci_summary.py::test_main_ignores_non_list_runs_and_uses_output_path",
        ),
    ),
)


def read_file(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def write_file(rel: str, text: str) -> None:
    (ROOT / rel).write_text(text, encoding="utf-8")


def run_pytest(node_id: str) -> tuple[int, str]:
    proc = subprocess.run(
        [PY, "-m", "pytest", node_id, "-q", "--no-cov"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    tail = (proc.stdout + proc.stderr)[-2000:]
    return proc.returncode, tail


def main() -> int:
    proofs: list[dict] = []
    failures: list[str] = []
    for spec in MUTATIONS:
        path = ROOT / spec.rel_path
        original = path.read_text(encoding="utf-8")
        if spec.old not in original:
            failures.append(f"{spec.mutation_id}: old snippet not found in {spec.rel_path}")
            continue
        mutated = original.replace(spec.old, spec.new, 1)
        path.write_text(mutated, encoding="utf-8")
        case_results = []
        try:
            for node_id in spec.node_ids:
                red_code, red_out = run_pytest(node_id)
                path.write_text(original, encoding="utf-8")
                green_code, green_out = run_pytest(node_id)
                path.write_text(mutated, encoding="utf-8")
                case_results.append(
                    {
                        "node_id": node_id,
                        "red_exit": red_code,
                        "green_exit": green_code,
                        "red_tail": red_out,
                        "green_tail": green_out,
                    }
                )
                if red_code == 0:
                    failures.append(f"{node_id}: expected RED under {spec.mutation_id}")
                if green_code != 0:
                    failures.append(f"{node_id}: expected GREEN after restore under {spec.mutation_id}")
        finally:
            path.write_text(original, encoding="utf-8")
        proofs.append(
            {
                "mutation_id": spec.mutation_id,
                "file": spec.rel_path,
                "old": spec.old,
                "new": spec.new,
                "cases": case_results,
            }
        )

    out = ROOT / "docs/evidence/issue-4013/deliberate-break-proof.json"
    out.write_text(json.dumps({"proofs": proofs, "failures": failures}, indent=2), encoding="utf-8")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"wrote {out} ({len(proofs)} mutations, {sum(len(p['cases']) for p in proofs)} node runs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
