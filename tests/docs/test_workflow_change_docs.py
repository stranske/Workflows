"""Documentation coverage for workflow suppression guidance."""

from pathlib import Path

KEEPALIVE_DOC = Path("docs/workflow-changes-keepalive.md")
AUTOFIX_DOC = Path("docs/workflow-changes-autofix.md")


def test_keepalive_doc_includes_guard_and_if() -> None:
    content = KEEPALIVE_DOC.read_text(encoding="utf-8")
    assert "id: review_gate" in content
    assert "should_post_review" in content
    assert "steps.review_gate.outputs.should_post_review == 'true'" in content


def test_autofix_doc_includes_should_post_guard() -> None:
    content = AUTOFIX_DOC.read_text(encoding="utf-8")
    assert "id: build_comment" in content
    assert "steps.build_comment.outputs.should-post == 'true'" in content
    assert "Upsert consolidated PR comment" in content
