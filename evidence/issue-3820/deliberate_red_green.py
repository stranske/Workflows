#!/usr/bin/env python3
"""Reproduce #3820 production mutations, retain RED/GREEN and restore exact bytes."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path(__file__).resolve().parent
JS = ".github/scripts/agents_verifier_context.js"
PYTHON = "scripts/langchain/pr_verifier.py"
WORKFLOW = ".github/workflows/reusable-agents-verifier.yml"
NODE = ["node", "--test"]
SUITE = ".github/scripts/__tests__/agents-verifier-context.test.js"
PYTEST = ["python3", "-m", "pytest", "-q", "--no-cov"]
RECOVERY = "tests/scripts/test_pr_verifier_recovery.py"
MUTATIONS = [
    (
        "single-run-artifact-page",
        JS,
        "page <= pageLimit",
        "page <= 1",
        NODE + ["--test-name-pattern=bounded recovery retrieves late", SUITE],
    ),
    (
        "ignore-incomplete-reference-sources",
        JS,
        "const referenceInspectionComplete = body.complete && comments.complete && referenceSourcesComplete;",
        "const referenceInspectionComplete = true;",
        NODE + ["--test-name-pattern=bounded recovery unions late", SUITE],
    ),
    (
        "ignore-unsupported-archive-payload",
        JS,
        "entries.length > selected.length || filteredPayloadEntries.length > 0;",
        "entries.length > selected.length;",
        NODE + ["--test-name-pattern=archive extractor independently records", SUITE],
    ),
    (
        "remove-global-download-bound",
        JS,
        "diagnostics.counters.archive_bytes + artifact.size_in_bytes > totalArchiveBytes",
        "false",
        NODE + ["--test-name-pattern=bounded recovery archive ceilings", SUITE],
    ),
    (
        "old-expanded-diff-budget",
        WORKFLOW,
        "VERIFIER_DIFF_BUDGET_TOKENS=65536",
        "VERIFIER_DIFF_BUDGET_TOKENS=32000",
        PYTEST + [RECOVERY + "::test_authenticated_capture_replay"],
    ),
    (
        "remove-native-capacity-guard",
        PYTHON,
        "    _preflight_input_capacity(client, prompt)\n    config =",
        "    config =",
        PYTEST + [RECOVERY + "::test_actual_capacity_boundary_counts_entire_rendered_request"],
    ),
    (
        "remove-schema-repair-capacity-guard",
        PYTHON,
        "        _preflight_input_capacity(self.client, prompt)\n",
        "",
        PYTEST + [RECOVERY + "::test_native_message_capacity_and_schema_repair_are_checked"],
    ),
    (
        "disable-incomplete-coverage-floor",
        PYTHON,
        'if coverage.sufficient or result.verdict != "PASS" or not result.used_llm:',
        "if True:",
        PYTEST + [RECOVERY + "::test_authenticated_capture_replay"],
    ),
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def execute(command):
    run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, env=os.environ)
    output = run.stdout + run.stderr
    return {
        "exit": run.returncode,
        "output_sha256": digest(output.encode()),
        "tail": output.splitlines()[-22:],
    }


def main():
    if not os.environ.get("VERIFIER_RECOVERY_CAPTURE_DIR"):
        raise SystemExit("Set VERIFIER_RECOVERY_CAPTURE_DIR to the immutable authenticated capture")
    results = []
    for name, source, before, after, command in MUTATIONS:
        paths = [ROOT / source]
        template = ROOT / "templates/consumer-repo" / source
        if template.is_file():
            paths.append(template)
        originals = {path: path.read_bytes() for path in paths}
        assert all(before.encode() in data for data in originals.values()), name
        try:
            for path, data in originals.items():
                path.write_bytes(data.replace(before.encode(), after.encode()))
            red = execute(command)
        finally:
            for path, data in originals.items():
                path.write_bytes(data)
        restoration = {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in paths}
        assert all(path.read_bytes() == data for path, data in originals.items()), name
        green = execute(command)
        record = {
            "mutation": name,
            "source": source,
            "before": before,
            "after": after,
            "command": command,
            "source_sha256": restoration,
            "restoration_byte_identical": True,
            "red": red,
            "green": green,
        }
        results.append(record)
        (EVIDENCE / "deliberate-red-green.json").write_text(json.dumps(results, indent=2) + "\n")
        print(
            f'{name}: RED={red["exit"]} GREEN={green["exit"]} byte-identical restoration',
            flush=True,
        )
        assert red["exit"] == 1 and green["exit"] == 0, name


if __name__ == "__main__":
    main()
