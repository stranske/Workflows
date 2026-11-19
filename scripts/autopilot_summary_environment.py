"""Shared GitHub environment details for auto-pilot metric summaries."""

from __future__ import annotations

import os

_SUMMARY_ENVIRONMENT_KEYS = (
    "GITHUB_RUN_ID",
    "GITHUB_WORKFLOW",
    "GITHUB_JOB",
    "GITHUB_RUN_ATTEMPT",
    "GITHUB_REF",
    "GITHUB_SHA",
    "RUNNER_OS",
)


def summary_environment_details() -> dict[str, str]:
    """Return populated GitHub environment values using the summary field names."""
    return {
        key.lower(): value for key in _SUMMARY_ENVIRONMENT_KEYS if (value := os.environ.get(key))
    }
