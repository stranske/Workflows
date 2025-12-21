import re
from pathlib import Path


def test_issue_15_is_documented():
    issues_path = Path("Issues.txt")
    assert issues_path.exists(), "Issues.txt file is missing"

    content = issues_path.read_text(encoding="utf-8")
    assert re.search(
        r"^15\)\s+Create GitHub starter workflow template", content, flags=re.MULTILINE
    ), "Issue #15 should be documented in Issues.txt before being referenced by bootstrap files"
