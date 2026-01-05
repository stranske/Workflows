import sys
import types

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
