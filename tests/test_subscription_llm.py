"""Subscription CLI availability uses the same auth directory as the child CLI."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from tools import subscription_llm

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(params=("source", "template"))
def claude_client(request, monkeypatch, tmp_path):
    transport = subscription_llm
    if request.param == "template":
        name = "subscription_llm_availability_template"
        spec = importlib.util.spec_from_file_location(
            name, ROOT / "templates/consumer-repo/tools/subscription_llm.py"
        )
        transport = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, transport)
        spec.loader.exec_module(transport)

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(transport.shutil, "which", lambda _: "/fixture/bin/claude")
    return transport.SubscriptionClient(agent="claude", model="fixture-model")


def test_claude_available_with_configured_directory(claude_client, monkeypatch, tmp_path):
    config = tmp_path / "custom-claude"
    config.mkdir()
    (config / ".credentials.json").touch()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))

    assert (claude_client.available() is True,) == (True,)


@pytest.mark.parametrize("default_auth_exists", (False, True))
def test_claude_invocation_uses_configured_directory(
    claude_client, monkeypatch, tmp_path, default_auth_exists
):
    config = tmp_path / "custom-claude"
    config.mkdir()
    (config / ".credentials.json").touch()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    if default_auth_exists:
        default = Path.home() / ".claude"
        default.mkdir(parents=True)
        (default / ".credentials.json").touch()
    transport = sys.modules[type(claude_client).__module__]
    calls = []

    def run_cli(command, **options):
        calls.append((command[0], options["env"]["CLAUDE_CONFIG_DIR"]))
        assert options["input"] == "fixture prompt"
        return SimpleNamespace(returncode=0, stdout='{"result": "fixture analysis"}')

    monkeypatch.setattr(transport.subprocess, "run", run_cli)

    assert claude_client.invoke("fixture prompt").content == "fixture analysis"
    assert calls == [("claude", str(config))]


@pytest.mark.parametrize("default_auth_exists", (False, True))
@pytest.mark.parametrize("config_state", ("missing", "empty", "directory-entry"))
def test_claude_unavailable_without_configured_credentials(
    claude_client, monkeypatch, tmp_path, default_auth_exists, config_state
):
    config = tmp_path / "custom-claude"
    if config_state != "missing":
        config.mkdir()
    if config_state == "directory-entry":
        (config / ".credentials.json").mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    if default_auth_exists:
        default = Path.home() / ".claude"
        default.mkdir(parents=True)
        (default / ".credentials.json").touch()

    assert (claude_client.available() is False,) == (True,)

    def unexpected_cli(*_args, **_kwargs):
        pytest.fail("Missing configured auth must prevent launching the CLI")

    transport = sys.modules[type(claude_client).__module__]
    monkeypatch.setattr(transport.subprocess, "run", unexpected_cli)
    with pytest.raises(RuntimeError, match="claude subscription CLI/auth unavailable"):
        claude_client.invoke("fixture prompt")


@pytest.mark.parametrize("auth_exists", (False, True))
def test_claude_available_with_default_directory(claude_client, auth_exists):
    if auth_exists:
        default = Path.home() / ".claude"
        default.mkdir(parents=True)
        (default / ".credentials.json").touch()

    assert (claude_client.available() is auth_exists,) == (True,)
