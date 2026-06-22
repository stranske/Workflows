"""Shared LLM slot and model-registry resolution helpers."""

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

DEFAULT_SLOT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "llm_slots.json"
DEFAULT_MODEL_REGISTRY_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "model_registry.json"
)


@dataclass(frozen=True)
class ModelRegistryEntry:
    provider: str
    model: str
    blocked: bool
    quality: dict[str, float]


@dataclass(frozen=True)
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
    config_path = os.environ.get(ENV_MODEL_REGISTRY_CONFIG)
    path = Path(config_path) if config_path else DEFAULT_MODEL_REGISTRY_CONFIG_PATH
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read model registry %s; continuing without registry", path)
        return []
    if not isinstance(payload, dict):
        logger.warning("Invalid model registry format in %s; expected object", path)
        return []

    entries: list[ModelRegistryEntry] = []
    for raw_entry in payload.get("models", []):
        if not isinstance(raw_entry, dict):
            logger.warning("Ignoring invalid model registry entry in %s; expected object", path)
            continue
        provider = normalize_provider(str(raw_entry.get("provider", "")))
        model = str(raw_entry.get("model_id", "")).strip()
        if not provider or not model:
            continue
        quality_payload = raw_entry.get("quality", {})
        quality = {
            str(tier).upper(): float(score)
            for tier, score in quality_payload.items()
            if isinstance(score, int | float)
        }
        entries.append(
            ModelRegistryEntry(
                provider=provider,
                model=model,
                blocked=bool(raw_entry.get("blocked", False)),
                quality=quality,
            )
        )
    return entries


def registry_entry_for(
    provider: str, model: str, registry: list[ModelRegistryEntry] | None = None
) -> ModelRegistryEntry | None:
    entries = registry if registry is not None else load_model_registry()
    normalized_provider = normalize_provider(provider)
    normalized_model = model.strip()
    for entry in entries:
        if entry.provider == normalized_provider and entry.model == normalized_model:
            return entry
    return None


def is_model_blocked(
    provider: str, model: str, registry: list[ModelRegistryEntry] | None = None
) -> bool:
    entry = registry_entry_for(provider, model, registry=registry)
    return bool(entry and entry.blocked)


def select_model_for_tier(
    *,
    provider: str,
    tier: str,
    registry: list[ModelRegistryEntry] | None = None,
) -> str | None:
    entries = registry if registry is not None else load_model_registry()
    normalized_provider = normalize_provider(provider)
    normalized_tier = tier.strip().upper()
    candidates = [
        entry
        for entry in entries
        if entry.provider == normalized_provider
        and not entry.blocked
        and normalized_tier in entry.quality
    ]
    if not candidates:
        return None
    selected = max(candidates, key=lambda entry: entry.quality[normalized_tier])
    return selected.model


def configured_model_for_provider(
    provider: str,
    *,
    fallback: str,
    tier: str = "T3",
    registry: list[ModelRegistryEntry] | None = None,
) -> str:
    normalized_provider = normalize_provider(provider)
    entries = registry if registry is not None else load_model_registry()

    config_path = os.environ.get(ENV_SLOT_CONFIG)
    path = Path(config_path) if config_path else DEFAULT_SLOT_CONFIG_PATH
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        if not isinstance(payload, dict):
            logger.warning("Invalid slot config format in %s; expected object", path)
            payload = {}
        for slot in _slot_entries(payload, path):
            slot_provider = normalize_provider(str(slot.get("provider", "")))
            if slot_provider != normalized_provider:
                continue
            model = str(slot.get("model", "")).strip()
            slot_tier = str(slot.get("quality_tier") or slot.get("tier") or tier).strip()
            if not model and slot_tier:
                model = (
                    select_model_for_tier(
                        provider=slot_provider or "",
                        tier=slot_tier,
                        registry=entries,
                    )
                    or ""
                )
            if model and not is_model_blocked(slot_provider or "", model, registry=entries):
                return model

    selected = select_model_for_tier(provider=provider, tier=tier, registry=entries)
    if selected:
        return selected
    if not is_model_blocked(provider, fallback, registry=entries):
        return fallback
    return ""


def default_slots(*, github_default_model: str) -> list[SlotDefinition]:
    return [
        SlotDefinition(name="slot1", provider=PROVIDER_OPENAI, model="gpt-5.4"),
        SlotDefinition(name="slot2", provider=PROVIDER_ANTHROPIC, model="claude-sonnet-4-6"),
        SlotDefinition(name="slot3", provider=PROVIDER_GITHUB, model=github_default_model),
    ]


def load_slot_config(*, github_default_model: str) -> list[SlotDefinition]:
    config_path = os.environ.get(ENV_SLOT_CONFIG)
    path = Path(config_path) if config_path else DEFAULT_SLOT_CONFIG_PATH
    fallback_slots = default_slots(github_default_model=github_default_model)
    if not path.is_file():
        return fallback_slots
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback_slots
    if not isinstance(payload, dict):
        logger.warning("Invalid slot config format in %s; expected object", path)
        return fallback_slots

    registry = load_model_registry()
    slots: list[SlotDefinition] = []
    for idx, entry in enumerate(_slot_entries(payload, path), start=1):
        provider = normalize_provider(str(entry.get("provider", "")))
        model = str(entry.get("model", "")).strip()
        tier = str(entry.get("quality_tier") or entry.get("tier") or "").strip()
        if provider and not model and tier:
            model = select_model_for_tier(provider=provider, tier=tier, registry=registry) or ""
        if not provider or not model:
            continue
        if is_model_blocked(provider, model, registry=registry):
            logger.warning("Skipping blocked LLM model in slot config: %s/%s", provider, model)
            continue
        name = str(entry.get("name") or f"slot{idx}").strip() or f"slot{idx}"
        slots.append(SlotDefinition(name=name, provider=provider, model=model))

    return slots or fallback_slots


def apply_slot_env_overrides(
    slots: list[SlotDefinition],
    *,
    env_model_name: str = "LANGCHAIN_MODEL",
    env_slot_prefix: str = "LANGCHAIN_SLOT",
) -> list[SlotDefinition]:
    registry = load_model_registry()
    updated: list[SlotDefinition] = []
    for idx, slot in enumerate(slots, start=1):
        provider_key = f"{env_slot_prefix}{idx}_PROVIDER"
        model_key = f"{env_slot_prefix}{idx}_MODEL"
        provider_override = normalize_provider(os.environ.get(provider_key))
        model_override = os.environ.get(model_key)
        if idx == 1:
            model_override = model_override or os.environ.get(env_model_name)
        provider = provider_override or slot.provider
        model = (model_override or slot.model).strip()
        if is_model_blocked(provider, model, registry=registry):
            logger.warning("Skipping blocked LLM slot override: %s/%s", provider, model)
            continue
        updated.append(
            SlotDefinition(
                name=slot.name,
                provider=provider,
                model=model,
            )
        )
    return updated


def resolve_slots(
    *,
    github_default_model: str,
    env_model_name: str = "LANGCHAIN_MODEL",
    env_slot_prefix: str = "LANGCHAIN_SLOT",
) -> list[SlotDefinition]:
    return apply_slot_env_overrides(
        load_slot_config(github_default_model=github_default_model),
        env_model_name=env_model_name,
        env_slot_prefix=env_slot_prefix,
    )
