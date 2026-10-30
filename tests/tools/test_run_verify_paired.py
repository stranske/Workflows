"""Inert causal coverage of the real compare CLI and native policy boundaries."""

from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from scripts.langchain import pr_verifier as verifier
from tools import langchain_client
from tools import run_verify_paired as runner
from tools import verify_paired_policy as policy

_real_packet_loader_for_test = runner.load_packet


@pytest.fixture(autouse=True)
def deny_unmocked_network(monkeypatch):
    def refuse(*args, **kwargs):
        pytest.fail("paired source tests require inert transports; live network is forbidden")

    monkeypatch.setattr("socket.getaddrinfo", refuse)
    monkeypatch.setattr("socket.socket.connect", refuse)
    monkeypatch.setattr(
        runner, "DESCRIPTOR_PATH", runner.PACKET / "historical-square-descriptor.json"
    )


@pytest.fixture
def enabled(monkeypatch, tmp_path, request):
    if getattr(request, "param", None) == "representative":
        monkeypatch.setattr(runner, "DESCRIPTOR_PATH", runner.PACKET / "descriptor.json")
    proposal, caps = runner.load_packet()
    caps.update(execution_enabled=True, review_status="reviewed")
    monkeypatch.setattr(runner, "load_packet", lambda: (proposal, deepcopy(caps)))
    monkeypatch.setattr(policy, "load_packet", lambda: (proposal, deepcopy(caps)))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "offline-openai-placeholder")
    monkeypatch.setenv("CLAUDE_API_STRANSKE", "offline-anthropic-placeholder")
    # These are source-behavior tests against the locally available SDKs, not
    # qualification evidence for the unexecuted fresh locked Actions runtime.
    deps = runner.runtime_dependencies()
    monkeypatch.setattr(runner, "runtime_dependencies", lambda: {**deps, "matches_lock": True})
    return caps


@pytest.fixture
def native(monkeypatch, enabled):
    import httpx

    pytest.importorskip("langchain_openai")
    pytest.importorskip("langchain_anthropic")
    calls = []
    transports = []
    original = langchain_client.build_chat_clients

    def serve(request):
        provider = "openai" if request.url.host == "api.openai.com" else "anthropic"
        assert request.url.host in {"api.openai.com", "api.anthropic.com"}
        if request.method == "GET":
            calls.append(("metadata", provider, None))
            return httpx.Response(
                200,
                json={
                    "id": enabled["models"][1]["model"],
                    "type": "model",
                    "display_name": "offline",
                    "created_at": "2026-10-10T00:00:00Z",
                    "max_input_tokens": 1000000,
                    "max_tokens": 128000,
                },
            )
        payload = json.loads(request.content)
        if request.url.path.endswith(("input_tokens", "count_tokens")):
            calls.append(("count", provider, payload))
            return httpx.Response(
                200, json={"input_tokens": 1000, "object": "response.input_tokens"}
            )
        calls.append(("generation", provider, payload))
        assert (
            payload.get("max_output_tokens", payload.get("max_tokens"))
            == enabled["max_output_tokens"]
        )
        prompt = json.dumps(payload)
        assert "precommitted-semantic-oracle" not in prompt
        if not enabled.get("preserve_native_output_policy"):
            assert "No execution or CI result is supplied or claimed" in prompt
        raw = (
            '{"verdict":"CONCERNS","concerns":["abs(value) is not square: -3 gives 3, not 9"],'
            '"summary":"Arithmetic defect"}'
            if "+    return abs(value)" in prompt
            else '{"verdict":"PASS","concerns":[],"summary":"Complete source square meets specification"}'
        )
        if provider == "openai":
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
                "model": enabled["models"][1]["model"],
                "content": [{"type": "text", "text": raw}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1000, "output_tokens": 25},
            },
        )

    def build(**kwargs):
        assert kwargs["timeout"] == enabled["per_request_timeout_seconds"]
        assert kwargs["max_retries"] == 0
        clients = original(**kwargs)
        assert len(clients) == 2
        for item in clients:
            sdk = item.client.root_client if item.provider == "openai" else item.client._client
            assert sdk.max_retries == 0
            assert sdk.timeout == enabled["per_request_timeout_seconds"]
            transport = httpx.Client(transport=httpx.MockTransport(serve), follow_redirects=True)
            transports.append(transport)
            monkeypatch.setattr(sdk, "_client", transport)
        return clients

    monkeypatch.setattr(langchain_client, "build_chat_clients", build)
    try:
        yield calls
    finally:
        for transport in transports:
            transport.close()


