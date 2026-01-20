import os

from scripts.langchain import issue_dedup


class _FakeDoc:
    def __init__(self, metadata: dict, page_content: str) -> None:
        self.metadata = metadata
        self.page_content = page_content


class _FakeStore:
    def __init__(self, results: list[tuple[_FakeDoc, float]]) -> None:
        self._results = list(results)

    def similarity_search_with_relevance_scores(
        self, _query: str, *, k: int = 3
    ) -> list[tuple[_FakeDoc, float]]:
        return list(self._results[:k])


def _simulate_agents_dedup_workflow(
    open_issues: list[issue_dedup.IssueRecord],
    *,
    new_title: str,
    new_body: str,
    scores: list[float],
) -> dict:
    threshold = float(os.environ.get("SIMILARITY_THRESHOLD", "0.85"))
    docs = []
    for issue in open_issues:
        docs.append(
            _FakeDoc(
                {
                    "number": issue.number,
                    "title": issue.title,
                    "url": issue.url,
                },
                issue.title,
            )
        )
    results = list(zip(docs, scores, strict=False))
    store = issue_dedup.IssueVectorStore(
        store=_FakeStore(results), provider="fake", model="fake", issues=open_issues
    )
    query = f"{new_title}\n\n{new_body}"
    matches = issue_dedup.find_similar_issues(store, query, threshold=threshold, k=3)
    if not matches:
        return {"has_duplicates": False, "duplicates": [], "comment": None}

    duplicates = [
        {
            "number": match.issue.number,
            "title": match.issue.title,
            "url": match.issue.url,
            "score": f"{match.score:.0%}",
        }
        for match in matches
    ]
    return {
        "has_duplicates": True,
        "duplicates": duplicates,
        "comment": issue_dedup.format_similar_issues_comment(matches, max_items=3),
    }


def test_agents_dedup_links_duplicates(monkeypatch) -> None:
    monkeypatch.setenv("SIMILARITY_THRESHOLD", "0.85")
    open_issues = [
        issue_dedup.IssueRecord(
            number=101,
            title="Login error on mobile",
            body="App fails after entering credentials.",
            url="https://example.test/issues/101",
        ),
        issue_dedup.IssueRecord(
            number=202,
            title="Crash on login screen",
            body="Screen freezes before MFA step.",
            url="https://example.test/issues/202",
        ),
    ]

    result = _simulate_agents_dedup_workflow(
        open_issues,
        new_title="Login crash after sign in",
        new_body="The app crashes after entering credentials.",
        scores=[0.92, 0.88],
    )

    assert result["has_duplicates"] is True
    assert len(result["duplicates"]) == 2
    comment = result["comment"]
    assert comment is not None
    assert "**#101**" in comment
    assert "**#202**" in comment
    assert "[Login error on mobile](https://example.test/issues/101)" in comment
    assert "[Crash on login screen](https://example.test/issues/202)" in comment


def test_agents_dedup_allows_unique_issue(monkeypatch) -> None:
    monkeypatch.setenv("SIMILARITY_THRESHOLD", "0.85")
    open_issues = [
        issue_dedup.IssueRecord(
            number=303,
            title="Update docs for API",
            body="Docs need refresh for v2 endpoints.",
            url="https://example.test/issues/303",
        )
    ]

    result = _simulate_agents_dedup_workflow(
        open_issues,
        new_title="Add export button",
        new_body="Need CSV export for reports.",
        scores=[0.2],
    )

    assert result["has_duplicates"] is False
    assert result["duplicates"] == []
    assert result["comment"] is None
