"""Shared LLM slot and model-registry resolution helpers.

The registry records model facts separately from explicit workload-profile
selection decisions. Runtime selection never manufactures quality or cost scores.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

ENV_MODEL_REGISTRY_CONFIG = "LANGCHAIN_MODEL_REGISTRY_CONFIG"
ENV_SLOT_CONFIG = "LANGCHAIN_SLOT_CONFIG"

PROVIDER_OPENAI = "openai"
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_GITHUB = "github-models"
DEFAULT_SELECTION_PROFILE = "verifier-balanced"

DEFAULT_SLOT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "llm_slots.json"
DEFAULT_MODEL_REGISTRY_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "model_registry.json"
)


@dataclass(frozen=True, slots=True)
class ModelRegistryEntry:
    provider: str
    model: str
    blocked: bool
    lifecycle: str = "unknown"
    # Retained as empty compatibility attributes for callers migrating from v1.
    # They are deliberately not inputs to model selection.
    quality: dict[str, float] | None = None
    cost_score: float | None = None


@dataclass(frozen=True, slots=True)
class SelectionDecision:
    profile: str
    provider: str
    model: str
    status: str
    review_by: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SlotDefinition:
    name: str
    provider: str
    model: str


def normalize_provider(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in {"github", "github_models", "github-models"}:
        return PROVIDER_GITHUB
    if normalized in {"anthropic", "claude"}:
        return PROVIDER_ANTHROPIC
    if normalized == PROVIDER_OPENAI:
        return PROVIDER_OPENAI
    return None


def _registry_path() -> Path:
    configured = os.environ.get(ENV_MODEL_REGISTRY_CONFIG)
    return Path(configured) if configured else DEFAULT_MODEL_REGISTRY_CONFIG_PATH


def _slot_path() -> Path:
    configured = os.environ.get(ENV_SLOT_CONFIG)
    return Path(configured) if configured else DEFAULT_SLOT_CONFIG_PATH


def _load_object(path: Path, *, label: str) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("Could not read %s %s", label, path)
        return None
    if not isinstance(payload, dict):
        logger.warning("Invalid %s format in %s; expected object", label, path)
        return None
    return payload


def _slot_entries(payload: dict[str, object], path: Path) -> list[dict[str, object]]:
    raw_slots = payload.get("slots", [])
    if not isinstance(raw_slots, list):
        logger.warning("Invalid slot config format in %s; expected slots list", path)
        return []
    slots: list[dict[str, object]] = []
    for raw_slot in raw_slots:
        if isinstance(raw_slot, dict):
            slots.append(raw_slot)
        else:
            logger.warning("Ignoring invalid slot entry in %s; expected object", path)
    return slots


def load_model_registry() -> list[ModelRegistryEntry]:
    path = _registry_path()
    payload = _load_object(path, label="model registry")
    if payload is None:
        return []
    raw_models = payload.get("models", [])
    if not isinstance(raw_models, list):
        logger.warning("Invalid model registry format in %s; expected models list", path)
        return []

    entries: list[ModelRegistryEntry] = []
    for raw_entry in raw_models:
        if not isinstance(raw_entry, dict):
            logger.warning("Ignoring invalid model registry entry in %s; expected object", path)
            continue
        provider = normalize_provider(str(raw_entry.get("provider", "")))
        model = str(raw_entry.get("model_id", "")).strip()
        if not provider or not model:
            continue
        entries.append(
            ModelRegistryEntry(
                provider=provider,
                model=model,
                blocked=bool(raw_entry.get("blocked", False)),
                lifecycle=str(raw_entry.get("lifecycle", "unknown")).strip().lower(),
                quality={},
            )
        )
    return entries


def load_selection_decisions() -> list[SelectionDecision]:
    path = _registry_path()
    payload = _load_object(path, label="model registry")
    if payload is None:
        return []
    raw_selections = payload.get("selections", [])
    if not isinstance(raw_selections, list):
        logger.warning("Invalid model registry format in %s; expected selections list", path)
        return []

    decisions: list[SelectionDecision] = []
    for raw in raw_selections:
        if not isinstance(raw, dict):
            continue
        provider = normalize_provider(str(raw.get("provider", "")))
        profile = str(raw.get("profile", "")).strip()
        model = str(raw.get("model_id", "")).strip()
        evidence = raw.get("evidence_ids", [])
        if not provider or not profile or not model or not isinstance(evidence, list):
            continue
        decisions.append(
            SelectionDecision(
                profile=profile,
                provider=provider,
                model=model,
                status=str(raw.get("status", "")).strip().lower(),
                review_by=str(raw.get("review_by", "")).strip(),
                evidence_ids=tuple(str(item) for item in evidence if str(item).strip()),
            )
        )
    return decisions


def _model_registry_format_valid() -> bool:
    payload = _load_object(_registry_path(), label="model registry")
    return bool(
        payload is not None
        and isinstance(payload.get("models"), list)
        and isinstance(payload.get("selections"), list)
    )


def registry_entry_for(
    provider: str, model: str, registry: list[ModelRegistryEntry] | None = None
) -> ModelRegistryEntry | None:
    entries = registry if registry is not None else load_model_registry()
    normalized_provider = normalize_provider(provider)
    normalized_model = model.strip()
    return next(
        (
            entry
            for entry in entries
            if entry.provider == normalized_provider and entry.model == normalized_model
        ),
        None,
    )


def is_model_blocked(
    provider: str, model: str, registry: list[ModelRegistryEntry] | None = None
) -> bool:
    entry = registry_entry_for(provider, model, registry=registry)
    return bool(entry and entry.blocked)


def select_model_for_profile(
    *,
    provider: str,
    profile: str = DEFAULT_SELECTION_PROFILE,
    registry: list[ModelRegistryEntry] | None = None,
    decisions: list[SelectionDecision] | None = None,
) -> str | None:
    """Resolve the one explicit reviewed decision for provider/profile."""
    entries = registry if registry is not None else load_model_registry()
    selections = decisions if decisions is not None else load_selection_decisions()
    normalized_provider = normalize_provider(provider)
    matches = [
        decision
        for decision in selections
        if decision.provider == normalized_provider and decision.profile == profile
    ]
    if len(matches) != 1:
        if matches:
            logger.warning(
                "Ambiguous model selections for %s/%s; expected exactly one",
                normalized_provider,
                profile,
            )
        return None
    decision = matches[0]
    if not decision.evidence_ids:
        logger.warning(
            "Model selection %s/%s has no evidence; refusing to use it",
            normalized_provider,
            profile,
        )
        return None
    entry = registry_entry_for(decision.provider, decision.model, registry=entries)
    if entry is None or entry.blocked or entry.lifecycle != "current":
        return None
    if decision.status not in {"provisional", "approved"}:
        return None
    return decision.model


def select_model_for_tier(
    *,
    provider: str,
    tier: str,
    registry: list[ModelRegistryEntry] | None = None,
    **_ignored: object,
) -> str | None:
    """Compatibility adapter for v1 callers; tiers no longer rank models."""
    logger.warning(
        "quality tier %s is deprecated; resolving profile %s",
        tier,
        DEFAULT_SELECTION_PROFILE,
    )
    return select_model_for_profile(provider=provider, registry=registry)


def configured_model_for_provider(
    provider: str,
    *,
    fallback: str = "",
    profile: str = DEFAULT_SELECTION_PROFILE,
    tier: str | None = None,
    registry: list[ModelRegistryEntry] | None = None,
) -> str:
    normalized_provider = normalize_provider(provider)
    entries = registry if registry is not None else load_model_registry()
    # An explicit slot config is an execution allowlist, including when its
    # path is missing or malformed. Never broaden execution because a
    # configured allowlist cannot be read or does not contain this provider.
    if os.environ.get(ENV_SLOT_CONFIG):
        configured_slots = load_slot_config()
        if not configured_slots:
            return ""
        for slot in apply_slot_env_overrides(configured_slots):
            if (
                slot.provider == normalized_provider
                and slot.model
                and not is_model_blocked(slot.provider, slot.model, registry=entries)
            ):
                return slot.model
        return ""

    selected = select_model_for_profile(provider=provider, profile=profile, registry=entries)
    if selected:
        return selected
    if fallback and not is_model_blocked(provider, fallback, registry=entries):
        return fallback
    return ""


def default_slots(*, github_default_model: str = "") -> list[SlotDefinition]:
    """Build no-slot-config defaults from registry decisions, never version constants."""
    slots: list[SlotDefinition] = []
    for index, provider in enumerate(
        (PROVIDER_OPENAI, PROVIDER_ANTHROPIC, PROVIDER_GITHUB), start=1
    ):
        model = select_model_for_profile(provider=provider)
        if not model and provider == PROVIDER_GITHUB:
            model = github_default_model.strip()
        if model:
            slots.append(SlotDefinition(name=f"slot{index}", provider=provider, model=model))
    return slots


def load_slot_config(*, github_default_model: str = "") -> list[SlotDefinition]:
    path = _slot_path()
    payload = _load_object(path, label="slot config")
    fallback_slots = default_slots(github_default_model=github_default_model)
    if payload is None:
        # An unreadable or missing explicitly configured slot file must fail
        # closed. Only an unconfigured default path permits default slots.
        if os.environ.get(ENV_SLOT_CONFIG):
            return []
        return fallback_slots

    registry = load_model_registry()
    slot_entries = _slot_entries(payload, path)
    if not _model_registry_format_valid() and any(
        str(entry.get("provider", "")).strip()
        and not str(entry.get("model", "")).strip()
        and str(
            entry.get("profile") or entry.get("quality_tier") or entry.get("tier") or ""
        ).strip()
        for entry in slot_entries
    ):
        return [] if os.environ.get(ENV_SLOT_CONFIG) else fallback_slots

    slots: list[SlotDefinition] = []
    fallback_by_provider = {slot.provider: slot for slot in fallback_slots}
    for idx, entry in enumerate(slot_entries, start=1):
        provider = normalize_provider(str(entry.get("provider", "")))
        explicit_model = str(entry.get("model", "")).strip()
        configured_profile = str(entry.get("profile") or "").strip()
        profile = configured_profile or DEFAULT_SELECTION_PROFILE
        model = ""
        if provider:
            model = (
                select_model_for_profile(provider=provider, profile=profile, registry=registry)
                or ""
            )
        explicit_entry = (
            registry_entry_for(provider, explicit_model, registry=registry)
            if provider and explicit_model
            else None
        )
        if (
            provider
            and explicit_model
            and not configured_profile
            and explicit_entry
            and not (explicit_entry.blocked or explicit_entry.lifecycle != "current")
        ):
            model = explicit_model
        elif provider and explicit_model and explicit_model != model:
            logger.warning(
                "Skipping unresolved slot model pin %s/%s; reviewed %s selection is %s",
                provider,
                explicit_model,
                profile,
                model or "unavailable",
            )
            # An explicit legacy pin is also an allowlist decision. Do not
            # silently substitute a newer reviewed selection for it.
            continue
        if provider and configured_profile and not model:
            logger.warning(
                "Skipping slot with unresolved reviewed profile: %s/%s",
                configured_profile,
                provider,
            )
            continue
        if provider and not model:
            fallback_slot = fallback_by_provider.get(provider)
            model = fallback_slot.model if fallback_slot else ""
        if not provider or not model:
            continue
        if is_model_blocked(provider, model, registry=registry):
            logger.warning("Skipping blocked LLM model in slot config: %s/%s", provider, model)
            continue
        name = str(entry.get("name") or f"slot{idx}").strip() or f"slot{idx}"
        slots.append(SlotDefinition(name=name, provider=provider, model=model))
    # A present slot file is an allowlist.  If every configured slot is
    # unusable, fail closed instead of broadening execution to default providers.
    return slots


def apply_slot_env_overrides(
    slots: list[SlotDefinition],
    *,
    env_model_name: str = "LANGCHAIN_MODEL",
    env_slot_prefix: str = "LANGCHAIN_SLOT",
) -> list[SlotDefinition]:
    registry = load_model_registry()
    updated: list[SlotDefinition] = []
    for idx, slot in enumerate(slots, start=1):
        provider_override = normalize_provider(os.environ.get(f"{env_slot_prefix}{idx}_PROVIDER"))
        model_override = os.environ.get(f"{env_slot_prefix}{idx}_MODEL")
        if idx == 1:
            model_override = model_override or os.environ.get(env_model_name)
        provider = provider_override or slot.provider
        model = (model_override or slot.model).strip()
        if is_model_blocked(provider, model, registry=registry):
            logger.warning("Skipping blocked LLM slot override: %s/%s", provider, model)
            override_requested = provider_override is not None or model_override is not None
            if override_requested and not is_model_blocked(
                slot.provider, slot.model, registry=registry
            ):
                updated.append(slot)
            continue
        updated.append(SlotDefinition(name=slot.name, provider=provider, model=model))
    return updated


def resolve_slots(
    *,
    github_default_model: str = "",
    env_model_name: str = "LANGCHAIN_MODEL",
    env_slot_prefix: str = "LANGCHAIN_SLOT",
) -> list[SlotDefinition]:
    slots = load_slot_config(github_default_model=github_default_model)
    # Preserve an explicit runtime override as an emergency bootstrap when the
    # registry file is unavailable. Empty models are never invoked directly;
    # langchain_client skips them when the override cannot serve that provider.
    if not slots and not os.environ.get(ENV_SLOT_CONFIG) and os.environ.get(env_model_name):
        slots = [
            SlotDefinition(name=f"slot{index}", provider=provider, model="")
            for index, provider in enumerate(
                (PROVIDER_OPENAI, PROVIDER_ANTHROPIC, PROVIDER_GITHUB), start=1
            )
        ]
    return apply_slot_env_overrides(
        slots,
        env_model_name=env_model_name,
        env_slot_prefix=env_slot_prefix,
    )
