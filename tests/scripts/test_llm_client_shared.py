"""Tests for the shared ``scripts/langchain/_llm_client`` module (issue #2343).

The ``get_llm_client`` / ``get_llm_clients`` helpers replace the ``_get_llm_client``
bodies that were copy-pasted across the langchain agent scripts. These tests stub
``tools.langchain_client`` so they run without the optional langchain deps or any
real credentials.
"""

from __future__ import annotations

import functools
import json
import sys
from types import ModuleType, SimpleNamespace

import pytest
from scripts.langchain import _llm_client


@pytest.fixture(autouse=True)
def _isolate_routing_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("WORKFLOWS_ANALYSIS_CLI", "LANGCHAIN_PROVIDER", "LANGCHAIN_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")


@pytest.fixture(params=["codex", "claude"])
def subscription_process(monkeypatch: pytest.MonkeyPatch, request):
    """Use real client construction/invoke, with auth and process boundaries stubbed."""
    from tools import subscription_llm

    agent = request.param
    monkeypatch.setenv(subscription_llm.MODE_ENV, agent)
    monkeypatch.setattr(subscription_llm.shutil, "which", lambda name: f"/cli/{name}")
    monkeypatch.setattr(subscription_llm, "_has_subscription_auth", lambda name: True)
    calls = []
    state = SimpleNamespace(content="answer", calls=calls, agent=agent)
    original_invoke = subscription_llm.SubscriptionClient.invoke

    def invoke(client, prompt, **kwargs):
        assert isinstance(prompt, str)
        return original_invoke(client, prompt, **kwargs)

    monkeypatch.setattr(subscription_llm.SubscriptionClient, "invoke", invoke)

    def run(command, **kwargs):
        assert isinstance(kwargs["input"], str)
        assert command[0] == agent
        assert command[command.index("--model") + 1] == subscription_llm.analysis_model(agent)
        calls.append(kwargs["input"])
        if agent == "claude":
            output = {"result": state.content}
        else:
            output = {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": state.content},
            }
        return SimpleNamespace(returncode=0, stdout=json.dumps(output))

    monkeypatch.setattr(subscription_llm.subprocess, "run", run)
    return state


def _install_fake_langchain_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    info: object | None = None,
    clients: list[object] | None = None,
) -> ModuleType:
    """Install a fake ``tools.langchain_client`` module and record calls."""
    fake = ModuleType("tools.langchain_client")
    fake.calls = []  # type: ignore[attr-defined]
    fake.clients_calls = []  # type: ignore[attr-defined]

    def build_chat_client(*, model=None, provider=None, force_openai=False):
        fake.calls.append(  # type: ignore[attr-defined]
            {"model": model, "provider": provider, "force_openai": force_openai}
        )
        return info

    def build_chat_clients(*, model1=None, model2=None):
        fake.clients_calls.append({"model1": model1, "model2": model2})  # type: ignore[attr-defined]
        return clients or []

    fake.build_chat_client = build_chat_client  # type: ignore[attr-defined]
    fake.build_chat_clients = build_chat_clients  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tools.langchain_client", fake)
    return fake


def _fake_info() -> SimpleNamespace:
    return SimpleNamespace(
        client=object(),
        provider="openai",
        model="gpt-5.4",
        provider_label="openai:gpt-5.4",
    )


