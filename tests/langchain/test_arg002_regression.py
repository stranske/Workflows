"""Consumer lint and invoke compatibility regressions for issue #4484."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from scripts.langchain import pr_verifier
from scripts.langchain._llm_client import SubscriptionClientAdapter
from tools.subscription_llm import SubscriptionClient

ROOT = Path(__file__).resolve().parents[2]

ARG002_SOURCES = (
    "scripts/langchain/_llm_client.py",
    "scripts/langchain/pr_verifier.py",
    "templates/consumer-repo/scripts/langchain/pr_verifier.py",
)


def _ruff_arg002(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--isolated", "--select", "ARG002", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize(
    "source_path",
    ARG002_SOURCES,
    ids=["subscription-source", "verifier-source", "verifier-template"],
)
def test_no_arg002_violations(source_path: str) -> None:
    """Check shipped sources and the verifier template with the consumer's rule."""
    result = _ruff_arg002(ROOT / source_path)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("source_path", "restore_needle"),
    [
        (
            "scripts/langchain/_llm_client.py",
            "        _ = config\n",
        ),
        (
            "scripts/langchain/pr_verifier.py",
            "def invoke(self, prompt: str, config: Any = None, **_: Any) -> Any:  # noqa: ARG002",
        ),
        (
            "templates/consumer-repo/scripts/langchain/pr_verifier.py",
            "def invoke(self, prompt: str, config: Any = None, **_: Any) -> Any:  # noqa: ARG002",
        ),
    ],
    ids=["subscription-source", "verifier-source", "verifier-template"],
)
def test_reintroducing_unused_config_fails_arg002(
    tmp_path: Path, source_path: str, restore_needle: str
) -> None:
    """Deliberate-break: the reported unused-config shape must fail ARG002 again."""
    original = (ROOT / source_path).read_text()
    assert restore_needle in original, f"fix needle missing from {source_path}"

    if source_path.endswith("_llm_client.py"):
        # Keep the config parameter in the signature but stop referencing it.
        broken = original.replace(restore_needle, "", 1)
    else:
        broken = original.replace(
            "def invoke(self, prompt: str, config: Any = None, **_: Any) -> Any:  # noqa: ARG002",
            "def invoke(self, prompt: str, config: Any = None, **_: Any) -> Any:",
            1,
        )
    assert broken != original
    assert restore_needle not in broken

    mutant = tmp_path / Path(source_path).name
    mutant.write_text(broken)
    failed = _ruff_arg002(mutant)
    assert failed.returncode != 0, failed.stdout + failed.stderr
    assert "ARG002" in failed.stdout
    assert re.search(r"\bconfig\b", failed.stdout)

    # Restoring the retained fix on the real path must still pass.
    restored = _ruff_arg002(ROOT / source_path)
    assert restored.returncode == 0, restored.stdout + restored.stderr


@pytest.mark.parametrize("config", [None, {}, {"tags": ["arg002-regression"]}])
@pytest.mark.parametrize("prompt_value", [False, True], ids=["string", "prompt-value"])
def test_subscription_adapter_accepts_config_without_forwarding(config, prompt_value: bool) -> None:
    """Runnable config is accepted for coercion, but not forwarded to the CLI client."""
    client = Mock()
    adapter = SubscriptionClientAdapter(client)
    prompt = (
        SimpleNamespace(to_string=lambda: "Review the change")
        if prompt_value
        else "Review the change"
    )

    result = adapter.invoke(prompt, config=config, stop=["END"])

    client.invoke.assert_called_once_with("Review the change", stop=["END"])
    assert "config" not in client.invoke.call_args.kwargs
    assert result is client.invoke.return_value


@pytest.mark.parametrize("config", [None, {}, {"tags": ["arg002-regression"]}])
def test_capacity_backup_client_accepts_unused_config(monkeypatch, config) -> None:
    """CapacityBackupClient keeps the Runnable config kwarg without forwarding it."""
    import urllib.request

    client = pr_verifier.CapacityBackupClient(
        model="m",
        base_url="https://example.invalid/v1",
        key_env="ARG002_CAPACITY_KEY",
    )
    monkeypatch.setenv("ARG002_CAPACITY_KEY", "test-key")

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"ok"}}]}'

    opened: list[object] = []

    def fake_urlopen(request, timeout=0):
        opened.append((request.full_url, timeout, request.data))
        return _Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = client.invoke("Review the change", config=config, stop=["END"])

    assert result.content == "ok"
    assert len(opened) == 1
    assert opened[0][0] == "https://example.invalid/v1/chat/completions"
    assert b"Review the change" in opened[0][2]


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
