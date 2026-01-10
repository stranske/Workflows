import sys
import types
from dataclasses import dataclass

import pytest

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


def test_build_label_vector_store_rejects_invalid_label_iterables():
    with pytest.raises(ValueError, match="labels must be an iterable of label records, not None."):
        label_matcher.build_label_vector_store(None)
    with pytest.raises(
        ValueError,
        match="labels must be an iterable of label records, not a string.",
    ):
        label_matcher.build_label_vector_store("bug")
    with pytest.raises(ValueError, match="labels must be an iterable of label records."):
        label_matcher.build_label_vector_store(123)


def test_build_label_vector_store_rejects_invalid_label_entries():
    with pytest.raises(ValueError, match="Label entry at index 0 is missing a name."):
        label_matcher.build_label_vector_store([{"description": "missing name"}])
    with pytest.raises(ValueError, match="Label entry at index 0 has an empty name."):
        label_matcher.build_label_vector_store([types.SimpleNamespace(name=" ")])
    with pytest.raises(
        ValueError,
        match="Unsupported label entry at index 0: int.",
    ):
        label_matcher.build_label_vector_store([123])


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


def test_find_similar_labels_rejects_invalid_inputs():
    vector_store = label_matcher.LabelVectorStore(
        store=object(), provider="unit-test", model="unit-test-model", labels=[]
    )

    with pytest.raises(ValueError, match="label_store must be a LabelVectorStore instance."):
        label_matcher.find_similar_labels(object(), "bug")
    with pytest.raises(ValueError, match="query must be a string."):
        label_matcher.find_similar_labels(vector_store, None)


def test_find_similar_labels_handles_missing_metadata_name():
    store = types.SimpleNamespace(
        similarity_search_with_relevance_scores=lambda query, k=5: [
            (DummyDoc("type:bug", None), 0.92),
        ]
    )
    vector_store = label_matcher.LabelVectorStore(
        store=store, provider="unit-test", model="unit-test-model", labels=[]
    )

    matches = label_matcher.find_similar_labels(vector_store, "bug", threshold=0.8)

    assert len(matches) == 1
    assert matches[0].label.name == "type:bug"


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
    bug_match = next(match for match in matches if match.label.name == "type:bug")
    assert bug_match.score >= label_matcher.KEYWORD_BUG_SCORE


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
    doc_match = next(match for match in matches if match.label.name == "documentation")
    assert doc_match.score >= label_matcher.KEYWORD_DOCS_SCORE


def test_find_similar_labels_keyword_docs_description_match():
    """Test that labels with 'doc' in their NAME match docs keywords."""
    labels = [
        label_matcher.LabelRecord(name="type:bug"),
        label_matcher.LabelRecord(name="type:documentation", description="Documentation updates"),
    ]
    vector_store = label_matcher.LabelVectorStore(
        store=object(), provider="unit-test", model="unit-test-model", labels=labels
    )

    matches = label_matcher.find_similar_labels(vector_store, "Bug in docs examples", threshold=0.8)

    names = {match.label.name for match in matches}
    assert "type:bug" in names
    assert "type:documentation" in names
    doc_match = next(match for match in matches if match.label.name == "type:documentation")
    assert doc_match.score >= label_matcher.KEYWORD_DOCS_SCORE


def test_find_similar_labels_appends_keyword_matches_after_semantic():
    labels = [
        label_matcher.LabelRecord(name="type:bug"),
        label_matcher.LabelRecord(name="documentation"),
    ]
    store = types.SimpleNamespace(
        similarity_search_with_relevance_scores=lambda query, k=5: [
            (DummyDoc("type:bug", {"name": "type:bug"}), 0.92),
        ]
    )
    vector_store = label_matcher.LabelVectorStore(
        store=store, provider="unit-test", model="unit-test-model", labels=labels
    )

    matches = label_matcher.find_similar_labels(vector_store, "Bug in docs examples", threshold=0.8)

    names = {match.label.name for match in matches}
    assert "type:bug" in names
    assert "documentation" in names
    doc_match = next(match for match in matches if match.label.name == "documentation")
    assert doc_match.score >= label_matcher.KEYWORD_DOCS_SCORE


def test_find_similar_labels_dedupes_normalized_keyword_matches():
    labels = [label_matcher.LabelRecord(name="documentation")]
    store = types.SimpleNamespace(
        similarity_search_with_relevance_scores=lambda query, k=5: [
            (DummyDoc("Documentation", {"name": "Documentation"}), 0.92),
        ]
    )
    vector_store = label_matcher.LabelVectorStore(
        store=store, provider="unit-test", model="unit-test-model", labels=labels
    )

    matches = label_matcher.find_similar_labels(vector_store, "Bug in docs examples", threshold=0.8)

    assert len(matches) == 1
    assert matches[0].label.name == "Documentation"


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
