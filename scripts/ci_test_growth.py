"""Build JUnit growth receipts without presenting unknown durations as measurements.

The reusable workflow's summary can call ``junit_report`` after parsing its
collection receipt. XML/read errors propagate to its existing UNKNOWN handler.
"""

from __future__ import annotations

import math
from pathlib import Path

from defusedxml import ElementTree as SafeET


def junit_report(path: Path) -> dict[str, object]:
    """Keep reported counts even when individual testcase durations are unusable.

    Rankings require complete timings: a partial sum could incorrectly rank a
    costly function below a completely measured one. Return null rankings and an
    explicit UNKNOWN status whenever any duration is absent, invalid or negative.
    An explicit finite zero is a valid measurement.
    """
    cases = list(SafeET.parse(path).getroot().iter("testcase"))
    functions: dict[str, float] = {}
    suites: dict[str, float] = {}
    untimed = 0
    for case in cases:
        raw = case.get("time")
        try:
            seconds = float(raw) if raw is not None else None
        except ValueError:
            seconds = None
        if seconds is None or not math.isfinite(seconds) or seconds < 0:
            untimed += 1
            continue
        suite = case.get("classname", "unknown")
        name = suite + "::" + case.get("name", "unknown").split("[", 1)[0]
        functions[name] = functions.get(name, 0.0) + seconds
        suites[suite] = suites.get(suite, 0.0) + seconds

    complete = bool(cases) and untimed == 0
    complete = complete and all(math.isfinite(value) for value in functions.values())
    complete = complete and all(math.isfinite(value) for value in suites.values())
    report: dict[str, object] = {
        "cases": len(cases),
        "timed_cases": len(cases) - untimed,
        "untimed_cases": untimed,
        "timing_status": "KNOWN" if complete else "UNKNOWN",
        "dominant_functions_worker_seconds": (
            sorted(functions.items(), key=lambda item: -item[1])[:10] if complete else None
        ),
        "dominant_suites_worker_seconds": (
            sorted(suites.items(), key=lambda item: -item[1])[:10] if complete else None
        ),
        "source": "JUnit reported cases; summed worker time, not wall time",
    }
    if not complete:
        report["timing_error"] = "JUnit durations UNKNOWN: missing, invalid or incomplete timings"
    return report
