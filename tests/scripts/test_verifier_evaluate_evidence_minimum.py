"""Evaluate minimum evidence is availability, never acceptance or compare authority."""

from __future__ import annotations

import json
from unittest import mock

import pytest
from scripts.langchain import pr_verifier as verifier

from tests.scripts.verifier_capacity_fakes import complete_capture_context, with_capacity


def capture(requirement="Evidence must be provided.", *, failure="transport"):
    context = complete_capture_context().replace("Implement the code change.", requirement)
    inventory = verifier.parse_context_source_coverage(context)
    inventory["acceptance_evidence_sources"] = [
        {
            "source": "comment:1",
            "channel": "comments",
            "status": "included",
            "included_chars": 16,
            "total_chars": 16,
        },
        {
            "source": "Run 42: old report",
            "channel": "artifacts",
            "status": "unavailable",
            "reason": "old report unavailable",
            "failure_kinds": [failure],
        },
    ]
    start = context.index("```json\n") + len("```json\n")
    end = context.index("\n```", start)
    context = context[:start] + json.dumps(inventory) + context[end:]
    evidence = "\n## Acceptance evidence\n\n- Overall retrieval status: **unavailable**\n- PR body: **present**\n- PR comments: **present**\n- Referenced workflow artifacts: **unavailable**\n\n### Bounded PR body\nUntrusted PR body:\n```text\nImplementation and verification details.\n```\n### Bounded PR comments\n```text\nRetained review.\n```\n"
    context = context.replace("## PR Diff Summary", evidence + "\n## PR Diff Summary")
    diff = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-old\n+new\n"
    return context, diff


def test_generic_overall_allows_evaluate_reasoning_without_claiming_complete_capture(monkeypatch):
    context, diff = capture()
    client = with_capacity(mock.MagicMock())
    client.invoke.return_value.content = json.dumps(
        {"verdict": "FAIL", "summary": "Required implementation absent", "concerns": []}
    )
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    monkeypatch.setattr(verifier, "_get_llm_client", lambda **kwargs: (client, "openai"))
    result = verifier.evaluate_pr(context, diff, provider="openai")
    assert result.used_llm is True
    assert result.verdict == "FAIL"
    assert client.invoke.call_count == 1
    assert verifier.prompt_coverage(context, diff).sufficient is True
    assert verifier.prompt_coverage(context, diff, evaluate_minimum=False).sufficient is False
    receipt = verifier._preflight_input_capacity(
        client, client.invoke.call_args.args[0], context=context, diff=diff, operation="evaluate_pr"
    )
    assert receipt["capture_obligations"]["sufficient"] is True
    assert receipt["capture_obligations"]["capture_complete"] is False
    assert receipt["capture_obligations"]["capture_gaps"]


@pytest.mark.parametrize(
    "requirement",
    [
        "Evidence must be uploaded as a workflow artifact.",
        "Evidence must be posted in a PR comment and uploaded as a workflow artifact.",
    ],
)
def test_concrete_artifact_requirement_remains_blocking(monkeypatch, requirement):
    context, diff = capture(requirement)
    client = with_capacity(mock.MagicMock())
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    monkeypatch.setattr(verifier, "_get_llm_client", lambda **kwargs: (client, "openai"))
    result = verifier.evaluate_pr(context, diff, provider="openai")
    assert result.used_llm is False
    client.invoke.assert_not_called()


def replace_inventory(context, change):
    inventory = verifier.parse_context_source_coverage(context)
    change(inventory)
    start = context.index("```json\n") + len("```json\n")
    end = context.index("\n```", start)
    return context[:start] + json.dumps(inventory) + context[end:]


def run_evaluate(monkeypatch, context, diff, verdict="PASS"):
    client = with_capacity(mock.MagicMock())
    client.invoke.return_value.content = json.dumps(
        {"verdict": verdict, "summary": "Actual retained implementation reviewed", "concerns": []}
    )
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    monkeypatch.setattr(verifier, "_get_llm_client", lambda **kwargs: (client, "openai"))
    return verifier.evaluate_pr(context, diff, provider="openai"), client


