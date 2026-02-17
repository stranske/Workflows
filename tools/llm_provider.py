"""
LLM Provider Abstraction with Fallback Chain

Provides a unified interface for LLM calls with automatic fallback:
1. OpenAI API (primary) - uses OPENAI_API_KEY
2. Anthropic API (secondary) - uses CLAUDE_API_STRANSKE
3. GitHub Models API (fallback) - uses GITHUB_TOKEN
4. Regex patterns (last resort) - no API calls

Usage:
    from tools.llm_provider import get_llm_provider, LLMProvider

    provider = get_llm_provider()
    result = provider.analyze_completion(session_text, tasks)

LangSmith Tracing:
    Set these environment variables to enable LangSmith tracing:
    - LANGSMITH_API_KEY: Your LangSmith API key
    - LANGCHAIN_TRACING_V2: Set to "true" to enable tracing
    - LANGCHAIN_PROJECT: Project name (default: "workflows-agents")
"""

from __future__ import annotations

import inspect
import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# GitHub Models API endpoint (OpenAI-compatible)
GITHUB_MODELS_BASE_URL = "https://models.inference.ai.azure.com"
# Legacy/default model identifier:
# - Not used for issuing requests to primary providers (OpenAI/Anthropic/GitHub Models)
# - Still used internally (e.g., default slot model in langchain_client.py)
# - Kept for backward compatibility with external code that references it
DEFAULT_MODEL = "codex-mini-latest"
ANTHROPIC_API_KEY_ENV = "CLAUDE_API_STRANSKE"
SHORT_ANALYSIS_CONFIDENCE_CAP = 0.4


def _setup_langsmith_tracing() -> bool:
    """
    Configure LangSmith tracing if API key is available.

    Returns True if tracing is enabled, False otherwise.
    """
    api_key = os.environ.get("LANGSMITH_API_KEY")
    if not api_key:
        return False

    # Enable LangChain tracing v2
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ.setdefault("LANGCHAIN_PROJECT", "workflows-agents")
    # LangSmith uses LANGSMITH_API_KEY directly, but LangChain expects LANGCHAIN_API_KEY
    os.environ.setdefault("LANGCHAIN_API_KEY", api_key)
    os.environ.setdefault("LANGSMITH_API_KEY", api_key)

    project = os.environ.get("LANGCHAIN_PROJECT")
    logger.info(f"LangSmith tracing enabled for project: {project}")
    return True


# Initialize tracing on module load.
# This flag can be used to conditionally enable LangSmith-specific features.
LANGSMITH_ENABLED = _setup_langsmith_tracing()

LANGSMITH_TRACE_URL_BASE = "https://smith.langchain.com/r/"


def build_langsmith_metadata(
    *,
    operation: str,
    repo: str | None = None,
    run_id: str | None = None,
    issue_or_pr_number: str | None = None,
    pr_number: int | None = None,
    issue_number: int | None = None,
) -> dict[str, object]:
    """Build a standardized LangSmith metadata and tags config dict.

    Returns a dict with ``metadata`` and ``tags`` keys suitable for passing
    as ``config=`` to a LangChain ``client.invoke()`` call.  When
    ``LANGSMITH_API_KEY`` is set the metadata also includes a
    ``langsmith_project`` field so traces are grouped correctly.

    The returned dict always includes ``metadata`` and ``tags`` keys. When
    LangSmith tracing is enabled, ``metadata`` gains an additional
    ``langsmith_project`` entry so traces group correctly.
    """
    repo = repo or os.environ.get("GITHUB_REPOSITORY", "unknown")
    run_id = run_id or os.environ.get("GITHUB_RUN_ID") or os.environ.get("RUN_ID") or "unknown"

    if issue_or_pr_number is None:
        if pr_number is not None:
            issue_or_pr_number = str(pr_number)
        elif issue_number is not None:
            issue_or_pr_number = str(issue_number)
        else:
            env_pr = os.environ.get("PR_NUMBER", "")
            env_issue = os.environ.get("ISSUE_NUMBER", "")
            issue_or_pr_number = (
                env_pr if env_pr.isdigit() else env_issue if env_issue.isdigit() else "unknown"
            )

    metadata: dict[str, object] = {
        "repo": repo,
        "run_id": run_id,
        "issue_or_pr_number": issue_or_pr_number,
        "operation": operation,
        "pr_number": str(pr_number) if pr_number is not None else None,
        "issue_number": str(issue_number) if issue_number is not None else None,
    }

    if LANGSMITH_ENABLED:
        metadata["langsmith_project"] = os.environ.get("LANGCHAIN_PROJECT", "workflows-agents")

    tags = [
        "workflows-agents",
        f"operation:{operation}",
        f"repo:{repo}",
        f"issue_or_pr:{issue_or_pr_number}",
        f"run_id:{run_id}",
    ]

    return {"metadata": metadata, "tags": tags}


