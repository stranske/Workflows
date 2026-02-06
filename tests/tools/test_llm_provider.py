"""Tests for tools/llm_provider.py"""

import inspect
import os
from unittest.mock import MagicMock, patch

import pytest

from tools.llm_provider import (
    CompletionAnalysis,
    FallbackChainProvider,
    GitHubModelsProvider,
    LLMProvider,
    OpenAIProvider,
    RegexFallbackProvider,
    SessionQualityContext,
    check_providers,
    get_llm_provider,
    get_quality_context_capable_providers,
    get_quality_context_support_table,
    supports_quality_context,
)


class TestProviderAvailability:
    """Test provider availability checks."""

    def test_github_models_available_with_token(self):
        """GitHub Models is available when GITHUB_TOKEN is set."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"}):
            provider = GitHubModelsProvider()
            assert provider.is_available() is True

    def test_github_models_unavailable_without_token(self):
        """GitHub Models is unavailable without GITHUB_TOKEN."""
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_TOKEN"}
        with patch.dict(os.environ, env, clear=True):
            provider = GitHubModelsProvider()
            assert provider.is_available() is False

    def test_openai_available_with_key(self):
        """OpenAI is available when OPENAI_API_KEY is set."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            provider = OpenAIProvider()
            assert provider.is_available() is True

    def test_openai_unavailable_without_key(self):
        """OpenAI is unavailable without OPENAI_API_KEY."""
        env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            provider = OpenAIProvider()
            assert provider.is_available() is False

    def test_regex_always_available(self):
        """Regex fallback is always available."""
        provider = RegexFallbackProvider()
        assert provider.is_available() is True

    def test_check_providers_returns_dict(self):
        """check_providers returns availability dict."""
        result = check_providers()
        assert isinstance(result, dict)
        assert "github-models" in result
        assert "openai" in result
        assert "regex-fallback" in result
        assert result["regex-fallback"] is True

    def test_quality_context_capable_providers(self):
        """Quality-context-capable providers are identified."""
        result = get_quality_context_capable_providers()
        assert "github-models" in result
        assert "openai" in result
        assert "regex-fallback" not in result

    def test_quality_context_support_table(self):
        """Support table documents which built-ins accept quality_context."""
        result = get_quality_context_support_table()
        assert result["github-models"] is True
        assert result["openai"] is True
        assert result["regex-fallback"] is False


class TestLLMProviderInterface:
    """Test LLMProvider interface expectations."""

    def test_analyze_completion_signature_includes_quality_context_default_none(self):
        """Interface defines optional quality_context with default None."""
        signature = inspect.signature(LLMProvider.analyze_completion)
        assert "quality_context" in signature.parameters
        assert signature.parameters["quality_context"].default is None

    def test_supports_quality_context_with_kwargs(self):
        """supports_quality_context returns True for providers accepting **kwargs."""

        class KwargsProvider(LLMProvider):
            @property
            def name(self) -> str:
                return "kwargs-provider"

            def is_available(self) -> bool:
                return True

            def analyze_completion(
                self,
                session_output: str,
                tasks: list[str],
                context: str | None = None,
                **_kwargs: object,
            ) -> CompletionAnalysis:
                _ = session_output
                _ = tasks
                _ = context
                return CompletionAnalysis(
                    completed_tasks=[],
                    in_progress_tasks=[],
                    blocked_tasks=[],
                    confidence=0.5,
                    reasoning="kwargs",
                    provider_used=self.name,
                )

        provider = KwargsProvider()
        assert supports_quality_context(provider) is True

    def test_supports_quality_context_falls_back_on_supports_error(self):
        """supports_quality_context falls back to signature when helper errors."""

        class ErroringSupportProvider(LLMProvider):
            @property
            def name(self) -> str:
                return "erroring-support"

            def is_available(self) -> bool:
                return True

            def supports_quality_context(self) -> bool:
                raise RuntimeError("boom")

            def analyze_completion(
                self,
                session_output: str,
                tasks: list[str],
                context: str | None = None,
                quality_context: SessionQualityContext | None = None,
            ) -> CompletionAnalysis:
                _ = session_output
                _ = tasks
                _ = context
                _ = quality_context
                return CompletionAnalysis(
                    completed_tasks=[],
                    in_progress_tasks=[],
                    blocked_tasks=[],
                    confidence=0.5,
                    reasoning="erroring support",
                    provider_used=self.name,
                )

        provider = ErroringSupportProvider()
        assert supports_quality_context(provider) is True


