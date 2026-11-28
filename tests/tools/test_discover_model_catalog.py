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

    assert discovery._request_json("https://api.openai.com/v1/models", {"X-Test": "yes"}) == {
        "data": []
    }
    assert calls[0][0].full_url == "https://api.openai.com/v1/models"
    assert calls[0][0].headers["X-test"] == "yes"
    assert calls[0][1] == {"timeout": 30}


def test_github_models_is_retired():
    """GitHub Models was retired on 2026-10-31: no provider, no URL, no baseline."""
    assert discovery.PROVIDERS == ("openai", "anthropic")
    assert not any("github" in url for url in discovery.CATALOG_URLS)
    with pytest.raises(ValueError):
        discovery._request_json("https://models.github.ai/catalog/models", {})
    registry = json.loads(discovery.DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8"))
    assert set(registry["catalog_baselines"]) == set(discovery.PROVIDERS)


def test_catalog_cli_reports_without_promoting(monkeypatch, tmp_path, capsys):
    registry = tmp_path / "registry.json"
    original = json.dumps({"catalog_baselines": {"openai": {"model_ids": ["known"]}}})
    registry.write_text(original, encoding="utf-8")
    output = tmp_path / "report.json"
    payload = {"data": [{"id": "known"}, {"id": "new-b"}, {"id": "new-a"}]}
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(discovery, "_request_json", lambda url, headers: payload)

    assert (
        discovery.main(
            ["--provider", "openai", "--registry", str(registry), "--output", str(output)]
        )
        == 1
    )  # Catalog drift is the CLI's documented nonzero result, not a parse error.
    report = json.loads(output.read_text(encoding="utf-8"))
    assert json.loads(capsys.readouterr().out) == report
    assert report["providers"][0]["added_candidates"] == ["new-a", "new-b"]
    assert report["providers"][0]["observed_count"] == 3
    assert "do not auto-promote" in report["providers"][0]["note"]
    assert "baseline_changes" not in report
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
        provider="openai",
        models=[discovery.CatalogModel("known"), discovery.CatalogModel("new")],
        baseline=baseline,
    )
    assert report["added_candidates"] == ["new"]
    assert "do not auto-promote" in report["note"]


def test_removed_model_is_catalog_drift():
    report = discovery.catalog_diff(
        provider="anthropic",
        models=[],
        baseline={"checked_at": "2026-07-10T00:00:00Z", "model_ids": ["removed"]},
    )
    assert report["status"] == "drift"
    assert report["removed_from_catalog"] == ["removed"]


def test_parse_timestamp_rejects_bool_created_at():
    payload = {"data": [{"id": "boolean-timestamp", "created": True}]}

    assert discovery.parse_catalog("openai", payload) == [
        discovery.CatalogModel("boolean-timestamp")
    ]


@pytest.mark.parametrize("timestamp", [1e100, -1e100, float("inf"), float("-inf"), float("nan")])
def test_invalid_numeric_timestamp_does_not_abort(timestamp):
    payload = {"data": [{"id": "bad-time", "created": timestamp}, {"id": "valid", "created": 0}]}
    # `created: 0` is falsy, so the parser falls back to `created_at` (absent).
    assert discovery.parse_catalog("openai", payload) == [
        discovery.CatalogModel("bad-time"),
        discovery.CatalogModel("valid"),
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


NOW = dt.datetime(2026, 11, 30, 5, 20, tzinfo=dt.UTC)


def _observed(**catalogs: list[str]) -> dict[str, list[discovery.CatalogModel]]:
    return {
        provider: [discovery.CatalogModel(model_id) for model_id in ids]
        for provider, ids in catalogs.items()
    }


def _registry(review_by: str = "2026-08-30") -> dict:
    return {
        "review_by": review_by,
        "catalog_baselines": {
            "openai": {"checked_at": "2026-09-30T12:09:00Z", "model_ids": ["gpt-a"]},
            "anthropic": {"checked_at": "2026-09-30T00:00:00Z", "model_ids": ["claude-a"]},
        },
    }


def test_recorded_baseline_reports_only_later_additions(monkeypatch):
    """Round-3 M2: nothing wrote catalog_baselines, so every week re-reported the same
    additions (8 models since 2026-09-30, commented on the tracker weekly)."""
    registry = _registry()
    catalogs = {"openai": ["gpt-a", "gpt-b"], "anthropic": ["claude-a", "claude-b"]}
    monkeypatch.setattr(
        discovery,
        "fetch_provider",
        lambda provider: ([discovery.CatalogModel(m) for m in catalogs[provider]], None),
    )
    observed: dict = {}
    first = discovery.build_report(registry, list(discovery.PROVIDERS), observed)
    assert first["drift"] is True
    changes = discovery.record_observation(registry, observed, list(discovery.PROVIDERS), NOW)
    assert "openai: recorded 2 observed model id(s)" in changes
    assert registry["catalog_baselines"]["openai"] == {
        "checked_at": "2026-11-30T05:20:00Z",
        "model_ids": ["gpt-a", "gpt-b"],
    }

    second = discovery.build_report(registry, list(discovery.PROVIDERS))
    assert second["drift"] is False
    assert [item["status"] for item in second["providers"]] == ["current", "current"]

    catalogs["openai"].append("gpt-c")
    third = discovery.build_report(registry, list(discovery.PROVIDERS))
    assert third["providers"][0]["added_candidates"] == ["gpt-c"]


def test_recording_renews_registry_review_only_when_every_catalog_was_read():
    registry = _registry()
    changes = discovery.record_observation(
        registry, _observed(openai=["gpt-a", "gpt-b"]), ["openai"], NOW
    )
    assert changes == ["openai: recorded 2 observed model id(s)"]
    assert registry["review_by"] == "2026-08-30"  # anthropic unread: not reviewed
    assert registry["catalog_baselines"]["anthropic"]["model_ids"] == ["claude-a"]

    discovery.record_observation(
        registry, _observed(openai=["gpt-a", "gpt-b"], anthropic=["claude-a"]), ["openai"], NOW
    )
    assert registry["review_by"] == "2026-12-30"


def test_quiet_week_writes_nothing_until_the_review_is_due_soon():
    same = _observed(openai=["gpt-a"], anthropic=["claude-a"])
    registry = _registry(review_by="2026-12-20")  # 20 days left
    assert discovery.record_observation(registry, same, list(discovery.PROVIDERS), NOW) == []
    assert registry["review_by"] == "2026-12-20"

    registry = _registry(review_by="2026-12-10")  # 10 days left
    changes = discovery.record_observation(registry, same, list(discovery.PROVIDERS), NOW)
    assert changes == ["review_by: 2026-12-10 -> 2026-12-30 (every provider catalog observed)"]


def test_record_baselines_cli_writes_the_registry(monkeypatch, tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(_registry(), indent=2) + "\n", encoding="utf-8")
    catalogs = {"openai": ["gpt-a", "gpt-new"], "anthropic": ["claude-a"]}
    monkeypatch.setattr(
        discovery,
        "fetch_provider",
        lambda provider: ([discovery.CatalogModel(m) for m in catalogs[provider]], None),
    )
    output = tmp_path / "report.json"
    rc = discovery.main(["--registry", str(path), "--output", str(output), "--record-baselines"])
    assert rc == 1  # this run still reports the addition it recorded
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["providers"][0]["added_candidates"] == ["gpt-new"]
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["catalog_baselines"]["openai"]["model_ids"] == ["gpt-a", "gpt-new"]
    assert written["review_by"] > "2026-11-28"
    assert discovery.main(["--registry", str(path), "--record-baselines"]) == 0
