"""The slot-3 capacity backup: stands in for one production judge whose budget is exhausted."""

from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts.langchain import pr_verifier as pv

ROOT = Path(__file__).resolve().parents[2]
ANTHROPIC_CAP = (
    "LLM invocation failed: Verifier input capacity blocked: Error code: 400 - {'type': 'error', "
    "'error': {'type': 'invalid_request_error', 'message': 'You have reached your specified API "
    "usage limits. You will regain access on 2026-11-01 at 00:00 UTC.'}}"
)


def judged(provider: str, model: str, verdict: str = "PASS", error: str | None = None):
    return pv.EvaluationResult(
        verdict=verdict, provider_used=provider, model=model, used_llm=error is None, error=error
    )


def runner():
    return pv.ComparisonRunner(context="ctx", diff=None, prompt="p", clients=[], coverage=None)


def assert_bundled_backup_never_invoked(calls) -> None:
    """The quota path must not send the review prompt to the bundled backup.

    ``ComparisonRunner.run_single`` catches every exception from the model call,
    including assertion failures. A check inside the invoke stub is swallowed, so
    the objective check has to inspect the recorded calls after comparison returns.
    """
    invoked = [client for client in calls if isinstance(client, pv.CapacityBackupClient)]
    assert invoked == [], "bundled backup must never be invoked"


@pytest.fixture
def backup_on(monkeypatch):
    monkeypatch.setenv("MUSE_API_KEY", "test-key-not-real")
    monkeypatch.delenv("LANGCHAIN_SLOT_CONFIG", raising=False)
    monkeypatch.delenv("VERIFIER_EVIDENCE_PROFILE", raising=False)
    monkeypatch.delenv("VERIFIER_SEMANTIC_MODE", raising=False)
    calls = []

    def run_single(self, client, provider, model):
        calls.append((type(client).__name__, provider, model))
        return judged(provider, model, "PASS")

    monkeypatch.setattr(pv.ComparisonRunner, "run_single", run_single)
    return calls


def test_the_real_anthropic_cap_message_and_openai_quota_count_as_exhausted():
    assert pv.capacity_exhausted(judged("anthropic", "m", "CONCERNS", ANTHROPIC_CAP))
    quota = "Error code: 429 - insufficient_quota: You exceeded your current quota"
    assert pv.capacity_exhausted(judged("openai", "m", "CONCERNS", quota))
    assert not pv.capacity_exhausted(judged("openai", "m", "CONCERNS", "Failed to parse JSON"))
    assert not pv.capacity_exhausted(judged("openai", "m", "PASS"))


def test_the_backup_stands_in_for_the_exhausted_judge_only(backup_on):
    results = [
        judged("openai", "gpt-6.1-sol", "PASS"),
        judged("anthropic", "claude-sonnet-5-5", "CONCERNS", ANTHROPIC_CAP),
    ]
    out = pv._with_capacity_backup(runner(), results, "application")
    assert backup_on == [("CapacityBackupClient", "muse-api", "muse-spark-1.3")]
    assert out[0] is results[0]
    assert (out[1].provider_used, out[1].model) == ("muse-api", "muse-spark-1.3")
    assert out[1].capacity_backup_for.startswith("anthropic/claude-sonnet-5-5: ")
    assert "usage limits" in out[1].capacity_backup_for
    assert pv.comparison_verdict(out) == "PASS"
    assert pv.comparison_verdict(results) != "PASS"


@pytest.mark.parametrize(
    "configuration",
    [
        "omitted",
        "disabled",
        "empty-file",
        "missing-file",
        "empty-env",
        "whitespace-env",
        "malformed",
        "non-object",
        "directory",
        "read-denied",
    ],
)
def test_explicit_slot_config_never_uses_bundled_backup(
    monkeypatch, tmp_path, backup_on, configuration
):
    payload = json.loads((ROOT / "config/llm_slots.json").read_text())
    if configuration == "disabled":
        payload["capacity_backup"]["enabled"] = False
    else:
        payload.pop("capacity_backup")
    path = tmp_path / "slots.json"
    if configuration == "directory":
        path.mkdir()
    elif configuration not in {"missing-file", "empty-env", "whitespace-env"}:
        contents = {
            "empty-file": "",
            "malformed": "{",
            "non-object": "[]",
        }.get(configuration, json.dumps(payload))
        path.write_text(contents, encoding="utf-8")
    setting = {"empty-env": "", "whitespace-env": "   "}.get(configuration, str(path))
    monkeypatch.setenv("LANGCHAIN_SLOT_CONFIG", setting)
    if configuration == "read-denied":
        read_text = Path.read_text

        def guarded_read_text(self, *args, **kwargs):
            if self == path:
                raise PermissionError("slot config is unreadable")
            return read_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", guarded_read_text)
    results = [
        judged("openai", "gpt-6.1-sol", "PASS"),
        judged("anthropic", "claude-sonnet-5-5", "CONCERNS", ANTHROPIC_CAP),
    ]

    out = pv._with_capacity_backup(runner(), results, "application")

    assert out is results
    assert backup_on == []
    assert pv.comparison_verdict(out) != "PASS"


