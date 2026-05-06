#!/usr/bin/env python3
"""Shared issue and PR context assembly with prompt budget caps."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import math
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

DEFAULT_TOKEN_BUDGET = 4000
TOKEN_CHARS = 4
MARKER_VERSION = "v1"
MARKER_PREFIX = "issue-pr-context:formatted-body"
MARKER_RE = re.compile(
    rf"<!--\s*{re.escape(MARKER_PREFIX)}:{MARKER_VERSION}\s+(.+?)\s*-->",
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
    """Estimate prompt tokens using tiktoken when available, else 4 chars/token.

    Returns ``max(tiktoken_count, chars/4)``: tiktoken's BPE encoding aggressively
    compresses repeated patterns (e.g. 60K of the same character collapses to a
    handful of tokens), which would let oversized inputs slip past token-budget
    truncation. The chars/4 floor keeps the cap honest against compressible
    inputs while preserving accurate counts on normal prose.
    """
    value = text or ""
    if not value:
        return 0

    chars_estimate = math.ceil(len(value) / TOKEN_CHARS)

    try:
        import tiktoken  # type: ignore[import-not-found]
    except ImportError:
        return chars_estimate

    try:
        encoding = (
            tiktoken.encoding_for_model(model) if model else tiktoken.get_encoding("cl100k_base")
        )
    except Exception:
        encoding = tiktoken.get_encoding("cl100k_base")
    return max(len(encoding.encode(value)), chars_estimate)


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
    metadata_block = _pr_metadata(pr, resolved, diff_body=diff_body)
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
            if ("sha256" in payload or "body_sha256" in payload) and not _body_hash_matches(
                payload,
                embedded,
            ):
                continue
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
        payload["sha256"] = hashlib.sha256(formatted_body.encode("utf-8")).hexdigest()
    marker_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return f"<!-- {MARKER_PREFIX}:{MARKER_VERSION} {marker_payload} -->"


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
    return _truncate_with_suffix(text, token_budget, suffix=marker, model=model), True


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
        base_context = _join_context([prefix, *rendered])
        section_prefix = "\n\n" if base_context else ""
        remaining = budget - estimate_tokens(f"{base_context}{section_prefix}", model=options.model)
        if remaining <= 0:
            truncated = True
            continue

        section = f"{heading}\n{_text(text).strip()}".rstrip()
        if (
            estimate_tokens(f"{base_context}{section_prefix}{section}", model=options.model)
            <= budget
        ):
            rendered.append(section)
            continue

        marker = "\n\n[truncated: context exceeded token budget]"
        capped_section = _truncate_section(
            heading,
            _text(text).strip(),
            remaining,
            suffix=marker,
            model=options.model,
        )
        if capped_section:
            rendered.append(capped_section)
        truncated = True

    context = "\n\n".join(part for part in [metadata_block, *rendered] if part)
    while estimate_tokens(context, model=options.model) > budget and rendered:
        truncated = True
        previous = context
        heading = rendered[-1].split("\n", 1)[0]
        base_context = _join_context([metadata_block, *rendered[:-1]])
        section_prefix = "\n\n" if base_context else ""
        remaining = budget - estimate_tokens(f"{base_context}{section_prefix}", model=options.model)
        rendered[-1] = _truncate_section(
            heading,
            "",
            remaining,
            suffix="\n[truncated: token budget exhausted before this section]",
            model=options.model,
        )
        if not rendered[-1]:
            rendered.pop()
        context = "\n\n".join(part for part in [metadata_block, *rendered] if part)
        if context == previous:
            rendered.pop()
            context = "\n\n".join(part for part in [metadata_block, *rendered] if part)

    return rendered, truncated


def _join_context(parts: list[str]) -> str:
    return "\n\n".join(part for part in parts if part)


def _truncate_with_suffix(
    text: str,
    token_budget: int,
    *,
    suffix: str = "",
    model: str | None = None,
) -> str:
    budget = max(0, token_budget)
    source = _text(text).rstrip()
    suffix_text = suffix if estimate_tokens(suffix, model=model) <= budget else ""
    low = 0
    high = len(source)
    best = ""
    while low <= high:
        midpoint = (low + high) // 2
        candidate = f"{source[:midpoint].rstrip()}{suffix_text}".rstrip()
        if estimate_tokens(candidate, model=model) <= budget:
            best = candidate
            low = midpoint + 1
        else:
            high = midpoint - 1
    return best


def _truncate_section(
    heading: str,
    text: str,
    token_budget: int,
    *,
    suffix: str,
    model: str | None = None,
) -> str:
    budget = max(0, token_budget)
    prefix = f"{heading}\n"
    if estimate_tokens(prefix.rstrip(), model=model) > budget:
        return _truncate_with_suffix(heading, budget, model=model)

    suffix_text = (
        suffix if estimate_tokens(f"{prefix}{suffix}".rstrip(), model=model) <= budget else ""
    )
    low = 0
    high = len(text)
    best = prefix.rstrip()
    while low <= high:
        midpoint = (low + high) // 2
        candidate = f"{prefix}{text[:midpoint].rstrip()}{suffix_text}".rstrip()
        if estimate_tokens(candidate, model=model) <= budget:
            best = candidate
            low = midpoint + 1
        else:
            high = midpoint - 1
    return best


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


def _pr_metadata(pr: Mapping[str, Any], options: ContextOptions, *, diff_body: str = "") -> str:
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
    if options.include_diff and diff_body:
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
    except (binascii.Error, UnicodeEncodeError, UnicodeDecodeError, ValueError):
        return None


def _body_hash_matches(payload: Mapping[str, Any], body: str) -> bool:
    expected = payload.get("sha256") or payload.get("body_sha256")
    if not isinstance(expected, str):
        return False
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


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build capped issue or PR context.")
    parser.add_argument("--kind", choices=("issue", "pr"), default="issue")
    parser.add_argument(
        "--input-file", required=True, help="Path containing issue or PR body text."
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit the full context payload as JSON."
    )
    parser.add_argument("--token-budget", type=int, default=DEFAULT_TOKEN_BUDGET)
    parser.add_argument("--downstream-workflow")
    parser.add_argument("--include-diff", action="store_true")
    parser.add_argument("--no-labels", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    from pathlib import Path

    body = Path(args.input_file).read_text(encoding="utf-8")
    options = ContextOptions(
        token_budget=args.token_budget,
        include_diff=args.include_diff,
        include_labels=not args.no_labels,
        downstream_workflow=args.downstream_workflow,
    )
    subject = {"body": body}
    payload = (
        build_pr_context(subject, options)
        if args.kind == "pr"
        else build_issue_context(subject, options)
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
    else:
        print(payload["context"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
