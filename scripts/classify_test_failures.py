"""Classify pytest failures into cosmetic vs runtime buckets.

This helper parses one or more JUnit XML documents (``pytest --junitxml``)
looking for test cases flagged as failing.  We attach the markers recorded by
``tests/conftest.py`` via ``user_properties`` so that the automation layer can
reason about the failure category.  The summary returned by ``classify_reports``
contains both per-test metadata and aggregated booleans that downstream
workflows can consume.

Usage example::

    python scripts/classify_test_failures.py pytest-report-*.xml --output summary.json

If no failures are found the script still writes a summary so callers can keep
a consistent IO contract.  The module intentionally sticks to the standard
library so it runs inside GitHub Actions without extra dependencies.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

_MARKER_KEYS = {
    "test_markers",
    "markers",
    "pytest_markers",
    "pytestmark",
}

_MARKER_SPLIT_RE = re.compile(r"[\s,]+")


@dataclass(frozen=True)
class FailureRecord:
    """Structured data describing a single failing test case."""

    id: str
    file: str
    markers: Sequence[str]
    message: str
    failure_type: str


@dataclass
class FailureSummary:
    cosmetic: List[FailureRecord]
    runtime: List[FailureRecord]
    unknown: List[FailureRecord]

    def as_dict(self) -> dict[str, object]:
        cosmetic = [record.__dict__ for record in self.cosmetic]
        runtime = [record.__dict__ for record in self.runtime]
        unknown = [record.__dict__ for record in self.unknown]
        total = len(cosmetic) + len(runtime) + len(unknown)
        only_cosmetic = bool(cosmetic) and not runtime and not unknown
        has_failures = total > 0
        return {
            "cosmetic": cosmetic,
            "runtime": runtime,
            "unknown": unknown,
            "total_failures": total,
            "has_failures": has_failures,
            "only_cosmetic": only_cosmetic,
        }


def _extract_markers(testcase: ET.Element) -> set[str]:
    markers: set[str] = set()
    properties = testcase.find("properties")
    if properties is None:
        return markers
    for prop in properties.findall("property"):
        name = (prop.get("name") or "").strip()
        value = (prop.get("value") or "").strip()
        if not value:
            continue
        lowered = name.lower()
        if lowered in _MARKER_KEYS:
            markers.update(token for token in _MARKER_SPLIT_RE.split(value) if token)
        elif lowered.startswith("marker:"):
            markers.add(lowered.split(":", 1)[1])
    return markers


def _failure_message(testcase: ET.Element) -> tuple[str, str]:
    for tag, failure_type in (("failure", "failure"), ("error", "error")):
        node = testcase.find(tag)
        if node is not None:
            message = node.get("message") or ""
            text = (node.text or "").strip()
            if text and message:
                message = f"{message}: {text}"
            elif text:
                message = text
            return message, failure_type
    return "", "failure"


def _test_id(testcase: ET.Element, source: Path) -> str:
    classname = testcase.get("classname") or ""
    name = testcase.get("name") or ""
    if classname and name:
        return f"{classname}::{name}"
    if name:
        return name
    return f"{source.name}::{testcase.tag}"


def classify_reports(paths: Iterable[str | Path]) -> dict[str, object]:
    cosmetic: list[FailureRecord] = []
    runtime: list[FailureRecord] = []
    unknown: list[FailureRecord] = []
    seen_ids: set[tuple[str, str]] = set()

    for path in sorted({str(Path(p)) for p in paths}):
        junit_path = Path(path)
        if not junit_path.exists():
            continue
        try:
            tree = ET.parse(junit_path)
        except ET.ParseError as exc:
            unknown.append(
                FailureRecord(
                    id=f"<parse-error>:{junit_path.name}",
                    file=str(junit_path),
                    markers=(),
                    message=f"Unable to parse JUnit XML: {exc}",
                    failure_type="error",
                )
            )
            continue
        root = tree.getroot()
        testcases = list(root.iter("testcase"))
        for testcase in testcases:
            failure_node = testcase.find("failure") or testcase.find("error")
            if failure_node is None:
                continue
            marker_set = _extract_markers(testcase)
            case_id = _test_id(testcase, junit_path)
            dedupe_key = (case_id, str(junit_path))
            if dedupe_key in seen_ids:
                continue
            seen_ids.add(dedupe_key)
            message, failure_type = _failure_message(testcase)
            record = FailureRecord(
                id=case_id,
                file=str(junit_path),
                markers=tuple(sorted(marker_set)),
                message=message,
                failure_type=failure_type,
            )
            if "runtime" in marker_set:
                runtime.append(record)
            elif "cosmetic" in marker_set:
                cosmetic.append(record)
            elif marker_set:
                # Unknown marker – treat as runtime but capture separately for visibility.
                unknown.append(record)
            else:
                runtime.append(record)

    summary = FailureSummary(cosmetic=cosmetic, runtime=runtime, unknown=unknown)
    return summary.as_dict()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "reports",
        nargs="+",
        help="JUnit XML files or glob patterns",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON path for the summary",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    ns = _parse_args(argv)
    expanded: list[str] = []
    for pattern in ns.reports:
        paths = list(Path().glob(pattern))
        if paths:
            expanded.extend(str(p) for p in paths)
        else:
            expanded.append(pattern)
    summary = classify_reports(expanded)
    payload = json.dumps(summary, indent=2, sort_keys=True)
    if ns.output:
        ns.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":  # pragma: no cover
    from trend_analysis.script_logging import setup_script_logging

    setup_script_logging(module_file=__file__)
    sys.exit(main())