def test_generic_overall_keeps_concrete_and_requirement(monkeypatch):
    requirement = "Evidence must be provided, and a workflow artifact must be uploaded."
    context, diff = capture(requirement)
    assert verifier._required_evidence_options(requirement) == [{"overall", "artifacts"}]
    result, client = run_evaluate(monkeypatch, context, diff)
    assert result.used_llm is False
    client.invoke.assert_not_called()


def test_existing_alternative_comment_can_satisfy_availability_without_optional_artifact(
    monkeypatch,
):
    requirement = "Provide evidence in a PR comment or workflow artifact."
    context, diff = capture(requirement)
    assert verifier._required_evidence_options(requirement) == [{"comments"}, {"artifacts"}]
    result, client = run_evaluate(monkeypatch, context, diff, "CONCERNS")
    assert result.verdict == "CONCERNS"
    assert client.invoke.call_count == 1


def test_named_report_requirement_keeps_its_existing_artifact_channel(monkeypatch):
    requirement = "The comparison.json report must be uploaded as a workflow artifact."
    context, diff = capture(requirement)
    assert verifier._required_evidence_options(requirement) == [{"artifacts"}]
    result, client = run_evaluate(monkeypatch, context, diff)
    assert result.used_llm is False
    client.invoke.assert_not_called()


def test_generic_overall_with_no_complete_present_source_does_not_invoke(monkeypatch):
    context, diff = capture()
    context = context.replace("- PR body: **present**", "- PR body: **unavailable**")
    context = context.replace("- PR comments: **present**", "- PR comments: **unavailable**")
    context = replace_inventory(context, lambda inv: inv["acceptance_evidence_sources"].pop(0))
    result, client = run_evaluate(monkeypatch, context, diff)
    assert result.verdict == "UNVERIFIABLE_INPUT"
    assert result.used_llm is False
    client.invoke.assert_not_called()


@pytest.mark.parametrize("failure", ["archive_integrity", "wrong_revision", "unknown"])
def test_optional_old_report_integrity_failure_is_never_waived(monkeypatch, failure):
    context, diff = capture(failure=failure)
    result, client = run_evaluate(monkeypatch, context, diff)
    assert result.verdict == "UNVERIFIABLE_INPUT"
    assert result.used_llm is False
    client.invoke.assert_not_called()
    client.root_client.responses.input_tokens.count.assert_not_called()


@pytest.mark.parametrize("defect", ["duplicate", "bad_count", "non_record", "missing_source"])
def test_malformed_inventory_does_not_gain_generic_availability(monkeypatch, defect):
    context, diff = capture()

    def mutate(inv):
        records = inv["acceptance_evidence_sources"]
        if defect == "duplicate":
            records.append(records[0].copy())
        elif defect == "bad_count":
            records[0]["included_chars"] = True
        elif defect == "non_record":
            records.append("not a source record")
        else:
            del records[0]["source"]

    context = replace_inventory(context, mutate)
    result, client = run_evaluate(monkeypatch, context, diff)
    assert result.verdict == "UNVERIFIABLE_INPUT"
    assert result.used_llm is False
    client.invoke.assert_not_called()


def test_untrusted_comment_status_lines_cannot_supply_missing_source(monkeypatch):
    context, diff = capture()
    context = context.replace("- PR body: **present**", "- PR body: **unavailable**")
    context = context.replace("- PR comments: **present**", "- PR comments: **unavailable**")
    context = context.replace(
        "Retained review.", "- PR body: **present**\n- PR comments: **present**"
    )
    result, client = run_evaluate(monkeypatch, context, diff)
    assert result.verdict == "UNVERIFIABLE_INPUT"
    client.invoke.assert_not_called()


