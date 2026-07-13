# Model Selection Framework

> **Historical design only.** This document contains the original estimated
> score proposal and stale model examples. The authoritative, implemented policy
> is [`MODEL_SELECTION_POLICY.md`](MODEL_SELECTION_POLICY.md), which requires
> paired workload evidence and constrained selection rather than weighted scores.
> **Last updated**: February 7, 2026
> **Purpose**: Define a model registry, selection algorithm, and slot-system
> integration that enables task-aware, performance-driven model selection.

---

## Table of Contents

1. [Full Model Registry](#full-model-registry)
2. [Task Classification](#task-classification)
3. [Selection Algorithm](#selection-algorithm)
4. [Slot System Integration](#slot-system-integration)
5. [LangSmith Feedback Loop](#langsmith-feedback-loop)
6. [Implementation Plan](#implementation-plan)

---

## Full Model Registry

### LangChain API Names

These are the exact model ID strings to pass to `ChatOpenAI(model=...)` or
`ChatAnthropic(model=...)` via LangChain. Models are grouped by generation and
capability tier.

#### OpenAI Models (via `langchain_openai.ChatOpenAI`)

For GitHub Models provider, add `base_url="https://models.inference.ai.azure.com"`.
For direct OpenAI, no `base_url` is needed.

| Model ID | Generation | Tier | Reasoning | Context | API | Notes |
|----------|-----------|------|-----------|---------|-----|-------|
| `gpt-5.2` | 5.2 | Flagship | Configurable (default: medium) | 128K+ | Chat | Latest flagship (Dec 2025) |
| `gpt-5.2-2025-12-11` | 5.2 | Flagship | Configurable | 128K+ | Chat | Pinned version |
| `gpt-5.2-pro` | 5.2 | Pro | High only | 128K+ | Responses | Extended reasoning |
| `gpt-5.2-pro-2025-12-11` | 5.2 | Pro | High only | 128K+ | Responses | Pinned |
| `gpt-5.1` | 5.1 | Flagship | Configurable (default: **none**) | 128K+ | Chat | Must set effort explicitly |
| `gpt-5.1-2025-11-13` | 5.1 | Flagship | Configurable | 128K+ | Chat | Pinned |
| `gpt-5.1-codex` | 5.1 | Codex | Configurable | 128K+ | Chat | Code-optimized |
| `gpt-5.1-mini` | 5.1 | Mini | Configurable | 128K+ | Chat | Lightweight |
| `gpt-5.1-codex-max` | 5.1 | Codex-Max | Up to xhigh | 128K+ | Responses | Max reasoning, Responses API only |
| `gpt-5` | 5.0 | Flagship | Configurable (default: medium) | 128K+ | Chat | Aug 2025 |
| `gpt-5-2025-08-07` | 5.0 | Flagship | Configurable | 128K+ | Chat | Pinned |
| `gpt-5-codex` | 5.0 | Codex | Configurable | 128K+ | Responses | Responses API only |
| `gpt-5-mini` | 5.0 | Mini | Configurable | 128K+ | Chat | Lightweight |
| `gpt-5-mini-2025-08-07` | 5.0 | Mini | Configurable | 128K+ | Chat | Pinned |
| `gpt-5-nano` | 5.0 | Nano | Light | 128K+ | Chat | Smallest GPT-5 |
| `gpt-5-nano-2025-08-07` | 5.0 | Nano | Light | 128K+ | Chat | Pinned |
| `gpt-5-pro` | 5.0 | Pro | High only | 128K+ | Responses | Responses API only |
| `gpt-4.1` | 4.1 | Flagship | Standard | 128K+ | Chat | Battle-tested (Apr 2025) |
| `gpt-4.1-2025-04-14` | 4.1 | Flagship | Standard | 128K+ | Chat | Pinned |
| `gpt-4.1-mini` | 4.1 | Mini | Standard | 128K+ | Chat | Lightweight |
| `gpt-4.1-mini-2025-04-14` | 4.1 | Mini | Standard | 128K+ | Chat | Pinned |
| `gpt-4.1-nano` | 4.1 | Nano | Light | 128K+ | Chat | Smallest 4.1 |
| `gpt-4.1-nano-2025-04-14` | 4.1 | Nano | Light | 128K+ | Chat | Pinned |
| `codex-mini-latest` | Rolling | Codex-Mini | Light | 128K | Chat | Rolling alias for Codex product |
| `o4-mini` | o4 | Reasoning | Extended | 128K+ | Chat | Fastest reasoning model |
| `o4-mini-2025-04-16` | o4 | Reasoning | Extended | 128K+ | Chat | Pinned |
| `o3` | o3 | Reasoning | Extended | 128K+ | Chat | Deep reasoning |
| `o3-2025-04-16` | o3 | Reasoning | Extended | 128K+ | Chat | Pinned |
| `o3-mini` | o3 | Reasoning | Extended | 128K+ | Chat | Lighter reasoning |
| `o3-mini-2025-01-31` | o3 | Reasoning | Extended | 128K+ | Chat | Pinned |
| `o3-pro` | o3 | Reasoning | Deep | 128K+ | Responses | Responses API only |
| `o1-pro` | o1 | Reasoning | Deep | 128K+ | Responses | Legacy |
| `gpt-4o` | 4o | Legacy | Standard | 128K | Chat | **Currently used** |
| `gpt-4o-2024-11-20` | 4o | Legacy | Standard | 128K | Chat | Latest 4o pinned |
| `gpt-4o-mini` | 4o | Legacy-Mini | Light | 128K | Chat | **Rejected** — too lenient |

#### Anthropic Models (via `langchain_anthropic.ChatAnthropic`)

| Model ID | Generation | Tier | Reasoning | Context | Notes |
|----------|-----------|------|-----------|---------|-------|
| `claude-opus-4-6` | 4.6 | Opus | Strongest | 200K | Just released (Feb 5, 2026) |
| `claude-opus-4-5` | 4.5 | Opus | Very strong | 200K | Nov 2025 |
| `claude-opus-4-5-20251101` | 4.5 | Opus | Very strong | 200K | Pinned |
| `claude-sonnet-4-5` | 4.5 | Sonnet | Strong | 200K | Best price/perf (Sep 2025) |
| `claude-sonnet-4-5-20250929` | 4.5 | Sonnet | Strong | 200K | Pinned |
| `claude-sonnet-4-0` | 4.0 | Sonnet | Good | 200K | May 2025 |
| `claude-sonnet-4-20250514` | 4.0 | Sonnet | Good | 200K | Pinned |
| `claude-opus-4-0` | 4.0 | Opus | Strong | 200K | May 2025 |
| `claude-opus-4-1-20250805` | 4.1 | Opus | Strong | 200K | Aug 2025 |
| `claude-haiku-4-5` | 4.5 | Haiku | Fast | 200K | Oct 2025 |
| `claude-haiku-4-5-20251001` | 4.5 | Haiku | Fast | 200K | Pinned |
| `claude-3-7-sonnet-latest` | 3.7 | Sonnet | Good | 200K | Legacy (Feb 2025) |
| `claude-3-7-sonnet-20250219` | 3.7 | Sonnet | Good | 200K | Pinned |
| `claude-3-5-haiku-latest` | 3.5 | Haiku | Fast | 200K | Legacy |
| `claude-3-5-haiku-20241022` | 3.5 | Haiku | Fast | 200K | Pinned |
| `claude-3-opus-latest` | 3 | Opus | Strong | 200K | Deprecated |
| `claude-3-haiku-20240307` | 3 | Haiku | Fast | 200K | Deprecated |

### Models NOT Compatible with Chat Completions API

These models require the OpenAI **Responses API** (`client.responses.create()`),
not the Chat Completions API (`client.chat.completions.create()`). LangChain's
`ChatOpenAI` uses **Chat Completions**, so these models **cannot be used directly**
with our current `build_chat_client()` implementation without code changes:

- `gpt-5.2-pro`, `gpt-5.2-pro-2025-12-11`
- `gpt-5.1-codex-max`
- `gpt-5-codex`, `gpt-5-pro`
- `o3-pro`, `o1-pro`
- `o3-deep-research`, `o4-mini-deep-research`
- `computer-use-preview`

### Invalid Model IDs in Current Codebase

| Previously Used | Status | Replacement Applied |
|---------------|--------|---------------------|
| `claude-4.5-sonnet` | **Did not exist** | `claude-sonnet-4-5` (fixed) |
| `gpt-4o` (as default) | Works but legacy | `codex-mini-latest` (trialing) |

---

## Task Classification

Each LangChain consumer script has different requirements. We classify them by
the cognitive demands of the task to drive model selection.

### Task Complexity Tiers

| Tier | Description | Key Attribute | Time Budget |
|------|-------------|---------------|-------------|
| **T1: Classify** | Simple classification, labeling, routing | Pattern matching, short output | < 5s |
| **T2: Extract** | Information extraction, structured parsing | Follows templates, medium output | < 8s |
| **T3: Analyze** | Reasoning about quality, completeness, alignment | Judgment calls, longer output | < 15s |
| **T4: Generate** | Creating new content (issues, decompositions, reviews) | Creative, lengthy output | < 30s |
| **T5: Evaluate** | Multi-factor evaluation, cross-referencing, comparison | Deep reasoning, highest accuracy | < 45s |

### Script → Task Tier Mapping

| Script | Task | Tier | Reasoning Needs | Accuracy Priority | Token Output |
|--------|------|------|-----------------|-------------------|--------------|
| `capability_check.py` | Classify issue capability | **T1** | Low | Medium | Small |
| `label_matcher.py` | Match semantic labels | **T1** | Low | Medium | Small |
| `topic_splitter.py` | Split text into topics | **T2** | Low-Med | Medium | Medium |
| `context_extractor.py` | Extract context from issues | **T2** | Low-Med | Medium | Medium |
| `issue_formatter.py` | Format issue to template | **T2** | Low | Medium | Medium |
| `issue_dedup.py` | Build FAISS vectors for dedup | **T1** | Low | Medium | Small (embeddings) |
| `task_decomposer.py` | Decompose large tasks | **T3** | Medium | High | Large |
| `task_validator.py` | Validate task quality | **T3** | Medium | High | Medium |
| `issue_optimizer.py` | Analyze for optimization | **T3** | Medium | Medium | Medium |
| `progress_reviewer.py` | Review agent progress | **T4** | High | High | Large |
| `followup_issue_generator.py` | Generate follow-up issues | **T4** | High | Medium | Large |
| `pr_verifier.py` | Evaluate PR against rubric | **T5** | High | Very High | Large |
| `analyze_codex_session.py` | Assess task completion | **T3** | Medium | High | Medium |

---

## Selection Algorithm

### Core Concept: Score-Based Model Ranking

For each task, compute a **fitness score** for each available model based on three
weighted dimensions:

$$\text{fitness}(m, t) = w_q \cdot Q(m, t) + w_c \cdot C(m) + w_s \cdot S(m)$$

Where:
- $Q(m, t)$ = quality score of model $m$ for task tier $t$ (0.0–1.0)
- $C(m)$ = cost efficiency score (0.0–1.0, higher = cheaper)
- $S(m)$ = speed score (0.0–1.0, higher = faster)
- $w_q, w_c, w_s$ = weights per task tier

### Weight Profiles by Task Tier

| Tier | $w_q$ (Quality) | $w_c$ (Cost) | $w_s$ (Speed) | Strategy |
|------|---------|---------|---------|----------|
| **T1: Classify** | 0.2 | 0.5 | 0.3 | Cheapest that works |
| **T2: Extract** | 0.4 | 0.3 | 0.3 | Balanced |
| **T3: Analyze** | 0.6 | 0.2 | 0.2 | Quality-biased |
| **T4: Generate** | 0.5 | 0.2 | 0.3 | Quality + speed |
| **T5: Evaluate** | 0.8 | 0.1 | 0.1 | Maximum quality |

### Model Attribute Scores

Estimated initial scores. These should be refined through LangSmith observation.

#### Quality Score $Q(m, t)$ by Task Tier

| Model ID | T1 | T2 | T3 | T4 | T5 | Provider |
|----------|-----|-----|-----|-----|-----|----------|
| `gpt-5.2` | 0.95 | 0.95 | 0.95 | 0.95 | 0.95 | openai |
| `gpt-5.1` | 0.90 | 0.90 | 0.92 | 0.92 | 0.93 | openai |
| `gpt-5.1-codex`| 0.88 | 0.92 | 0.95 | 0.93 | 0.94 | openai |
| `gpt-5.1-mini` | 0.82 | 0.80 | 0.75 | 0.72 | 0.68 | openai |
| `gpt-5` | 0.88 | 0.88 | 0.90 | 0.90 | 0.90 | openai |
| `gpt-5-mini` | 0.78 | 0.75 | 0.70 | 0.68 | 0.62 | openai |
| `gpt-5-nano` | 0.70 | 0.65 | 0.55 | 0.50 | 0.40 | openai |
| `gpt-4.1` | 0.88 | 0.88 | 0.88 | 0.87 | 0.88 | openai |
| `gpt-4.1-mini` | 0.80 | 0.78 | 0.72 | 0.70 | 0.65 | openai |
| `gpt-4.1-nano` | 0.68 | 0.63 | 0.52 | 0.48 | 0.38 | openai |
| `codex-mini-latest` | 0.75 | 0.80 | 0.78 | 0.72 | 0.65 | openai |
| `gpt-4o` | 0.85 | 0.85 | 0.85 | 0.84 | 0.84 | openai |
| `gpt-4o-mini` | 0.60 | 0.55 | 0.45 | 0.40 | 0.30 | openai |
| `o4-mini` | 0.85 | 0.88 | 0.92 | 0.88 | 0.93 | openai |
| `o3` | 0.90 | 0.92 | 0.95 | 0.92 | 0.96 | openai |
| `claude-sonnet-4-5` | 0.90 | 0.90 | 0.92 | 0.92 | 0.94 | anthropic |
| `claude-sonnet-4-0` | 0.85 | 0.85 | 0.88 | 0.88 | 0.90 | anthropic |
| `claude-opus-4-5` | 0.92 | 0.93 | 0.95 | 0.95 | 0.97 | anthropic |
| `claude-opus-4-6` | 0.93 | 0.94 | 0.96 | 0.96 | 0.98 | anthropic |
| `claude-haiku-4-5` | 0.80 | 0.78 | 0.72 | 0.70 | 0.62 | anthropic |

> **Note on gpt-4o-mini**: Quality scores for T3–T5 are intentionally low.
> This model was explicitly rejected in our codebase for being "too lenient"
> on task completion detection. This penalty should persist across all
> analysis-tier tasks.

#### Cost Efficiency Score $C(m)$

Normalized relative cost (1.0 = cheapest, 0.0 = most expensive).
Based on relative pricing tiers — exact values will shift with API changes.

| Model ID | $C(m)$ | Relative Cost | Notes |
|----------|--------|---------------|-------|
| `gpt-4.1-nano` | 1.00 | $ | Cheapest useful model |
| `gpt-5-nano` | 0.95 | $ | Very cheap |
| `gpt-4.1-mini` | 0.90 | $ | Cheap |
| `gpt-5-mini` | 0.85 | $$ | Budget |
| `gpt-5.1-mini` | 0.82 | $$ | Budget |
| `codex-mini-latest` | 0.80 | $$ | Rolling mini |
| `gpt-4o-mini` | 0.78 | $$ | Legacy budget |
| `claude-haiku-4-5` | 0.75 | $$ | Cheapest Claude |
| `gpt-4o` | 0.55 | $$$ | Legacy mid-tier |
| `gpt-4.1` | 0.55 | $$$ | Mid-tier |
| `gpt-5` | 0.45 | $$$ | Standard |
| `gpt-5.1` | 0.40 | $$$$ | Standard+ |
| `gpt-5.1-codex` | 0.38 | $$$$ | Code-optimized |
| `claude-sonnet-4-0` | 0.40 | $$$$ | Anthropic standard |
| `claude-sonnet-4-5` | 0.35 | $$$$ | Anthropic standard+ |
| `gpt-5.2` | 0.30 | $$$$ | Latest flagship |
| `o4-mini` | 0.30 | $$$$ | Reasoning adds cost |
| `o3` | 0.15 | $$$$$ | Expensive reasoning |
| `claude-opus-4-5` | 0.10 | $$$$$ | Opus tier |
| `claude-opus-4-6` | 0.08 | $$$$$ | Latest Opus |

#### Speed Score $S(m)$

Normalized response time (1.0 = fastest, 0.0 = slowest).
Estimated for typical 5K input / 1K output token workloads.

| Model ID | $S(m)$ | Est. Response | Notes |
|----------|--------|---------------|-------|
| `gpt-4.1-nano` | 1.00 | < 1s | Fastest |
| `gpt-5-nano` | 0.98 | ~1s | Very fast |
| `gpt-4.1-mini` | 0.95 | 1–2s | Fast |
| `gpt-5-mini` | 0.93 | 1–2s | Fast |
| `gpt-5.1-mini` | 0.92 | 1–2s | Fast |
| `claude-haiku-4-5` | 0.90 | 1–3s | Fast |
| `codex-mini-latest` | 0.88 | 1–3s | Fast |
| `gpt-4o-mini` | 0.88 | 1–3s | Fast (legacy) |
| `gpt-4o` | 0.80 | 2–4s | Standard |
| `gpt-4.1` | 0.80 | 2–4s | Standard |
| `gpt-5` | 0.75 | 2–5s | Standard |
| `gpt-5.1` | 0.72 | 2–5s | Standard |
| `gpt-5.1-codex` | 0.70 | 2–5s | Standard |
| `gpt-5.2` | 0.68 | 2–5s | Standard |
| `claude-sonnet-4-0` | 0.65 | 3–6s | Moderate |
| `claude-sonnet-4-5` | 0.62 | 3–6s | Moderate |
| `claude-opus-4-5` | 0.40 | 5–12s | Slow |
| `claude-opus-4-6` | 0.38 | 5–12s | Slow |
| `o4-mini` | 0.35 | 5–15s | Reasoning overhead |
| `o3` | 0.15 | 10–30s | Extended reasoning |

### Algorithm Implementation

```python
"""
Model selection algorithm for task-aware slot configuration.

Usage:
    selector = ModelSelector.from_registry("config/model_registry.json")
    best = selector.select(task_tier="T3", available_providers=["github-models"])
    # Returns: ModelChoice(model_id="gpt-4.1", provider="github-models", score=0.82)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


# Task tier weight profiles
TIER_WEIGHTS: dict[str, tuple[float, float, float]] = {
    #              w_quality, w_cost, w_speed
    "T1":          (0.2,      0.5,    0.3),
    "T2":          (0.4,      0.3,    0.3),
    "T3":          (0.6,      0.2,    0.2),
    "T4":          (0.5,      0.2,    0.3),
    "T5":          (0.8,      0.1,    0.1),
}


@dataclass(frozen=True)
class ModelSpec:
    """Static model attributes from the registry."""
    model_id: str
    provider: str                    # "openai", "anthropic", "github-models"
    api: str = "chat"                # "chat" or "responses"
    quality: dict[str, float] = field(default_factory=dict)  # tier -> score
    cost_score: float = 0.5
    speed_score: float = 0.5
    blocked: bool = False            # Hard-block (e.g., gpt-4o-mini)
    notes: str = ""


@dataclass(frozen=True)
class ModelChoice:
    """A scored model selection result."""
    model_id: str
    provider: str
    score: float
    quality: float
    cost: float
    speed: float


class ModelSelector:
    """Select the best model for a task tier given available providers."""

    def __init__(self, models: list[ModelSpec]):
        self.models = models

    @classmethod
    def from_registry(cls, path: str | Path) -> ModelSelector:
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        models = []
        for entry in data.get("models", []):
            models.append(ModelSpec(
                model_id=entry["model_id"],
                provider=entry["provider"],
                api=entry.get("api", "chat"),
                quality=entry.get("quality", {}),
                cost_score=entry.get("cost_score", 0.5),
                speed_score=entry.get("speed_score", 0.5),
                blocked=entry.get("blocked", False),
                notes=entry.get("notes", ""),
            ))
        return cls(models)

    def select(
        self,
        task_tier: str,
        available_providers: list[str] | None = None,
        *,
        exclude_models: list[str] | None = None,
        override_weights: tuple[float, float, float] | None = None,
        min_quality: float = 0.0,
    ) -> ModelChoice | None:
        """
        Select the best model for the given task tier.

        Args:
            task_tier: One of T1-T5
            available_providers: List of providers with valid API keys.
                                 None = all providers available.
            exclude_models: Model IDs to skip
            override_weights: (w_quality, w_cost, w_speed) overrides
            min_quality: Minimum quality score (filter out weak models)

        Returns:
            Best-scoring ModelChoice, or None if no viable model.
        """
        wq, wc, ws = override_weights or TIER_WEIGHTS.get(task_tier, (0.5, 0.25, 0.25))
        exclude = set(exclude_models or [])

        candidates: list[ModelChoice] = []
        for m in self.models:
            # Filter
            if m.blocked:
                continue
            if m.api != "chat":
                continue  # Only Chat Completions API compatible
            if m.model_id in exclude:
                continue
            if available_providers and m.provider not in available_providers:
                continue

            q = m.quality.get(task_tier, 0.5)
            if q < min_quality:
                continue

            score = wq * q + wc * m.cost_score + ws * m.speed_score
            candidates.append(ModelChoice(
                model_id=m.model_id,
                provider=m.provider,
                score=score,
                quality=q,
                cost=m.cost_score,
                speed=m.speed_score,
            ))

        if not candidates:
            return None

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[0]

    def select_top_n(
        self,
        task_tier: str,
        n: int = 3,
        available_providers: list[str] | None = None,
        **kwargs,
    ) -> list[ModelChoice]:
        """Return top N models for A/B testing or compare mode."""
        wq, wc, ws = kwargs.get("override_weights") or TIER_WEIGHTS.get(task_tier, (0.5, 0.25, 0.25))
        exclude = set(kwargs.get("exclude_models", []))
        min_quality = kwargs.get("min_quality", 0.0)

        candidates: list[ModelChoice] = []
        for m in self.models:
            if m.blocked or m.api != "chat" or m.model_id in exclude:
                continue
            if available_providers and m.provider not in available_providers:
                continue
            q = m.quality.get(task_tier, 0.5)
            if q < min_quality:
                continue
            score = wq * q + wc * m.cost_score + ws * m.speed_score
            candidates.append(ModelChoice(
                model_id=m.model_id,
                provider=m.provider,
                score=score,
                quality=q,
                cost=m.cost_score,
                speed=m.speed_score,
            ))

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:n]
```

### Example Selection Results

Using the initial scores above, here are the top-ranked models per task tier
when only GitHub Models (`GITHUB_TOKEN`) is available (our current CI reality):

| Task Tier | #1 Model | Score | #2 Model | Score | #3 Model | Score |
|-----------|----------|-------|----------|-------|----------|-------|
| **T1: Classify** | `gpt-4.1-mini` | 0.74 | `gpt-5-mini` | 0.72 | `gpt-4.1-nano` | 0.70 |
| **T2: Extract** | `gpt-4.1` | 0.72 | `gpt-5.1` | 0.70 | `gpt-5` | 0.69 |
| **T3: Analyze** | `gpt-5.1-codex` | 0.71 | `gpt-5.2` | 0.71 | `gpt-5.1` | 0.70 |
| **T4: Generate** | `gpt-5.1` | 0.68 | `gpt-5.1-codex` | 0.68 | `gpt-4.1` | 0.68 |
| **T5: Evaluate** | `gpt-5.2` | 0.83 | `gpt-5.1-codex` | 0.82 | `gpt-5.1` | 0.82 |

When all providers are available (OpenAI + Anthropic + GitHub Models):

| Task Tier | #1 Model | Score | Provider |
|-----------|----------|-------|----------|
| **T1: Classify** | `gpt-4.1-mini` | 0.74 | openai |
| **T2: Extract** | `claude-sonnet-4-5` | 0.72 | anthropic |
| **T3: Analyze** | `claude-sonnet-4-5` | 0.72 | anthropic |
| **T4: Generate** | `gpt-5.1` | 0.68 | openai |
| **T5: Evaluate** | `claude-opus-4-6` | 0.86 | anthropic |

---

## Slot System Integration

### Current Architecture

The slot system (`config/llm_slots.json`) currently defines 3 static slots
tried in order. The model selection algorithm should **feed** the slot system,
not replace it.

```
┌─────────────────────────────────────────────────────────────┐
│  Model Selection Algorithm (NEW)                            │
│                                                             │
│  Input: task_tier, available_providers, langsmith_feedback   │
│  Output: Ordered list of (provider, model) for slots        │
│                                                             │
│  ┌─────────────┐     ┌──────────────┐     ┌──────────────┐ │
│  │ Model       │────>│ Score &      │────>│ Slot Config  │ │
│  │ Registry    │     │ Rank         │     │ Generator    │ │
│  │ (JSON)      │     │              │     │              │ │
│  └─────────────┘     └──────────────┘     └──────┬───────┘ │
└──────────────────────────────────────────────────┼──────────┘
                                                   │
                                                   ▼
┌─────────────────────────────────────────────────────────────┐
│  Slot System (EXISTING)                                     │
│                                                             │
│  config/llm_slots.json                                      │
│  ┌────────┐  ┌────────┐  ┌────────┐                        │
│  │ slot1  │  │ slot2  │  │ slot3  │                        │
│  │ Best   │  │ 2nd    │  │ Fallback│                        │
│  │ choice │  │ choice │  │        │                        │
│  └────────┘  └────────┘  └────────┘                        │
│                                                             │
│  langchain_client.py: build_chat_client()                   │
│  Tries slot1 → slot2 → slot3, first available wins          │
└─────────────────────────────────────────────────────────────┘
```

### Proposed: Task-Aware Slot Configuration

Instead of one global `llm_slots.json`, generate **per-task slot profiles**:

```json
{
  "profiles": {
    "classify": {
      "tier": "T1",
      "slots": [
        { "name": "slot1", "provider": "openai", "model": "gpt-4.1-mini" },
        { "name": "slot2", "provider": "github-models", "model": "gpt-4.1-mini" },
        { "name": "slot3", "provider": "github-models", "model": "gpt-4o" }
      ]
    },
    "extract": {
      "tier": "T2",
      "slots": [
        { "name": "slot1", "provider": "anthropic", "model": "claude-sonnet-4-5" },
        { "name": "slot2", "provider": "openai", "model": "gpt-4.1" },
        { "name": "slot3", "provider": "github-models", "model": "gpt-4.1" }
      ]
    },
    "analyze": {
      "tier": "T3",
      "slots": [
        { "name": "slot1", "provider": "openai", "model": "gpt-5.1-codex" },
        { "name": "slot2", "provider": "anthropic", "model": "claude-sonnet-4-5" },
        { "name": "slot3", "provider": "github-models", "model": "gpt-4.1" }
      ]
    },
    "generate": {
      "tier": "T4",
      "slots": [
        { "name": "slot1", "provider": "openai", "model": "gpt-5.1" },
        { "name": "slot2", "provider": "anthropic", "model": "claude-sonnet-4-5" },
        { "name": "slot3", "provider": "github-models", "model": "gpt-4.1" }
      ]
    },
    "evaluate": {
      "tier": "T5",
      "slots": [
        { "name": "slot1", "provider": "openai", "model": "gpt-5.2" },
        { "name": "slot2", "provider": "anthropic", "model": "claude-sonnet-4-5" },
        { "name": "slot3", "provider": "github-models", "model": "gpt-5.1-codex" }
      ]
    }
  },
  "default": {
    "tier": "T3",
    "slots": [
      { "name": "slot1", "provider": "openai", "model": "gpt-5.1" },
      { "name": "slot2", "provider": "anthropic", "model": "claude-sonnet-4-5" },
      { "name": "slot3", "provider": "github-models", "model": "gpt-4.1" }
    ]
  }
}
```

### Integration with `build_chat_client()`

Add a `task_tier` parameter to `build_chat_client()`:

```python
def build_chat_client(
    *,
    model: str | None = None,
    provider: str | None = None,
    task_tier: str | None = None,        # NEW: "T1", "T2", etc.
    task_profile: str | None = None,     # NEW: "classify", "evaluate", etc.
    force_openai: bool = False,
    timeout: int | None = None,
    max_retries: int | None = None,
) -> ClientInfo | None:
    """
    Build a LangChain chat client with task-aware model selection.

    If task_tier or task_profile is specified (and no explicit model/provider),
    loads the appropriate slot profile from the task-aware config instead of
    the default slot order.

    Explicit model/provider always takes priority.
    """
    ...
```

### Script Integration (Minimal Change)

Each script simply declares its task profile:

```python
# capability_check.py — before
client = build_chat_client()

# capability_check.py — after
client = build_chat_client(task_profile="classify")

# pr_verifier.py — after
client = build_chat_client(task_profile="evaluate")

# progress_reviewer.py — after
client = build_chat_client(task_profile="generate")
```

The slot system handles fallback as before — the only change is which
models are in which slots.

---

## LangSmith Feedback Loop

### Architecture

```
┌──────────────────────────────────────────┐
│  LangChain Script Execution              │
│  (with LANGCHAIN_TRACING_V2=true)        │
│                                          │
│  Metadata sent per run:                  │
│  - task_profile: "evaluate"              │
│  - task_tier: "T5"                       │
│  - model_id: "gpt-5.2"                  │
│  - provider: "openai"                    │
│  - slot_used: "slot1"                    │
│  - script: "pr_verifier.py"             │
└──────────────┬───────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────┐
│  LangSmith Dashboard                     │
│                                          │
│  Metrics per (model, task_profile):      │
│  - Latency (p50, p95, p99)              │
│  - Token usage (input, output, total)    │
│  - Success rate                          │
│  - Cost                                  │
│  - Human feedback scores (when avail.)   │
│  - Error rate                            │
│  - Retry rate                            │
└──────────────┬───────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────┐
│  Feedback Aggregation (Periodic Job)     │
│                                          │
│  1. Query LangSmith API for metrics      │
│  2. Compute observed quality scores      │
│  3. Update model_registry.json           │
│  4. Re-run selection algorithm           │
│  5. Update llm_slots.json profiles       │
│  6. Commit changes (or PR for review)    │
└──────────────────────────────────────────┘
```

### LangSmith Metadata Tags

Add to every LangChain invocation:

```python
from langchain_core.runnables import RunnableConfig

config = RunnableConfig(
    metadata={
        "task_profile": "evaluate",
        "task_tier": "T5",
        "model_id": client.model,
        "provider": client.provider,
        "script": "pr_verifier.py",
    },
    tags=["task:evaluate", "tier:T5", "script:pr_verifier"],
)

result = client.invoke(prompt, config=config)
```

### Feedback-Driven Score Updates

The quality score $Q(m, t)$ should be updated based on observed performance:

$$Q_{\text{new}}(m, t) = \alpha \cdot Q_{\text{observed}}(m, t) + (1 - \alpha) \cdot Q_{\text{prior}}(m, t)$$

Where:
- $\alpha$ = learning rate (start at 0.3, increase as data volume grows)
- $Q_{\text{observed}}$ = computed from LangSmith metrics:
  - Success rate × 0.4
  - (1 − retry rate) × 0.2
  - Human feedback score × 0.3 (if available)
  - (1 − error rate) × 0.1

Similarly, update speed scores based on observed latency:

$$S_{\text{new}}(m) = \alpha \cdot S_{\text{observed}}(m) + (1 - \alpha) \cdot S_{\text{prior}}(m)$$

Where $S_{\text{observed}}$ normalizes the observed p50 latency against the
latency budget for the task tier.

---

## Implementation Plan

### Phase 1: Model Registry (This PR)

- [x] Create `docs/MODEL_SELECTION_FRAMEWORK.md` (this document)
- [ ] Create `config/model_registry.json` with initial scores
- [ ] Fix `config/llm_slots.json` invalid model IDs
- [ ] Fix `tools/llm_provider.py` Anthropic model ID

### Phase 2: Selection Algorithm

- [ ] Implement `tools/model_selector.py` with `ModelSelector` class
- [ ] Add `task_profile` parameter to `build_chat_client()`
- [ ] Create `config/llm_task_profiles.json` with per-task slot profiles
- [ ] Wire up `_resolve_slots()` to read task profiles

### Phase 3: Script Integration

- [ ] Add `task_profile` declarations to each `scripts/langchain/*.py`
- [ ] Add LangSmith metadata tags to all invocations
- [ ] Test task-aware model selection in CI

### Phase 4: LangSmith Feedback Loop

- [ ] Build `scripts/update_model_scores.py` — queries LangSmith API
- [ ] Create scheduled workflow to run score updates
- [ ] Implement exponential moving average for score updates
- [ ] Add guardrails (minimum sample size, max score change per update)
- [ ] Dashboard integration for visibility

### Phase 5: Advanced Features

- [ ] A/B testing mode via `select_top_n()` + `build_chat_clients()`
- [ ] Auto-promote/demote models based on sustained performance
- [ ] Cost alerting when spend exceeds budget per task profile
- [ ] Model sunset detection (flag deprecated models automatically)
- [ ] Provider health tracking (rate limit detection, degradation)

---

## Appendix: Model Registry JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["models", "version"],
  "properties": {
    "version": {
      "type": "string",
      "description": "Registry version for cache invalidation"
    },
    "last_updated": {
      "type": "string",
      "format": "date",
      "description": "When scores were last updated"
    },
    "models": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["model_id", "provider"],
        "properties": {
          "model_id": { "type": "string" },
          "provider": { "enum": ["openai", "anthropic", "github-models"] },
          "api": { "enum": ["chat", "responses"], "default": "chat" },
          "worker_profile": {
            "type": "boolean",
            "default": false,
            "description": "True when the entry exists only to validate a coding-worker execution profile"
          },
          "lifecycle": {
            "enum": ["trial", "active", "retired"],
            "description": "Optional coding-worker profile lifecycle; omitted for evaluator-only entries"
          },
          "quality": {
            "type": "object",
            "properties": {
              "T1": { "type": "number", "minimum": 0, "maximum": 1 },
              "T2": { "type": "number", "minimum": 0, "maximum": 1 },
              "T3": { "type": "number", "minimum": 0, "maximum": 1 },
              "T4": { "type": "number", "minimum": 0, "maximum": 1 },
              "T5": { "type": "number", "minimum": 0, "maximum": 1 }
            }
          },
          "cost_score": { "type": "number", "minimum": 0, "maximum": 1 },
          "speed_score": { "type": "number", "minimum": 0, "maximum": 1 },
          "blocked": { "type": "boolean", "default": false },
          "notes": { "type": "string" }
        }
      }
    }
  }
}
```

Worker-only validation entries may set `worker_profile: true` and a lifecycle while omitting quality, cost, and speed scores. Their presence proves that an execution-profile model ID is allowed; it is not evaluator evidence and must not be used to rank models.