@pytest.mark.parametrize(
    "configuration",
    [
        "omitted",
        "disabled",
        "disabled-null",
        "disabled-string-false",
        "disabled-string-true",
        "disabled-number",
        "disabled-absent",
        "empty-file",
        "missing-file",
        "empty-env",
        "whitespace-env",
        "malformed",
        "non-object",
        "invalid-encoding",
        "directory",
        "read-denied",
    ],
)
@pytest.mark.parametrize("exhausted_provider", ["openai", "anthropic"])
def test_compare_quota_failure_respects_explicit_slot_config(
    monkeypatch, tmp_path, configuration, exhausted_provider
):
    """The public comparison path must retain quota failures without calling a forbidden backup."""
    monkeypatch.delenv("VERIFIER_EVIDENCE_PROFILE", raising=False)
    monkeypatch.delenv("VERIFIER_SEMANTIC_MODE", raising=False)
    monkeypatch.delenv(pv.SIMULATE_CAPACITY_EXHAUSTED_ENV, raising=False)
    monkeypatch.setenv("MUSE_API_KEY", "test-key-not-real")
    path = tmp_path / "slots.json"
    payload = json.loads((ROOT / "config/llm_slots.json").read_text())
    if configuration == "disabled-absent":
        payload["capacity_backup"].pop("enabled")
    elif configuration.startswith("disabled"):
        payload["capacity_backup"]["enabled"] = {
            "disabled": False,
            "disabled-null": None,
            "disabled-string-false": "false",
            "disabled-string-true": "true",
            "disabled-number": 1,
        }[configuration]
    else:
        payload.pop("capacity_backup")
    if configuration == "directory":
        path.mkdir()
    elif configuration == "invalid-encoding":
        path.write_bytes(b"\xff")
    elif configuration not in {"missing-file", "empty-env", "whitespace-env"}:
        contents = {
            "empty-file": "",
            "malformed": "{",
            "non-object": "[]",
        }.get(configuration, json.dumps(payload))
        path.write_text(contents, encoding="utf-8")
    setting = {"empty-env": "", "whitespace-env": "   "}.get(configuration, str(path))
    monkeypatch.setenv("LANGCHAIN_SLOT_CONFIG", setting)
    if configuration == "read-denied":
        read_text = Path.read_text

        def guarded_read_text(self, *args, **kwargs):
            if self == path:
                raise PermissionError("slot config is unreadable")
            return read_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", guarded_read_text)
    clients = [(object(), "openai", "gpt-6.1-sol"), (object(), "anthropic", "claude-sonnet-5-5")]
    comparison = pv.ComparisonRunner(context="ctx", diff=None, prompt="p", clients=clients)
    monkeypatch.setattr(
        pv.ComparisonRunner, "from_environment", classmethod(lambda cls, *args: comparison)
    )
    calls = []

    def invoke(client, prompt, **kwargs):
        calls.append(client)
        if client is next(
            client for client, provider, _ in clients if provider == exhausted_provider
        ):
            raise RuntimeError("insufficient_quota")
        return SimpleNamespace(content='{"verdict":"PASS","summary":"ok"}'), None, None

    monkeypatch.setattr(pv, "_invoke_llm", invoke)

    results = pv.evaluate_pr_multiple("ctx")

    assert_bundled_backup_never_invoked(calls)
    assert calls == [client for client, _, _ in clients]
    assert [result.provider_used for result in results] == ["openai", "anthropic"]
    exhausted = next(result for result in results if result.provider_used == exhausted_provider)
    assert pv.capacity_exhausted(exhausted)
    surviving = next(result for result in results if result.provider_used != exhausted_provider)
    assert surviving.used_llm is True
    assert surviving.verdict == "PASS"
    assert all(result.capacity_backup_for is None for result in results)
    assert pv.comparison_verdict(results) != "PASS"


