from unittest.mock import MagicMock

import tools.llm_provider as llm_provider
from tools.llm_provider import GitHubModelsProvider, SessionQualityContext


def test_confidence_capped_for_sub_50_analysis_text_with_work_evidence():
    response = """
{
    "completed": ["task1"],
    "in_progress": [],
    "blocked": [],
    "confidence": 0.95,
    "reasoning": "Short analysis."
}
"""
    mock_client = MagicMock()
    mock_client.invoke.return_value = MagicMock(content=response)

    quality_context = SessionQualityContext(
        has_agent_messages=False,
        has_work_evidence=True,
        file_change_count=2,
        successful_command_count=1,
        estimated_effort_score=6,
        data_quality="high",
        analysis_text_length=40,
    )

    provider = GitHubModelsProvider()
    provider._get_client = MagicMock(return_value=mock_client)
    result = provider.analyze_completion(
        "output",
        ["task1"],
        quality_context=quality_context,
    )

    assert result.confidence <= llm_provider.SHORT_ANALYSIS_CONFIDENCE_CAP
