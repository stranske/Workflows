"""Read-only subscription CLI transport for keepalive auxiliary analysis.

Opt-in only. Missing CLI/auth or failed execution never falls back to an API.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

MODE_ENV = "WORKFLOWS_ANALYSIS_CLI"
REGISTRY = Path(__file__).resolve().parents[1] / ".github/agents/registry.yml"

# Disable analysis capabilities explicitly: read-only sandbox alone permits
# credential reads. Deployment still needs effective-tool and canary evidence.
# unified_exec opt-outs are ignored; shell_tool controls command execution.
_CODEX_DISABLED_FEATURES = (
    "shell_tool",
    "view_image",
    "multi_agent",
    "multi_agent_v2",
    "plugins",
    "hooks",
    "code_mode_host",
    "browser_use",
    "in_app_browser",
    "apps",
    "computer_use",
    "skill_search",
)


def analysis_model(agent: str) -> str:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    profile = registry["subscription_analysis"][agent]
    if "execution_profile" in profile:
        return str(registry["execution_profiles"][profile["execution_profile"]]["model"])
    return str(profile["model"])


def _has_subscription_auth(agent: str) -> bool:
    if agent == "claude":
        return (
            bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))
            or (Path.home() / ".claude/.credentials.json").is_file()
        )
    home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    try:
        auth = json.loads((home / "auth.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return auth.get("auth_mode") == "chatgpt" and bool(
        (auth.get("tokens") or {}).get("access_token")
    )


@dataclass(frozen=True)
class SubscriptionClient:
    agent: str
    model: str

    def available(self) -> bool:
        return bool(shutil.which(self.agent)) and _has_subscription_auth(self.agent)

    def invoke(self, prompt: str, **_kwargs: Any) -> SimpleNamespace:
        if not self.available():
            raise RuntimeError(f"{self.agent} subscription CLI/auth unavailable")
        # Do not pass GitHub, tracing, API-provider or other job credentials to
        # the analysis child. Subscription auth stays in the existing CLI store.
        allowed = {"PATH", "HOME", "TMPDIR", "TEMP", "SYSTEMROOT", "NO_COLOR"}
        allowed.update(
            {"CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CONFIG_DIR"}
            if self.agent == "claude"
            else {"CODEX_HOME"}
        )
        env = {key: value for key, value in os.environ.items() if key in allowed}
        if self.agent == "codex":
            command = [
                "codex",
                "exec",
                "--json",
                "--ignore-user-config",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--model",
                self.model,
                "-c",
                'approval_policy="never"',
                "-c",
                'forced_login_method="chatgpt"',
                "-c",
                'model_reasoning_effort="low"',
                "-c",
                'web_search="disabled"',
            ]
            for feature in _CODEX_DISABLED_FEATURES:
                command.extend(["--disable", feature])
            command.append("-")
        elif self.agent == "claude":
            command = [
                "claude",
                "-p",
                "--model",
                self.model,
                "--output-format",
                "json",
                "--tools",
                "",
                "--strict-mcp-config",
                "--mcp-config",
                '{"mcpServers":{}}',
                "--setting-sources",
                "",
                "--no-session-persistence",
            ]
        else:
            raise ValueError("Unsupported subscription analysis agent")
        # Empty cwd limits workspace discovery; it does not deny absolute-path reads.
        # Prompt input is stdin-only. Capability controls above require runtime proof.
        with tempfile.TemporaryDirectory(prefix="workflows-analysis-") as scratch:
            result = subprocess.run(
                command,
                input=prompt,
                capture_output=True,
                text=True,
                env=env,
                cwd=scratch,
                timeout=90,
                check=False,
            )
        if result.returncode:
            raise RuntimeError(f"{self.agent} analysis CLI exited {result.returncode}")
        if self.agent == "claude":
            data = json.loads(result.stdout)
            if data.get("is_error"):
                raise RuntimeError("Claude analysis returned an error")
            content = data.get("result")
        else:
            messages = []
            for line in result.stdout.splitlines():
                event = json.loads(line)
                item = event.get("item") or {}
                if event.get("type") == "item.completed" and item.get("type") == "agent_message":
                    messages.append(item.get("text"))
            content = messages[-1] if messages else None
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Subscription analysis returned no final message")
        return SimpleNamespace(content=content)


def build_subscription_client() -> SimpleNamespace | None:
    agent = os.environ.get(MODE_ENV, "")
    if agent not in {"codex", "claude"}:
        raise ValueError("Subscription analysis mode must name codex or claude")
    client = SubscriptionClient(agent=agent, model=analysis_model(agent))
    if not client.available():
        raise RuntimeError("Subscription analysis CLI/auth unavailable; no API fallback")
    return SimpleNamespace(client=client, provider=agent, provider_label=agent, model=client.model)
