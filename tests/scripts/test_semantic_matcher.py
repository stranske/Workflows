import sys
import types

from scripts.langchain import semantic_matcher
from tools.embedding_provider import FALLBACK_DIMENSIONS


class StubEmbeddings:
    def __init__(self, model, base_url=None, api_key=None):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key

    def embed_documents(self, texts):
        return [[float(len(text))] for text in texts]


def _install_stub_langchain(monkeypatch):
    module = types.SimpleNamespace(OpenAIEmbeddings=StubEmbeddings)
    monkeypatch.setitem(sys.modules, "langchain_openai", module)


def test_generate_embeddings_uses_client_info():
    client_info = semantic_matcher.EmbeddingClientInfo(
        client=StubEmbeddings("stub-model"),
        provider="stub",
        model="stub-model",
        is_fallback=False,
    )
    result = semantic_matcher.generate_embeddings(["alpha", "beta"], client_info=client_info)
    assert result is not None
    assert result.provider == "stub"
    assert result.model == "stub-model"
    assert result.is_fallback is False
    assert result.dimensions == 1
    assert result.vectors == [[5.0], [4.0]]


def test_generate_embeddings_uses_openai_provider(monkeypatch):
    _install_stub_langchain(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "token")

    result = semantic_matcher.generate_embeddings(["alpha", "beta"])

    assert result is not None
    assert result.provider == "openai"
    assert result.is_fallback is False
    assert result.dimensions == 1


