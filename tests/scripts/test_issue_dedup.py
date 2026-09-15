import sys
import types
from dataclasses import dataclass

import pytest
from scripts.langchain import issue_dedup, semantic_matcher


class DummyFAISS:
    calls = []

    @classmethod
    def from_texts(cls, texts, embeddings, metadatas=None):
        cls.calls.append((texts, embeddings, metadatas))
        return {"texts": texts, "metadatas": metadatas}


def _install_faiss_stub(monkeypatch):
    vectorstores_module = types.SimpleNamespace(FAISS=DummyFAISS)
    langchain_community_module = types.SimpleNamespace(vectorstores=vectorstores_module)
    monkeypatch.setitem(sys.modules, "langchain_community", langchain_community_module)
    monkeypatch.setitem(sys.modules, "langchain_community.vectorstores", vectorstores_module)
    DummyFAISS.calls = []


@dataclass
class DummyDoc:
    page_content: str
    metadata: dict


def test_build_issue_vector_store_uses_faiss_from_texts(monkeypatch):
    _install_faiss_stub(monkeypatch)
    client_info = semantic_matcher.EmbeddingClientInfo(
        client=object(),
        provider="unit-test",
        model="unit-test-model",
        is_fallback=False,
    )
    issues = [
        {"number": 42, "title": "Sample", "body": "Body", "html_url": "http://example"},
    ]

    result = issue_dedup.build_issue_vector_store(issues, client_info=client_info)

    assert result is not None
    assert result.store["texts"] == ["Sample\nBody"]
    assert result.store["metadatas"] == [{"number": 42, "title": "Sample", "url": "http://example"}]
    assert result.is_fallback is False
    assert DummyFAISS.calls


def test_build_issue_vector_store_returns_none_without_client(monkeypatch):
    _install_faiss_stub(monkeypatch)
    monkeypatch.setattr(semantic_matcher, "get_embedding_client", lambda model=None: None)

    result = issue_dedup.build_issue_vector_store([{"number": 1, "title": "Only"}])

    assert result is None


def test_find_similar_issues_filters_by_relevance_score():
    store = types.SimpleNamespace(
        similarity_search_with_relevance_scores=lambda query, k=5: [
            (DummyDoc("Alpha", {"number": 1, "title": "Alpha", "url": "http://a"}), 0.92),
            (DummyDoc("Beta", {"number": 2, "title": "Beta", "url": "http://b"}), 0.4),
        ]
    )
    vector_store = issue_dedup.IssueVectorStore(
        store=store,
        provider="unit-test",
        model="unit-test-model",
        is_fallback=False,
        issues=[],
    )

    matches = issue_dedup.find_similar_issues(vector_store, "query", threshold=0.8)

    assert len(matches) == 1
    assert matches[0].issue.number == 1
    assert matches[0].score == 0.92
    assert matches[0].score_type == "relevance"


def test_find_similar_issues_converts_distance_scores():
    store = types.SimpleNamespace(
        similarity_search_with_score=lambda query, k=5: [
            (DummyDoc("Alpha", {"number": 10, "title": "Alpha", "url": "http://a"}), 0.1),
            (DummyDoc("Beta", {"number": 11, "title": "Beta", "url": "http://b"}), 1.5),
        ]
    )
    vector_store = issue_dedup.IssueVectorStore(
        store=store,
        provider="unit-test",
        model="unit-test-model",
        is_fallback=False,
        issues=[],
    )

    matches = issue_dedup.find_similar_issues(vector_store, "query", threshold=0.85)

    assert len(matches) == 1
    assert matches[0].issue.number == 10
    assert matches[0].raw_score == 0.1
    assert matches[0].score_type == "distance"


def test_format_similar_issues_comment_formats_links():
    matches = [
        issue_dedup.IssueMatch(
            issue=issue_dedup.IssueRecord(number=12, title="Alpha", url="http://a"),
            score=0.92,
            raw_score=0.92,
            score_type="relevance",
        ),
        issue_dedup.IssueMatch(
            issue=issue_dedup.IssueRecord(number=34, title="Beta", url=None),
            score=0.85,
            raw_score=0.85,
            score_type="relevance",
        ),
    ]

    comment = issue_dedup.format_similar_issues_comment(matches, max_items=1)

    assert comment is not None
    assert issue_dedup.SIMILAR_ISSUES_MARKER in comment
    assert "**#12**" in comment
    assert "[Alpha](http://a)" in comment
    assert "Alpha" in comment
    assert "92% similarity" in comment
    assert "<summary>Next steps for maintainers</summary>" in comment
    assert "1. **Review the linked issues**" not in comment


def test_format_similar_issues_comment_returns_none_for_empty():
    assert issue_dedup.format_similar_issues_comment([]) is None


@pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf")])
def test_format_similarity_nonfinite(score):
    assert issue_dedup._format_similarity(score) == "0%"


@pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf")])
def test_format_similar_issues_comment_nonfinite(score):
    match = issue_dedup.IssueMatch(
        issue=issue_dedup.IssueRecord(number=12, title="Alpha", url="http://a"),
        score=score,
        raw_score=score,
        score_type="relevance",
    )
    comment = issue_dedup.format_similar_issues_comment([match])
    assert "**#12** - [Alpha](http://a) (0% similarity)" in comment


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (-0.1, "0%"),
        (0.0, "0%"),
        (0.924, "92%"),
        (0.926, "93%"),
        (0.125, "12%"),
        (0.375, "38%"),
        (1.0, "100%"),
        (1.1, "100%"),
    ],
)
def test_format_similarity_preserves_finite_clamping_and_rounding(score, expected):
    assert issue_dedup._format_similarity(score) == expected

    match = issue_dedup.IssueMatch(
        issue=issue_dedup.IssueRecord(number=12, title="Alpha", url="http://a"),
        score=score,
        raw_score=score,
        score_type="relevance",
    )
    comment = issue_dedup.format_similar_issues_comment([match])
    assert f"**#12** - [Alpha](http://a) ({expected} similarity)" in comment
