from tools.llm_provider import (
    SHORT_ANALYSIS_CONFIDENCE_CAP,
    CompletionAnalysis,
    FallbackChainProvider,
    GitHubModelsProvider,
    SessionQualityContext,
)


class QualityAwareProvider(GitHubModelsProvider):
    @property
    def name(self) -> str:
        return "quality-aware"

    def is_available(self) -> bool:
        return True

    def analyze_completion(
        self,
        session_output: str,
        tasks: list[str],
        context: str | None = None,
        quality_context: SessionQualityContext | None = None,
    ) -> CompletionAnalysis:
        response = """
{
    "completed": ["task1"],
    "in_progress": [],
    "blocked": [],
    "confidence": 0.95,
    "reasoning": "Short analysis."
}
"""
        parsed = self._parse_response(
            response,
            tasks,
            quality_context=quality_context,
        )
        return CompletionAnalysis(
            completed_tasks=parsed.completed_tasks,
            in_progress_tasks=parsed.in_progress_tasks,
            blocked_tasks=parsed.blocked_tasks,
            confidence=parsed.confidence,
            reasoning=parsed.reasoning,
            provider_used=self.name,
            raw_confidence=parsed.raw_confidence,
            confidence_adjusted=parsed.confidence_adjusted,
            quality_warnings=parsed.quality_warnings,
        )


def test_confidence_capped_for_sub_50_analysis_text_with_work_evidence():
    quality_context = SessionQualityContext(
        has_agent_messages=False,
        has_work_evidence=True,
        file_change_count=2,
        successful_command_count=1,
        estimated_effort_score=6,
        data_quality="high",
        analysis_text_length=40,
    )

    chain = FallbackChainProvider([QualityAwareProvider()])
    result = chain.analyze_completion(
        "output",
        ["task1"],
        quality_context=quality_context,
    )

    assert result.confidence <= SHORT_ANALYSIS_CONFIDENCE_CAP