@pytest.mark.parametrize("exhausted_provider", ["openai", "anthropic"])
def test_quota_failure_with_omitted_explicit_backup_does_not_call_bundled_provider(
    monkeypatch, tmp_path, exhausted_provider
):
    """A file selected by LANGCHAIN_SLOT_CONFIG that omits capacity_backup is the allowlist.

    The bundled slot file still enables the Muse backup. A quota failure must read
    only the explicit file and must not send the review prompt to that bundled provider.
    """
    import urllib.request

    bundled_path = ROOT / "config" / "llm_slots.json"
    bundled = json.loads(bundled_path.read_text(encoding="utf-8"))
    assert bundled["capacity_backup"]["enabled"] is True
    assert bundled["capacity_backup"]["base_url"] == "https://api.meta.ai/v1"
    payload = json.loads(json.dumps(bundled))
    assert payload.pop("capacity_backup")["provider"] == "muse-api"
    path = tmp_path / "slots.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert "capacity_backup" not in json.loads(path.read_text(encoding="utf-8"))
    monkeypatch.delenv("VERIFIER_EVIDENCE_PROFILE", raising=False)
    monkeypatch.delenv("VERIFIER_SEMANTIC_MODE", raising=False)
    monkeypatch.delenv(pv.SIMULATE_CAPACITY_EXHAUSTED_ENV, raising=False)
    monkeypatch.setenv("MUSE_API_KEY", "test-key-not-real")
    monkeypatch.setenv("LANGCHAIN_SLOT_CONFIG", str(path))
    assert pv._slot_path() == path
    assert pv.capacity_backup() is None

    clients = [(object(), "openai", "gpt-6.1-sol"), (object(), "anthropic", "claude-sonnet-5-5")]
    comparison = pv.ComparisonRunner(context="ctx", diff=None, prompt="p", clients=clients)
    monkeypatch.setattr(
        pv.ComparisonRunner, "from_environment", classmethod(lambda cls, *args: comparison)
    )
    calls, requests, reads = [], [], []
    read_text = Path.read_text

    def tracking_read_text(self, *args, **kwargs):
        reads.append(self)
        return read_text(self, *args, **kwargs)

    def invoke(client, prompt, **kwargs):
        calls.append(client)
        if client is next(
            client for client, provider, _ in clients if provider == exhausted_provider
        ):
            raise RuntimeError("insufficient_quota")
        return SimpleNamespace(content='{"verdict":"PASS","summary":"ok"}'), None, None

    def urlopen(request, timeout):
        requests.append(request.full_url)
        return _Response(b'{"choices":[{"message":{"content":"{\\"verdict\\":\\"PASS\\"}"}}]}')

    monkeypatch.setattr(Path, "read_text", tracking_read_text)
    monkeypatch.setattr(pv, "_invoke_llm", invoke)
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)

    results = pv.evaluate_pr_multiple("ctx")

    assert_bundled_backup_never_invoked(calls)
    assert calls == [client for client, _, _ in clients]
    assert requests == []
    assert path in reads
    assert bundled_path not in reads
    assert not any(read.name == "llm_slots.json" for read in reads)
    exhausted = next(result for result in results if result.provider_used == exhausted_provider)
    assert pv.capacity_exhausted(exhausted)
    assert all(result.capacity_backup_for is None for result in results)
    assert pv.comparison_verdict(results) != "PASS"


def test_quota_failure_with_disabled_explicit_backup_does_not_call_bundled_provider(
    monkeypatch, tmp_path
):
    """A file selected by LANGCHAIN_SLOT_CONFIG with the backup disabled is the allowlist.

    The bundled slot file still enables the Muse backup. A quota failure must read the
    explicit file and must not send the review prompt to that bundled provider.
    """
    import urllib.request

    bundled_path = ROOT / "config" / "llm_slots.json"
    bundled = json.loads(bundled_path.read_text(encoding="utf-8"))
    assert bundled["capacity_backup"]["enabled"] is True
    assert bundled["capacity_backup"]["base_url"] == "https://api.meta.ai/v1"
    payload = json.loads(json.dumps(bundled))
    payload["capacity_backup"]["enabled"] = False
    path = tmp_path / "slots.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.delenv("VERIFIER_EVIDENCE_PROFILE", raising=False)
    monkeypatch.delenv("VERIFIER_SEMANTIC_MODE", raising=False)
    monkeypatch.delenv(pv.SIMULATE_CAPACITY_EXHAUSTED_ENV, raising=False)
    monkeypatch.setenv("MUSE_API_KEY", "test-key-not-real")
    monkeypatch.setenv("LANGCHAIN_SLOT_CONFIG", str(path))
    assert pv._slot_path() == path
    assert pv.capacity_backup() is None

    clients = [(object(), "openai", "gpt-6.1-sol"), (object(), "anthropic", "claude-sonnet-5-5")]
    comparison = pv.ComparisonRunner(context="ctx", diff=None, prompt="p", clients=clients)
    monkeypatch.setattr(
        pv.ComparisonRunner, "from_environment", classmethod(lambda cls, *args: comparison)
    )
    calls, requests, reads = [], [], []
    read_text = Path.read_text

    def tracking_read_text(self, *args, **kwargs):
        reads.append(self)
        return read_text(self, *args, **kwargs)

    def invoke(client, prompt, **kwargs):
        calls.append(client)
        if isinstance(client, pv.CapacityBackupClient):
            return client.invoke(prompt), None, None
        if client is clients[1][0]:
            raise RuntimeError("insufficient_quota")
        return SimpleNamespace(content='{"verdict":"PASS","summary":"ok"}'), None, None

    def urlopen(request, timeout):
        requests.append(request.full_url)
        return _Response(b'{"choices":[{"message":{"content":"{\\"verdict\\":\\"PASS\\"}"}}]}')

    monkeypatch.setattr(Path, "read_text", tracking_read_text)
    monkeypatch.setattr(pv, "_invoke_llm", invoke)
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)

    results = pv.evaluate_pr_multiple("ctx")

    assert_bundled_backup_never_invoked(calls)
    assert calls == [client for client, _, _ in clients]
    assert requests == []
    assert path in reads
    assert bundled_path not in reads
    assert [result.provider_used for result in results] == ["openai", "anthropic"]
    assert pv.capacity_exhausted(results[1])
    assert all(result.capacity_backup_for is None for result in results)
    assert pv.comparison_verdict(results) != "PASS"


