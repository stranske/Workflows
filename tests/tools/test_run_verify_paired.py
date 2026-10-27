"""Inert causal coverage of the real compare CLI and native policy boundaries."""

from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stdout
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from scripts.langchain import pr_verifier as verifier
from tools import langchain_client
from tools import run_verify_paired as runner
from tools import verify_paired_policy as policy


@pytest.fixture
def enabled(monkeypatch, tmp_path):
    proposal, caps = runner.load_packet()
    caps.update(execution_enabled=True, review_status="reviewed")
    monkeypatch.setattr(runner, "load_packet", lambda: (proposal, deepcopy(caps)))
    monkeypatch.setattr(policy, "load_packet", lambda: (proposal, deepcopy(caps)))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "offline-openai-placeholder")
    monkeypatch.setenv("CLAUDE_API_STRANSKE", "offline-anthropic-placeholder")
    return caps


@pytest.fixture
def native(monkeypatch):
    openai = pytest.importorskip("langchain_openai").ChatOpenAI
    anthropic = pytest.importorskip("langchain_anthropic").ChatAnthropic
    calls = []
    original = langchain_client.build_chat_clients

    def build(**kwargs):
        assert kwargs["timeout"] == 30
        assert kwargs["max_retries"] == 0
        clients = original(**kwargs)
        assert len(clients) == 2
        for item in clients:
            sdk = item.client.root_client if item.provider == "openai" else item.client._client
            assert sdk.max_retries == 0 and sdk.timeout == 30

            def count(*, _provider=item.provider, **payload):
                calls.append(("count", _provider, payload))
                return SimpleNamespace(input_tokens=1000)

            if item.provider == "openai":
                monkeypatch.setattr(sdk.responses.input_tokens, "count", count)
            else:
                monkeypatch.setattr(sdk.messages, "count_tokens", count)

                def metadata(model):
                    calls.append(("metadata", "anthropic", model))
                    return SimpleNamespace(id=model, max_input_tokens=1000000, max_tokens=128000)

                monkeypatch.setattr(sdk.models, "retrieve", metadata)
        return clients

    def invoke(client, prompt, **kwargs):
        payload = client._get_request_payload(prompt)
        provider = "openai" if isinstance(client, openai) else "anthropic"
        calls.append(("generation", provider, payload))
        assert payload.get("max_output_tokens", payload.get("max_tokens")) == 4096
        assert "precommitted-semantic-oracle" not in prompt
        assert "No execution or CI result is supplied or claimed" in prompt
        raw = (
            '{"verdict":"CONCERNS","concerns":["abs(value) is not square: -3 gives 3, not 9"],'
            '"summary":"Arithmetic defect"}'
            if "+    return abs(value)" in prompt
            else '{"verdict":"PASS","concerns":[],"summary":"Complete source square meets specification"}'
        )
        return SimpleNamespace(content=raw)

    monkeypatch.setattr(langchain_client, "build_chat_clients", build)
    monkeypatch.setattr(openai, "invoke", invoke)
    monkeypatch.setattr(anthropic, "invoke", invoke)
    return calls


def inline_cli(monkeypatch):
    def run(argv, *, cwd, env, stdout, stderr, timeout, check):
        assert argv[1] == str(runner.ROOT / "scripts/langchain/pr_verifier.py")
        assert "--compare" in argv and "--create-issue" not in argv
        assert "GITHUB_TOKEN" not in env and "CODEX_AUTH_JSON" not in env
        assert 0 < timeout <= 300
        text = io.StringIO()
        with (
            patch.dict(os.environ, env, clear=True),
            patch("sys.argv", argv[1:]),
            redirect_stdout(text),
        ):
            verifier.main()
        stdout.write(text.getvalue().encode())
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", run)


def test_actual_two_case_cli_four_generations_eight_counts_six_metadata(
    enabled, native, monkeypatch, tmp_path
):
    inline_cli(monkeypatch)
    result = runner.run(execute=True)
    assert result["status"] == "completed_screen_only", result
    assert [
        sum(call[0] == kind for call in native) for kind in ("generation", "count", "metadata")
    ] == [4, 8, 6]
    assert not (tmp_path / "verify-paired/.semantic-key").exists()
    for case, expected in (("square-pass", "PASS"), ("square-nonpass", "CONCERNS")):
        report = json.loads((tmp_path / "verify-paired" / case / "comparison.json").read_text())
        assert [arm["verdict"] for arm in report["results"]] == [expected, expected]
        trial = report["semantic_acceptance"]["qualification_trial"]
        assert trial["attempted_native_requests"] == {"count": 4, "generation": 2, "metadata": 3}
        assert trial["native_capacity_claim"] is False
        assert trial["role_qualification_claim"] is False
        original = json.loads((runner.PACKET / case / "capture.json").read_text())
        assert report["semantic_acceptance"]["capture"] == original
        assert all(arm["raw_content"] for arm in report["results"])


