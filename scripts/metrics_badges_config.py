#!/usr/bin/env python3
"""Badge type definitions for metrics reporting.

These definitions describe the metric keys and display labels used when
rendering metrics badges for agent automation telemetry.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BadgeType:
    name: str
    label: str
    metric_key: str
    description: str


BADGE_TYPES: tuple[BadgeType, ...] = (
    BadgeType(
        name="success_rate",
        label="Success Rate",
        metric_key="success_rate",
        description="Percent of successful runs over the reporting window.",
    ),
    BadgeType(
        name="avg_duration",
        label="Avg Duration",
        metric_key="avg_duration_seconds",
        description="Average run duration for completed workflows.",
    ),
    BadgeType(
        name="last_run_status",
        label="Last Run",
        metric_key="last_run_status",
        description="Status label for the most recent workflow run.",
    ),
)
