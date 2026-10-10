"""Real configured LangChain adapters; only native HTTP results are simulated."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from scripts.langchain import pr_verifier
from tools import langchain_client


@pytest.fixture(params=["openai", "anthropic"])
def native(request, monkeypatch):
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    provider = request.param
    selections = json.loads(Path("config/model_registry.json").read_text())["selections"]
    model = next(
        row["model_id"]
        for row in selections
        if row["profile"] == "verifier-balanced" and row["provider"] == provider
    )
    if provider == "openai":
        cls = pytest.importorskip("langchain_openai").ChatOpenAI
        builder = langchain_client._build_openai_client
    else:
        cls = pytest.importorskip("langchain_anthropic").ChatAnthropic
        builder = langchain_client._build_anthropic_client
    client = builder(cls, model=model, token="offline-placeholder", timeout=17, max_retries=0)
    root = client.root_client if provider == "openai" else client._client
    counter = mock.Mock(return_value=SimpleNamespace(input_tokens=1000))
    metadata = mock.Mock(
        return_value=SimpleNamespace(id=model, max_input_tokens=1_000_000, max_tokens=128000)
    )
    if provider == "openai":
        monkeypatch.setattr(root.responses.input_tokens, "count", counter)
    else:
        monkeypatch.setattr(root.messages, "count_tokens", counter)
        monkeypatch.setattr(root.models, "retrieve", metadata)
    return client, provider, model, counter, metadata


@pytest.mark.parametrize("operation", ["evaluate", "compare", "repair"])
def test_configured_native_expanded_reaches_count_and_generation(native, operation, monkeypatch):
    client, provider, model, counter, metadata = native
    original = client._get_request_payload("full request")
    monkeypatch.setattr(pr_verifier, "_get_llm_client", lambda **kwargs: (client, provider))
    seen = []

    def generate(prepared, prompt, **kwargs):
        seen.append((prepared, prepared._get_request_payload(prompt)))
        return SimpleNamespace(content='{"verdict":"PASS"}')

    with mock.patch.object(type(client), "invoke", autospec=True, side_effect=generate):
        if operation == "repair":
            result = pr_verifier._parse_llm_response("invalid JSON", provider, client=client)
        elif operation == "compare":
            result = pr_verifier.ComparisonRunner("context", None, "full request", []).run_single(
                client, provider, model
            )
        else:
            result = pr_verifier.evaluate_pr("context", provider=provider)
    assert result.used_llm, result.error
    counter.assert_called_once()
    prepared, payload = seen[0]
    assert payload["model"] == model
    assert counter.call_args.kwargs["model"] == model
    key = "input" if provider == "openai" else "messages"
    assert counter.call_args.kwargs[key] == payload[key]
    assert payload["max_output_tokens" if provider == "openai" else "max_tokens"] == 128000
    assert client._get_request_payload("full request") == original
    if provider == "openai":
        assert prepared is not client
        assert prepared.root_client is client.root_client
        assert prepared.openai_api_key == client.openai_api_key
        assert prepared.request_timeout == client.request_timeout == 17
        assert prepared.max_retries == client.max_retries == 0
        assert client.use_responses_api is None
    else:
        metadata.assert_called_once_with(model)
        assert prepared._client is client._client


@pytest.mark.parametrize("profile", [None, "standard"])
@pytest.mark.parametrize("operation", ["invoke", "repair"])
def test_standard_keeps_client_and_request_bytes(native, profile, operation, monkeypatch):
    client, _, _, counter, metadata = native
    if profile is None:
        monkeypatch.delenv("VERIFIER_EVIDENCE_PROFILE")
    else:
        monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", profile)
    before = json.dumps(client._get_request_payload("full request"), sort_keys=True)
    seen = []

    def invoke(actual, prompt, **kwargs):
        seen.append(actual)
        assert json.dumps(actual._get_request_payload(prompt), sort_keys=True) == before

    with mock.patch.object(type(client), "invoke", autospec=True, side_effect=invoke):
        if operation == "repair":
            pr_verifier._CapacityCheckedRepairClient(client).invoke("full request")
        else:
            pr_verifier._invoke_llm(client, "full request", operation="test")
    assert seen == [client]
    counter.assert_not_called()
    metadata.assert_not_called()


@pytest.mark.parametrize("operation", ["invoke", "repair"])
@pytest.mark.parametrize(
    "defect",
    [
        "future-model",
        "wrong-provider-model",
        "payload-model",
        "profile-model",
        "profile-provider",
        "custom-endpoint",
        "counter-root",
        "query-fields",
        "missing-counter",
        "count-bool",
        "count-zero",
        "count-negative",
        "count-string",
        "count-unavailable",
        "overflow",
        "output-overflow",
        "output-bool",
        "output-zero",
        "unsupported-fields",
        "wrong-provider-payload",
        "stateful",
        "truncation",
        "changed-payload",
    ],
)
def test_native_unknowns_block_generation(native, operation, defect, monkeypatch):
    client, provider, model, counter, metadata = native
    model_attr = "model_name" if provider == "openai" else "model"
    root = client.root_client if provider == "openai" else client._client
    resource = root.responses.input_tokens if provider == "openai" else root.messages
    counter_attr = "count" if provider == "openai" else "count_tokens"
    if defect in {"future-model", "wrong-provider-model"}:
        other = "claude-sonnet-5-5" if provider == "openai" else "gpt-5.6-terra"
        setattr(client, model_attr, model + "-future" if defect == "future-model" else other)
    elif defect == "profile-model":
        client.profile = {"model": "unrelated"}
    elif defect == "profile-provider":
        client.profile = {"provider": "github-models"}
    elif defect == "custom-endpoint":
        root.base_url = "https://example.invalid/v1"
    elif defect == "counter-root":
        monkeypatch.setattr(resource, "_client", object())
    elif defect == "query-fields":
        root._custom_query = {"model": "unrelated"}
    elif defect == "missing-counter":
        monkeypatch.setattr(resource, counter_attr, None)
    elif defect.startswith("count-"):
        value = {"count-bool": True, "count-zero": 0, "count-negative": -1, "count-string": "1"}
        if defect == "count-unavailable":
            counter.side_effect = RuntimeError("401 native count unavailable")
        else:
            counter.return_value.input_tokens = value[defect]
    elif defect == "overflow":
        counter.return_value.input_tokens = 1_000_000
    elif defect.startswith("output-"):
        client.max_tokens = {"output-overflow": 128001, "output-bool": True, "output-zero": 0}[
            defect
        ]
    else:
        original = type(client)._get_request_payload
        calls = []

        def payload(actual, prompt, **kwargs):
            result = original(actual, prompt, **kwargs)
            if defect == "payload-model":
                result["model"] = "unrelated"
            elif defect == "unsupported-fields":
                result["unaccounted_extension"] = {"input": "hidden"}
            elif defect == "wrong-provider-payload":
                result["messages" if provider == "openai" else "input"] = "foreign transport"
            elif defect == "stateful":
                result["previous_response_id"] = "prior-state"
            elif defect == "truncation":
                result["truncation"] = "auto"
            elif defect == "changed-payload" and calls:
                result["input" if provider == "openai" else "messages"] = "different input"
            calls.append(True)
            return result

        monkeypatch.setattr(type(client), "_get_request_payload", payload)
    with mock.patch.object(type(client), "invoke") as invoke:
        with pytest.raises(pr_verifier.InputCapacityError):
            if operation == "repair":
                pr_verifier._CapacityCheckedRepairClient(client).invoke("entire evidence")
            else:
                pr_verifier._invoke_llm(client, "entire evidence", operation="test")
        invoke.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "claude-sonnet-5-5-alias"),
        ("max_input_tokens", None),
        ("max_input_tokens", True),
        ("max_input_tokens", 0),
        ("max_tokens", "128000"),
        ("max_tokens", 127999),
    ],
)
def test_anthropic_metadata_unavailable_or_invalid_blocks(native, field, value):
    client, provider, _, counter, metadata = native
    if provider != "anthropic":
        pytest.skip("Anthropic Models API contract")
    setattr(metadata.return_value, field, value)
    with mock.patch.object(type(client), "invoke") as invoke:
        with pytest.raises(pr_verifier.InputCapacityError):
            pr_verifier._invoke_llm(client, "entire evidence", operation="test")
        invoke.assert_not_called()
        counter.assert_not_called()


def test_complete_native_count_shape_and_receipt(native, monkeypatch, tmp_path):
    client, provider, model, counter, metadata = native
    if provider == "openai":
        client.model_kwargs = {
            "instructions": "system instructions",
            "tools": [{"type": "function", "name": "f", "parameters": {"type": "object"}}],
            "text": {"format": {"type": "json_object"}},
        }
        client.reasoning = {"effort": "high"}
    else:
        client.model_kwargs = {
            "system": "system instructions",
            "tools": [{"name": "f", "input_schema": {"type": "object"}}],
        }
        client.output_config = {"format": {"type": "json_schema", "schema": {"type": "object"}}}
        client.thinking = {"type": "adaptive"}
    report = tmp_path / "capacity.jsonl"
    monkeypatch.setenv("VERIFIER_CAPACITY_REPORT_PATH", str(report))
    prepared = pr_verifier._prepare_capacity_client(client)
    payload = prepared._get_request_payload("all evidence")
    receipt = pr_verifier._preflight_input_capacity(prepared, "all evidence")
    counted = counter.call_args.kwargs
    for key in (
        {"input", "instructions", "tools", "text", "reasoning"}
        if provider == "openai"
        else {"messages", "system", "tools", "output_config", "thinking"}
    ):
        assert counted[key] == payload[key]
    assert receipt["status"] == "PASS"
    assert receipt["output_reserve"] == 128000
    assert receipt["provider"] == provider and receipt["model"] == model
    assert receipt["endpoint"].startswith(f"https://api.{provider}.com/")
    assert "exact-model" in receipt["provenance"]
    assert len(receipt["request_sha256"]) == 64
    assert json.loads(report.read_text()) == receipt


def test_native_count_failure_never_resolves_an_alternate_judge(native, monkeypatch):
    client, provider, _, counter, _ = native
    counter.side_effect = RuntimeError("401 native count unavailable")
    resolver = mock.Mock(return_value=(client, provider))
    monkeypatch.setattr(pr_verifier, "_get_llm_client", resolver)
    with mock.patch.object(type(client), "invoke") as invoke:
        result = pr_verifier.evaluate_pr("context")
        assert result.verdict == "CONCERNS"
        assert not result.used_llm
        resolver.assert_called_once()
        invoke.assert_not_called()


def test_schema_repair_unknown_generation_kwargs_block(native):
    client, _, _, counter, _ = native
    with mock.patch.object(type(client), "invoke") as invoke:
        with pytest.raises(pr_verifier.InputCapacityError, match="kwargs"):
            pr_verifier._CapacityCheckedRepairClient(client).invoke("full repair", tools=[])
        invoke.assert_not_called()
        counter.assert_not_called()


def test_expanded_generation_transport_failure_never_switches_provider(native, monkeypatch):
    client, provider, _, counter, _ = native
    resolver = mock.Mock(return_value=(client, provider))
    monkeypatch.setattr(pr_verifier, "_get_llm_client", resolver)
    with mock.patch.object(type(client), "invoke", side_effect=RuntimeError("401 unavailable")):
        result = pr_verifier.evaluate_pr("context")
    assert result.verdict == "CONCERNS" and not result.used_llm
    resolver.assert_called_once()
    counter.assert_called_once()


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_installed_sdk_counts_and_generates_on_same_native_transport(provider, monkeypatch):
    import httpx

    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    model = "gpt-5.6-terra" if provider == "openai" else "claude-sonnet-5-5"
    if provider == "openai":
        cls = pytest.importorskip("langchain_openai").ChatOpenAI
        builder = langchain_client._build_openai_client
    else:
        cls = pytest.importorskip("langchain_anthropic").ChatAnthropic
        builder = langchain_client._build_anthropic_client
    client = builder(cls, model=model, token="offline-placeholder", timeout=17, max_retries=0)
    root = client.root_client if provider == "openai" else client._client
    requests = []

    def serve(request):
        requests.append(request)
        assert request.url.host == f"api.{provider}.com"
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "id": model,
                    "type": "model",
                    "display_name": model,
                    "created_at": "2026-10-10T00:00:00Z",
                    "max_input_tokens": 1000000,
                    "max_tokens": 128000,
                },
            )
        if request.url.path.endswith(("input_tokens", "count_tokens")):
            return httpx.Response(
                200, json={"input_tokens": 1000, "object": "response.input_tokens"}
            )
        if provider == "openai":
            return httpx.Response(
                200,
                json={
                    "id": "resp_offline",
                    "object": "response",
                    "created_at": 0,
                    "model": model,
                    "status": "completed",
                    "output": [
                        {
                            "id": "msg_offline",
                            "type": "message",
                            "role": "assistant",
                            "status": "completed",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": '{"verdict":"PASS"}',
                                    "annotations": [],
                                }
                            ],
                        }
                    ],
                    "usage": {"input_tokens": 1000, "output_tokens": 25, "total_tokens": 1025},
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "msg_offline",
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [{"type": "text", "text": '{"verdict":"PASS"}'}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1000, "output_tokens": 25},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(serve)) as transport:
        monkeypatch.setattr(root, "_client", transport)
        response, _, _ = pr_verifier._invoke_llm(client, "complete input", operation="test")
    assert pr_verifier._coerce_response_content(response.content) == '{"verdict":"PASS"}'
    assert pr_verifier._parse_llm_response(response.content, provider).verdict == "PASS"
    expected = (
        ["/v1/responses/input_tokens", "/v1/responses"]
        if provider == "openai"
        else [f"/v1/models/{model}", "/v1/messages/count_tokens", "/v1/messages"]
    )
    assert [r.url.path for r in requests] == expected
    counted = json.loads(requests[-2].content)
    generated = json.loads(requests[-1].content)
    input_key = "input" if provider == "openai" else "messages"
    assert counted[input_key] == generated[input_key]
    assert counted["model"] == generated["model"] == model
    assert generated["max_output_tokens" if provider == "openai" else "max_tokens"] == 128000
    auth = "authorization" if provider == "openai" else "x-api-key"
    assert requests[-2].headers[auth] == requests[-1].headers[auth]


@pytest.mark.parametrize("output", [64000, 128000])
def test_native_exact_input_and_context_boundary_and_explicit_output_preservation(native, output):
    client, provider, _, counter, _ = native
    client.max_tokens = output
    prepared = pr_verifier._prepare_capacity_client(client)
    limit = 922000 if provider == "openai" else 1000000 - output
    counter.return_value.input_tokens = limit
    receipt = pr_verifier._preflight_input_capacity(prepared, "all input")
    assert receipt["status"] == "PASS"
    assert receipt["input_limit"] == (922000 if provider == "openai" else 1000000)
    assert receipt["context_limit"] == (1050000 if provider == "openai" else 1000000)
    assert receipt["output_limit"] == 128000
    assert receipt["output_reserve"] == output
    payload = prepared._get_request_payload("all input")
    assert payload["max_output_tokens" if provider == "openai" else "max_tokens"] == output
    counter.return_value.input_tokens += 1
    with pytest.raises(pr_verifier.InputCapacityError, match="overflow"):
        pr_verifier._preflight_input_capacity(prepared, "all input")


def _run_operation(client, provider, model, operation, monkeypatch):
    monkeypatch.setattr(pr_verifier, "_get_llm_client", lambda **kwargs: (client, provider))
    if operation == "repair":
        return pr_verifier._parse_llm_response("invalid JSON", provider, client=client)
    if operation == "compare":
        return pr_verifier.ComparisonRunner("context", None, "full request", []).run_single(
            client, provider, model
        )
    return pr_verifier.evaluate_pr("context", provider=provider)


@pytest.mark.parametrize("operation", ["evaluate", "compare", "repair"])
@pytest.mark.parametrize(
    "case",
    [
        "formerly-rejected-low",
        "formerly-rejected-mid",
        "boundary",
        "input-overflow",
        "context-overflow",
        "smaller-output-boundary",
        "smaller-output-overflow",
        "output-overflow",
        "metadata-smaller-input-boundary",
        "metadata-smaller-input-overflow",
        "metadata-larger-input-context-boundary",
        "metadata-larger-input-context-overflow",
    ],
)
def test_native_capacity_operations_matrix(native, operation, case, monkeypatch, tmp_path):
    client, provider, model, counter, metadata = native
    input_limit, context_limit, output = (
        (922000, 1050000, 128000) if provider == "openai" else (1000000, 1000000, 128000)
    )
    if case.startswith("metadata-"):
        if provider != "anthropic":
            pytest.skip("Anthropic Models API contract")
        input_limit = 800000 if "smaller" in case else 1100000
        metadata.return_value.max_input_tokens = input_limit
    if case.startswith("smaller-output"):
        output = 64000
        client.max_tokens = output
    if case == "output-overflow":
        output = 128001
        client.max_tokens = output
    tokens = min(input_limit, context_limit - output)
    if case == "formerly-rejected-low":
        tokens = 794001
    elif case == "formerly-rejected-mid":
        tokens = 858001
    elif case == "input-overflow":
        # Isolate the input-only constraint from combined context overflow.
        client.max_tokens = output = 64000
        if provider == "anthropic":
            metadata.return_value.max_input_tokens = input_limit = 800000
        tokens = input_limit + 1
    elif case == "context-overflow":
        # Terra's official input+maximum output equals its context; this crosses both.
        tokens = context_limit - output + 1
    elif case.endswith("overflow") and case != "output-overflow":
        tokens += 1
    counter.return_value.input_tokens = tokens
    report = tmp_path / "capacity.jsonl"
    monkeypatch.setenv("VERIFIER_CAPACITY_REPORT_PATH", str(report))
    expected = "overflow" not in case
    generated = []

    def generate(prepared, prompt, **kwargs):
        payload = prepared._get_request_payload(prompt)
        generated.append(payload)
        key = "input" if provider == "openai" else "messages"
        assert counter.call_args.kwargs[key] == payload[key]
        assert counter.call_args.kwargs["model"] == payload["model"] == model
        assert payload["max_output_tokens" if provider == "openai" else "max_tokens"] == output
        return SimpleNamespace(content='{"verdict":"PASS"}')

    with mock.patch.object(type(client), "invoke", autospec=True, side_effect=generate):
        result = _run_operation(client, provider, model, operation, monkeypatch)
    if operation != "repair":
        assert result.used_llm is expected, result.error
    assert bool(generated) is expected
    receipt = json.loads(report.read_text())
    assert receipt["status"] == (
        "PASS" if expected else "unavailable" if case == "output-overflow" else "overflow"
    )
    assert receipt["input_limit"] == input_limit
    assert receipt["context_limit"] == context_limit
    assert receipt["output_limit"] == 128000
    assert receipt["output_reserve"] == output
    if case == "output-overflow":
        counter.assert_not_called()
    else:
        counter.assert_called_once()
        assert receipt["input_tokens"] == tokens
        assert len(receipt["request_sha256"]) == 64
    if not expected:
        assert result.verdict == "CONCERNS"


@pytest.mark.parametrize("operation", ["evaluate", "compare", "repair"])
@pytest.mark.parametrize("context", ["missing", None, True, False, 0, -1, "1050000", 1050000.0])
def test_native_malformed_context_facts_block(native, operation, context, monkeypatch, tmp_path):
    client, provider, model, counter, _ = native
    native_contract = pr_verifier._native_capacity_contract

    def contract(prepared):
        result = native_contract(prepared)
        if context == "missing":
            result["profile"].pop("max_context_tokens", None)
        else:
            result["profile"]["max_context_tokens"] = context
        return result

    monkeypatch.setattr(pr_verifier, "_native_capacity_contract", contract)
    report = tmp_path / "capacity.jsonl"
    monkeypatch.setenv("VERIFIER_CAPACITY_REPORT_PATH", str(report))
    with mock.patch.object(type(client), "invoke") as invoke:
        result = _run_operation(client, provider, model, operation, monkeypatch)
    assert result.verdict == "CONCERNS"
    if operation != "repair":
        assert not result.used_llm
    invoke.assert_not_called()
    counter.assert_not_called()
    receipt = json.loads(report.read_text())
    assert receipt["status"] == "unavailable"
    assert "context" in receipt["reason"]


def test_native_reserves_actual_payload_output(native, monkeypatch):
    client, provider, _, counter, _ = native
    # Payload overrides are authoritative even when the adapter's default is larger.
    original = type(client)._get_request_payload

    def payload(prepared, prompt, **kwargs):
        result = original(prepared, prompt, **kwargs)
        result["max_output_tokens" if provider == "openai" else "max_tokens"] = 64000
        return result

    monkeypatch.setattr(type(client), "_get_request_payload", payload)
    counter.return_value.input_tokens = 922000 if provider == "openai" else 936000
    receipt = pr_verifier._preflight_input_capacity(
        pr_verifier._prepare_capacity_client(client), "full request"
    )
    assert receipt["status"] == "PASS"
    assert receipt["output_reserve"] == 64000


@pytest.mark.parametrize("operation", ["evaluate", "compare", "repair"])
@pytest.mark.parametrize("output", ["missing", None, True, 0, -1, "64000", 64000.0])
def test_native_missing_or_malformed_payload_output_blocks(native, operation, output, monkeypatch):
    client, provider, model, counter, _ = native
    original = type(client)._get_request_payload

    def payload(prepared, prompt, **kwargs):
        result = original(prepared, prompt, **kwargs)
        key = "max_output_tokens" if provider == "openai" else "max_tokens"
        if output == "missing":
            result.pop(key)
        else:
            result[key] = output
        return result

    monkeypatch.setattr(type(client), "_get_request_payload", payload)
    with mock.patch.object(type(client), "invoke") as invoke:
        result = _run_operation(client, provider, model, operation, monkeypatch)
    assert result.verdict == "CONCERNS"
    if operation != "repair":
        assert not result.used_llm
    invoke.assert_not_called()
    counter.assert_not_called()
