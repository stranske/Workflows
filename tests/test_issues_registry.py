from pathlib import Path


def test_issue_15_is_documented():
    content = Path("Issues.txt").read_text()
    assert "15) Create GitHub starter workflow template" in content
    assert "Template appears in GitHub Actions UI when creating new workflow." in content
