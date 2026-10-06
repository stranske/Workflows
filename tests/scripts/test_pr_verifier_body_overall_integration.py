"""Exercise the actual JavaScript evidence producer through Python verdict flooring."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from scripts.langchain import pr_verifier

from tests.scripts.test_pr_verifier_prompt_coverage import ACCEPTANCE_SENTINEL, _context

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")


@pytest.mark.parametrize("status", ["absent", "unavailable", "present"])
@pytest.mark.parametrize("case", ["pronoun", "unrelated", "compound"])
def test_proof_actor_and_comment_compound_actual_floor(status, case):
    criterion, channel = {
        "pronoun": (
            "The UI must display test results, and the reviewer must record them in the PR body",
            "body",
        ),
        "unrelated": (
            "The UI must display test results, and the automation agent must update the PR body",
            "body",
        ),
        "compound": ("The PR must include a comment button", "comments"),
    }[case]
    states = {"body": "present", "comments": "present"}
    states[channel] = status
    evidence = (
        "Overall retrieval status: **present**\n"
        f"- PR body: **{states['body']}**\n"
        f"- PR comments: **{states['comments']}**\n"
        "- Referenced workflow artifacts: **absent**\n"
    )
    context, _ = _context(1, 1000, 1000)
    context = context.replace(ACCEPTANCE_SENTINEL, criterion).replace(
        "## PR Diff Summary", "## Acceptance evidence\n\n- " + evidence + "\n## PR Diff Summary"
    )
    result = pr_verifier._apply_coverage_floor(
        pr_verifier.EvaluationResult(verdict="PASS", used_llm=True),
        pr_verifier.prompt_coverage(context, None),
    )
    assert result.verdict == ("CONCERNS" if case == "pronoun" and status != "present" else "PASS")


@pytest.mark.parametrize("status", ["absent", "unavailable", "present"])
@pytest.mark.parametrize("governor", ["must", "must not", "is not expected to"])
@pytest.mark.parametrize(
    "destination,channel",
    [
        ("the PR body", "body"),
        ("a PR comment", "comments"),
        ("workflow artifacts", "artifacts"),
    ],
)
def test_qualified_recording_actual_floor(status, governor, destination, channel):
    criterion = f"A recording of the session {governor} be in {destination}"
    channels = {"body": "present", "comments": "present", "artifacts": "present"}
    channels[channel] = status
    evidence = (
        "Overall retrieval status: **present**\n"
        f"- PR body: **{channels['body']}**\n"
        f"- PR comments: **{channels['comments']}**\n"
        f"- Referenced workflow artifacts: **{channels['artifacts']}**\n"
    )
    context, _ = _context(1, 1000, 1000)
    context = context.replace(ACCEPTANCE_SENTINEL, criterion).replace(
        "## PR Diff Summary", "## Acceptance evidence\n\n- " + evidence + "\n## PR Diff Summary"
    )
    result = pr_verifier._apply_coverage_floor(
        pr_verifier.EvaluationResult(verdict="PASS", used_llm=True),
        pr_verifier.prompt_coverage(context, None),
    )
    assert result.verdict == ("CONCERNS" if governor == "must" and status != "present" else "PASS")


@pytest.mark.parametrize("actor", ["The UI", "The reviewer"])
@pytest.mark.parametrize("status", ["absent", "unavailable", "present"])
def test_product_link_actual_floor(actor, status):
    criterion = f"{actor} must link to PR comments"
    evidence = (
        "Overall retrieval status: **present**\n- PR body: **present**\n"
        f"- PR comments: **{status}**\n- Referenced workflow artifacts: **absent**\n"
    )
    context, _ = _context(1, 1000, 1000)
    context = context.replace(ACCEPTANCE_SENTINEL, criterion).replace(
        "## PR Diff Summary", "## Acceptance evidence\n\n- " + evidence + "\n## PR Diff Summary"
    )
    result = pr_verifier._apply_coverage_floor(
        pr_verifier.EvaluationResult(verdict="PASS", used_llm=True),
        pr_verifier.prompt_coverage(context, None),
    )
    assert result.verdict == (
        "CONCERNS" if actor == "The reviewer" and status != "present" else "PASS"
    )


@pytest.mark.parametrize("status", ["absent", "unavailable", "present"])
@pytest.mark.parametrize("governor", ["must", "must not", "may"])
def test_pr_contained_comment_actual_floor(status, governor):
    criterion = f"The PR {governor} include a comment with test evidence"
    evidence = (
        "Overall retrieval status: **present**\n- PR body: **present**\n"
        f"- PR comments: **{status}**\n- Referenced workflow artifacts: **absent**\n"
    )
    context, _ = _context(1, 1000, 1000)
    context = context.replace(ACCEPTANCE_SENTINEL, criterion).replace(
        "## PR Diff Summary", "## Acceptance evidence\n\n- " + evidence + "\n## PR Diff Summary"
    )
    result = pr_verifier._apply_coverage_floor(
        pr_verifier.EvaluationResult(verdict="PASS", used_llm=True),
        pr_verifier.prompt_coverage(context, None),
    )
    assert result.verdict == ("CONCERNS" if governor == "must" and status != "present" else "PASS")


@pytest.mark.parametrize(
    "object_name",
    [
        "Test results",
        "Test logs",
        "Before/after screenshots",
        "Recordings",
    ],
)
@pytest.mark.parametrize("status", ["absent", "unavailable", "present"])
@pytest.mark.parametrize("negative", [False, True])
def test_common_body_proof_objects_actual_floor(object_name, status, negative):
    criterion = f"{object_name} must {'not ' if negative else ''}be recorded in the PR body"
    evidence = (
        "Overall retrieval status: **present**\n"
        f"- PR body: **{status}**\n"
        "- PR comments: **present**\n"
        "- Referenced workflow artifacts: **present**\n"
    )
    context, _ = _context(1, 1000, 1000)
    context = context.replace(ACCEPTANCE_SENTINEL, criterion).replace(
        "## PR Diff Summary", "## Acceptance evidence\n\n- " + evidence + "\n## PR Diff Summary"
    )
    result = pr_verifier._apply_coverage_floor(
        pr_verifier.EvaluationResult(verdict="PASS", used_llm=True),
        pr_verifier.prompt_coverage(context, None),
    )
    assert result.verdict == ("CONCERNS" if not negative and status != "present" else "PASS")


@pytest.mark.parametrize("governor", ["is not expected to", "is not supposed to"])
@pytest.mark.parametrize("status", ["absent", "unavailable", "present"])
@pytest.mark.parametrize("positive_position", ["none", "before", "after"])
def test_negative_comment_presence_does_not_floor_pass(governor, status, positive_position):
    negative = f"Command output {governor} be in a PR comment"
    positive = "The reviewer must record command output in a PR comment"
    criterion = {
        "none": negative,
        "before": positive + "; " + negative,
        "after": negative + "; " + positive,
    }[positive_position]
    evidence = (
        "Overall retrieval status: **present**\n"
        "- PR body: **present**\n"
        f"- PR comments: **{status}**\n"
        "- Referenced workflow artifacts: **present**\n"
    )
    context, _ = _context(1, 1000, 1000)
    context = context.replace(ACCEPTANCE_SENTINEL, criterion).replace(
        "## PR Diff Summary", "## Acceptance evidence\n\n- " + evidence + "\n## PR Diff Summary"
    )
    result = pr_verifier._apply_coverage_floor(
        pr_verifier.EvaluationResult(verdict="PASS", used_llm=True),
        pr_verifier.prompt_coverage(context, None),
    )
    assert result.verdict == (
        "CONCERNS" if positive_position != "none" and status != "present" else "PASS"
    )


@pytest.mark.parametrize("status", ["absent", "unavailable", "present"])
@pytest.mark.parametrize("kind", ["permit", "share", "negated-artifact"])
def test_permit_capability_and_share_delivery_use_actual_floor(status, kind):
    criterion = {
        "permit": "The UI must permit users to upload artifacts",
        "share": "The reviewer must share test evidence in a PR comment",
        "negated-artifact": "Evidence must not appear as workflow artifacts",
    }[kind]
    evidence = (
        "Overall retrieval status: **present**\n- PR body: **present**\n"
        f"- PR comments: **{status}**\n- Referenced workflow artifacts: **{status}**\n"
    )
    context, _ = _context(1, 1000, 1000)
    context = context.replace(ACCEPTANCE_SENTINEL, criterion).replace(
        "## PR Diff Summary", "## Acceptance evidence\n\n- " + evidence + "\n## PR Diff Summary"
    )
    result = pr_verifier._apply_coverage_floor(
        pr_verifier.EvaluationResult(verdict="PASS", used_llm=True),
        pr_verifier.prompt_coverage(context, None),
    )
    assert result.verdict == ("CONCERNS" if kind == "share" and status != "present" else "PASS")


@pytest.mark.parametrize("status", ["absent", "unavailable", "present"])
@pytest.mark.parametrize("position", ["none", "before", "after"])
@pytest.mark.parametrize(
    "destinations",
    ["a PR comment or workflow artifacts", "the PR body, a PR comment and workflow artifacts"],
)
def test_negative_coordinated_presence_actual_floor(status, position, destinations):
    negative = f"- [ ] No evidence is required to appear in {destinations}"
    positive = "The reviewer must record evidence in workflow artifacts"
    criterion = {
        "none": negative,
        "before": positive + "; " + negative,
        "after": negative + "; " + positive,
    }[position]
    evidence = (
        "Overall retrieval status: **present**\n- PR body: **present**\n"
        f"- PR comments: **{status}**\n- Referenced workflow artifacts: **{status}**\n"
    )
    context, _ = _context(1, 1000, 1000)
    context = context.replace("- " + ACCEPTANCE_SENTINEL, criterion).replace(
        "## PR Diff Summary", "## Acceptance evidence\n\n- " + evidence + "\n## PR Diff Summary"
    )
    result = pr_verifier._apply_coverage_floor(
        pr_verifier.EvaluationResult(verdict="PASS", used_llm=True),
        pr_verifier.prompt_coverage(context, None),
    )
    assert result.verdict == ("CONCERNS" if position != "none" and status != "present" else "PASS")


@pytest.mark.parametrize("status", ["absent", "unavailable", "present"])
@pytest.mark.parametrize("governor", ["must", "required to"])
@pytest.mark.parametrize("marker", ["", "- [ ] "])
@pytest.mark.parametrize(
    "destination,channel",
    [("workflow artifacts", "artifacts"), ("the PR body", "body"), ("a PR comment", "comments")],
)
@pytest.mark.parametrize("predicate_prefix", ["", "currently ", "that ", "which now "])
def test_independent_destination_actor_actual_floor(
    status, governor, marker, destination, channel, predicate_prefix
):
    criterion = (
        marker
        + f"No evidence is required to appear in a PR comment, and {destination} {predicate_prefix}{governor} contain command output"
    )
    statuses = {"body": "present", "comments": "present", "artifacts": "present", channel: status}
    evidence = (
        "Overall retrieval status: **present**\n"
        f"- PR body: **{statuses['body']}**\n- PR comments: **{statuses['comments']}**\n"
        f"- Referenced workflow artifacts: **{statuses['artifacts']}**\n"
    )
    context, _ = _context(1, 1000, 1000)
    context = context.replace("- " + ACCEPTANCE_SENTINEL, criterion).replace(
        "## PR Diff Summary", "## Acceptance evidence\n\n- " + evidence + "\n## PR Diff Summary"
    )
    result = pr_verifier._apply_coverage_floor(
        pr_verifier.EvaluationResult(verdict="PASS", used_llm=True),
        pr_verifier.prompt_coverage(context, None),
    )
    assert result.verdict == ("PASS" if status == "present" else "CONCERNS")


@pytest.mark.skipif(NODE is None, reason="Node is required for producer integration")
@pytest.mark.parametrize("channel", ["overall", "body"])
def test_unavailable_comments_cannot_hide_behind_requirement_only_body(channel):
    """An available requirement is not proof of a generic evidence obligation."""
    script = r"""
