import sys
import types
from dataclasses import dataclass

import pytest
from scripts.langchain import label_matcher, semantic_matcher


def test_keyword_matching_rejects_short_prefix_false_positives() -> None:
    assert label_matcher._token_matches_keyword("doctor", "doc") is False
    assert label_matcher._token_matches_keyword("doc", "doctor") is False
    assert label_matcher._token_matches_keyword("documentary", "doc") is False
    assert label_matcher._token_matches_keyword("defective", "defect") is False
    assert label_matcher._token_matches_keyword("doctor", "doctors") is True
    assert label_matcher._token_matches_keyword("docs", "documentation") is True
    assert label_matcher._token_matches_keyword("document", "documentation") is True
    assert label_matcher._token_matches_keyword("crashing", "crash") is True
    assert label_matcher._token_matches_keyword("regressions", "regression") is True
    assert label_matcher._token_matches_keyword("defects", "defect") is True
    assert label_matcher._token_matches_keyword("improve", "improvement") is True
    assert label_matcher._token_matches_keyword("enhance", "enhancement") is True
    assert label_matcher._token_matches_keyword("panicking", "panic") is True


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
        is_fallback=False,
    )
    labels = [
        {"name": "bug", "description": "Something isn't working"},
    ]

    result = label_matcher.build_label_vector_store(labels, client_info=client_info)

    assert result is not None
    assert result.store["texts"] == ["bug\nSomething isn't working"]
    assert result.store["metadatas"] == [{"name": "bug", "description": "Something isn't working"}]
    assert result.is_fallback is False
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
        store=store,
        provider="unit-test",
        model="unit-test-model",
        is_fallback=False,
        labels=[],
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
        store=store,
        provider="unit-test",
        model="unit-test-model",
        is_fallback=False,
        labels=[],
    )

    matches = label_matcher.find_similar_labels(vector_store, "defect", threshold=0.85)

    assert len(matches) == 1
    assert matches[0].label.name == "bug"
    assert matches[0].raw_score == 0.1
    assert matches[0].score_type == "distance"


def test_find_similar_labels_rejects_invalid_inputs():
    vector_store = label_matcher.LabelVectorStore(
        store=object(),
        provider="unit-test",
        model="unit-test-model",
        is_fallback=False,
        labels=[],
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
        store=store,
        provider="unit-test",
        model="unit-test-model",
        is_fallback=False,
        labels=[],
    )

    matches = label_matcher.find_similar_labels(vector_store, "bug", threshold=0.8)

    assert len(matches) == 1
    assert matches[0].label.name == "type:bug"


def test_resolve_label_match_prefers_exact_for_short_labels():
    label = label_matcher.LabelRecord(name="CI", description="Pipeline failures")
    vector_store = label_matcher.LabelVectorStore(
        store=object(),
        provider="unit-test",
        model="unit-test-model",
        is_fallback=False,
        labels=[label],
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
        store=store,
        provider="unit-test",
        model="unit-test-model",
        is_fallback=False,
        labels=[],
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
        store=object(),
        provider="unit-test",
        model="unit-test-model",
        is_fallback=False,
        labels=labels,
    )

    matches = label_matcher.find_similar_labels(vector_store, "App crashes on login", threshold=0.8)

    names = [match.label.name for match in matches]
    assert "type:bug" in names
    assert "type:feature" not in names
    bug_match = next(match for match in matches if match.label.name == "type:bug")
    assert bug_match.score >= label_matcher.KEYWORD_BUG_SCORE


def test_find_similar_labels_keyword_bug_inflection_aliases() -> None:
    labels = [
        label_matcher.LabelRecord(name="type:bug"),
        label_matcher.LabelRecord(name="type:feature"),
    ]
    vector_store = label_matcher.LabelVectorStore(
        store=object(),
        provider="unit-test",
        model="unit-test-model",
        is_fallback=False,
        labels=labels,
    )

    for query in (
        "App keeps crashing on login",
        "The service is panicking under load",
        "Recent regressions in nightly build",
        "Two defects in checkout flow",
    ):
        matches = label_matcher.find_similar_labels(vector_store, query, threshold=0.8)
        names = [match.label.name for match in matches]
        assert "type:bug" in names, query
        assert "type:feature" not in names


