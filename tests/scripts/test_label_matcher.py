import sys
import types
from dataclasses import dataclass

from scripts.langchain import label_matcher, semantic_matcher


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


def test_build_label_vector_store_uses_faiss_from_texts(monkeypatch):
    _install_faiss_stub(monkeypatch)
    client_info = semantic_matcher.EmbeddingClientInfo(
        client=object(),
        provider="unit-test",
        model="unit-test-model",
    )
    labels = [
        {"name": "bug", "description": "Something isn't working"},
    ]

    result = label_matcher.build_label_vector_store(labels, client_info=client_info)

    assert result is not None
    assert result.store["texts"] == ["bug\nSomething isn't working"]
    assert result.store["metadatas"] == [{"name": "bug", "description": "Something isn't working"}]
    assert DummyFAISS.calls


def test_build_label_vector_store_returns_none_without_client(monkeypatch):
    _install_faiss_stub(monkeypatch)
    monkeypatch.setattr(semantic_matcher, "get_embedding_client", lambda model=None: None)

    result = label_matcher.build_label_vector_store([{"name": "bug"}])

    assert result is None


def test_find_similar_labels_filters_by_relevance_score():
    store = types.SimpleNamespace(
        similarity_search_with_relevance_scores=lambda query, k=5: [
            (DummyDoc("bug", {"name": "bug", "description": "broken"}), 0.91),
            (DummyDoc("enhancement", {"name": "enhancement"}), 0.4),
        ]
    )
    vector_store = label_matcher.LabelVectorStore(
        store=store, provider="unit-test", model="unit-test-model", labels=[]
    )

    matches = label_matcher.find_similar_labels(vector_store, "defect", threshold=0.8)

    assert len(matches) == 1
    assert matches[0].label.name == "bug"
    assert matches[0].score == 0.91
    assert matches[0].score_type == "relevance"


def test_find_similar_labels_converts_distance_scores():
    store = types.SimpleNamespace(
        similarity_search_with_score=lambda query, k=5: [
            (DummyDoc("bug", {"name": "bug"}), 0.1),
            (DummyDoc("enhancement", {"name": "enhancement"}), 1.5),
        ]
    )
    vector_store = label_matcher.LabelVectorStore(
        store=store, provider="unit-test", model="unit-test-model", labels=[]
    )

    matches = label_matcher.find_similar_labels(vector_store, "defect", threshold=0.85)

    assert len(matches) == 1
    assert matches[0].label.name == "bug"
    assert matches[0].raw_score == 0.1
    assert matches[0].score_type == "distance"


def test_resolve_label_match_prefers_exact_for_short_labels():
    label = label_matcher.LabelRecord(name="CI", description="Pipeline failures")
    vector_store = label_matcher.LabelVectorStore(
        store=object(), provider="unit-test", model="unit-test-model", labels=[label]
    )

    match = label_matcher.resolve_label_match(vector_store, "ci")

    assert match is not None
    assert match.label.name == "CI"
    assert match.score_type == "exact"


def test_resolve_label_match_uses_semantic_search():
    store = types.SimpleNamespace(
        similarity_search_with_relevance_scores=lambda query, k=5: [
            (DummyDoc("bug", {"name": "bug", "description": "broken"}), 0.93),
            (DummyDoc("enhancement", {"name": "enhancement"}), 0.82),
        ]
    )
    vector_store = label_matcher.LabelVectorStore(
        store=store, provider="unit-test", model="unit-test-model", labels=[]
    )

    match = label_matcher.resolve_label_match(vector_store, "defect", threshold=0.8)

    assert match is not None
    assert match.label.name == "bug"
    assert match.score == 0.93


def test_find_similar_labels_keyword_bug_match():
    labels = [
        label_matcher.LabelRecord(name="type:bug"),
        label_matcher.LabelRecord(name="type:feature"),
    ]
    vector_store = label_matcher.LabelVectorStore(
        store=object(), provider="unit-test", model="unit-test-model", labels=labels
    )

    matches = label_matcher.find_similar_labels(vector_store, "App crashes on login", threshold=0.8)

    names = [match.label.name for match in matches]
    assert "type:bug" in names
    assert "type:feature" not in names


def test_find_similar_labels_keyword_feature_match():
    labels = [
        label_matcher.LabelRecord(name="type:bug"),
        label_matcher.LabelRecord(name="type:feature"),
    ]
    vector_store = label_matcher.LabelVectorStore(
        store=object(), provider="unit-test", model="unit-test-model", labels=labels
    )

    matches = label_matcher.find_similar_labels(
        vector_store, "Add dark mode support", threshold=0.8
    )

    names = [match.label.name for match in matches]
    assert "type:feature" in names
    assert "type:bug" not in names


def test_find_similar_labels_keyword_feature_phrase_match():
    labels = [
        label_matcher.LabelRecord(name="type:bug"),
        label_matcher.LabelRecord(name="type:feature"),
    ]
    vector_store = label_matcher.LabelVectorStore(
        store=object(), provider="unit-test", model="unit-test-model", labels=labels
    )

    matches = label_matcher.find_similar_labels(vector_store, "Dark mode", threshold=0.8)

    names = [match.label.name for match in matches]
    assert "type:feature" in names
    assert "type:bug" not in names


def test_find_similar_labels_keyword_multicategory_match():
    labels = [
        label_matcher.LabelRecord(name="type:bug"),
        label_matcher.LabelRecord(name="documentation"),
    ]
    vector_store = label_matcher.LabelVectorStore(
        store=object(), provider="unit-test", model="unit-test-model", labels=labels
    )

    matches = label_matcher.find_similar_labels(vector_store, "Bug in docs examples", threshold=0.8)

    names = {match.label.name for match in matches}
    assert "type:bug" in names
    assert "documentation" in names


def test_resolve_label_match_keyword_bug_match():
    labels = [
        label_matcher.LabelRecord(name="type:bug"),
        label_matcher.LabelRecord(name="type:feature"),
    ]
    vector_store = label_matcher.LabelVectorStore(
        store=object(), provider="unit-test", model="unit-test-model", labels=labels
    )

    match = label_matcher.resolve_label_match(vector_store, "App crashes on login", threshold=0.8)

    assert match is not None
    assert match.label.name == "type:bug"
    assert match.score_type == "keyword"


def test_resolve_label_match_keyword_feature_match():
    labels = [
        label_matcher.LabelRecord(name="type:bug"),
        label_matcher.LabelRecord(name="type:feature"),
    ]
    vector_store = label_matcher.LabelVectorStore(
        store=object(), provider="unit-test", model="unit-test-model", labels=labels
    )

    match = label_matcher.resolve_label_match(vector_store, "Add dark mode support", threshold=0.8)

    assert match is not None
    assert match.label.name == "type:feature"
    assert match.score_type == "keyword"
