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
