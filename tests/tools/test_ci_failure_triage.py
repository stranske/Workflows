import sys
import types

from tools import ci_failure_triage, llm_registry


def test_extract_pytest_failures_parses_unique() -> None:
    log_text = "\n".join(
        [
            "FAILED tests/workflows/test_keepalive_workflow.py::test_keepalive_requires_dispatch_token - AssertionError",
            "FAILED tests/workflows/test_keepalive_workflow.py::test_keepalive_prefers_dedicated_dispatch_token[param] - ValueError",
            "FAILED tests/workflows/test_keepalive_workflow.py::test_keepalive_requires_dispatch_token - AssertionError",
        ]
    )

    failures = ci_failure_triage.extract_pytest_failures(log_text)

    assert failures == [
        "tests/workflows/test_keepalive_workflow.py::test_keepalive_requires_dispatch_token",
        "tests/workflows/test_keepalive_workflow.py::test_keepalive_prefers_dedicated_dispatch_token[param]",
    ]


def test_triage_report_includes_failed_tests() -> None:
    log_text = "\n".join(
        [
            "=================================== FAILURES ===================================",
            "FAILED tests/workflows/test_keepalive_workflow.py::test_keepalive_requires_dispatch_token - AssertionError",
        ]
    )

    report = ci_failure_triage.triage_ci_failure(log_text)

    assert report.failed_tests == [
        "tests/workflows/test_keepalive_workflow.py::test_keepalive_requires_dispatch_token"
    ]
    assert "Pytest failures: 1" in report.summary


def test_llm_triage_does_not_fall_back_outside_slot_allowlist(monkeypatch) -> None:
    created: list[object] = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs: object) -> None:
            created.append(kwargs)

    monkeypatch.setitem(
        sys.modules, "langchain_openai", types.SimpleNamespace(ChatOpenAI=FakeChatOpenAI)
    )
    monkeypatch.setenv("GITHUB_TOKEN", "github-token")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-token")
    monkeypatch.setattr(llm_registry, "configured_model_for_provider", lambda _provider: "")

    assert ci_failure_triage._get_llm_client() is None
    assert created == []


def test_llm_triage_falls_back_from_github_models_to_openai(monkeypatch) -> None:
    created: list[dict[str, object]] = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs: object) -> None:
            created.append(kwargs)

    monkeypatch.setitem(
        sys.modules, "langchain_openai", types.SimpleNamespace(ChatOpenAI=FakeChatOpenAI)
    )
    monkeypatch.setenv("GITHUB_TOKEN", "github-token")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-token")
    monkeypatch.setattr(
        llm_registry,
        "configured_model_for_provider",
        lambda provider: "" if provider == "github-models" else "gpt-5-mini",
    )

    client_and_provider = ci_failure_triage._get_llm_client()

    assert client_and_provider is not None
    client, provider = client_and_provider
    assert provider == "openai"
    assert isinstance(client, FakeChatOpenAI)
    assert created == [{"model": "gpt-5-mini", "api_key": "openai-token", "temperature": 0.1}]


def test_llm_triage_does_not_use_empty_openai_token(monkeypatch) -> None:
    created: list[object] = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs: object) -> None:
            created.append(kwargs)

    monkeypatch.setitem(
        sys.modules, "langchain_openai", types.SimpleNamespace(ChatOpenAI=FakeChatOpenAI)
    )
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "")

    assert ci_failure_triage._get_llm_client() is None
    assert created == []