def inline_cli(monkeypatch):
    def run(argv, *, cwd, env, stdout, stderr, timeout, check, shell):
        assert shell is False
        assert argv[1] == str(runner.ROOT / "scripts/langchain/pr_verifier.py")
        assert "--compare" in argv and "--create-issue" not in argv
        assert "GITHUB_TOKEN" not in env and "CODEX_AUTH_JSON" not in env
        assert 0 < timeout <= 600
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
        assert trial["attempted_physical_http_requests"] == 9
        assert trial["native_capacity_claim"] is False
        assert trial["role_qualification_claim"] is False
        original = json.loads((runner.PACKET / case / "capture.json").read_text())
        assert report["semantic_acceptance"]["capture"] == original
        assert all(arm["raw_content"] for arm in report["results"])
        private = tmp_path / "verify-paired-private" / case
        assert (tmp_path / "verify-paired" / case / "comparison.json").read_bytes() == (
            private / "comparison.json"
        ).read_bytes()


def test_shell_metacharacters_in_native_temp_path_are_only_argv_data(
    enabled, native, monkeypatch, tmp_path
):
    directory = tmp_path / "native temp ; $(inert) & 'quoted'"
    directory.mkdir()
    monkeypatch.setenv("RUNNER_TEMP", str(directory))
    inline_cli(monkeypatch)
    result = runner.run(execute=True)
    assert result["status"] == "completed_screen_only", result
    assert len(native) == 18
    assert (directory / "verify-paired" / "square-pass" / "comparison.json").is_file()


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


def test_installed_runtime_mismatch_holds_before_child(enabled, monkeypatch):
    deps = runner.runtime_dependencies()
    monkeypatch.setattr(runner, "runtime_dependencies", lambda: {**deps, "matches_lock": False})
    monkeypatch.setattr(
        runner.subprocess, "run", lambda *a, **kw: pytest.fail("provider-capable child")
    )
    result = runner.run(execute=True)
    assert result["status"] == "held" and result["semantic_cli_started"] is False
    assert result["native_request_state"] == "not_started"
    assert result["runtime_source"]["dependencies"]["matches_lock"] is False


def test_private_namespace_collision_holds_without_reading_or_cleaning_prior_files(
    enabled, monkeypatch, tmp_path
):
    private = tmp_path / "verify-paired-private"
    private.mkdir()
    key = private / ".semantic-key"
    key.write_bytes(b"prior-run-owned-key")
    (private / "square-pass").mkdir()
    (private / "square-pass/comparison.json").write_bytes(b"prior private output")
    monkeypatch.setattr(
        runner.subprocess, "run", lambda *a, **kw: pytest.fail("provider-capable child")
    )
    result = runner.run(execute=True)
    assert result["status"] == "held" and result["native_request_state"] == "not_started"
    assert key.read_bytes() == b"prior-run-owned-key"
    assert result["output_publication"] == {}
    assert not (tmp_path / "verify-paired/square-pass/comparison.json").exists()


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
    assert job["timeout-minutes"] == 11
    assert all("github-script" not in step.get("uses", "") for step in job["steps"])
    step = next(step for step in job["steps"] if "env" in step)
    assert set(step["env"]) == {"OPENAI_API_KEY", "CLAUDE_API_STRANSKE"}
    upload = job["steps"][-1]
    assert upload["with"]["include-hidden-files"] is False
    assert any(
        "uv pip sync" in entry.get("run", "") and "requirements.lock" in entry["run"]
        for entry in job["steps"]
    )
    assert "uv run" not in step["run"]
    assert "timeout --signal=KILL 600s" in step["run"]