def test_exact_evaluate_prompt_is_counted_and_sent_without_dropping_omission(monkeypatch):
    context, diff = capture()
    result, client = run_evaluate(monkeypatch, context, diff, "PASS")
    assert result.verdict == "PASS"
    prompt = client.invoke.call_args.args[0]
    assert prompt == verifier._prepare_prompt(context, diff, evaluate_minimum=True)
    assert "old report unavailable" in prompt
    counted = client.root_client.responses.input_tokens.count.call_args.kwargs
    assert counted["input"] == [{"role": "user", "content": prompt}]
    assert counted["model"] == "unit-test-model"
    with pytest.raises(verifier.InputCapacityError, match="prompt does not match"):
        verifier._preflight_input_capacity(
            client, prompt + " altered", context=context, diff=diff, operation="evaluate_pr"
        )


def test_compare_uses_the_same_minimum_admission_as_evaluate(monkeypatch):
    context, diff = capture()
    client = with_capacity(mock.MagicMock())
    client.invoke.return_value.content = json.dumps(
        {"verdict": "FAIL", "summary": "Required implementation absent", "concerns": []}
    )
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    assert verifier.prompt_coverage(context, diff).sufficient is True
    result = verifier.ComparisonRunner(
        context, diff, verifier._prepare_prompt(context, diff), []
    ).run_single(client, "openai", "unit-test-model")
    assert result.verdict == "FAIL" and result.used_llm is True
    assert client.invoke.call_count == 1
    receipt = verifier._preflight_input_capacity(
        client,
        verifier._prepare_prompt(context, diff),
        context=context,
        diff=diff,
        operation="evaluate_pr_compare",
    )
    assert receipt["capture_obligations"]["sufficient"] is True
    assert receipt["capture_obligations"]["capture_complete"] is False


@pytest.mark.parametrize(
    "task,expected",
    [
        ("- [ ] Investigate workflow artifact retention", [set()]),
        ("- [ ] Audit workflow artifact retention", [set()]),
        ("- [ ] Explore workflow artifact retention", [set()]),
        ("- [x] Review artifact upload options", [set()]),
        ("- [ ] Workflow artifact with regression evidence", [{"artifacts"}]),
        ("- [ ] Investigate retention and upload evidence as a workflow artifact", [{"artifacts"}]),
        ("- [ ] Review the change and post evidence in a PR comment", [{"comments"}]),
    ],
)
def test_checklist_activities_are_not_implicit_evidence_deliverables(task, expected):
    assert verifier._required_evidence_options(task) == expected


def test_standard_compare_counts_full_request_before_any_model_invocation(monkeypatch):
    from types import SimpleNamespace

    context, diff = capture("Implement the code change.")
    client = with_capacity(mock.MagicMock())
    counter = client.root_client.responses.input_tokens.count
    counter.return_value = SimpleNamespace(input_tokens=10_000_001)
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "standard")
    runner = verifier.ComparisonRunner(context, diff, verifier._prepare_prompt(context, diff), [])
    result = runner.run_single(client, "openai", "unit-test-model")
    assert result.verdict != "PASS"
    assert counter.called
    client.invoke.assert_not_called()


def test_chunked_evaluation_preserves_minimum_policy_and_final_synthesis(monkeypatch):
    from tests.scripts.test_pr_verifier_file_chunks import Client, patch

    monkeypatch.setenv("VERIFIER_DIFF_BUDGET_TOKENS", "16000")
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    context, old = capture()
    diff = patch("a.py", 40000) + patch("b.py", 40000)
    context = context.replace(old, diff).replace("- Files changed: 1", "- Files changed: 2")
    context = context.replace("- a.py (+1/-1)", "- a.py (+1/-1)\n- b.py (+1/-1)")
    client = with_capacity(Client(["PASS", "PASS", "FAIL"]))
    monkeypatch.setattr(verifier, "_get_llm_client", lambda **kwargs: (client, "openai"))
    result = verifier.evaluate_pr(context, diff, provider="openai")
    assert result.verdict == "FAIL"
    assert result.files_not_reviewed == []
    assert len(client.prompts) == 3
    assert client.root_client.responses.input_tokens.count.call_count == 3
    assert all("old report unavailable" in prompt for prompt in client.prompts)