class TestRegexFallbackProvider:
    """Test regex-based analysis."""

    def test_detects_completion_keywords(self):
        """Regex detects completion keywords."""
        provider = RegexFallbackProvider()
        tasks = ["Fix the calculator tests"]
        output = "I have completed fixing the calculator tests. They all pass now."

        result = provider.analyze_completion(output, tasks)
        assert len(result.completed_tasks) == 1
        assert result.provider_used == "regex-fallback"
        assert result.confidence < 0.5  # Low confidence for regex

    def test_detects_progress_keywords(self):
        """Regex detects progress keywords."""
        provider = RegexFallbackProvider()
        tasks = ["Update documentation"]
        output = "I'm working on updating the documentation now."

        result = provider.analyze_completion(output, tasks)
        assert len(result.in_progress_tasks) == 1

    def test_detects_blocker_keywords(self):
        """Regex detects blocker keywords."""
        provider = RegexFallbackProvider()
        tasks = ["Deploy to production"]
        output = "I'm blocked on the deploy - there's an error with credentials."

        result = provider.analyze_completion(output, tasks)
        assert len(result.blocked_tasks) == 1

    def test_no_false_positives_without_keywords(self):
        """No detection without relevant keywords."""
        provider = RegexFallbackProvider()
        tasks = ["Implement feature X"]
        output = "Looking at the codebase structure."

        result = provider.analyze_completion(output, tasks)
        assert len(result.completed_tasks) == 0
        assert len(result.in_progress_tasks) == 0
        assert len(result.blocked_tasks) == 0


