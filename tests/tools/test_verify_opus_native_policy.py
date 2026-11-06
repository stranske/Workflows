"""Offline native Opus response and documented-capacity controls; no qualification."""

from __future__ import annotations

import json

import pytest
from scripts.langchain import pr_verifier as verifier
from tools import langchain_client, llm_registry


def test_documented_opus_facts_do_not_invent_separate_input_limit(monkeypatch):
    monkeypatch.delenv(llm_registry.ENV_MODEL_REGISTRY_CONFIG, raising=False)
    facts = llm_registry.native_capacity_facts_for("anthropic", "claude-opus-5-5")
    assert facts.max_input_tokens is None
    assert (facts.max_context_tokens, facts.max_output_tokens) == (1000000, 128000)
    assert facts.provenance.endswith(":2026-10-27")


@pytest.fixture(autouse=True)
def deny_unmocked_network(monkeypatch):
    def refuse(*args, **kwargs):
        pytest.fail("native policy tests require inert transports; live network is forbidden")

    monkeypatch.setattr("socket.getaddrinfo", refuse)
    monkeypatch.setattr("socket.socket.connect", refuse)


@pytest.mark.parametrize("defect", [None, "model", "input", "output", "count"])
def test_native_opus_thinking_text_parser_and_admission(monkeypatch, defect):
    httpx = pytest.importorskip("httpx")
    cls = pytest.importorskip("langchain_anthropic").ChatAnthropic
    from anthropic.types import Message, TextBlock, ThinkingBlock, Usage

    monkeypatch.delenv(llm_registry.ENV_MODEL_REGISTRY_CONFIG, raising=False)
    model = "claude-opus-5-5"
    raw = '{"verdict":"PASS","concerns":[],"summary":"Substantive fixture judgment"}'
    native = Message(
        id="msg_offline",
        model=model,
        role="assistant",
        type="message",
        content=[
            ThinkingBlock(
                type="thinking",
                thinking="PRIVATE reasoning is not verdict JSON",
                signature="offline",
            ),
            TextBlock(type="text", text=raw),
        ],
        stop_reason="end_turn",
        stop_sequence=None,
        usage=Usage(input_tokens=1000, output_tokens=50),
    )
    requests = []

    def serve(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "id": "wrong-model" if defect == "model" else model,
                    "type": "model",
                    "display_name": "offline",
                    "created_at": "2026-10-27T00:00:00Z",
                    "max_input_tokens": None if defect == "input" else 1000000,
                    "max_tokens": None if defect == "output" else 128000,
                },
            )
        payload = json.loads(request.content)
        assert payload["model"] == model
        if request.url.path.endswith("count_tokens"):
            return httpx.Response(200, json={"input_tokens": 999999 if defect == "count" else 1000})
        assert payload["max_tokens"] == 128000
        assert (
            not {
                "temperature",
                "top_p",
                "top_k",
                "thinking",
                "output_config",
                "tools",
                "tool_choice",
            }
            & payload.keys()
        )
        return httpx.Response(200, json=native.model_dump())

    client = langchain_client._build_anthropic_client(
        cls, model=model, token="offline-placeholder", timeout=60, max_retries=0
    )
    transport = httpx.Client(transport=httpx.MockTransport(serve))
    monkeypatch.setattr(client._client, "_client", transport)
    try:
        if defect:
            with pytest.raises(verifier.InputCapacityError):
                verifier._invoke_llm(
                    client, "complete offline prompt", operation="opus-native-policy"
                )
            assert not any(r.method == "POST" and r.url.path == "/v1/messages" for r in requests)
        else:
            response, _, _ = verifier._invoke_llm(
                client, "complete offline prompt", operation="opus-native-policy"
            )
            text = verifier._coerce_response_content(response.content)
            assert text == raw
            parsed = verifier._parse_semantic_evaluation_payload(text)
            assert parsed.verdict == "PASS"
            assert "PRIVATE" not in parsed.summary
            assert [r.url.path for r in requests] == [
                "/v1/models/claude-opus-5-5",
                "/v1/messages/count_tokens",
                "/v1/messages",
            ]
    finally:
        transport.close()
