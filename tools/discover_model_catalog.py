#!/usr/bin/env python3
"""Discover provider catalog drift without changing model selections.

GitHub Models is public. OpenAI and Anthropic discovery run only when their API
keys are available. Newly observed models are review candidates, not evidence
that they are better than an approved selection.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY_PATH = _REPO_ROOT / "config" / "model_registry.json"
PROVIDERS = ("openai", "anthropic", "github-models")
CATALOG_URLS = frozenset(
    {
        "https://models.github.ai/catalog/models",
        "https://api.openai.com/v1/models",
        "https://api.anthropic.com/v1/models?limit=1000",
    }
)


@dataclass(frozen=True)
class CatalogModel:
    model_id: str
    created_at: dt.datetime | None = None


def _request_json(url: str, headers: dict[str, str]) -> Any:
    if url not in CATALOG_URLS:
        raise ValueError(f"unsupported catalog URL: {url}")
    request = Request(url, headers=headers)
    with urlopen(request, timeout=30) as response:  # noqa: S310 - validated static catalog URL
        return json.load(response)


def _parse_timestamp(value: object) -> dt.datetime | None:
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value, tz=dt.UTC)
    if isinstance(value, str) and value.strip():
        normalized = value.strip().replace("Z", "+00:00")
        try:
            parsed = dt.datetime.fromisoformat(normalized)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.UTC)
    return None


def parse_catalog(provider: str, payload: Any) -> list[CatalogModel]:
    if provider == "github-models":
        if not isinstance(payload, list):
            raise ValueError("GitHub Models catalog must be a list")
        return [
            CatalogModel(str(item["id"]), _parse_timestamp(item.get("created_at")))
            for item in payload
            if isinstance(item, dict)
            and item.get("id")
            and item.get("publisher") == "OpenAI"
            and item.get("capabilities")
        ]
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError(f"{provider} catalog must contain a data list")
    return [
        CatalogModel(
            str(item["id"]),
            _parse_timestamp(item.get("created") or item.get("created_at")),
        )
        for item in payload["data"]
        if isinstance(item, dict) and item.get("id")
    ]


def catalog_diff(
    *,
    provider: str,
    models: list[CatalogModel],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    known = {str(item) for item in baseline.get("model_ids", [])}
    checked_at = _parse_timestamp(baseline.get("checked_at"))
    current = {model.model_id for model in models}
    additions = []
    for model in models:
        if model.model_id in known:
            continue
        # Credentialed provider APIs contain long-lived historical catalogs.
        # Only post-baseline additions are actionable. A missing timestamp is
        # retained because silently ignoring it would hide real drift.
        if (
            provider != "github-models"
            and checked_at
            and model.created_at
            and model.created_at <= checked_at
        ):
            continue
        additions.append(model.model_id)
    removed = sorted(known - current)
    return {
        "provider": provider,
        "status": "drift" if additions or removed else "current",
        "added_candidates": sorted(set(additions)),
        "removed_from_catalog": removed,
        "observed_count": len(current),
        "note": "Catalog changes require benchmark review; they do not auto-promote models.",
    }


def fetch_provider(provider: str) -> tuple[list[CatalogModel] | None, str | None]:
    try:
        if provider == "github-models":
            payload = _request_json("https://models.github.ai/catalog/models", {})
        elif provider == "openai":
            token = os.environ.get("OPENAI_API_KEY")
            if not token:
                return None, "OPENAI_API_KEY unavailable"
            payload = _request_json(
                "https://api.openai.com/v1/models",
                {"Authorization": f"Bearer {token}"},
            )
        elif provider == "anthropic":
            token = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_STRANSKE")
            if not token:
                return None, "ANTHROPIC_API_KEY/CLAUDE_API_STRANSKE unavailable"
            payload = _request_json(
                "https://api.anthropic.com/v1/models?limit=1000",
                {"x-api-key": token, "anthropic-version": "2023-06-01"},
            )
        else:  # pragma: no cover - argparse constrains values
            raise ValueError(f"unsupported provider: {provider}")
        return parse_catalog(provider, payload), None
    except (OSError, URLError, ValueError) as exc:
        return None, str(exc)


def build_report(registry: dict[str, Any], providers: list[str]) -> dict[str, Any]:
    baselines = registry.get("catalog_baselines", {})
    results: list[dict[str, Any]] = []
    for provider in providers:
        baseline = baselines.get(provider) if isinstance(baselines, dict) else None
        if not isinstance(baseline, dict):
            results.append({"provider": provider, "status": "error", "error": "missing baseline"})
            continue
        models, error = fetch_provider(provider)
        if models is None:
            results.append({"provider": provider, "status": "skipped", "reason": error})
            continue
        results.append(catalog_diff(provider=provider, models=models, baseline=baseline))
    return {
        "schema": "workflows-model-catalog-discovery/v1",
        "generated_at": dt.datetime.now(tz=dt.UTC).isoformat(),
        "drift": any(item.get("status") == "drift" for item in results),
        "providers": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover model catalog drift.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--provider", action="append", choices=PROVIDERS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
        if not isinstance(registry, dict):
            raise ValueError("registry must be a JSON object")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    report = build_report(registry, args.provider or list(PROVIDERS))
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 1 if report["drift"] else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
