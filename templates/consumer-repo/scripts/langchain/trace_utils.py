"""Small LangSmith tracing helpers for LangChain script entry points."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TraceInfo:
    """Trace metadata extracted from a LangChain response."""

    trace_id: str | None = None
    trace_url: str | None = None

    @property
    def available(self) -> bool:
        return bool(self.trace_id or self.trace_url)

    def as_dict(self) -> dict[str, str]:
        payload: dict[str, str] = {}
        if self.trace_id:
            payload["langsmith_trace_id"] = self.trace_id
        if self.trace_url:
            payload["langsmith_trace_url"] = self.trace_url
        return payload


def build_trace_config(
    *,
    operation: str,
    pr_number: int | None = None,
    issue_number: int | None = None,
) -> dict[str, object]:
    """Build standard LangSmith config for a LangChain invocation."""

    try:
        from tools.llm_provider import build_langsmith_metadata

        return build_langsmith_metadata(
            operation=operation,
            pr_number=pr_number,
            issue_number=issue_number,
        )
    except Exception:
        metadata = {
            "operation": operation,
            "pr_number": str(pr_number) if pr_number is not None else None,
            "issue_number": str(issue_number) if issue_number is not None else None,
        }
        return {"metadata": metadata, "tags": [f"operation:{operation}"]}


def extract_trace_info(response: Any) -> TraceInfo:
    """Extract trace ID and URL from a LangChain response when available."""

    try:
        from tools.llm_provider import derive_langsmith_trace_url, extract_trace_id

        trace_id = extract_trace_id(response)
        trace_url = derive_langsmith_trace_url(trace_id) if trace_id else None
        return TraceInfo(trace_id=trace_id, trace_url=trace_url)
    except Exception:
        LOGGER.debug("LangSmith trace extraction unavailable", exc_info=True)
        return TraceInfo()


def invoke_with_trace(
    runnable: Any,
    payload: Any,
    *,
    operation: str,
    pr_number: int | None = None,
    issue_number: int | None = None,
) -> tuple[Any, TraceInfo]:
    """Invoke a LangChain runnable with metadata and return trace details.

    Some older local tests and provider shims do not accept a ``config=``
    argument. In that case, retry once without config while still extracting
    trace details if the provider response exposes them.
    """

    config = build_trace_config(
        operation=operation,
        pr_number=pr_number,
        issue_number=issue_number,
    )
    try:
        response = runnable.invoke(payload, config=config)
    except Exception as first_exc:
        try:
            response = runnable.invoke(payload)
        except Exception as fallback_exc:
            raise first_exc from fallback_exc
    trace = extract_trace_info(response)
    if trace.trace_url:
        LOGGER.info("LangSmith trace: %s", trace.trace_url)
    return response, trace