def test_get_llm_client_returns_configured_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Named test (acceptance + deliberate-break gate): a configured client is returned.

    If ``get_llm_client`` is made to return ``None`` this test fails, proving the
    deliberate-break gate from issue #2343.
    """
    info = _fake_info()
    _install_fake_langchain_client(monkeypatch, info=info)

    result = _llm_client.get_llm_client()

    assert result is not None
    client, label = result
    assert client is info.client
    assert label == "openai"


def test_get_llm_client_passes_through_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    info = _fake_info()
    fake = _install_fake_langchain_client(monkeypatch, info=info)

    _llm_client.get_llm_client(force_openai=True, model="o3-mini", provider="openai")

    assert fake.calls == [{"model": "o3-mini", "provider": "openai", "force_openai": True}]


@pytest.mark.parametrize(
    ("return_field", "expected"),
    [
        ("provider", "openai"),
        ("model", "gpt-5.4"),
        ("provider_label", "openai:gpt-5.4"),
    ],
)
def test_get_llm_client_return_field_selects_label(
    monkeypatch: pytest.MonkeyPatch, return_field: str, expected: str
) -> None:
    info = _fake_info()
    _install_fake_langchain_client(monkeypatch, info=info)

    result = _llm_client.get_llm_client(return_field=return_field)

    assert result is not None
    assert result[1] == expected


def test_get_llm_client_rejects_unknown_return_field(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_langchain_client(monkeypatch, info=_fake_info())

    with pytest.raises(ValueError, match="return_field must be one of"):
        _llm_client.get_llm_client(return_field="provider_lable")


def test_get_llm_client_returns_none_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_langchain_client(monkeypatch, info=None)

    assert _llm_client.get_llm_client() is None


def test_get_llm_client_returns_none_without_langchain(monkeypatch: pytest.MonkeyPatch) -> None:
    # Setting the module to None makes ``import tools.langchain_client`` raise ImportError.
    monkeypatch.setitem(sys.modules, "tools.langchain_client", None)

    assert _llm_client.get_llm_client() is None
    assert _llm_client.build_client() is None


def test_get_llm_clients_returns_tuples(monkeypatch: pytest.MonkeyPatch) -> None:
    entries = [
        SimpleNamespace(client=object(), provider="openai", model="m1"),
        SimpleNamespace(client=object(), provider="github-models", model="m2"),
    ]
    _install_fake_langchain_client(monkeypatch, clients=entries)

    result = _llm_client.get_llm_clients(model1="m1", model2="m2")

    assert [(c, p, m) for (c, p, m) in result] == [
        (entries[0].client, "openai", "m1"),
        (entries[1].client, "github-models", "m2"),
    ]


def test_get_llm_clients_returns_empty_without_langchain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "tools.langchain_client", None)

    assert _llm_client.get_llm_clients() == []


def test_representative_scripts_import_shared_helper() -> None:
    """Each script wires its client construction to the shared module."""
    from scripts.langchain import context_extractor, pr_verifier

    # Simple scripts bind the shared helper under the historical mockable name.
    assert context_extractor._get_llm_client is _llm_client.get_llm_client

    # pr_verifier returns the provider_label and reuses the shared dual builder.
    assert isinstance(pr_verifier._get_llm_client, functools.partial)
    assert pr_verifier._get_llm_client.func is _llm_client.get_llm_client
    assert pr_verifier._get_llm_client.keywords == {"return_field": "provider_label"}
    assert pr_verifier._get_llm_clients is _llm_client.get_llm_clients


@pytest.mark.parametrize("chat", [False, True])
def test_subscription_pipe_renders_prompt_values(subscription_process, chat):
    pytest.importorskip("langchain_core.prompts")
    from langchain_core.prompts import ChatPromptTemplate, PromptTemplate

    template_cls = ChatPromptTemplate if chat else PromptTemplate
    template = template_cls.from_template("Review {task}")
    info = _llm_client.build_auxiliary_client()
    client, provider = info.client, info.provider

    response = (template | client).invoke({"task": "the parser"}, config={"tags": ["test"]})

    assert response.content == "answer"
    assert provider == subscription_process.agent
    assert subscription_process.calls == [template.invoke({"task": "the parser"}).to_string()]
    assert client.invoke("plain text", config={}).content == "answer"
    assert subscription_process.calls[-1] == "plain text"


@pytest.mark.parametrize("operation", ["batch", "stream"])
def test_subscription_pipe_renders_batched_and_streaming_prompts(subscription_process, operation):
    pytest.importorskip("langchain_core.prompts")
    from langchain_core.prompts import ChatPromptTemplate

    template = ChatPromptTemplate.from_template("Review {task}")
    chain = template | _llm_client.build_auxiliary_client().client
    inputs = [{"task": "the parser"}, {"task": "the formatter"}]
    config = {"max_concurrency": 1, "tags": ["subscription-regression"]}

    if operation == "stream":
        inputs = inputs[:1]
        responses = list(chain.stream(inputs[0], config=config))
    else:
        responses = chain.batch(inputs, config=config)

    assert [response.content for response in responses] == ["answer"] * len(inputs)
    assert subscription_process.calls == [template.invoke(values).to_string() for values in inputs]


@pytest.mark.parametrize("failure", ["exit", "timeout"])
def test_subscription_pipe_execution_failure_does_not_retry_api(
    monkeypatch, subscription_process, failure
):
    pytest.importorskip("langchain_core.prompts")
    from langchain_core.prompts import ChatPromptTemplate
    from tools import subscription_llm

    fake = _install_fake_langchain_client(monkeypatch, info=_fake_info())
    chain = ChatPromptTemplate.from_template("Review {task}") | (
        _llm_client.build_auxiliary_client().client
    )
    calls = []

    def run(command, **kwargs):
        calls.append(kwargs["input"])
        assert isinstance(kwargs["input"], str)
        if failure == "timeout":
            raise subscription_llm.subprocess.TimeoutExpired(command, kwargs["timeout"])
        return SimpleNamespace(returncode=1, stdout="")

    monkeypatch.setattr(subscription_llm.subprocess, "run", run)
    expected = subscription_llm.subprocess.TimeoutExpired if failure == "timeout" else RuntimeError
    with pytest.raises(expected):
        chain.invoke({"task": "the parser"})

    assert calls == ["Human: Review the parser"]
    assert fake.calls == []


@pytest.mark.parametrize(
    "prompt", [object(), {"task": "invalid"}, SimpleNamespace(to_string=lambda: 3)]
)
def test_subscription_adapter_rejects_nontext_before_transport(prompt):
    calls = []
    adapter = _llm_client.SubscriptionClientAdapter(SimpleNamespace(invoke=calls.append))
    with pytest.raises(TypeError, match="Subscription prompt"):
        adapter.invoke(prompt)
    assert calls == []


@pytest.mark.parametrize(
    "kwargs,env",
    [
        ({"provider": "anthropic", "model": "requested-model"}, {}),
        ({"provider": "github-models"}, {}),
        ({"provider": "openai"}, {}),
        ({"model": "requested-model"}, {}),
        ({"force_openai": True, "provider": "anthropic", "model": "requested-model"}, {}),
        ({}, {"LANGCHAIN_PROVIDER": "anthropic", "LANGCHAIN_MODEL": "requested-model"}),
        ({}, {"LANGCHAIN_PROVIDER": "openai"}),
        ({}, {"LANGCHAIN_MODEL": "requested-model"}),
    ],
)
def test_subscription_mode_preserves_override_routing(
    monkeypatch, subscription_process, kwargs, env
):
    pytest.importorskip("langchain_core.prompts")
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnableLambda

    for name, value in env.items():
        monkeypatch.setenv(name, value)
    invocations = []
    info = _fake_info()
    info.client = RunnableLambda(lambda prompt: invocations.append(prompt.to_string()) or "API")
    fake = _install_fake_langchain_client(monkeypatch, info=info)

    client, label = _llm_client.get_llm_client(**kwargs)
    response = (ChatPromptTemplate.from_template("{task}") | client).invoke({"task": "review"})

    assert response == "API"
    assert label == info.provider
    assert fake.calls == [
        {
            "model": kwargs.get("model"),
            "provider": kwargs.get("provider"),
            "force_openai": kwargs.get("force_openai", False),
        }
    ]
    assert invocations == ["Human: review"]
    assert subscription_process.calls == []


def test_subscription_failure_does_not_retry_api(monkeypatch, subscription_process):
    from tools import subscription_llm

    fake = _install_fake_langchain_client(monkeypatch, info=_fake_info())
    monkeypatch.setattr(subscription_llm, "_has_subscription_auth", lambda name: False)
    with pytest.raises(RuntimeError, match="no API fallback"):
        _llm_client.build_auxiliary_client()
    assert fake.calls == []


@pytest.mark.parametrize("has_chat_client", [False, True])
def test_chat_factory_does_not_require_subscription_auth(
    monkeypatch, subscription_process, has_chat_client
):
    from tools import subscription_llm

    def unexpected_subscription_check(*args):
        pytest.fail("Ordinary chat construction must not inspect subscription auth or registry")

    monkeypatch.setattr(subscription_llm, "_has_subscription_auth", unexpected_subscription_check)
    monkeypatch.setattr(subscription_llm, "analysis_model", unexpected_subscription_check)
    info = _fake_info() if has_chat_client else None
    fake = _install_fake_langchain_client(monkeypatch, info=info)

    result = _llm_client.get_llm_client()

    assert result == ((info.client, info.provider) if has_chat_client else None)
    assert fake.calls == [{"model": None, "provider": None, "force_openai": False}]
    assert subscription_process.calls == []


@pytest.mark.parametrize("factory_name", ["build_client", "get_llm_client"])
@pytest.mark.parametrize("chat_available", [False, True])
def test_auxiliary_selection_does_not_leak_into_ordinary_factory(
    monkeypatch, subscription_process, factory_name, chat_available
):
    """Alternating auxiliary and ordinary calls preserves each transport's contract."""
    chat_prompts = []
    info = _fake_info()
    info.client = SimpleNamespace(
        invoke=lambda prompt: chat_prompts.append(prompt) or SimpleNamespace(content="chat reply")
    )
    fake = _install_fake_langchain_client(monkeypatch, info=info)
    if not chat_available:
        # Subscription analysis must work even when the ordinary factory cannot import.
        monkeypatch.setitem(sys.modules, "tools.langchain_client", None)

    factory = getattr(_llm_client, factory_name)
    for phase in ("before", "after"):
        resolved = factory()
        if chat_available:
            if factory_name == "build_client":
                assert resolved is info
                client = resolved.client
            else:
                client, provider = resolved
                assert provider == info.provider
            assert client is info.client
            assert client.invoke(phase).content == "chat reply"
        else:
            assert resolved is None

        if phase == "before":
            chat_calls_before = list(fake.calls)
            auxiliary = _llm_client.build_auxiliary_client()
            assert isinstance(auxiliary.client, _llm_client.SubscriptionClientAdapter)
            assert auxiliary.provider == subscription_process.agent
            assert auxiliary.client.invoke("auxiliary review").content == "answer"
            assert fake.calls == chat_calls_before

    assert chat_prompts == (["before", "after"] if chat_available else [])
    assert fake.calls == (
        [{"model": None, "provider": None, "force_openai": False}] * 2 if chat_available else []
    )
    assert subscription_process.calls == ["auxiliary review"]