@pytest.mark.parametrize(
    "defect",
    [
        "missing",
        "null",
        "case",
        "policy",
        "policy-type",
        "count-bool",
        "count-string",
        "count-negative",
        "count-overbound",
        "count-extra",
        "record-extra",
        "claim",
        "partial",
        "physical-missing",
        "physical-bool",
        "physical-overbound",
        "physical-partial",
    ],
)
def test_bad_child_counter_record_holds_without_advancing_case(enabled, monkeypatch, defect):
    calls = []

    def child(argv, **kwargs):
        calls.append(argv)
        trial = {
            "case": "square-pass",
            "policy": deepcopy(enabled),
            "attempted_native_requests": {"generation": 2, "count": 4, "metadata": 3},
            "attempted_physical_http_requests": 9,
            "native_capacity_claim": False,
            "role_qualification_claim": False,
        }
        report = {
            "results": [{"used_llm": True, "error": None}] * 2,
            "semantic_acceptance": {"qualification_trial": trial},
        }
        if defect == "missing":
            report.pop("semantic_acceptance")
        elif defect == "null":
            report["semantic_acceptance"]["qualification_trial"] = None
        elif defect == "case":
            trial["case"] = "square-nonpass"
        elif defect == "policy":
            trial["policy"]["max_output_tokens"] = 4095
        elif defect == "policy-type":
            trial["policy"]["retries"] = False
        elif defect.startswith("count-"):
            counts = trial["attempted_native_requests"]
            if defect == "count-extra":
                counts["other"] = 0
            else:
                counts["count"] = {
                    "count-bool": True,
                    "count-string": "4",
                    "count-negative": -1,
                    "count-overbound": 5,
                }[defect]
        elif defect == "record-extra":
            trial["other"] = "unexpected"
        elif defect == "claim":
            trial["native_capacity_claim"] = True
        elif defect == "partial":
            trial["attempted_native_requests"]["generation"] = 1
            trial["attempted_physical_http_requests"] = 8
        elif defect == "physical-missing":
            trial.pop("attempted_physical_http_requests")
        elif defect == "physical-bool":
            trial["attempted_physical_http_requests"] = True
        elif defect == "physical-overbound":
            trial["attempted_physical_http_requests"] = 10
        elif defect == "physical-partial":
            trial["attempted_physical_http_requests"] = 8
        kwargs["stdout"].write(json.dumps(report).encode())
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", child)
    result = runner.run(execute=True)
    assert result["status"] == "held" and len(calls) == 1
    if defect in {"partial", "physical-partial"}:
        assert result["native_request_state"] == "attempts_recorded"
        assert result["results"][0]["attempted_physical_http_requests"] == 8
    else:
        assert result["native_request_state"] == "unknown"
        assert "attempted_native_requests" not in result["results"][0]


def test_valid_partial_counters_survive_failed_child_exit(enabled, monkeypatch):
    calls = []

    def child(argv, **kwargs):
        calls.append(argv)
        report = {
            "semantic_acceptance": {
                "qualification_trial": {
                    "case": "square-pass",
                    "policy": enabled,
                    "attempted_native_requests": {"generation": 0, "count": 1, "metadata": 1},
                    "attempted_physical_http_requests": 2,
                    "native_capacity_claim": False,
                    "role_qualification_claim": False,
                }
            }
        }
        kwargs["stdout"].write(json.dumps(report).encode())
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(runner.subprocess, "run", child)
    result = runner.run(execute=True)
    assert result["status"] == "held" and len(calls) == 1
    assert result["native_request_state"] == "attempts_recorded"
    assert result["results"][0]["attempted_native_requests"] == {
        "generation": 0,
        "count": 1,
        "metadata": 1,
    }


def _http_guarded_sdks(enabled, monkeypatch, tmp_path, requests):
    import httpx

    pytest.importorskip("langchain_openai")
    pytest.importorskip("langchain_anthropic")

    key = tmp_path / "key"
    key.write_bytes(b"k" * 32)
    env = runner.child_environment("square-pass", runner.PACKET / "square-pass", key)
    trial = policy.PairedTrial("square-pass", enabled, float("inf"))

    def serve(request):
        requests.append(request)
        return httpx.Response(200, json={"input_tokens": 1000})

    with patch.dict(os.environ, env, clear=True):
        clients = langchain_client.build_chat_clients(timeout=30, max_retries=0)
    sdks = []
    for item in clients:
        sdk = item.client.root_client if item.provider == "openai" else item.client._client
        monkeypatch.setattr(sdk, "_client", httpx.Client(transport=httpx.MockTransport(serve)))
        trial.client(item.client)
        sdks.append(sdk)
    return trial, sdks


def test_shared_physical_budget_blocks_tenth_sdk_send_before_transport(
    enabled, monkeypatch, tmp_path
):
    from anthropic import APIConnectionError

    requests = []
    trial, sdks = _http_guarded_sdks(enabled, monkeypatch, tmp_path, requests)
    try:
        for index in range(9):
            sdk = sdks[index % 2]
            path = "/responses/input_tokens" if index % 2 == 0 else "/v1/messages/count_tokens"
            sdk.post(path, cast_to=dict[str, object], body={})
        with pytest.raises(APIConnectionError):
            sdks[1].post("/v1/messages/count_tokens", cast_to=dict[str, object], body={})
        assert len(requests) == 9 and trial.physical_http_attempts == 9
    finally:
        for sdk in sdks:
            sdk._client.close()


