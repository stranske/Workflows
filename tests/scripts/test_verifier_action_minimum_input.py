"""Single-provider admission separates usable input from complete enrichment."""

import json
import re
from unittest import mock

import pytest
from scripts.langchain import pr_verifier
from tools.verifier_capture_obligation_manifest import (
    build_capture_obligation_manifest,
    parse_context_source_coverage,
)

from tests.scripts.test_native_capacity_recovery import native as _native_fixture
from tests.scripts.verifier_capacity_fakes import complete_capture_context

native = _native_fixture


@pytest.mark.parametrize("channel", [[], {}])
def test_malformed_channel_is_a_recoverable_gap_even_before_preflight(channel):
    text = context(
        "- Implement the code change.",
        change=lambda record, coverage: record.update(channel=channel),
    )
    manifest = build_capture_obligation_manifest(text)
    assert not manifest["sufficient"]
    assert "acceptance_evidence:Run 7: coverage:truncated" in manifest["gaps"]


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
        lambda record, coverage: record.update(failure_kinds=None),
        lambda record, coverage: record.update(included_chars=-1),
        lambda record, coverage: coverage["changed_code_sources"][0].update(status="truncated"),
        lambda record, coverage: coverage["acceptance_sources"][0].update(status="unavailable"),
    ],
)
def test_legacy_integrity_and_core_gaps_remain_blocking(native, change):
    with pytest.raises(pr_verifier.InputCapacityError, match="capture obligation gaps"):
        check(native, context("- Implement the code change.", change=change))
    native[3].assert_not_called()


@pytest.mark.parametrize(
    "kinds",
    [
        ["provenance"],
        ["duplicate_member"],
        ["retrieval"],
        ["extraction_byte_or_read"],
        ["unknown"],
        "retrieval",
        [None],
        [],
    ],
)
def test_optional_evidence_integrity_failures_still_block(native, kinds):
    text = context(
        "- Implement the code change.",
        change=lambda record, coverage: record.update(status="unavailable", failure_kinds=kinds),
    )
    with pytest.raises(pr_verifier.InputCapacityError, match="capture obligation gaps"):
        check(native, text)
    native[3].assert_not_called()


def test_included_record_cannot_hide_integrity_failure(native):
    text = context(
        "- Implement the code change.",
        change=lambda record, coverage: record.update(
            status="included", total_chars=10, failure_kinds=["provenance"]
        ),
    )
    with pytest.raises(pr_verifier.InputCapacityError, match="capture obligation gaps"):
        check(native, text)
    native[3].assert_not_called()


@pytest.mark.parametrize("kinds", [["transport"], ["character", "extraction_byte"]])
def test_typed_optional_availability_failure_allows_reasoning(native, kinds):
    text = context(
        "- Implement the code change.",
        change=lambda record, coverage: record.update(status="unavailable", failure_kinds=kinds),
    )
    assert check(native, text)["status"] == "PASS"


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


@pytest.mark.parametrize(
    "case",
    [
        "corrupt_zip",
        "duplicate_comments",
        "mixed_inventory",
        "incidental_revision",
        "explicit_revision",
        "transport",
        "byte_bound",
    ],
)
def test_real_collector_failures_reach_the_same_admission_screen(native, case):
    """Corrupt source transport and bounded omission retain distinct meanings."""
    import base64
    import io
    import subprocess
    import zipfile

    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("proof.txt", "unique-proof-" + "x" * 200)
    archive_bytes = raw.getvalue()
    if case == "corrupt_zip":
        archive_bytes = archive_bytes.replace(b"unique-proof-", b"broken-proof-", 1)
    script = r"""
const {fetchVerifierEvidence, buildContextSourceCoverage} = require('./.github/scripts/agents_verifier_context.js');
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const sha = 'a'.repeat(40);
let downloads = 0;
if (input.case === 'byte_bound') process.env.VERIFIER_EVIDENCE_ARTIFACT_CHARS = '30';
const github = {rest: {
  issues: {listComments: async () => {
    if (input.case === 'transport') throw Object.assign(new Error('rate limited'), {status: 429});
    return {data: input.case === 'duplicate_comments' ? [{id: 1, body: 'proof'}, {id: 1, body: 'proof'}] : []};
  }},
  pulls: {listReviewComments: async () => ({data: []}), listReviews: async () => ({data: []})},
  actions: {
    getWorkflowRun: async () => ({data: {id: 7, head_sha: ['incidental_revision', 'explicit_revision'].includes(input.case) ? 'b'.repeat(40) : sha}}),
    listWorkflowRunsForRepo: async () => ({data: {workflow_runs: [], total_count: 0}}),
    listWorkflowRuns: async ({workflow_id}) => {
      if (workflow_id === 'first') return {data: {workflow_runs: 'malformed'}};
      throw Object.assign(new Error('rate limited'), {status: 429});
    },
    listWorkflowRunArtifacts: async () => ({data: {artifacts: [{id: 8, name: 'proof', size_in_bytes: 1000}], total_count: 1}}),
    downloadArtifact: async () => {downloads += 1; return {data: Buffer.from(input.archive, 'base64')};},
  },
}};
(async () => {
  const evidence = await fetchVerifierEvidence({github, owner: 'o', repo: 'r', pullNumber: 1,
    pullRequestBody: (input.case === 'explicit_revision' ? 'Evidence run: ' : '') + 'https://github.com/o/r/actions/runs/7', associatedCommitShas: [sha],
    workflows: input.case === 'mixed_inventory' ? ['first', 'second'] : []});
  const coverage = buildContextSourceCoverage({planSources: [], diffText: '', evidence});
  console.log(JSON.stringify({records: coverage.acceptance_evidence_sources, references: evidence.diagnostics.references, downloads}));
})();
"""
    result = subprocess.run(
        ["node", "-e", script],
        input=json.dumps({"case": case, "archive": base64.b64encode(archive_bytes).decode()}),
        text=True,
        capture_output=True,
        check=True,
    )
    collected = json.loads(result.stdout)
    records = collected["records"]
    if case == "incidental_revision":
        assert collected["downloads"] == 0
    if case == "explicit_revision":
        assert collected["downloads"] == 0
    text = context("- Implement the code change.")
    coverage = parse_context_source_coverage(text)
    coverage["acceptance_evidence_sources"] = records
    text = re.sub(r"(?<=```json\n).*?(?=\n```)", json.dumps(coverage), text, count=1, flags=re.S)
    if case in {"corrupt_zip", "duplicate_comments", "mixed_inventory", "explicit_revision"}:
        with pytest.raises(pr_verifier.InputCapacityError, match="capture obligation gaps"):
            check(native, text)
        native[3].assert_not_called()
    else:
        assert check(native, text)["status"] == "PASS"
        if case == "incidental_revision":
            assert collected["references"]["excluded_incidental_runs"] == [
                {"run_id": 7, "head_sha": "b" * 40, "reason": "different_revision"}
            ]
