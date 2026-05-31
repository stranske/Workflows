"""Invariant result type and assertion helper.

Apps write their own invariant functions (the bounds are domain-specific), but
they all return ``InvariantResult`` objects, and they all assert the same way:
``error`` severity fails the suite; ``warn`` severity is reported via the
warnings system but never fails.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

ERROR = "error"
WARN = "warn"


@dataclass
class InvariantResult:
    name: str
    ok: bool
    severity: str = ERROR  # "error" | "warn"
    detail: str = ""


def split_results(
    results: list[InvariantResult],
) -> tuple[list[InvariantResult], list[InvariantResult]]:
    """Return (failing errors, failing warnings)."""
    errors = [r for r in results if r.severity == ERROR and not r.ok]
    warns = [r for r in results if r.severity == WARN and not r.ok]
    return errors, warns


def assert_invariants(results: list[InvariantResult], *, context: str = "") -> None:
    """Raise AssertionError on any failing error-invariant; warn on soft ones."""
    errors, warns = split_results(results)
    for r in warns:
        warnings.warn(
            f"[soft]{(' ' + context) if context else ''} {r.name}: {r.detail}", stacklevel=2
        )
    if errors:
        head = f"Invariant violations{(' (' + context + ')') if context else ''}:"
        raise AssertionError(head + "\n" + "\n".join(f"  - {r.name}: {r.detail}" for r in errors))
