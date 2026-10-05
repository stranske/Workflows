"""Exercise the actual JavaScript evidence producer through Python verdict flooring."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from scripts.langchain import pr_verifier

from tests.scripts.test_pr_verifier_prompt_coverage import ACCEPTANCE_SENTINEL, _context

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")


@pytest.mark.parametrize("operation", ["submit", "deliver", "record", "post"])
@pytest.mark.parametrize(
    "noun",
    [
        "validation evidence",
        "before/after evidence",
        "test transcript",
        "validation command output",
    ],
)
def test_qualified_body_delivery_cannot_use_another_present_channel(operation, noun):
    criterion = f"The reviewer must {operation} {noun} in the PR body"
    assert pr_verifier._required_evidence_channels(criterion) == {"body"}
    for body_status in ("absent", "unavailable", "present"):
        evidence = (
            "Overall retrieval status: **present**\n"
            f"- PR body: **{body_status}**\n"
            "- PR comments: **present**\n"
            "- Referenced workflow artifacts: **present**\n"
        )
        assert pr_verifier._required_evidence_is_missing(evidence, {"body"}) == (
            body_status != "present"
        )


@pytest.mark.parametrize(
    "criterion",
    [
        "The reviewer may submit validation evidence in the PR body",
        "The reviewer must not submit validation evidence in the PR body",
        "The UI lets users submit validation evidence in the PR body editor",
    ],
)
def test_qualified_body_delivery_preserves_optional_negative_and_product_boundaries(criterion):
    assert pr_verifier._required_evidence_channels(criterion) == set()


@pytest.mark.skipif(NODE is None, reason="Node is required for producer integration")
@pytest.mark.parametrize("expired", [False, True])
def test_complete_explicit_artifact_reaches_the_artifact_floor(expired):
    script = r"""
const {fetchVerifierEvidence,formatVerifierEvidence}=require('./.github/scripts/agents_verifier_context.js');
const expired=JSON.parse(require('fs').readFileSync(0,'utf8'));
const empty=async()=>({data:[]}), sha='a'.repeat(40);
const github={rest:{issues:{listComments:empty},pulls:{listReviewComments:empty,listReviews:empty},actions:{
  getWorkflowRun:async()=>({data:{id:123,head_sha:sha}}),
  listWorkflowRunsForRepo:async()=>({data:{total_count:9,workflow_runs:[{id:124,head_sha:sha}]}}),
  listWorkflowRunArtifacts:async()=>({data:{total_count:1,artifacts:[{id:9,size_in_bytes:10,expired}]}}),
  downloadArtifact:async()=>({data:Buffer.from('zip')})}}};
fetchVerifierEvidence({github,owner:'owner',repo:'repo',pullNumber:1,pullRequestBody:'',
  associatedCommitShas:[sha],evidenceTexts:['https://github.com/owner/repo/actions/runs/123'],
  extractArtifactText:()=>({text:'RED then GREEN',truncated:false})})
  .then(e=>process.stdout.write(JSON.stringify({status:e.artifacts.status,markdown:formatVerifierEvidence(e)})))
  .catch(e=>{console.error(e);process.exit(1)});
"""
    produced = json.loads(
        subprocess.check_output(
            [NODE, "-e", script], cwd=ROOT, input=json.dumps(expired), text=True
        )
    )
    assert produced["status"] == ("unavailable" if expired else "present")
    context, _ = _context(1, 1000, 1000)
    context = context.replace(ACCEPTANCE_SENTINEL, "Upload a workflow artifact").replace(
        "## PR Diff Summary", produced["markdown"] + "\n\n## PR Diff Summary"
    )
    result = pr_verifier._apply_coverage_floor(
        pr_verifier.EvaluationResult(verdict="PASS", used_llm=True),
        pr_verifier.prompt_coverage(context, None),
    )
    assert result.verdict == ("CONCERNS" if expired else "PASS")


@pytest.mark.skipif(NODE is None, reason="Node is required for producer integration")
@pytest.mark.parametrize("comment", ["Validation evidence: command passed", ""])
@pytest.mark.parametrize(
    "channel,criterion",
    [
        ("overall", "Provide validation evidence"),
        ("comments", "Post evidence in a PR comment"),
        ("artifacts", "Upload a workflow artifact"),
    ],
)
def test_complete_comment_is_sufficient_only_for_generic_or_comment_evidence(
    comment, channel, criterion
):
    """An expired artifact cannot veto a different complete evidence channel."""
    script = r"""
