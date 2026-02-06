"""
Shared LangChain client construction helpers.

Standardizes provider selection (GitHub Models first, then OpenAI fallback),
timeouts, retries, and environment overrides.
"""

from __future__ import annotations

import contextlib
import logging
import os
from dataclasses import dataclass

from tools.llm_provider import DEFAULT_MODEL, GITHUB_MODELS_BASE_URL

logger = logging.getLogger(__name__)

ENV_PROVIDER = "LANGCHAIN_PROVIDER"
ENV_MODEL = "LANGCHAIN_MODEL"
ENV_TIMEOUT = "LANGCHAIN_TIMEOUT"
ENV_MAX_RETRIES = "LANGCHAIN_MAX_RETRIES"

PROVIDER_OPENAI = "openai"
PROVIDER_GITHUB = "github-models"


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning("Invalid %s value %r; using default %s", name, value, default)
        return default


def _resolve_timeout(timeout: int | None) -> int:
    return _env_int(ENV_TIMEOUT, 60) if timeout is None else timeout


def _resolve_max_retries(max_retries: int | None) -> int:
    return _env_int(ENV_MAX_RETRIES, 2) if max_retries is None else max_retries


class MissingOpenAIAPIKeyError(RuntimeError):
    """Raised when OPENAI_API_KEY is required but missing."""


@dataclass(frozen=True)
class ClientInfo:
    client: object
    provider: str
    model: str

    @property
    def provider_label(self) -> str:
        return f"{self.provider}/{self.model}"


def _normalize_provider(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in {"github", "github_models", "github-models"}:
        return PROVIDER_GITHUB
    if normalized in {"openai"}:
        return PROVIDER_OPENAI
    return None


def _warn_invalid_provider(value: str) -> None:
    logger.warning("Invalid provider %r; falling back to auto-selection.", value)


def _resolve_provider(provider: str | None, *, force_openai: bool) -> str | None:
    if force_openai:
        return PROVIDER_OPENAI
    if provider:
        normalized = _normalize_provider(provider)
        if normalized:
            return normalized
        _warn_invalid_provider(provider)
        return None
    env_provider = os.environ.get(ENV_PROVIDER)
    if env_provider:
        normalized = _normalize_provider(env_provider)
        if normalized:
            return normalized
        _warn_invalid_provider(env_provider)
    return None


def _resolve_model(model: str | None) -> str:
    env_model = os.environ.get(ENV_MODEL)
    return model or env_model or DEFAULT_MODEL


def _get_env_token(name: str) -> str | None:
    value = os.environ.get(name)
    if not value:
        return None
    stripped = value.strip()
    return stripped or None


def _build_openai_client(
    chat_openai: type, *, model: str, token: str, timeout: int, max_retries: int
) -> object:
    return chat_openai(
        model=model,
        api_key=token,
        temperature=0.1,
        timeout=timeout,
        max_retries=max_retries,
    )


def _build_github_client(
    chat_openai: type, *, model: str, token: str, timeout: int, max_retries: int
) -> object:
    return chat_openai(
        model=model,
        base_url=GITHUB_MODELS_BASE_URL,
        api_key=token,
        temperature=0.1,
        timeout=timeout,
        max_retries=max_retries,
    )


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

    github_token = _get_env_token("GITHUB_TOKEN")
    openai_token = _get_env_token("OPENAI_API_KEY")

    selected_model = _resolve_model(model)
    selected_timeout = _resolve_timeout(timeout)
    selected_retries = _resolve_max_retries(max_retries)

    if force_openai and not openai_token:
        if github_token:
            try:
                logger.warning(
                    "force_openai requested but OPENAI_API_KEY is missing; falling back to GitHub Models."
                )
                client = _build_github_client(
                    ChatOpenAI,
                    model=selected_model,
                    token=github_token,
                    timeout=selected_timeout,
                    max_retries=selected_retries,
                )
                return ClientInfo(client=client, provider=PROVIDER_GITHUB, model=selected_model)
            except Exception as exc:
                raise MissingOpenAIAPIKeyError(
                    "OPENAI_API_KEY is required when force_openai=True and GitHub Models fallback "
                    "failed to initialize."
                ) from exc
        raise MissingOpenAIAPIKeyError("OPENAI_API_KEY is required when force_openai=True.")

    if not github_token and not openai_token:
        return None

    selected_provider = _resolve_provider(provider, force_openai=force_openai)

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

    # Auto-select: GitHub Models first, OpenAI fallback.
    if github_token:
        with contextlib.suppress(Exception):
            # GitHub Models failed, try OpenAI fallback
            client = _build_github_client(
                ChatOpenAI,
                model=selected_model,
                token=github_token,
                timeout=selected_timeout,
                max_retries=selected_retries,
            )
            return ClientInfo(client=client, provider=PROVIDER_GITHUB, model=selected_model)

    if openai_token:
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

    github_token = _get_env_token("GITHUB_TOKEN")
    openai_token = _get_env_token("OPENAI_API_KEY")
    if not github_token and not openai_token:
        return []

    selected_timeout = _resolve_timeout(timeout)
    selected_retries = _resolve_max_retries(max_retries)

    first_model = _resolve_model(model1)
    second_model = model2 or model1 or os.environ.get(ENV_MODEL) or DEFAULT_MODEL

    selected_provider = _resolve_provider(provider, force_openai=False)

    clients: list[ClientInfo] = []

    if selected_provider:
        if selected_provider == PROVIDER_GITHUB and github_token:
            # GitHub Models client initialization failed - skip this provider
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
                # GitHub Models client initialization failed - skip this provider
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
        if selected_provider == PROVIDER_OPENAI and openai_token:
            # OpenAI client initialization failed - skip this provider
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
                # OpenAI client initialization failed - skip this provider
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
        return clients

    if github_token:
        # GitHub Models client initialization failed - skip this provider
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

    if openai_token:
        # OpenAI client initialization failed - skip this provider
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

    return clients
