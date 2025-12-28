#!/usr/bin/env python
"""Generate ASCII sparklines for residual Ruff diagnostics trend.

Reads: ci/autofix/history.json
Writes:
  ci/autofix/trend.json (latest metrics + sparkline strings)
Prints a one-line summary for workflow consumption.

Sparkline chars chosen for good monotonic density distribution.
"""
from __future__ import annotations

import collections
import json
import pathlib

HISTORY = pathlib.Path("ci/autofix/history.json")
OUT = pathlib.Path("ci/autofix/trend.json")
SPARK_CHARS = "▁▂▃▄▅▆▇█"


def _coerce_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return 0
    return 0


def sparkline(series: list[int]) -> str:
    if not series:
        return ""
    mn = min(series)
    mx = max(series)
    if mx == mn:
        return SPARK_CHARS[0] * len(series)
    span = mx - mn
    out = []
    for v in series:
        idx = int((v - mn) / span * (len(SPARK_CHARS) - 1))
        out.append(SPARK_CHARS[idx])
    return "".join(out)


def main() -> int:
    try:
        hist_raw = json.loads(HISTORY.read_text())
    except Exception:
        hist_raw = []
    hist: list[dict[str, object]]
    if isinstance(hist_raw, list):
        hist = [snap for snap in hist_raw if isinstance(snap, dict)]
    else:
        hist = []
    remaining_series = [_coerce_int(snap.get("remaining", 0)) for snap in hist][-40:]
    new_series = [_coerce_int(snap.get("new", 0)) for snap in hist][-40:]

    # Build per-code time series (last 40) for top residual codes ranked by latest count
    code_counts_latest: collections.Counter[str] = collections.Counter()
    for snap in hist[-1:]:  # only latest snapshot for ranking
        by_code = snap.get("by_code")
        if isinstance(by_code, dict):
            for code, c in by_code.items():
                if isinstance(code, str):
                    code_counts_latest[code] += int(c)
    top_codes = [code for code, _ in code_counts_latest.most_common(6)]  # limit to 6
    code_series: dict[str, list[int]] = {code: [] for code in top_codes}
    for snap in hist[-40:]:
        by_code_obj = snap.get("by_code")
        by_code = by_code_obj if isinstance(by_code_obj, dict) else {}
        for code in top_codes:
            code_series[code].append(_coerce_int(by_code.get(code, 0)))

    code_sparklines = {
        code: {"latest": series[-1] if series else 0, "spark": sparkline(series)}
        for code, series in code_series.items()
    }
    trend = {
        "points": len(hist),
        "remaining_latest": remaining_series[-1] if remaining_series else 0,
        "new_latest": new_series[-1] if new_series else 0,
        "remaining_spark": sparkline(remaining_series),
        "new_spark": sparkline(new_series),
        "codes": code_sparklines,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(trend, indent=2, sort_keys=True))
    print(
        f"trend remaining={trend['remaining_latest']} new={trend['new_latest']} {trend['remaining_spark']} / {trend['new_spark']}"
    )
    return 0


if __name__ == "__main__":
    try:
        from trend_analysis.script_logging import setup_script_logging

        setup_script_logging(module_file=__file__)
    except ImportError:
        pass  # Package not installed in CI environment
    raise SystemExit(main())