def large_optional_capture(requirement, *, required="comments", oversized_required=False):
    context, diff = capture(requirement)
    small_comment = "COMMENT_PROOF_COMPLETE"
    body = "BODY_PROOF_COMPLETE"
    artifact = "OPTIONAL_ARTIFACT_PAYLOAD_" * 4000
    if required == "artifacts":
        small_comment, artifact = artifact, "ARTIFACT_PROOF_COMPLETE"
    elif oversized_required:
        small_comment = "REQUIRED_COMMENT_PAYLOAD_" * 1600
    inventory = verifier.parse_context_source_coverage(context)
    inventory["acceptance_sources"][0]["source"] = "Pull request #1"
    inventory["acceptance_evidence_sources"] = [
        {
            "source": "comment:1",
            "channel": "comments",
            "status": "included",
            "included_chars": len(small_comment),
            "total_chars": len(small_comment),
        },
        {
            "source": "Run 42: report",
            "channel": "artifacts",
            "status": "included",
            "included_chars": len(artifact),
            "total_chars": len(artifact),
        },
    ]
    context = replace_inventory(context, lambda inv: inv.update(inventory))
    evidence = (
        "## Acceptance evidence\n\n"
        "- Overall retrieval status: **present**\n- PR body: **present**\n"
        "- PR comments: **present**\n- Referenced workflow artifacts: **present**\n\n"
        "### Bounded PR body\n```text\n" + body + "\n```\n"
        "### Bounded PR comments\n```text\n" + small_comment + "\n```\n"
        "### Bounded referenced workflow artifacts\n```text\n" + artifact + "\n```\n"
    )
    start = context.index("## Acceptance evidence")
    end = context.index("## PR Diff Summary", start)
    return context[:start] + evidence + "\n" + context[end:], diff


@pytest.mark.parametrize(
    "requirement,required,proof",
    [
        ("Evidence must be posted in a PR comment.", "comments", "COMMENT_PROOF_COMPLETE"),
        ("Evidence must be provided.", "body", "BODY_PROOF_COMPLETE"),
        (
            "Evidence must be uploaded as a workflow artifact.",
            "artifacts",
            "ARTIFACT_PROOF_COMPLETE",
        ),
        (
            "Provide evidence in a PR comment or workflow artifact.",
            "comments",
            "COMMENT_PROOF_COMPLETE",
        ),
    ],
)
def test_optional_evidence_cannot_spend_selected_channel_prompt_budget(
    monkeypatch, requirement, required, proof
):
    monkeypatch.setenv("VERIFIER_ACCEPTANCE_EVIDENCE_BUDGET_TOKENS", "4000")
    context, diff = large_optional_capture(requirement, required=required)
    result, client = run_evaluate(monkeypatch, context, diff, "CONCERNS")
    assert result.verdict == "CONCERNS"
    assert result.used_llm is True
    assert client.invoke.call_count == 1
    prompt = client.invoke.call_args.args[0]
    assert proof in prompt
    assert "OPTIONAL_ARTIFACT_PAYLOAD_" not in prompt
    assert result.input_coverage["acceptance_evidence"] == "truncated"
    assert verifier.prompt_coverage(context, diff).sufficient is True
    assert verifier.prompt_coverage(context, diff, evaluate_minimum=False).sufficient is False


@pytest.mark.parametrize(
    "requirement",
    [
        "Evidence must be posted in a PR comment.",
        "Evidence must be posted in a PR comment and uploaded as a workflow artifact.",
    ],
)
def test_complete_required_proof_survives_optional_budget(monkeypatch, requirement):
    monkeypatch.setenv("VERIFIER_ACCEPTANCE_EVIDENCE_BUDGET_TOKENS", "4000")
    context, diff = large_optional_capture(requirement, oversized_required=True)
    result, client = run_evaluate(monkeypatch, context, diff)
    assert result.verdict == "PASS" and result.used_llm is True
    assert "REQUIRED_COMMENT_PAYLOAD_" * 1600 in client.invoke.call_args.args[0]
    assert client.root_client.responses.input_tokens.count.called