@pytest.mark.parametrize(
    "url,method",
    [
        ("https://unapproved.invalid/v1/responses/input_tokens", "POST"),
        ("https://api.anthropic.com/v1/messages/count_tokens", "POST"),
        ("http://api.openai.com/v1/responses/input_tokens", "POST"),
        ("https://api.openai.com:444/v1/responses/input_tokens", "POST"),
        ("https://api.openai.com/v1/unknown", "POST"),
        ("https://api.openai.com/v1/responses%2Finput_tokens", "POST"),
        ("https://api.openai.com/v1/responses/input_tokens?extra=1", "POST"),
        ("https://api.openai.com/v1/responses/input_tokens#extra", "POST"),
        ("https://user:password@api.openai.com/v1/responses/input_tokens", "POST"),
        ("https://api.openai.com/v1/responses/input_tokens", "GET"),
    ],
)
def test_sdk_foreign_or_unknown_request_denied_before_transport_auth_disclosure(
    enabled, monkeypatch, tmp_path, url, method
):
    from openai import APIConnectionError

    requests = []
    trial, sdks = _http_guarded_sdks(enabled, monkeypatch, tmp_path, requests)
    try:
        with pytest.raises(APIConnectionError):
            if method == "GET":
                sdks[0].get(url, cast_to=dict)
            else:
                sdks[0].post(url, cast_to=dict, body={})
        assert requests == [] and trial.physical_http_attempts == 0
    finally:
        for sdk in sdks:
            sdk._client.close()


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
        "generation-401-keyecho",
    ],
)
def test_real_sdk_http_transport_bounded_and_no_redirect_fallback(
    enabled, monkeypatch, failure, tmp_path
):
    import httpx

    pytest.importorskip("langchain_openai")
    pytest.importorskip("langchain_anthropic")

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
        if not metadata and not count and failure == "generation-401-keyecho":
            key = (
                "offline-openai-placeholder"
                if request.url.host == "api.openai.com"
                else "offline-anthropic-placeholder"
            )
            return httpx.Response(401, json={"error": {"message": "invalid key " + key}})
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
                    "id": enabled["models"][1]["model"],
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
                "model": enabled["models"][1]["model"],
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
    if failure == "generation-401-keyecho":
        private = tmp_path / "verify-paired-private/square-pass/comparison.json"
        raw = private.read_bytes()
        assert b"offline-openai-placeholder" in raw
        for path in (tmp_path / "verify-paired").rglob("*"):
            if path.is_file():
                assert b"offline-openai-placeholder" not in path.read_bytes()
                assert b"offline-anthropic-placeholder" not in path.read_bytes()
        withheld = json.loads(
            (tmp_path / "verify-paired/square-pass/comparison.json.withheld.json").read_text()
        )
        assert withheld["status"] == "withheld_credentials"
        assert withheld["sha256"] == runner.digest(raw)
        assert not (tmp_path / "verify-paired/square-pass/comparison.json").exists()


@pytest.mark.parametrize("failure", ["timeout", "malformed"])
def test_unfinished_child_bytes_stay_private_even_before_parent_cleanup(
    enabled, monkeypatch, tmp_path, failure
):
    calls = []
    key = b"offline-openai-placeholder"
    public = tmp_path / "verify-paired"

    def child(argv, **kwargs):
        calls.append(argv)
        for name in ("stdout", "stderr"):
            assert not Path(kwargs[name].name).is_relative_to(public)
            kwargs[name].write(key)
            kwargs[name].flush()
        report = Path(argv[argv.index("--output-file") + 1])
        assert not report.is_relative_to(public)
        report.write_bytes(key)
        # An abrupt process kill here leaves only public packet bytes in the
        # artifact root; cleanup and publication have not run yet.
        assert all(key not in path.read_bytes() for path in public.rglob("*") if path.is_file())
        if failure == "timeout":
            checkpoint = json.loads((public / "invocation.json").read_text())
            assert checkpoint["status"] == "in_progress"
            assert checkpoint["native_request_state"] == "unknown"
            raise runner.subprocess.TimeoutExpired(argv, kwargs["timeout"])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", child)
    result = runner.run(execute=True)
    assert result["status"] == "held" and len(calls) == 1
    assert result["native_request_state"] == "unknown"
    assert all(key not in path.read_bytes() for path in public.rglob("*") if path.is_file())
    assert {row["status"] for row in result["output_publication"]["square-pass"].values()} == {
        "withheld_credentials"
    }


