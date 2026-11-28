import pytest
from scripts.langchain import integration_layer, semantic_matcher


@pytest.fixture(autouse=True)
def _disable_embeddings(monkeypatch):
    monkeypatch.setattr(semantic_matcher, "get_embedding_client", lambda model=None: None)


def test_labeling_integration_applies_expected_labels():
    available_labels = [
        {"name": "type:bug", "description": "Bug reports"},
        {"name": "type:feature", "description": "Feature requests"},
        {"name": "documentation", "description": "Docs updates"},
    ]

    bug_issue = integration_layer.IssueData(
        title="App crashes on login",
        body="The app crashes after the sign-in screen.",
    )
    bug_labels = integration_layer.label_issue(bug_issue, available_labels, threshold=0.8)
    assert "type:bug" in bug_labels
    assert "type:bug" in bug_issue.labels

    feature_issue = integration_layer.IssueData(
        title="Add dark mode support",
        body="It would be great to enable a dark theme.",
    )
    feature_labels = integration_layer.label_issue(feature_issue, available_labels, threshold=0.8)
    assert "type:feature" in feature_labels
    assert "type:feature" in feature_issue.labels

    multi_issue = integration_layer.IssueData(
        title="Bug in dark mode feature",
        body="The new theme crashes on settings.",
    )
    multi_labels = integration_layer.label_issue(multi_issue, available_labels, threshold=0.8)
    assert "type:bug" in multi_labels
    assert "type:feature" in multi_labels
    assert "type:bug" in multi_issue.labels
    assert "type:feature" in multi_issue.labels
