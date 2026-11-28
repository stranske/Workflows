"""Maint 52's delivery lease must outlast its own cadence (round-2 D6).

The generated dev-tool PR carries a lease that only the next Maint 52 run refreshes.
With a 72 h lease and a weekly schedule, every PR expired on day 3 and Maint 71 then
closed it, leaving the repo without a delivery for up to 4 days.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/maint-52-sync-dev-versions.yml"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _cadence_hours() -> int:
    triggers = _workflow().get(True) or _workflow()["on"]
    crons = [entry["cron"] for entry in triggers["schedule"]]
    assert len(crons) == 1
    minute, hour, day_of_month, month, day_of_week = crons[0].split()
    assert day_of_month == "*" and month == "*"
    if day_of_week != "*":
        assert re.fullmatch(r"\d", day_of_week), "one run per week expected"
        return 7 * 24
    return 24


def test_lease_outlasts_the_weekly_cadence_that_refreshes_it() -> None:
    lease = int(_workflow()["jobs"]["sync"]["env"]["DELIVERY_LEASE_HOURS"])
    assert lease > _cadence_hours(), (lease, _cadence_hours())


def test_delivery_record_uses_the_named_lease() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert 'date -u -d "+${DELIVERY_LEASE_HOURS} hours"' in text
    assert "+72 hours" not in text
