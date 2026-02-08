"""Tests for FallbackChainProvider quality_context wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

from tools.llm_provider import (
    CompletionAnalysis,
    FallbackChainProvider,
    LLMProvider,
)


class StubProvider(LLMProvider):
    @property
    def name(self) -> str:
        return "stub-provider"

    def is_available(self) -> bool:
        return True

    def analyze_completion(
        self,
        session_output: str,
        tasks: list[str],
        context: str | None = None,
        quality_context: object | None = None,
    ) -> CompletionAnalysis:
        _ = session_output
        _ = tasks
        _ = context
        _ = quality_context
        return CompletionAnalysis(
            completed_tasks=[],
            in_progress_tasks=[],
            blocked_tasks=[],
            confidence=0.9,
            reasoning="stub",
            provider_used=self.name,
        )


def test_fallback_chain_forwards_quality_context_to_active_provider():
    sentinel = object()
    provider = StubProvider()
    provider.analyze_completion = MagicMock(wraps=provider.analyze_completion)

    chain = FallbackChainProvider([provider])
    chain.analyze_completion("session", ["task"], quality_context=sentinel)

    provider.analyze_completion.assert_called_once()
    call_args = provider.analyze_completion.call_args
    assert call_args.args == ()
    call_kwargs = call_args.kwargs
    assert call_kwargs["session_output"] == "session"
    assert call_kwargs["tasks"] == ["task"]
    assert call_kwargs["quality_context"] is sentinel
    assert sentinel not in call_args.args


class LegacyProvider(LLMProvider):
    @property
    def name(self) -> str:
        return "legacy-provider"

    def is_available(self) -> bool:
        return False

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
            confidence=0.1,
            reasoning="legacy",
            provider_used=self.name,
        )


class QualityProvider(LLMProvider):
    @property
    def name(self) -> str:
        return "quality-provider"

    def is_available(self) -> bool:
        return True

    def analyze_completion(
        self,
        session_output: str,
        tasks: list[str],
        context: str | None = None,
        quality_context: object | None = None,
    ) -> CompletionAnalysis:
        _ = session_output
        _ = tasks
        _ = context
        _ = quality_context
        return CompletionAnalysis(
            completed_tasks=[],
            in_progress_tasks=[],
            blocked_tasks=[],
            confidence=0.8,
            reasoning="quality",
            provider_used=self.name,
        )


def test_fallback_chain_selects_expected_active_provider_and_forwards_args():
    sentinel = object()
    legacy_provider = LegacyProvider()
    quality_provider = QualityProvider()
    legacy_provider.analyze_completion = MagicMock(wraps=legacy_provider.analyze_completion)
    quality_provider.analyze_completion = MagicMock(wraps=quality_provider.analyze_completion)

    chain = FallbackChainProvider([legacy_provider, quality_provider])
    chain.analyze_completion("session", ["task"], "ctx", quality_context=sentinel)

    assert chain._active_provider is quality_provider
    assert legacy_provider.analyze_completion.call_count == 0
    quality_provider.analyze_completion.assert_called_once()
    call_args = quality_provider.analyze_completion.call_args
    assert call_args.args == ()
    call_kwargs = call_args.kwargs
    assert call_kwargs["session_output"] == "session"
    assert call_kwargs["tasks"] == ["task"]
    assert call_kwargs["context"] == "ctx"
    assert call_kwargs["quality_context"] is sentinel
    assert sentinel not in call_args.args
