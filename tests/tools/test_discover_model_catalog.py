from __future__ import annotations

import datetime as dt
import json
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from tools import discover_model_catalog as discovery


def test_request_json_uses_http_only_client(monkeypatch):
    response = SimpleNamespace(read=lambda: b'{"data": []}')
    calls = []
    monkeypatch.setattr(
        discovery,
        "urlopen",
        lambda request, **kwargs: calls.append((request, kwargs)) or nullcontext(response),
    )

    assert discovery._request_json(
        "https://models.github.ai/catalog/models", {"X-Test": "yes"}
    ) == {"data": []}
    assert calls[0][0].full_url == "https://models.github.ai/catalog/models"
    assert calls[0][0].headers["X-test"] == "yes"
    assert calls[0][1] == {"timeout": 30}


def test_github_catalog_parser_requires_id_and_capabilities():
    payload = [
        {"id": "openai/gpt-current", "publisher": "OpenAI", "capabilities": ["streaming"]},
        {"id": "openai/embedding", "publisher": "OpenAI", "capabilities": []},
        {"id": "other/model", "publisher": "Other", "capabilities": ["streaming"]},
        {"id": "missing-capabilities", "publisher": "Meta"},
        {"id": "", "publisher": "Meta", "capabilities": ["streaming"]},
        {"publisher": "Meta", "capabilities": ["streaming"]},
        None,
        "invalid-entry",
    ]
    assert discovery.parse_catalog("github-models", payload) == [
        discovery.CatalogModel("openai/gpt-current"),
        discovery.CatalogModel("other/model"),
    ]


@pytest.mark.parametrize("publisher", ["OpenAI", "Meta", "Mistral AI", "Microsoft", "Cohere"])
def test_github_catalog_accepts_all_publishers(publisher):
    payload = [
        {
            "id": "publisher/model",
            "publisher": publisher,
            "capabilities": ["streaming"],
            "created_at": "2026-09-01T12:00:00Z",
        }
    ]
    assert discovery.parse_catalog("github-models", payload) == [
        discovery.CatalogModel("publisher/model", dt.datetime(2026, 9, 1, 12, tzinfo=dt.UTC))
    ]


def test_github_catalog_cli_reports_publishers_without_promoting(monkeypatch, tmp_path, capsys):
    registry = tmp_path / "registry.json"
    original = json.dumps({"catalog_baselines": {"github-models": {"model_ids": ["openai/known"]}}})
    registry.write_text(original, encoding="utf-8")
    output = tmp_path / "report.json"
    payload = [
        {"id": "openai/known", "publisher": "OpenAI", "capabilities": ["streaming"]},
        {"id": "meta/new", "publisher": "Meta", "capabilities": ["streaming"]},
        {"id": "cohere/new", "publisher": "Cohere", "capabilities": ["streaming"]},
    ]
    monkeypatch.setattr(discovery, "_request_json", lambda url, headers: payload)

    assert (
        discovery.main(
            ["--provider", "github-models", "--registry", str(registry), "--output", str(output)]
        )
        == 1
    )  # Catalog drift is the CLI's documented nonzero result, not a parse error.
    report = json.loads(output.read_text(encoding="utf-8"))
    assert json.loads(capsys.readouterr().out) == report
    assert report["providers"][0]["added_candidates"] == ["cohere/new", "meta/new"]
    assert report["providers"][0]["observed_count"] == 3
    assert "do not auto-promote" in report["providers"][0]["note"]
    assert registry.read_text(encoding="utf-8") == original


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


def test_parse_timestamp_rejects_bool_created_at():
    payload = [
        {
            "id": "boolean-timestamp",
            "capabilities": ["streaming"],
            "created_at": True,
        }
    ]

    assert discovery.parse_catalog("github-models", payload) == [
        discovery.CatalogModel("boolean-timestamp")
    ]


@pytest.mark.parametrize("timestamp", [1e100, -1e100, float("inf"), float("-inf"), float("nan")])
def test_github_catalog_invalid_numeric_timestamp_does_not_abort(timestamp):
    payload = [
        {"id": "bad-time", "capabilities": ["streaming"], "created_at": timestamp},
        {"id": "valid", "capabilities": ["streaming"], "created_at": 0},
    ]
    assert discovery.parse_catalog("github-models", payload) == [
        discovery.CatalogModel("bad-time"),
        discovery.CatalogModel("valid", dt.datetime(1970, 1, 1, tzinfo=dt.UTC)),
    ]


@pytest.mark.parametrize("error", [OSError, OverflowError, ValueError])
def test_numeric_timestamp_platform_errors_are_ignored(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error("unsupported timestamp")

    monkeypatch.setattr(
        discovery,
        "dt",
        SimpleNamespace(
            datetime=SimpleNamespace(fromtimestamp=fail),
            UTC=dt.UTC,
        ),
    )
    assert discovery._parse_timestamp(123) is None