def test_generate_embeddings_uses_fallback_provider(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = semantic_matcher.generate_embeddings(["alpha", "beta"])

    assert result is not None
    assert result.provider == "fallback"
    assert result.is_fallback is True
    assert result.dimensions == FALLBACK_DIMENSIONS


def test_get_embedding_client_prefers_openai(monkeypatch):
    _install_stub_langchain(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "token")

    info = semantic_matcher.get_embedding_client(model="unit-test-model")

    assert info is not None
    assert info.provider == "openai"
    assert info.model == "unit-test-model"
    assert info.is_fallback is False


def test_get_embedding_client_falls_back_without_token(monkeypatch):
    """get_embedding_client returns fallback when no external credentials are available."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    info = semantic_matcher.get_embedding_client()

    assert info is not None
    assert info.provider == "fallback"
    assert info.is_fallback is True


def test_get_embedding_client_uses_env_model(monkeypatch):
    """get_embedding_client uses EMBEDDING_MODEL env var when no model is provided."""
    _install_stub_langchain(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "token")
    monkeypatch.setenv("EMBEDDING_MODEL", "custom-embedding-model")

    info = semantic_matcher.get_embedding_client()

    assert info is not None
    assert info.model == "custom-embedding-model"


def test_get_embedding_client_uses_default_model(monkeypatch):
    """get_embedding_client uses DEFAULT_EMBEDDING_MODEL when no model is specified."""
    _install_stub_langchain(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "token")
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)

    info = semantic_matcher.get_embedding_client()

    assert info is not None
    assert info.model == semantic_matcher.DEFAULT_EMBEDDING_MODEL


def test_generate_embeddings_empty_texts():
    """generate_embeddings returns empty result for empty input."""
    result = semantic_matcher.generate_embeddings([])
    assert result is not None
    assert result.vectors == []
    assert result.provider == "none"


def test_generate_embeddings_strips_whitespace_only_texts():
    """generate_embeddings filters out whitespace-only texts."""
    result = semantic_matcher.generate_embeddings(["", "  ", "\n\t"])
    assert result is not None
    assert result.vectors == []


def test_generate_embeddings_returns_none_without_client(monkeypatch):
    """generate_embeddings returns None when no client is available."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("EMBEDDING_PROVIDER_ALLOWLIST", "openai")

    result = semantic_matcher.generate_embeddings(["some text"])

    assert result is None


def test_generate_embeddings_with_model_override():
    """generate_embeddings respects model parameter."""
    client_info = semantic_matcher.EmbeddingClientInfo(
        client=StubEmbeddings("override-model"),
        provider="test",
        model="override-model",
        is_fallback=False,
    )
    result = semantic_matcher.generate_embeddings(
        ["text"], client_info=client_info, model="ignored"
    )
    assert result is not None
    assert result.model == "override-model"


def test_cosine_similarity_identical_vectors():
    """cosine_similarity returns 1.0 for identical vectors."""
    vec = [1.0, 2.0, 3.0]
    similarity = semantic_matcher.cosine_similarity(vec, vec)
    assert abs(similarity - 1.0) < 0.0001


def test_cosine_similarity_orthogonal_vectors():
    """cosine_similarity returns 0.0 for orthogonal vectors."""
    left = [1.0, 0.0]
    right = [0.0, 1.0]
    similarity = semantic_matcher.cosine_similarity(left, right)
    assert abs(similarity - 0.0) < 0.0001


def test_cosine_similarity_opposite_vectors():
    """cosine_similarity returns -1.0 for opposite vectors."""
    left = [1.0, 0.0]
    right = [-1.0, 0.0]
    similarity = semantic_matcher.cosine_similarity(left, right)
    assert abs(similarity - (-1.0)) < 0.0001


def test_cosine_similarity_empty_vectors():
    """cosine_similarity returns 0.0 for empty vectors."""
    assert semantic_matcher.cosine_similarity([], []) == 0.0


def test_cosine_similarity_mismatched_lengths():
    """cosine_similarity returns 0.0 for vectors of different lengths."""
    assert semantic_matcher.cosine_similarity([1.0, 2.0], [1.0]) == 0.0


def test_cosine_similarity_zero_norm():
    """cosine_similarity returns 0.0 when a vector has zero norm."""
    zero = [0.0, 0.0, 0.0]
    non_zero = [1.0, 2.0, 3.0]
    assert semantic_matcher.cosine_similarity(zero, non_zero) == 0.0
    assert semantic_matcher.cosine_similarity(non_zero, zero) == 0.0


def test_best_cosine_matches_returns_top_k():
    """best_cosine_matches returns top k matches sorted by similarity."""
    query = [1.0, 0.0, 0.0]
    candidates = [
        [1.0, 0.0, 0.0],  # identical (idx 0)
        [0.0, 1.0, 0.0],  # orthogonal (idx 1)
        [0.5, 0.5, 0.0],  # partial match (idx 2)
    ]
    matches = semantic_matcher.best_cosine_matches(query, candidates, top_k=2)

    assert len(matches) == 2
    assert matches[0][0] == 0  # index 0 should be first (identical)
    assert matches[0][1] > 0.9  # should be ~1.0
    assert matches[1][0] == 2  # index 2 should be second (partial)


def test_best_cosine_matches_zero_top_k():
    """best_cosine_matches returns empty list when top_k is 0."""
    query = [1.0, 0.0]
    candidates = [[1.0, 0.0], [0.0, 1.0]]
    matches = semantic_matcher.best_cosine_matches(query, candidates, top_k=0)
    assert matches == []


def test_best_cosine_matches_negative_top_k():
    """best_cosine_matches returns empty list when top_k is negative."""
    query = [1.0, 0.0]
    candidates = [[1.0, 0.0]]
    matches = semantic_matcher.best_cosine_matches(query, candidates, top_k=-1)
    assert matches == []


def test_best_cosine_matches_empty_candidates():
    """best_cosine_matches handles empty candidates list."""
    query = [1.0, 0.0]
    matches = semantic_matcher.best_cosine_matches(query, [], top_k=5)
    assert matches == []


def test_best_cosine_matches_top_k_exceeds_candidates():
    """best_cosine_matches returns all candidates when top_k exceeds count."""
    query = [1.0, 0.0]
    candidates = [[1.0, 0.0], [0.0, 1.0]]
    matches = semantic_matcher.best_cosine_matches(query, candidates, top_k=10)
    assert len(matches) == 2
