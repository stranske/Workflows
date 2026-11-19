"""Small LangSmith tracing helpers for LangChain script entry points."""

from __future__ import annotations

import dis
import inspect
import linecache
import logging
import os
from dataclasses import dataclass
from typing import Any, Literal

LOGGER = logging.getLogger(__name__)

ConfigSupport = Literal["explicit", "variadic", "unknown", "none"]


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


@dataclass(frozen=True)
class _TracebackFrame:
    code: Any
    lineno: int
    lasti: int


def build_llm_config(
    *,
    operation: str,
    issue_number: int | None = None,
) -> dict[str, object]:
    """Build LangSmith metadata/tags for LLM call (issue-scoped entry points)."""

    try:
        from tools.llm_provider import build_langsmith_metadata

        return build_langsmith_metadata(
            operation=operation,
            issue_number=issue_number,
        )
    except ImportError:
        pass

    repo = os.environ.get("GITHUB_REPOSITORY", "unknown")
    run_id = os.environ.get("GITHUB_RUN_ID") or os.environ.get("RUN_ID") or "unknown"
    env_issue = os.environ.get("ISSUE_NUMBER", "")
    issue_or_pr = (
        str(issue_number)
        if issue_number is not None
        else env_issue if env_issue.isdigit() else "unknown"
    )
    metadata = {
        "repo": repo,
        "run_id": run_id,
        "issue_or_pr_number": issue_or_pr,
        "operation": operation,
        "issue_number": str(issue_number) if issue_number is not None else None,
    }
    tags = [
        "workflows-agents",
        f"operation:{operation}",
        f"repo:{repo}",
        f"issue_or_pr:{issue_or_pr}",
        f"run_id:{run_id}",
    ]
    return {"metadata": metadata, "tags": tags}


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


def _invoke_config_support(invoke: Any) -> ConfigSupport:
    try:
        signature = inspect.signature(invoke)
    except (TypeError, ValueError):
        return "unknown"

    accepts_variadic_kwargs = False
    for param in signature.parameters.values():
        if param.name == "config":
            return "explicit"
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            accepts_variadic_kwargs = True
    return "variadic" if accepts_variadic_kwargs else "none"


def _is_unsupported_config_error(exc: TypeError, *, allow_delegated: bool = False) -> bool:
    message = str(exc).lower()
    no_keyword_support = (
        "takes no keyword argument" in message
        or "takes no keyword arguments" in message
        or "does not take keyword argument" in message
        or "does not take keyword arguments" in message
        or "doesn't take keyword argument" in message
        or "doesn't take keyword arguments" in message
    )
    unsupported_config_message = no_keyword_support or (
        "config" in message
        and (
            "unexpected keyword argument" in message
            or "got an unexpected keyword" in message
            or "positional-only" in message
        )
    )
    if not unsupported_config_message:
        return False
    if _is_direct_call_type_error(exc):
        return True
    return allow_delegated and "config" in message and _is_delegated_call_type_error(exc)


def _traceback_frames(exc: TypeError) -> list[_TracebackFrame]:
    frames: list[_TracebackFrame] = []
    tb = exc.__traceback__
    while tb is not None:
        frames.append(
            _TracebackFrame(
                code=tb.tb_frame.f_code,
                lineno=tb.tb_lineno,
                lasti=tb.tb_lasti,
            )
        )
        tb = tb.tb_next
    return frames


def _is_call_instruction(frame: _TracebackFrame) -> bool:
    for instruction in dis.get_instructions(frame.code):
        if instruction.offset == frame.lasti:
            return instruction.opname.startswith("CALL")
    return False


def _is_forwarding_invoke_call(frame: _TracebackFrame) -> bool:
    if not _is_call_instruction(frame):
        return False

    source = " ".join(
        linecache.getline(frame.code.co_filename, lineno).strip()
        for lineno in range(frame.lineno, frame.lineno + 6)
    )
    return "invoke(" in source or "__call__(" in source


def _is_direct_call_type_error(exc: TypeError) -> bool:
    """Return true when Python rejected the call before entering invoke()."""

    frames = _traceback_frames(exc)
    # TypeErrors raised by the runnable include an inner traceback frame.
    # Direct argument-binding failures from builtins/C shims stop at this call site.
    return len(frames) == 1 and frames[0].code is invoke_with_trace.__code__


def _is_delegated_call_type_error(exc: TypeError) -> bool:
    """Return true for ``invoke(**kwargs)`` wrappers rejected below the wrapper."""

    frames = _traceback_frames(exc)
    return (
        len(frames) > 1
        and frames[0].code is invoke_with_trace.__code__
        and frames[1].code.co_name in {"invoke", "__call__"}
        and _is_forwarding_invoke_call(frames[-1])
    )


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
    invoke = runnable.invoke
    config_support = _invoke_config_support(invoke)
    if config_support != "none":
        try:
            response = invoke(payload, config=config)
        except TypeError as exc:
            if not _is_unsupported_config_error(
                exc,
                allow_delegated=config_support == "variadic",
            ):
                raise
            response = invoke(payload)
    else:
        response = invoke(payload)
    trace = extract_trace_info(response)
    if trace.trace_url:
        LOGGER.info("LangSmith trace: %s", trace.trace_url)
    return response, trace
