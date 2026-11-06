"""Consumer lint and invoke compatibility regressions for issue #4484."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from scripts.langchain._llm_client import SubscriptionClientAdapter

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("filename", ["_llm_client.py", "pr_verifier.py"])
def test_no_arg002_violations(filename: str) -> None:
    """Check each copy-delivered source with the consumer's unused-argument rule."""
    source = ROOT / "scripts" / "langchain" / filename
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