@pytest.mark.parametrize("consumer", ["capability", "decomposer", "optimizer", "apply"])
@pytest.mark.parametrize("provider", ["openai", "anthropic", "github-models"])
def test_consumers_keep_chat_routing_with_subscription_enabled(
    monkeypatch, subscription_process, consumer, provider
):
    """Exercise consumer composition and overrides through the real shared factory."""
    pytest.importorskip("langchain_core.prompts")
    from langchain_core.runnables import RunnableLambda
    from scripts.langchain import capability_check, issue_optimizer, task_decomposer

    invocations = []

    def chat_class(selected_provider):
        def build(**kwargs):
            actual_provider = selected_provider
            if selected_provider == "openai" and "base_url" in kwargs:
                actual_provider = "github-models"

            def invoke(prompt):
                invocations.append((actual_provider, kwargs["model"], prompt.to_string()))
                return SimpleNamespace(content=subscription_process.content)

            return RunnableLambda(invoke)

        return build

    monkeypatch.setitem(
        sys.modules, "langchain_openai", SimpleNamespace(ChatOpenAI=chat_class("openai"))
    )
    monkeypatch.setitem(
        sys.modules, "langchain_anthropic", SimpleNamespace(ChatAnthropic=chat_class("anthropic"))
    )
    for name in ("OPENAI_API_KEY", "CLAUDE_API_STRANSKE", "GITHUB_TOKEN"):
        monkeypatch.setenv(name, "test-only")
    monkeypatch.setenv("LANGCHAIN_PROVIDER", provider)
    monkeypatch.setenv("LANGCHAIN_MODEL", "consumer-requested-model")

    if consumer == "capability":
        subscription_process.content = json.dumps(
            {"actionable_tasks": ["Add parser tests"], "recommendation": "PROCEED"}
        )
        result = capability_check.classify_capabilities(["Add parser tests"], "Tests pass")
        assert result.recommendation == "PROCEED"
        assert result.provider_used == provider
    elif consumer == "decomposer":
        subscription_process.content = json.dumps({"sub_tasks": ["Implement parser", "Add tests"]})
        result = task_decomposer.decompose_task("Implement a parser and add tests and update docs")
        assert result["used_llm"] is True
        assert result["provider_used"] == provider
    elif consumer == "optimizer":
        subscription_process.content = json.dumps(
            {
                "task_splitting": [],
                "blocked_tasks": [],
                "objective_criteria": [],
                "missing_sections": [],
                "formatting_issues": [],
                "overall_notes": "Ready",
            }
        )
        result = issue_optimizer.analyze_issue("## Tasks\n- [ ] Add parser tests")
        assert result.overall_notes == "Ready"
        assert result.provider_used == provider
    else:
        subscription_process.content = (
            "## Why\nTest the parser.\n\n## Scope\nParser tests.\n\n"
            "## Tasks\n- [ ] Add tests\n\n## Acceptance Criteria\n- [ ] Tests pass\n"
        )
        result = issue_optimizer.apply_suggestions("## Tasks\n- [ ] Add tests", {})
        assert result["used_llm"] is True
        assert result["provider_used"] == provider
    expected_model = (
        "openai/consumer-requested-model"
        if provider == "github-models"
        else "consumer-requested-model"
    )
    assert len(invocations) == 1
    actual_provider, actual_model, prompt = invocations[0]
    assert (actual_provider, actual_model) == (provider, expected_model)
    assert isinstance(prompt, str) and "Add" in prompt
    assert subscription_process.calls == []


