#!/usr/bin/env python3
"""Generate coverage trend analysis from coverage outputs.

This script compares current coverage against a baseline and generates trend
artifacts for CI reporting, including low-coverage hotspot files.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    """Load JSON from a file, returning empty dict on error."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        return {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# The keys a `config/coverage-baseline.json` may use for the percentage. BOTH are real and
# both are in service today: stranske/Workflows and stranske/learning-management-system write
# `coverage`, stranske/Trend_Model_Project writes `line`. `tools/coverage_guard.py` -- the OTHER
# consumer of the very same file -- has always read `payload.get("line", payload.get("coverage"))`,
# so the two scripts disagreed about their shared config and only one of them said so.
BASELINE_KEYS = ("line", "coverage")


# Why `baseline` is Optional and never 0.0: this function used to return a bare float, defaulting
# to 0.0 whenever the file was missing, unparseable, or keyed differently. That made ONE sentinel
# mean two opposite things -- "there is no baseline to compare against" and "the baseline is zero"
# -- and only the second is a measurement. The visible result was a summary reading
# `Baseline 0.00% | Delta +83.32% | Status Pass` on a repo whose baseline file says 85.0 and whose
# real coverage of 83.32% is a BREACH. A comparison against a silently-absent baseline cannot fail,
# so it was reporting success at the exact moment it had nothing to report.
def _resolve_baseline(path: Path | None) -> tuple[float | None, str]:
    """Return (baseline, status). `None` means NOT CONFIGURED -- never the number zero.

    status is one of: ok, unset, absent, unreadable, no_recognised_key. Each names a different
    fix, which is the whole point of not collapsing them: `absent` means write the file,
    `no_recognised_key` means it is there and this script cannot read it.
    """
    if path is None:
        return None, "unset"
    if not path.exists():
        return None, "absent"
    payload = _load_json(path)
    if not payload:
        return None, "unreadable"
    for key in BASELINE_KEYS:
        if key in payload:
            try:
                return float(payload[key]), "ok"
            except (TypeError, ValueError):
                return None, "unreadable"
    return None, "no_recognised_key"


def _partition_files(
    files: dict[str, Any], project_root: Path | None
) -> tuple[dict[str, Any], list[str]]:
    """Split coverage rows into rows inside the project and rows measured somewhere else.

    A test that copies the source tree into a tmpdir and exercises the copy makes coverage.py
    record BOTH: the real module under its relative path, and the copy under an absolute
    `/tmp/...` path. The copy is barely executed, so it sorts to the top of every hotspot table
    and is counted a second time in the total. Observed on stranske/Trend_Model_Project, where 13
    of the 15 reported worst files were
    `/tmp/pytest-of-runner/pytest-0/popen-gw0/test_autofix_pipeline_repairs_0/workspace/src/...`
    -- paths that do not exist in the repository, so the one actionable output of this script
    pointed at files nobody could open.

    Relative paths are always in-project: coverage.py records repo files relative to the run root,
    so an ABSOLUTE path outside that root is the tell. Reported, never silently dropped from the
    headline number -- see `current_project_only`.
    """
    if project_root is None:
        return files, []
    root = project_root.resolve()
    inside: dict[str, Any] = {}
    foreign: list[str] = []
    for filepath, data in files.items():
        candidate = Path(filepath)
        if candidate.is_absolute() and not candidate.resolve().is_relative_to(root):
            foreign.append(filepath)
        else:
            inside[filepath] = data
    return inside, foreign


