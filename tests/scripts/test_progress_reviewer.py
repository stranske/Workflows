from __future__ import annotations

import json

from scripts.langchain import progress_reviewer


def test_build_review_payload_includes_review_fields():
    result = progress_reviewer.review_progress(
        acceptance_criteria=["Add guard to progress review comments"],
        recent_commits=["chore: update progress reviewer"],
        files_changed=["scripts/langchain/progress_reviewer.py"],
        rounds_without_completion=2,
        use_llm=False,
    )

    payload = progress_reviewer.build_review_payload(result)
    review = payload.get("review")

    assert isinstance(review, dict)
    assert review["score"] == result.alignment_score
    assert review["feedback"] == result.feedback_for_agent
    assert "suggestions" in review


def test_json_output_contains_review_fields():
    result = progress_reviewer.review_progress(
        acceptance_criteria=[],
        recent_commits=[],
        files_changed=[],
        rounds_without_completion=0,
        use_llm=False,
    )

    payload = progress_reviewer.build_review_payload(result)
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)

    assert "review" in decoded
    assert set(decoded["review"].keys()) == {"score", "feedback", "suggestions"}