const {fetchVerifierEvidence,formatVerifierEvidence}=require('./.github/scripts/agents_verifier_context.js');
const empty=async()=>({data:[]});
const github={rest:{issues:{listComments:async()=>{throw new Error('unavailable')}},
  pulls:{listReviewComments:empty,listReviews:empty}}};
fetchVerifierEvidence({github,owner:'owner',repo:'repo',pullNumber:1,evidenceTexts:[],
  pullRequestBody:'Provide a link to test evidence'})
.then(e=>process.stdout.write(JSON.stringify({status:e.status,markdown:formatVerifierEvidence(e)})))
.catch(e=>{console.error(e);process.exit(1)});
"""
    produced = json.loads(subprocess.check_output([NODE, "-e", script], cwd=ROOT, text=True))
    assert produced["status"] == "unavailable"
    criterion = (
        "Provide a link to test evidence"
        if channel == "overall"
        else "Evidence in the PR body is required"
    )
    context, _ = _context(1, 1000, 1000)
    context = context.replace(ACCEPTANCE_SENTINEL, criterion).replace(
        "## PR Diff Summary", produced["markdown"] + "\n\n## PR Diff Summary"
    )
    result = pr_verifier._apply_coverage_floor(
        pr_verifier.EvaluationResult(verdict="PASS", used_llm=True),
        pr_verifier.prompt_coverage(context, None),
    )
    # Explicit body retrieval is complete; the model still judges its contents.
    assert result.verdict == ("CONCERNS" if channel == "overall" else "PASS")


@pytest.mark.parametrize("predicate", ["appear", "be present"])
@pytest.mark.parametrize(
    "destination", ["in a PR comment", "in comments on the PR", "in comments in the pull request"]
)
@pytest.mark.parametrize(
    "noun",
    [
        "Test evidence",
        "Validation command output",
        "Test transcript",
        "Artifacts",
        "Validation artifacts",
    ],
)
def test_mandatory_evidence_presence_in_comments_cannot_use_other_channels(
    predicate, destination, noun
):
    criterion = f"{noun} must {predicate} {destination}"
    assert pr_verifier._required_evidence_channels(criterion) == {"comments"}
    for status in ("absent", "unavailable", "present"):
        evidence = (
            "Overall retrieval status: **present**\n"
            "- PR body: **present**\n"
            f"- PR comments: **{status}**\n"
            "- Referenced workflow artifacts: **present**\n"
        )
        context, _ = _context(1, 1000, 1000)
        context = context.replace(ACCEPTANCE_SENTINEL, criterion).replace(
            "## PR Diff Summary", "## Acceptance evidence\n\n- " + evidence + "\n## PR Diff Summary"
        )
        result = pr_verifier._apply_coverage_floor(
            pr_verifier.EvaluationResult(verdict="PASS", used_llm=True),
            pr_verifier.prompt_coverage(context, None),
        )
        assert result.verdict == ("PASS" if status == "present" else "CONCERNS")


@pytest.mark.parametrize(
    "criterion",
    [
        "Test evidence may appear in a PR comment",
        "Test evidence need not be present in a PR comment",
        "Test evidence must not appear in a PR comment",
        "Test evidence must not be present in a PR comment",
        "Test evidence is not expected to be present in a PR comment",
        "Test evidence is not supposed to appear in a PR comment",
        "No test evidence must appear in a PR comment",
        "No test evidence is required to appear in a PR comment",
        "No artifacts are required to appear in a PR comment",
        "Neither test evidence nor command output is required to appear in a PR comment",
        "Neither independently collected validation artifacts nor exact-head regression command output is required to be present in comments on the PR",
        "Validation artifacts must not be present in comments on the PR",
        "No validation command output is required to be present in comments on the PR",
        "Evidence must be collected, and the UI makes it appear in a PR comment preview",
        "Evidence must be collected; the UI makes it appear in a PR comment preview",
        "Test evidence is no longer required to appear in a PR comment",
        "The UI lets users make test evidence appear in a PR comment preview",
    ],
)
def test_evidence_presence_keeps_optional_prohibited_and_product_boundaries(criterion):
    expected = {"overall"} if criterion.startswith("Evidence must be collected;") else set()
    assert pr_verifier._required_evidence_channels(criterion) == expected
    assert pr_verifier._required_evidence_channels(
        criterion + "; the reviewer must post validation evidence in a PR comment"
    ) == expected | {"comments"}


@pytest.mark.parametrize("operation", ["submit", "deliver", "record", "post"])
@pytest.mark.parametrize(
    "noun",
    [
        "validation evidence",
        "CI validation evidence",
        "independently collected evidence",
        "exact-head regression evidence",
        "before/after evidence",
        "test transcript",
        "validation command output",
        "excluded-case test evidence",
        "omitted-case validation evidence",
        "optional-case validation evidence",
        "independently collected exact-head regression validation command output",
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
        context, _ = _context(1, 1000, 1000)
        context = context.replace(ACCEPTANCE_SENTINEL, criterion).replace(
            "## PR Diff Summary", "## Acceptance evidence\n\n- " + evidence + "\n## PR Diff Summary"
        )
        result = pr_verifier._apply_coverage_floor(
            pr_verifier.EvaluationResult(verdict="PASS", used_llm=True),
            pr_verifier.prompt_coverage(context, None),
        )
        assert result.verdict == ("PASS" if body_status == "present" else "CONCERNS")


@pytest.mark.parametrize(
    "noun", ["CI validation evidence", "independently collected evidence", "test transcript"]
)
@pytest.mark.parametrize(
    "template",
    [
        "{noun} must be delivered in the PR body",
        "There must be {noun} in the PR body",
        "The PR body must contain {noun}",
        "{noun} in the PR body is required",
    ],
)
def test_qualified_body_predicates_bind_the_same_destination(noun, template):
    assert pr_verifier._required_evidence_channels(template.format(noun=noun)) == {"body"}


@pytest.mark.parametrize(
    "noun",
    ["CI validation evidence", "independently collected evidence", "validation command output"],
)
@pytest.mark.parametrize(
    "template",
    [
        "No {noun} must be recorded in the PR body",
        "The PR body must contain no {noun}",
        "No {noun} in the PR body is required",
        "The reviewer may deliver {noun} in the PR body",
        "The reviewer must not submit {noun} in the PR body",
        "The UI lets users submit {noun} in the PR body editor",
    ],
)
def test_qualified_body_exemptions_preserve_independent_delivery(noun, template):
    criterion = template.format(noun=noun)
    assert pr_verifier._required_evidence_channels(criterion) == set()
    assert pr_verifier._required_evidence_channels(
        criterion + "; the reviewer must deliver validation evidence in a PR comment"
    ) == {"comments"}


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
@pytest.mark.parametrize("source", ["body", "comment", "production-body"])
@pytest.mark.parametrize(
    "workflow", ["CI", "Validation", "Artifact validation", "Validation | Linux", "Artifact | Mac"]
)
def test_incidental_status_run_link_does_not_suppress_artifact_discovery(source, workflow):
    """A status-table link is not an explicit validation-evidence selection."""
    script = r"""
