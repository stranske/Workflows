"""Tests for tools/llm_provider.py"""

import os
from unittest.mock import MagicMock, patch

import pytest

from tools.llm_provider import (
    CompletionAnalysis,
    FallbackChainProvider,
    GitHubModelsProvider,
    OpenAIProvider,
    RegexFallbackProvider,
    check_providers,
    get_llm_provider,
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
