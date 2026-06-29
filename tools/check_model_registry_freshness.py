#!/usr/bin/env python3
"""Model-registry freshness gate.

Offline, deterministic, stdlib-only. Detects when the canonical LLM model
configuration has drifted into staleness so old models do not get stuck as the
primary ones indefinitely. It does NOT change model selection — it only reports.

Inputs (defaults resolve relative to the repo root):
  - config/model_registry.json  : curated models with per-tier quality scores.
  - config/llm_slots.json        : provider/model slot pins consumed by
                                   tools/llm_registry.py.

Findings:
  review_overdue : registry `review_by` (or `last_updated` + --max-age-days) is
                   in the past relative to --today. The registry is hand-curated;
                   without a periodic review, new GA models never enter it.
  blocked_pin    : a slot pins a model the registry marks `blocked: true`.
  unknown_pin    : a slot pins a model absent from the registry.
  dominated_pin  : a slot pins a model whose best per-tier quality is strictly
                   lower than another non-blocked model from the SAME provider in
                   the registry — i.e. the registry's own data already says a
                   better model exists, but the pin keeps the old one primary.

Exit codes: 0 = fresh, 1 = stale findings, 2 = config/usage error.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY_PATH = _REPO_ROOT / "config" / "model_registry.json"
DEFAULT_SLOTS_PATH = _REPO_ROOT / "config" / "llm_slots.json"
DEFAULT_MAX_AGE_DAYS = 60


def _normalize_provider(provider: str) -> str:
    p = (provider or "").strip().lower()
    if p in {"anthropic", "claude"}:
        return "anthropic"
    if p in {"openai", "azure-openai"}:
        return "openai"
    if p in {"github", "github-models", "github_models"}:
        return "github"
    return p


def _headline_quality(entry: dict[str, Any]) -> float:
    quality = entry.get("quality") or {}
    values = [float(v) for v in quality.values() if isinstance(v, (int, float))]
    return max(values) if values else 0.0


def _parse_date(value: str) -> _dt.date:
    return _dt.date.fromisoformat(str(value).strip())


def evaluate(
    registry: dict[str, Any],
    slots: dict[str, Any],
    *,
    today: _dt.date,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> list[dict[str, str]]:
    """Return a list of finding dicts (empty == fresh). Pure function."""
    findings: list[dict[str, str]] = []

    models = registry.get("models") or []
    # Index by (provider, model_id).
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    by_provider: dict[str, list[dict[str, Any]]] = {}
    for m in models:
        prov = _normalize_provider(str(m.get("provider", "")))
        mid = str(m.get("model_id", "")).strip()
        if not mid:
            continue
        by_key[(prov, mid)] = m
        by_provider.setdefault(prov, []).append(m)

    # 1. review_overdue -------------------------------------------------------
    review_by_raw = registry.get("review_by")
    try:
        if review_by_raw:
            review_by = _parse_date(review_by_raw)
        else:
            last_updated = registry.get("last_updated")
            if not last_updated:
                findings.append(
                    {
                        "kind": "review_overdue",
                        "detail": "registry has neither `review_by` nor `last_updated`; "
                        "cannot prove freshness.",
                    }
                )
                review_by = None
            else:
                review_by = _parse_date(last_updated) + _dt.timedelta(days=max_age_days)
    except ValueError as exc:
        findings.append({"kind": "review_overdue", "detail": f"unparseable date: {exc}"})
        review_by = None

    if review_by is not None and review_by < today:
        days = (today - review_by).days
        findings.append(
            {
                "kind": "review_overdue",
                "detail": f"model registry review is overdue by {days} day(s) "
                f"(review_by={review_by.isoformat()}, today={today.isoformat()}). "
                "Re-check provider model lists and refresh quality scores.",
            }
        )

    # Slot pins ---------------------------------------------------------------
    for slot in slots.get("slots") or []:
        name = str(slot.get("name", "?"))
        prov = _normalize_provider(str(slot.get("provider", "")))
        model = str(slot.get("model", "")).strip()
        if not model:
            # Tier-derived slot: model comes from the registry at runtime — this is
            # the non-ossifying shape, nothing to flag here.
            continue
        entry = by_key.get((prov, model))
        if entry is None:
            findings.append(
                {
                    "kind": "unknown_pin",
                    "detail": f"slot {name!r} pins {prov}/{model} which is absent from "
                    "the model registry (cannot verify it is current or unblocked).",
                }
            )
            continue
        if entry.get("blocked"):
            findings.append(
                {
                    "kind": "blocked_pin",
                    "detail": f"slot {name!r} pins {prov}/{model} which is marked "
                    "blocked in the registry.",
                }
            )
            continue
        tier = str(slot.get("quality_tier", "")).strip()

        def _slot_quality(model_entry: dict[str, Any], slot_tier: str = tier) -> float:
            if not slot_tier:
                return _headline_quality(model_entry)
            quality = model_entry.get("quality") or {}
            value = quality.get(slot_tier)
            return float(value) if isinstance(value, (int, float)) else float("-inf")

        pinned_q = _slot_quality(entry)
        better = [
            m
            for m in by_provider.get(prov, [])
            if not m.get("blocked") and _slot_quality(m) > pinned_q
        ]
        if better:
            best = max(better, key=_slot_quality)
            findings.append(
                {
                    "kind": "dominated_pin",
                    "detail": f"slot {name!r} pins {prov}/{model} "
                    f"(quality {pinned_q:.2f}) but the registry rates "
                    f"{prov}/{best.get('model_id')} higher "
                    f"({_slot_quality(best):.2f}); the pin keeps an older model primary.",
                }
            )

    return findings


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Model-registry freshness gate.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--slots", type=Path, default=DEFAULT_SLOTS_PATH)
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=DEFAULT_MAX_AGE_DAYS,
        help="Used only when the registry has no explicit `review_by`.",
    )
    parser.add_argument(
        "--today",
        type=str,
        default=None,
        help="ISO date override (testing); defaults to system date.",
    )
    parser.add_argument("--json", action="store_true", help="Emit findings as JSON.")
    args = parser.parse_args(argv)

    try:
        registry = _load_json(args.registry)
        slots = _load_json(args.slots)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    try:
        today = _parse_date(args.today) if args.today else _dt.date.today()
    except ValueError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    findings = evaluate(registry, slots, today=today, max_age_days=args.max_age_days)

    if args.json:
        print(json.dumps({"fresh": not findings, "findings": findings}, indent=2))
    else:
        if not findings:
            print("Model registry is fresh: no stale or dominated pins.")
        else:
            print(f"Model registry freshness: {len(findings)} finding(s):")
            for f in findings:
                print(f"  [{f['kind']}] {f['detail']}")
    return 1 if findings else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