const {fetchVerifierEvidence}=require('./.github/scripts/agents_verifier_context.js');
const {source,workflow}=JSON.parse(require('fs').readFileSync(0,'utf8'));
const sha='a'.repeat(40), status='| '+workflow+' | SUCCESS | [View run](https://github.com/owner/repo/actions/runs/123) |';
let discoveries=0;
const empty=async()=>({data:[]});
const github={rest:{issues:{listComments:async()=>({data:source==='comment'?[{id:1,body:status}]:[]})},
pulls:{listReviewComments:empty,listReviews:empty},actions:{
getWorkflowRun:async()=>({data:{id:123,head_sha:sha}}),
listWorkflowRunsForRepo:async()=>{discoveries++;return {data:{total_count:1,workflow_runs:[{id:124,head_sha:sha}]}}},
listWorkflowRunArtifacts:async({run_id})=>({data:{total_count:run_id===124?1:0,artifacts:run_id===124?[{id:9,size_in_bytes:10,expired:false}]:[]}}),
downloadArtifact:async()=>({data:Buffer.from('zip')})}}};
fetchVerifierEvidence({github,owner:'owner',repo:'repo',pullNumber:1,
pullRequestBody:source==='body'||source==='production-body'?status:'',associatedCommitShas:[sha],
evidenceTexts:source==='production-body'?[status]:[],
extractArtifactText:()=>({text:'RED then GREEN',truncated:false})})
.then(e=>process.stdout.write(JSON.stringify({discoveries,status:e.artifacts.status})))
.catch(e=>{console.error(e);process.exit(1)});
"""
    produced = json.loads(
        subprocess.check_output(
            [NODE, "-e", script],
            cwd=ROOT,
            input=json.dumps({"source": source, "workflow": workflow}),
            text=True,
        )
    )
    assert produced == {"discoveries": 1, "status": "present"}


@pytest.mark.skipif(NODE is None, reason="Node is required for producer integration")
@pytest.mark.parametrize("channel", ["body", "comment", "issue"])
@pytest.mark.parametrize("explicit", ["typed", "labelled"])
@pytest.mark.parametrize("overflow", [False, True])
def test_explicit_artifact_scope_ignores_incidental_reference_budget(channel, explicit, overflow):
    """Incidental status URLs cannot change a complete selected proof set."""
    script = r"""