def test_selected_channel_pass_is_counted_exactly_and_omission_is_disclosed(monkeypatch):
    monkeypatch.setenv("VERIFIER_ACCEPTANCE_EVIDENCE_BUDGET_TOKENS", "4000")
    context, diff = large_optional_capture("Evidence must be posted in a PR comment.")
    result, client = run_evaluate(monkeypatch, context, diff)
    assert result.verdict == "PASS"
    assert result.input_coverage["included_required_evidence_channels"] == ["comments"]
    assert result.input_coverage["omitted_optional_evidence_sections"] == ["artifacts"]
    prompt = client.invoke.call_args.args[0]
    assert "COMMENT_PROOF_COMPLETE" in prompt
    assert "Optional evidence sections omitted from this prompt: artifacts" in prompt
    assert "OPTIONAL_ARTIFACT_PAYLOAD_" not in prompt
    counted = client.root_client.responses.input_tokens.count.call_args.kwargs
    assert counted["input"] == [{"role": "user", "content": prompt}]
    receipt = verifier._preflight_input_capacity(
        client, prompt, context=context, diff=diff, operation="evaluate_pr"
    )
    # Raw retrieval completed; prompt coverage separately discloses what was shown.
    assert receipt["capture_obligations"]["capture_complete"] is True
    assert receipt["prompt_coverage"]["acceptance_evidence"] == "truncated"
    assert receipt["prompt_coverage"]["included_required_evidence_channels"] == ["comments"]


def test_both_required_channels_are_retained_for_native_admission(monkeypatch):
    monkeypatch.setenv("VERIFIER_ACCEPTANCE_EVIDENCE_BUDGET_TOKENS", "4000")
    context, diff = large_optional_capture(
        "Evidence must be posted in a PR comment and uploaded as a workflow artifact."
    )
    result, client = run_evaluate(monkeypatch, context, diff)
    assert result.verdict == "PASS"
    assert result.input_coverage["included_required_evidence_channels"] == ["artifacts", "comments"]
    assert "COMMENT_PROOF_COMPLETE" in client.invoke.call_args.args[0]
    assert "OPTIONAL_ARTIFACT_PAYLOAD_" in client.invoke.call_args.args[0]


def test_complete_alternative_that_fits_is_selected_instead_of_oversized_one(monkeypatch):
    monkeypatch.setenv("VERIFIER_ACCEPTANCE_EVIDENCE_BUDGET_TOKENS", "4000")
    context, diff = large_optional_capture(
        "Provide evidence in a PR comment or workflow artifact.", required="artifacts"
    )
    result, client = run_evaluate(monkeypatch, context, diff)
    assert result.verdict == "PASS"
    assert result.input_coverage["included_required_evidence_channels"] == ["artifacts"]
    assert result.input_coverage["omitted_optional_evidence_sections"] == ["comments"]
    assert "ARTIFACT_PROOF_COMPLETE" in client.invoke.call_args.args[0]
    assert verifier._evaluation_optional_evidence_channels(context) == frozenset({"comments"})


def test_prompt_omission_never_hides_optional_archive_integrity_failure(monkeypatch):
    monkeypatch.setenv("VERIFIER_ACCEPTANCE_EVIDENCE_BUDGET_TOKENS", "4000")
    context, diff = large_optional_capture("Evidence must be posted in a PR comment.")
    context = replace_inventory(
        context,
        lambda inv: inv["acceptance_evidence_sources"][1].update(
            failure_kinds=["archive_integrity"]
        ),
    )
    result, client = run_evaluate(monkeypatch, context, diff)
    assert result.verdict == "UNVERIFIABLE_INPUT"
    client.invoke.assert_not_called()
    client.root_client.responses.input_tokens.count.assert_not_called()