@pytest.mark.parametrize(
    "backup_block",
    [
        pytest.param({}, id="empty-block"),
        pytest.param(None, id="null-block"),
        pytest.param({"enabled": True}, id="enabled-without-fields"),
        pytest.param(
            {
                "enabled": True,
                "provider": "muse-api",
                "model": "muse-spark-1.3",
                "key_env": "MUSE_API_KEY",
            },
            id="bundled-identity-without-base-url",
        ),
        pytest.param(
            {
                "enabled": True,
                "provider": "muse-api",
                "model": "muse-spark-1.3",
                "base_url": "https://api.meta.ai/v1",
            },
            id="bundled-url-without-key-env",
        ),
    ],
)
@pytest.mark.parametrize("exhausted_provider", ["openai", "anthropic"])
def test_quota_failure_on_explicit_file_with_backup_block_does_not_call_bundled_provider(
    monkeypatch, tmp_path, backup_block, exhausted_provider
):
    """LANGCHAIN_SLOT_CONFIG selects a file that includes a capacity_backup block.

    A block that is empty, null, or only partly filled must not be completed from
    the bundled slot file. A quota failure must not call the bundled Muse provider.
    """
    import urllib.request

    bundled_path = ROOT / "config" / "llm_slots.json"
    bundled = json.loads(bundled_path.read_text(encoding="utf-8"))
    assert bundled["capacity_backup"]["enabled"] is True
    assert bundled["capacity_backup"]["provider"] == "muse-api"
    assert bundled["capacity_backup"]["base_url"] == "https://api.meta.ai/v1"
    payload = json.loads(json.dumps(bundled))
    payload["capacity_backup"] = backup_block
    path = tmp_path / "slots.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.delenv("VERIFIER_EVIDENCE_PROFILE", raising=False)
    monkeypatch.delenv("VERIFIER_SEMANTIC_MODE", raising=False)
    monkeypatch.delenv(pv.SIMULATE_CAPACITY_EXHAUSTED_ENV, raising=False)
    monkeypatch.setenv("MUSE_API_KEY", "test-key-not-real")
    monkeypatch.setenv("LANGCHAIN_SLOT_CONFIG", str(path))
    assert pv._slot_path() == path
    assert pv.capacity_backup() is None

    clients = [(object(), "openai", "gpt-6.1-sol"), (object(), "anthropic", "claude-sonnet-5-5")]
    comparison = pv.ComparisonRunner(context="ctx", diff=None, prompt="p", clients=clients)
    monkeypatch.setattr(
        pv.ComparisonRunner, "from_environment", classmethod(lambda cls, *args: comparison)
    )
    calls, requests, reads = [], [], []
    read_text = Path.read_text

    def tracking_read_text(self, *args, **kwargs):
        reads.append(self)
        return read_text(self, *args, **kwargs)

    def invoke(client, prompt, **kwargs):
        calls.append(client)
        if client is next(
            client for client, provider, _ in clients if provider == exhausted_provider
        ):
            raise RuntimeError("insufficient_quota")
        return SimpleNamespace(content='{"verdict":"PASS","summary":"ok"}'), None, None

    def urlopen(request, timeout):
        requests.append(request.full_url)
        return _Response(b'{"choices":[{"message":{"content":"{\\"verdict\\":\\"PASS\\"}"}}]}')

    monkeypatch.setattr(Path, "read_text", tracking_read_text)
    monkeypatch.setattr(pv, "_invoke_llm", invoke)
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)

    results = pv.evaluate_pr_multiple("ctx")

    assert_bundled_backup_never_invoked(calls)
    assert calls == [client for client, _, _ in clients]
    assert requests == []
    assert path in reads
    assert bundled_path not in reads
    exhausted = next(result for result in results if result.provider_used == exhausted_provider)
    assert pv.capacity_exhausted(exhausted)
    assert all(result.capacity_backup_for is None for result in results)
    assert pv.comparison_verdict(results) != "PASS"