const {fetchVerifierEvidence}=require('./.github/scripts/agents_verifier_context.js');
const {channel,explicit,overflow}=JSON.parse(require('fs').readFileSync(0,'utf8'));
const sha='a'.repeat(40), url='https://github.com/owner/repo/actions/runs/123';
const count=overflow?5:1, rows=Array.from({length:count},(_,i)=>
'| Validation | SUCCESS | [View run](https://github.com/owner/repo/actions/runs/'+(125+i)+') |').join('\n');
const prose=rows+(explicit==='labelled'?'\nValidation evidence: '+url:'');
const empty=async()=>({data:[]}), inspected=[];let discoveries=0;
const github={rest:{issues:{listComments:async()=>({data:channel==='comment'?[{id:1,body:prose}]:[]})},
pulls:{listReviewComments:empty,listReviews:empty},actions:{
getWorkflowRun:async({run_id})=>{inspected.push(run_id);if(run_id!==123)throw Error('incidental run is outside selected scope');return {data:{id:123,head_sha:sha}}},
listWorkflowRunsForRepo:async()=>{discoveries++;throw Error('explicit set must not discover unrelated runs')},
listWorkflowRunArtifacts:async()=>({data:{total_count:1,artifacts:[{id:9,size_in_bytes:10,expired:false}]}}),
downloadArtifact:async()=>({data:Buffer.from('zip')})}}};
fetchVerifierEvidence({github,owner:'owner',repo:'repo',pullNumber:1,
pullRequestBody:channel==='body'?prose:'',referenceTexts:channel==='issue'?[prose]:[],
evidenceTexts:explicit==='typed'?[url]:[],associatedCommitShas:[sha],
extractArtifactText:()=>({text:'RED then GREEN',truncated:false})})
.then(e=>process.stdout.write(JSON.stringify({inspected,discoveries,status:e.artifacts.status})))
.catch(e=>{console.error(e);process.exit(1)});
"""
    produced = json.loads(
        subprocess.check_output(
            [NODE, "-e", script],
            cwd=ROOT,
            input=json.dumps({"channel": channel, "explicit": explicit, "overflow": overflow}),
            text=True,
            env={**os.environ, "VERIFIER_EVIDENCE_RUN_LIMIT": "1"},
        )
    )
    assert produced == {"inspected": [123], "discoveries": 0, "status": "present"}


@pytest.mark.skipif(NODE is None, reason="Node is required for producer integration")
@pytest.mark.parametrize("mode", ["union", "empty", "wrong-head", "excess", "incomplete"])
def test_selected_explicit_union_retains_fail_closed_controls(mode):
    """Incidental exclusion never repairs selected-set provenance or completeness."""
    script = r"""
