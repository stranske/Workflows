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


class _ProviderConfigTypeErrorRunnable:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, payload, *, config=None):
        self.calls += 1
        raise TypeError("provider got an unexpected keyword argument 'config'")


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


class _DelegatingRunnable:
    def __init__(self) -> None:
        self.calls = 0
        self.inner = _LegacyRunnable()

    def invoke(self, payload, **kwargs):
        self.calls += 1
        return self.inner.invoke(payload, **kwargs)


class _HelperDelegatingRunnable:
    def __init__(self) -> None:
        self.calls = 0
        self.helper_calls = 0
        self.inner = _LegacyRunnable()

    def invoke(self, payload, **kwargs):
        self.calls += 1
        return self._forward(payload, **kwargs)

    def _forward(self, payload, **kwargs):
        self.helper_calls += 1
        return self.inner.invoke(payload, **kwargs)


class _VariadicWrapperProviderConfigTypeErrorRunnable:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, payload, **kwargs):
        self.calls += 1
        raise TypeError("provider got an unexpected keyword argument 'config'")


class _HelperProviderConfigTypeErrorRunnable:
    def __init__(self) -> None:
        self.calls = 0
        self.helper_calls = 0

    def invoke(self, payload, **kwargs):
        self.calls += 1
        return self._forward(payload, **kwargs)

    def _forward(self, payload, **kwargs):
        self.helper_calls += 1
        raise TypeError("provider got an unexpected keyword argument 'config'")


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
    monkeypatch.setattr(trace_utils, "_invoke_config_support", lambda _invoke: "unknown")
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
    runnable = _NoKeywordErrorRunnable()

    with pytest.raises(TypeError, match="takes no keyword arguments"):
        invoke_with_trace(
            runnable,
            "prompt",
            operation="no_keyword_unit_test",
        )

    assert runnable.invoke.calls == 1


def test_invoke_with_trace_retries_delegating_variadic_wrapper_without_config(
    monkeypatch,
):
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    runnable = _DelegatingRunnable()

    _response, trace = invoke_with_trace(
        runnable,
        "prompt",
        operation="delegating_unit_test",
    )

    assert runnable.calls == 2
    assert runnable.inner.calls == 1
    assert trace.trace_id == "trace-123"


def test_invoke_with_trace_retries_helper_delegating_wrapper_without_config(
    monkeypatch,
):
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    runnable = _HelperDelegatingRunnable()

    _response, trace = invoke_with_trace(
        runnable,
        "prompt",
        operation="helper_delegating_unit_test",
    )

    assert runnable.calls == 2
    assert runnable.helper_calls == 2
    assert runnable.inner.calls == 1
    assert trace.trace_id == "trace-123"


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


def test_invoke_with_trace_does_not_retry_explicit_config_provider_type_error(
    monkeypatch,
):
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    runnable = _ProviderConfigTypeErrorRunnable()

    with pytest.raises(TypeError, match="unexpected keyword argument 'config'"):
        invoke_with_trace(runnable, "prompt", operation="config_type_error_unit_test")

    assert runnable.calls == 1


def test_invoke_with_trace_does_not_retry_variadic_provider_config_type_error(
    monkeypatch,
):
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    runnable = _VariadicWrapperProviderConfigTypeErrorRunnable()

    with pytest.raises(TypeError, match="unexpected keyword argument 'config'"):
        invoke_with_trace(runnable, "prompt", operation="variadic_config_type_error_unit_test")

    assert runnable.calls == 1


def test_invoke_with_trace_does_not_retry_helper_provider_config_type_error(
    monkeypatch,
):
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    runnable = _HelperProviderConfigTypeErrorRunnable()

    with pytest.raises(TypeError, match="unexpected keyword argument 'config'"):
        invoke_with_trace(runnable, "prompt", operation="helper_config_type_error_unit_test")

    assert runnable.calls == 1
    assert runnable.helper_calls == 1


def test_trace_helpers_fall_back_when_provider_imports_fail(monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__

    def unavailable_provider(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: ANN001
        if name == "tools.llm_provider":
            raise ImportError("provider unavailable")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", unavailable_provider)

    config = trace_utils.build_trace_config(operation="fallback", pr_number=4)
    trace = trace_utils.extract_trace_info(object())

    assert config == {
        "metadata": {"operation": "fallback", "pr_number": "4", "issue_number": None},
        "tags": ["operation:fallback"],
    }
    assert trace == trace_utils.TraceInfo()


def test_is_call_instruction_returns_false_for_unknown_instruction_offset() -> None:
    frame = trace_utils._TracebackFrame(
        code=test_is_call_instruction_returns_false_for_unknown_instruction_offset.__code__,
        lineno=1,
        lasti=-1,
    )

    assert trace_utils._is_call_instruction(frame) is False


def test_trace_info_and_signature_detection_cover_optional_paths(monkeypatch) -> None:
    assert trace_utils.TraceInfo(trace_url="https://trace").as_dict() == {
        "langsmith_trace_url": "https://trace"
    }

    def unavailable_signature(_invoke):  # noqa: ANN001
        raise ValueError("no signature")

    monkeypatch.setattr(trace_utils.inspect, "signature", unavailable_signature)
    assert trace_utils._invoke_config_support(object()) == "unknown"
