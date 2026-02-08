from types import SimpleNamespace
from unittest.mock import MagicMock

from tools.llm_provider import OpenAIProvider


def test_openai_provider_analyze_completion_without_quality_context():
    provider = OpenAIProvider()
    mock_client = MagicMock()
    mock_client.invoke.return_value = SimpleNamespace(content="""
{
    "completed": ["task1"],
    "in_progress": [],
    "blocked": [],
    "confidence": 0.8,
    "reasoning": "Task 1 done."
}
""")
    provider._get_client = MagicMock(return_value=mock_client)

    result = provider.analyze_completion("output", ["task1"])

    assert result.completed_tasks == ["task1"]
    mock_client.invoke.assert_called_once()
