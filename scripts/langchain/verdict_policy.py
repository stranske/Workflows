"""Utility helpers to extract provider verdicts and apply a policy."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Iterable


VERDICT_SEVERITY = {
    "unknown": 0,
    "pass": 1,
    "concerns": 2,
    "fail": 3,
}


@dataclass(frozen=True)
class ProviderVerdict:
    provider: str
    model: str
    verdict: str
    confidence: float


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


def select_verdict(
    verdicts: Iterable[ProviderVerdict], policy: str = "worst"
) -> str:
    """Resolve a verdict using either worst-case or majority policy."""
    verdict_list = list(verdicts)
    if not verdict_list:
        return "Unknown"

    if policy == "worst":
        worst = max(
            verdict_list,
            key=lambda item: VERDICT_SEVERITY.get(_classify_verdict(item.verdict), 0),
        )
        return worst.verdict.strip() or "Unknown"

    if policy == "majority":
        buckets: dict[str, list[ProviderVerdict]] = {}
        for item in verdict_list:
            buckets.setdefault(_classify_verdict(item.verdict), []).append(item)
        majority_kind = max(
            buckets.items(),
            key=lambda pair: (len(pair[1]), VERDICT_SEVERITY.get(pair[0], 0)),
        )[0]
        for item in verdict_list:
            if _classify_verdict(item.verdict) == majority_kind:
                return item.verdict.strip() or "Unknown"
        return "Unknown"

    raise ValueError(f"Unknown policy: {policy}")


def _read_summary(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as handle:
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
    provider_verdicts = extract_provider_verdicts(summary)
    verdict = select_verdict(provider_verdicts, policy=args.policy)

    if args.format == "json":
        payload = {
            "verdict": verdict,
            "policy": args.policy,
            "providers": [item.__dict__ for item in provider_verdicts],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(verdict)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