@pytest.mark.parametrize("configuration", ["empty-file", "missing-file"])
@pytest.mark.parametrize("exhausted_provider", ["openai", "anthropic"])
def test_quota_failure_with_empty_or_missing_explicit_slot_config_does_not_fall_back(
    monkeypatch, tmp_path, configuration, exhausted_provider
):
    """An empty or missing file selected by LANGCHAIN_SLOT_CONFIG is the allowlist.

    The bundled slot file still enables the Muse backup. When that explicit file
    is empty or absent, a quota failure must not read the bundled file or send
    the review prompt to the bundled backup provider.
    """
    import urllib.request

    bundled_path = ROOT / "config" / "llm_slots.json"
    bundled = json.loads(bundled_path.read_text(encoding="utf-8"))
    assert bundled["capacity_backup"]["enabled"] is True
    assert bundled["capacity_backup"]["provider"] == "muse-api"
    assert bundled["capacity_backup"]["base_url"] == "https://api.meta.ai/v1"
    path = tmp_path / "slots.json"
    if configuration == "empty-file":
        path.write_text("", encoding="utf-8")
    else:
        assert not path.exists()
    monkeypatch.delenv("VERIFIER_EVIDENCE_PROFILE", raising=False)
    monkeypatch.delenv("VERIFIER_SEMANTIC_MODE", raising=False)
    monkeypatch.delenv(pv.SIMULATE_CAPACITY_EXHAUSTED_ENV, raising=False)
    monkeypatch.setenv("MUSE_API_KEY", "test-key-not-real")
    monkeypatch.setenv("LANGCHAIN_SLOT_CONFIG", str(path))
    assert pv._slot_path() == path
    assert pv.capacity_backup() is None

    clients = [(object(), "openai", "gpt-6.1-sol"), (object(), "anthropic", "claude-sonnet-5-5")]
    comparison = pv.ComparisonRunner(context="ctx", diff=None, prompt="p", clients=clients)
    monkeypatch.setattr(
        pv.ComparisonRunner, "from_environment", classmethod(lambda cls, *args: comparison)
    )
    calls, requests, reads = [], [], []
    read_text = Path.read_text

    def tracking_read_text(self, *args, **kwargs):
        reads.append(self)
        return read_text(self, *args, **kwargs)

    def invoke(client, prompt, **kwargs):
        calls.append(client)
        if client is next(
            client for client, provider, _ in clients if provider == exhausted_provider
        ):
            raise RuntimeError("insufficient_quota")
        return SimpleNamespace(content='{"verdict":"PASS","summary":"ok"}'), None, None

    def urlopen(request, timeout):
        requests.append(request.full_url)
        return _Response(b'{"choices":[{"message":{"content":"{\\"verdict\\":\\"PASS\\"}"}}]}')

    monkeypatch.setattr(Path, "read_text", tracking_read_text)
    monkeypatch.setattr(pv, "_invoke_llm", invoke)
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)

    results = pv.evaluate_pr_multiple("ctx")

    assert_bundled_backup_never_invoked(calls)
    assert calls == [client for client, _, _ in clients]
    assert requests == []
    assert bundled_path not in reads
    assert not any(read.name == "llm_slots.json" for read in reads)
    if configuration == "empty-file":
        assert path in reads
    exhausted = next(result for result in results if result.provider_used == exhausted_provider)
    assert pv.capacity_exhausted(exhausted)
    assert all(result.capacity_backup_for is None for result in results)
    assert pv.comparison_verdict(results) != "PASS"


def test_explicit_slot_config_selects_its_own_backup(monkeypatch, tmp_path, backup_on):
    payload = json.loads((ROOT / "config/llm_slots.json").read_text())
    payload["capacity_backup"].update(
        provider="configured-provider",
        model="configured-model",
        base_url="https://backup.example.invalid/v1",
    )
    path = tmp_path / "slots.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LANGCHAIN_SLOT_CONFIG", "  slots.json  ")
    backup = pv.capacity_backup()
    assert backup is not None
    assert backup[0].base_url == "https://backup.example.invalid/v1"
    results = [
        judged("openai", "gpt-6.1-sol", "PASS"),
        judged("anthropic", "claude-sonnet-5-5", "CONCERNS", ANTHROPIC_CAP),
    ]

    out = pv._with_capacity_backup(runner(), results, "application")

    assert backup_on == [("CapacityBackupClient", "configured-provider", "configured-model")]
    assert out[0] is results[0]
    assert out[1].capacity_backup_for.startswith("anthropic/claude-sonnet-5-5: ")
    assert pv.comparison_verdict(out) == "PASS"