class TestFallbackChainProvider:
    """Test fallback chain behavior."""

    def test_uses_first_available_provider(self):
        """Chain uses first available provider."""
        mock_provider1 = MagicMock()
        mock_provider1.name = "mock1"
        mock_provider1.is_available.return_value = False

        mock_provider2 = MagicMock()
        mock_provider2.name = "mock2"
        mock_provider2.is_available.return_value = True
        mock_provider2.analyze_completion.return_value = CompletionAnalysis(
            completed_tasks=["task1"],
            in_progress_tasks=[],
            blocked_tasks=[],
            confidence=0.9,
            reasoning="test",
            provider_used="mock2",
        )

        chain = FallbackChainProvider([mock_provider1, mock_provider2])
        result = chain.analyze_completion("output", ["task1"])

        mock_provider1.analyze_completion.assert_not_called()
        mock_provider2.analyze_completion.assert_called()
        assert result.provider_used == "mock2"

    def test_passes_quality_context(self):
        """Chain forwards quality context to providers."""
        mock_provider = MagicMock()
        mock_provider.name = "mock"
        mock_provider.is_available.return_value = True
        mock_provider.analyze_completion.return_value = CompletionAnalysis(
            completed_tasks=[],
            in_progress_tasks=[],
            blocked_tasks=[],
            confidence=0.5,
            reasoning="ok",
            provider_used="mock",
        )

        quality_context = SessionQualityContext(
            has_agent_messages=True,
            has_work_evidence=True,
            file_change_count=1,
            successful_command_count=0,
            estimated_effort_score=10,
            data_quality="low",
            analysis_text_length=120,
        )

        chain = FallbackChainProvider([mock_provider])
        chain.analyze_completion(
            "output",
            ["task1"],
            context="ctx",
            quality_context=quality_context,
        )

        mock_provider.analyze_completion.assert_called_with(
            session_output="output",
            tasks=["task1"],
            context="ctx",
            quality_context=quality_context,
        )

    def test_passes_quality_context_to_kwargs_provider(self):
        """Chain forwards quality context to providers accepting **kwargs."""

        class KwargsProvider(LLMProvider):
            def __init__(self) -> None:
                self.received_quality_context: SessionQualityContext | None = None

            @property
            def name(self) -> str:
                return "kwargs-provider"

            def is_available(self) -> bool:
                return True

            def analyze_completion(
                self,
                session_output: str,
                tasks: list[str],
                context: str | None = None,
                **kwargs: object,
            ) -> CompletionAnalysis:
                _ = session_output
                _ = tasks
                _ = context
                self.received_quality_context = kwargs.get("quality_context")
                return CompletionAnalysis(
                    completed_tasks=[],
                    in_progress_tasks=[],
                    blocked_tasks=[],
                    confidence=0.5,
                    reasoning="kwargs",
                    provider_used=self.name,
                )

        quality_context = SessionQualityContext(
            has_agent_messages=True,
            has_work_evidence=True,
            file_change_count=2,
            successful_command_count=1,
            estimated_effort_score=7,
            data_quality="low",
            analysis_text_length=120,
        )

        provider = KwargsProvider()
        chain = FallbackChainProvider([provider])
        chain.analyze_completion(
            "output",
            ["task1"],
            context="ctx",
            quality_context=quality_context,
        )

        assert provider.received_quality_context is quality_context

    def test_quality_context_capable_providers_list(self):
        """Chain reports providers that support quality_context."""

        class LegacyProvider(LLMProvider):
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
                _ = session_output
                _ = tasks
                _ = context
                return CompletionAnalysis(
                    completed_tasks=[],
                    in_progress_tasks=[],
                    blocked_tasks=[],
                    confidence=0.0,
                    reasoning="legacy",
                    provider_used=self.name,
                )

        chain = FallbackChainProvider(
            [LegacyProvider(), RegexFallbackProvider(), GitHubModelsProvider()]
        )

        assert chain.quality_context_capable_providers() == ["github-models"]

    def test_passes_quality_context_for_attribute_support_provider(self):
        """Chain forwards quality context when provider uses attribute flag."""

        class AttrSupportProvider(LLMProvider):
            supports_quality_context = True

            def __init__(self) -> None:
                self.received_quality_context: SessionQualityContext | None = None

            @property
            def name(self) -> str:
                return "attr-support"

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
                    confidence=0.5,
                    reasoning="attr",
                    provider_used=self.name,
                )

        quality_context = SessionQualityContext(
            has_agent_messages=True,
            has_work_evidence=True,
            file_change_count=1,
            successful_command_count=0,
            estimated_effort_score=3,
            data_quality="low",
            analysis_text_length=120,
        )

        provider = AttrSupportProvider()
        chain = FallbackChainProvider([provider])
        chain.analyze_completion(
            "output",
            ["task1"],
            context="ctx",
            quality_context=quality_context,
        )

        assert provider.received_quality_context is quality_context

    def test_skips_quality_context_for_legacy_provider(self):
        """Chain avoids passing quality context to legacy providers."""

        class LegacyProvider(LLMProvider):
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
                return CompletionAnalysis(
                    completed_tasks=["task1"],
                    in_progress_tasks=[],
                    blocked_tasks=[],
                    confidence=0.6,
                    reasoning="legacy",
                    provider_used=self.name,
                )

        quality_context = SessionQualityContext(
            has_agent_messages=True,
            has_work_evidence=True,
            file_change_count=2,
            successful_command_count=1,
            estimated_effort_score=12,
            data_quality="medium",
            analysis_text_length=150,
        )

        chain = FallbackChainProvider([LegacyProvider()])
        result = chain.analyze_completion(
            "output",
            ["task1"],
            context="ctx",
            quality_context=quality_context,
        )

        assert result.completed_tasks == ["task1"]

    def test_retries_without_quality_context_on_type_error(self):
        """Chain retries without quality_context when provider rejects it."""
        mock_provider = MagicMock()
        mock_provider.name = "misleading"
        mock_provider.is_available.return_value = True
        mock_provider.supports_quality_context = True
        mock_provider.analyze_completion.side_effect = [
            TypeError("analyze_completion() got an unexpected keyword argument 'quality_context'"),
            CompletionAnalysis(
                completed_tasks=["task1"],
                in_progress_tasks=[],
                blocked_tasks=[],
                confidence=0.6,
                reasoning="retry",
                provider_used="misleading",
            ),
        ]

        quality_context = SessionQualityContext(
            has_agent_messages=True,
            has_work_evidence=False,
            file_change_count=0,
            successful_command_count=0,
            estimated_effort_score=1,
            data_quality="low",
            analysis_text_length=90,
        )

        chain = FallbackChainProvider([mock_provider])
        result = chain.analyze_completion(
            "output",
            ["task1"],
            context="ctx",
            quality_context=quality_context,
        )

        assert result.provider_used == "misleading"
        assert len(mock_provider.analyze_completion.call_args_list) == 2
        first_call = mock_provider.analyze_completion.call_args_list[0]
        assert "quality_context" in first_call.kwargs
        second_call = mock_provider.analyze_completion.call_args_list[1]
        assert "quality_context" not in second_call.kwargs

    def test_retries_without_quality_context_on_multiple_values_type_error(self):
        """Chain retries when provider errors on duplicated quality_context values."""
        mock_provider = MagicMock()
        mock_provider.name = "misleading"
        mock_provider.is_available.return_value = True
        mock_provider.supports_quality_context = True
        mock_provider.analyze_completion.side_effect = [
            TypeError("analyze_completion() got multiple values for argument 'quality_context'"),
            CompletionAnalysis(
                completed_tasks=["task1"],
                in_progress_tasks=[],
                blocked_tasks=[],
                confidence=0.6,
                reasoning="retry",
                provider_used="misleading",
            ),
        ]

        quality_context = SessionQualityContext(
            has_agent_messages=True,
            has_work_evidence=False,
            file_change_count=0,
            successful_command_count=0,
            estimated_effort_score=1,
            data_quality="low",
            analysis_text_length=90,
        )

        chain = FallbackChainProvider([mock_provider])
        result = chain.analyze_completion(
            "output",
            ["task1"],
            context="ctx",
            quality_context=quality_context,
        )

        assert result.provider_used == "misleading"
        assert len(mock_provider.analyze_completion.call_args_list) == 2
        first_call = mock_provider.analyze_completion.call_args_list[0]
        assert "quality_context" in first_call.kwargs
        second_call = mock_provider.analyze_completion.call_args_list[1]
        assert "quality_context" not in second_call.kwargs

    def test_regex_fallback_accepts_context_kwargs(self):
        """Regex fallback handles context keyword via fallback chain."""
        chain = FallbackChainProvider([RegexFallbackProvider()])

        quality_context = SessionQualityContext(
            has_agent_messages=False,
            has_work_evidence=False,
            file_change_count=0,
            successful_command_count=0,
            estimated_effort_score=0,
            data_quality="minimal",
            analysis_text_length=80,
        )

        result = chain.analyze_completion(
            "No task updates yet.",
            ["task1"],
            context="ctx",
            quality_context=quality_context,
        )

        assert result.provider_used == "regex-fallback"

    def test_prefers_quality_context_provider(self):
        """Chain prefers providers that support quality_context when available."""

        class LegacyProvider(LLMProvider):
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
                return CompletionAnalysis(
                    completed_tasks=["legacy"],
                    in_progress_tasks=[],
                    blocked_tasks=[],
                    confidence=0.6,
                    reasoning="legacy",
                    provider_used=self.name,
                )

        class QualityAwareProvider(LLMProvider):
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
                return CompletionAnalysis(
                    completed_tasks=["quality-aware"],
                    in_progress_tasks=[],
                    blocked_tasks=[],
                    confidence=0.7,
                    reasoning="quality-aware",
                    provider_used=self.name,
                )

        quality_context = SessionQualityContext(
            has_agent_messages=True,
            has_work_evidence=True,
            file_change_count=1,
            successful_command_count=1,
            estimated_effort_score=10,
            data_quality="medium",
            analysis_text_length=250,
        )

        chain = FallbackChainProvider([LegacyProvider(), QualityAwareProvider()])
        result = chain.analyze_completion(
            "output",
            ["task1"],
            quality_context=quality_context,
        )

        assert result.provider_used == "quality-aware"

    def test_quality_context_reaches_selected_provider(self):
        """Chain forwards quality_context to the active quality-aware provider."""

        class LegacyProvider(LLMProvider):
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
                return CompletionAnalysis(
                    completed_tasks=["legacy"],
                    in_progress_tasks=[],
                    blocked_tasks=[],
                    confidence=0.6,
                    reasoning="legacy",
                    provider_used=self.name,
                )

        class QualityAwareProvider(LLMProvider):
            def __init__(self) -> None:
                self.received_quality_context: SessionQualityContext | None = None

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
                self.received_quality_context = quality_context
                return CompletionAnalysis(
                    completed_tasks=["quality-aware"],
                    in_progress_tasks=[],
                    blocked_tasks=[],
                    confidence=0.7,
                    reasoning="quality-aware",
                    provider_used=self.name,
                )

        quality_context = SessionQualityContext(
            has_agent_messages=True,
            has_work_evidence=True,
            file_change_count=2,
            successful_command_count=1,
            estimated_effort_score=12,
            data_quality="high",
            analysis_text_length=300,
        )

        quality_provider = QualityAwareProvider()
        chain = FallbackChainProvider([LegacyProvider(), quality_provider])

        result = chain.analyze_completion(
            "output",
            ["task1"],
            quality_context=quality_context,
        )

        assert result.provider_used == "quality-aware"
        assert quality_provider.received_quality_context is quality_context

    def test_supports_quality_context_reflects_children(self):
        """Chain reports quality context support only when a child supports it."""

        class LegacyProvider(LLMProvider):
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
                return CompletionAnalysis(
                    completed_tasks=[],
                    in_progress_tasks=[],
                    blocked_tasks=[],
                    confidence=0.4,
                    reasoning="legacy",
                    provider_used=self.name,
                )

        class QualityAwareProvider(LLMProvider):
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
                _ = quality_context
                return CompletionAnalysis(
                    completed_tasks=[],
                    in_progress_tasks=[],
                    blocked_tasks=[],
                    confidence=0.5,
                    reasoning="quality-aware",
                    provider_used=self.name,
                )

        legacy_chain = FallbackChainProvider([LegacyProvider()])
        assert legacy_chain.supports_quality_context() is False

        quality_chain = FallbackChainProvider([LegacyProvider(), QualityAwareProvider()])
        assert quality_chain.supports_quality_context() is True

    def test_falls_back_on_error(self):
        """Chain falls back when provider raises error."""
        mock_provider1 = MagicMock()
        mock_provider1.name = "mock1"
        mock_provider1.is_available.return_value = True
        mock_provider1.analyze_completion.side_effect = RuntimeError("API error")

        mock_provider2 = MagicMock()
        mock_provider2.name = "mock2"
        mock_provider2.is_available.return_value = True
        mock_provider2.analyze_completion.return_value = CompletionAnalysis(
            completed_tasks=[],
            in_progress_tasks=[],
            blocked_tasks=[],
            confidence=0.5,
            reasoning="fallback",
            provider_used="mock2",
        )

        chain = FallbackChainProvider([mock_provider1, mock_provider2])
        result = chain.analyze_completion("output", ["task1"])

        assert result.provider_used == "mock2"

    def test_raises_when_all_fail(self):
        """Chain raises error when all providers fail."""
        mock_provider = MagicMock()
        mock_provider.name = "mock"
        mock_provider.is_available.return_value = True
        mock_provider.analyze_completion.side_effect = RuntimeError("Failed")

        chain = FallbackChainProvider([mock_provider])

        with pytest.raises(RuntimeError, match="All providers failed"):
            chain.analyze_completion("output", ["task1"])

    def test_confidence_capped_for_short_analysis_text(self):
        """Confidence is capped when quality context flags short analysis text."""

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

        quality_context = SessionQualityContext(
            has_agent_messages=False,
            has_work_evidence=True,
            file_change_count=1,
            successful_command_count=0,
            estimated_effort_score=5,
            data_quality="high",
            analysis_text_length=50,
        )

        chain = FallbackChainProvider([QualityAwareProvider()])
        result = chain.analyze_completion(
            "output",
            ["task1"],
            quality_context=quality_context,
        )

        assert result.confidence <= 0.4
        assert result.confidence_adjusted is True

    def test_confidence_capped_after_fallback(self):
        """Confidence capping still applies when falling back to a later provider."""

        failing_provider = MagicMock()
        failing_provider.name = "failing"
        failing_provider.is_available.return_value = True
        failing_provider.analyze_completion.side_effect = RuntimeError("provider down")

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

        quality_context = SessionQualityContext(
            has_agent_messages=False,
            has_work_evidence=True,
            file_change_count=3,
            successful_command_count=1,
            estimated_effort_score=8,
            data_quality="high",
            analysis_text_length=40,
        )

        chain = FallbackChainProvider([failing_provider, QualityAwareProvider()])
        result = chain.analyze_completion(
            "output",
            ["task1"],
            quality_context=quality_context,
        )

        assert result.confidence <= 0.4
        assert result.confidence_adjusted is True


