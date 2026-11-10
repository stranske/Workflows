"""Focused gate for finding 4273098296's reported sentence.

The reviewer must report test results in a PR comment. That sentence has the
same required comment channel as record. An LLM PASS does not survive absent
or unavailable comment evidence.
"""

from __future__ import annotations

from scripts.langchain import pr_verifier as verifier

from tests.scripts.test_pr_verifier_prompt_coverage import ACCEPTANCE_SENTINEL, _context

REPORTED = "The reviewer must report test results in a PR comment"
RECORDED = "The reviewer must record test results in a PR comment"


def _floor_verdict(criterion: str, comments: str) -> str:
    """Apply the coverage floor to an LLM PASS for one comment status."""
    context, _paths = _context(1, 1000, 1000)
    evidence = (
        "- Overall retrieval status: **present**\n"
        "- PR body: **present**\n"
        f"- PR comments: **{comments}**\n"
        "- Referenced workflow artifacts: **present**"
    )
    context = context.replace("- " + ACCEPTANCE_SENTINEL, criterion).replace(
        "## PR Diff Summary",
        "## Acceptance evidence\n\n" + evidence + "\n\n## PR Diff Summary",
    )
    return verifier._apply_coverage_floor(
        verifier.EvaluationResult(verdict="PASS", used_llm=True),
        verifier.prompt_coverage(context, None),
    ).verdict


def test_reported_sentence_requires_pr_comment_and_rejects_ungrounded_pass() -> None:
    """Current-main execution of the exact reported sentence."""
    report_channels = verifier._required_evidence_channels(REPORTED)
    record_channels = verifier._required_evidence_channels(RECORDED)
    expected = {
        "absent": "CONCERNS",
        "unavailable": "UNVERIFIABLE_INPUT",
        "present": "PASS",
    }
    report_verdicts = {status: _floor_verdict(REPORTED, status) for status in expected}
    record_verdicts = {status: _floor_verdict(RECORDED, status) for status in expected}
    failures = sum(
        (
            report_channels != {"comments"},
            report_channels != record_channels,
            *(report_verdicts[status] != verdict for status, verdict in expected.items()),
            *(record_verdicts[status] != verdict for status, verdict in expected.items()),
        )
    )
    print(
        "required_channels="
        + str(sorted(report_channels))
        + f" comments_absent_verdict={report_verdicts['absent']}"
        + f" comments_unavailable_verdict={report_verdicts['unavailable']}"
        + f" comments_present_verdict={report_verdicts['present']}"
        + f" report_delivery_failures={failures}"
    )
    assert report_channels == {"comments"}
    assert report_channels == record_channels
    assert report_verdicts == expected
    assert record_verdicts == expected
    assert failures == 0