@pytest.mark.parametrize("enabled", ["representative"], indirect=True)
def test_real_representative_packets_actual_native_payloads(enabled, native, monkeypatch, tmp_path):
    inline_cli(monkeypatch)
    result = runner.run(execute=True)
    assert result["status"] == "completed_screen_only", result
    assert [
        sum(row[0] == kind for row in native) for kind in ("generation", "count", "metadata")
    ] == [4, 8, 6]
    descriptor = runner.source_descriptor()
    expected_sizes = [469268, 481446]
    for case, size in zip(descriptor["cases"], expected_sizes, strict=True):
        report = json.loads((tmp_path / "verify-paired" / case / "comparison.json").read_text())
        assert report["semantic_acceptance"]["capture"] == json.loads(
            (descriptor["root"] / case / "capture.json").read_text()
        )
        assert result["input_preflight"][case]["prompt_bytes"] == size
        assert (
            report["semantic_acceptance"]["qualification_trial"]["attempted_physical_http_requests"]
            == 9
        )
    for kind, provider, payload in native:
        if kind != "generation":
            continue
        assert payload.get("max_output_tokens", payload.get("max_tokens")) == 128000
        assert payload["model"] == ("gpt-5.6-terra" if provider == "openai" else "claude-opus-5-5")
        assert "effort" not in payload and "output_config" not in payload
        text = payload["input"] if provider == "openai" else payload["messages"]
        # The full frozen prompt is present in the actual SDK request, not a legacy truncation.
        flattened = json.dumps(text, ensure_ascii=False)
        assert any(
            json.dumps((descriptor["root"] / case / "prompt.txt").read_text(), ensure_ascii=False)[
                1:-1
            ]
            in flattened
            for case in descriptor["cases"]
        )


@pytest.mark.parametrize("enabled", ["representative"], indirect=True)
def test_original_entry_deadline_shared_after_expensive_preflight(enabled, monkeypatch):
    original = runner.preflight_inputs
    clock = [1000.0]
    monkeypatch.setattr(runner.time, "monotonic", lambda: clock[0])

    def preflight(*args):
        result = original(*args)
        clock[0] += 120
        return result

    monkeypatch.setattr(runner, "preflight_inputs", preflight)
    deadlines = []

    def child(argv, *, env, stdout, **kwargs):
        deadlines.append(float(env["VERIFIER_PAIRED_PACKAGE_DEADLINE_MONOTONIC"]))
        assert kwargs["timeout"] == 480
        case = env["VERIFIER_PAIRED_QUALIFICATION"]
        stdout.write(
            json.dumps(
                {
                    "results": [{"used_llm": True, "error": None}] * 2,
                    "semantic_acceptance": {
                        "qualification_trial": {
                            "case": case,
                            "policy": enabled,
                            "attempted_native_requests": {
                                "generation": 2,
                                "count": 4,
                                "metadata": 3,
                            },
                            "attempted_physical_http_requests": 9,
                            "native_capacity_claim": False,
                            "role_qualification_claim": False,
                        }
                    },
                }
            ).encode()
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", child)
    result = runner.run(execute=True)
    assert result["status"] == "completed_screen_only", result
    assert deadlines == [1600, 1600]


@pytest.mark.parametrize("enabled", ["representative"], indirect=True)
def test_all_inputs_admitted_before_first_client_even_when_second_is_bad(enabled, monkeypatch):
    original = verifier._semantic_capture
    calls = []

    def capture(context, diff):
        result = original(context, diff)
        calls.append(result["id"])
        if len(calls) == 2:
            result["gaps"] = ["required execution evidence missing"]
        return result

    monkeypatch.setattr(verifier, "_semantic_capture", capture)
    monkeypatch.setattr(
        langchain_client,
        "build_chat_clients",
        lambda **kwargs: pytest.fail("no client before all packet admission"),
    )
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *a, **k: pytest.fail("no child before all packet admission"),
    )
    result = runner.run(execute=True)
    assert result["status"] == "held" and result["native_request_state"] == "not_started"
    assert len(calls) == 2


