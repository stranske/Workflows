"""Classify whether sync-core still reports the ci_history ``no-redef`` finding.

Sync-core round ``20261107T014654Z`` quoted a verbatim mypy diagnostic from
trip-planner#1957 (Workflows#4508). A later round clears that shipment-caused
finding only when the fingerprint is absent from the consumer
``Python CI / typecheck-mypy`` log.

GitHub Actions job logs prefix each line with a timestamp. Substring matching
keeps classification stable for both sanitized excerpts and raw job logs::

    python scripts/sync_core_shipment_finding.py path/to/typecheck-mypy.log
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Verbatim finding sync-core quoted on trip-planner#1957 (round 20261107T014654Z).
CI_HISTORY_RECORD_NO_REDEF_FINDING = (
    'scripts/ci_history.py:152: error: Name "record" already defined on line 119  [no-redef]'
)


def reports_ci_history_record_no_redef(log_text: str) -> bool:
    """Return True when a consumer mypy log still carries the #4508 fingerprint."""
    return CI_HISTORY_RECORD_NO_REDEF_FINDING in log_text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Exit 0 when the ci_history no-redef shipment finding is cleared; "
            "exit 1 when sync-core would still report it."
        )
    )
    parser.add_argument(
        "log_path",
        type=Path,
        help="Path to a typecheck-mypy job log or excerpt",
    )
    args = parser.parse_args(argv)
    log_text = args.log_path.read_text(encoding="utf-8")
    if reports_ci_history_record_no_redef(log_text):
        print(f"still-reported: {CI_HISTORY_RECORD_NO_REDEF_FINDING}", file=sys.stderr)
        return 1
    print("cleared: ci_history record no-redef fingerprint absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
