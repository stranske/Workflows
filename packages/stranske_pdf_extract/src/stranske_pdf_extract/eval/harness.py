"""Golden-set evaluation harness — normalize-then-compare, per-field macro-F1.

Methodology doc §6: score against a golden set built from human corrections; compare
**normalized** values (numbers as numerics, dates canonical) not raw exact-match; report
per-field precision/recall/F1 **macro-averaged** so rare-but-critical fields count. The
core scorer here is deterministic and dependency-free; DeepEval (CI gate) and LangSmith
(online sampling) are optional hooks layered on top, shipped so every consumer inherits
one scorer and one gate.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_NUMERIC_RE = re.compile(r"^[-+(]?\$?\s*\d[\d,]*(?:\.\d+)?\)?%?$")


def normalize_value(value: str) -> str:
    """Canonicalize a cell for comparison.

    Numbers -> a canonical numeric string (strip $, commas, %, parens=negative);
    everything else -> casefolded, whitespace-collapsed text. Deterministic.
    """
    raw = value.strip()
    if _NUMERIC_RE.match(raw):
        negative = raw.startswith("(") and raw.endswith(")")
        cleaned = raw.strip("()").replace("$", "").replace(",", "").replace("%", "").strip()
        try:
            number = Decimal(cleaned)
        except InvalidOperation:
            return raw.casefold()
        if negative:
            number = -number
        return format(number.normalize(), "f")
    return " ".join(raw.casefold().split())


@dataclass(frozen=True)
class FieldScore:
    key: str
    precision: float
    recall: float
    f1: float


@dataclass(frozen=True)
class ScoreReport:
    per_field: tuple[FieldScore, ...]
    macro_f1: float

    def regressed_against(self, baseline: ScoreReport, *, tol: float = 1e-9) -> tuple[str, ...]:
        """Field keys whose F1 dropped vs a baseline report (for a PR gate)."""
        base = {fs.key: fs.f1 for fs in baseline.per_field}
        return tuple(
            fs.key for fs in self.per_field if fs.key in base and fs.f1 < base[fs.key] - tol
        )


def score_against_golden(
    predictions: Sequence[Mapping[str, str]],
    golden: Sequence[Mapping[str, str]],
) -> ScoreReport:
    """Per-field precision/recall/F1 (normalized), macro-averaged across fields.

    ``predictions`` and ``golden`` are aligned per-document field maps (same length,
    same document order). A field counts as a true positive when present in both and
    normalized-equal.
    """
    if len(predictions) != len(golden):
        raise ValueError("predictions and golden must have the same number of documents")

    keys = sorted({k for doc in golden for k in doc} | {k for doc in predictions for k in doc})
    scores: list[FieldScore] = []
    for key in keys:
        tp = fp = fn = 0
        for pred, gold in zip(predictions, golden, strict=True):
            p = pred.get(key)
            g = gold.get(key)
            if p is None and g is None:
                continue
            if p is not None and g is not None:
                if normalize_value(p) == normalize_value(g):
                    tp += 1
                else:
                    fp += 1
                    fn += 1
            elif p is not None:
                fp += 1
            else:
                fn += 1
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        scores.append(FieldScore(key=key, precision=precision, recall=recall, f1=f1))

    macro_f1 = sum(s.f1 for s in scores) / len(scores) if scores else 0.0
    return ScoreReport(per_field=tuple(scores), macro_f1=macro_f1)


__all__ = ["FieldScore", "ScoreReport", "normalize_value", "score_against_golden"]
