#!/usr/bin/env python3
"""Shared LangChain chat-client construction for the agent scripts.

The ``_get_llm_client`` helper used to be copy-pasted across the langchain
agent scripts (``context_extractor``, ``capability_check``, ``issue_optimizer``,
``topic_splitter``, ``issue_formatter``, ``task_decomposer``,
``followup_issue_generator``, ``pr_verifier``, ``task_validator``). The bodies
were all variations on the same construction: import
``tools.langchain_client.build_chat_client``, return ``None`` if the import or
credential lookup failed, otherwise return ``(client, <label>)``.

This module hosts that construction once. Per-script differences (forcing
OpenAI, an explicit model/provider override, and which ``ClientInfo`` attribute
is returned as the label) are expressed as parameters rather than divergent
copies. Scripts whose provider selection is genuinely script-specific
(``task_decomposer``'s env-based resolution, ``followup_issue_generator``'s
reasoning-model selection and diagnostics) keep that logic locally and delegate
only the import-guarded construction here.
"""

from __future__ import annotations

from typing import Any

_RETURN_FIELDS = frozenset({"provider", "model", "provider_label"})


def get_llm_client(
    *,
    force_openai: bool = False,
    model: str | None = None,
    provider: str | None = None,
    return_field: str = "provider",
) -> tuple[Any, str] | None:
    """Build a single LangChain chat client.

    Wraps :func:`tools.langchain_client.build_chat_client`, preserving the exact
    behavior of the former per-script ``_get_llm_client`` helpers.

    Args:
        force_openai: Force the OpenAI provider (used for retry after a GitHub
            Models 401). Equivalent to ``provider="openai"``.
        model: Optional model-name override passed through to ``build_chat_client``.
        provider: Optional provider override (``"openai"``/``"github-models"``/...).
        return_field: Which ``ClientInfo`` attribute to return as the second
            tuple element — ``"provider"`` (default), ``"model"``, or
            ``"provider_label"``.

    Returns:
        ``(client, label)`` or ``None`` when ``langchain`` deps are missing or no
        credentials are available.
    """
    if return_field not in _RETURN_FIELDS:
        allowed = ", ".join(sorted(_RETURN_FIELDS))
        raise ValueError(f"return_field must be one of: {allowed}")

    info = build_client(model=model, provider=provider, force_openai=force_openai)
    if not info:
        return None
    return info.client, getattr(info, return_field)


def build_client(
    *,
    model: str | None = None,
    provider: str | None = None,
    force_openai: bool = False,
) -> Any | None:
    """Return the raw ``ClientInfo`` (or ``None``) from ``build_chat_client``.

    Exposes the import-guarded construction for callers that need more than the
    ``(client, label)`` shape — e.g. ``followup_issue_generator`` which logs both
    provider and model and returns the model as its label.
    """
    try:
        from tools.langchain_client import build_chat_client
    except ImportError:
        return None
    return build_chat_client(model=model, provider=provider, force_openai=force_openai)


def get_llm_clients(
    model1: str | None = None,
    model2: str | None = None,
) -> list[tuple[Any, str, str]]:
    """Build the dual-client comparison list used by ``pr_verifier``.

    Mirrors the former ``pr_verifier._get_llm_clients`` exactly: returns a list
    of ``(client, provider, model)`` tuples, or ``[]`` when deps are missing.
    """
    try:
        from tools.langchain_client import build_chat_clients
    except ImportError:
        return []
    clients = build_chat_clients(model1=model1, model2=model2)
    return [(entry.client, entry.provider, entry.model) for entry in clients]
