#!/usr/bin/env python3
"""Shared issue and PR context assembly with prompt budget caps."""

from __future__ import annotations

import base64
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

DEFAULT_TOKEN_BUDGET = 4000
TOKEN_CHARS = 4
MARKER_VERSION = "v1"
MARKER_PREFIX = "issue-pr-context:formatted-body"
MARKER_RE = re.compile(
    rf"<!--\s*{re.escape(MARKER_PREFIX)}:{MARKER_VERSION}\s+(\{{.*?\}})\s*-->",
    re.DOTALL,
)


@dataclass(frozen=True)
class ContextOptions:
    token_budget: int = DEFAULT_TOKEN_BUDGET
    include_diff: bool = False
    include_labels: bool = True
    include_author: bool = True
    include_url: bool = True
    downstream_workflow: str | None = None
    model: str | None = None


def estimate_tokens(text: str, *, model: str | None = None) -> int:
    """Estimate prompt tokens using tiktoken when available, else 4 chars/token."""
    value = text or ""
    if not value:
        return 0

    try:
        import tiktoken  # type: ignore[import-not-found]
    except ImportError:
        return math.ceil(len(value) / TOKEN_CHARS)

    try:
        encoding = (
            tiktoken.encoding_for_model(model) if model else tiktoken.get_encoding("cl100k_base")
        )
    except Exception:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(value))


def build_issue_context(
    issue: Mapping[str, Any],
    options: ContextOptions | None = None,
) -> dict[str, Any]:
    """Return a capped context payload for a GitHub issue object."""
    resolved = options or ContextOptions()
    body = reuse_formatted_body(issue, resolved.downstream_workflow)
    if body is None:
        body = _text(issue.get("formatted_body") or issue.get("body"))

    metadata_block = _issue_metadata(issue, resolved)
    return _build_payload(
        kind="issue",
        body_heading="## Issue Body",
        body=body,
        metadata_block=metadata_block,
        options=resolved,
    )


def build_pr_context(
    pr: Mapping[str, Any],
    options: ContextOptions | None = None,
) -> dict[str, Any]:
    """Return a capped context payload for a GitHub pull request object."""
    resolved = options or ContextOptions()
    body = reuse_formatted_body(pr, resolved.downstream_workflow)
    if body is None:
        body = _text(pr.get("formatted_body") or pr.get("body"))

    diff_body = _diff_text(pr) if resolved.include_diff else ""
    metadata_block = _pr_metadata(pr, resolved)
    extra_sections = [("## Pull Request Diff", diff_body)] if diff_body else None
    return _build_payload(
        kind="pr",
        body_heading="## Pull Request Body",
        body=body,
        metadata_block=metadata_block,
        options=resolved,
        extra_sections=extra_sections,
    )


def reuse_formatted_body(
    issue_or_pr: Mapping[str, Any],
    downstream_workflow: str | None,
) -> str | None:
    """Return a marker-backed formatted body for the same issue or PR, if present."""
    body = _text(issue_or_pr.get("body"))
    if not body:
        return None

    for match in MARKER_RE.finditer(body):
        payload = _loads_marker(match.group(1))
        if payload is None:
            continue
        if not _workflow_matches(payload, downstream_workflow):
            continue

        embedded = _embedded_body(payload)
        if embedded is not None:
            return embedded

        cleaned = (body[: match.start()] + body[match.end() :]).strip()
        if _body_hash_matches(payload, cleaned):
            return cleaned
        if "sha256" not in payload and "body_sha256" not in payload:
            return cleaned
    return None


def build_formatted_body_marker(
    *,
    downstream_workflow: str | None = None,
    workflows: list[str] | tuple[str, ...] | None = None,
    formatted_body: str | None = None,
) -> str:
    """Build a compact marker that downstream callers can store with a body."""
    payload: dict[str, Any] = {}
    if downstream_workflow:
        payload["workflow"] = downstream_workflow
    if workflows:
        payload["workflows"] = list(workflows)
    if formatted_body is not None:
        payload["body_b64"] = base64.b64encode(formatted_body.encode("utf-8")).decode("ascii")
    return f"<!-- {MARKER_PREFIX}:{MARKER_VERSION} {json.dumps(payload, sort_keys=True)} -->"


