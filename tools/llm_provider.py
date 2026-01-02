"""
LLM Provider Abstraction with Fallback Chain

Provides a unified interface for LLM calls with automatic fallback:
1. GitHub Models API (primary) - uses GITHUB_TOKEN
2. OpenAI API (fallback) - uses OPENAI_API_KEY
3. Regex patterns (last resort) - no API calls

Usage:
    from tools.llm_provider import get_llm_provider, LLMProvider

    provider = get_llm_provider()
    result = provider.analyze_completion(session_text, tasks)
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# GitHub Models API endpoint (OpenAI-compatible)
GITHUB_MODELS_BASE_URL = "https://models.inference.ai.azure.com"
DEFAULT_MODEL = "gpt-4o-mini"


@dataclass
class CompletionAnalysis:
    """Result of task completion analysis."""

    completed_tasks: list[str]  # Task descriptions marked complete
    in_progress_tasks: list[str]  # Tasks currently being worked on
    blocked_tasks: list[str]  # Tasks that are blocked
    confidence: float  # 0.0 to 1.0
    reasoning: str  # Explanation of the analysis
    provider_used: str  # Which provider generated this


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider can be used."""
        pass

    @abstractmethod
    def analyze_completion(
        self,
        session_output: str,
        tasks: list[str],
        context: str | None = None,
    ) -> CompletionAnalysis:
        """
        Analyze session output to determine task completion status.

        Args:
            session_output: Codex session output (summary or JSONL events)
            tasks: List of task descriptions from PR checkboxes
            context: Optional additional context (PR description, etc.)

        Returns:
            CompletionAnalysis with task status breakdown
        """
        pass