def derive_langsmith_trace_url(trace_id: str | None) -> str | None:
    """Derive a clickable LangSmith trace URL from a trace ID.

    Returns ``None`` when *trace_id* is falsy.
    """
    if not trace_id:
        return None
    return f"{LANGSMITH_TRACE_URL_BASE}{trace_id}"


def extract_trace_id(response) -> str | None:
    """Extract LangSmith trace ID from a LangChain response object.

    Works with responses from ChatOpenAI, ChatAnthropic, and other LangChain clients.
    Returns None if no trace ID is available or LangSmith tracing is disabled.

    Args:
        response: LangChain response object (e.g., AIMessage from client.invoke())

    Returns:
        Trace ID string or None
    """
    if not LANGSMITH_ENABLED:
        return None

    # LangChain response objects have a response_metadata dict with run_id
    # The run_id is the trace ID in LangSmith
    try:
        # Try to get run_id from response metadata (primary method)
        if hasattr(response, "response_metadata"):
            metadata = response.response_metadata
            if isinstance(metadata, dict) and "run_id" in metadata:
                return str(metadata["run_id"])

        # Fallback: Some LangChain providers may use id attribute directly
        # WARNING: This may not always correspond to the LangSmith trace ID
        if hasattr(response, "id"):
            trace_id = str(response.id)
            logger.debug(
                "Using response.id as trace ID (fallback). "
                "Verify this corresponds to LangSmith trace for your provider."
            )
            return trace_id

        # Additional fallback for compatibility
        if hasattr(response, "__dict__"):
            response_dict = response.__dict__
            if "id" in response_dict:
                trace_id = str(response_dict["id"])
                logger.debug(
                    "Using response.__dict__['id'] as trace ID (fallback). "
                    "Verify this corresponds to LangSmith trace for your provider."
                )
                return trace_id

    except Exception as e:
        logger.debug(f"Failed to extract trace ID from response: {e}")
        return None

    return None


def _is_token_limit_error(error: Exception) -> bool:
    """Check if error is a token limit (413) error from GitHub Models."""
    error_str = str(error).lower()
    # Check for 413 status code (both with and without colon separators)
    has_413 = "413" in error_str and ("error code" in error_str or "status code" in error_str)
    has_token_message = "tokens_limit_reached" in error_str or "request body too large" in error_str
    return has_413 and has_token_message


@dataclass
class CompletionAnalysis:
    """Result of task completion analysis."""

    completed_tasks: list[str]  # Task descriptions marked complete
    in_progress_tasks: list[str]  # Tasks currently being worked on
    blocked_tasks: list[str]  # Tasks that are blocked
    confidence: float  # 0.0 to 1.0
    reasoning: str  # Explanation of the analysis
    provider_used: str  # Which provider generated this
    model_name: str = "unknown"  # Specific model used (e.g., gpt-4o, claude-3.5-sonnet)

    # Quality metrics for BS detection
    raw_confidence: float | None = None  # Original confidence before adjustment
    confidence_adjusted: bool = False  # Whether confidence was adjusted
    quality_warnings: list[str] | None = None  # Warnings about analysis quality