def _percent_from_rows(files: dict[str, Any]) -> float | None:
    """Recompute a coverage percentage from per-file rows, or None when there are none.

    ON THE SAME BASIS AS `current`, which is coverage.py's `totals.percent_covered`. With branch
    coverage enabled that is (covered_lines + covered_branches) over (statements + branches), NOT
    statements alone -- coverage.py reports the statements-only figure separately, as
    `percent_statements_covered`.

    The first version summed lines only, and the failure did not look like a failure: it produced
    a plausible number about three points away, so `current_project_only` read as though
    contamination had cost three points on repos where NOTHING was contaminated. Measured on
    stranske/Pension-Data (foreign_file_count 0): statements-only 90.96%, line+branch 87.78%, and
    coverage.py's own percent_covered 87.78%. The invariant that catches it is cheap and is now a
    test -- with no foreign rows this MUST equal `current`.
    """
    covered = 0
    missing = 0
    covered_branches = 0
    num_branches = 0
    for data in files.values():
        summary = data.get("summary", {}) if isinstance(data, dict) else {}
        covered += int(summary.get("covered_lines", 0) or 0)
        missing += int(summary.get("missing_lines", 0) or 0)
        covered_branches += int(summary.get("covered_branches", 0) or 0)
        num_branches += int(summary.get("num_branches", 0) or 0)
    denominator = covered + missing + num_branches
    if denominator <= 0:
        return None
    return (covered + covered_branches) / denominator * 100.0


def _extract_coverage_percent(coverage_json: dict[str, Any]) -> float:
    """Extract overall coverage percentage from coverage.json."""
    totals = coverage_json.get("totals", {})
    return float(totals.get("percent_covered", 0.0))