class GitHubModelsProvider(LLMProvider):
    """LLM provider using GitHub Models API (OpenAI-compatible)."""

    @property
    def name(self) -> str:
        return "github-models"

    def is_available(self) -> bool:
        return bool(os.environ.get("GITHUB_TOKEN"))

    def _get_client(self):
        """Get LangChain ChatOpenAI client configured for GitHub Models."""
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            logger.warning("langchain_openai not installed")
            return None

        return ChatOpenAI(
            model=DEFAULT_MODEL,
            base_url=GITHUB_MODELS_BASE_URL,
            api_key=os.environ.get("GITHUB_TOKEN"),
            temperature=0.1,  # Low temperature for consistent analysis
        )

    def analyze_completion(
        self,
        session_output: str,
        tasks: list[str],
        context: str | None = None,
    ) -> CompletionAnalysis:
        client = self._get_client()
        if not client:
            raise RuntimeError("LangChain OpenAI not available")

        prompt = self._build_analysis_prompt(session_output, tasks, context)

        try:
            response = client.invoke(prompt)
            return self._parse_response(response.content, tasks)
        except Exception as e:
            logger.error(f"GitHub Models API error: {e}")
            raise

    def _build_analysis_prompt(
        self,
        session_output: str,
        tasks: list[str],
        context: str | None = None,
    ) -> str:
        task_list = "\n".join(f"- [ ] {task}" for task in tasks)

        return f"""Analyze this Codex session output and determine which tasks have been completed.

## Tasks to Track
{task_list}

## Session Output
{session_output[:8000]}  # Truncate to avoid token limits

## Instructions
For each task, determine if it was:
- COMPLETED: Clear evidence the task was finished
- IN_PROGRESS: Work started but not finished
- BLOCKED: Cannot proceed due to an issue
- NOT_STARTED: No evidence of work on this task

Respond in JSON format:
{{
    "completed": ["task description 1", ...],
    "in_progress": ["task description 2", ...],
    "blocked": ["task description 3", ...],
    "confidence": 0.85,
    "reasoning": "Brief explanation of your analysis"
}}

Only include tasks in completed/in_progress/blocked if you have evidence. Be conservative - if unsure, don't mark as completed."""

    def _parse_response(self, content: str, tasks: list[str]) -> CompletionAnalysis:
        """Parse LLM response into CompletionAnalysis."""
        try:
            # Try to extract JSON from response
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(content[json_start:json_end])
            else:
                raise ValueError("No JSON found in response")

            return CompletionAnalysis(
                completed_tasks=data.get("completed", []),
                in_progress_tasks=data.get("in_progress", []),
                blocked_tasks=data.get("blocked", []),
                confidence=float(data.get("confidence", 0.5)),
                reasoning=data.get("reasoning", ""),
                provider_used=self.name,
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            # Return empty analysis on parse failure
            return CompletionAnalysis(
                completed_tasks=[],
                in_progress_tasks=[],
                blocked_tasks=[],
                confidence=0.0,
                reasoning=f"Failed to parse response: {e}",
                provider_used=self.name,
            )


class OpenAIProvider(LLMProvider):
    """LLM provider using OpenAI API directly."""

    @property
    def name(self) -> str:
        return "openai"

    def is_available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def _get_client(self):
        """Get LangChain ChatOpenAI client."""
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            logger.warning("langchain_openai not installed")
            return None

        return ChatOpenAI(
            model=DEFAULT_MODEL,
            api_key=os.environ.get("OPENAI_API_KEY"),
            temperature=0.1,
        )

    def analyze_completion(
        self,
        session_output: str,
        tasks: list[str],
        context: str | None = None,
    ) -> CompletionAnalysis:
        client = self._get_client()
        if not client:
            raise RuntimeError("LangChain OpenAI not available")

        # Reuse the same prompt building logic
        github_provider = GitHubModelsProvider()
        prompt = github_provider._build_analysis_prompt(session_output, tasks, context)

        try:
            response = client.invoke(prompt)
            result = github_provider._parse_response(response.content, tasks)
            # Override provider name
            return CompletionAnalysis(
                completed_tasks=result.completed_tasks,
                in_progress_tasks=result.in_progress_tasks,
                blocked_tasks=result.blocked_tasks,
                confidence=result.confidence,
                reasoning=result.reasoning,
                provider_used=self.name,
            )
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise


class RegexFallbackProvider(LLMProvider):
    """Fallback provider using regex pattern matching (no API calls)."""

    # Patterns indicating task completion
    COMPLETION_PATTERNS = [
        r"(?:completed?|finished|done|implemented|fixed|resolved)\s+(?:the\s+)?(.+?)(?:\.|$)",
        r"✓\s+(.+?)(?:\.|$)",
        r"\[x\]\s+(.+?)(?:\.|$)",
        r"successfully\s+(?:completed?|implemented|fixed)\s+(.+?)(?:\.|$)",
    ]

    # Patterns indicating work in progress
    PROGRESS_PATTERNS = [
        r"(?:working on|started|beginning|implementing)\s+(.+?)(?:\.|$)",
        r"(?:in progress|ongoing):\s*(.+?)(?:\.|$)",
    ]

    # Patterns indicating blockers
    BLOCKER_PATTERNS = [
        r"(?:blocked|stuck|cannot|failed|error)\s+(?:on\s+)?(.+?)(?:\.|$)",
        r"(?:issue|problem|bug)\s+(?:with\s+)?(.+?)(?:\.|$)",
    ]

    @property
    def name(self) -> str:
        return "regex-fallback"

    def is_available(self) -> bool:
        return True  # Always available

    def analyze_completion(
        self,
        session_output: str,
        tasks: list[str],
        context: str | None = None,
    ) -> CompletionAnalysis:

        output_lower = session_output.lower()
        completed = []
        in_progress = []
        blocked = []

        for task in tasks:
            task_lower = task.lower()
            # Simple keyword matching
            task_words = set(task_lower.split())

            # Check for completion signals
            is_completed = any(
                word in output_lower
                and any(
                    p in output_lower
                    for p in ["completed", "finished", "done", "fixed", "✓", "[x]"]
                )
                for word in task_words
                if len(word) > 3
            )

            # Check for progress signals
            is_in_progress = any(
                word in output_lower
                and any(
                    p in output_lower
                    for p in ["working on", "started", "implementing", "in progress"]
                )
                for word in task_words
                if len(word) > 3
            )

            # Check for blocker signals
            is_blocked = any(
                word in output_lower
                and any(
                    p in output_lower for p in ["blocked", "stuck", "failed", "error", "cannot"]
                )
                for word in task_words
                if len(word) > 3
            )

            if is_completed:
                completed.append(task)
            elif is_blocked:
                blocked.append(task)
            elif is_in_progress:
                in_progress.append(task)

        return CompletionAnalysis(
            completed_tasks=completed,
            in_progress_tasks=in_progress,
            blocked_tasks=blocked,
            confidence=0.3,  # Low confidence for regex
            reasoning="Pattern-based analysis (no LLM available)",
            provider_used=self.name,
        )


class FallbackChainProvider(LLMProvider):
    """Provider that tries multiple providers in sequence."""

    def __init__(self, providers: list[LLMProvider]):
        self._providers = providers
        self._active_provider: LLMProvider | None = None

    @property
    def name(self) -> str:
        if self._active_provider:
            return f"fallback-chain({self._active_provider.name})"
        return "fallback-chain"

    def is_available(self) -> bool:
        return any(p.is_available() for p in self._providers)

    def analyze_completion(
        self,
        session_output: str,
        tasks: list[str],
        context: str | None = None,
    ) -> CompletionAnalysis:
        last_error = None

        for provider in self._providers:
            if not provider.is_available():
                logger.debug(f"Provider {provider.name} not available, skipping")
                continue

            try:
                logger.info(f"Attempting analysis with {provider.name}")
                self._active_provider = provider
                result = provider.analyze_completion(session_output, tasks, context)
                logger.info(f"Successfully analyzed with {provider.name}")
                return result
            except Exception as e:
                logger.warning(f"Provider {provider.name} failed: {e}")
                last_error = e
                continue

        if last_error:
            raise RuntimeError(f"All providers failed. Last error: {last_error}")
        raise RuntimeError("No providers available")


def get_llm_provider() -> LLMProvider:
    """
    Get the best available LLM provider with fallback chain.

    Returns a FallbackChainProvider that tries:
    1. GitHub Models API (if GITHUB_TOKEN set)
    2. OpenAI API (if OPENAI_API_KEY set)
    3. Regex fallback (always available)
    """
    providers = [
        GitHubModelsProvider(),
        OpenAIProvider(),
        RegexFallbackProvider(),
    ]

    return FallbackChainProvider(providers)


def check_providers() -> dict[str, bool]:
    """Check which providers are available."""
    return {
        "github-models": GitHubModelsProvider().is_available(),
        "openai": OpenAIProvider().is_available(),
        "regex-fallback": True,
    }


if __name__ == "__main__":
    import sys

    # Quick test - log to stderr
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)

    print("Provider availability:")
    for name, available in check_providers().items():
        status = "✓" if available else "✗"
        print(f"  {status} {name}")

    provider = get_llm_provider()
    print(f"\nActive provider chain: {provider.name}")
