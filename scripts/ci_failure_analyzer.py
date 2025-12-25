"""Analyze CI failure patterns to identify flaky tests and recurring issues.

This module provides utilities for parsing CI logs and identifying patterns
in test failures that may indicate flaky tests or infrastructure issues.
"""

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Common failure pattern signatures
FLAKY_PATTERNS = [
    r"timeout.*exceeded",
    r"connection.*refused",
    r"rate.*limit",
    r"resource.*temporarily.*unavailable",
]

INFRASTRUCTURE_PATTERNS = [
    r"disk.*space",
    r"out.*of.*memory",
    r"network.*unreachable",
]


def load_failure_logs(log_path: str) -> List[Dict[str, Any]]:
    """Load failure logs from NDJSON file.

    Args:
        log_path: Path to the NDJSON log file

    Returns:
        List of failure records
    """
    failures: List[Dict[str, Any]] = []
    path = Path(log_path)

    if not path.exists():
        return failures

    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    failures.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return failures


def classify_failure(error_message: str) -> str:
    """Classify a failure based on error message patterns.

    Args:
        error_message: The error message to classify

    Returns:
        Classification: 'flaky', 'infrastructure', 'test', or 'unknown'
    """
    msg_lower = error_message.lower()

    for pattern in FLAKY_PATTERNS:
        if re.search(pattern, msg_lower):
            return "flaky"

    for pattern in INFRASTRUCTURE_PATTERNS:
        if re.search(pattern, msg_lower):
            return "infrastructure"

    # Check for common test failure patterns
    if "assertion" in msg_lower or "assert" in msg_lower:
        return "test"
    if "error" in msg_lower or "exception" in msg_lower:
        return "test"

    return "unknown"


def aggregate_failures(failures: List[Dict[str, Any]]) -> Dict[str, int]:
    """Aggregate failures by classification.

    Args:
        failures: List of failure records with 'error' field

    Returns:
        Dictionary mapping classification to count
    """
    classifications = []
    for failure in failures:
        error = failure.get("error", "")
        classification = classify_failure(error)
        classifications.append(classification)

    return dict(Counter(classifications))


def identify_flaky_tests(
    failures: List[Dict[str, Any]],
    threshold: float = 0.3,
) -> List[str]:
    """Identify tests that fail intermittently (flaky tests).

    A test is considered flaky if it fails more than threshold% of the time
    but also passes sometimes.

    Args:
        failures: List of test run records
        threshold: Failure rate threshold (0.0-1.0)

    Returns:
        List of test names identified as flaky
    """
    test_results: Dict[str, Dict[str, int]] = {}

    for record in failures:
        test_name = record.get("test_name", "")
        verdict = record.get("verdict", "")

        if not test_name:
            continue

        if test_name not in test_results:
            test_results[test_name] = {"pass": 0, "fail": 0}

        if verdict == "pass":
            test_results[test_name]["pass"] += 1
        elif verdict == "fail":
            test_results[test_name]["fail"] += 1

    flaky_tests = []
    for test_name, results in test_results.items():
        total = results["pass"] + results["fail"]
        if total == 0:
            continue
        fail_rate = results["fail"] / total
        # Flaky = fails sometimes but not always
        if threshold <= fail_rate < 1.0 and results["pass"] > 0:
            flaky_tests.append(test_name)

    return flaky_tests


def generate_failure_report(
    failures: List[Dict[str, Any]],
    output_format: str = "text",
) -> str:
    """Generate a human-readable failure report.

    Args:
        failures: List of failure records
        output_format: Output format ('text' or 'markdown')

    Returns:
        Formatted report string
    """
    if not failures:
        return "No failures recorded."

    aggregated = aggregate_failures(failures)
    flaky = identify_flaky_tests(failures)

    if output_format == "markdown":
        lines = ["# CI Failure Report", ""]
        lines.append("## Summary")
        lines.append("")
        for classification, count in sorted(aggregated.items()):
            lines.append(f"- **{classification}**: {count}")
        lines.append("")

        if flaky:
            lines.append("## Flaky Tests")
            lines.append("")
            for test in flaky:
                lines.append(f"- `{test}`")
        return "\n".join(lines)
    else:
        lines = ["CI Failure Report", "=" * 40]
        lines.append("")
        lines.append("Summary:")
        for classification, count in sorted(aggregated.items()):
            lines.append(f"  {classification}: {count}")
        lines.append("")

        if flaky:
            lines.append("Flaky Tests:")
            for test in flaky:
                lines.append(f"  - {test}")
        return "\n".join(lines)


def get_recent_failures(
    failures: List[Dict[str, Any]],
    days: int = 7,
) -> List[Dict[str, Any]]:
    """Filter failures to only recent ones.

    Args:
        failures: List of failure records with 'timestamp' field
        days: Number of days to look back

    Returns:
        Filtered list of recent failures
    """
    now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - (days * 86400)

    recent = []
    for failure in failures:
        ts = failure.get("timestamp", "")
        if not ts:
            continue
        try:
            failure_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if failure_time.timestamp() >= cutoff:
                recent.append(failure)
        except (ValueError, AttributeError):
            continue

    return recent
