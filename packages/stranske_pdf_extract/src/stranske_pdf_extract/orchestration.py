"""Fallback-ladder orchestration primitive.

Lifted from Pension-Data's ``extract/orchestration/fallback.py`` — it was already
generic over the stage result type. Try stages in order, accept the first that
satisfies ``is_complete``, escalate with a structured event on exhaustion, and keep
a best-partial when nothing fully completes. This is the canonical primitive for
"pdfplumber -> pypdf -> OCR" style ladders and for provider primary/fallback chains.

``ParserAttempt`` and ``EscalationEvent`` live in :mod:`contract` so the same types
flow straight into :class:`contract.ExtractedDocumentResult`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .contract import EscalationEvent, ParserAttempt


@dataclass(frozen=True, slots=True)
class ParserStage[TResult]:
    """One stage in a fallback chain."""

    stage_name: str
    parser_name: str
    parse: Callable[[], TResult]


@dataclass(frozen=True, slots=True)
class FallbackOutcome[TResult]:
    """Outcome of running a fallback chain."""

    result: TResult | None
    attempts: tuple[ParserAttempt, ...]
    escalation: EscalationEvent | None


def run_fallback_chain[TResult](
    *,
    domain: str,
    stages: Sequence[ParserStage[TResult]],
    is_complete: Callable[[TResult], bool],
) -> FallbackOutcome[TResult]:
    """Execute stages in order; accept first complete result, else escalate."""
    attempts: list[ParserAttempt] = []
    for stage in stages:
        try:
            parsed = stage.parse()
            complete = is_complete(parsed)
        except Exception as exc:  # noqa: BLE001 - structured failure path is the point
            attempts.append(
                ParserAttempt(
                    stage_name=stage.stage_name,
                    parser_name=stage.parser_name,
                    succeeded=False,
                    failure_reason=f"exception:{type(exc).__name__}:{exc}",
                )
            )
            continue

        if not complete:
            attempts.append(
                ParserAttempt(
                    stage_name=stage.stage_name,
                    parser_name=stage.parser_name,
                    succeeded=False,
                    failure_reason="incomplete-required-fields",
                )
            )
            continue

        attempts.append(
            ParserAttempt(
                stage_name=stage.stage_name, parser_name=stage.parser_name, succeeded=True
            )
        )
        return FallbackOutcome(result=parsed, attempts=tuple(attempts), escalation=None)

    return FallbackOutcome(
        result=None,
        attempts=tuple(attempts),
        escalation=EscalationEvent(
            domain=domain,
            reason="parser_fallback_exhaustion",
            exhausted_stage_count=len(stages),
            attempts=tuple(attempts),
        ),
    )


def best_partial[TResult](
    candidates: Sequence[TResult], *, score: Callable[[TResult], float]
) -> TResult | None:
    """Pick the highest-scoring partial when no stage fully completed.

    Generalizes Pension-Data's ``_best_partial`` (which ranked by fewest missing
    metrics then confidence) to any caller-supplied score (higher = better).
    """
    if not candidates:
        return None
    return max(candidates, key=score)


__all__ = ["ParserStage", "FallbackOutcome", "run_fallback_chain", "best_partial"]
