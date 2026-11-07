#!/usr/bin/env python3
"""Run whole-file pytest batches and retain exact collection/execution evidence.

Each pytest child is bounded below two minutes. Exit zero requires the original
collection and every batch to succeed, with identical node-ID multisets and a
terminal result for every node. Skips are retained separately from passes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

PLUGIN = "scripts.validate_workflow_test_batches"


class Receipt:
    """Record pytest hooks instead of parsing potentially truncated console output."""

    def __init__(self, path: Path):
        self.path = path
        self.nodes: list[str] = []
        self.files: dict[str, str] = {}
        self.reports: list[dict[str, str]] = []

    def pytest_collection_finish(self, session):
        self.nodes = [item.nodeid for item in session.items]
        self.files = {item.nodeid: str(item.path) for item in session.items}

    def pytest_runtest_logreport(self, report):
        self.reports.append(
            {"nodeid": report.nodeid, "when": report.when, "outcome": report.outcome}
        )

    def pytest_sessionfinish(self, session, exitstatus):
        self.path.write_text(
            json.dumps(
                {
                    "nodes": self.nodes,
                    "files": self.files,
                    "reports": self.reports,
                    "exit_code": int(exitstatus),
                },
                indent=2,
            )
            + "\n"
        )


def pytest_addoption(parser):
    parser.addoption("--workflow-batch-receipt", help="Write exact pytest node/phase results")


def pytest_configure(config):
    path = config.getoption("--workflow-batch-receipt")
    if path:
        config.pluginmanager.register(Receipt(Path(path)), "workflow-batch-receipt")


def partition_files(collection: dict, max_nodes: int) -> list[list[str]]:
    """Keep whole files in collection order; oversized files run alone."""
    if max_nodes < 1:
        raise ValueError("max_nodes must be positive")
    counts = Counter(collection["files"][node] for node in collection["nodes"])
    batches: list[list[str]] = []
    current: list[str] = []
    size = 0
    for file, count in counts.items():
        if current and size + count > max_nodes:
            batches.append(current)
            current, size = [], 0
        current.append(file)
        size += count
    if current:
        batches.append(current)
    return batches


def compare_receipts(original: list[str], batches: list[dict]) -> dict:
    """Reject missing, extra, duplicated or nonterminal observations."""
    expected = Counter(original)
    collected: Counter[str] = Counter()
    terminal: Counter[str] = Counter()
    outcomes: Counter[str] = Counter()
    for batch in batches:
        collected.update(batch.get("nodes", []))
        by_node: dict[str, list[dict]] = {}
        for report in batch.get("reports", []):
            by_node.setdefault(report["nodeid"], []).append(report)
        for node, reports in by_node.items():
            phases = Counter(report["when"] for report in reports)
            if any(report["outcome"] == "failed" for report in reports):
                outcome = "failed"
            elif any(report["outcome"] == "skipped" for report in reports):
                outcome = "skipped"
            else:
                outcome = "passed"
            # A missing teardown or repeated phase cannot prove complete execution.
            if phases["setup"] == phases["teardown"] == 1 and (
                phases["call"] == 1 or (phases["call"] == 0 and outcome != "passed")
            ):
                terminal[node] += 1
                outcomes[outcome] += 1
    missing = expected - collected
    extra = collected - expected
    missing_results = expected - terminal
    extra_results = terminal - expected
    return {
        "expected": len(original),
        "collected": collected.total(),
        "terminal": terminal.total(),
        "missing": dict(missing),
        "extra": dict(extra),
        "missing_results": dict(missing_results),
        "extra_results": dict(extra_results),
        "outcomes": dict(outcomes),
        "node_ids_sha256": hashlib.sha256(
            ("\n".join(sorted(original)) + "\n").encode()
        ).hexdigest(),
        "success": bool(original)
        and bool(batches)
        and not (missing or extra or missing_results or extra_results)
        and all(batch.get("exit_code") == 0 for batch in batches)
        and not outcomes["failed"],
    }


def execute_pytest(args: list[str], prefix: Path, timeout: float) -> dict:
    """Bound a child and its descendants, preserving its log and terminal status."""
    receipt_path = prefix.with_suffix(".json")
    receipt_path.unlink(missing_ok=True)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        PLUGIN,
        "--workflow-batch-receipt",
        str(receipt_path),
        *args,
    ]
    started = time.monotonic()
    with prefix.with_suffix(".log").open("w") as log:
        child = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
        try:
            exit_code = child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
            exit_code = 124
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    receipt.update(
        command=command,
        exit_code=exit_code,
        seconds=round(time.monotonic() - started, 2),
    )
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", nargs="?", default="tests/workflows/")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=110)
    parser.add_argument("--max-nodes", type=int, default=100)
    args = parser.parse_args(argv)
    if not 0 < args.timeout < 120 or args.max_nodes < 1:
        parser.error("timeout must be between 0 and 120 seconds; max-nodes must be positive")
    args.output.mkdir(parents=True, exist_ok=True)
    # A failed recollection must not leave an earlier successful summary behind.
    (args.output / "summary.json").unlink(missing_ok=True)
    collection = execute_pytest(
        [args.suite, "--collect-only", "-q"], args.output / "collection", args.timeout
    )
    if collection["exit_code"] != 0 or not collection.get("nodes"):
        print("Collection failed; inspect collection.log", flush=True)
        return 1
    batches = []
    for number, files in enumerate(partition_files(collection, args.max_nodes), 1):
        batch = execute_pytest(files + ["-v"], args.output / f"batch-{number:02}", args.timeout)
        batches.append(batch)
        print(
            f"Batch {number}: exit {batch['exit_code']}, {batch['seconds']}s, "
            f"{len(batch.get('nodes', []))} collected",
            flush=True,
        )
    summary = compare_receipts(collection["nodes"], batches)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
