from __future__ import annotations

from scripts.langchain.trace_utils import invoke_with_trace


class _Response:
    response_metadata = {"run_id": "trace-123"}
    content = "ok"


class _Runnable:
    def __init__(self) -> None:
        self.payload = None
        self.config = None

    def invoke(self, payload, *, config=None):
        self.payload = payload
        self.config = config
        return _Response()


class _LegacyRunnable:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, payload):
        self.calls += 1
        return _Response()


def test_invoke_with_trace_passes_standard_metadata(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    runnable = _Runnable()

    response, trace = invoke_with_trace(
        runnable,
        {"input": "value"},
        operation="unit_test",
        issue_number=42,
    )

    assert response.content == "ok"
    assert runnable.payload == {"input": "value"}
    assert runnable.config["metadata"]["operation"] == "unit_test"
    assert runnable.config["metadata"]["issue_number"] == "42"
    assert trace.trace_id == "trace-123"
    assert trace.trace_url == "https://smith.langchain.com/r/trace-123"


def test_invoke_with_trace_retries_legacy_runnable_without_config(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    runnable = _LegacyRunnable()

    _response, trace = invoke_with_trace(
        runnable,
        "prompt",
        operation="legacy_unit_test",
    )

    assert runnable.calls == 1
    assert trace.trace_id == "trace-123"
