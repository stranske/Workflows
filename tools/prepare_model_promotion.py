#!/usr/bin/env python3
"""Prepare (never auto-apply) verifier model promotions from benchmark evidence.

Move 3 of the self-feeding verifier-model promotion system (stranske/Workflows#2819).

Moves 1-2 make the evaluation evidence flow on its own (registry-derived candidates
+ a corpus that grows from realized PR outcomes). This module turns a passing
benchmark into a *prepared* promotion: it computes the registry mutation and hands
it to a workflow that opens a PR a human merges. It never edits a live selection by
itself — `human_approval_required` stays true; merging the PR IS the approval.

Guardrails (a candidate is only prepared when ALL hold):
  - it is the SAME FAMILY as the incumbent (openai gpt-5.x, anthropic claude-<line>);
    cross-family swaps always need a human to initiate, never auto-preparation;
  - it PASSED every quality gate on the benchmark (including paired non-inferiority);
  - its cost per accepted review is <= the incumbent's.

Rollback is the inverse: if the *active* selection has a failed workload-benchmark
result (a quality-gate breach), propose reverting to the prior selection recorded in
``selection_history``. Rollback PRs are likewise human-merged.

The tool is pure/deterministic given an injected ``today``; the CLI stamps the real
date. Auto-promotion cannot actually fire until the corpus reaches the approval
minimum and the pilot runs on it — this ships the tested logic ahead of that.
"""

from __future__ import annotations

import argparse
import copy
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY_PATH = _REPO_ROOT / "config" / "model_registry.json"
DEFAULT_PROFILE = "verifier-balanced"
REVIEW_INTERVAL_DAYS = 30


def _normalize_provider(provider: str) -> str:
    normalized = (provider or "").strip().lower()
    if normalized in {"anthropic", "claude"}:
        return "anthropic"
    if normalized in {"openai", "azure-openai"}:
        return "openai"
    if normalized in {"github", "github-models", "github_models"}:
        return "github-models"
    return normalized


def model_family(provider: str, model_id: str) -> str:
    """Return a conservative model-family key used to gate same-family promotions.

    anthropic ``claude-opus-4-8`` -> ``claude-opus``; openai ``gpt-5.6-terra`` ->
    ``gpt-5``. For any other provider the family is the exact model id, so an
    unrecognised provider never yields a same-family candidate (auto-preparation
    stays off until a human teaches it the family rule).
    """
    provider = _normalize_provider(provider)
    model_id = (model_id or "").strip()
    if provider == "anthropic":
        parts = model_id.split("-")
        return "-".join(parts[:2]) if len(parts) >= 2 else model_id
    if provider == "openai":
        parts = model_id.split("-")
        head = parts[0] if parts else model_id  # "gpt", then version token in parts[1]
        if len(parts) >= 2:
            major = parts[1].split(".")[0]
            return f"{head}-{major}"
        return model_id
    return model_id


def _selection_for(registry: dict[str, Any], profile: str, provider: str) -> dict[str, Any] | None:
    provider = _normalize_provider(provider)
    for sel in registry.get("selections", []):
        if (
            str(sel.get("profile", "")).strip() == profile
            and _normalize_provider(str(sel.get("provider", ""))) == provider
        ):
            return sel
    return None


def _cost(result: dict[str, Any]) -> float | None:
    value = (result.get("metrics") or {}).get("cost_per_accepted_review_usd")
    return None if value is None else float(value)


def _result_for(report: dict[str, Any], model_id: str) -> dict[str, Any] | None:
    for result in report.get("results", []):
        if str(result.get("model_id", "")).strip() == model_id:
            return result
    return None


def _evidence_id(report: dict[str, Any], provider: str, model_id: str) -> str | None:
    for ev in report.get("registry_evidence", []):
        if str(ev.get("model_id", "")).strip() == model_id and _normalize_provider(
            str(ev.get("provider", ""))
        ) == _normalize_provider(provider):
            return str(ev.get("evidence_id", "")).strip() or None
    return None