def test_actual_http_remaining_deadline_clamps_each_phase_before_send(monkeypatch):
    import httpx

    _, caps = runner.load_packet()
    caps["per_request_timeout_seconds"] = 60
    clock = [100.0]
    monkeypatch.setattr(policy, "monotonic", lambda: clock[0])
    trial = policy.PairedTrial("square-pass", caps, 100.25)
    request = httpx.Request(
        "POST",
        "https://api.openai.com/v1/responses",
        extensions={"timeout": dict.fromkeys(("read", "write", "connect", "pool"), 60.0)},
    )
    trial.authorize_http_request(request, expected_host="api.openai.com")
    assert set(request.extensions["timeout"].values()) == {0.25}
    clock[0] = 100.25
    with pytest.raises(ValueError, match="exhausted before HTTP"):
        trial.authorize_http_request(request, expected_host="api.openai.com")
    assert trial.physical_http_attempts == 1


@pytest.mark.parametrize(
    "defect", ["unknown", "absolute", "traversal", "symlink", "hash", "duplicate"]
)
def test_closed_descriptor_denies_bad_source_before_client(monkeypatch, tmp_path, defect):
    namespace = tmp_path / "packet"
    namespace.mkdir()
    descriptor = json.loads((runner.PACKET / "descriptor.json").read_text())
    if defect == "unknown":
        descriptor["caller_url"] = "https://untrusted.invalid"
    if defect == "absolute":
        descriptor["packet_root"] = "/tmp"
    if defect == "traversal":
        descriptor["packet_root"] = "../escape"
    if defect == "symlink":
        (namespace / "representative-v1").symlink_to(
            runner.PACKET / "representative-v1", target_is_directory=True
        )
    if defect == "hash":
        directory = namespace / "representative-v1"
        directory.mkdir()
        (directory / "PROPOSAL.json").write_bytes(
            (runner.PACKET / "representative-v1/PROPOSAL.json").read_bytes()
        )
        descriptor["proposal_sha256"] = "0" * 64
    raw = json.dumps(descriptor)
    if defect == "duplicate":
        raw = raw[:-1] + ',"cases":["other"]}'
    (namespace / "descriptor.json").write_text(raw)
    monkeypatch.setattr(runner, "PACKET", namespace)
    monkeypatch.setattr(runner, "DESCRIPTOR_PATH", namespace / "descriptor.json")
    monkeypatch.setattr(
        langchain_client,
        "build_chat_clients",
        lambda **k: pytest.fail("untrusted descriptor constructed clients"),
    )
    with pytest.raises(ValueError):
        runner.load_packet()


@pytest.mark.parametrize("enabled", ["representative"], indirect=True)
def test_one_case_descriptor_completes_exactly_two_generations(
    enabled, native, monkeypatch, tmp_path
):
    # Select a subset using the same source-owned data contract, not a new runner.
    import shutil

    # Retain the real loader before the enablement-only test wrapper.
    real_loader = _real_packet_loader_for_test
    source = tmp_path / "source"
    namespace = source / "config/verify_paired"
    shutil.copytree(runner.PACKET, namespace)
    for name in (
        "tools/run_verify_paired.py",
        "tools/verify_paired_policy.py",
        "scripts/langchain/pr_verifier.py",
        "scripts/langchain/prompts/pr_evaluation.md",
        "config/model_registry.json",
        "requirements.lock",
        "pyproject.toml",
    ):
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(runner.ROOT / name, target)
    descriptor = json.loads((namespace / "descriptor.json").read_text())
    proposal_path = namespace / "representative-v1/PROPOSAL.json"
    proposal = json.loads(proposal_path.read_text())
    removed = descriptor["cases"].pop()
    proposal["cases"] = proposal["cases"][:1]
    proposal["frozen_files"] = {
        name: value
        for name, value in proposal["frozen_files"].items()
        if not name.startswith(removed + "/")
    }
    shutil.rmtree(namespace / "representative-v1" / removed)
    proposal_path.write_text(json.dumps(proposal, indent=2) + "\n")
    descriptor["proposal_sha256"] = runner.digest(proposal_path.read_bytes())
    (namespace / "descriptor.json").write_text(json.dumps(descriptor, indent=2) + "\n")
    monkeypatch.setattr(runner, "ROOT", source)
    monkeypatch.setattr(policy, "ROOT", source)
    monkeypatch.setattr(runner, "PACKET", namespace)
    monkeypatch.setattr(runner, "DESCRIPTOR_PATH", namespace / "descriptor.json")

    def enabled_loader():
        proposal, caps = real_loader()
        caps.update(execution_enabled=True, review_status="reviewed")
        return proposal, caps

    monkeypatch.setattr(runner, "load_packet", enabled_loader)
    monkeypatch.setattr(policy, "load_packet", enabled_loader)
    inline_cli(monkeypatch)
    result = runner.run(execute=True)
    assert result["status"] == "completed_screen_only", result
    assert [
        sum(row[0] == kind for row in native) for kind in ("generation", "count", "metadata")
    ] == [2, 4, 3]
    assert len(result["results"]) == 1
    assert result["results"][0]["attempted_physical_http_requests"] == 9


