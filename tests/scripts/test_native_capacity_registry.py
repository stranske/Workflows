"""Exact registry facts must authorize expanded native generation, never routing."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from scripts.langchain import pr_verifier
from tools import langchain_client, llm_registry

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "config/model_registry.json"


@pytest.fixture(params=["openai", "anthropic"])
def configured_native(request, monkeypatch):
    provider = request.param
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    monkeypatch.delenv(llm_registry.ENV_MODEL_REGISTRY_CONFIG, raising=False)
    if provider == "openai":
        cls = pytest.importorskip("langchain_openai").ChatOpenAI
        model = "gpt-5.6-terra"
        builder = langchain_client._build_openai_client
    else:
        cls = pytest.importorskip("langchain_anthropic").ChatAnthropic
        model = "claude-sonnet-5-5"
        builder = langchain_client._build_anthropic_client
    client = builder(cls, model=model, token="offline-placeholder", timeout=17, max_retries=0)
    root = client.root_client if provider == "openai" else client._client
    counter = mock.Mock(return_value=SimpleNamespace(input_tokens=1000))
    metadata = mock.Mock(
        return_value=SimpleNamespace(id=model, max_input_tokens=1000000, max_tokens=128000)
    )
    resource = root.responses.input_tokens if provider == "openai" else root.messages
    monkeypatch.setattr(resource, "count" if provider == "openai" else "count_tokens", counter)
    if provider == "anthropic":
        monkeypatch.setattr(root.models, "retrieve", metadata)
    return client, provider, model, counter, metadata


def test_selected_entry_missing_blocks_generation(configured_native, tmp_path, monkeypatch):
    client, provider, model, counter, metadata = configured_native
    payload = json.loads(REGISTRY.read_text())
    payload["models"] = [
        row for row in payload["models"] if (row["provider"], row["model_id"]) != (provider, model)
    ]
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload))
    monkeypatch.setenv(llm_registry.ENV_MODEL_REGISTRY_CONFIG, str(path))
    with (
        mock.patch.object(type(client), "invoke") as generation,
        pytest.raises(pr_verifier.InputCapacityError),
    ):
        pr_verifier._invoke_llm(client, "full request", operation="registry-test")
    generation.assert_not_called()
    counter.assert_not_called()
    metadata.assert_not_called()


@pytest.mark.parametrize("operation", ["invoke", "repair"])
@pytest.mark.parametrize(
    "defect",
    [
        "missing-facts",
        "null-facts",
        "list-facts",
        "missing-context",
        "missing-output",
        "context-bool",
        "context-zero",
        "context-negative",
        "context-string",
        "context-float",
        "output-bool",
        "output-zero",
        "output-string",
        "extra-fact",
        "transport",
        "api-root",
        "count-endpoint",
        "input-source",
        "provider-wrong",
        "duplicate-model",
        "blocked",
        "wrong-provenance",
        "wrong-source",
        "wrong-date",
        "missing-file",
        "malformed-json",
        "duplicate-json-key",
        "schema",
        "models-shape",
        "entry-shape",
        "input-malformed",
        "input-missing",
    ],
)
def test_invalid_registry_denies_native_generation(
    configured_native, tmp_path, monkeypatch, defect, operation
):
    client, provider, model, counter, metadata = configured_native
    payload = json.loads(REGISTRY.read_text())
    row = next(r for r in payload["models"] if (r["provider"], r["model_id"]) == (provider, model))
    facts = row["native_capacity"]
    if defect == "missing-facts":
        row.pop("native_capacity")
    elif defect in {"null-facts", "list-facts"}:
        row["native_capacity"] = None if defect == "null-facts" else []
    elif defect in {"missing-context", "missing-output"}:
        facts.pop("max_context_tokens" if defect == "missing-context" else "max_output_tokens")
    elif defect.startswith(("context-", "output-")):
        field, bad = defect.split("-")
        facts[f"max_{field}_tokens"] = {
            "bool": True,
            "zero": 0,
            "negative": -1,
            "string": "1000000",
            "float": 1000000.0,
        }[bad]
    elif defect == "extra-fact":
        facts["sdk_type"] = "arbitrary.Type"
    elif defect in {"transport", "api-root", "count-endpoint", "input-source"}:
        key = {
            "transport": "transport",
            "api-root": "api_root",
            "count-endpoint": "count_endpoint",
            "input-source": "input_limit_source",
        }[defect]
        facts[key] = {
            "transport": "anthropic-messages" if provider == "openai" else "openai-responses",
            "api_root": "https://example.invalid",
            "count_endpoint": "https://example.invalid/count",
            "input_limit_source": "guess",
        }[key]
    elif defect == "provider-wrong":
        row["provider"] = "anthropic" if provider == "openai" else "openai"
    elif defect == "duplicate-model":
        payload["models"].append(dict(row))
    elif defect == "blocked":
        row["blocked"] = True
    elif defect == "wrong-provenance":
        facts["provenance"] = "unverified"
    elif defect == "wrong-source":
        facts["source_urls"] = ["https://example.invalid/model"]
    elif defect == "wrong-date":
        facts["as_of"] = "2026-02-30"
    elif defect == "schema":
        payload["schema_version"] = "unknown"
    elif defect == "models-shape":
        payload["models"] = {}
    elif defect == "entry-shape":
        payload["models"].append("not-an-entry")
    elif defect in {"input-malformed", "input-missing"}:
        if provider == "openai":
            if defect == "input-malformed":
                facts["max_input_tokens"] = True
            else:
                facts.pop("max_input_tokens")
        else:
            # A documented input substitute must not replace exact native metadata.
            facts["max_input_tokens"] = 1000000
    text = json.dumps(payload)
    if defect == "malformed-json":
        text = "{invalid"
    elif defect == "duplicate-json-key":
        text = text.replace(
            '"native_capacity": {', '"native_capacity": null, "native_capacity": {', 1
        )
    path = tmp_path / "registry.json"
    if defect != "missing-file":
        path.write_text(text)
    monkeypatch.setenv(llm_registry.ENV_MODEL_REGISTRY_CONFIG, str(path))
    with (
        mock.patch.object(type(client), "invoke") as generation,
        pytest.raises(pr_verifier.InputCapacityError),
    ):
        if operation == "repair":
            pr_verifier._CapacityCheckedRepairClient(client).invoke("full request")
        else:
            pr_verifier._invoke_llm(client, "full request", operation="registry-test")
    generation.assert_not_called()
    counter.assert_not_called()
    metadata.assert_not_called()


def test_registry_values_bind_actual_contract(configured_native, tmp_path, monkeypatch):
    client, provider, model, counter, metadata = configured_native
    payload = json.loads(REGISTRY.read_text())
    row = next(r for r in payload["models"] if (r["provider"], r["model_id"]) == (provider, model))
    row["native_capacity"]["max_output_tokens"] = 64000
    row["native_capacity"]["max_context_tokens"] = 900000
    if provider == "openai":
        row["native_capacity"]["max_input_tokens"] = 800000
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload))
    monkeypatch.setenv(llm_registry.ENV_MODEL_REGISTRY_CONFIG, str(path))
    prepared = pr_verifier._prepare_capacity_client(client)
    contract = pr_verifier._native_capacity_contract(prepared)
    assert contract["profile"] == {
        "max_input_tokens": 800000 if provider == "openai" else 1000000,
        "max_context_tokens": 900000,
        "max_output_tokens": 64000,
    }
    if provider == "openai":
        assert prepared.max_tokens == 64000
        assert client.max_tokens is None
    else:
        assert prepared is client and client.max_tokens == 128000
        metadata.assert_called_once_with(model)
    # Preserve explicit output and still reject it against configured ceilings.
    client.max_tokens = 64001
    with (
        mock.patch.object(type(client), "invoke") as generation,
        pytest.raises(pr_verifier.InputCapacityError),
    ):
        pr_verifier._invoke_llm(client, "full request", operation="registry-test")
    generation.assert_not_called()
    counter.assert_not_called()


def test_standard_does_not_read_capacity_registry(configured_native, tmp_path, monkeypatch):
    client, _, _, counter, metadata = configured_native
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "standard")
    monkeypatch.setenv(llm_registry.ENV_MODEL_REGISTRY_CONFIG, str(tmp_path / "absent.json"))
    before = json.dumps(client._get_request_payload("full request"), sort_keys=True)
    with mock.patch.object(
        type(client), "invoke", return_value=SimpleNamespace(content="PASS")
    ) as gen:
        pr_verifier._invoke_llm(client, "full request", operation="registry-test")
    assert gen.call_count == 1
    assert json.dumps(client._get_request_payload("full request"), sort_keys=True) == before
    counter.assert_not_called()
    metadata.assert_not_called()


@pytest.mark.parametrize(
    "provider,model",
    [
        ("openai", "gpt-5.6-terra-future"),
        ("anthropic", "claude-sonnet-5-5-future"),
        ("anthropic", "gpt-5.6-terra"),
        ("openai", "claude-sonnet-5-5"),
        ("openai", "gpt-6-astra"),
        ("github-models", "openai/gpt-5"),
        ("OpenAI", "gpt-5.6-terra"),
        ("openai", " gpt-5.6-terra"),
    ],
)
def test_exact_registry_lookup_rejects_unsupported(provider, model, monkeypatch):
    monkeypatch.delenv(llm_registry.ENV_MODEL_REGISTRY_CONFIG, raising=False)
    with pytest.raises(ValueError):
        llm_registry.native_capacity_facts_for(provider, model)


def test_native_facts_and_helper_are_managed_with_exact_template_parity():
    manifest = (ROOT / ".github/sync-manifest.yml").read_text()
    for name in (
        "config/model_registry.json",
        "tools/llm_registry.py",
        "scripts/langchain/pr_verifier.py",
    ):
        assert f"- source: {name}" in manifest
        assert (ROOT / name).read_bytes() == (ROOT / "templates/consumer-repo" / name).read_bytes()
    registry = json.loads(REGISTRY.read_text())
    supported = {
        (r["provider"], r["model_id"]) for r in registry["models"] if "native_capacity" in r
    }
    assert supported == {("openai", "gpt-5.6-terra"), ("anthropic", "claude-sonnet-5-5")}
    source = (ROOT / "scripts/langchain/pr_verifier.py").read_text()
    native_block = source[
        source.index("def _prepare_capacity_client") : source.index("def _preflight_input_capacity")
    ]
    for literal in ("gpt-5.6-terra", "claude-sonnet-5-5", "922000", "1050000", "1000000", "128000"):
        assert literal not in native_block


@pytest.mark.parametrize("field", ["max_input_tokens", "max_context_tokens", "max_output_tokens"])
@pytest.mark.parametrize("value", [None, True, False, 0, -1, "128000", 128000.0, [], {}])
def test_each_documented_limit_requires_independent_positive_integer(
    tmp_path, monkeypatch, field, value
):
    payload = json.loads(REGISTRY.read_text())
    row = next(r for r in payload["models"] if r["model_id"] == "gpt-5.6-terra")
    row["native_capacity"][field] = value
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload))
    monkeypatch.setenv(llm_registry.ENV_MODEL_REGISTRY_CONFIG, str(path))
    with pytest.raises(ValueError, match="positive integers"):
        llm_registry.native_capacity_facts_for("openai", "gpt-5.6-terra")


@pytest.mark.parametrize(
    "raw", ["null", "[]", "NaN", '{"schema_version":"2.0.0","models":[],"x":Infinity}']
)
def test_strict_registry_json_rejects_non_objects_and_non_finite(tmp_path, monkeypatch, raw):
    path = tmp_path / "registry.json"
    path.write_text(raw)
    monkeypatch.setenv(llm_registry.ENV_MODEL_REGISTRY_CONFIG, str(path))
    with pytest.raises(ValueError):
        llm_registry.native_capacity_facts_for("openai", "gpt-5.6-terra")


@pytest.mark.parametrize("provider", ["OpenAI", "claude", "github", "other"])
def test_noncanonical_provider_row_cannot_hide_ambiguous_identity(tmp_path, monkeypatch, provider):
    payload = json.loads(REGISTRY.read_text())
    row = dict(next(r for r in payload["models"] if r["model_id"] == "gpt-5.6-terra"))
    row["provider"] = provider
    payload["models"].append(row)
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload))
    monkeypatch.setenv(llm_registry.ENV_MODEL_REGISTRY_CONFIG, str(path))
    with pytest.raises(ValueError, match="noncanonical"):
        llm_registry.native_capacity_facts_for("openai", "gpt-5.6-terra")
