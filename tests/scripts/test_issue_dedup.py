import sys
import types
from dataclasses import dataclass

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
    )
    issues = [
        {"number": 42, "title": "Sample", "body": "Body", "html_url": "http://example"},
    ]

    result = issue_dedup.build_issue_vector_store(issues, client_info=client_info)

    assert result is not None
    assert result.store["texts"] == ["Sample\nBody"]
    assert result.store["metadatas"] == [{"number": 42, "title": "Sample", "url": "http://example"}]
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
        store=store, provider="unit-test", model="unit-test-model", issues=[]
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
        store=store, provider="unit-test", model="unit-test-model", issues=[]
    )

    matches = issue_dedup.find_similar_issues(vector_store, "query", threshold=0.85)

    assert len(matches) == 1
    assert matches[0].issue.number == 10
    assert matches[0].raw_score == 0.1
    assert matches[0].score_type == "distance"
