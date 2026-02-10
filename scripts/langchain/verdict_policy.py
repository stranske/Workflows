"""Utility helpers to extract provider verdicts and apply a policy."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

VERDICT_SEVERITY = {
    "unknown": 0,
    "pass": 1,
    "concerns": 2,
    "fail": 3,
}

CONCERNS_NEEDS_HUMAN_THRESHOLD = 0.85


@dataclass(frozen=True)
class ProviderVerdict:
    provider: str
    model: str
    verdict: str
    confidence: float


@dataclass(frozen=True)
class VerdictPolicyResult:
    verdict: str
    verdict_kind: str
    policy: str
    needs_human: bool
    needs_human_reason: str
    selected_provider: str | None
    selected_model: str | None
    selected_confidence: float | None
    split_verdict: bool
    concerns_confidence: float | None
    providers: list[ProviderVerdict]

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "verdict_kind": self.verdict_kind,
            "policy": self.policy,
            "needs_human": self.needs_human,
            "needs_human_reason": self.needs_human_reason,
            "selected_provider": self.selected_provider,
            "selected_model": self.selected_model,
            "selected_confidence": self.selected_confidence,
            "split_verdict": self.split_verdict,
            "concerns_confidence": self.concerns_confidence,
            "providers": [item.__dict__ for item in self.providers],
        }


def _classify_verdict(verdict: str) -> str:
    verdict = verdict.strip().lower()
    if not verdict:
        return "unknown"
    if verdict.startswith("pass"):
        return "pass"
    if verdict.startswith("concerns"):
        return "concerns"
    if verdict.startswith("fail"):
        return "fail"
    return "unknown"


def _coerce_confidence(value: str) -> float:
    cleaned = value.strip().rstrip("%")
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _normalize_confidence(value: float) -> float:
    if value <= 0:
        return 0.0
    if value <= 1:
        return value
    return value / 100.0


def _iter_markdown_rows(lines: Iterable[str]) -> Iterable[list[str]]:
    for line in lines:
        line = line.rstrip()
        if not line.startswith("|"):
            continue
        parts = [segment.strip() for segment in line.strip("|").split("|")]
        if not parts or all(not part for part in parts):
            continue
        yield parts


def extract_provider_verdicts(summary: str) -> list[ProviderVerdict]:
    """Parse provider verdict rows from a markdown summary table."""
    verdicts: list[ProviderVerdict] = []
    for cols in _iter_markdown_rows(summary.splitlines()):
        if cols[0].lower() in {"provider", "---"}:
            continue
        if len(cols) < 4:
            continue
        provider = cols[0]
        if not provider:
            continue
        model = cols[1] if len(cols) > 1 else ""
        verdict = cols[2] if len(cols) > 2 else ""
        confidence = cols[3] if len(cols) > 3 else ""
        verdicts.append(
            ProviderVerdict(
                provider=provider,
                model=model,
                verdict=verdict,
                confidence=_coerce_confidence(confidence),
            )
        )
    return verdicts


def _select_deterministic(
    verdicts: list[ProviderVerdict], *, policy: str
) -> ProviderVerdict | None:
    if not verdicts:
        return None

    if policy == "worst":
        return max(
            verdicts,
            key=lambda item: (
                VERDICT_SEVERITY.get(_classify_verdict(item.verdict), 0),
                _normalize_confidence(item.confidence),
                (item.provider or "").lower(),
                (item.model or "").lower(),
                (item.verdict or "").lower(),
            ),
        )

    if policy == "majority":
        buckets: dict[str, list[ProviderVerdict]] = {}
        for item in verdicts:
            buckets.setdefault(_classify_verdict(item.verdict), []).append(item)
        majority_kind = max(
            buckets.items(),
            key=lambda pair: (len(pair[1]), VERDICT_SEVERITY.get(pair[0], 0)),
        )[0]
        majority_bucket = buckets.get(majority_kind, [])
        if not majority_bucket:
            return None
        return max(
            majority_bucket,
            key=lambda item: (
                _normalize_confidence(item.confidence),
                (item.provider or "").lower(),
                (item.model or "").lower(),
                (item.verdict or "").lower(),
            ),
        )

    raise ValueError(f"Unknown policy: {policy}")


def _split_pass_concerns(verdicts: list[ProviderVerdict]) -> tuple[bool, float | None]:
    if not verdicts:
        return False, None
    kinds = [_classify_verdict(item.verdict) for item in verdicts]
    has_pass = any(kind == "pass" for kind in kinds)
    has_concerns = any(kind == "concerns" for kind in kinds)
    if not (has_pass and has_concerns):
        return False, None
    max_confidence = 0.0
    for item in verdicts:
        if _classify_verdict(item.verdict) == "concerns":
            max_confidence = max(max_confidence, _normalize_confidence(item.confidence))
    return True, max_confidence


def evaluate_verdict_policy(
    verdicts: Iterable[ProviderVerdict],
    *,
    policy: str = "worst",
) -> VerdictPolicyResult:
    verdict_list = list(verdicts)
    selected = _select_deterministic(verdict_list, policy=policy)
    split_verdict, concerns_confidence = _split_pass_concerns(verdict_list)
    needs_human = False
    needs_human_reason = ""
    if split_verdict:
        confidence_value = concerns_confidence or 0.0
        if confidence_value < CONCERNS_NEEDS_HUMAN_THRESHOLD:
            needs_human = True
            needs_human_reason = (
                "Provider verdicts split with low-confidence concerns; "
                f"dissenting confidence {confidence_value:.2f} < "
                f"{CONCERNS_NEEDS_HUMAN_THRESHOLD:.2f}. "
                "Requires human review before starting another automated follow-up."
            )

    if not selected:
        return VerdictPolicyResult(
            verdict="Unknown",
            verdict_kind="unknown",
            policy=policy,
            needs_human=needs_human,
            needs_human_reason=needs_human_reason,
            selected_provider=None,
            selected_model=None,
            selected_confidence=None,
            split_verdict=split_verdict,
            concerns_confidence=concerns_confidence,
            providers=verdict_list,
        )

    verdict_text = selected.verdict.strip() or "Unknown"
    verdict_kind = _classify_verdict(verdict_text)

    return VerdictPolicyResult(
        verdict=verdict_text,
        verdict_kind=verdict_kind,
        policy=policy,
        needs_human=needs_human,
        needs_human_reason=needs_human_reason,
        selected_provider=selected.provider,
        selected_model=selected.model,
        selected_confidence=_normalize_confidence(selected.confidence),
        split_verdict=split_verdict,
        concerns_confidence=concerns_confidence,
        providers=verdict_list,
    )


def evaluate_summary(
    summary: str,
    *,
    policy: str = "worst",
) -> VerdictPolicyResult:
    verdicts = extract_provider_verdicts(summary)
    return evaluate_verdict_policy(verdicts, policy=policy)


def select_verdict(verdicts: Iterable[ProviderVerdict], policy: str = "worst") -> str:
    """Resolve a verdict using either worst-case or majority policy."""
    return evaluate_verdict_policy(verdicts, policy=policy).verdict


def _read_summary(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Select a deterministic verdict from a markdown summary table."
    )
    parser.add_argument(
        "--summary-path",
        required=True,
        help="Path to the markdown summary (use '-' for stdin).",
    )
    parser.add_argument(
        "--policy",
        choices=["worst", "majority"],
        default="worst",
        help="Policy used to resolve split provider verdicts.",
    )
    parser.add_argument(
        "--format",
        choices=["verdict", "json"],
        default="verdict",
        help="Output format.",
    )
    args = parser.parse_args(argv)

    summary = _read_summary(args.summary_path)
    result = evaluate_summary(summary, policy=args.policy)

    if args.format == "json":
        print(json.dumps(result.as_dict(), indent=2))
    else:
        print(result.verdict)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