def test_auxiliary_progress_review_ignores_chat_overrides(monkeypatch, subscription_process):
    from scripts.langchain.progress_reviewer import review_progress_with_llm

    monkeypatch.setenv("LANGCHAIN_PROVIDER", "github-models")
    monkeypatch.setenv("LANGCHAIN_MODEL", "api-model")
    monkeypatch.setitem(sys.modules, "langchain_core", None)
    fake = _install_fake_langchain_client(monkeypatch, info=_fake_info())
    subscription_process.content = json.dumps(
        {
            "recommendation": "CONTINUE",
            "confidence": 0.9,
            "alignment_score": 8,
            "trajectory": "advancing",
            "analysis": {"prep_work_identified": [], "scope_drift_identified": []},
            "feedback_for_agent": "Continue",
            "summary": "On track",
        }
    )

    result = review_progress_with_llm(["Add tests"], ["Added tests"], ["test.py"], 1)

    assert result.recommendation == "CONTINUE"
    assert subscription_process.calls
    assert fake.calls == []


@pytest.mark.parametrize("provider", ["openai", "anthropic", "github-models"])
@pytest.mark.parametrize(
    "selection",
    ["arguments", "environment", "argument-provider", "argument-model", "argument-precedence"],
)
def test_subscription_mode_invokes_requested_provider_and_model(
    monkeypatch, subscription_process, provider, selection
):
    pytest.importorskip("langchain_core.prompts")
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnableLambda

    calls = []

    def chat_class(selected_provider):
        def build(**kwargs):
            actual_provider = selected_provider
            if selected_provider == "openai" and "base_url" in kwargs:
                actual_provider = "github-models"

            def invoke(prompt):
                calls.append((actual_provider, kwargs["model"], prompt.to_string()))
                return SimpleNamespace(content="selected model reply")

            return RunnableLambda(invoke)

        return build

    monkeypatch.setitem(
        sys.modules,
        "langchain_openai",
        SimpleNamespace(ChatOpenAI=chat_class("openai")),
    )
    monkeypatch.setitem(
        sys.modules, "langchain_anthropic", SimpleNamespace(ChatAnthropic=chat_class("anthropic"))
    )
    for name in ("OPENAI_API_KEY", "CLAUDE_API_STRANSKE", "GITHUB_TOKEN"):
        monkeypatch.setenv(name, "test-only")

    kwargs = {}
    if selection in {"arguments", "argument-provider", "argument-precedence"}:
        kwargs["provider"] = provider
    else:
        monkeypatch.setenv("LANGCHAIN_PROVIDER", provider)
    if selection in {"arguments", "argument-model", "argument-precedence"}:
        kwargs["model"] = "requested-model"
    else:
        monkeypatch.setenv("LANGCHAIN_MODEL", "requested-model")
    if selection == "argument-precedence":
        other_provider = "anthropic" if provider == "openai" else "openai"
        monkeypatch.setenv("LANGCHAIN_PROVIDER", other_provider)
        monkeypatch.setenv("LANGCHAIN_MODEL", "environment-model")

    info = _llm_client.build_client(**kwargs)
    assert info is not None
    response = (ChatPromptTemplate.from_template("{task}") | info.client).invoke({"task": "review"})

    expected_model = "openai/requested-model" if provider == "github-models" else "requested-model"
    assert calls == [(provider, expected_model, "Human: review")]
    assert (info.provider, info.model) == (provider, "requested-model")
    assert response.content == "selected model reply"
    assert subscription_process.calls == []