@pytest.mark.parametrize("enabled", ["representative"], indirect=True)
def test_frozen_public_archive_retains_hidden_evidence_without_private_bytes(
    enabled, monkeypatch, tmp_path
):
    import zipfile

    descriptor = runner.source_descriptor()
    proposal, _ = runner.load_packet()
    result = runner.run(execute=False)
    assert result["status"] == "prepared"
    archive_bytes = (tmp_path / "verify-paired/frozen-public-packet.zip").read_bytes()
    retained = result["public_packet_archive"]
    assert retained["sha256"] == runner.digest(archive_bytes)
    assert retained["entry_count"] == len(proposal["frozen_files"]) + 4
    with zipfile.ZipFile(tmp_path / "verify-paired/frozen-public-packet.zip") as archive:
        assert archive.namelist() == sorted(archive.namelist())
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())
        assert {name: runner.digest(archive.read(name)) for name in archive.namelist()} == retained[
            "entries_sha256"
        ]
        second = tmp_path / "second-archive"
        second.mkdir()
        runner.retain_public_packet(second, descriptor, proposal)
        assert (second / "frozen-public-packet.zip").read_bytes() == archive_bytes
        assert any("/source/.github/" in name for name in archive.namelist())
        for name, sha in proposal["frozen_files"].items():
            assert runner.digest(archive.read("packet/" + name)) == sha
        assert archive.read("descriptor.json") == runner.DESCRIPTOR_PATH.read_bytes()
        assert not any(
            "semantic-key" in name or "comparison.json" in name for name in archive.namelist()
        )
        assert (
            archive.read("packet/PROPOSAL.json")
            == (descriptor["root"] / "PROPOSAL.json").read_bytes()
        )


def test_actual_sdk_request_deadline_blocks_expired_send(enabled, monkeypatch, tmp_path):
    from openai import APIConnectionError

    requests = []
    trial, sdks = _http_guarded_sdks(enabled, monkeypatch, tmp_path, requests)
    clock = [100.0]
    monkeypatch.setattr(policy, "monotonic", lambda: clock[0])
    trial.deadline = 100.125
    try:
        sdks[0].post("/responses/input_tokens", cast_to=dict[str, object], body={})
        assert len(requests) == 1
        assert set(requests[0].extensions["timeout"].values()) == {0.125}
        clock[0] = 100.125
        with pytest.raises(APIConnectionError):
            sdks[0].post("/responses/input_tokens", cast_to=dict[str, object], body={})
        assert len(requests) == 1 and trial.physical_http_attempts == 1
    finally:
        for sdk in sdks:
            sdk._client.close()


@pytest.mark.parametrize("enabled", ["representative"], indirect=True)
@pytest.mark.parametrize("missing", ["OPENAI_API_KEY", "CLAUDE_API_STRANSKE"])
def test_missing_provider_does_not_shift_representative_slots(enabled, monkeypatch, missing):
    pytest.importorskip("langchain_openai")
    pytest.importorskip("langchain_anthropic")
    monkeypatch.delenv(missing)
    inline_cli(monkeypatch)
    result = runner.run(execute=True)
    assert result["status"] == "held", result
    assert len(result["results"]) == 1
    assert result["results"][0]["attempted_native_requests"] == {
        "count": 0,
        "generation": 0,
        "metadata": 0,
    }
    assert result["results"][0]["attempted_physical_http_requests"] == 0