@dataclass
class SessionQualityContext:
    """Context about session quality for validating LLM responses."""

    has_agent_messages: bool = False
    has_work_evidence: bool = False
    file_change_count: int = 0
    successful_command_count: int = 0
    estimated_effort_score: int = 0
    data_quality: str = "unknown"  # high, medium, low, minimal
    analysis_text_length: int = 0


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
        quality_context: SessionQualityContext | None = None,
    ) -> CompletionAnalysis:
        """
        Analyze session output to determine task completion status.

        Args:
            session_output: Codex session output (summary or JSONL events)
            tasks: List of task descriptions from PR checkboxes
            context: Optional additional context (PR description, etc.)
            quality_context: Optional session quality context for confidence checks

        Returns:
            CompletionAnalysis with task status breakdown
        """
        pass

    def supports_quality_context(self) -> bool:
        """Return True if analyze_completion accepts a quality_context parameter."""
        try:
            parameters = inspect.signature(self.analyze_completion).parameters
        except (TypeError, ValueError):
            return False
        return "quality_context" in parameters or any(
            param.kind == inspect.Parameter.VAR_KEYWORD for param in parameters.values()
        )


def _supports_quality_context(provider: LLMProvider) -> bool:
    supports = getattr(provider, "supports_quality_context", None)
    if callable(supports):
        try:
            return bool(supports())
        except Exception:
            logger.debug(
                "supports_quality_context raised for %s, falling back to signature",
                getattr(provider, "name", provider.__class__.__name__),
            )
    if supports is not None:
        return bool(supports)
    try:
        parameters = inspect.signature(provider.analyze_completion).parameters
    except (TypeError, ValueError):
        return False
    return "quality_context" in parameters or any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in parameters.values()
    )


def supports_quality_context(provider: LLMProvider) -> bool:
    """Return True if provider supports a quality_context parameter."""
    return _supports_quality_context(provider)


