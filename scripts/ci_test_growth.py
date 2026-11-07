"""Build JUnit growth receipts without presenting unknown durations as measurements.

The reusable workflow embeds ``junit_report`` for consumer portability. XML/read
errors propagate to its existing UNKNOWN handler. ``format_growth_summary`` is
prepared for the matching workflow update; it renders unknown receipts explicitly.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from defusedxml import ElementTree as SafeET


def format_growth_summary(growth: dict[str, object]) -> str:
    """Render validated growth receipts, retaining unknowns in text and JSON.

    A default false review flag cannot establish that collection is within budget
    when collection did not complete. JUnit case counts are independent of timing:
    preserve them even when durations or timing rankings are unavailable.
    """
    collection = growth.get("collection")
    total = collection.get("total") if isinstance(collection, dict) else None
    collection_known = (
        isinstance(collection, dict)
        and collection.get("complete") is not False
        and isinstance(total, int)
        and not isinstance(total, bool)
        and total >= 0
        and not growth.get("collection_error")
    )
    review = growth.get("review_required") if collection_known else None
    review = review if isinstance(review, bool) else None
    reported = growth.get("reported")
    cases = reported.get("cases") if isinstance(reported, dict) else None
    cases_known = isinstance(cases, int) and not isinstance(cases, bool) and cases >= 0
    timing_known = (
        isinstance(reported, dict)
        and reported.get("timing_status") == "KNOWN"
        and not growth.get("junit_error")
    )
    timing = (
        "KNOWN (summed worker time, not wall time)"
        if timing_known
        else "UNKNOWN (missing, unreadable or incomplete JUnit timing)"
    )
    rendered = {**growth, "review_required": review}
    return (
        "\n### Test collection and execution growth\n\n"
        "Review signal only; existing test/coverage/merge gates are unchanged.\n\n"
        f"- Selected collection cases: {total if collection_known else 'UNKNOWN'}\n"
        f"- Collection budget review required: {str(review) if review is not None else 'UNKNOWN'}\n"
        f"- JUnit reported cases: {cases if cases_known else 'UNKNOWN'}\n"
        f"- JUnit timing: {timing}\n\n"
        "```json\n" + json.dumps(rendered, indent=2) + "\n```\n"
    )


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