@pytest.mark.parametrize("enabled", ["representative"], indirect=True)
def test_current_prompt_drift_held_before_any_child(enabled, monkeypatch):
    monkeypatch.setattr(verifier, "_load_prompt", lambda: "different full wrapper {context} {diff}")
    monkeypatch.setattr(
        runner.subprocess, "run", lambda *a, **k: pytest.fail("drift launched child")
    )
    result = runner.run(execute=True)
    assert result["status"] == "held" and "native prompt differs" in result["reason"]
    assert result["semantic_cli_started"] is False


@pytest.mark.parametrize("deadline", ["nan", "inf", "0", "401", "bad", None])
def test_child_refuses_missing_expired_or_extended_original_deadline(
    enabled, monkeypatch, tmp_path, deadline
):
    key = tmp_path / "key"
    env = runner.child_environment("square-pass", runner.PACKET / "square-pass", key)
    if deadline is None:
        env.pop("VERIFIER_PAIRED_PACKAGE_DEADLINE_MONOTONIC")
    else:
        env["VERIFIER_PAIRED_PACKAGE_DEADLINE_MONOTONIC"] = deadline
    monkeypatch.setattr(policy, "monotonic", lambda: 100)
    capture = json.loads((runner.PACKET / "square-pass/capture.json").read_text())
    with patch.dict(os.environ, env, clear=True), pytest.raises(ValueError, match="deadline"):
        policy.PairedTrial.from_environment(capture)


def test_immutable_packet_data_exclusions_do_not_cover_runner_or_siblings():
    import re
    import tomllib

    config = tomllib.loads((runner.ROOT / "pyproject.toml").read_text())
    black = re.compile(config["tool"]["black"]["force-exclude"], re.VERBOSE)
    data = "config/verify_paired/representative-v1"
    assert black.search("/" + data + "/case/evidence/raw.py")
    ruff = config["tool"]["ruff"]["exclude"]
    assert config["tool"]["ruff"]["force-exclude"] is True
    assert data in ruff
    for source in (
        "tools/run_verify_paired.py",
        "tools/verify_paired_policy.py",
        "scripts/langchain/pr_verifier.py",
        "tests/tools/test_run_verify_paired.py",
        "config/verify_paired/sibling/raw.py",
        "config/verify_paired/representative-v10/raw.py",
    ):
        assert not black.search("/" + source)
        assert not source.startswith(data + "/")
    assert not any(
        path in ruff for path in ("config", "config/verify_paired", "tools", "scripts", "tests")
    )


def test_fixed_compare_argv_never_imports_or_executes_evidence(enabled, monkeypatch):
    def no_child(argv, **kwargs):
        assert argv[:2] == [
            runner.sys.executable,
            str(runner.ROOT / "scripts/langchain/pr_verifier.py"),
        ]
        assert not any("current-review-runner.py" in value for value in argv)
        assert "--context-file" in argv and "--diff-file" in argv
        raise TimeoutError("inert stop before command")

    monkeypatch.setattr(runner.subprocess, "run", no_child)
    result = runner.run(execute=True)
    assert result["status"] == "held" and result["native_request_state"] == "unknown"


@pytest.mark.parametrize("tool", ["black", "ruff"])
def test_explicit_formatter_arguments_protect_only_frozen_data(tool, tmp_path):
    import subprocess

    pytest.importorskip(tool)
    (tmp_path / "pyproject.toml").write_bytes((runner.ROOT / "pyproject.toml").read_bytes())
    paths = (
        "config/verify_paired/representative-v1/case/raw.py",
        "tools/run_verify_paired.py",
        "tools/verify_paired_policy.py",
        "scripts/langchain/pr_verifier.py",
        "tests/tools/test_run_verify_paired.py",
        "config/verify_paired/sibling/raw.py",
        "config/verify_paired/representative-v10/raw.py",
    )
    for name in paths:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("import os\nprint(  1)\n")
        flags = ["--check"] if tool == "black" else ["check"]
        result = subprocess.run(
            [runner.sys.executable, "-m", tool, *flags, str(path)],
            cwd=tmp_path,
            capture_output=True,
            check=False,
        )
        assert result.returncode == (0 if name == paths[0] else 1), (
            tool,
            name,
            result.stdout,
            result.stderr,
        )
    original = (
        runner.PACKET
        / "representative-v1/workflows-4265-verified/evidence/current-review-runner.py"
    )
    before = original.read_bytes()
    flags = ["--check"] if tool == "black" else ["check"]
    result = subprocess.run(
        [runner.sys.executable, "-m", tool, *flags, str(original)],
        cwd=runner.ROOT,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert original.read_bytes() == before
