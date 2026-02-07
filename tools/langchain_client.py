"""
Shared LangChain client construction helpers.

Standardizes provider selection (slot order with OpenAI, Claude, then GitHub Models),
timeouts, retries, and environment overrides.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from tools.llm_provider import DEFAULT_MODEL, GITHUB_MODELS_BASE_URL

logger = logging.getLogger(__name__)

ENV_PROVIDER = "LANGCHAIN_PROVIDER"
ENV_MODEL = "LANGCHAIN_MODEL"
ENV_TIMEOUT = "LANGCHAIN_TIMEOUT"
ENV_MAX_RETRIES = "LANGCHAIN_MAX_RETRIES"
ENV_SLOT_CONFIG = "LANGCHAIN_SLOT_CONFIG"
ENV_SLOT_PREFIX = "LANGCHAIN_SLOT"
ENV_ANTHROPIC_KEY = "CLAUDE_API_STRANSKE"

PROVIDER_OPENAI = "openai"
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_GITHUB = "github-models"

DEFAULT_SLOT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "llm_slots.json"


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


@dataclass(frozen=True)
class SlotDefinition:
    name: str
    provider: str
    model: str


def _normalize_provider(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in {"github", "github_models", "github-models"}:
        return PROVIDER_GITHUB
    if normalized in {"anthropic", "claude"}:
        return PROVIDER_ANTHROPIC
    if normalized in {"openai"}:
        return PROVIDER_OPENAI
    return None


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


def _default_slots() -> list[SlotDefinition]:
    return [
        SlotDefinition(name="slot1", provider=PROVIDER_OPENAI, model="gpt-5.2"),
        SlotDefinition(
            name="slot2", provider=PROVIDER_ANTHROPIC, model="claude-sonnet-4-5-20250929"
        ),
        SlotDefinition(name="slot3", provider=PROVIDER_GITHUB, model=DEFAULT_MODEL),
    ]


def _load_slot_config() -> list[SlotDefinition]:
    config_path = os.environ.get(ENV_SLOT_CONFIG)
    path = Path(config_path) if config_path else DEFAULT_SLOT_CONFIG_PATH
    if not path.is_file():
        return _default_slots()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_slots()

    slots: list[SlotDefinition] = []
    for idx, entry in enumerate(payload.get("slots", []), start=1):
        provider = _normalize_provider(str(entry.get("provider", "")))
        model = str(entry.get("model", "")).strip()
        if not provider or not model:
            continue
        name = str(entry.get("name") or f"slot{idx}").strip() or f"slot{idx}"
        slots.append(SlotDefinition(name=name, provider=provider, model=model))

    return slots or _default_slots()


def _apply_slot_env_overrides(slots: list[SlotDefinition]) -> list[SlotDefinition]:
    updated: list[SlotDefinition] = []
    for idx, slot in enumerate(slots, start=1):
        provider_key = f"{ENV_SLOT_PREFIX}{idx}_PROVIDER"
        model_key = f"{ENV_SLOT_PREFIX}{idx}_MODEL"
        provider_override = _normalize_provider(os.environ.get(provider_key))
        model_override = os.environ.get(model_key)
        if idx == 1:
            model_override = model_override or os.environ.get(ENV_MODEL)
        updated.append(
            SlotDefinition(
                name=slot.name,
                provider=provider_override or slot.provider,
                model=(model_override or slot.model).strip(),
            )
        )
    return updated


def _resolve_slots() -> list[SlotDefinition]:
    return _apply_slot_env_overrides(_load_slot_config())


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
        return None

    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError:
        ChatAnthropic = None  # noqa: N806

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

    if selected_provider == PROVIDER_GITHUB:
        if not github_token:
            return None
        try:
            client = _build_github_client(
                ChatOpenAI,
                model=selected_model,
                token=github_token,
                timeout=selected_timeout,
                max_retries=selected_retries,
            )
            return ClientInfo(client=client, provider=PROVIDER_GITHUB, model=selected_model)
        except Exception:
            return None

    if selected_provider == PROVIDER_OPENAI:
        if not openai_token:
            return None
        try:
            client = _build_openai_client(
                ChatOpenAI,
                model=selected_model,
                token=openai_token,
                timeout=selected_timeout,
                max_retries=selected_retries,
            )
            return ClientInfo(client=client, provider=PROVIDER_OPENAI, model=selected_model)
        except Exception:
            return None

    if selected_provider == PROVIDER_ANTHROPIC:
        if not anthropic_token or not ChatAnthropic:
            return None
        try:
            client = _build_anthropic_client(
                ChatAnthropic,
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
        if slot.provider == PROVIDER_OPENAI and openai_token:
            with contextlib.suppress(Exception):
                client = _build_openai_client(
                    ChatOpenAI,
                    model=slot_model,
                    token=openai_token,
                    timeout=selected_timeout,
                    max_retries=selected_retries,
                )
                used_override = True
                return ClientInfo(client=client, provider=PROVIDER_OPENAI, model=slot_model)
        if slot.provider == PROVIDER_ANTHROPIC and anthropic_token and ChatAnthropic:
            with contextlib.suppress(Exception):
                client = _build_anthropic_client(
                    ChatAnthropic,
                    model=slot_model,
                    token=anthropic_token,
                    timeout=selected_timeout,
                    max_retries=selected_retries,
                )
                used_override = True
                return ClientInfo(client=client, provider=PROVIDER_ANTHROPIC, model=slot_model)
        if slot.provider == PROVIDER_GITHUB and github_token:
            with contextlib.suppress(Exception):
                client = _build_github_client(
                    ChatOpenAI,
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
        return []

    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError:
        ChatAnthropic = None  # noqa: N806

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

    clients: list[ClientInfo] = []

    if selected_provider:
        if selected_provider == PROVIDER_GITHUB and github_token:
            with contextlib.suppress(Exception):
                clients.append(
                    ClientInfo(
                        client=_build_github_client(
                            ChatOpenAI,
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
                                ChatOpenAI,
                                model=second_model,
                                token=github_token,
                                timeout=selected_timeout,
                                max_retries=selected_retries,
                            ),
                            provider=PROVIDER_GITHUB,
                            model=second_model,
                        )
                    )
        elif selected_provider == PROVIDER_OPENAI and openai_token:
            with contextlib.suppress(Exception):
                clients.append(
                    ClientInfo(
                        client=_build_openai_client(
                            ChatOpenAI,
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
                                ChatOpenAI,
                                model=second_model,
                                token=openai_token,
                                timeout=selected_timeout,
                                max_retries=selected_retries,
                            ),
                            provider=PROVIDER_OPENAI,
                            model=second_model,
                        )
                    )
        elif selected_provider == PROVIDER_ANTHROPIC and anthropic_token and ChatAnthropic:
            with contextlib.suppress(Exception):
                clients.append(
                    ClientInfo(
                        client=_build_anthropic_client(
                            ChatAnthropic,
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
                                ChatAnthropic,
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
                slot.provider == PROVIDER_ANTHROPIC and anthropic_token and ChatAnthropic,
                slot.provider == PROVIDER_GITHUB and github_token,
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
        if slot.provider == PROVIDER_OPENAI and openai_token:
            with contextlib.suppress(Exception):
                clients.append(
                    ClientInfo(
                        client=_build_openai_client(
                            ChatOpenAI,
                            model=slot_model,
                            token=openai_token,
                            timeout=selected_timeout,
                            max_retries=selected_retries,
                        ),
                        provider=PROVIDER_OPENAI,
                        model=slot_model,
                    )
                )
        if slot.provider == PROVIDER_ANTHROPIC and anthropic_token and ChatAnthropic:
            with contextlib.suppress(Exception):
                clients.append(
                    ClientInfo(
                        client=_build_anthropic_client(
                            ChatAnthropic,
                            model=slot_model,
                            token=anthropic_token,
                            timeout=selected_timeout,
                            max_retries=selected_retries,
                        ),
                        provider=PROVIDER_ANTHROPIC,
                        model=slot_model,
                    )
                )
        if slot.provider == PROVIDER_GITHUB and github_token:
            with contextlib.suppress(Exception):
                clients.append(
                    ClientInfo(
                        client=_build_github_client(
                            ChatOpenAI,
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