def test_source_proposed_policy_holds_before_subprocess(monkeypatch, tmp_path):
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setattr(
        runner.subprocess, "run", lambda *a, **kw: pytest.fail("provider-capable child")
    )
    result = runner.run(execute=True)
    assert result["status"] == "held"
    assert result["semantic_cli_started"] is False
    assert result["native_request_state"] == "not_started"
    assert not (tmp_path / "verify-paired/.semantic-key").exists()


@pytest.mark.parametrize("kind,limit", [("generation", 2), ("count", 4), ("metadata", 3)])
def test_request_budget_counts_attempts_and_never_repeats(enabled, kind, limit):
    trial = policy.PairedTrial("square-pass", enabled, float("inf"))
    for _ in range(limit):
        trial.consume(kind)
    with pytest.raises(ValueError, match="request policy exhausted"):
        trial.consume(kind)
    assert trial.calls[kind] == limit


@pytest.mark.parametrize(
    "defect", ["capture", "prompt", "model", "packages", "slots", "provider", "registry-path"]
)
def test_mismatch_stops_before_client_construction(enabled, monkeypatch, tmp_path, defect):
    case = "square-pass"
    directory = runner.PACKET / case
    key = tmp_path / "key"
    key.write_bytes(b"k" * 32)
    env = runner.child_environment(case, directory, key)
    context = (directory / "context.md").read_text()
    diff = (directory / "diff.patch").read_text()
    if defect == "capture":
        diff += "\n"
    elif defect == "prompt":
        monkeypatch.setattr(verifier, "_load_prompt", lambda: "changed {context} {diff}")
    elif defect == "packages":
        original = verifier.prepare_residual_all_input

        def split(*args):
            prepared = original(*args)
            prepared["plan"]["packages"] *= 2
            return prepared

        monkeypatch.setattr(verifier, "prepare_residual_all_input", split)
    elif defect == "slots":
        env["LANGCHAIN_SLOT1_MODEL"] = "gpt-6-luna"
    elif defect == "provider":
        env["LANGCHAIN_PROVIDER"] = "anthropic"
    elif defect == "registry-path":
        env["LANGCHAIN_MODEL_REGISTRY_CONFIG"] = str(tmp_path / "caller-registry.json")
    monkeypatch.setattr(
        verifier, "_build_semantic_clients", lambda *a, **kw: pytest.fail("constructed client")
    )
    with patch.dict(os.environ, env, clear=True):
        result = verifier.evaluate_pr_multiple(
            context, diff, model1="override" if defect == "model" else None
        )
    assert all(arm.used_llm is False for arm in result)


def test_count_exception_no_retry_and_no_generation(enabled, native, monkeypatch, tmp_path):
    original = verifier._preflight_input_capacity
    calls = []

    def fail(client, prompt, **kwargs):
        calls.append(prompt)
        raise verifier.InputCapacityError("inert count failure")

    monkeypatch.setattr(verifier, "_preflight_input_capacity", fail)
    inline_cli(monkeypatch)
    result = runner.run(execute=True)
    assert result["status"] == "held"
    assert len(calls) == 1
    assert not any(call[0] == "generation" for call in native)
    assert len(result["results"]) == 1
    assert original is not None


def test_timeout_stops_pair_without_relaunch(enabled, monkeypatch):
    calls = []

    def timeout(argv, **kwargs):
        calls.append(argv)
        raise runner.subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(runner.subprocess, "run", timeout)
    result = runner.run(execute=True)
    assert result["status"] == "held" and len(calls) == 1
    assert result["native_request_state"] == "unknown"


def test_job_has_no_repository_write_or_legacy_job_overlap():
    import yaml

    workflow = yaml.safe_load(
        (runner.ROOT / ".github/workflows/maint-78-model-evaluation-pilot.yml").read_text()
    )
    job = workflow["jobs"]["verify-paired"]
    assert workflow["jobs"]["assess"]["if"] == "inputs.mode != 'verify-paired'"
    assert job["permissions"] == {"contents": "read"}
    assert job["steps"][0]["with"]["persist-credentials"] is False
    assert job["timeout-minutes"] == 6
    assert all("github-script" not in step.get("uses", "") for step in job["steps"])
    step = next(step for step in job["steps"] if "env" in step)
    assert set(step["env"]) == {"OPENAI_API_KEY", "CLAUDE_API_STRANSKE"}


