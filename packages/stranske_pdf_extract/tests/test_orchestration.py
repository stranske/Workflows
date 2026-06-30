"""Fallback-ladder orchestration primitive (deterministic, no deps)."""

from __future__ import annotations

from stranske_pdf_extract.orchestration import (
    ParserStage,
    best_partial,
    run_fallback_chain,
)


def _stage(name: str, value, *, boom: bool = False):
    def parse():
        if boom:
            raise RuntimeError("kaboom")
        return value

    return ParserStage(stage_name=name, parser_name=f"parser_{name}", parse=parse)


def test_accepts_first_complete_stage():
    outcome = run_fallback_chain(
        domain="funded",
        stages=(_stage("a", {"x": 1}), _stage("b", {"x": 2})),
        is_complete=lambda r: bool(r),
    )
    assert outcome.result == {"x": 1}
    assert outcome.escalation is None
    assert outcome.attempts[-1].succeeded is True


def test_skips_incomplete_and_exceptions_then_succeeds():
    outcome = run_fallback_chain(
        domain="funded",
        stages=(_stage("a", {}, boom=True), _stage("b", {}), _stage("c", {"ok": 1})),
        is_complete=lambda r: bool(r),
    )
    assert outcome.result == {"ok": 1}
    reasons = [a.failure_reason for a in outcome.attempts if not a.succeeded]
    assert any(r and r.startswith("exception:RuntimeError") for r in reasons)
    assert "incomplete-required-fields" in reasons


def test_is_complete_exception_is_recorded_as_stage_failure():
    outcome = run_fallback_chain(
        domain="funded",
        stages=(_stage("a", {"broken": True}), _stage("b", {"ok": 1})),
        is_complete=lambda r: (
            (_ for _ in ()).throw(ValueError("bad completeness")) if "broken" in r else bool(r)
        ),
    )
    assert outcome.result == {"ok": 1}
    assert outcome.attempts[0].succeeded is False
    assert outcome.attempts[0].failure_reason == "exception:ValueError:bad completeness"


def test_escalates_when_chain_exhausts():
    outcome = run_fallback_chain(
        domain="actuarial",
        stages=(_stage("a", {}), _stage("b", {})),
        is_complete=lambda r: bool(r),
    )
    assert outcome.result is None
    assert outcome.escalation is not None
    assert outcome.escalation.reason == "parser_fallback_exhaustion"
    assert outcome.escalation.exhausted_stage_count == 2


def test_best_partial_picks_highest_score():
    candidates = [{"missing": 3}, {"missing": 1}, {"missing": 2}]
    chosen = best_partial(candidates, score=lambda c: -c["missing"])
    assert chosen == {"missing": 1}
    assert best_partial([], score=lambda c: 0.0) is None
