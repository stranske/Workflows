"""
Shared LangChain client construction helpers.

Standardizes provider selection (slot order with OpenAI, Claude, then GitHub Models),
timeouts, retries, and environment overrides.
"""

from __future__ import annotations

import contextlib
import logging
import os
from dataclasses import dataclass

from tools import llm_registry as _llm_registry
from tools.llm_provider import DEFAULT_MODEL, GITHUB_MODELS_BASE_URL
from tools.llm_registry import (
    PROVIDER_ANTHROPIC,
    PROVIDER_GITHUB,
    PROVIDER_OPENAI,
    ModelRegistryEntry,
    SlotDefinition,
    apply_slot_env_overrides,
    default_slots,
    is_model_blocked,
    load_model_registry,
    load_slot_config,
    normalize_provider,
    registry_entry_for,
    resolve_slots,
    select_model_for_tier,
)

logger = logging.getLogger(__name__)

ENV_PROVIDER = "LANGCHAIN_PROVIDER"
ENV_MODEL = "LANGCHAIN_MODEL"
ENV_TIMEOUT = "LANGCHAIN_TIMEOUT"
ENV_MAX_RETRIES = "LANGCHAIN_MAX_RETRIES"
ENV_SLOT_CONFIG = _llm_registry.ENV_SLOT_CONFIG
ENV_MODEL_REGISTRY_CONFIG = _llm_registry.ENV_MODEL_REGISTRY_CONFIG
ENV_SLOT_PREFIX = "LANGCHAIN_SLOT"
ENV_ANTHROPIC_KEY = "CLAUDE_API_STRANSKE"
DEFAULT_SLOT_CONFIG_PATH = _llm_registry.DEFAULT_SLOT_CONFIG_PATH
DEFAULT_MODEL_REGISTRY_CONFIG_PATH = _llm_registry.DEFAULT_MODEL_REGISTRY_CONFIG_PATH


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning("Invalid %s value %r; using default %s", name, value, default)
        return default


DEFAULT_TIMEOUT = _env_int(ENV_TIMEOUT, 60)
DEFAULT_MAX_RETRIES = _env_int(ENV_MAX_RETRIES, 2)


@dataclass(frozen=True)
class ClientInfo:
    client: object
    provider: str
    model: str

    @property
    def provider_label(self) -> str:
        return f"{self.provider}/{self.model}"


def _normalize_provider(value: str | None) -> str | None:
    return normalize_provider(value)


def _resolve_provider(provider: str | None, *, force_openai: bool) -> tuple[str | None, bool]:
    if force_openai:
        return PROVIDER_OPENAI, True
    if provider:
        return _normalize_provider(provider), True
    env_provider = os.environ.get(ENV_PROVIDER)
    return _normalize_provider(env_provider), False


def _resolve_model(model: str | None) -> str:
    env_model = os.environ.get(ENV_MODEL)
    return model or env_model or DEFAULT_MODEL


def _load_model_registry() -> list[ModelRegistryEntry]:
    return load_model_registry()


def _registry_entry_for(
    provider: str, model: str, registry: list[ModelRegistryEntry] | None = None
) -> ModelRegistryEntry | None:
    return registry_entry_for(provider, model, registry=registry)


def _is_model_blocked(
    provider: str, model: str, registry: list[ModelRegistryEntry] | None = None
) -> bool:
    return is_model_blocked(provider, model, registry=registry)


def _select_model_for_tier(
    *,
    provider: str,
    tier: str,
    registry: list[ModelRegistryEntry] | None = None,
) -> str | None:
    return select_model_for_tier(provider=provider, tier=tier, registry=registry)


def _default_slots() -> list[SlotDefinition]:
    return default_slots(github_default_model=DEFAULT_MODEL)


def _load_slot_config() -> list[SlotDefinition]:
    return load_slot_config(github_default_model=DEFAULT_MODEL)


def _apply_slot_env_overrides(slots: list[SlotDefinition]) -> list[SlotDefinition]:
    return apply_slot_env_overrides(
        slots,
        env_model_name=ENV_MODEL,
        env_slot_prefix=ENV_SLOT_PREFIX,
    )


def _resolve_slots() -> list[SlotDefinition]:
    return resolve_slots(
        github_default_model=DEFAULT_MODEL,
        env_model_name=ENV_MODEL,
        env_slot_prefix=ENV_SLOT_PREFIX,
    )


