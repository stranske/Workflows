from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from tools import discover_model_catalog as discovery


def test_request_json_uses_http_only_client(monkeypatch):
    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"data": []},
    )
    calls = []
    monkeypatch.setattr(
        discovery.requests,
        "get",
        lambda url, **kwargs: calls.append((url, kwargs)) or response,
    )

    assert discovery._request_json("https://provider.example/models", {"X-Test": "yes"}) == {
        "data": []
    }
    assert calls == [
        (
            "https://provider.example/models",
            {"headers": {"X-Test": "yes"}, "timeout": 30},
        )
    ]


def test_github_catalog_parser_filters_non_chat_entries():
    payload = [
        {"id": "openai/gpt-current", "publisher": "OpenAI", "capabilities": ["streaming"]},
        {"id": "openai/embedding", "publisher": "OpenAI", "capabilities": []},
        {"id": "other/model", "publisher": "Other", "capabilities": ["streaming"]},
    ]
    assert discovery.parse_catalog("github-models", payload) == [
        discovery.CatalogModel("openai/gpt-current")
    ]


def test_credentialed_catalog_ignores_historical_unknown_models():
    baseline = {
        "checked_at": "2026-07-10T00:00:00Z",
        "model_ids": ["current"],
    }
    models = [
        discovery.CatalogModel("current", dt.datetime(2026, 7, 1, tzinfo=dt.UTC)),
        discovery.CatalogModel("historical", dt.datetime(2025, 1, 1, tzinfo=dt.UTC)),
        discovery.CatalogModel("new", dt.datetime(2026, 7, 11, tzinfo=dt.UTC)),
    ]
    report = discovery.catalog_diff(provider="openai", models=models, baseline=baseline)
    assert report["added_candidates"] == ["new"]
    assert report["status"] == "drift"


def test_new_model_is_candidate_not_selection():
    baseline = {"checked_at": "2026-07-10T00:00:00Z", "model_ids": ["known"]}
    report = discovery.catalog_diff(
        provider="github-models",
        models=[discovery.CatalogModel("known"), discovery.CatalogModel("new")],
        baseline=baseline,
    )
    assert report["added_candidates"] == ["new"]
    assert "do not auto-promote" in report["note"]


def test_removed_model_is_catalog_drift():
    report = discovery.catalog_diff(
        provider="github-models",
        models=[],
        baseline={"checked_at": "2026-07-10T00:00:00Z", "model_ids": ["removed"]},
    )
    assert report["status"] == "drift"
    assert report["removed_from_catalog"] == ["removed"]