const {fetchVerifierEvidence,formatVerifierEvidence}=require('./.github/scripts/agents_verifier_context.js');
const input=JSON.parse(require('fs').readFileSync(0,'utf8'));
const empty=async()=>({data:[]});
const sha='a'.repeat(40);
const github={rest:{issues:{listComments:async()=>({data:input.comment?[{id:1,body:input.comment}]:[]})},
  pulls:{listReviewComments:empty,listReviews:empty},actions:{
  listWorkflowRunsForRepo:async()=>({data:{workflow_runs:[{id:2,head_sha:sha}],total_count:1}}),
  listWorkflowRunArtifacts:async()=>({data:{artifacts:[{id:3,expired:true}],total_count:1}}),
  downloadArtifact:async()=>{throw Error('Expired artifacts must not be downloaded')}}}};
fetchVerifierEvidence({github,owner:'owner',repo:'repo',pullNumber:1,evidenceTexts:[],
  pullRequestBody:'',associatedCommitShas:[sha]})
.then(e=>process.stdout.write(JSON.stringify({status:e.status,artifacts:e.artifacts.status,markdown:formatVerifierEvidence(e)})))
.catch(e=>{console.error(e);process.exit(1)});
"""
    produced = json.loads(
        subprocess.check_output(
            [NODE, "-e", script], cwd=ROOT, input=json.dumps({"comment": comment}), text=True
        )
    )
    assert produced["artifacts"] == "unavailable"
    assert produced["status"] == ("present" if comment else "unavailable")
    assert pr_verifier._required_evidence_channels("- [ ] " + criterion) == {channel}
    context, _ = _context(1, 1000, 1000)
    context = context.replace(ACCEPTANCE_SENTINEL, criterion).replace(
        "## PR Diff Summary", produced["markdown"] + "\n\n## PR Diff Summary"
    )
    result = pr_verifier._apply_coverage_floor(
        pr_verifier.EvaluationResult(verdict="PASS", used_llm=True),
        pr_verifier.prompt_coverage(context, None),
    )
    assert result.verdict == (
        "PASS" if comment and channel in {"overall", "comments"} else "CONCERNS"
    )


@pytest.mark.skipif(NODE is None, reason="Node is required for producer integration")
@pytest.mark.parametrize(
    "body,status",
    [("Before/after evidence: RED then GREEN", "present"), ("", "absent"), (None, "unavailable")],
)
@pytest.mark.parametrize(
    "criterion,channel",
    [
        ("The PR must include before/after evidence", "overall"),
        ("Evidence in the PR body is required", "body"),
        ("The reviewer must paste command output into a PR comment", "comments"),
        ("The reviewer must upload evidence to a workflow artifact", "artifacts"),
    ],
)
def test_body_availability_reaches_generic_and_specific_evidence_floors(
    body, status, criterion, channel
):
    """Body retrieval counts generically without satisfying another channel."""
    script = r"""
const {fetchVerifierEvidence,formatVerifierEvidence}=require('./.github/scripts/agents_verifier_context.js');
const input=JSON.parse(require('fs').readFileSync(0,'utf8'));
const empty=async()=>({data:[]});
const github={rest:{issues:{listComments:empty},pulls:{listReviewComments:empty,listReviews:empty}}};
fetchVerifierEvidence({github,owner:'owner',repo:'repo',pullNumber:1,evidenceTexts:[],
  pullRequestBody: input.body === null ? undefined : input.body})
.then(e=>process.stdout.write(JSON.stringify({status:e.status,markdown:formatVerifierEvidence(e)})))
.catch(e=>{console.error(e);process.exit(1)});
"""
    produced = json.loads(
        subprocess.check_output(
            [NODE, "-e", script], cwd=ROOT, input=json.dumps({"body": body}), text=True
        )
    )
    assert produced["status"] == status
    assert pr_verifier._required_evidence_channels("- [ ] " + criterion) == {channel}
    context, _ = _context(1, 1000, 1000)
    context = context.replace(ACCEPTANCE_SENTINEL, criterion).replace(
        "## PR Diff Summary", produced["markdown"] + "\n\n## PR Diff Summary"
    )
    result = pr_verifier._apply_coverage_floor(
        pr_verifier.EvaluationResult(verdict="PASS", used_llm=True),
        pr_verifier.prompt_coverage(context, None),
    )
    expected = "PASS" if channel in {"overall", "body"} and status == "present" else "CONCERNS"
    assert result.verdict == expected