def _is_reasoning_model(model: str) -> bool:
    """Return True if the model is an OpenAI reasoning model that rejects temperature.

    Supported naming pattern: `o` + digits, with optional suffixes. Examples: `o1`,
    `o1-preview`, `o1-preview-2024-09-12`, `o3`, `o3-mini`, `o3-pro`, `o4-mini`,
    `o4-mini-deep-research`. Non-matching examples: `o`, `o-1`, `openai-o1`, `oasis-1`.
    """
    name = model.lower().strip()
    # o-series reasoning models use an `o` prefix followed by digits with optional
    # hyphen-separated suffixes: o1, o1-preview, o1-preview-2024-09-12, o3, o3-mini,
    # o3-pro, o4-mini, o4-mini-deep-research.
    return bool(__import__("re").fullmatch(r"o[0-9]+(?:-[a-z0-9]+)*", name))


def _build_openai_client(
    chat_openai: type, *, model: str, token: str, timeout: int, max_retries: int
) -> object:
    kwargs: dict = {
        "model": model,
        "api_key": token,
        "timeout": timeout,
        "max_retries": max_retries,
    }
    if not _is_reasoning_model(model):
        kwargs["temperature"] = 0.1
    return chat_openai(**kwargs)


def _build_anthropic_client(
    chat_anthropic: type, *, model: str, token: str, timeout: int, max_retries: int
) -> object:
    return chat_anthropic(
        model=model,
        anthropic_api_key=token,
        temperature=0.1,
        timeout=timeout,
        max_retries=max_retries,
    )


def _build_github_client(
    chat_openai: type, *, model: str, token: str, timeout: int, max_retries: int
) -> object:
    kwargs: dict = {
        "model": model,
        "base_url": GITHUB_MODELS_BASE_URL,
        "api_key": token,
        "timeout": timeout,
        "max_retries": max_retries,
    }
    if not _is_reasoning_model(model):
        kwargs["temperature"] = 0.1
    return chat_openai(**kwargs)


def build_chat_client(
    *,
    model: str | None = None,
    provider: str | None = None,
    force_openai: bool = False,
    timeout: int | None = None,
    max_retries: int | None = None,
) -> ClientInfo | None:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        chat_openai_cls = None
    else:
        chat_openai_cls = ChatOpenAI

    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError:
        chat_anthropic_cls = None
    else:
        chat_anthropic_cls = ChatAnthropic

    github_token = os.environ.get("GITHUB_TOKEN")
    openai_token = os.environ.get("OPENAI_API_KEY")
    anthropic_token = os.environ.get(ENV_ANTHROPIC_KEY)
    if not github_token and not openai_token and not anthropic_token:
        return None

    selected_model = _resolve_model(model)
    selected_timeout = DEFAULT_TIMEOUT if timeout is None else timeout
    selected_retries = DEFAULT_MAX_RETRIES if max_retries is None else max_retries

    selected_provider, provider_explicit = _resolve_provider(provider, force_openai=force_openai)
    if provider_explicit and selected_provider is None:
        return None
    if selected_provider and _is_model_blocked(selected_provider, selected_model):
        logger.warning("Refusing blocked LLM model: %s/%s", selected_provider, selected_model)
        return None

    if selected_provider == PROVIDER_GITHUB:
        if not github_token or not chat_openai_cls:
            return None
        try:
            client = _build_github_client(
                chat_openai_cls,
                model=selected_model,
                token=github_token,
                timeout=selected_timeout,
                max_retries=selected_retries,
            )
            return ClientInfo(client=client, provider=PROVIDER_GITHUB, model=selected_model)
        except Exception:
            return None

    if selected_provider == PROVIDER_OPENAI:
        if not openai_token or not chat_openai_cls:
            return None
        try:
            client = _build_openai_client(
                chat_openai_cls,
                model=selected_model,
                token=openai_token,
                timeout=selected_timeout,
                max_retries=selected_retries,
            )
            return ClientInfo(client=client, provider=PROVIDER_OPENAI, model=selected_model)
        except Exception:
            return None

    if selected_provider == PROVIDER_ANTHROPIC:
        if not anthropic_token or not chat_anthropic_cls:
            return None
        try:
            client = _build_anthropic_client(
                chat_anthropic_cls,
                model=selected_model,
                token=anthropic_token,
                timeout=selected_timeout,
                max_retries=selected_retries,
            )
            return ClientInfo(client=client, provider=PROVIDER_ANTHROPIC, model=selected_model)
        except Exception:
            return None

    # Auto-select: slot order (OpenAI -> Claude -> GitHub Models by default).
    slots = _resolve_slots()
    model_override = model or os.environ.get(ENV_MODEL)
    used_override = False
    for slot in slots:
        slot_model = model_override if model_override and not used_override else slot.model
        if model_override and not used_override and _is_model_blocked(slot.provider, slot_model):
            logger.warning("Skipping blocked LLM model override: %s/%s", slot.provider, slot_model)
            used_override = True
            slot_model = slot.model
        if _is_model_blocked(slot.provider, slot_model):
            logger.warning("Skipping blocked LLM model: %s/%s", slot.provider, slot_model)
            continue
        slot_available = any(
            (
                slot.provider == PROVIDER_OPENAI and openai_token,
                slot.provider == PROVIDER_ANTHROPIC and anthropic_token and chat_anthropic_cls,
                slot.provider == PROVIDER_GITHUB and github_token and chat_openai_cls,
            )
        )
        if not slot_available:
            continue
        if slot.provider == PROVIDER_OPENAI and openai_token and chat_openai_cls:
            with contextlib.suppress(Exception):
                client = _build_openai_client(
                    chat_openai_cls,
                    model=slot_model,
                    token=openai_token,
                    timeout=selected_timeout,
                    max_retries=selected_retries,
                )
                used_override = True
                return ClientInfo(client=client, provider=PROVIDER_OPENAI, model=slot_model)
        if slot.provider == PROVIDER_ANTHROPIC and anthropic_token and chat_anthropic_cls:
            with contextlib.suppress(Exception):
                client = _build_anthropic_client(
                    chat_anthropic_cls,
                    model=slot_model,
                    token=anthropic_token,
                    timeout=selected_timeout,
                    max_retries=selected_retries,
                )
                used_override = True
                return ClientInfo(client=client, provider=PROVIDER_ANTHROPIC, model=slot_model)
        if slot.provider == PROVIDER_GITHUB and github_token and chat_openai_cls:
            with contextlib.suppress(Exception):
                client = _build_github_client(
                    chat_openai_cls,
                    model=slot_model,
                    token=github_token,
                    timeout=selected_timeout,
                    max_retries=selected_retries,
                )
                used_override = True
                return ClientInfo(client=client, provider=PROVIDER_GITHUB, model=slot_model)

    return None