@pytest.mark.parametrize("environment_model", [False, True])
@pytest.mark.parametrize("force_openai", [False, True])
def test_subscription_mode_model_override_without_provider(
    monkeypatch, subscription_process, environment_model, force_openai
):
    pytest.importorskip("langchain_core.prompts")
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnableLambda

    invocations = []

    def build(**kwargs):
        assert "base_url" not in kwargs

        def invoke(prompt):
            invocations.append((kwargs["model"], prompt.to_string()))
            return SimpleNamespace(content="selected model reply")

        return RunnableLambda(invoke)

    monkeypatch.setitem(sys.modules, "langchain_openai", SimpleNamespace(ChatOpenAI=build))
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    kwargs = {"force_openai": force_openai}
    if environment_model:
        monkeypatch.setenv("LANGCHAIN_MODEL", "requested-model")
    else:
        kwargs["model"] = "requested-model"
    if force_openai:
        # Forced OpenAI must win over both caller and environment provider choices.
        kwargs["provider"] = "anthropic"
        monkeypatch.setenv("LANGCHAIN_PROVIDER", "github-models")

    info = _llm_client.build_client(**kwargs)
    assert info is not None
    response = (ChatPromptTemplate.from_template("{task}") | info.client).invoke({"task": "review"})

    assert (info.provider, info.model) == ("openai", "requested-model")
    assert invocations == [("requested-model", "Human: review")]
    assert response.content == "selected model reply"
    assert subscription_process.calls == []