def _get_hotspots(
    coverage_json: dict[str, Any],
    limit: int = 15,
    low_threshold: float = 50.0,
    project_root: Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract hotspot files from coverage.json.

    `project_root` defaults to None, which keeps every row -- the behaviour callers had before
    contamination filtering existed. Pass a root to drop rows measured outside the project.
    The two-value return shape is deliberately preserved because consumer repositories call this
    helper directly; callers that need the excluded paths can use ``_partition_files``.

    Returns:
        Tuple of (all_hotspots sorted by coverage, low_coverage_files below threshold)
    """
    files, _foreign = _partition_files(coverage_json.get("files", {}), project_root)
    all_files = []

    for filepath, data in files.items():
        summary = data.get("summary", {})
        percent = summary.get("percent_covered", 0.0)
        missing = summary.get("missing_lines", 0)
        covered = summary.get("covered_lines", 0)
        all_files.append(
            {
                "file": filepath,
                "coverage": percent,
                "missing_lines": missing,
                "covered_lines": covered,
            }
        )

    # Sort by coverage ascending (lowest first)
    all_files.sort(key=lambda x: x["coverage"])

    # Split into hotspots and low coverage
    hotspots = all_files[:limit]
    low_coverage = [f for f in all_files if f["coverage"] < low_threshold][:limit]

    return hotspots, low_coverage


def _format_hotspot_table(files: list[dict[str, Any]], title: str) -> str:
    """Format a markdown table of hotspot files."""
    if not files:
        return ""

    lines = [
        f"### {title}",
        "",
        "| File | Coverage | Missing |",
        "|------|----------|---------|",
    ]

    for f in files:
        lines.append(f"| `{f['file']}` | {f['coverage']:.1f}% | {f['missing_lines']} |")

    lines.append("")
    return "\n".join(lines)


def main(args: list[str] | None = None) -> int:
    """Main entry point for coverage trend analysis."""
    parser = argparse.ArgumentParser(description="Coverage trend analysis")
    parser.add_argument("--coverage-xml", type=Path, help="Path to coverage.xml")
    parser.add_argument("--coverage-json", type=Path, help="Path to coverage.json")
    parser.add_argument("--baseline", type=Path, help="Path to baseline JSON")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help=(
            "Project root used to tell repository files from files a test copied elsewhere "
            "(coverage rows with an absolute path outside this root). Defaults to the cwd."
        ),
    )
    parser.add_argument("--summary-path", type=Path, help="Path to output summary markdown")
    parser.add_argument("--job-summary", type=Path, help="Path to GITHUB_STEP_SUMMARY")
    parser.add_argument("--artifact-path", type=Path, help="Path to output trend artifact")
    parser.add_argument("--github-output", type=Path, help="Path to write env file")
    parser.add_argument("--minimum", type=float, default=70.0, help="Minimum coverage threshold")
    parser.add_argument("--hotspot-limit", type=int, default=15, help="Max hotspot files to show")
    parser.add_argument("--low-threshold", type=float, default=50.0, help="Low coverage threshold")
    parser.add_argument(
        "--soft", action="store_true", help="Soft gate mode - report only, always exit 0"
    )
    parsed = parser.parse_args(args)

    # Load current coverage
    coverage_data = {}
    current_coverage = 0.0
    if parsed.coverage_json and parsed.coverage_json.exists():
        coverage_data = _load_json(parsed.coverage_json)
        current_coverage = _extract_coverage_percent(coverage_data)

    # Load baseline. None means not configured; it is NEVER swapped for 0.0 (see _resolve_baseline).
    baseline_coverage, baseline_status = _resolve_baseline(parsed.baseline)

    # Calculate delta. Absent baseline -> absent delta, rather than a delta against zero that
    # renders as a large improvement on every run.
    delta = None if baseline_coverage is None else current_coverage - baseline_coverage
    passes_minimum = current_coverage >= parsed.minimum

    # Get hotspots
    hotspots, low_coverage = _get_hotspots(
        coverage_data,
        limit=parsed.hotspot_limit,
        low_threshold=parsed.low_threshold,
        project_root=parsed.project_root,
    )
    project_files, foreign_files = _partition_files(
        coverage_data.get("files", {}), parsed.project_root
    )
    project_only = _percent_from_rows(project_files)

    # Generate trend record
    trend_record = {
        "current": current_coverage,
        "baseline": baseline_coverage,
        "baseline_status": baseline_status,
        "delta": delta,
        "minimum": parsed.minimum,
        "passes_minimum": passes_minimum,
        "hotspot_count": len(hotspots),
        "low_coverage_count": len(low_coverage),
        # Contamination reporting. `current` stays exactly as coverage.py computed it, so this
        # record still agrees with coverage.xml and with the delta job; the project-only figure
        # sits BESIDE it, and the gap between the two is the size of the problem.
        "foreign_file_count": len(foreign_files),
        "foreign_files": foreign_files[:10],
        "current_project_only": project_only,
    }

    # Write outputs
    if parsed.artifact_path:
        parsed.artifact_path.parent.mkdir(parents=True, exist_ok=True)
        # Include hotspots in artifact for downstream processing
        artifact_data = {
            **trend_record,
            "hotspots": hotspots,
            "low_coverage_files": low_coverage,
        }
        parsed.artifact_path.write_text(json.dumps(artifact_data, indent=2), encoding="utf-8")

    status = "✅ Pass" if passes_minimum else "❌ Below minimum"
    if baseline_coverage is None:
        baseline_cell = f"⚠️ not configured ({baseline_status})"
        delta_cell = "n/a — nothing to compare against"
    else:
        baseline_cell = f"{baseline_coverage:.2f}%"
        delta_cell = f"{delta:+.2f}%"
    summary = f"""## Coverage Trend

| Metric | Value |
|--------|-------|
| Current | {current_coverage:.2f}% |
| Baseline | {baseline_cell} |
| Delta | {delta_cell} |
| Minimum | {parsed.minimum:.2f}% |
| Status | {status} |

"""

    if baseline_coverage is None:
        summary += (
            f"> **No baseline was read ({baseline_status}), so the delta above is not a "
            "measurement.** `Status` reflects only the `--minimum` floor. Write "
            "`config/coverage-baseline.json` with a `line` or `coverage` percentage to enable "
            "the comparison; that file is deliberately not synced from Workflows, so each repo "
            "owns its own.\n\n"
        )

    if foreign_files and not hotspots:
        summary += (
            f"> **⚠️ EVERY coverage row ({len(foreign_files)}) is outside `{parsed.project_root}`, "
            "so nothing could be attributed to this project.** That is almost certainly a wrong "
            "`--project-root`, not a contaminated test run — a real fixture copy leaves the "
            "genuine rows behind. Check the working directory the reporter runs in before reading "
            "anything below.\n\n"
        )
    elif foreign_files:
        shown = "\n".join(f"> - `{path}`" for path in foreign_files[:5])
        more = f"\n> - …and {len(foreign_files) - 5} more" if len(foreign_files) > 5 else ""
        project_cell = f"{project_only:.2f}%" if project_only is not None else "not computable"
        summary += (
            f"> **⚠️ {len(foreign_files)} file(s) were measured OUTSIDE the project root, so "
            f"`Current` above is contaminated.** A test is copying the source tree somewhere "
            f"else and exercising the copy, so those modules are counted twice — once as "
            f"themselves and once as a barely-executed duplicate. Project-only coverage is "
            f"**{project_cell}**. They are excluded from the tables below because their paths do "
            f"not exist in the repository. Fix by adding the copy location to "
            f"`[tool.coverage.run] omit`.\n{shown}{more}\n\n"
        )

    # Add hotspot tables if we have coverage data
    if hotspots:
        summary += _format_hotspot_table(hotspots, "Top Coverage Hotspots (lowest coverage)")

    if low_coverage:
        summary += _format_hotspot_table(
            low_coverage,
            f"Low Coverage Files (<{parsed.low_threshold}%)",
        )

    if parsed.summary_path:
        parsed.summary_path.parent.mkdir(parents=True, exist_ok=True)
        parsed.summary_path.write_text(summary, encoding="utf-8")

    if parsed.job_summary and parsed.job_summary.exists():
        with parsed.job_summary.open("a", encoding="utf-8") as f:
            f.write(summary)

    if parsed.github_output:
        parsed.github_output.parent.mkdir(parents=True, exist_ok=True)
        with parsed.github_output.open("w", encoding="utf-8") as f:
            # Plain locals rather than f-strings nested inside f-strings: the nested form is
            # valid only from 3.12 (PEP 701) and this file ships to 3.12 AND 3.13 runners.
            baseline_out = "" if baseline_coverage is None else f"{baseline_coverage:.2f}"
            delta_out = "" if delta is None else f"{delta:.2f}"
            f.write(f"coverage={current_coverage:.2f}\n")
            # Empty, not 0.00, when there is no baseline: a reader testing `-n "$baseline"` then
            # sees the difference, where 0.00 is indistinguishable from a real measurement.
            f.write(f"baseline={baseline_out}\n")
            f.write(f"baseline_status={baseline_status}\n")
            f.write(f"delta={delta_out}\n")
            f.write(f"passes_minimum={'true' if passes_minimum else 'false'}\n")
            f.write(f"hotspot_count={len(hotspots)}\n")
            f.write(f"low_coverage_count={len(low_coverage)}\n")
            f.write(f"foreign_file_count={len(foreign_files)}\n")

    if baseline_coverage is None:
        print(
            f"Coverage: {current_coverage:.2f}% "
            f"(no baseline: {baseline_status} — delta not computed)"
        )
    else:
        print(
            f"Coverage: {current_coverage:.2f}% "
            f"(baseline: {baseline_coverage:.2f}%, delta: {delta:+.2f}%)"
        )
    if foreign_files:
        project_only_out = "n/a" if project_only is None else f"{project_only:.2f}%"
        print(
            f"WARNING: {len(foreign_files)} file(s) measured outside the project root; "
            f"`Current` is contaminated (project-only: {project_only_out})"
        )
    if hotspots:
        print(f"Hotspots: {len(hotspots)} files with lowest coverage")

    # In soft mode, always return 0 (report only, don't fail build)
    if parsed.soft:
        return 0
    return 0 if passes_minimum else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
