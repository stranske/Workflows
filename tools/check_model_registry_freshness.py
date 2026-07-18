#!/usr/bin/env python3
"""Offline model-registry decision and freshness gate.

The gate validates dated model facts, explicit profile selections, evidence
references, and slot resolution. Provider discovery is a separate advisory tool;
it proposes catalog candidates but never changes a selection.
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
DEFAULT_POLICY_PATH = _REPO_ROOT / "config" / "model_selection_policy.json"
DEFAULT_MAX_AGE_DAYS = 30
VALID_SELECTION_STATUSES = {"provisional", "approved"}


def _normalize_provider(provider: str) -> str:
    normalized = (provider or "").strip().lower()
    if normalized in {"anthropic", "claude"}:
        return "anthropic"
    if normalized in {"openai", "azure-openai"}:
        return "openai"
    if normalized in {"github", "github-models", "github_models"}:
        return "github-models"
    return normalized


def _parse_date(value: str) -> _dt.date:
    return _dt.date.fromisoformat(str(value).strip())


def _finding(kind: str, detail: str) -> dict[str, str]:
    return {"kind": kind, "detail": detail}


def _review_date(
    registry: dict[str, Any], max_age_days: int, findings: list[dict[str, str]]
) -> _dt.date | None:
    raw = registry.get("review_by")
    try:
        if raw:
            return _parse_date(str(raw))
        as_of = registry.get("as_of") or registry.get("last_updated")
        if as_of:
            return _parse_date(str(as_of)) + _dt.timedelta(days=max_age_days)
    except ValueError as exc:
        findings.append(_finding("review_overdue", f"unparseable registry date: {exc}"))
        return None
    findings.append(
        _finding(
            "review_overdue",
            "registry has neither review_by nor as_of; freshness cannot be proved.",
        )
    )
    return None


def evaluate(
    registry: dict[str, Any],
    slots: dict[str, Any],
    *,
    today: _dt.date,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    policy: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Return deterministic findings; an empty list means configuration is fresh."""
    findings: list[dict[str, str]] = []
    review_by = _review_date(registry, max_age_days, findings)
    if review_by is not None and review_by < today:
        findings.append(
            _finding(
                "review_overdue",
                f"registry review is overdue by {(today - review_by).days} day(s) "
                f"(review_by={review_by}, today={today}).",
            )
        )

    models = registry.get("models")
    if not isinstance(models, list):
        return findings + [_finding("invalid_registry", "models must be a list.")]

    raw_sources = registry.get("sources")
    sources = raw_sources if isinstance(raw_sources, list) else []
    source_by_id = {
        str(item.get("source_id", "")).strip(): item
        for item in sources
        if isinstance(item, dict) and str(item.get("source_id", "")).strip()
    }
    if not source_by_id:
        findings.append(_finding("missing_source", "registry has no dated model sources."))

    model_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in models:
        if not isinstance(raw, dict):
            findings.append(_finding("invalid_model", "model entries must be objects."))
            continue
        provider = _normalize_provider(str(raw.get("provider", "")))
        model_id = str(raw.get("model_id", "")).strip()
        if not provider or not model_id:
            findings.append(
                _finding("invalid_model", "model entry is missing provider or model_id.")
            )
            continue
        key = (provider, model_id)
        if key in model_by_key:
            findings.append(_finding("duplicate_model", f"duplicate model {provider}/{model_id}."))
        model_by_key[key] = raw
        if str(raw.get("lifecycle", "")).strip().lower() == "current":
            source_ids = raw.get("source_ids")
            if not isinstance(source_ids, list) or not source_ids:
                findings.append(
                    _finding(
                        "missing_source",
                        f"current model {provider}/{model_id} has no source_ids.",
                    )
                )
            else:
                missing_sources = [
                    str(item) for item in source_ids if str(item) not in source_by_id
                ]
                if missing_sources:
                    findings.append(
                        _finding(
                            "missing_source",
                            f"current model {provider}/{model_id} references absent sources: "
                            f"{missing_sources}.",
                        )
                    )
            pricing = raw.get("pricing")
            if not isinstance(pricing, dict) or not pricing.get("as_of"):
                findings.append(
                    _finding(
                        "missing_pricing_date",
                        f"current model {provider}/{model_id} lacks dated pricing facts.",
                    )
                )

    raw_evidence = registry.get("evidence")
    evidence = raw_evidence if isinstance(raw_evidence, list) else []
    evidence_by_id = {
        str(item.get("evidence_id", "")).strip(): item
        for item in evidence
        if isinstance(item, dict) and str(item.get("evidence_id", "")).strip()
    }
    for evidence_id, item in evidence_by_id.items():
        evidence_sources = item.get("source_ids", [])
        if isinstance(evidence_sources, list):
            missing_sources = [
                str(source) for source in evidence_sources if str(source) not in source_by_id
            ]
            if missing_sources:
                findings.append(
                    _finding(
                        "missing_source",
                        f"evidence {evidence_id} references absent sources: {missing_sources}.",
                    )
                )

    selections = registry.get("selections")
    if not isinstance(selections, list):
        return findings + [_finding("invalid_registry", "selections must be a list.")]

    selection_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    policy_profiles = (policy or {}).get("profiles", {})
    if not isinstance(policy_profiles, dict):
        policy_profiles = {}

    for raw in selections:
        if not isinstance(raw, dict):
            findings.append(_finding("invalid_selection", "selection entries must be objects."))
            continue
        profile = str(raw.get("profile", "")).strip()
        provider = _normalize_provider(str(raw.get("provider", "")))
        model_id = str(raw.get("model_id", "")).strip()
        key = (profile, provider)
        if not profile or not provider or not model_id:
            findings.append(
                _finding(
                    "invalid_selection",
                    "selection is missing profile, provider, or model_id.",
                )
            )
            continue
        if key in selection_by_key:
            findings.append(
                _finding(
                    "duplicate_selection",
                    f"multiple selections exist for profile/provider {profile}/{provider}.",
                )
            )
        selection_by_key[key] = raw

        if policy is not None and profile not in policy_profiles:
            findings.append(
                _finding("unknown_profile", f"selection references unknown profile {profile!r}.")
            )

        model = model_by_key.get((provider, model_id))
        if model is None:
            findings.append(
                _finding(
                    "unknown_selection",
                    f"selection {profile}/{provider} references absent model {model_id}.",
                )
            )
        else:
            if model.get("blocked"):
                findings.append(
                    _finding(
                        "blocked_selection",
                        f"selection {profile}/{provider} uses blocked model {model_id}.",
                    )
                )
            lifecycle = str(model.get("lifecycle", "")).strip().lower()
            if lifecycle != "current":
                findings.append(
                    _finding(
                        "inactive_selection",
                        f"selection {profile}/{provider} uses lifecycle={lifecycle or 'missing'} "
                        f"model {model_id}.",
                    )
                )

        status = str(raw.get("status", "")).strip().lower()
        if status not in VALID_SELECTION_STATUSES:
            findings.append(
                _finding(
                    "invalid_selection_status",
                    f"selection {profile}/{provider} has status {status!r}.",
                )
            )

        evidence_ids = raw.get("evidence_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            findings.append(
                _finding(
                    "missing_evidence",
                    f"selection {profile}/{provider} has no evidence_ids.",
                )
            )
            evidence_ids = []
        missing = [str(item) for item in evidence_ids if str(item) not in evidence_by_id]
        if missing:
            findings.append(
                _finding(
                    "missing_evidence",
                    f"selection {profile}/{provider} references absent evidence: {missing}.",
                )
            )
        if status == "approved":
            benchmark_evidence = [
                evidence_by_id[str(item)]
                for item in evidence_ids
                if str(item) in evidence_by_id
                and evidence_by_id[str(item)].get("kind") == "workload-benchmark"
                and evidence_by_id[str(item)].get("status") == "passed"
                and evidence_by_id[str(item)].get("schema")
                == "workflows-model-benchmark-evidence/v1"
                and evidence_by_id[str(item)].get("profile") == profile
                and evidence_by_id[str(item)].get("model_id") == model_id
                and evidence_by_id[str(item)].get("policy_id") == (policy or {}).get("policy_id")
                and evidence_by_id[str(item)].get("corpus_version")
                and evidence_by_id[str(item)].get("prompt_version")
                and evidence_by_id[str(item)].get("measured_at")
                and isinstance(evidence_by_id[str(item)].get("gate_results"), dict)
                and all(evidence_by_id[str(item)]["gate_results"].values())
            ]
            if not benchmark_evidence:
                findings.append(
                    _finding(
                        "unproved_approval",
                        f"approved selection {profile}/{provider} lacks passed workload-benchmark evidence.",
                    )
                )

        try:
            selection_review = _parse_date(str(raw.get("review_by", "")))
        except ValueError:
            findings.append(
                _finding(
                    "selection_review_overdue",
                    f"selection {profile}/{provider} has missing or invalid review_by.",
                )
            )
        else:
            if selection_review < today:
                kind = (
                    "provisional_overdue" if status == "provisional" else "selection_review_overdue"
                )
                findings.append(
                    _finding(
                        kind,
                        f"selection {profile}/{provider} review was due {selection_review}.",
                    )
                )

    raw_slots = slots.get("slots")
    if not isinstance(raw_slots, list):
        return findings + [_finding("invalid_slots", "slots must be a list.")]
    for raw in raw_slots:
        if not isinstance(raw, dict):
            findings.append(_finding("invalid_slot", "slot entries must be objects."))
            continue
        name = str(raw.get("name", "?")).strip()
        provider = _normalize_provider(str(raw.get("provider", "")))
        profile = str(raw.get("profile", "")).strip()
        explicit_model = str(raw.get("model", "")).strip()
        if not provider:
            findings.append(_finding("invalid_slot", f"slot {name!r} has no provider."))
            continue
        if explicit_model:
            model = model_by_key.get((provider, explicit_model))
            # Explicit-profile pins must match their reviewed decision.  A
            # legacy pin without a profile is also valid at runtime when the
            # pin is a current, unblocked catalog model.
            effective_profile = profile or "verifier-balanced"
            selected = selection_by_key.get((effective_profile, provider))
            legacy_pin_is_current = bool(
                not profile
                and model is not None
                and not model.get("blocked")
                and str(model.get("lifecycle", "")).strip().lower() == "current"
            )
            if (
                selected
                and selected.get("model_id") != explicit_model
                and not legacy_pin_is_current
            ):
                findings.append(
                    _finding(
                        "selection_override",
                        f"slot {name!r} pins {provider}/{explicit_model} instead of reviewed "
                        f"selection {selected.get('model_id')} for {effective_profile}.",
                    )
                )
            if model is None:
                findings.append(
                    _finding(
                        "unknown_pin",
                        f"slot {name!r} pins absent model {provider}/{explicit_model}.",
                    )
                )
            elif model.get("blocked"):
                findings.append(
                    _finding(
                        "blocked_pin",
                        f"slot {name!r} pins blocked model {provider}/{explicit_model}.",
                    )
                )
            continue
        if not profile:
            findings.append(
                _finding(
                    "missing_profile",
                    f"slot {name!r} has neither an explicit model nor a profile.",
                )
            )
        elif (profile, provider) not in selection_by_key:
            findings.append(
                _finding(
                    "missing_selection",
                    f"slot {name!r} has no selection for {profile}/{provider}.",
                )
            )

    return findings


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Model-registry decision freshness gate.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--slots", type=Path, default=DEFAULT_SLOTS_PATH)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    parser.add_argument("--today", type=str, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        registry = _load_json(args.registry)
        slots = _load_json(args.slots)
        policy = _load_json(args.policy)
        today = _parse_date(args.today) if args.today else _dt.date.today()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    findings = evaluate(
        registry,
        slots,
        today=today,
        max_age_days=args.max_age_days,
        policy=policy,
    )
    if args.json:
        print(json.dumps({"fresh": not findings, "findings": findings}, indent=2))
    elif findings:
        print(f"Model registry freshness: {len(findings)} finding(s):")
        for finding in findings:
            print(f"  [{finding['kind']}] {finding['detail']}")
    else:
        print("Model registry is fresh: decisions, evidence, and slots are consistent.")
    return 1 if findings else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
