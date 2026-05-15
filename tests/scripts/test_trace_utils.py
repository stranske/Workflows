from __future__ import annotations

import pytest
from scripts.langchain import trace_utils
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


class _ProviderFailureRunnable:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, payload, *, config=None):
        self.calls += 1
        raise RuntimeError("provider failed")


class _ProviderTypeErrorRunnable:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, payload, *, config=None):
        self.calls += 1
        raise TypeError("provider payload type failed")


class _NoKeywordCallable:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, payload, **kwargs):
        self.calls += 1
        if kwargs:
            raise TypeError("invoke() takes no keyword arguments")
        return _Response()


class _NoKeywordErrorRunnable:
    def __init__(self) -> None:
        self.invoke = _NoKeywordCallable()


class _BuiltinNoKeywordRunnable:
    invoke = staticmethod(len)


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


def test_invoke_with_trace_retries_builtin_no_keyword_callable_without_config(
    monkeypatch,
):
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    monkeypatch.setattr(trace_utils, "_invoke_accepts_config", lambda _invoke: True)
    runnable = _BuiltinNoKeywordRunnable()

    response, trace = invoke_with_trace(
        runnable,
        "prompt",
        operation="builtin_no_keyword_unit_test",
    )

    assert response == len("prompt")
    assert not trace.available


def test_invoke_with_trace_does_not_retry_internal_no_keyword_type_error(
    monkeypatch,
):
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    monkeypatch.setattr(trace_utils, "_invoke_accepts_config", lambda _invoke: True)
    runnable = _NoKeywordErrorRunnable()

    with pytest.raises(TypeError, match="takes no keyword arguments"):
        invoke_with_trace(
            runnable,
            "prompt",
            operation="no_keyword_unit_test",
        )

    assert runnable.invoke.calls == 1


def test_invoke_with_trace_does_not_retry_provider_failures(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    runnable = _ProviderFailureRunnable()

    with pytest.raises(RuntimeError, match="provider failed"):
        invoke_with_trace(runnable, "prompt", operation="failure_unit_test")

    assert runnable.calls == 1


def test_invoke_with_trace_does_not_retry_unrelated_type_errors(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    runnable = _ProviderTypeErrorRunnable()

    with pytest.raises(TypeError, match="provider payload type failed"):
        invoke_with_trace(runnable, "prompt", operation="type_error_unit_test")

    assert runnable.calls == 1
