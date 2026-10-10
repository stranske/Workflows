"""#3820 recovery: immutable capture, full requests and independent provider gaps."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
import yaml
from scripts.langchain import pr_verifier


@pytest.fixture(autouse=True)
def expanded_recovery(monkeypatch):
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")


@pytest.fixture(params=["openai", "anthropic"])
def configured_native_client(request):
    """Construct the actual selected adapters without credentials or network calls."""
    from tools import langchain_client

    provider = request.param
    registry = json.loads(Path("config/model_registry.json").read_text())
    selection = next(
        item
        for item in registry["selections"]
        if item["profile"] == "verifier-balanced" and item["provider"] == provider
    )
    if provider == "openai":
        cls = pytest.importorskip("langchain_openai").ChatOpenAI
        builder = langchain_client._build_openai_client
    else:
        cls = pytest.importorskip("langchain_anthropic").ChatAnthropic
        builder = langchain_client._build_anthropic_client
    client = builder(
        cls, model=selection["model_id"], token="offline-placeholder", timeout=1, max_retries=0
    )
    payload = client._get_request_payload("full request")
    assert payload["model"] == selection["model_id"]
    assert "messages" in payload
    if provider == "openai":
        assert "input" not in payload  # Incumbent Terra uses Chat Completions.
    return client, provider, selection["model_id"]


@pytest.mark.parametrize("profile", [None, "standard", "expanded"])
@pytest.mark.parametrize("operation", ["evaluate", "compare", "repair"])
def test_configured_native_client_compatibility(
    configured_native_client, profile, operation, monkeypatch, tmp_path
):
    client, provider, model = configured_native_client
    # Current installed adapters have no authoritative exact-model capacity facts.
    assert client.profile is None
    if profile is None:
        monkeypatch.delenv("VERIFIER_EVIDENCE_PROFILE", raising=False)
    else:
        monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", profile)
    report = tmp_path / "capacity.jsonl"
    monkeypatch.setenv("VERIFIER_CAPACITY_REPORT_PATH", str(report))
    monkeypatch.setattr(pr_verifier, "_get_llm_client", lambda **kwargs: (client, provider))
    with mock.patch.object(
        type(client), "invoke", return_value=SimpleNamespace(content='{"verdict":"PASS"}')
    ) as invoke:
        if operation == "repair":
            result = pr_verifier._parse_llm_response("invalid JSON", provider, client=client)
        elif operation == "compare":
            result = pr_verifier.ComparisonRunner("context", None, "full request", []).run_single(
                client, provider, model
            )
        else:
            result = pr_verifier.evaluate_pr("context", provider=provider)
    if profile == "expanded":
        assert result.verdict == "CONCERNS"
        invoke.assert_not_called()
        record = json.loads(report.read_text())
        assert record["status"] == "unavailable"
        assert "model-specific capacity profile unavailable" in record["reason"]
    else:
        invoke.assert_called_once()
        assert result.used_llm
        assert not report.exists()  # Standard does not claim native capacity proof.
        if operation == "repair":
            assert result.verdict == "PASS"


@pytest.mark.parametrize("profile", ["standard", "expanded"])
@pytest.mark.parametrize("gap", ["code", "evidence"])
def test_evidence_floor_is_unconditional(profile, gap, monkeypatch):
    from tests.scripts.test_pr_verifier_prompt_coverage import _context

    context, _ = _context(1, 1000, 500, drop_diff=gap == "code")
    if gap == "evidence":
        inventory = {"acceptance_source_discovery": {"required": True, "status": "unavailable"}}
        context = context.replace(
            "## CI Information",
            "## Context source coverage\n\n```json\n"
            + json.dumps(inventory)
            + "\n```\n\n## CI Information",
            1,
        )
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", profile)
    client, _ = capacity_client(window=1_000_000)
    monkeypatch.setattr(pr_verifier, "_get_llm_client", lambda **kwargs: (client, "configured"))
    result = pr_verifier.evaluate_pr(context)
    client.invoke.assert_called_once()
    assert result.verdict == "CONCERNS"
    assert "retained" in result.concerns
    assert not result.input_coverage["sufficient"]


def test_authenticated_capture_replay(monkeypatch):
    capture = os.environ.get("VERIFIER_RECOVERY_CAPTURE_DIR")
    if not capture:
        pytest.skip(
            "immutable authenticated capture is owner-local; set VERIFIER_RECOVERY_CAPTURE_DIR"
        )
    root = Path(capture)
    hashes = {
        "verifier-context.md": "efefb70dcd4dff7c6751adecf4a8145854bbe716f306a2c8e18e731aeffd993c",
        "verifier-pr-diff.patch": "21f504e512061b73e4a9bb226837ec5f325c9822779eed8a429a9274d5ccacf9",
        "comparison.json": "5c266ffbbacb5fbc50bbcd87fc2c4ff1d85455656b2a53b7e8ed519298bb0051",
    }
    for name, digest in hashes.items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
    context = (root / "verifier-context.md").read_text()
    diff = (root / "verifier-pr-diff.patch").read_text()
    monkeypatch.setenv("VERIFIER_DIFF_BUDGET_TOKENS", "32000")
    monkeypatch.setenv("VERIFIER_ACCEPTANCE_EVIDENCE_BUDGET_TOKENS", "48000")
    monkeypatch.setenv("VERIFIER_CONTEXT_BUDGET_TOKENS", "4000")
    old = pr_verifier.build_prompt_inputs(context, diff).coverage.to_dict()
    assert old["files_complete"] == 4
    assert old["code_included_chars"] == 127635
    assert old["code_total_chars"] == 257099
    workflow = yaml.load(
        Path(".github/workflows/reusable-agents-verifier.yml").read_text(), Loader=yaml.BaseLoader
    )
    step = next(
        s
        for s in workflow["jobs"]["verifier"]["steps"]
        if s.get("name") == "Select bounded verifier evidence profile"
    )
    import re

    for name, value in re.findall(r"'(VERIFIER_\w+)=(\d+)'", step["run"]):
        monkeypatch.setenv(name, value)
    inputs = pr_verifier.build_prompt_inputs(context, diff)
    new = inputs.coverage.to_dict()
    assert new["files_complete"] == 7
    assert new["code_included_chars"] == new["code_total_chars"] == 257099
    assert not inputs.coverage.sufficient  # Retrieval gaps are immutable in this capture.
    result = pr_verifier._apply_coverage_floor(
        pr_verifier.EvaluationResult(
            verdict="PASS", used_llm=True, concerns=["independent finding"]
        ),
        inputs.coverage,
    )
    assert result.verdict == "CONCERNS"
    assert "independent finding" in result.concerns


def capacity_client(input_tokens=100, window=120, output=20):
    counter = mock.Mock(return_value=SimpleNamespace(input_tokens=input_tokens))
    client = SimpleNamespace(
        profile={"max_input_tokens": window, "max_output_tokens": output},
        max_tokens=output,
        root_client=SimpleNamespace(
            responses=SimpleNamespace(input_tokens=SimpleNamespace(count=counter))
        ),
        _get_request_payload=lambda prompt: {
            "model": "configured-model",
            "input": [{"role": "user", "content": prompt}],
            "max_output_tokens": output,
        },
        invoke=mock.Mock(
            return_value=SimpleNamespace(content='{"verdict":"PASS","concerns":["retained"]}')
        ),
    )
    return client, counter


def test_actual_capacity_boundary_counts_entire_rendered_request():
    client, counter = capacity_client()
    prompt = pr_verifier._prepare_prompt(
        "## Plan sources (scope, tasks, acceptance)\n- [ ] Deliver evidence\n"
        "## Acceptance evidence\n- PR body: **present**\nall required evidence",
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new\n",
    )
    assert "## Verifier input coverage" in prompt
    assert "all required evidence" in prompt
    assert "+new" in prompt
    pr_verifier._invoke_llm(client, prompt, operation="test")
    assert counter.call_args.kwargs["input"][0]["content"] == prompt
    client.invoke.assert_called_once()
    client.invoke.reset_mock()
    counter.return_value.input_tokens += 1
    with pytest.raises(Exception, match="capacity"):
        pr_verifier._invoke_llm(client, prompt, operation="test")
    client.invoke.assert_not_called()


@pytest.mark.parametrize(
    "defect",
    [
        "unknown-window",
        "unknown-output",
        "bad-count",
        "counter-error",
        "unsupported-counter",
        "auto-truncation",
        "overflow",
    ],
)
@pytest.mark.parametrize("operation", ["invoke", "repair"])
def test_actual_capacity_unknowns_never_invoke(defect, operation):
    client, counter = capacity_client()
    if defect == "unknown-window":
        client.profile = None
    if defect == "unknown-output":
        client.max_tokens = None
        client.profile.pop("max_output_tokens")
    if defect == "bad-count":
        counter.return_value.input_tokens = True
    if defect == "counter-error":
        counter.side_effect = RuntimeError("capacity count unavailable")
    if defect == "unsupported-counter":
        client.root_client = None
    if defect == "overflow":
        counter.return_value.input_tokens = 101
    if defect == "auto-truncation":
        client._get_request_payload = lambda prompt: {
            "model": "configured-model",
            "input": prompt,
            "truncation": "auto",
        }
    if operation == "repair":
        result = pr_verifier._parse_llm_response("invalid JSON", "configured", client=client)
        assert result.verdict == "CONCERNS"
        assert result.error
    else:
        with pytest.raises(pr_verifier.InputCapacityError, match="capacity"):
            pr_verifier._invoke_llm(client, "entire input", operation="test")
    client.invoke.assert_not_called()


def test_capacity_overflow_floors_compare_arm_without_erasing_sibling_findings():
    client, _ = capacity_client(input_tokens=101)
    runner = pr_verifier.ComparisonRunner(
        context="context", diff=None, prompt="full prompt", clients=[]
    )
    failed = runner.run_single(client, "configured-provider", "configured-model")
    assert failed.verdict == "CONCERNS"
    assert not failed.used_llm
    assert "capacity" in failed.error.lower()
    client.invoke.assert_not_called()


def test_counting_auth_failure_cannot_switch_models(monkeypatch):
    client, counter = capacity_client()
    counter.side_effect = RuntimeError("401 Unauthorized")
    resolver = mock.Mock(return_value=(client, "configured-provider"))
    monkeypatch.setattr(pr_verifier, "_get_llm_client", resolver)
    result = pr_verifier.evaluate_pr("full context")
    assert result.verdict == "CONCERNS"
    assert "capacity" in result.error.lower()
    assert resolver.call_count == 1
    client.invoke.assert_not_called()


def test_native_message_capacity_and_schema_repair_are_checked():
    client, _ = capacity_client()
    counter = mock.Mock(return_value=SimpleNamespace(input_tokens=100))
    client._client = SimpleNamespace(messages=SimpleNamespace(count_tokens=counter))
    client._get_request_payload = lambda prompt: {
        "model": "configured-model",
        "messages": [{"role": "user", "content": prompt}],
        "system": "system instructions",
        "max_tokens": 20,
    }
    receipt = pr_verifier._preflight_input_capacity(client, "all evidence")
    assert receipt["status"] == "PASS"
    assert counter.call_args.kwargs["system"] == "system instructions"
    assert counter.call_args.kwargs["messages"][0]["content"] == "all evidence"
    client.invoke.reset_mock()
    counter.return_value.input_tokens = 101
    repair = pr_verifier._build_verifier_repair_callback(client)
    assert repair("{}", "invalid", "all previous findings") is None
    client.invoke.assert_not_called()


def test_capacity_receipt_retains_overflow_without_prompt_clipping(tmp_path, monkeypatch):
    report = tmp_path / "capacity.jsonl"
    monkeypatch.setenv("VERIFIER_CAPACITY_REPORT_PATH", str(report))
    client, _ = capacity_client(input_tokens=101)
    with pytest.raises(pr_verifier.InputCapacityError):
        pr_verifier._invoke_llm(client, "entire request", operation="test")
    record = json.loads(report.read_text())
    assert record["status"] == "overflow"
    assert record["input_tokens"] == 101
    assert record["output_reserve"] == 20
    assert record["prompt_chars"] == len("entire request")