def find_promotions(
    report: dict[str, Any], registry: dict[str, Any], *, profile: str = DEFAULT_PROFILE
) -> list[dict[str, Any]]:
    """Return prepared same-family, passing, cost<= promotions for the profile.

    At most one promotion per provider (the cheapest, then lowest-latency, of the
    qualifying same-family candidates).
    """
    incumbent_id = str(report.get("baseline_model_id", "")).strip()
    if not incumbent_id:
        return []
    incumbent_result = _result_for(report, incumbent_id)
    incumbent_cost = _cost(incumbent_result) if incumbent_result else None

    proposals: list[dict[str, Any]] = []
    for result in report.get("results", []):
        model_id = str(result.get("model_id", "")).strip()
        provider = str(result.get("provider", "")).strip()
        if not model_id or model_id == incumbent_id:
            continue
        selection = _selection_for(registry, profile, provider)
        if selection is None:
            continue
        # Only prepare a swap of the *actual* incumbent for this provider/profile.
        if str(selection.get("model_id", "")).strip() != incumbent_id:
            continue
        if result.get("status") != "passed":
            continue
        if model_family(provider, model_id) != model_family(provider, incumbent_id):
            continue
        cand_cost = _cost(result)
        if cand_cost is None or incumbent_cost is None or cand_cost > incumbent_cost:
            continue
        evidence_id = _evidence_id(report, provider, model_id)
        if not evidence_id:
            continue
        proposals.append(
            {
                "profile": profile,
                "provider": _normalize_provider(provider),
                "from_model_id": incumbent_id,
                "to_model_id": model_id,
                "evidence_id": evidence_id,
                "incumbent_cost": incumbent_cost,
                "candidate_cost": cand_cost,
                "p95_latency_ms": (result.get("metrics") or {}).get("p95_latency_ms"),
                "reason": (
                    f"same-family ({model_family(provider, model_id)}) non-inferior pass at "
                    f"cost/accepted {cand_cost} <= incumbent {incumbent_cost}"
                ),
            }
        )

    # One winner per provider: cheapest, then lowest latency.
    best_by_provider: dict[str, dict[str, Any]] = {}
    for proposal in sorted(
        proposals,
        key=lambda p: (p["candidate_cost"], p["p95_latency_ms"] or float("inf"), p["to_model_id"]),
    ):
        best_by_provider.setdefault(proposal["provider"], proposal)
    return list(best_by_provider.values())


def apply_promotion(
    registry: dict[str, Any], promotion: dict[str, Any], *, today: _dt.date
) -> dict[str, Any]:
    """Return a new registry with the promotion applied and history recorded."""
    new_registry = copy.deepcopy(registry)
    selection = _selection_for(new_registry, promotion["profile"], promotion["provider"])
    if selection is None:  # pragma: no cover - guarded by find_promotions
        raise ValueError("no selection to promote for the given profile/provider")

    history = new_registry.setdefault("selection_history", [])
    history.insert(
        0,
        {
            **copy.deepcopy(selection),
            "superseded_at": today.isoformat(),
            "superseded_by": promotion["to_model_id"],
            "supersede_reason": promotion["reason"],
        },
    )

    evidence_ids = list(selection.get("evidence_ids", []))
    if promotion["evidence_id"] not in evidence_ids:
        evidence_ids.append(promotion["evidence_id"])
    selection["model_id"] = promotion["to_model_id"]
    selection["evidence_ids"] = evidence_ids
    selection["decided_at"] = today.isoformat()
    selection["review_by"] = (today + _dt.timedelta(days=REVIEW_INTERVAL_DAYS)).isoformat()
    selection["rationale"] = (
        "Auto-prepared same-family non-inferior + cost<= promotion (#2819 move 3); "
        "human-approved by merging the promotion PR."
    )
    return new_registry


def find_rollbacks(
    report: dict[str, Any], registry: dict[str, Any], *, profile: str = DEFAULT_PROFILE
) -> list[dict[str, Any]]:
    """Propose reverting any active selection whose model failed the benchmark."""
    rollbacks: list[dict[str, Any]] = []
    for sel in registry.get("selections", []):
        if str(sel.get("profile", "")).strip() != profile:
            continue
        active_id = str(sel.get("model_id", "")).strip()
        result = _result_for(report, active_id)
        if not result or result.get("status") != "failed":
            continue
        prior = _latest_history(registry, profile, str(sel.get("provider", "")))
        if prior is None:
            continue
        breached = [k for k, ok in (result.get("gate_results") or {}).items() if ok is False]
        rollbacks.append(
            {
                "profile": profile,
                "provider": _normalize_provider(str(sel.get("provider", ""))),
                "from_model_id": active_id,
                "to_model_id": str(prior.get("model_id", "")).strip(),
                "breached_gates": breached,
                "reason": f"active model {active_id} failed gates {breached}; reverting to prior selection",
            }
        )
    return rollbacks


