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
    assert provider.analyze_completion.call_args.kwargs["quality_context"] is sentinel