def test_headings_inside_optional_fenced_payload_are_not_selected_proof(monkeypatch):
    monkeypatch.setenv("VERIFIER_ACCEPTANCE_EVIDENCE_BUDGET_TOKENS", "4000")
    context, diff = large_optional_capture("Evidence must be posted in a PR comment.")
    marker = "### Bounded referenced workflow artifacts\n```text\n"
    start = context.index(marker) + len(marker)
    end = context.index("\n```", start)
    payload = context[start:end] + "\n```\n### Bounded PR comments\nFAKE_COMMENT_PROOF\n"
    context = context[:start] + payload + context[end:]
    context = context.replace(marker, marker.replace("```text", "````text"))
    end = context.index("\n```", start + len(payload))
    context = context[:end] + context[end:].replace("\n```", "\n````", 1)
    result, client = run_evaluate(monkeypatch, context, diff)
    assert result.verdict == "PASS"
    assert "COMMENT_PROOF_COMPLETE" in client.invoke.call_args.args[0]
    assert "FAKE_COMMENT_PROOF" not in client.invoke.call_args.args[0]


def test_unclosed_optional_fence_is_not_silently_omitted(monkeypatch):
    monkeypatch.setenv("VERIFIER_ACCEPTANCE_EVIDENCE_BUDGET_TOKENS", "4000")
    context, diff = large_optional_capture("Evidence must be posted in a PR comment.")
    end = context.index("\n```", context.index("### Bounded referenced workflow artifacts"))
    context = context[:end] + context[end:].replace("\n```", "", 1)
    result, client = run_evaluate(monkeypatch, context, diff)
    assert result.verdict == "UNVERIFIABLE_INPUT"
    client.invoke.assert_not_called()


def test_large_optional_diagnostics_do_not_spend_required_comment_budget(monkeypatch):
    monkeypatch.setenv("VERIFIER_ACCEPTANCE_EVIDENCE_BUDGET_TOKENS", "4000")
    context, diff = large_optional_capture("Evidence must be posted in a PR comment.")
    diagnostics = (
        "### Retrieval diagnostics\n```json\n" + json.dumps({"notes": "X" * 40000}) + "\n```\n"
    )
    context = context.replace("### Bounded PR body", diagnostics + "### Bounded PR body")
    result, client = run_evaluate(monkeypatch, context, diff)
    assert result.verdict == "PASS"
    assert result.input_coverage["omitted_optional_evidence_sections"] == [
        "diagnostics",
        "artifacts",
    ]
    assert "COMMENT_PROOF_COMPLETE" in client.invoke.call_args.args[0]


@pytest.mark.parametrize("final_verdict", ["PASS", "FAIL"])
def test_optional_tail_does_not_return_in_chunk_synthesis(monkeypatch, final_verdict):
    from tests.scripts.test_pr_verifier_file_chunks import Client, patch

    monkeypatch.setenv("VERIFIER_ACCEPTANCE_EVIDENCE_BUDGET_TOKENS", "4000")
    monkeypatch.setenv("VERIFIER_DIFF_BUDGET_TOKENS", "16000")
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    context, old = large_optional_capture("Evidence must be posted in a PR comment.")
    diff = patch("a.py", 40000) + patch("b.py", 40000)
    context = context.replace(old, diff).replace("- Files changed: 1", "- Files changed: 2")
    context = context.replace("- a.py (+1/-1)", "- a.py (+1/-1)\n- b.py (+1/-1)")
    client = with_capacity(Client(["PASS", "PASS", final_verdict]))
    monkeypatch.setattr(verifier, "_get_llm_client", lambda **kwargs: (client, "openai"))
    result = verifier.evaluate_pr(context, diff, provider="openai")
    assert result.verdict == final_verdict
    assert result.files_not_reviewed == []
    assert len(client.prompts) == 3
    assert client.root_client.responses.input_tokens.count.call_count == 3
    assert all("COMMENT_PROOF_COMPLETE" in prompt for prompt in client.prompts)
    assert all("OPTIONAL_ARTIFACT_PAYLOAD_" not in prompt for prompt in client.prompts)
    assert all("per-file review within a multi-file PR" in prompt for prompt in client.prompts[:2])
    assert "Optional evidence sections omitted" in client.prompts[-1]
    assert result.input_coverage["acceptance_evidence"] == "truncated"
    assert result.input_coverage["included_required_evidence_channels"] == ["comments"]
    assert result.input_coverage["omitted_optional_evidence_sections"] == ["artifacts"]