def _build_payload(
    *,
    kind: str,
    body_heading: str,
    body: str,
    metadata_block: str,
    options: ContextOptions,
    extra_sections: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    sections = [(body_heading, body)]
    sections.extend(extra_sections or [])

    metadata_block, metadata_truncated = _cap_block(
        metadata_block,
        max(1, options.token_budget),
        model=options.model,
    )
    capped_sections, truncated = _cap_sections(metadata_block, sections, options)
    context = "\n\n".join(part for part in [metadata_block, *capped_sections] if part).strip()
    return {
        "kind": kind,
        "metadata_block": metadata_block,
        "formatted_body": (
            capped_sections[0].split("\n", 1)[1].strip()
            if capped_sections and "\n" in capped_sections[0]
            else ""
        ),
        "context": context,
        "truncated": truncated or metadata_truncated,
        "estimated_tokens": estimate_tokens(context, model=options.model),
        "token_budget": max(1, options.token_budget),
    }


def _cap_block(text: str, token_budget: int, *, model: str | None = None) -> tuple[str, bool]:
    if estimate_tokens(text, model=model) <= token_budget:
        return text, False

    marker = "\n[truncated: context exceeded token budget]"
    marker_tokens = estimate_tokens(marker, model=model)
    allowed_chars = max(1, (token_budget - marker_tokens) * TOKEN_CHARS)
    return f"{text[:allowed_chars].rstrip()}{marker}", True


def _cap_sections(
    metadata_block: str,
    sections: list[tuple[str, str]],
    options: ContextOptions,
) -> tuple[list[str], bool]:
    budget = max(1, options.token_budget)
    rendered: list[str] = []
    truncated = False

    prefix = metadata_block.strip()
    for heading, text in sections:
        remaining = budget - estimate_tokens(
            "\n\n".join(part for part in [prefix, *rendered] if part),
            model=options.model,
        )
        if remaining <= 0:
            rendered.append(f"{heading}\n[truncated: token budget exhausted before this section]")
            truncated = True
            continue

        section = f"{heading}\n{_text(text).strip()}".rstrip()
        if estimate_tokens(section, model=options.model) <= remaining:
            rendered.append(section)
            continue

        marker = "\n\n[truncated: context exceeded token budget]"
        marker_tokens = estimate_tokens(f"{heading}{marker}", model=options.model)
        allowed_tokens = max(1, remaining - marker_tokens)
        allowed_chars = allowed_tokens * TOKEN_CHARS
        capped_text = _text(text).strip()[:allowed_chars].rstrip()
        rendered.append(f"{heading}\n{capped_text}{marker}".rstrip())
        truncated = True

    context = "\n\n".join(part for part in [metadata_block, *rendered] if part)
    while estimate_tokens(context, model=options.model) > budget and rendered:
        truncated = True
        heading = rendered[-1].split("\n", 1)[0]
        rendered[-1] = f"{heading}\n[truncated: token budget exhausted before this section]"
        context = "\n\n".join(part for part in [metadata_block, *rendered] if part)

    return rendered, truncated


def _issue_metadata(issue: Mapping[str, Any], options: ContextOptions) -> str:
    lines = ["## Issue Metadata"]
    number = issue.get("number")
    if number is not None:
        lines.append(f"- Number: #{number}")
    _append_value(lines, "Title", issue.get("title"))
    _append_value(lines, "State", issue.get("state"))
    if options.include_author:
        _append_value(lines, "Author", _login(issue.get("user")))
    if options.include_url:
        _append_value(lines, "URL", issue.get("html_url") or issue.get("url"))
    if options.include_labels:
        labels = _labels(issue.get("labels"))
        if labels:
            lines.append(f"- Labels: {', '.join(labels)}")
    return "\n".join(lines)


def _pr_metadata(pr: Mapping[str, Any], options: ContextOptions) -> str:
    lines = ["## Pull Request Metadata"]
    number = pr.get("number")
    if number is not None:
        lines.append(f"- Number: #{number}")
    _append_value(lines, "Title", pr.get("title"))
    _append_value(lines, "State", pr.get("state"))
    if options.include_author:
        _append_value(lines, "Author", _login(pr.get("user")))
    if options.include_url:
        _append_value(lines, "URL", pr.get("html_url") or pr.get("url"))
    _append_value(lines, "Base", _branch_name(pr.get("base")))
    _append_value(lines, "Head", _branch_name(pr.get("head")))
    for key in ("changed_files", "additions", "deletions"):
        if pr.get(key) is not None:
            lines.append(f"- {key.replace('_', ' ').title()}: {pr[key]}")
    if options.include_labels:
        labels = _labels(pr.get("labels"))
        if labels:
            lines.append(f"- Labels: {', '.join(labels)}")
    if options.include_diff and _diff_text(pr):
        lines.append("- Diff: included")
    return "\n".join(lines)


def _loads_marker(value: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _workflow_matches(payload: Mapping[str, Any], downstream_workflow: str | None) -> bool:
    if not downstream_workflow:
        return True
    workflow = payload.get("workflow") or payload.get("downstream_workflow")
    workflows = payload.get("workflows")
    if workflow in (downstream_workflow, "*", "all"):
        return True
    if isinstance(workflows, list):
        return downstream_workflow in workflows or "*" in workflows or "all" in workflows
    return workflow is None and workflows is None


def _embedded_body(payload: Mapping[str, Any]) -> str | None:
    body = payload.get("formatted_body")
    if isinstance(body, str):
        return body
    body_b64 = payload.get("body_b64")
    if not isinstance(body_b64, str):
        return None
    try:
        return base64.b64decode(body_b64.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def _body_hash_matches(payload: Mapping[str, Any], body: str) -> bool:
    expected = payload.get("sha256") or payload.get("body_sha256")
    if not isinstance(expected, str):
        return False
    import hashlib

    return hashlib.sha256(body.encode("utf-8")).hexdigest() == expected


def _diff_text(pr: Mapping[str, Any]) -> str:
    diff = pr.get("diff") or pr.get("patch")
    if isinstance(diff, str):
        return diff
    files = pr.get("files")
    if not isinstance(files, list):
        return ""
    parts: list[str] = []
    for entry in files:
        if not isinstance(entry, Mapping):
            continue
        filename = _text(entry.get("filename"))
        patch = _text(entry.get("patch"))
        if filename and patch:
            parts.append(f"diff -- {filename}\n{patch}")
    return "\n\n".join(parts)


def _append_value(lines: list[str], label: str, value: Any) -> None:
    text = _text(value).strip()
    if text:
        lines.append(f"- {label}: {text}")


def _labels(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    labels: list[str] = []
    for item in value:
        if isinstance(item, str):
            labels.append(item)
        elif isinstance(item, Mapping) and item.get("name"):
            labels.append(str(item["name"]))
    return labels


def _login(value: Any) -> str:
    if isinstance(value, Mapping):
        return _text(value.get("login"))
    return _text(value)


def _branch_name(value: Any) -> str:
    if isinstance(value, Mapping):
        return _text(value.get("label") or value.get("ref"))
    return _text(value)


def _text(value: Any) -> str:
    return value if isinstance(value, str) else "" if value is None else str(value)
