#!/usr/bin/env python3
"""Run deliberate-break / revert / pass probes for PR #4012's six added tests."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PYTHON = "/opt/anaconda3/bin/python3"
MARKERS = "not quarantine and not slow"


@dataclass
class Probe:
    test_id: str
    source: str
    before: str
    after: str
    red_exit: int
    green_exit: int
    red_output_tail: str
    green_output_tail: str


PROBES: list[tuple[str, Path, str, str]] = [
    (
        "tests/contracts/test_validate_run_contract.py::test_document_identity_cross_checks_reject_conflicting_or_noncanonical_values",
        ROOT / "scripts/validate_run_contract.py",
        'def _check_document_page(document: Any, report: Report, prefix: str = "") -> None:',
        'def _check_document_page(document: Any, report: Report, prefix: str = "") -> None:\n    return',
    ),
    (
        "tests/contracts/test_validate_run_contract.py::test_standalone_validators_and_evidence_paths_fail_closed_on_unreadable_inputs",
        ROOT / "scripts/validate_run_contract.py",
        '        report.fail("evidence artifact path must not be absolute or traverse parents", path_label)\n        return None',
        '        report.fail("evidence artifact path must not be absolute or traverse parents", path_label)\n        return run_dir',
    ),
    (
        "tests/scripts/test_aggregate_agent_metrics.py::test_metrics_helpers_preserve_empty_and_malformed_input_boundaries",
        ROOT / "scripts/aggregate_agent_metrics.py",
        "def _artifact_family(artifact: str) -> str:",
        'def _artifact_family(artifact: str) -> str:\n    return "broken-family"',
    ),
    (
        "tests/scripts/test_check_consumer_sync_drift.py::test_drift_cli_and_remote_read_boundaries",
        ROOT / "scripts/check_consumer_sync_drift.py",
        'return base64.b64decode(data.get("content", "")).decode("utf-8")',
        'return base64.b64decode(data.get("content", "")).decode("utf-8")[::-1]',
    ),
    (
        "tests/scripts/test_check_consumer_sync_drift.py::test_drift_summary_renders_actionable_nested_report_data",
        ROOT / "scripts/check_consumer_sync_drift.py",
        'handle.write("### Repo summary\\n")',
        'handle.write("### Broken repo summary\\n")',
    ),
    (
        "tests/scripts/test_check_consumer_sync_drift.py::test_drift_network_helpers_fail_closed_without_readable_probe_targets",
        ROOT / "scripts/check_consumer_sync_drift.py",
        'if not candidates:\n        diagnostics["error"] = "no_token_candidates"',
        'if not candidates:\n        diagnostics["error"] = "broken_no_token_candidates"',
    ),
]


def run_pytest(test_id: str) -> tuple[int, str]:
    proc = subprocess.run(
        [
            PYTHON,
            "-m",
            "pytest",
            test_id,
            "-m",
            MARKERS,
            "-q",
            "--tb=short",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    tail = combined[-2000:] if len(combined) > 2000 else combined
    return proc.returncode, tail


def apply_mutation(path: Path, before: str, after: str) -> None:
    text = path.read_text(encoding="utf-8")
    if before not in text:
        raise RuntimeError(f"mutation anchor missing in {path}: {before!r}")
    path.write_text(text.replace(before, after, 1), encoding="utf-8")


def main() -> int:
    results: list[Probe] = []
    for test_id, source, before, after in PROBES:
        original = source.read_text(encoding="utf-8")
        try:
            apply_mutation(source, before, after)
            red_exit, red_tail = run_pytest(test_id)
            apply_mutation(source, after, before)
            green_exit, green_tail = run_pytest(test_id)
        finally:
            source.write_text(original, encoding="utf-8")
        if red_exit == 0:
            raise RuntimeError(f"expected RED for {test_id}, got exit 0")
        if green_exit != 0:
            raise RuntimeError(f"expected GREEN for {test_id}, got exit {green_exit}")
        results.append(
            Probe(
                test_id=test_id,
                source=str(source.relative_to(ROOT)),
                before=before,
                after=after,
                red_exit=red_exit,
                green_exit=green_exit,
                red_output_tail=red_tail,
                green_output_tail=green_tail,
            )
        )
    out = ROOT / "docs/evidence/issue-4001/break-revert-proof.json"
    out.write_text(
        json.dumps({"probes": [asdict(item) for item in results]}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out} ({len(results)} probes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
