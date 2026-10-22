"""Real JS capture -> native evaluation input screen, with no model invocation."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest import mock

from scripts.langchain import pr_verifier

from tests.scripts.verifier_capacity_fakes import with_capacity

ROOT = Path(__file__).resolve().parents[2]


def test_freeform_original_request_reaches_native_input_preflight(tmp_path):
    env = dict(os.environ, VERIFIER_TEST_CAPTURE_DIR=str(tmp_path))
    subprocess.run(
        [
            "node",
            "--test",
            "--test-name-pattern=explicit evaluate admits authentic freeform request",
            ".github/scripts/__tests__/agents-verifier-context.test.js",
        ],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    context = (tmp_path / "context.md").read_text()
    diff = (tmp_path / "diff.patch").read_text()
    original = json.loads(
        (
            ROOT / ".github/scripts/__tests__/fixtures/orchestrator-pr866-original-request.json"
        ).read_text()
    )
    assert original["body"].strip() in context
    client = with_capacity(mock.MagicMock())
    receipt = pr_verifier._preflight_input_capacity(
        client,
        pr_verifier._prepare_prompt(context, diff),
        context=context,
        diff=diff,
        operation="evaluate_pr",
    )
    assert receipt["capture_obligations"]["sufficient"] is True
    assert receipt["prompt_coverage"]["sufficient"] is True
    client.invoke.assert_not_called()


def test_workflow_passes_explicit_mode_to_context_builder():
    workflow = (ROOT / ".github/workflows/reusable-agents-verifier.yml").read_text()
    step = workflow.split("- name: Build verifier context", 1)[1].split("\n      - name:", 1)[0]
    assert "VERIFIER_MODE: ${{ inputs.mode }}" in step
    assert "mode: process.env.VERIFIER_MODE" in step
