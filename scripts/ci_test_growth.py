"""Build JUnit and collection growth receipts for the reusable Python CI summary.

The workflow embeds these helpers so consumers do not import this unsynced module.
``junit_report`` XML/read errors propagate to the summary's existing UNKNOWN handler.
Collection review names case-count budget breaches and stays nonblocking.
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


_REVIEW_PROCEDURE = (
    "Nonblocking review: inspect the new semantic interaction, retained lexical axes, "
    "before/after node counts, dominant JUnit worker-seconds, and causal regression proof. "
    "Record that rationale in the PR. Do not raise timeouts or remove coverage, security, "
    "or merge gates. A collected count equal to the budget stays within review."
)


def _count(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def collection_review(collection: dict[str, object]) -> dict[str, object]:
    """Name top-function and per-file counts above the inclusive case budget.

    ``largest_functions`` is the receipt's top 10. A function outside that list cannot
    exceed the function budget unless one of those ten does too. Every file is checked.
    Timings stay on the JUnit receipt and do not use this case-count budget.
    """
    budget = {"cases_per_function": 1000, "cases_per_file": 50000}
    breaches: list[dict[str, object]] = []
    largest = collection.get("largest_functions")
    if isinstance(largest, list):
        for row in largest:
            if not isinstance(row, (list, tuple)) or len(row) != 2 or not isinstance(row[0], str):
                continue
            count = _count(row[1])
            if count is not None and count > budget["cases_per_function"]:
                breaches.append(
                    {
                        "kind": "function",
                        "name": row[0],
                        "cases": count,
                        "limit": budget["cases_per_function"],
                    }
                )
    per_file = collection.get("per_file")
    if isinstance(per_file, dict):
        for name, raw in per_file.items():
            count = _count(raw)
            if isinstance(name, str) and count is not None and count > budget["cases_per_file"]:
                breaches.append(
                    {
                        "kind": "file",
                        "name": name,
                        "cases": count,
                        "limit": budget["cases_per_file"],
                    }
                )
    breaches.sort(key=lambda item: (str(item["kind"]), str(item["name"])))
    return {
        "budget": budget,
        "review_required": bool(breaches),
        "breach_count": len(breaches),
        "breaches": breaches[:10],
        "review_procedure": _REVIEW_PROCEDURE,
    }


def format_growth_summary(growth: dict[str, object]) -> str:
    """Expose collection counts, dominant JUnit timing, and the review procedure."""
    lines = [
        "### Test collection and execution growth",
        "",
        str(growth.get("review_procedure") or _REVIEW_PROCEDURE),
        "",
        "Review signal only; existing test/coverage/merge gates are unchanged.",
        "",
    ]
    collection = growth.get("collection")
    if isinstance(collection, dict) and _count(collection.get("total")) is not None:
        lines.append(f"Selected collection: {collection['total']} cases.")
    else:
        lines.append("Selected collection: unknown.")
    reported = growth.get("reported")
    dominant: object = None
    status = None
    if isinstance(reported, dict):
        status = reported.get("timing_status")
        dominant = reported.get("dominant_functions_worker_seconds")
    if (
        status == "KNOWN"
        and isinstance(dominant, list)
        and dominant
        and isinstance(dominant[0], (list, tuple))
        and len(dominant[0]) == 2
    ):
        name, seconds = dominant[0]
        lines.append(
            f"JUnit timing: KNOWN. Dominant function {name} at {seconds} summed worker-seconds."
        )
    elif status == "UNKNOWN":
        lines.append("JUnit timing: UNKNOWN. Dominant rankings withheld.")
    else:
        lines.append("JUnit timing: not reported.")
    if growth.get("review_required") is True:
        breach_count = _count(growth.get("breach_count")) or 0
        shown = growth.get("breaches")
        shown_count = len(shown) if isinstance(shown, list) else 0
        lines.append(f"Review required: {breach_count} collection budget breach(es).")
        if breach_count > shown_count:
            lines.append(f"Showing {shown_count} of {breach_count}.")
        if isinstance(shown, list):
            for breach in shown:
                if not isinstance(breach, dict):
                    continue
                lines.append(
                    f"- {breach.get('kind')} `{breach.get('name')}`: "
                    f"{breach.get('cases')} cases (limit {breach.get('limit')})"
                )
    else:
        budget = growth.get("budget") if isinstance(growth.get("budget"), dict) else {}
        lines.append(
            "Within budget "
            f"({budget.get('cases_per_function')} cases/function, "
            f"{budget.get('cases_per_file')} cases/file)."
        )
    lines.append("")
    return "\n".join(lines)