def _latest_history(registry: dict[str, Any], profile: str, provider: str) -> dict[str, Any] | None:
    provider = _normalize_provider(provider)
    for entry in registry.get("selection_history", []):
        if (
            str(entry.get("profile", "")).strip() == profile
            and _normalize_provider(str(entry.get("provider", ""))) == provider
        ):
            return entry
    return None


def apply_rollback(
    registry: dict[str, Any], rollback: dict[str, Any], *, today: _dt.date
) -> dict[str, Any]:
    """Return a new registry with the active selection reverted to its prior model."""
    new_registry = copy.deepcopy(registry)
    selection = _selection_for(new_registry, rollback["profile"], rollback["provider"])
    history = new_registry.get("selection_history", [])
    provider = _normalize_provider(rollback["provider"])
    prior_index = next(
        (
            i
            for i, entry in enumerate(history)
            if str(entry.get("profile", "")).strip() == rollback["profile"]
            and _normalize_provider(str(entry.get("provider", ""))) == provider
        ),
        None,
    )
    if selection is None or prior_index is None:  # pragma: no cover - guarded by find_rollbacks
        raise ValueError("no prior selection to roll back to")
    prior = history.pop(prior_index)
    selection["model_id"] = str(prior.get("model_id", "")).strip()
    selection["evidence_ids"] = list(prior.get("evidence_ids", []))
    selection["status"] = str(prior.get("status", selection.get("status", "provisional")))
    selection["decided_at"] = today.isoformat()
    selection["review_by"] = (today + _dt.timedelta(days=REVIEW_INTERVAL_DAYS)).isoformat()
    selection["rationale"] = (
        f"Auto-rolled back from {rollback['from_model_id']} after a quality-gate breach "
        "(#2819 move 3); human-approved by merging the rollback PR."
    )
    return new_registry


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare verifier model promotions/rollbacks.")
    parser.add_argument(
        "--benchmark", type=Path, required=True, help="evaluate_model_benchmark output"
    )
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--mode", choices=["promote", "rollback", "auto"], default="auto")
    parser.add_argument("--today", default=None, help="ISO date override (default: today)")
    parser.add_argument("--write", type=Path, help="Write the mutated registry here (for a PR).")
    args = parser.parse_args(argv)

    try:
        report = _load(args.benchmark)
        registry = _load(args.registry)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2
    today = _dt.date.fromisoformat(args.today) if args.today else _dt.date.today()

    promotions = (
        find_promotions(report, registry, profile=args.profile)
        if args.mode in {"promote", "auto"}
        else []
    )
    rollbacks = (
        find_rollbacks(report, registry, profile=args.profile)
        if args.mode in {"rollback", "auto"}
        else []
    )

    mutated = registry
    for promotion in promotions:
        print(
            f"PROMOTE {promotion['provider']}: {promotion['from_model_id']} -> "
            f"{promotion['to_model_id']} ({promotion['reason']})"
        )
        mutated = apply_promotion(mutated, promotion, today=today)
    for rollback in rollbacks:
        print(
            f"ROLLBACK {rollback['provider']}: {rollback['from_model_id']} -> "
            f"{rollback['to_model_id']} ({rollback['reason']})"
        )
        mutated = apply_rollback(mutated, rollback, today=today)

    if not promotions and not rollbacks:
        print("no same-family non-inferior promotion or gate-breach rollback to prepare.")
    elif args.write:
        args.write.write_text(json.dumps(mutated, indent=2) + "\n", encoding="utf-8")
        print(f"wrote proposed registry to {args.write}")

    # Exit 10 signals "a change is prepared" so a workflow can gate PR creation on it.
    return 10 if (promotions or rollbacks) else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
