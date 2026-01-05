import sys
import types

from scripts.langchain import semantic_matcher


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
    )
    result = semantic_matcher.generate_embeddings(["alpha", "beta"], client_info=client_info)
    assert result is not None
    assert result.provider == "stub"
    assert result.model == "stub-model"
    assert result.vectors == [[5.0], [4.0]]


def test_get_embedding_client_prefers_github_models(monkeypatch):
    _install_stub_langchain(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    info = semantic_matcher.get_embedding_client(model="unit-test-model")

    assert info is not None
    assert info.provider == "github-models"
    assert info.model == "unit-test-model"
    assert info.client.base_url == semantic_matcher.GITHUB_MODELS_BASE_URL


def test_get_embedding_client_falls_back_to_openai(monkeypatch):
    _install_stub_langchain(monkeypatch)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "token")

    info = semantic_matcher.get_embedding_client(model="unit-test-model")

    assert info is not None
    assert info.provider == "openai"
    assert info.model == "unit-test-model"
    assert info.client.base_url is None
