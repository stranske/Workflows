from types import SimpleNamespace

from tools.llm_provider import GitHubModelsProvider


def test_github_models_provider_analyze_completion_without_quality_context(monkeypatch):
    provider = GitHubModelsProvider()

    class DummyClient:
        def __init__(self):
            self.calls = []

        def invoke(self, prompt: str):
            self.calls.append(prompt)
            return SimpleNamespace(
                content='''
{
    "completed": ["task1"],
    "in_progress": [],
    "blocked": [],
    "confidence": 0.8,
    "reasoning": "Task 1 done."
}
'''
            )

    client = DummyClient()
    monkeypatch.setattr(provider, "_get_client", lambda: client)

    result = provider.analyze_completion("output", ["task1"])

    assert result.completed_tasks == ["task1"]
    assert client.calls