@pytest.mark.parametrize(
    "failure",
    [
        None,
        "count-503",
        "redirect",
        "timeout",
        "metadata-403",
        "generation-503",
        "generation-redirect",
        "generation-timeout",
    ],
)
def test_real_sdk_http_transport_bounded_and_no_redirect_fallback(enabled, monkeypatch, failure):
    import httpx

    requests = []
    original = langchain_client.build_chat_clients
    transports = []

    def serve(request):
        requests.append(request)
        assert request.url.host in {"api.openai.com", "api.anthropic.com"}
        assert request.url.path in {
            "/v1/responses/input_tokens",
            "/v1/responses",
            "/v1/messages/count_tokens",
            "/v1/messages",
            "/v1/models/claude-sonnet-5-5",
        }
        metadata = request.method == "GET"
        count = request.url.path.endswith(("input_tokens", "count_tokens"))
        if not metadata and not count and failure == "generation-503":
            return httpx.Response(503, json={"error": {"message": "inert generation failure"}})
        if not metadata and not count and failure == "generation-redirect":
            return httpx.Response(307, headers={"location": "https://unapproved.invalid/redirect"})
        if not metadata and not count and failure == "generation-timeout":
            raise httpx.ReadTimeout("inert generation timeout", request=request)
        if metadata and failure == "metadata-403":
            return httpx.Response(403, json={"error": {"message": "inert entitlement refusal"}})
        if count and failure == "count-503":
            return httpx.Response(503, json={"error": {"message": "inert service failure"}})
        if count and failure == "redirect":
            return httpx.Response(307, headers={"location": "https://unapproved.invalid/redirect"})
        if count and failure == "timeout":
            raise httpx.ReadTimeout("inert timeout", request=request)
        if metadata:
            return httpx.Response(
                200,
                json={
                    "id": "claude-sonnet-5-5",
                    "type": "model",
                    "display_name": "offline",
                    "created_at": "2026-10-10T00:00:00Z",
                    "max_input_tokens": 1000000,
                    "max_tokens": 128000,
                },
            )
        if count:
            return httpx.Response(
                200, json={"input_tokens": 1000, "object": "response.input_tokens"}
            )
        body = json.loads(request.content)
        assert body.get("max_output_tokens", body.get("max_tokens")) == 4096
        raw = '{"verdict":"PASS","concerns":[],"summary":"Offline native-shaped response"}'
        if request.url.host == "api.openai.com":
            return httpx.Response(
                200,
                json={
                    "id": "resp_offline",
                    "object": "response",
                    "created_at": 0,
                    "model": "gpt-5.6-terra",
                    "status": "completed",
                    "output": [
                        {
                            "id": "msg_offline",
                            "type": "message",
                            "role": "assistant",
                            "status": "completed",
                            "content": [{"type": "output_text", "text": raw, "annotations": []}],
                        }
                    ],
                    "usage": {"input_tokens": 1000, "output_tokens": 25, "total_tokens": 1025},
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "msg_offline",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-5-5",
                "content": [{"type": "text", "text": raw}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1000, "output_tokens": 25},
            },
        )

    def build(**kwargs):
        clients = original(**kwargs)
        for item in clients:
            sdk = item.client.root_client if item.provider == "openai" else item.client._client
            transport = httpx.Client(transport=httpx.MockTransport(serve), follow_redirects=True)
            transports.append(transport)
            monkeypatch.setattr(sdk, "_client", transport)
        return clients

    monkeypatch.setattr(langchain_client, "build_chat_clients", build)
    inline_cli(monkeypatch)
    try:
        result = runner.run(execute=True)
    finally:
        for transport in transports:
            transport.close()
    if failure is None:
        assert result["status"] == "completed_screen_only", result
        assert len(requests) == 18
    else:
        assert result["status"] == "held"
        if failure.startswith("generation-"):
            assert len(requests) == 9
            assert (
                sum(request.url.path in {"/v1/responses", "/v1/messages"} for request in requests)
                == 2
            )
        else:
            # Failed initial metadata/count cannot reach any generation.
            assert len(requests) == (1 if failure == "metadata-403" else 2)
            assert all(
                request.method == "GET"
                or request.url.path.endswith(("input_tokens", "count_tokens"))
                for request in requests
            )