class GitHubModelsProvider(LLMProvider):
    """LLM provider using GitHub Models API (OpenAI-compatible)."""

    @property
    def name(self) -> str:
        return "github-models"

    def is_available(self) -> bool:
        return bool(os.environ.get("GITHUB_TOKEN"))

    def supports_quality_context(self) -> bool:
        return True

    def _get_client(self):
        """Get LangChain ChatOpenAI client configured for GitHub Models."""
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            logger.warning("langchain_openai not installed")
            return None

        return ChatOpenAI(
            model="gpt-4.1",  # Battle-tested, reliable, available on GitHub Models
            base_url=GITHUB_MODELS_BASE_URL,
            api_key=os.environ.get("GITHUB_TOKEN"),
            temperature=0.1,  # Low temperature for consistent analysis
        )

    def analyze_completion(
        self,
        session_output: str,
        tasks: list[str],
        context: str | None = None,
        quality_context: SessionQualityContext | None = None,
    ) -> CompletionAnalysis:
        client = self._get_client()
        if not client:
            raise RuntimeError("LangChain OpenAI not available")

        prompt = self._build_analysis_prompt(session_output, tasks, context)

        try:
            response = client.invoke(prompt)
            return self._parse_response(response.content, tasks, quality_context)
        except Exception as e:
            logger.error(f"GitHub Models API error: {e}")
            raise

    def _validate_confidence(
        self,
        raw_confidence: float,
        completed_count: int,
        in_progress_count: int,
        quality_context: SessionQualityContext | None,
        reasoning: str,
    ) -> tuple[float, list[str]]:
        """
        BS Detector: Validate and potentially adjust LLM confidence.

        This catches cases where the LLM reports high confidence but the
        analysis is inconsistent with the session evidence.

        Args:
            raw_confidence: The confidence reported by the LLM
            completed_count: Number of tasks marked as completed
            in_progress_count: Number of tasks marked as in progress
            quality_context: Session quality metrics (if available)
            reasoning: The LLM's reasoning text

        Returns:
            Tuple of (adjusted_confidence, list of warnings)
        """
        warnings = []
        confidence = raw_confidence

        # Sanity check: Confidence should be between 0 and 1
        confidence = max(0.0, min(1.0, confidence))

        if quality_context is None:
            # No context available, trust LLM but note it
            return confidence, []

        # BS Detection Rule 1: High confidence + zero work + evidence of work = suspicious
        if (
            raw_confidence > 0.7
            and completed_count == 0
            and in_progress_count == 0
            and quality_context.has_work_evidence
        ):
            warnings.append(
                f"High confidence ({raw_confidence:.0%}) but no tasks detected "
                f"despite {quality_context.file_change_count} file changes and "
                f"{quality_context.successful_command_count} successful commands"
            )
            # Reduce confidence significantly - the LLM might have had insufficient data
            confidence = min(confidence, 0.3)
            logger.warning(f"BS detected: {warnings[-1]}")

        # BS Detection Rule 2: Very short analysis text = likely data loss
        if quality_context.analysis_text_length < 200:
            warnings.append(
                f"Analysis text suspiciously short "
                f"({quality_context.analysis_text_length} chars) - "
                "possible data loss in pipeline"
            )
            # Short text means limited evidence - cap confidence
            confidence = min(confidence, SHORT_ANALYSIS_CONFIDENCE_CAP)
            logger.warning(f"Short analysis text: {quality_context.analysis_text_length} chars")

        # BS Detection Rule 3: Zero tasks + high effort score = something's wrong
        if (
            quality_context.estimated_effort_score > 30
            and completed_count == 0
            and in_progress_count == 0
        ):
            warnings.append(
                f"Effort score ({quality_context.estimated_effort_score}) suggests work was done "
                "but no tasks detected"
            )
            confidence = min(confidence, 0.4)

        # BS Detection Rule 4: Reasoning mentions "no evidence" but there's evidence
        no_evidence_phrases = ["no evidence", "no work", "nothing done", "no specific"]
        reasoning_lower = reasoning.lower()
        if (
            any(phrase in reasoning_lower for phrase in no_evidence_phrases)
            and quality_context.has_work_evidence
        ):
            warnings.append("LLM claims 'no evidence' but session has file changes/commands")
            confidence = min(confidence, 0.35)

        # BS Detection Rule 5: Data quality impacts confidence ceiling
        quality_caps = {
            "high": 1.0,
            "medium": 0.8,
            "low": 0.6,
            "minimal": 0.4,
        }
        quality_cap = quality_caps.get(quality_context.data_quality, 0.5)
        if confidence > quality_cap:
            warnings.append(
                f"Confidence capped from {raw_confidence:.0%} to {quality_cap:.0%} "
                f"due to {quality_context.data_quality} data quality"
            )
            confidence = quality_cap

        return confidence, warnings

    def _build_analysis_prompt(
        self,
        session_output: str,
        tasks: list[str],
        _context: str | None = None,
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

IMPORTANT: Base your analysis on CONCRETE EVIDENCE such as:
- File modifications (files being created/edited)
- Successful test runs
- Command outputs showing completed work
- Direct statements of completion

If the session output is very short or lacks detail, lower your confidence accordingly.

Respond in JSON format:
{{
    "completed": ["task description 1", ...],
    "in_progress": ["task description 2", ...],
    "blocked": ["task description 3", ...],
    "confidence": 0.85,
    "reasoning": "Brief explanation of your analysis with specific evidence cited"
}}

Only include tasks in completed/in_progress/blocked if you have evidence.
Be conservative - if unsure, don't mark as completed."""

    def _parse_response(
        self,
        content: str | list,
        _tasks: list[str],
        quality_context: SessionQualityContext | None = None,
    ) -> CompletionAnalysis:
        """Parse LLM response into CompletionAnalysis with BS detection."""
        # Normalize content: Anthropic can return a list of content blocks
        if isinstance(content, list):
            content = "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            )
        try:
            # Try to extract JSON from response
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(content[json_start:json_end])
            else:
                raise ValueError("No JSON found in response")

            raw_confidence = float(data.get("confidence", 0.5))
            completed = data.get("completed", [])
            in_progress = data.get("in_progress", [])
            reasoning = data.get("reasoning", "")

            # Apply BS detection to validate/adjust confidence
            adjusted_confidence, warnings = self._validate_confidence(
                raw_confidence=raw_confidence,
                completed_count=len(completed),
                in_progress_count=len(in_progress),
                quality_context=quality_context,
                reasoning=reasoning,
            )

            return CompletionAnalysis(
                completed_tasks=completed,
                in_progress_tasks=in_progress,
                blocked_tasks=data.get("blocked", []),
                confidence=adjusted_confidence,
                reasoning=reasoning,
                provider_used=self.name,
                model_name="gpt-4.1",  # Actual model used by GitHubModelsProvider
                raw_confidence=raw_confidence if adjusted_confidence != raw_confidence else None,
                confidence_adjusted=adjusted_confidence != raw_confidence,
                quality_warnings=warnings if warnings else None,
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
                model_name="gpt-4.1",  # Actual model used by GitHubModelsProvider
            )


class OpenAIProvider(LLMProvider):
    """LLM provider using OpenAI API directly."""

    @property
    def name(self) -> str:
        return "openai"

    def is_available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def supports_quality_context(self) -> bool:
        return True

    def _get_client(self):
        """Get LangChain ChatOpenAI client."""
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            logger.warning("langchain_openai not installed")
            return None

        return ChatOpenAI(
            model="gpt-5.1-codex",  # Purpose-built for analyzing Codex coding sessions
            api_key=os.environ.get("OPENAI_API_KEY"),
            temperature=0.1,
        )

    def analyze_completion(
        self,
        session_output: str,
        tasks: list[str],
        context: str | None = None,
        quality_context: SessionQualityContext | None = None,
    ) -> CompletionAnalysis:
        client = self._get_client()
        if not client:
            raise RuntimeError("LangChain OpenAI not available")

        # Reuse the same prompt building logic
        github_provider = GitHubModelsProvider()
        prompt = github_provider._build_analysis_prompt(session_output, tasks, context)

        try:
            response = client.invoke(prompt)
            result = github_provider._parse_response(
                response.content,
                tasks,
                quality_context=quality_context,
            )
            # Override provider name
            return CompletionAnalysis(
                completed_tasks=result.completed_tasks,
                in_progress_tasks=result.in_progress_tasks,
                blocked_tasks=result.blocked_tasks,
                confidence=result.confidence,
                reasoning=result.reasoning,
                provider_used=self.name,
                model_name="gpt-5.1-codex",  # Actual model used by OpenAIProvider
                raw_confidence=result.raw_confidence,
                confidence_adjusted=result.confidence_adjusted,
                quality_warnings=result.quality_warnings,
            )
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise


class AnthropicProvider(LLMProvider):
    """LLM provider using Anthropic API directly."""

    @property
    def name(self) -> str:
        return "anthropic"

    def is_available(self) -> bool:
        return bool(os.environ.get(ANTHROPIC_API_KEY_ENV))

    def supports_quality_context(self) -> bool:
        return True

    def _get_client(self):
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            logger.warning("langchain_anthropic not installed")
            return None

        return ChatAnthropic(
            model="claude-sonnet-4-5-20250929",
            anthropic_api_key=os.environ.get(ANTHROPIC_API_KEY_ENV),
            temperature=0.1,
        )

    def analyze_completion(
        self,
        session_output: str,
        tasks: list[str],
        context: str | None = None,
        quality_context: SessionQualityContext | None = None,
    ) -> CompletionAnalysis:
        client = self._get_client()
        if not client:
            raise RuntimeError("LangChain Anthropic not available")

        github_provider = GitHubModelsProvider()
        prompt = github_provider._build_analysis_prompt(session_output, tasks, context)

        try:
            if quality_context is None:
                response = client.invoke(prompt)
            else:
                try:
                    response = client.invoke(prompt, quality_context=quality_context)
                except TypeError as exc:
                    message = str(exc)
                    if "quality_context" not in message:
                        raise
                    logger.debug(
                        "Anthropic client invoke rejected quality_context, retrying without it"
                    )
                    response = client.invoke(prompt)
            result = github_provider._parse_response(
                response.content,
                tasks,
                quality_context=quality_context,
            )
            return CompletionAnalysis(
                completed_tasks=result.completed_tasks,
                in_progress_tasks=result.in_progress_tasks,
                blocked_tasks=result.blocked_tasks,
                confidence=result.confidence,
                reasoning=result.reasoning,
                provider_used=self.name,
                model_name="claude-sonnet-4-5-20250929",
                raw_confidence=result.raw_confidence,
                confidence_adjusted=result.confidence_adjusted,
                quality_warnings=result.quality_warnings,
            )
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
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

    def supports_quality_context(self) -> bool:
        return False

    def analyze_completion(
        self,
        session_output: str,
        tasks: list[str],
        context: str | None = None,
        quality_context: SessionQualityContext | None = None,
    ) -> CompletionAnalysis:
        _ = context
        _ = quality_context
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
            model_name="regex-patterns",
            reasoning="Pattern-based analysis (no LLM available)",
            provider_used=self.name,
        )


