#!/usr/bin/env python
"""Append current classification snapshot to history file.
Inputs:
  - autofix_report_enriched.json (produced by composite action)
Outputs:
  - ci/autofix/history.json (list of snapshots)
"""
from __future__ import annotations

import json
import pathlib
import time

from trend_analysis.script_logging import setup_script_logging

setup_script_logging(module_file=__file__, announce=False)

report_path = pathlib.Path("autofix_report_enriched.json")
hist_path = pathlib.Path("ci/autofix/history.json")
hist_path.parent.mkdir(parents=True, exist_ok=True)
try:
    rep = json.loads(report_path.read_text())
except Exception:
    rep = {}
cls = rep.get("classification", {})
entry = {
    "timestamp": cls.get("timestamp") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "remaining": cls.get("total"),
    "new": cls.get("new"),
    "allowed": cls.get("allowed"),
    "by_code": cls.get("by_code", {}),
}
try:
    hist = json.loads(hist_path.read_text())
    if not isinstance(hist, list):
        hist = []
except Exception:
    hist = []

hist.append(entry)

# Retention policy: cap total snapshots to latest 400 to bound repo growth
MAX_HISTORY = 400
if len(hist) > MAX_HISTORY:
    hist = hist[-MAX_HISTORY:]

hist_path.write_text(json.dumps(hist, indent=2, sort_keys=True))
print(
    "Updated history with snapshot: remaining=",
    entry["remaining"],
    "new=",
    entry["new"],
    "history_len=",
    len(hist),
)