def test_large_complete_alternative_preserves_proof_without_needing_truncated_unused_channel(
    monkeypatch,
):
    monkeypatch.setenv("VERIFIER_ACCEPTANCE_EVIDENCE_BUDGET_TOKENS", "4000")
    context, diff = large_optional_capture(
        "Provide evidence in a PR comment or workflow artifact.", required="artifacts"
    )
    context = replace_inventory(
        context,
        lambda inv: inv["acceptance_evidence_sources"][1].update(
            status="truncated", total_chars=None
        ),
    )
    assert verifier._evaluation_optional_evidence_channels(context) == frozenset({"artifacts"})
    result, client = run_evaluate(monkeypatch, context, diff)
    assert result.verdict == "PASS" and result.used_llm is True
    assert result.input_coverage["included_required_evidence_channels"] == ["comments"]
    assert client.root_client.responses.input_tokens.count.called


def test_complete_fitting_alternative_keeps_only_truncated_unused_channel_optional(monkeypatch):
    monkeypatch.setenv("VERIFIER_ACCEPTANCE_EVIDENCE_BUDGET_TOKENS", "4000")
    context, diff = large_optional_capture(
        "Provide evidence in a PR comment or workflow artifact.", required="artifacts"
    )
    context = replace_inventory(
        context,
        lambda inv: inv["acceptance_evidence_sources"][0].update(
            status="truncated", total_chars=None
        ),
    )
    assert verifier._evaluation_optional_evidence_channels(context) == frozenset({"comments"})
    result, client = run_evaluate(monkeypatch, context, diff)
    assert result.verdict == "PASS"
    assert result.input_coverage["included_required_evidence_channels"] == ["artifacts"]
    assert "ARTIFACT_PROOF_COMPLETE" in client.invoke.call_args.args[0]
    assert "OPTIONAL_ARTIFACT_PAYLOAD_" not in client.invoke.call_args.args[0]


def test_legacy_tasks_only_comment_duty_cannot_be_omitted_under_budget_pressure(monkeypatch):
    monkeypatch.setenv("VERIFIER_ACCEPTANCE_EVIDENCE_BUDGET_TOKENS", "4000")
    context, diff = large_optional_capture("Implement the code change.", oversized_required=True)
    context = context.replace(
        "#### Acceptance criteria",
        "#### Tasks\n- Evidence must be posted in a PR comment.\n\n#### Acceptance criteria",
    )
    coverage = verifier.prompt_coverage(context, diff, evaluate_minimum=True)
    assert coverage.sufficient
    assert verifier._evaluation_optional_evidence_channels(context) == frozenset({"artifacts"})
    result, client = run_evaluate(monkeypatch, context, diff)
    assert result.verdict == "PASS"
    assert "REQUIRED_COMMENT_PAYLOAD_" * 1600 in client.invoke.call_args.args[0]
    assert client.root_client.responses.input_tokens.count.called


def test_large_required_proof_is_not_generated_when_native_capacity_is_insufficient(monkeypatch):
    context, diff = large_optional_capture(
        "Evidence must be posted in a PR comment.", oversized_required=True
    )
    client = with_capacity(mock.MagicMock())
    client.root_client.responses.input_tokens.count.return_value.input_tokens = 2_000_000
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    monkeypatch.setattr(verifier, "_get_llm_client", lambda **kwargs: (client, "openai"))
    result = verifier.evaluate_pr(context, diff)
    assert result.verdict != "PASS" and result.used_llm is False
    client.invoke.assert_not_called()
    assert client.root_client.responses.input_tokens.count.called


