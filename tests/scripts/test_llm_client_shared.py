"""Tests for the shared ``scripts/langchain/_llm_client`` module (issue #2343).

The ``get_llm_client`` / ``get_llm_clients`` helpers replace the ``_get_llm_client``
bodies that were copy-pasted across the langchain agent scripts. Core helper tests
stub ``tools.langchain_client``. Subscription regression tests
use real LangChain composition and provider/model selection, with authentication
and process/SDK boundaries stubbed; they require ``langchain_core``.
"""

from __future__ import annotations

import asyncio
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


@pytest.fixture
def chat_process(monkeypatch, subscription_process):
    """Keep real provider/model selection; stub only provider SDK construction."""
    from langchain_core.runnables import RunnableLambda

    calls = []

    def chat_class(selected_provider):
        def build(**kwargs):
            actual_provider = selected_provider
            if selected_provider == "openai" and "base_url" in kwargs:
                actual_provider = "github-models"

            def invoke(prompt):
                calls.append((actual_provider, kwargs["model"], prompt.to_string()))
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
    return calls


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


@pytest.mark.parametrize("analysis_cli", [None, "codex", "claude"])
def test_missing_chat_factory_does_not_substitute_subscription(
    monkeypatch: pytest.MonkeyPatch, analysis_cli: str | None
) -> None:
    """Ordinary callers stay unavailable when LangChain cannot be imported.

    The reviewed failure returned a subscription client whenever
    ``WORKFLOWS_ANALYSIS_CLI`` was set, including when chat construction was
    impossible. That client is not a pipe participant and ignores caller
    provider and model selection. Import failure must stay a clean miss.
    """
    from tools import subscription_llm

    if analysis_cli:
        monkeypatch.setenv("WORKFLOWS_ANALYSIS_CLI", analysis_cli)
    monkeypatch.setitem(sys.modules, "tools.langchain_client", None)

    def unexpected_subscription(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Ordinary chat construction must not substitute a subscription client")

    monkeypatch.setattr(subscription_llm, "build_subscription_client", unexpected_subscription)

    assert _llm_client.build_client(provider="openai", model="requested-model") is None
    assert _llm_client.get_llm_client(provider="openai", model="requested-model") is None
    assert _llm_client.get_llm_clients(model1="primary-model") == []


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


def test_subscription_pipe_preserves_chat_roles_and_content(subscription_process):
    """Render the full chat history as text before it reaches either CLI transport."""
    from langchain_core.prompts import ChatPromptTemplate

    template = ChatPromptTemplate.from_messages(
        [
            ("system", "Review the parser; preserve quoted input."),
            ("human", "{task}"),
            ("ai", "Previously checked: {context}"),
        ]
    )
    chain = template | _llm_client.build_auxiliary_client().client

    response = chain.invoke({"task": 'Check "café"\nand braces: {value}', "context": "escaping"})

    assert response.content == "answer"
    assert subscription_process.calls == [
        "System: Review the parser; preserve quoted input.\n"
        'Human: Check "café"\nand braces: {value}\n'
        "AI: Previously checked: escaping"
    ]


@pytest.mark.parametrize("operation", ["batch", "stream", "ainvoke", "abatch", "astream"])
def test_subscription_pipe_renders_each_execution_mode(subscription_process, operation):
    from langchain_core.prompts import ChatPromptTemplate

    template = ChatPromptTemplate.from_template("Review {task}")
    chain = template | _llm_client.build_auxiliary_client().client
    inputs = [{"task": "the parser"}, {"task": "the formatter"}]
    config = {"max_concurrency": 1, "tags": ["subscription-regression"]}

    if operation in {"stream", "ainvoke", "astream"}:
        inputs = inputs[:1]

    async def run_async():
        if operation == "ainvoke":
            return [await chain.ainvoke(inputs[0], config=config)]
        if operation == "astream":
            return [response async for response in chain.astream(inputs[0], config=config)]
        return await chain.abatch(inputs, config=config)

    if operation.startswith("a"):
        with asyncio.Runner() as runner:
            loop = runner.get_loop()

            def heartbeat():
                # Restricted runners may deny asyncio's socketpair send when
                # the real LangChain executor finishes. A timer wakes the loop
                # without replacing the executor or the subscription adapter.
                loop.call_later(0.05, heartbeat)

            heartbeat()
            responses = runner.run(asyncio.wait_for(run_async(), timeout=10))
    elif operation == "stream":
        responses = list(chain.stream(inputs[0], config=config))
    else:
        responses = chain.batch(inputs, config=config)

    assert [response.content for response in responses] == ["answer"] * len(inputs)
    assert subscription_process.calls == [template.invoke(values).to_string() for values in inputs]


@pytest.mark.parametrize("failure", ["exit", "timeout"])
def test_subscription_pipe_execution_failure_does_not_retry_api(
    monkeypatch, subscription_process, failure
):
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


@pytest.mark.parametrize("consumer", ["capability", "decomposer", "optimizer", "apply"])
@pytest.mark.parametrize("provider", ["openai", "anthropic", "github-models"])
def test_consumers_keep_chat_routing_with_subscription_enabled(
    monkeypatch, subscription_process, chat_process, consumer, provider
):
    """Exercise consumer composition and overrides through the real shared factory."""
    from scripts.langchain import capability_check, issue_optimizer, task_decomposer

    invocations = chat_process
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


@pytest.mark.parametrize("consumer", ["analyze", "apply"])
def test_subscription_mode_preserves_consumer_openai_retry(
    monkeypatch, subscription_process, chat_process, consumer
):
    """A real consumer pipe retries GitHub Models failures through the chat factory."""
    from langchain_core.runnables import RunnableLambda
    from scripts.langchain import issue_optimizer

    monkeypatch.setenv("LANGCHAIN_PROVIDER", "github-models")
    monkeypatch.setenv("LANGCHAIN_MODEL", "requested-model")
    openai_sdk = sys.modules["langchain_openai"]
    original_build = openai_sdk.ChatOpenAI

    def build(**kwargs):
        client = original_build(**kwargs)
        if "base_url" not in kwargs:
            return client

        def fail(prompt):
            client.invoke(prompt)
            raise RuntimeError("Error code: 413 tokens_limit_reached")

        return RunnableLambda(fail)

    monkeypatch.setattr(openai_sdk, "ChatOpenAI", build)
    if consumer == "analyze":
        subscription_process.content = json.dumps(
            {
                "task_splitting": [],
                "blocked_tasks": [],
                "objective_criteria": [],
                "missing_sections": [],
                "formatting_issues": [],
                "overall_notes": "Recovered with OpenAI",
            }
        )
        result = issue_optimizer.analyze_issue("## Tasks\n- [ ] Add parser tests")
        assert result.provider_used == "openai"
        assert result.overall_notes == "Recovered with OpenAI"
    else:
        subscription_process.content = (
            "## Why\nTest the parser.\n\n## Scope\nParser tests.\n\n"
            "## Tasks\n- [ ] Add tests\n\n## Acceptance Criteria\n- [ ] Tests pass\n"
        )
        result = issue_optimizer.apply_suggestions("## Tasks\n- [ ] Add tests", {})
        assert result["used_llm"] is True
        assert result["provider_used"] == "openai"

    assert [(provider, model) for provider, model, _ in chat_process] == [
        ("github-models", "openai/requested-model"),
        ("openai", "requested-model"),
    ]
    assert chat_process[0][2] == chat_process[1][2]
    assert subscription_process.calls == []


def test_subscription_mode_preserves_decomposer_openai_retry(
    monkeypatch, subscription_process, chat_process
):
    """GitHub Models auth failures retry through the standard factory, not the CLI."""
    from langchain_core.runnables import RunnableLambda
    from scripts.langchain import task_decomposer

    monkeypatch.setenv("LANGCHAIN_PROVIDER", "github-models")
    monkeypatch.setenv("LANGCHAIN_MODEL", "requested-model")
    openai_sdk = sys.modules["langchain_openai"]
    original_build = openai_sdk.ChatOpenAI

    def build(**kwargs):
        client = original_build(**kwargs)
        if "base_url" not in kwargs:
            return client

        def fail(prompt):
            client.invoke(prompt)
            raise RuntimeError("Error code: 401 models unauthorized")

        return RunnableLambda(fail)

    monkeypatch.setattr(openai_sdk, "ChatOpenAI", build)
    subscription_process.content = "- Implement the parser\n- Add parser tests"
    result = task_decomposer.decompose_task("Implement a parser and add tests and update docs")

    assert result["used_llm"] is True
    assert result["provider_used"] == "openai"
    assert result["sub_tasks"]
    assert [(provider, model) for provider, model, _ in chat_process] == [
        ("github-models", "openai/requested-model"),
        ("openai", "requested-model"),
    ]
    assert all(isinstance(prompt, str) and prompt for _, _, prompt in chat_process)
    assert subscription_process.calls == []


@pytest.mark.parametrize("provider", ["openai", "anthropic", "github-models"])
@pytest.mark.parametrize(
    "selection",
    ["arguments", "environment", "argument-provider", "argument-model", "argument-precedence"],
)
def test_subscription_mode_preserves_override_routing(
    monkeypatch, subscription_process, chat_process, provider, selection
):
    from langchain_core.prompts import ChatPromptTemplate

    subscription_process.content = "selected model reply"
    calls = chat_process

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
    monkeypatch, subscription_process, chat_process, provider, overrides, expected_models
):
    """Comparison callers retain model selection and prompt composition for every client."""
    from langchain_core.prompts import ChatPromptTemplate

    subscription_process.content = "comparison reply"
    invocations = chat_process
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
