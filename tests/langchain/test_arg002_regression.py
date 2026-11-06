"""Consumer lint and invoke compatibility regressions for issue #4484."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from scripts.langchain._llm_client import SubscriptionClientAdapter
from tools.subscription_llm import SubscriptionClient

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "source_path",
    [
        "scripts/langchain/_llm_client.py",
        "scripts/langchain/pr_verifier.py",
        "templates/consumer-repo/scripts/langchain/pr_verifier.py",
    ],
    ids=["subscription-source", "verifier-source", "verifier-template"],
)
def test_no_arg002_violations(source_path: str) -> None:
    """Check shipped sources and the verifier template with the consumer's rule."""
    source = ROOT / source_path
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--isolated", "--select", "ARG002", str(source)],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("config", [None, {}, {"tags": ["arg002-regression"]}])
@pytest.mark.parametrize("prompt_value", [False, True], ids=["string", "prompt-value"])
def test_subscription_adapter_forwards_config_and_kwargs(config, prompt_value: bool) -> None:
    """Using config must preserve both prompt rendering and invocation options."""
    client = Mock()
    adapter = SubscriptionClientAdapter(client)
    prompt = (
        SimpleNamespace(to_string=lambda: "Review the change")
        if prompt_value
        else "Review the change"
    )

    result = adapter.invoke(prompt, config=config, stop=["END"])

    client.invoke.assert_called_once_with("Review the change", config=config, stop=["END"])
    assert client.invoke.call_args.kwargs["config"] is config
    assert result is client.invoke.return_value


@pytest.mark.parametrize("agent", ["codex", "claude"])
@pytest.mark.parametrize("config", [None, {}, {"tags": ["arg002-regression"]}])
@pytest.mark.parametrize("prompt_value", [False, True], ids=["string", "prompt-value"])
def test_subscription_adapter_real_transport(monkeypatch, agent, config, prompt_value) -> None:
    """Exercise the concrete invoke signature without launching a subscription CLI."""
    monkeypatch.setattr(SubscriptionClient, "available", lambda self: True)
    stdout = (
        '{"type":"item.completed","item":{"type":"agent_message","text":"reviewed"}}\n'
        if agent == "codex"
        else '{"result":"reviewed","is_error":false}'
    )
    transport = Mock(return_value=SimpleNamespace(returncode=0, stdout=stdout))
    monkeypatch.setattr("tools.subscription_llm.subprocess.run", transport)
    adapter = SubscriptionClientAdapter(SubscriptionClient(agent=agent, model="test-model"))
    prompt = (
        SimpleNamespace(to_string=lambda: "Review the change")
        if prompt_value
        else "Review the change"
    )

    result = adapter.invoke(prompt, config=config, stop=["END"])

    assert result.content == "reviewed"
    transport.assert_called_once()
    assert transport.call_args.kwargs["input"] == "Review the change"
    assert "config" not in transport.call_args.kwargs
    assert "stop" not in transport.call_args.kwargs