@pytest.mark.parametrize("exhausted_provider", ["openai", "anthropic"])
@pytest.mark.parametrize("key_available", [True, False])
def test_compare_quota_failure_uses_only_the_configured_backup_transport(
    monkeypatch, tmp_path, exhausted_provider, key_available
):
    import urllib.request

    monkeypatch.delenv("VERIFIER_EVIDENCE_PROFILE", raising=False)
    monkeypatch.delenv("VERIFIER_SEMANTIC_MODE", raising=False)
    monkeypatch.delenv(pv.SIMULATE_CAPACITY_EXHAUSTED_ENV, raising=False)
    monkeypatch.setenv("MUSE_API_KEY", "test-key-not-real")
    if key_available:
        monkeypatch.setenv("CONFIGURED_BACKUP_KEY", "test-key-not-real")
    else:
        monkeypatch.delenv("CONFIGURED_BACKUP_KEY", raising=False)
    payload = json.loads((ROOT / "config/llm_slots.json").read_text())
    payload["capacity_backup"].update(
        provider="configured-provider",
        model="configured-model",
        base_url="https://backup.example.invalid/v1",
        key_env="CONFIGURED_BACKUP_KEY",
    )
    (tmp_path / "slots.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LANGCHAIN_SLOT_CONFIG", "  slots.json  ")
    clients = [(object(), "openai", "gpt-6.1-sol"), (object(), "anthropic", "claude-sonnet-5-5")]
    comparison = pv.ComparisonRunner(context="ctx", diff=None, prompt="p", clients=clients)
    monkeypatch.setattr(
        pv.ComparisonRunner, "from_environment", classmethod(lambda cls, *args: comparison)
    )
    calls, requests = [], []

    def invoke(client, prompt, **kwargs):
        calls.append(client)
        if isinstance(client, pv.CapacityBackupClient):
            return client.invoke(prompt), None, None
        if client is next(
            client for client, provider, _ in clients if provider == exhausted_provider
        ):
            raise RuntimeError("insufficient_quota")
        return SimpleNamespace(content='{"verdict":"PASS","summary":"ok"}'), None, None

    def urlopen(request, timeout):
        requests.append((request.full_url, json.loads(request.data)))
        return _Response(b'{"choices":[{"message":{"content":"{\\"verdict\\":\\"PASS\\"}"}}]}')

    monkeypatch.setattr(pv, "_invoke_llm", invoke)
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)

    results = pv.evaluate_pr_multiple("ctx")

    assert calls[:2] == [client for client, _, _ in clients]
    replaced_index = next(
        i for i, (_, provider, _) in enumerate(clients) if provider == exhausted_provider
    )
    assert results[1 - replaced_index].provider_used == clients[1 - replaced_index][1]
    if key_available:
        assert len(calls) == 3
        assert calls[-1].key_env == "CONFIGURED_BACKUP_KEY"
        assert requests == [
            (
                "https://backup.example.invalid/v1/chat/completions",
                {"model": "configured-model", "messages": [{"role": "user", "content": "p"}]},
            )
        ]
        assert results[replaced_index].provider_used == "configured-provider"
        assert results[replaced_index].model == "configured-model"
        assert results[replaced_index].capacity_backup_for.startswith(f"{exhausted_provider}/")
        assert pv.comparison_verdict(results) == "PASS"
    else:
        assert len(calls) == 2
        assert requests == []
        assert pv.capacity_exhausted(results[replaced_index])
        assert all(result.capacity_backup_for is None for result in results)
        assert pv.comparison_verdict(results) != "PASS"


def test_both_judges_exhausted_means_no_backup_and_no_pass(backup_on):
    results = [
        judged("openai", "gpt-6.1-sol", "CONCERNS", "insufficient_quota"),
        judged("anthropic", "claude-sonnet-5-5", "CONCERNS", ANTHROPIC_CAP),
    ]
    assert pv._with_capacity_backup(runner(), results, None) == results
    assert backup_on == []
    assert pv.comparison_verdict(results) != "PASS"


def test_a_surviving_fail_still_decides(backup_on):
    results = [
        judged("openai", "gpt-6.1-sol", "FAIL"),
        judged("anthropic", "claude-sonnet-5-5", "CONCERNS", ANTHROPIC_CAP),
    ]
    assert pv.comparison_verdict(pv._with_capacity_backup(runner(), results, None)) == "FAIL"


def test_no_backup_on_an_ordinary_error(backup_on):
    results = [
        judged("openai", "gpt-6.1-sol", "PASS"),
        judged("anthropic", "claude-sonnet-5-5", "CONCERNS", "Failed to parse JSON response"),
    ]
    assert pv._with_capacity_backup(runner(), results, None) == results
    assert backup_on == []


def test_strict_paths_and_a_missing_key_never_use_the_backup(monkeypatch):
    monkeypatch.setenv("MUSE_API_KEY", "test-key-not-real")
    monkeypatch.delenv("LANGCHAIN_SLOT_CONFIG", raising=False)
    monkeypatch.delenv("VERIFIER_SEMANTIC_MODE", raising=False)
    monkeypatch.delenv("VERIFIER_EVIDENCE_PROFILE", raising=False)
    assert pv.capacity_backup() is not None
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    assert pv.capacity_backup() is None
    monkeypatch.delenv("VERIFIER_EVIDENCE_PROFILE")
    monkeypatch.setenv("VERIFIER_SEMANTIC_MODE", "1")
    assert pv.capacity_backup() is None
    monkeypatch.delenv("VERIFIER_SEMANTIC_MODE")
    monkeypatch.delenv("MUSE_API_KEY")
    assert pv.capacity_backup() is None


def test_the_backup_client_takes_the_standard_legacy_capacity_route_only(monkeypatch):
    client = pv.CapacityBackupClient(model="m", base_url="https://example.invalid/v1", key_env="K")
    monkeypatch.delenv("VERIFIER_EVIDENCE_PROFILE", raising=False)
    assert pv._legacy_capacity_route(client) is True
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    assert pv._legacy_capacity_route(client) is False


def test_the_simulated_canary_exhausts_only_the_named_judge(monkeypatch, backup_on):
    monkeypatch.setenv(pv.SIMULATE_CAPACITY_EXHAUSTED_ENV, "anthropic")
    fake = pv.ComparisonRunner(
        context="ctx",
        diff=None,
        prompt="p",
        clients=[(object(), "openai", "gpt-6.1-sol"), (object(), "anthropic", "claude-sonnet-5-5")],
        coverage=None,
    )
    monkeypatch.setattr(pv.ComparisonRunner, "from_environment", classmethod(lambda cls, *a: fake))
    monkeypatch.setattr(pv, "_validate_comparison_clients", lambda clients: (True, ""))
    out = pv.evaluate_pr_multiple("ctx", None)
    assert [r.provider_used for r in out] == ["openai", "muse-api"]
    assert ("object", "anthropic", "claude-sonnet-5-5") not in backup_on


