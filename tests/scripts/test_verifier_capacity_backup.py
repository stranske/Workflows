"""The slot-3 capacity backup: stands in for one production judge whose budget is exhausted."""

from __future__ import annotations

import io
import json
from pathlib import Path

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


@pytest.fixture
def backup_on(monkeypatch):
    monkeypatch.setenv("MUSE_API_KEY", "test-key-not-real")
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


def test_backup_transport_posts_the_prompt_with_an_unredirected_key(monkeypatch):
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
    assert client.invoke("the prompt").content == '{"verdict":"PASS"}'
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
