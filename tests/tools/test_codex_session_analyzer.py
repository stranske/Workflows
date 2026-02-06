"""Tests for tools/codex_session_analyzer.py."""

from __future__ import annotations

from unittest.mock import patch

from tools.codex_session_analyzer import analyze_session
from tools.llm_provider import (
    CompletionAnalysis,
    FallbackChainProvider,
    GitHubModelsProvider,
    LLMProvider,
    SessionQualityContext,
)


class RecordingProvider(LLMProvider):
    """Provider that records the quality context received."""

    def __init__(self) -> None:
        self.received_quality_context: SessionQualityContext | None = None

    @property
    def name(self) -> str:
        return "recording"

    def is_available(self) -> bool:
        return True

    def analyze_completion(
        self,
        session_output: str,
        tasks: list[str],
        context: str | None = None,
        quality_context: SessionQualityContext | None = None,
    ) -> CompletionAnalysis:
        self.received_quality_context = quality_context
        return CompletionAnalysis(
            completed_tasks=[],
            in_progress_tasks=[],
            blocked_tasks=[],
            confidence=0.4,
            reasoning="recording",
            provider_used=self.name,
        )


def test_analyze_session_passes_quality_context_through_fallback_chain():
    """Quality context is passed to the active provider in fallback chain."""
    provider = RecordingProvider()
    chain = FallbackChainProvider([provider])
    summary_text = "Summary of work completed."

    with patch("tools.codex_session_analyzer.get_llm_provider", return_value=chain):
        analyze_session(summary_text, ["task1"], data_source="summary")

    assert provider.received_quality_context is not None
    assert provider.received_quality_context.analysis_text_length == len(summary_text)


def test_analyze_session_reports_quality_context_capable_providers():
    """Analysis result lists providers that support quality_context."""
    provider = RecordingProvider()
    chain = FallbackChainProvider([provider])
    summary_text = "Summary of work completed."

    with patch("tools.codex_session_analyzer.get_llm_provider", return_value=chain):
        result = analyze_session(summary_text, ["task1"], data_source="summary")

    assert result.quality_context_capable_providers == ["recording"]


def test_analyze_session_passes_quality_context_from_jsonl():
    """JSONL parsing passes quality context derived from session evidence."""
    provider = RecordingProvider()
    chain = FallbackChainProvider([provider])
    jsonl = "\n".join(
        [
            '{"type": "item.completed", "item": {"id": "msg_1", "type": "agent_message", "text": "Did work."}}',
            '{"type": "item.completed", "item_type": "command_execution", "command": "pytest tests/", "exit_code": 0, "output": "1 passed"}',
        ]
    )

    with patch("tools.codex_session_analyzer.get_llm_provider", return_value=chain):
        analyze_session(jsonl, ["task1"], data_source="jsonl")

    assert provider.received_quality_context is not None
    assert provider.received_quality_context.has_work_evidence is True
    assert provider.received_quality_context.successful_command_count == 1
    assert provider.received_quality_context.analysis_text_length > 0


def test_analyze_session_skips_quality_context_for_legacy_provider():
    """Analyze session skips quality_context when provider doesn't support it."""

    class LegacyProvider(LLMProvider):
        def __init__(self) -> None:
            self.called = False

        @property
        def name(self) -> str:
            return "legacy"

        def is_available(self) -> bool:
            return True

        def analyze_completion(
            self,
            session_output: str,
            tasks: list[str],
            context: str | None = None,
        ) -> CompletionAnalysis:
            self.called = True
            _ = session_output
            _ = tasks
            _ = context
            return CompletionAnalysis(
                completed_tasks=[],
                in_progress_tasks=[],
                blocked_tasks=[],
                confidence=0.2,
                reasoning="legacy",
                provider_used=self.name,
            )

    provider = LegacyProvider()
    summary_text = "Summary of work completed."

    with patch("tools.codex_session_analyzer.get_llm_provider", return_value=provider):
        result = analyze_session(summary_text, ["task1"], data_source="summary")

    assert provider.called is True
    assert result.completion.provider_used == "legacy"


def test_analyze_session_caps_confidence_for_short_jsonl_analysis():
    """Short JSONL analysis with work evidence caps confidence via quality context."""

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
    "confidence": 0.9,
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

    jsonl = "\n".join(
        [
            '{"type": "item.completed", "item": {"id": "msg_1", "type": "agent_message", "text": "Did work."}}',
            '{"type": "item.completed", "item_type": "file_change", "path": "src/app.py", "change_type": "modified"}',
        ]
    )

    chain = FallbackChainProvider([QualityAwareProvider()])
    with patch("tools.codex_session_analyzer.get_llm_provider", return_value=chain):
        result = analyze_session(jsonl, ["task1"], data_source="jsonl_filtered")

    assert result.completion.confidence <= 0.4
    assert result.completion.confidence_adjusted is True