const {fetchVerifierEvidence}=require('./.github/scripts/agents_verifier_context.js');
const mode=JSON.parse(require('fs').readFileSync(0,'utf8')), sha='a'.repeat(40);
const url=id=>'https://github.com/owner/repo/actions/runs/'+id;
const empty=async()=>({data:[]}), inspected=[];let discoveries=0;
const github={rest:{issues:{listComments:empty},pulls:{listReviewComments:empty,listReviews:empty},actions:{
getWorkflowRun:async({run_id})=>{inspected.push(run_id);return {data:{id:run_id,head_sha:mode==='wrong-head'?'b'.repeat(40):sha}}},
listWorkflowRunsForRepo:async()=>{discoveries++;return {data:{workflow_runs:[],total_count:0}}},
listWorkflowRunArtifacts:async({run_id})=>({data:{total_count:mode==='empty'?0:1,artifacts:mode==='empty'?[]:[{id:run_id,size_in_bytes:10,expired:false}]}}),
downloadArtifact:async()=>({data:Buffer.from('zip')})}}};
fetchVerifierEvidence({github,owner:'owner',repo:'repo',pullNumber:1,
pullRequestBody:'| Validation | SUCCESS | [View run]('+url(999)+') |',
evidenceTexts:[url(123)],referenceTexts:['Validation evidence: '+url(123)+' '+url(124)],
referenceSourcesComplete:mode!=='incomplete',associatedCommitShas:[sha],
extractArtifactText:()=>({text:'RED then GREEN',truncated:false})})
.then(e=>process.stdout.write(JSON.stringify({inspected,discoveries,status:e.artifacts.status})))
.catch(e=>{console.error(e);process.exit(1)});
"""
    produced = json.loads(
        subprocess.check_output(
            [NODE, "-e", script],
            cwd=ROOT,
            input=json.dumps(mode),
            text=True,
            env={**os.environ, "VERIFIER_EVIDENCE_RUN_LIMIT": "1" if mode == "excess" else "2"},
        )
    )
    assert produced["inspected"] == ([123] if mode == "excess" else [123, 124])
    assert produced["status"] == (
        "present" if mode == "union" else "absent" if mode == "empty" else "unavailable"
    )
    if mode in {"union", "empty"}:
        assert produced["discoveries"] == 0


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
def test_complete_comment_only_satisfies_explicit_comment_retrieval_when_artifacts_incomplete(
    comment, channel, criterion
):
    """Incomplete artifacts veto generic availability, not explicit comments."""
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
    assert produced["status"] == "unavailable"
    assert pr_verifier._required_evidence_channels("- [ ] " + criterion) == {channel}
    context, _ = _context(1, 1000, 1000)
    context = context.replace(ACCEPTANCE_SENTINEL, criterion).replace(
        "## PR Diff Summary", produced["markdown"] + "\n\n## PR Diff Summary"
    )
    result = pr_verifier._apply_coverage_floor(
        pr_verifier.EvaluationResult(verdict="PASS", used_llm=True),
        pr_verifier.prompt_coverage(context, None),
    )
    assert result.verdict == ("PASS" if comment and channel == "comments" else "CONCERNS")


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