def build_chat_clients(
    *,
    model1: str | None = None,
    model2: str | None = None,
    provider: str | None = None,
    timeout: int | None = None,
    max_retries: int | None = None,
) -> list[ClientInfo]:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        chat_openai_cls = None
    else:
        chat_openai_cls = ChatOpenAI

    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError:
        chat_anthropic_cls = None
    else:
        chat_anthropic_cls = ChatAnthropic

    github_token = os.environ.get("GITHUB_TOKEN")
    openai_token = os.environ.get("OPENAI_API_KEY")
    anthropic_token = os.environ.get(ENV_ANTHROPIC_KEY)
    if not github_token and not openai_token and not anthropic_token:
        return []

    selected_timeout = DEFAULT_TIMEOUT if timeout is None else timeout
    selected_retries = DEFAULT_MAX_RETRIES if max_retries is None else max_retries

    first_model = _resolve_model(model1)
    second_model = model2 or model1 or os.environ.get(ENV_MODEL) or DEFAULT_MODEL

    selected_provider, provider_explicit = _resolve_provider(provider, force_openai=False)
    if provider_explicit and selected_provider is None:
        return []
    registry = _load_model_registry()
    if selected_provider:
        blocked_models = [candidate for candidate in (first_model, second_model) if candidate]
        if any(
            _is_model_blocked(selected_provider, candidate, registry=registry)
            for candidate in blocked_models
        ):
            logger.warning("Refusing blocked LLM model for provider %s", selected_provider)
            return []

    clients: list[ClientInfo] = []

    if selected_provider:
        if selected_provider == PROVIDER_GITHUB and github_token and chat_openai_cls:
            with contextlib.suppress(Exception):
                clients.append(
                    ClientInfo(
                        client=_build_github_client(
                            chat_openai_cls,
                            model=first_model,
                            token=github_token,
                            timeout=selected_timeout,
                            max_retries=selected_retries,
                        ),
                        provider=PROVIDER_GITHUB,
                        model=first_model,
                    )
                )
            if second_model != first_model:
                with contextlib.suppress(Exception):
                    clients.append(
                        ClientInfo(
                            client=_build_github_client(
                                chat_openai_cls,
                                model=second_model,
                                token=github_token,
                                timeout=selected_timeout,
                                max_retries=selected_retries,
                            ),
                            provider=PROVIDER_GITHUB,
                            model=second_model,
                        )
                    )
        elif selected_provider == PROVIDER_OPENAI and openai_token and chat_openai_cls:
            with contextlib.suppress(Exception):
                clients.append(
                    ClientInfo(
                        client=_build_openai_client(
                            chat_openai_cls,
                            model=first_model,
                            token=openai_token,
                            timeout=selected_timeout,
                            max_retries=selected_retries,
                        ),
                        provider=PROVIDER_OPENAI,
                        model=first_model,
                    )
                )
            if second_model != first_model:
                with contextlib.suppress(Exception):
                    clients.append(
                        ClientInfo(
                            client=_build_openai_client(
                                chat_openai_cls,
                                model=second_model,
                                token=openai_token,
                                timeout=selected_timeout,
                                max_retries=selected_retries,
                            ),
                            provider=PROVIDER_OPENAI,
                            model=second_model,
                        )
                    )
        elif selected_provider == PROVIDER_ANTHROPIC and anthropic_token and chat_anthropic_cls:
            with contextlib.suppress(Exception):
                clients.append(
                    ClientInfo(
                        client=_build_anthropic_client(
                            chat_anthropic_cls,
                            model=first_model,
                            token=anthropic_token,
                            timeout=selected_timeout,
                            max_retries=selected_retries,
                        ),
                        provider=PROVIDER_ANTHROPIC,
                        model=first_model,
                    )
                )
            if second_model != first_model:
                with contextlib.suppress(Exception):
                    clients.append(
                        ClientInfo(
                            client=_build_anthropic_client(
                                chat_anthropic_cls,
                                model=second_model,
                                token=anthropic_token,
                                timeout=selected_timeout,
                                max_retries=selected_retries,
                            ),
                            provider=PROVIDER_ANTHROPIC,
                            model=second_model,
                        )
                    )

        return clients

    slots = _resolve_slots()
    candidate_slots: list[SlotDefinition] = []
    for slot in slots:
        if any(
            (
                slot.provider == PROVIDER_OPENAI and openai_token,
                slot.provider == PROVIDER_ANTHROPIC and anthropic_token and chat_anthropic_cls,
                slot.provider == PROVIDER_GITHUB and github_token and chat_openai_cls,
            )
        ):
            candidate_slots.append(slot)
        if len(candidate_slots) >= 2:
            break

    primary_override = model1 or os.environ.get(ENV_MODEL)
    secondary_override = model2 or model1
    model_overrides = [primary_override, secondary_override]
    for idx, slot in enumerate(candidate_slots):
        slot_model = model_overrides[idx] if idx < len(model_overrides) else None
        slot_model = slot_model or slot.model
        if _is_model_blocked(slot.provider, slot_model, registry=registry):
            logger.warning("Skipping blocked LLM model override: %s/%s", slot.provider, slot_model)
            continue
        if slot.provider == PROVIDER_OPENAI and openai_token and chat_openai_cls:
            with contextlib.suppress(Exception):
                clients.append(
                    ClientInfo(
                        client=_build_openai_client(
                            chat_openai_cls,
                            model=slot_model,
                            token=openai_token,
                            timeout=selected_timeout,
                            max_retries=selected_retries,
                        ),
                        provider=PROVIDER_OPENAI,
                        model=slot_model,
                    )
                )
        if slot.provider == PROVIDER_ANTHROPIC and anthropic_token and chat_anthropic_cls:
            with contextlib.suppress(Exception):
                clients.append(
                    ClientInfo(
                        client=_build_anthropic_client(
                            chat_anthropic_cls,
                            model=slot_model,
                            token=anthropic_token,
                            timeout=selected_timeout,
                            max_retries=selected_retries,
                        ),
                        provider=PROVIDER_ANTHROPIC,
                        model=slot_model,
                    )
                )
        if slot.provider == PROVIDER_GITHUB and github_token and chat_openai_cls:
            with contextlib.suppress(Exception):
                clients.append(
                    ClientInfo(
                        client=_build_github_client(
                            chat_openai_cls,
                            model=slot_model,
                            token=github_token,
                            timeout=selected_timeout,
                            max_retries=selected_retries,
                        ),
                        provider=PROVIDER_GITHUB,
                        model=slot_model,
                    )
                )

    return clients
