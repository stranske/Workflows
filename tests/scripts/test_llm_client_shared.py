"""Tests for the shared ``scripts/langchain/_llm_client`` module (issue #2343).

The ``get_llm_client`` / ``get_llm_clients`` helpers replace the ``_get_llm_client``
bodies that were copy-pasted across the langchain agent scripts. These tests stub
``tools.langchain_client`` so they run without the optional langchain deps or any
real credentials.
"""

from __future__ import annotations

import functools
import sys
from types import ModuleType, SimpleNamespace

import pytest
from scripts.langchain import _llm_client


def _install_fake_langchain_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    info: object | None = None,
    clients: list[object] | None = None,
) -> ModuleType:
    """Install a fake ``tools.langchain_client`` module and record calls."""
    fake = ModuleType("tools.langchain_client")
    fake.calls = []  # type: ignore[attr-defined]
    fake.clients_calls = []  # type: ignore[attr-defined]

    def build_chat_client(*, model=None, provider=None, force_openai=False):
        fake.calls.append(  # type: ignore[attr-defined]
            {"model": model, "provider": provider, "force_openai": force_openai}
        )
        return info

    def build_chat_clients(*, model1=None, model2=None):
        fake.clients_calls.append({"model1": model1, "model2": model2})  # type: ignore[attr-defined]
        return clients or []

    fake.build_chat_client = build_chat_client  # type: ignore[attr-defined]
    fake.build_chat_clients = build_chat_clients  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tools.langchain_client", fake)
    return fake


def _fake_info() -> SimpleNamespace:
    return SimpleNamespace(
        client=object(),
        provider="openai",
        model="gpt-5.4",
        provider_label="openai:gpt-5.4",
    )


def test_get_llm_client_returns_configured_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Named test (acceptance + deliberate-break gate): a configured client is returned.

    If ``get_llm_client`` is made to return ``None`` this test fails, proving the
    deliberate-break gate from issue #2343.
    """
    info = _fake_info()
    _install_fake_langchain_client(monkeypatch, info=info)

    result = _llm_client.get_llm_client()

    assert result is not None
    client, label = result
    assert client is info.client
    assert label == "openai"


def test_get_llm_client_passes_through_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    info = _fake_info()
    fake = _install_fake_langchain_client(monkeypatch, info=info)

    _llm_client.get_llm_client(force_openai=True, model="o3-mini", provider="openai")

    assert fake.calls == [{"model": "o3-mini", "provider": "openai", "force_openai": True}]


@pytest.mark.parametrize(
    ("return_field", "expected"),
    [
        ("provider", "openai"),
        ("model", "gpt-5.4"),
        ("provider_label", "openai:gpt-5.4"),
    ],
)
def test_get_llm_client_return_field_selects_label(
    monkeypatch: pytest.MonkeyPatch, return_field: str, expected: str
) -> None:
    info = _fake_info()
    _install_fake_langchain_client(monkeypatch, info=info)

    result = _llm_client.get_llm_client(return_field=return_field)

    assert result is not None
    assert result[1] == expected


def test_get_llm_client_rejects_unknown_return_field(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_langchain_client(monkeypatch, info=_fake_info())

    with pytest.raises(ValueError, match="return_field must be one of"):
        _llm_client.get_llm_client(return_field="provider_lable")


def test_get_llm_client_returns_none_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_langchain_client(monkeypatch, info=None)

    assert _llm_client.get_llm_client() is None


def test_get_llm_client_returns_none_without_langchain(monkeypatch: pytest.MonkeyPatch) -> None:
    # Setting the module to None makes ``import tools.langchain_client`` raise ImportError.
    monkeypatch.setitem(sys.modules, "tools.langchain_client", None)

    assert _llm_client.get_llm_client() is None
    assert _llm_client.build_client() is None


def test_get_llm_clients_returns_tuples(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = [
        SimpleNamespace(client=object(), provider="openai", model="m1"),
        SimpleNamespace(client=object(), provider="github-models", model="m2"),
    ]
    _install_fake_langchain_client(monkeypatch, clients=entries)

    result = _llm_client.get_llm_clients(model1="m1", model2="m2")

    assert [(c, p, m) for (c, p, m) in result] == [
        (entries[0].client, "openai", "m1"),
        (entries[1].client, "github-models", "m2"),
    ]


def test_get_llm_clients_returns_empty_without_langchain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "tools.langchain_client", None)

    assert _llm_client.get_llm_clients() == []


def test_representative_scripts_import_shared_helper() -> None:
    """Each script wires its client construction to the shared module."""
    from scripts.langchain import context_extractor, pr_verifier

    # Simple scripts bind the shared helper under the historical mockable name.
    assert context_extractor._get_llm_client is _llm_client.get_llm_client

    # pr_verifier returns the provider_label and reuses the shared dual builder.
    assert isinstance(pr_verifier._get_llm_client, functools.partial)
    assert pr_verifier._get_llm_client.func is _llm_client.get_llm_client
    assert pr_verifier._get_llm_client.keywords == {"return_field": "provider_label"}
    assert pr_verifier._get_llm_clients is _llm_client.get_llm_clients