class FallbackChainProvider(LLMProvider):
    """Provider that tries multiple providers in sequence."""

    def __init__(self, providers: list[LLMProvider]):
        self._providers = providers
        self._active_provider: LLMProvider | None = None

    def supports_quality_context(self) -> bool:
        """Return True if any underlying provider supports quality_context."""
        return any(self._provider_supports_quality_context(p) for p in self._providers)

    def quality_context_capable_providers(self) -> list[str]:
        """List provider names in the chain that support quality_context."""
        return [
            provider.name
            for provider in self._providers
            if self._provider_supports_quality_context(provider)
        ]

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
        quality_context: SessionQualityContext | None = None,
    ) -> CompletionAnalysis:
        last_error = None
        providers = self._providers

        if quality_context is not None:
            quality_aware, legacy = self._partition_providers_by_quality_context()
            if quality_aware:
                logger.debug(
                    "Quality context available; preferring providers: %s",
                    [provider.name for provider in quality_aware],
                )
            providers = quality_aware + legacy

        for provider in providers:
            if not provider.is_available():
                logger.debug(f"Provider {provider.name} not available, skipping")
                continue

            try:
                logger.info(f"Attempting analysis with {provider.name}")
                self._active_provider = provider
                result = self._analyze_with_provider(
                    provider,
                    session_output=session_output,
                    tasks=tasks,
                    context=context,
                    quality_context=quality_context,
                )
                logger.info(f"Successfully analyzed with {provider.name}")
                return result
            except Exception as e:
                logger.warning(f"Provider {provider.name} failed: {e}")
                last_error = e
                continue

        if last_error:
            raise RuntimeError(f"All providers failed. Last error: {last_error}")
        raise RuntimeError("No providers available")

    @staticmethod
    def _provider_supports_quality_context(provider: LLMProvider) -> bool:
        return _supports_quality_context(provider)

    def _partition_providers_by_quality_context(
        self,
    ) -> tuple[list[LLMProvider], list[LLMProvider]]:
        quality_aware: list[LLMProvider] = []
        legacy: list[LLMProvider] = []
        for provider in self._providers:
            if self._provider_supports_quality_context(provider):
                quality_aware.append(provider)
            else:
                legacy.append(provider)
        return quality_aware, legacy

    def _analyze_with_provider(
        self,
        provider: LLMProvider,
        *,
        session_output: str,
        tasks: list[str],
        context: str | None,
        quality_context: SessionQualityContext | None,
    ) -> CompletionAnalysis:
        if quality_context is not None and self._provider_supports_quality_context(provider):
            try:
                return provider.analyze_completion(
                    session_output=session_output,
                    tasks=tasks,
                    context=context,
                    quality_context=quality_context,
                )
            except TypeError as exc:
                if not self._is_quality_context_type_error(exc):
                    raise
                logger.debug(
                    "Provider %s rejected quality_context, retrying without it",
                    provider.name,
                )

        return provider.analyze_completion(
            session_output=session_output,
            tasks=tasks,
            context=context,
        )

    @staticmethod
    def _is_quality_context_type_error(error: TypeError) -> bool:
        message = str(error)
        if "quality_context" not in message:
            return False
        if "unexpected keyword argument" in message:
            return True
        return "got multiple values for argument" in message


