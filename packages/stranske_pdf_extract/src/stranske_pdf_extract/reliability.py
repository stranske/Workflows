"""Reliability layer — the highest-leverage piece, currently absent fleet-wide.

Three stacked layers from the methodology doc §5, cheapest + most trustworthy first:

1. **Arithmetic / business-rule validation** — the document carries its own ground
   truth. Foot/cross-foot subtotals->totals, weights sum to 100%, sign/currency sanity,
   date-in-period. Deterministic; the LLM says *what*, this code does the arithmetic.
2. **Cross-check** — two structurally different extractors; agree=accept, disagree=flag
   the *specific* field (label-free correctness signal).
3. **Calibration + routing** — ECE measurement and a double-threshold router
   (auto-accept high / auto-reject low / human-review the middle). LLMs are
   systematically overconfident; never route on raw confidence without measuring ECE.

All pure-Python and deterministic. No network, no model calls here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class RuleViolation:
    """A failed business rule, localized to its evidence ref for targeted re-review."""

    rule: str
    message: str
    severity: Severity = "error"
    evidence_ref: str | None = None


# --- Layer 1: arithmetic / business-rule validation ------------------------------------


def check_foots(
    *,
    line_items: Sequence[float],
    total: float,
    rule: str = "foot_total",
    tolerance: float = 0.01,
    evidence_ref: str | None = None,
) -> RuleViolation | None:
    """Line items must sum to the stated total (re-foot)."""
    summed = sum(line_items)
    if abs(summed - total) > tolerance:
        return RuleViolation(
            rule=rule,
            message=f"line items sum to {summed:.4g}, stated total is {total:.4g}",
            evidence_ref=evidence_ref,
        )
    return None


def check_weights_sum_to_one(
    *,
    weights: Sequence[float],
    rule: str = "weights_sum",
    expected: float = 1.0,
    tolerance: float = 0.005,
    evidence_ref: str | None = None,
) -> RuleViolation | None:
    """Allocation weights must sum to 1.0 (or 100%). Pass percents as fractions."""
    summed = sum(weights)
    if abs(summed - expected) > tolerance:
        return RuleViolation(
            rule=rule,
            message=f"weights sum to {summed:.4g}, expected {expected:.4g}",
            evidence_ref=evidence_ref,
        )
    return None


def check_date_in_period(
    *,
    value: date,
    period_start: date,
    period_end: date,
    rule: str = "date_in_period",
    evidence_ref: str | None = None,
) -> RuleViolation | None:
    """An effective/as-of date must fall within the reporting period."""
    if not (period_start <= value <= period_end):
        return RuleViolation(
            rule=rule,
            message=f"date {value.isoformat()} outside period "
            f"[{period_start.isoformat()}, {period_end.isoformat()}]",
            evidence_ref=evidence_ref,
        )
    return None


def check_sign(
    *,
    value: float,
    expected: Literal["non_negative", "non_positive"],
    rule: str = "sign_sanity",
    evidence_ref: str | None = None,
) -> RuleViolation | None:
    """Sign sanity (e.g. a market value should be non-negative)."""
    if expected not in {"non_negative", "non_positive"}:
        raise ValueError("expected must be 'non_negative' or 'non_positive'")
    if expected == "non_negative" and value < 0:
        return RuleViolation(
            rule=rule, message=f"{value} should be >= 0", evidence_ref=evidence_ref
        )
    if expected == "non_positive" and value > 0:
        return RuleViolation(
            rule=rule, message=f"{value} should be <= 0", evidence_ref=evidence_ref
        )
    return None


# --- Layer 2: cross-check between two structurally different extractors -----------------


@dataclass(frozen=True)
class CrossCheckResult:
    """Per-field agreement between two extractors."""

    agreed: tuple[str, ...]
    disagreed: tuple[str, ...]
    only_in_a: tuple[str, ...]
    only_in_b: tuple[str, ...]

    @property
    def needs_review(self) -> tuple[str, ...]:
        """Fields a reviewer should look at: disagreements + one-sided extractions."""
        return tuple(sorted({*self.disagreed, *self.only_in_a, *self.only_in_b}))


def cross_check(
    a: Mapping[str, str],
    b: Mapping[str, str],
    *,
    normalize: bool = True,
) -> CrossCheckResult:
    """Compare two extractors' field maps; flag the specific disagreeing fields.

    Uses the shared numeric-aware ``normalize_value`` so e.g. ``100.0`` and ``100.00``
    agree — the same normalize-then-compare rule the eval harness applies.
    """
    from .eval.harness import normalize_value

    def norm(v: str) -> str:
        return normalize_value(v) if normalize else v

    keys_a, keys_b = set(a), set(b)
    shared = keys_a & keys_b
    agreed = tuple(sorted(k for k in shared if norm(a[k]) == norm(b[k])))
    disagreed = tuple(sorted(k for k in shared if norm(a[k]) != norm(b[k])))
    return CrossCheckResult(
        agreed=agreed,
        disagreed=disagreed,
        only_in_a=tuple(sorted(keys_a - keys_b)),
        only_in_b=tuple(sorted(keys_b - keys_a)),
    )


# --- Layer 3: calibration + confidence routing -----------------------------------------


def expected_calibration_error(pairs: Sequence[tuple[float, bool]], *, n_bins: int = 10) -> float:
    """Expected Calibration Error over (confidence, was_correct) pairs.

    Measure this on YOUR data before routing on confidence — LLM/OCR confidences are
    systematically overconfident. Returns 0.0 for an empty input.
    """
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")
    if not pairs:
        return 0.0
    bins: list[list[tuple[float, bool]]] = [[] for _ in range(n_bins)]
    for conf, correct in pairs:
        if not 0.0 <= conf <= 1.0:
            raise ValueError("confidence values must be within [0.0, 1.0]")
        idx = min(int(conf * n_bins), n_bins - 1)
        bins[idx].append((conf, correct))
    total = len(pairs)
    ece = 0.0
    for bucket in bins:
        if not bucket:
            continue
        avg_conf = sum(c for c, _ in bucket) / len(bucket)
        accuracy = sum(1 for _, ok in bucket if ok) / len(bucket)
        ece += (len(bucket) / total) * abs(avg_conf - accuracy)
    return ece


Route = Literal["auto_accept", "human_review", "auto_reject"]


def route_by_confidence(
    confidence: float, *, accept_at: float = 0.95, reject_below: float = 0.50
) -> Route:
    """Double-threshold router: accept high, reject low, review the ambiguous middle.

    Defaults reflect the methodology doc's finance gate (flag < ~95%). Tune
    ``accept_at`` from a reliability diagram on real data, not by guess.
    """
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be within [0.0, 1.0]")
    if reject_below > accept_at:
        raise ValueError("reject_below must be <= accept_at")
    if confidence >= accept_at:
        return "auto_accept"
    if confidence < reject_below:
        return "auto_reject"
    return "human_review"


__all__ = [
    "RuleViolation",
    "check_foots",
    "check_weights_sum_to_one",
    "check_date_in_period",
    "check_sign",
    "CrossCheckResult",
    "cross_check",
    "expected_calibration_error",
    "route_by_confidence",
]
