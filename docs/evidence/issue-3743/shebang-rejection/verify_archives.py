"""Open every delivered shebang-rejection archive and check current bindings.

Historical proof archives stay historical: their member hashes must verify, and
their input hashes are not required to equal the tree. Current acceptance
bindings in the acceptance run, validation run, and matched comparison must
equal the tree. The generated note records that split, the interpreter paths
actually stored in those receipts, and the measured validation file counts.
"""

from __future__ import annotations

import hashlib
import json
import runpy
import tarfile
from collections import Counter
from pathlib import Path

EVIDENCE = Path("docs/evidence/issue-3743/shebang-rejection")
DOC = EVIDENCE / "current-acceptance.md"
HISTORICAL = (
    EVIDENCE / "summary.json",
    EVIDENCE / "path-lookup/summary.json",
    EVIDENCE / "replay-validation/summary.json",
)
CURRENT = (
    EVIDENCE / "matched-comparison/summary.json",
    EVIDENCE / "raw-comparison-validation/summary.json",
)
COUNT_LABELS = (
    ("black_files", "Black files left unchanged"),
    ("ruff_files", "Focused Ruff paths"),
    ("workflows_directory_yml", "Workflow directory YAML files"),
    ("template_directory_yml", "Template workflow YAML files"),
    ("manifest_workflow_targets", "Manifest workflow targets"),
    ("strict_validation_inputs", "Strict validation input files"),
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_archive(root: Path, summary_rel: Path, kind: str) -> dict:
    """Require unique regular-file members and check every manifest hash and length."""
    summary_path = root / summary_rel
    summary = read_json(summary_path)
    meta = summary["archive"]
    archive = summary_path.parent / meta["path"]
    payload = archive.read_bytes()
    mismatches: list[str] = []
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        counts = Counter(member.name for member in members)
        mismatches.extend(f"{name}:duplicate" for name, count in counts.items() if count != 1)
        manifest_member = tar.getmember("manifest.json")
        if not manifest_member.isfile():
            raise ValueError(f"{archive} manifest.json is not a regular file")
        extracted = tar.extractfile(manifest_member)
        if extracted is None:
            raise ValueError(f"{archive} has no manifest.json")
        manifest_bytes = extracted.read()
        manifest = json.loads(manifest_bytes)
        names = {member.name for member in members if member.isfile()}
        for member in members:
            if not member.isfile():
                mismatches.append(f"{member.name}:not-regular-file")
                continue
            if member.name == "manifest.json":
                continue
            body_file = tar.extractfile(member)
            if body_file is None:
                mismatches.append(member.name)
                continue
            body = body_file.read()
            spec = manifest.get(member.name)
            if spec is None:
                mismatches.append(f"{member.name}:unmanifested")
                continue
            if digest(body) != spec["sha256"] or len(body) != spec["bytes"]:
                mismatches.append(member.name)
            if kind == "current" and body != (summary_path.parent / member.name).read_bytes():
                mismatches.append(f"{member.name}:loose")
    checked = {
        "summary": summary_rel.as_posix(),
        "kind": kind,
        "archive": archive.relative_to(root).as_posix(),
        "members": len(manifest),
        "sha256_matches_summary": digest(payload) == meta["sha256"],
        "bytes_match_summary": len(payload) == meta["bytes"],
        "manifest_sha256_matches_summary": digest(manifest_bytes) == meta["manifest_sha256"],
        "member_count_matches_summary": len(manifest) == meta["verified_manifest_members"],
        "manifest_covers_archive_files": names - {"manifest.json"} == set(manifest),
        "member_mismatches": mismatches,
    }
    flags = (
        "sha256_matches_summary",
        "bytes_match_summary",
        "manifest_sha256_matches_summary",
        "member_count_matches_summary",
        "manifest_covers_archive_files",
    )
    checked["verified"] = all(checked[flag] for flag in flags) and not mismatches
    return checked


def _problem(problems: list[str], condition: bool, message: str) -> None:
    if not condition:
        problems.append(message)


def verify_comparison(root: Path, summary: dict) -> dict:
    """Recompute counts and outcomes; archive integrity cannot certify summary claims."""
    compare = runpy.run_path(str(root / EVIDENCE / "compare_matched.py"))
    directory = root / EVIDENCE / "matched-comparison"
    computed = compare["build_comparison"](
        compare["junit_nodes"](directory / "baseline.xml"),
        compare["junit_nodes"](directory / "candidate.xml"),
        read_json(directory / "baseline.json"),
        read_json(directory / "candidate.json"),
        compare["expected_added_nodes"](root),
    )
    if summary["comparison"] != computed:
        raise ValueError("summary comparison drifted from raw inputs")
    if read_json(directory / "comparison.json") != computed:
        raise ValueError("stored comparison drifted from raw inputs")
    problems = compare["contract_errors"](computed)
    if problems:
        raise ValueError("; ".join(problems))
    return computed


def _current_bindings(root: Path, problems: list[str]) -> None:
    matched_summary = read_json(root / CURRENT[0])
    bindings = matched_summary["input_sha256"]
    stored = read_json(root / EVIDENCE / "matched-comparison/input-bindings.json")
    _problem(problems, stored == bindings, "matched input-bindings.json drifted from summary")
    for relative, spec in bindings.items():
        data = (root / relative).read_bytes()
        _problem(
            problems,
            digest(data) == spec["sha256"] and len(data) == spec["bytes"],
            f"current binding drifted: {relative}",
        )
    acceptance = runpy.run_path(str(root / EVIDENCE / "capture_acceptance_run.py"))
    acceptance_summary = read_json(root / EVIDENCE / "acceptance-run/summary.json")
    _problem(
        problems,
        acceptance["tree_digests"](root, acceptance["HISTORICAL"])
        == acceptance_summary["historical_sha256"],
        "acceptance-run historical bindings drifted",
    )
    for relative, expected in acceptance_summary["production_sha256"].items():
        _problem(
            problems,
            digest((root / relative).read_bytes()) == expected,
            f"acceptance-run production binding drifted: {relative}",
        )
    validation = runpy.run_path(str(root / EVIDENCE / "capture_validation_run.py"))
    validation_summary = read_json(root / EVIDENCE / "validation-run/summary.json")
    _problem(
        problems,
        validation["historical_digests"](root) == validation_summary["historical_sha256"],
        "validation-run historical bindings drifted",
    )
    measured = validation_summary["measured_file_counts"]
    recounted = validation["template_file_counts"](root)
    for key in (
        "workflows_directory_yml",
        "template_directory_yml",
        "manifest_workflow_targets",
        "strict_validation_inputs",
    ):
        _problem(problems, recounted[key] == measured[key], f"measured count drifted: {key}")
    _problem(problems, measured["black_files"] > 0, "black file count was not recorded")
    _problem(
        problems,
        measured["ruff_files"] == len(validation["FOCUSED_RUFF"]),
        "ruff file count drifted",
    )
    for summary in CURRENT[1:]:
        for relative, spec in read_json(root / summary)["input_sha256"].items():
            data = (root / relative).read_bytes()
            _problem(
                problems,
                digest(data) == spec["sha256"] and len(data) == spec["bytes"],
                f"current binding drifted: {relative}",
            )


def collect(root: Path) -> dict:
    """Verify archives and bindings. The returned report is safe to render."""
    problems: list[str] = []
    archives = [verify_archive(root, path, "historical") for path in HISTORICAL]
    archives.extend(verify_archive(root, path, "current") for path in CURRENT)
    for archive in archives:
        _problem(problems, archive["verified"], f"archive verification failed: {archive}")
    _current_bindings(root, problems)
    inspector = runpy.run_path(str(root / EVIDENCE / "inspect_main_acceptance.py"))
    rows = inspector["binding_rows"](root)
    copies_ok = all(row["archive_copy_matches_summary"] is True for row in rows)
    _problem(problems, copies_ok, "historical archive input copy does not match its summary")
    validation_summary = read_json(root / EVIDENCE / "validation-run/summary.json")
    acceptance_summary = read_json(root / EVIDENCE / "acceptance-run/summary.json")
    matched_summary = read_json(root / CURRENT[0])
    comparison = verify_comparison(root, matched_summary)
    interpreters = validation_summary["interpreters"]
    return {
        "problems": problems,
        "archives": archives,
        "historical_input_mismatches": sum(row["status"] == "mismatch" for row in rows),
        "interpreters": {
            "acceptance_run": acceptance_summary["receipt_interpreter"],
            "matched_comparison": matched_summary["interpreter"]["path"],
            "validation_python": interpreters["python"]["path"],
            "validation_black": interpreters["black"]["path"],
            "validation_ruff": interpreters["ruff"]["path"],
        },
        "measured_file_counts": validation_summary["measured_file_counts"],
        "matched_comparison": {
            "added": len(comparison["added_nodes"]),
            "removed": len(comparison["removed_nodes"]),
            "changed": len(comparison["changed_old_outcomes"]),
            "universes_identical": comparison["universes_identical"],
            "exclusions": comparison["exclusions"],
            "line_regressions": len(comparison["covered_line_regressions"]),
            "branch_regressions": len(comparison["covered_branch_regressions"]),
        },
    }


def render(report: dict) -> str:
    """Describe historical receipts separately from the current acceptance records."""
    interpreters = report["interpreters"]
    comparison = report["matched_comparison"]
    lines = [
        "# Current shebang-rejection acceptance",
        "",
        "Historical receipts are `README.md`, `summary.json`, `proof.tar.gz`, "
        "`path-lookup/`, and `replay-validation/`.",
        "Their input hashes describe earlier bytes and are not current acceptance.",
        "Historical summary input rows that differ from the tree: "
        f"{report['historical_input_mismatches']}.",
        "Archive-internal copies in those historical receipts still match their own summaries.",
        "",
        "Current acceptance is `acceptance-run/`, `validation-run/`, and `matched-comparison/`.",
        "`raw-comparison-validation/` binds the current verifier and its regression tests; "
        "its literal command attempts returned 127 because the required interpreter is absent.",
        "Current input bindings in those records match the files in this tree.",
        "`main-acceptance-map.json` remains the pre-change inspection record.",
        "",
        "## Actual interpreter paths",
        "",
        f"- Acceptance-run receipt interpreter: `{interpreters['acceptance_run']}`",
        f"- Matched-comparison interpreter: `{interpreters['matched_comparison']}`",
        f"- Validation Python: `{interpreters['validation_python']}`",
        f"- Validation Black: `{interpreters['validation_black']}`",
        f"- Validation Ruff: `{interpreters['validation_ruff']}`",
        "",
        "## Measured validation file counts",
        "",
    ]
    for key, label in COUNT_LABELS:
        lines.append(f"- {label}: {report['measured_file_counts'][key]}")
    lines.extend(["", "## Delivered archives", ""])
    for archive in report["archives"]:
        lines.append(
            f"- {archive['kind']} `{archive['archive']}`: "
            f"{archive['members']} members, verified {archive['verified']}"
        )
    lines.extend(
        [
            "",
            "## Matched comparison",
            "",
            f"Added passing nodes: {comparison['added']}. "
            f"Removed nodes: {comparison['removed']}. "
            f"Changed old outcomes: {comparison['changed']}. "
            f"Universes identical: {comparison['universes_identical']}. "
            f"Exclusions: {comparison['exclusions']}. "
            f"Covered-line regressions: {comparison['line_regressions']}. "
            f"Covered-branch regressions: {comparison['branch_regressions']}.",
            "",
        ]
    )
    return "\n".join(lines)


def validate(root: Path) -> dict:
    """Recompute archive verification and require the acceptance note to match."""
    report = collect(root)
    if report["problems"]:
        raise ValueError("; ".join(report["problems"]))
    note = root / DOC
    if note.read_text(encoding="utf-8") != render(report):
        raise ValueError("current-acceptance.md does not match the verified report")
    return report


def main() -> int:
    root = repo_root()
    report = collect(root)
    if report["problems"]:
        raise SystemExit("; ".join(report["problems"]))
    (root / DOC).write_text(render(report), encoding="utf-8")
    validate(root)
    print(
        json.dumps(
            {
                "archives": len(report["archives"]),
                "historical_input_mismatches": report["historical_input_mismatches"],
                "added_nodes": report["matched_comparison"]["added"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