class TestGetLLMProvider:
    """Test get_llm_provider factory."""

    def test_returns_fallback_chain(self):
        """get_llm_provider returns a FallbackChainProvider."""
        provider = get_llm_provider()
        assert isinstance(provider, FallbackChainProvider)

    def test_chain_always_available(self):
        """Chain is always available (regex fallback)."""
        provider = get_llm_provider()
        assert provider.is_available() is True


class TestCompletionAnalysis:
    """Test CompletionAnalysis dataclass."""

    def test_dataclass_creation(self):
        """CompletionAnalysis can be created."""
        analysis = CompletionAnalysis(
            completed_tasks=["task1", "task2"],
            in_progress_tasks=["task3"],
            blocked_tasks=[],
            confidence=0.85,
            reasoning="Tasks 1 and 2 were completed based on output.",
            provider_used="test",
        )
        assert len(analysis.completed_tasks) == 2
        assert analysis.confidence == 0.85


class TestGitHubModelsProvider:
    """Test GitHub Models provider (mocked)."""

    def test_parse_response_valid_json(self):
        """Parses valid JSON response."""
        provider = GitHubModelsProvider()
        response = """
Here's my analysis:
{
    "completed": ["task1"],
    "in_progress": ["task2"],
    "blocked": [],
    "confidence": 0.9,
    "reasoning": "Task 1 was explicitly marked done."
}
"""
        result = provider._parse_response(response, ["task1", "task2"])
        assert result.completed_tasks == ["task1"]
        assert result.in_progress_tasks == ["task2"]
        assert result.confidence == 0.9

    def test_parse_response_invalid_json(self):
        """Handles invalid JSON gracefully."""
        provider = GitHubModelsProvider()
        response = "I couldn't analyze this properly."

        result = provider._parse_response(response, ["task1"])
        assert result.completed_tasks == []
        assert result.confidence == 0.0
        assert "parse" in result.reasoning.lower()
