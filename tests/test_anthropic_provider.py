from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tools.llm_provider import AnthropicProvider, SessionQualityContext


def test_anthropic_provider_forwards_quality_context_to_client_invoke():
    sentinel = SessionQualityContext(
        has_agent_messages=False,
        has_work_evidence=False,
        file_change_count=0,
        successful_command_count=0,
        estimated_effort_score=0,
        data_quality="high",
        analysis_text_length=250,
    )

    class DummyClient:
        def __init__(self) -> None:
            self.invoke = MagicMock(side_effect=self._invoke)

        def _invoke(self, _prompt: str, **kwargs):
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

    provider.analyze_completion("output", ["task1"], quality_context=sentinel)

    assert client.invoke.call_args is not None
    assert client.invoke.call_args.kwargs["quality_context"] is sentinel


def test_anthropic_provider_propagates_invoke_errors():
    class DummyClient:
        def invoke(self, _prompt: str, **_kwargs):
            raise TimeoutError("boom")

    provider = AnthropicProvider()
    provider._get_client = MagicMock(return_value=DummyClient())

    with pytest.raises(TimeoutError):
        provider.analyze_completion("output", ["task1"])