@pytest.mark.parametrize(
    "kwargs,env",
    [
        ({"provider": "anthropic"}, {}),
        ({"model": "requested-model"}, {}),
        ({"force_openai": True}, {}),
        ({}, {"LANGCHAIN_PROVIDER": "openai"}),
        ({}, {"LANGCHAIN_MODEL": "requested-model"}),
    ],
)
def test_unavailable_requested_client_does_not_substitute_subscription(
    monkeypatch, subscription_process, kwargs, env
):
    for name in ("OPENAI_API_KEY", "CLAUDE_API_STRANSKE", "GITHUB_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    assert _llm_client.build_client(**kwargs) is None
    assert _llm_client.get_llm_client(**kwargs) is None
    assert subscription_process.calls == []


@pytest.mark.parametrize("provider", ["openai", "anthropic", "github-models"])
@pytest.mark.parametrize(
    "overrides,expected_models",
    [
        (
            {"model1": "primary-model", "model2": "secondary-model"},
            ["primary-model", "secondary-model"],
        ),
        ({"model2": "secondary-model"}, ["environment-model", "secondary-model"]),
        ({"model1": "primary-model"}, ["primary-model"]),
    ],
)
def test_subscription_mode_preserves_comparison_client_overrides(
    monkeypatch, subscription_process, provider, overrides, expected_models
):
    """Comparison callers retain model selection and prompt composition for every client."""
    pytest.importorskip("langchain_core.prompts")
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnableLambda

    invocations = []

    def chat_class(selected_provider):
        def build(**kwargs):
            actual_provider = selected_provider
            if selected_provider == "openai" and "base_url" in kwargs:
                actual_provider = "github-models"

            def invoke(prompt):
                invocations.append((actual_provider, kwargs["model"], prompt.to_string()))
                return SimpleNamespace(content="comparison reply")

            return RunnableLambda(invoke)

        return build

    monkeypatch.setitem(
        sys.modules, "langchain_openai", SimpleNamespace(ChatOpenAI=chat_class("openai"))
    )
    monkeypatch.setitem(
        sys.modules, "langchain_anthropic", SimpleNamespace(ChatAnthropic=chat_class("anthropic"))
    )
    for name in ("OPENAI_API_KEY", "CLAUDE_API_STRANSKE", "GITHUB_TOKEN"):
        monkeypatch.setenv(name, "test-only")
    monkeypatch.setenv("LANGCHAIN_PROVIDER", provider)
    monkeypatch.setenv("LANGCHAIN_MODEL", "environment-model")

    clients = _llm_client.get_llm_clients(**overrides)

    assert [(selected, model) for _, selected, model in clients] == [
        (provider, model) for model in expected_models
    ]
    template = ChatPromptTemplate.from_template("Compare {task}")
    for client, _, _ in clients:
        assert (template | client).invoke({"task": "the parser"}).content == "comparison reply"
    assert invocations == [
        (
            provider,
            f"openai/{model}" if provider == "github-models" else model,
            "Human: Compare the parser",
        )
        for model in expected_models
    ]
    assert subscription_process.calls == []
