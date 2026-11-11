#!/usr/bin/env python3
"""Reproduce each new test's deliberate break and exact byte restoration.

Run from the repository root, without another pytest process using these modules.
Every mutation preserves rejection of unsafe inputs. No change survives a probe.
"""

from __future__ import annotations

import difflib
import gzip
import hashlib
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).resolve().parent
DRIFT = "scripts/check_consumer_sync_drift.py"
CONTRACT = "scripts/validate_run_contract.py"
METRICS = "scripts/aggregate_agent_metrics.py"

# (module, test function, expected cases, exact replacements)
PROBES = (
    (
        DRIFT,
        "test_remote_tree_transport_failure_preserves_unknown",
        4,
        (
            (
                'None,\n            f"{repo}: repository access preflight failed (requests.',
                '{},\n            f"{repo}: repository access preflight failed (requests.',
            ),
            (
                'None,\n            f"{repo}: repository tree fetch failed (requests.',
                '{},\n            f"{repo}: repository tree fetch failed (requests.',
            ),
        ),
    ),
    (
        DRIFT,
        "test_main_caches_failed_blob_reads_by_repo_and_sha",
        1,
        (("if key not in blob_text_cache:", "if blob_text_cache.get(key) is None:"),),
    ),
    (
        CONTRACT,
        "test_consumer_schema_fails_closed_without_required_format",
        3,
        (
            (
                "def _validator_for_schema(schema_dir: Path, name: str) -> Draft202012Validator:\n"
                "    schema = _load_schema(schema_dir, name)\n",
                "def _validator_for_schema(schema_dir: Path, name: str) -> Draft202012Validator:\n"
                "    schema = _load_schema(schema_dir, name)\n"
                "    if name in ('mosaic-core-v1.schema.json', 'document-mirror-v1.schema.json'):\n"
                "        raise RuntimeError('schema loading regression')\n",
            ),
        ),
    ),
    (
        CONTRACT,
        "test_consumer_mirror_enforces_catalog_timestamp",
        2,
        (
            (
                'ingests = entry.get("ingests", []) or []\n',
                'ingests = entry.get("ingests", []) or []\n'
                '    if "document-mirror/v1" in ingests:\n'
                '        report.fail("mirror routing regression", "ingests")\n',
            ),
        ),
    ),
    (
        CONTRACT,
        "test_main_rejects_unreadable_artifact_manifest",
        3,
        (
            (
                'print(f"ERROR: cannot load artifact manifest {args.manifest}: {exc}", file=sys.stderr)\n'
                "            return 2",
                'print(f"ERROR: cannot load artifact manifest {args.manifest}: {exc}", file=sys.stderr)\n'
                "            return 1",
            ),
        ),
    ),
    (
        CONTRACT,
        "test_main_persists_valid_run_conformance",
        1,
        (("ok = report.conformant or report.skipped", "ok = False"),),
    ),
    (
        CONTRACT,
        "test_mirror_cli_reports_without_optional_output_files",
        1,
        (("file(s) conform to schema", "file(s) rejected by schema"),),
    ),
    (
        CONTRACT,
        "test_self_smoke_rejects_incomplete_schema_inventory",
        2,
        (
            (
                "return 1\n    missing = sorted(set(INGEST_SCHEMA_FILES.values())",
                "return 2\n    missing = sorted(set(INGEST_SCHEMA_FILES.values())",
            ),
            ("return 1\n    for name in schema_names:", "return 2\n    for name in schema_names:"),
        ),
    ),
    (
        METRICS,
        "test_verifier_ledger_counts_escalations_without_duplicating_shared_followups",
        1,
        (("ledger_needs_human += 1", "ledger_needs_human += 2"),),
    ),
)


def run_probe(module: str, test: str, cases: int, replacements: tuple) -> str:
    path = ROOT / module
    original = path.read_bytes()
    source = original.decode()
    changed = source
    for old, new in replacements:
        if changed.count(old) != 1:
            raise ValueError(f"{test}: replacement must match exactly once: {old!r}")
        changed = changed.replace(old, new, 1)
    patch = "".join(
        difflib.unified_diff(
            source.splitlines(keepends=True),
            changed.splitlines(keepends=True),
            fromfile=module,
            tofile=module,
        )
    )
    revert = "".join(
        difflib.unified_diff(
            changed.splitlines(keepends=True),
            source.splitlines(keepends=True),
            fromfile=module,
            tofile=module,
        )
    )
    test_file = "tests/scripts/test_" + Path(module).name
    command = [
        sys.executable,
        "-m",
        "pytest",
        f"{test_file}::{test}",
        "-m",
        "not slow",
        "--tb=short",
        "-q",
    ]
    transcript = f"# {test}\n\nDeliberate break:\n```diff\n{patch}```\n"
    try:
        path.write_text(changed)
        red = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=90)
        transcript += f"\n$ {shlex.join(command)}\n{red.stdout}{red.stderr}exit={red.returncode}\n"
    finally:
        path.write_bytes(original)
        assert path.read_bytes() == original
    transcript += f"\nExact reversion:\n```diff\n{revert}```\n"
    transcript += f"Restored source SHA-256: {hashlib.sha256(original).hexdigest()}\n"
    green = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=90)
    transcript += (
        f"\n$ {shlex.join(command)}\n{green.stdout}{green.stderr}exit={green.returncode}\n"
    )
    (EVIDENCE / "mutations").mkdir(exist_ok=True)
    (EVIDENCE / "mutations" / f"{test}.md.gz").write_bytes(
        gzip.compress(transcript.encode(), mtime=0)
    )
    (EVIDENCE / "mutations" / f"{test}.md").write_text(
        "\n".join(line.rstrip() for line in transcript.splitlines()) + "\n"
    )
    if red.returncode != 1 or f"{cases} failed" not in red.stdout:
        raise AssertionError(f"{test}: expected every case to fail; see transcript")
    if green.returncode != 0 or f"{cases} passed" not in green.stdout:
        raise AssertionError(f"{test}: expected every case to pass; see transcript")
    return f"{test}: {cases} failed under break, {cases} passed after exact restoration"


def main() -> int:
    for probe in PROBES:
        print(run_probe(*probe), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