def test_the_shipped_config_declares_the_muse_backup_in_slot_3():
    for path in ("config/llm_slots.json", "templates/consumer-repo/config/llm_slots.json"):
        block = json.loads((ROOT / path).read_text())["capacity_backup"]
        assert (block["slot"], block["provider"], block["model"], block["enabled"]) == (
            "slot3",
            "muse-api",
            "muse-spark-1.3",
            True,
        )


def test_a_partly_reviewed_judge_that_found_a_defect_is_never_replaced(backup_on):
    # A chunked review that found a defect and then hit its cap keeps its finding: replacing it
    # with a backup PASS would turn the comparison from FAIL into PASS.
    finding = judged("anthropic", "claude-sonnet-5-5", "FAIL")
    capped = judged("anthropic", "claude-sonnet-5-5", "UNVERIFIABLE_INPUT", ANTHROPIC_CAP)
    partial = judged("anthropic", "claude-sonnet-5-5", "FAIL", ANTHROPIC_CAP)
    partial.used_llm = False
    partial.chunk_reviews = [
        {"result": finding.model_dump(mode="json")},
        {"result": capped.model_dump(mode="json")},
    ]
    results = [judged("openai", "gpt-6.1-sol"), partial]
    assert not pv.capacity_exhausted(partial)
    assert pv._with_capacity_backup(runner(), results, None) == results
    assert backup_on == []


class _Response:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.body


@pytest.mark.parametrize("config", [None, {}, {"tags": ["arg002-regression"]}])
def test_backup_transport_posts_the_prompt_with_an_unredirected_key(monkeypatch, config):
    import urllib.request

    monkeypatch.setenv("MUSE_API_KEY", "test-key-not-real")
    sent = {}

    def urlopen(request, timeout):
        sent.update(
            url=request.full_url,
            method=request.get_method(),
            body=json.loads(request.data),
            redirected_headers=dict(request.headers),
            auth=request.unredirected_hdrs.get("Authorization"),
        )
        return _Response(b'{"choices":[{"message":{"content":"{\\"verdict\\":\\"PASS\\"}"}}]}')

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    client = pv.CapacityBackupClient(
        model="muse-spark-1.3", base_url="https://api.meta.ai/v1/", key_env="MUSE_API_KEY"
    )
    assert client.invoke("the prompt", config=config).content == '{"verdict":"PASS"}'
    assert sent["url"] == "https://api.meta.ai/v1/chat/completions"
    assert sent["method"] == "POST"
    assert sent["body"] == {
        "model": "muse-spark-1.3",
        "messages": [{"role": "user", "content": "the prompt"}],
    }
    assert sent["auth"] == "Bearer test-key-not-real"
    assert "Authorization" not in sent["redirected_headers"]


@pytest.mark.parametrize(
    "failure, message",
    [
        ("http", "capacity backup HTTP 429"),
        ("transport", "capacity backup unavailable: URLError"),
        ("body", "capacity backup returned an unexpected body"),
    ],
)
def test_backup_transport_failures_never_carry_the_key(monkeypatch, failure, message):
    import urllib.error
    import urllib.request

    monkeypatch.setenv("MUSE_API_KEY", "test-key-not-real")

    raised_errors = []

    def urlopen(request, timeout):
        if failure == "http":
            error = urllib.error.HTTPError(
                request.full_url, 429, "test-key-not-real", {}, io.BytesIO(b"quota")
            )
            raised_errors.append(error)
            raise error
        if failure == "transport":
            raise urllib.error.URLError("test-key-not-real")
        return _Response(b"{}")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    client = pv.CapacityBackupClient(
        model="m", base_url="https://api.meta.ai/v1", key_env="MUSE_API_KEY"
    )
    with pytest.raises(RuntimeError) as raised:
        client.invoke("p")
    assert str(raised.value) == message
    assert "test-key-not-real" not in str(raised.value)
    # the HTTP error owns the response body; the client closes it rather than leaking it
    assert all(error.fp.closed for error in raised_errors)


def test_backup_transport_refuses_a_non_https_base_url(monkeypatch):
    monkeypatch.setenv("MUSE_API_KEY", "test-key-not-real")
    client = pv.CapacityBackupClient(model="m", base_url="file:///etc", key_env="MUSE_API_KEY")
    with pytest.raises(RuntimeError, match="must be https"):
        client.invoke("p")


# ---------------------------------------------------------------- the ordered backup chain