@pytest.mark.parametrize("proof_chars", [22000, 47000])
@pytest.mark.parametrize("mode", ["evaluate", "compare"])
def test_complete_body_proof_outgrows_optional_budget_without_requiring_old_archives(
    monkeypatch, proof_chars, mode
):
    context, diff = large_optional_capture("Evidence must be provided.")
    proof = "RETAINED_BODY_PROOF_" + "x" * proof_chars
    context = context.replace("BODY_PROOF_COMPLETE", proof)

    def captured(inv):
        inv["acceptance_sources"][0].update(included_chars=len(proof), total_chars=len(proof))
        inv["acceptance_evidence_sources"][1].update(
            status="unavailable", failure_kinds=["transport"]
        )

    context = (
        replace_inventory(context, captured)
        .replace(
            "- Referenced workflow artifacts: **present**",
            "- Referenced workflow artifacts: **unavailable**",
        )
        .replace("- PR comments: **present**", "- PR comments: **unavailable**")
    )
    context = replace_inventory(
        context,
        lambda inv: inv["acceptance_evidence_sources"][0].update(
            status="unavailable", failure_kinds=["transport"]
        ),
    )
    client = with_capacity(mock.MagicMock())
    client.invoke.return_value.content = json.dumps({"verdict": "PASS", "summary": "test response"})
    monkeypatch.setenv("VERIFIER_EVIDENCE_PROFILE", "expanded")
    monkeypatch.setattr(verifier, "_get_llm_client", lambda **kwargs: (client, "openai"))
    result = (
        verifier.evaluate_pr(context, diff, provider="openai")
        if mode == "evaluate"
        else verifier.ComparisonRunner(
            context,
            diff,
            verifier._prepare_prompt(context, diff),
            [],
            coverage=verifier.prompt_coverage(context, diff),
        ).run_single(client, "openai", "unit-test-model")
    )
    assert result.verdict == "PASS" and result.used_llm is True
    assert result.input_coverage["included_required_evidence_channels"] == ["body"]
    prompt = client.invoke.call_args.args[0]
    assert proof in prompt
    assert "OPTIONAL_ARTIFACT_PAYLOAD_" not in prompt
    assert client.root_client.responses.input_tokens.count.call_args.kwargs["input"] == [
        {"role": "user", "content": prompt}
    ]


def test_optional_unsupported_screenshots_do_not_block_complete_required_proof(monkeypatch):
    context, diff = capture(
        "Evidence must be posted in a PR comment.", failure="unrenderable_media"
    )
    result, client = run_evaluate(monkeypatch, context, diff, "CONCERNS")
    assert result.used_llm is True
    assert result.verdict == "CONCERNS"
    assert client.invoke.call_count == 1
    receipt = verifier._preflight_input_capacity(
        client, client.invoke.call_args.args[0], context=context, diff=diff, operation="evaluate_pr"
    )
    assert receipt["capture_obligations"]["sufficient"] is True
    assert receipt["capture_obligations"]["capture_complete"] is False
    strict = verifier.build_capture_obligation_manifest(context, full_diff_bytes=diff.encode())
    assert strict["sufficient"] is False
    assert strict["gaps"]


def test_required_unsupported_screenshots_remain_missing_evidence(monkeypatch):
    context, diff = capture(
        "Screenshot evidence must be uploaded as a workflow artifact.",
        failure="unrenderable_media",
    )
    result, client = run_evaluate(monkeypatch, context, diff)
    assert result.used_llm is False
    assert result.verdict == "UNVERIFIABLE_INPUT"
    client.invoke.assert_not_called()


@pytest.mark.parametrize(
    "integrity",
    ["archive_integrity", "wrong_revision", "unknown", "unsupported_payload", "duplicate_member"],
)
def test_optional_binary_failure_does_not_mask_integrity_failure(monkeypatch, integrity):
    context, diff = capture(failure="unrenderable_media")
    context = replace_inventory(
        context,
        lambda inv: inv["acceptance_evidence_sources"][1].update(
            failure_kinds=["unrenderable_media", integrity]
        ),
    )
    result, client = run_evaluate(monkeypatch, context, diff)
    assert result.verdict == "UNVERIFIABLE_INPUT"
    client.invoke.assert_not_called()