def test_find_similar_labels_keyword_feature_verb_aliases() -> None:
    labels = [
        label_matcher.LabelRecord(name="type:bug"),
        label_matcher.LabelRecord(name="type:feature"),
    ]
    vector_store = label_matcher.LabelVectorStore(
        store=object(),
        provider="unit-test",
        model="unit-test-model",
        is_fallback=True,
        labels=labels,
    )

    for query in ("Please improve caching", "Please enhance caching"):
        matches = label_matcher.find_similar_labels(vector_store, query, threshold=0.8)
        names = [match.label.name for match in matches]
        assert "type:feature" in names, query
        assert "type:bug" not in names


def test_find_similar_labels_keyword_feature_match():
    labels = [
        label_matcher.LabelRecord(name="type:bug"),
        label_matcher.LabelRecord(name="type:feature"),
    ]
    vector_store = label_matcher.LabelVectorStore(
        store=object(),
        provider="unit-test",
        model="unit-test-model",
        is_fallback=False,
        labels=labels,
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
        store=object(),
        provider="unit-test",
        model="unit-test-model",
        is_fallback=False,
        labels=labels,
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
        store=object(),
        provider="unit-test",
        model="unit-test-model",
        is_fallback=False,
        labels=labels,
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
        store=object(),
        provider="unit-test",
        model="unit-test-model",
        is_fallback=False,
        labels=labels,
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
        store=store,
        provider="unit-test",
        model="unit-test-model",
        is_fallback=False,
        labels=labels,
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
        store=store,
        provider="unit-test",
        model="unit-test-model",
        is_fallback=False,
        labels=labels,
    )

    matches = label_matcher.find_similar_labels(vector_store, "Bug in docs examples", threshold=0.8)

    assert len(matches) == 1
    assert matches[0].label.name == "Documentation"


def test_body_naming_labels_does_not_sweep_inventory() -> None:
    labels = [
        label_matcher.LabelRecord(name="agent-high-privilege"),
        label_matcher.LabelRecord(name="agent:codex"),
        label_matcher.LabelRecord(name="agent:claude"),
        label_matcher.LabelRecord(name="status:ready"),
        label_matcher.LabelRecord(name="status:in-progress"),
        label_matcher.LabelRecord(name="type:bug"),
        label_matcher.LabelRecord(name="documentation"),
    ]
    vector_store = label_matcher.LabelVectorStore(
        store=object(),
        provider="unit-test",
        model="unit-test-model",
        is_fallback=True,
        labels=labels,
    )

    matches = label_matcher.find_similar_labels(
        vector_store,
        "Agent high privilege label must not auto-apply while a bug status is reviewed.",
        threshold=0.0,
        k=5,
    )

    names = [match.label.name for match in matches]
    assert len(matches) <= 5
    assert sum(name.startswith("agent:") or name.startswith("agent-") for name in names) <= 1
    assert sum(name.startswith("status:") for name in names) <= 1
    auto_apply = label_matcher.issue_auto_apply_matches(matches, threshold=0.9)
    assert "agent-high-privilege" not in [match.label.name for match in auto_apply]
    privileged = next(match for match in matches if match.label.name == "agent-high-privilege")
    assert label_matcher.issue_auto_apply_matches([privileged], threshold=0.9) == []


def test_keyword_overlap_scores_generic_single_tokens_below_auto_apply_threshold() -> None:
    label = label_matcher.LabelRecord(name="agent-high-privilege")
    assert label_matcher._keyword_match_score(label, "agent review") == pytest.approx(0.95 / 3)


def test_issue_auto_apply_requires_a_unique_non_pr_scoped_winner() -> None:
    bug = label_matcher.LabelMatch(
        label=label_matcher.LabelRecord(name="type:bug"),
        score=0.95,
        raw_score=0.95,
        score_type="keyword",
    )
    feature = label_matcher.LabelMatch(
        label=label_matcher.LabelRecord(name="type:feature"),
        score=0.93,
        raw_score=0.93,
        score_type="keyword",
    )
    assert label_matcher.issue_auto_apply_matches([bug, feature], threshold=0.9) == []
    assert label_matcher.issue_auto_apply_matches([bug], threshold=0.9) == [bug]


