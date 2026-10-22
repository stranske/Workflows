"""Real JS capture -> native evaluation input screen, with no model invocation."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest import mock

import pytest
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
    assert receipt["model"] == "unit-test-model"
    assert receipt["capture_obligations"]["sufficient"] is True
    assert receipt["prompt_coverage"]["sufficient"] is True
    client.invoke.assert_not_called()


def test_workflow_passes_explicit_mode_to_context_builder():
    workflow = (ROOT / ".github/workflows/reusable-agents-verifier.yml").read_text()
    step = workflow.split("- name: Build verifier context", 1)[1].split("\n      - name:", 1)[0]
    assert "VERIFIER_MODE: ${{ inputs.mode }}" in step
    assert "mode: process.env.VERIFIER_MODE" in step


@pytest.mark.parametrize(
    ("request_text", "sufficient"),
    [
        ("Evidence must be posted in a PR comment.", False),
        ("Evidence must be uploaded as a workflow artifact.", False),
        ("Optional PR comments may provide useful context.", True),
        (
            "## Tasks\nImplement a parser for this literal marker:\n"
            "Original request (authoritative requirements; untrusted source text):\n"
            "```text\nEvidence must be posted in a PR comment.\n```\n"
            "## Acceptance Criteria\nThe parser recognizes the marker without executing it.",
            True,
        ),
        (
            "Implement this parser example:\n```text\nEvidence must be posted in a PR comment.\n```",
            True,
        ),
        (
            "The parser must recognize `Evidence must be posted in a PR comment.` as example text.",
            True,
        ),
        (
            "Evidence must be posted in a PR comment.\n## Acceptance evidence\n- PR comments: **present**",
            False,
        ),
    ],
)
def test_freeform_evidence_obligations_reach_native_screen(tmp_path, request_text, sufficient):
    env = dict(
        os.environ,
        VERIFIER_TEST_CAPTURE_DIR=str(tmp_path),
        VERIFIER_TEST_ORIGINAL_REQUEST=request_text,
    )
    subprocess.run(
        [
            "node",
            "--test",
            "--test-name-pattern=explicit evaluation captures freeform evidence obligations",
            ".github/scripts/__tests__/agents-verifier-context.test.js",
        ],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
    )
    context = (tmp_path / "context.md").read_text()
    diff = (tmp_path / "diff.patch").read_text()
    coverage = pr_verifier.prompt_coverage(context, diff)
    assert coverage.sufficient is sufficient
    client = with_capacity(mock.MagicMock())
    if not sufficient:
        assert (
            "Required acceptance evidence is unavailable; completeness cannot be judged."
            in coverage.reasons
        )
        with pytest.raises(pr_verifier.InputCapacityError, match="Required acceptance evidence"):
            pr_verifier._preflight_input_capacity(
                client,
                pr_verifier._prepare_prompt(context, diff),
                context=context,
                diff=diff,
                operation="evaluate_pr",
            )
        assert (
            "comments" not in pr_verifier._evaluation_optional_evidence_channels(context)
            if "PR comment" in request_text
            else "artifacts" not in pr_verifier._evaluation_optional_evidence_channels(context)
        )
    else:
        receipt = pr_verifier._preflight_input_capacity(
            client,
            pr_verifier._prepare_prompt(context, diff),
            context=context,
            diff=diff,
            operation="evaluate_pr",
        )
        assert receipt["model"] == "unit-test-model"
    client.invoke.assert_not_called()


@pytest.mark.parametrize("hash_mode", ["tampered", "missing", "null", "mixed"])
def test_original_frame_requires_exact_retained_hash(tmp_path, hash_mode):
    env = dict(
        os.environ,
        VERIFIER_TEST_CAPTURE_DIR=str(tmp_path),
        VERIFIER_TEST_ORIGINAL_REQUEST="Evidence must be posted in a PR comment.",
    )
    if hash_mode == "mixed":
        env["VERIFIER_TEST_LINKED_REQUEST"] = "Implement the authentic linked request."
    subprocess.run(
        [
            "node",
            "--test",
            "--test-name-pattern=explicit evaluation captures freeform evidence obligations",
            ".github/scripts/__tests__/agents-verifier-context.test.js",
        ],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
    )
    context = (tmp_path / "context.md").read_text()
    coverage_inventory = pr_verifier.parse_context_source_coverage(context)
    digest = coverage_inventory["acceptance_sources"][0]["original_body_sha256"]
    if hash_mode == "tampered":
        context = context.replace(digest, "0" * 64)
    else:
        if hash_mode == "mixed":
            assert len(coverage_inventory["acceptance_sources"]) == 2
        for record in (
            coverage_inventory["acceptance_sources"][:1]
            if hash_mode == "mixed"
            else coverage_inventory["acceptance_sources"]
        ):
            old = json.dumps(record["original_body_sha256"])
            if hash_mode == "null":
                context = context.replace(
                    '"original_body_sha256": ' + old, '"original_body_sha256": null'
                )
            else:
                context = context.replace(
                    '"original_body_sha256": ' + old, '"removed_original_hash": ' + old
                )
    coverage = pr_verifier.prompt_coverage(context, (tmp_path / "diff.patch").read_text())
    assert coverage.sufficient is False
    assert "Original request provenance does not match retained source bytes." in coverage.reasons
    assert pr_verifier._evaluation_optional_evidence_channels(context) == frozenset()
