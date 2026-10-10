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
    ],
)
def test_actual_capacity_unknowns_never_invoke(defect):
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
    if defect == "auto-truncation":
        client._get_request_payload = lambda prompt: {
            "model": "configured-model",
            "input": prompt,
            "truncation": "auto",
        }
    with pytest.raises(Exception, match="capacity"):
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