def test_issue_auto_apply_rejects_at_exact_margin_boundary() -> None:
    # difference == margin (0.05) must be rejected; winning requires strictly more
    winner = label_matcher.LabelMatch(
        label=label_matcher.LabelRecord(name="type:bug"),
        score=0.95,
        raw_score=0.95,
        score_type="keyword",
    )
    runner_up = label_matcher.LabelMatch(
        label=label_matcher.LabelRecord(name="type:feature"),
        score=0.90,
        raw_score=0.90,
        score_type="keyword",
    )
    # 0.95 - 0.90 == 0.05 == default margin → must NOT auto-apply
    assert label_matcher.issue_auto_apply_matches([winner, runner_up], threshold=0.9) == []
    # 0.95 - 0.89 == 0.06 > 0.05 → may auto-apply
    close_but_clear = label_matcher.LabelMatch(
        label=label_matcher.LabelRecord(name="type:feature"),
        score=0.89,
        raw_score=0.89,
        score_type="keyword",
    )
    assert label_matcher.issue_auto_apply_matches([winner, close_but_clear], threshold=0.9) == [
        winner
    ]


def test_issue_auto_apply_sees_same_family_competitors_via_diverse_false() -> None:
    # Without diverse=False, bounded_diverse_matches removes agent:claude before the margin
    # check, so agent:codex would be auto-applied despite a dangerously close score.
    # With diverse=False the caller passes both and the margin check correctly rejects.
    codex = label_matcher.LabelMatch(
        label=label_matcher.LabelRecord(name="agent:codex"),
        score=0.94,
        raw_score=0.94,
        score_type="relevance",
    )
    claude = label_matcher.LabelMatch(
        label=label_matcher.LabelRecord(name="agent:claude"),
        score=0.93,
        raw_score=0.93,
        score_type="relevance",
    )
    # Deduped list (diverse=True path) only shows codex → margin check never fires
    deduped = label_matcher.bounded_diverse_matches([codex, claude], 5)
    assert deduped == [codex]
    assert label_matcher.issue_auto_apply_matches(deduped, threshold=0.9) == [codex]  # BUG path
    # Raw list (diverse=False path) → margin check correctly rejects (0.94 - 0.93 = 0.01 <= 0.05)
    assert label_matcher.issue_auto_apply_matches([codex, claude], threshold=0.9) == []


def test_bounded_diverse_matches_returns_empty_for_non_positive_limits() -> None:
    match = label_matcher.LabelMatch(
        label=label_matcher.LabelRecord(name="type:bug"),
        score=0.95,
        raw_score=0.95,
        score_type="keyword",
    )
    assert label_matcher.bounded_diverse_matches([match], 0) == []
    assert label_matcher.bounded_diverse_matches([match], -1) == []


def test_find_similar_labels_rejects_negative_k() -> None:
    labels = [label_matcher.LabelRecord(name="type:bug")]
    vector_store = label_matcher.LabelVectorStore(
        store=object(),
        provider="unit-test",
        model="unit-test-model",
        is_fallback=False,
        labels=labels,
    )
    with pytest.raises(ValueError, match="k must be a positive integer"):
        label_matcher.find_similar_labels(vector_store, "crash", k=-1)


def test_resolve_label_match_keyword_bug_match():
    labels = [
        label_matcher.LabelRecord(name="type:bug"),
        label_matcher.LabelRecord(name="type:feature"),
    ]
    vector_store = label_matcher.LabelVectorStore(
        store=object(),
        provider="unit-test",
        model="unit-test-model",
        is_fallback=False,
        labels=labels,
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
        store=object(),
        provider="unit-test",
        model="unit-test-model",
        is_fallback=False,
        labels=labels,
    )

    match = label_matcher.resolve_label_match(vector_store, "Add dark mode support", threshold=0.8)

    assert match is not None
    assert match.label.name == "type:feature"
    assert match.score_type == "keyword"
