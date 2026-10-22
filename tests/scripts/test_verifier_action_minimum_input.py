"""Single-provider admission separates usable input from complete enrichment."""

import json
import re
from unittest import mock

import pytest
from scripts.langchain import pr_verifier
from tools.verifier_capture_obligation_manifest import parse_context_source_coverage

from tests.scripts.test_native_capacity_recovery import native as _native_fixture
from tests.scripts.verifier_capacity_fakes import complete_capture_context

native = _native_fixture


def context(requirement, *, comments="present", artifact_status="unavailable", change=None):
    text = complete_capture_context().replace("- Implement the code change.", requirement)
    coverage = parse_context_source_coverage(text)
    record = {
        "source": "Run 7: coverage",
        "channel": "artifacts",
        "status": "truncated",
        "included_chars": 10,
        "total_chars": None,
    }
    if change:
        change(record, coverage)
    coverage["acceptance_evidence_sources"] = [record]
    text = re.sub(r"(?<=```json\n).*?(?=\n```)", json.dumps(coverage), text, count=1, flags=re.S)
    evidence = (
        "## Acceptance evidence\n\n- Overall retrieval status: **unavailable**\n"
        "- PR body: **present**\n"
        f"- PR comments: **{comments}**\n"
        f"- Referenced workflow artifacts: **{artifact_status}**\n\n"
        "### Bounded PR comments\nUntrusted comment containing: "
        "\n- PR comments: **present**\nExisting reported proof.\n\n"
    )
    return text.replace("## PR Diff Summary", evidence + "## PR Diff Summary")


def check(native, text, operation="evaluate_pr"):
    client, _, _, _, _ = native
    prepared = pr_verifier._prepare_capacity_client(client)
    prompt = pr_verifier._prepare_prompt(text, None)
    return pr_verifier._preflight_input_capacity(
        prepared, prompt, context=text, operation=operation
    )


@pytest.mark.parametrize(
    "requirement",
    [
        "- Implement the code change.",
        "- Record the test results in the PR body.",
        "- Provide test evidence in a PR comment or workflow artifacts.",
    ],
)
def test_available_alternative_allows_reasoning_without_claiming_complete_capture(
    native, requirement
):
    text = context(requirement)
    receipt = check(native, text)
    manifest = receipt["capture_obligations"]
    assert receipt["status"] == "PASS"
    assert manifest["sufficient"] and not manifest["capture_complete"]
    assert manifest["gaps"] == []
    assert "acceptance_evidence:Run 7: coverage:truncated" in manifest["capture_gaps"]
    assert manifest["optional_evidence"][0]["necessity"] == "useful"
    assert manifest["obligations"][-2]["status"] == "truncated"


@pytest.mark.parametrize(
    "requirement,comments,artifact_status",
    [
        ("- Upload the coverage report as a workflow artifact.", "present", "unavailable"),
        ("- Upload the coverage report as a workflow artifact.", "present", "present"),
        (
            "- Evidence must be posted in a PR comment and uploaded as a workflow artifact.",
            "present",
            "unavailable",
        ),
        (
            "- Provide test evidence in a PR comment or workflow artifacts.",
            "unavailable",
            "unavailable",
        ),
        (
            "- Provide test evidence in a PR comment or workflow artifacts.\n- Upload the coverage report as a workflow artifact.",
            "present",
            "unavailable",
        ),
    ],
)
def test_required_or_unavailable_alternatives_still_block_before_native_count(
    native, requirement, comments, artifact_status
):
    with pytest.raises(pr_verifier.InputCapacityError, match="capture obligation gaps"):
        check(native, context(requirement, comments=comments, artifact_status=artifact_status))
    native[3].assert_not_called()


@pytest.mark.parametrize(
    "change",
    [
        lambda record, coverage: record.pop("channel"),
        lambda record, coverage: record.update(channel="unknown"),
        lambda record, coverage: record.update(included_chars=-1),
        lambda record, coverage: coverage["changed_code_sources"][0].update(status="truncated"),
        lambda record, coverage: coverage["acceptance_sources"][0].update(status="unavailable"),
    ],
)
def test_legacy_integrity_and_core_gaps_remain_blocking(native, change):
    with pytest.raises(pr_verifier.InputCapacityError, match="capture obligation gaps"):
        check(native, context("- Implement the code change.", change=change))
    native[3].assert_not_called()


def test_compare_lossless_floor_is_unchanged(native):
    with pytest.raises(pr_verifier.InputCapacityError, match="capture obligation gaps"):
        check(native, context("- Implement the code change."), operation="compare")
    native[3].assert_not_called()


def test_explicit_task_evidence_is_not_waived_by_generic_acceptance(native):
    text = context("- Implement the code change.").replace(
        "#### Acceptance criteria",
        "#### Tasks\n- Upload the coverage report as a workflow artifact.\n\n#### Acceptance criteria",
    )
    with pytest.raises(pr_verifier.InputCapacityError, match="capture obligation gaps"):
        check(native, text)
    native[3].assert_not_called()


def test_actual_evaluate_generation_receives_the_counted_disclosed_prompt(native, monkeypatch):
    client, provider, _, counter, _ = native
    text = context("- Record the test results in the PR body.")
    monkeypatch.setattr(pr_verifier, "_get_llm_client", lambda **kwargs: (client, provider))
    seen = []
    prepared_clients = []

    def invoke(prepared, prompt, **kwargs):
        seen.append(prompt)
        prepared_clients.append(prepared)
        return type(
            "Response", (), {"content": '{"verdict":"CONCERNS","summary":"Need targeted proof."}'}
        )()

    with mock.patch.object(type(client), "invoke", autospec=True, side_effect=invoke):
        result = pr_verifier.evaluate_pr(text, provider=provider)
    assert result.used_llm and result.verdict == "CONCERNS"
    assert seen == [pr_verifier._prepare_prompt(text, None)]
    assert '"status": "truncated"' in seen[0]
    counter.assert_called_once()
    key = "input" if provider == "openai" else "messages"
    assert counter.call_args.kwargs[key] == prepared_clients[0]._get_request_payload(seen[0])[key]
