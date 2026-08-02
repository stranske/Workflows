#!/usr/bin/env python3
"""Decide whether the canonical dev-tool source lane may propose an update.

Routine updates are batched into one Monday UTC window. A security-sensitive
update may bypass that window only when an operator explicitly requests it.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

ROUTINE_WINDOW_WEEKDAY = 0  # Monday in ``datetime.weekday`` notation.


def should_propose_update(now: datetime, *, security_override: bool) -> bool:
    """Return whether the canonical source lane may open or refresh its PR."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return security_override or now.astimezone(UTC).weekday() == ROUTINE_WINDOW_WEEKDAY


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--security-override", action="store_true")
    parser.add_argument("--at", help="UTC ISO-8601 timestamp for deterministic checks")
    args = parser.parse_args(argv)
    now = datetime.fromisoformat(args.at.replace("Z", "+00:00")) if args.at else datetime.now(UTC)
    allowed = should_propose_update(now, security_override=args.security_override)
    if args.security_override:
        reason = "security_override"
    elif allowed:
        reason = "weekly_window"
    else:
        reason = "outside_weekly_window"
    print(f"should_propose={'true' if allowed else 'false'}")
    print(f"reason={reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
