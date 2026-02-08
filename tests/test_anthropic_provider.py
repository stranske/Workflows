from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tools.llm_provider import AnthropicProvider, CompletionAnalysis, GitHubModelsProvider


def test_anthropic_provider_forwards_quality_context_to_client_invoke(
    monkeypatch: pytest.MonkeyPatch,
):
    sentinel = object()

    class DummyClient:
        def __init__(self) -> None:
            self.invoke = MagicMock(side_effect=self._invoke)

        def _invoke(self, *_args, **_kwargs):
            return SimpleNamespace(content="""
{
    "completed": ["task1"],
    "in_progress": [],
    "blocked": [],
    "confidence": 0.8,
    "reasoning": "Task 1 done."
}
""")

    client = DummyClient()
    provider = AnthropicProvider()
    provider._get_client = MagicMock(return_value=client)
    monkeypatch.setattr(
        GitHubModelsProvider,
        "_parse_response",
        MagicMock(
            return_value=CompletionAnalysis(
                completed_tasks=["task1"],
                in_progress_tasks=[],
                blocked_tasks=[],
                confidence=0.8,
                reasoning="Task 1 done.",
                provider_used="anthropic",
            )
        ),
    )

    provider.analyze_completion("output", ["task1"], quality_context=sentinel)

    client.invoke.assert_called_once()
    assert client.invoke.call_args.kwargs["quality_context"] is sentinel


def test_anthropic_provider_propagates_invoke_errors():
    class DummyClient:
        def invoke(self, _prompt: str, **_kwargs):
            raise TimeoutError("boom")

    provider = AnthropicProvider()
    provider._get_client = MagicMock(return_value=DummyClient())

    with pytest.raises(TimeoutError):
        provider.analyze_completion("output", ["task1"])