@pytest.fixture
def chain_keys(monkeypatch):
    monkeypatch.setenv("MUSE_API_KEY", "test-key-not-real")
    monkeypatch.setenv("VERIFIER_GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("CURSOR_API_KEY", "test-key-not-real")
    monkeypatch.delenv("LANGCHAIN_SLOT_CONFIG", raising=False)
    monkeypatch.delenv("VERIFIER_EVIDENCE_PROFILE", raising=False)
    monkeypatch.delenv("VERIFIER_SEMANTIC_MODE", raising=False)
    monkeypatch.setattr(pv.CursorCliBackupClient, "available", lambda self: True)


def test_the_shipped_chain_is_muse_then_gemini_carbon_then_cursor(chain_keys):
    order = [(provider, model) for _, provider, model in pv.capacity_backups()]
    assert order == [
        ("muse-api", "muse-spark-1.3"),
        ("gemini-api", "gemini-4-carbon"),
        ("cursor-cli", "composer-2.5"),
    ]
    gemini = pv.capacity_backups()[1][0]
    # Its own secret name, so hosted Gemini implementation (GEMINI_API_KEY) never reads it.
    assert gemini.key_env == "VERIFIER_GEMINI_API_KEY"
    shipped = json.loads((ROOT / "config/llm_slots.json").read_text())
    template = json.loads((ROOT / "templates/consumer-repo/config/llm_slots.json").read_text())
    assert shipped["capacity_backup_chain"] == template["capacity_backup_chain"]


def test_a_failed_backup_falls_through_to_the_next_one(monkeypatch, chain_keys):
    calls = []

    def run_single(self, client, provider, model):
        calls.append(provider)
        if provider == "muse-api":
            return judged(provider, model, "CONCERNS", "capacity backup HTTP 429")
        return judged(provider, model, "PASS")

    monkeypatch.setattr(pv.ComparisonRunner, "run_single", run_single)
    results = [
        judged("openai", "gpt-6.1-sol", "PASS"),
        judged("anthropic", "claude-sonnet-5-5", "CONCERNS", ANTHROPIC_CAP),
    ]
    out = pv._with_capacity_backup(runner(), results, "application")
    assert calls == ["muse-api", "gemini-api"]
    assert (out[1].provider_used, out[1].model) == ("gemini-api", "gemini-4-carbon")
    assert out[1].capacity_backup_for.startswith("anthropic/claude-sonnet-5-5: ")
    assert "earlier backups failed: muse-api/muse-spark-1.3: capacity backup HTTP 429" in (
        out[1].capacity_backup_for
    )
    assert pv.comparison_verdict(out) == "PASS"


def test_when_every_backup_fails_the_last_failure_stands_and_nothing_passes(
    monkeypatch, chain_keys
):
    monkeypatch.setattr(
        pv.ComparisonRunner,
        "run_single",
        lambda self, c, provider, model: judged(provider, model, "CONCERNS", "unavailable"),
    )
    results = [
        judged("openai", "gpt-6.1-sol", "PASS"),
        judged("anthropic", "claude-sonnet-5-5", "CONCERNS", ANTHROPIC_CAP),
    ]
    out = pv._with_capacity_backup(runner(), results, "application")
    assert out[1].provider_used == "cursor-cli"
    assert pv.comparison_verdict(out) != "PASS"


def test_unkeyed_or_uninstalled_backups_are_skipped(monkeypatch, chain_keys):
    monkeypatch.delenv("VERIFIER_GEMINI_API_KEY")
    monkeypatch.setenv("GEMINI_API_KEY", "the-implementation-key-must-not-be-used")
    monkeypatch.setattr(pv.CursorCliBackupClient, "available", lambda self: False)
    assert [p for _, p, _ in pv.capacity_backups()] == ["muse-api"]


def test_the_strict_paths_use_no_backup_chain(monkeypatch, chain_keys):
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    assert pv.capacity_backups() == []


def test_cursor_answer_keeps_only_the_verdict_object():
    text = 'I will evaluate the diff now.\n{"note": 1}\n{"verdict": "PASS", "scores": {"a": 1}}'
    assert pv.last_verdict_object_text(text) == '{"verdict": "PASS", "scores": {"a": 1}}'
    assert pv.last_verdict_object_text("no json here") == "no json here"


def test_cursor_backup_runs_read_only_with_a_minimal_environment(monkeypatch, chain_keys):
    import subprocess

    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"], seen["env"], seen["input"] = command, kwargs["env"], kwargs["input"]
        body = {"result": 'Reviewing.\n{"verdict": "CONCERNS"}', "is_error": False}
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(body), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    answer = pv.CursorCliBackupClient(model="composer-2.5").invoke("the prompt")
    assert answer.content == '{"verdict": "CONCERNS"}'
    assert seen["command"][:6] == ["cursor-agent", "-p", "--output-format", "json", "--mode", "ask"]
    assert seen["command"][-2:] == ["--model", "composer-2.5"]
    assert seen["input"] == "the prompt"
    assert "OPENAI_API_KEY" not in seen["env"]
    assert seen["env"]["CURSOR_API_KEY"] == "test-key-not-real"


def test_cursor_backup_errors_never_carry_the_key(monkeypatch, chain_keys):
    import subprocess

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kw: subprocess.CompletedProcess(command, 3, stdout="oops", stderr=""),
    )
    with pytest.raises(RuntimeError) as caught:
        pv.CursorCliBackupClient(model="composer-2.5").invoke("p")
    assert "test-key-not-real" not in str(caught.value)