def get_llm_provider(force_provider: str | None = None) -> LLMProvider:
    """
    Get the best available LLM provider with fallback chain.

    Args:
        force_provider: If set, use only this provider (for testing).
            Options: "github-models", "openai", "anthropic", "regex-fallback"

    Returns a FallbackChainProvider that tries:
    1. Anthropic claude-sonnet-4-5 (if CLAUDE_API_STRANSKE set) - Best reasoning
    2. OpenAI gpt-5.1-codex (if OPENAI_API_KEY set) - Purpose-built for code analysis
    3. GitHub Models gpt-4.1 (if GITHUB_TOKEN set) - Always available, reliable
    4. Regex fallback (always available) - 30% confidence baseline
    """
    # Force a specific provider for testing
    if force_provider:
        provider_map: dict[str, type[LLMProvider]] = {
            "github-models": GitHubModelsProvider,
            "openai": OpenAIProvider,
            "anthropic": AnthropicProvider,
            "regex-fallback": RegexFallbackProvider,
        }
        if force_provider not in provider_map:
            raise ValueError(
                f"Unknown provider: {force_provider}. Options: {list(provider_map.keys())}"
            )
        provider_class = provider_map[force_provider]
        provider = provider_class()
        if not provider.is_available():
            raise RuntimeError(
                f"Forced provider '{force_provider}' is not available. "
                "Check required environment variables."
            )
        logger.info(f"Using forced provider: {force_provider}")
        return provider

    providers = [
        AnthropicProvider(),  # Primary: claude-sonnet-4-5 for best reasoning
        OpenAIProvider(),  # Secondary: gpt-5.1-codex for code-optimized analysis
        GitHubModelsProvider(),  # Tertiary: gpt-4.1 via GITHUB_TOKEN (always available)
        RegexFallbackProvider(),  # Last resort: 30% confidence pattern matching
    ]

    return FallbackChainProvider(providers)


def check_providers() -> dict[str, bool]:
    """Check which providers are available."""
    return {
        "github-models": GitHubModelsProvider().is_available(),
        "openai": OpenAIProvider().is_available(),
        "anthropic": AnthropicProvider().is_available(),
        "regex-fallback": True,
    }


def get_quality_context_support_table() -> dict[str, bool]:
    """Return provider -> quality_context support map for built-in providers."""
    providers = [
        OpenAIProvider(),
        AnthropicProvider(),
        GitHubModelsProvider(),
        RegexFallbackProvider(),
    ]
    return {provider.name: _supports_quality_context(provider) for provider in providers}


def get_quality_context_capable_providers() -> list[str]:
    """List providers that support quality_context."""
    support_table = get_quality_context_support_table()
    return [name for name, supported in support_table.items() if supported]


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
