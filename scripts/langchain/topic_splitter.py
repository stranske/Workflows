#!/usr/bin/env python3
"""
Split raw multi-issue text into individual topics using LLM.

This replaces regex-based parsing with intelligent LLM-based splitting,
allowing flexible input formats without adding pattern after pattern.

Run with:
    python scripts/langchain/topic_splitter.py \
        --input-file issues.txt --output-file topics.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

# LLM configuration
GITHUB_MODELS_BASE_URL = "https://models.inference.ai.azure.com"
DEFAULT_MODEL = "gpt-4o-mini"

TOPIC_SPLITTER_PROMPT = """
You are a text parsing assistant. The input contains one or more GitHub issues
or feature requests. Your job is to split them into separate, individual issues.

For EACH issue you identify, extract:
1. title: A concise title (the issue heading or first line describing it)
2. body: The full content of that issue (Why, Scope, Tasks, etc.)

Rules:
- Issues may be numbered ("Issue 1", "1.", "A)") or just separated by headers
- Preserve ALL content for each issue - don't summarize or truncate
- Keep markdown formatting, code blocks, and file paths intact
- If there's only ONE issue in the input, return an array with one item

Output format - respond with ONLY valid JSON, no other text:
{{
  "issues": [
    {{
      "title": "First issue title",
      "body": "Full body content of first issue..."
    }},
    {{
      "title": "Second issue title",
      "body": "Full body content of second issue..."
    }}
  ]
}}

Input text to split:
{input_text}
""".strip()


def _get_llm_client() -> tuple[object, str] | None:
    """Get LangChain LLM client."""
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        print("langchain_openai not installed", file=sys.stderr)
        return None

    github_token = os.environ.get("GITHUB_TOKEN")
    openai_token = os.environ.get("OPENAI_API_KEY")
    if not github_token and not openai_token:
        return None

    if github_token:
        return (
            ChatOpenAI(
                model=DEFAULT_MODEL,
                base_url=GITHUB_MODELS_BASE_URL,
                api_key=github_token,
                temperature=0.1,
            ),
            "github-models",
        )
    return (
        ChatOpenAI(
            model=DEFAULT_MODEL,
            api_key=openai_token,
            temperature=0.1,
        ),
        "openai",
    )


def _generate_guid(title: str) -> str:
    """Generate a stable GUID from the title."""
    normalized = re.sub(r"\s+", " ", title.strip().lower())
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, normalized))


def split_topics_with_llm(input_text: str) -> list[dict[str, Any]]:
    """Use LLM to split raw text into individual topics.

    Args:
        input_text: Raw text containing one or more issues

    Returns:
        List of topic dicts with title, body, guid, labels, sections
    """
    client_info = _get_llm_client()
    if not client_info:
        raise RuntimeError("No LLM client available. Set GITHUB_TOKEN or OPENAI_API_KEY.")

    llm, provider = client_info
    print(f"Using LLM provider: {provider}", file=sys.stderr)

    prompt = TOPIC_SPLITTER_PROMPT.format(input_text=input_text)

    try:
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        raise RuntimeError(f"LLM call failed: {e}") from e

    # Extract JSON from response (may be wrapped in markdown code block)
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    json_str = json_match.group(1).strip() if json_match else content.strip()

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"Failed to parse LLM response as JSON: {e}", file=sys.stderr)
        print(f"Response was: {content[:500]}", file=sys.stderr)
        raise RuntimeError("LLM did not return valid JSON") from e

    issues = data.get("issues", [])
    if not issues:
        raise RuntimeError("LLM returned no issues")

    # Convert to standard topic format
    topics = []
    for i, issue in enumerate(issues):
        title = issue.get("title", "").strip()
        body = issue.get("body", "").strip()

        if not title:
            title = f"Untitled Issue {i + 1}"

        topic = {
            "title": title,
            "guid": _generate_guid(title),
            "labels": [],
            "sections": {
                "why": "",
                "tasks": "",
                "acceptance_criteria": "",
                "implementation_notes": "",
            },
            "extras": body,
            "enumerator": str(i + 1),
            "continuity_break": False,
        }
        topics.append(topic)

    return topics


def main() -> None:
    parser = argparse.ArgumentParser(description="Split raw text into topics using LLM")
    parser.add_argument(
        "--input-file",
        type=Path,
        default=Path("input.txt"),
        help="Input file containing raw issue text",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=Path("topics.json"),
        help="Output JSON file with split topics",
    )
    args = parser.parse_args()

    if not args.input_file.exists():
        print(f"Input file not found: {args.input_file}", file=sys.stderr)
        sys.exit(1)

    input_text = args.input_file.read_text(encoding="utf-8").strip()
    if not input_text:
        print("Input file is empty", file=sys.stderr)
        sys.exit(2)

    try:
        topics = split_topics_with_llm(input_text)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    args.output_file.write_text(json.dumps(topics, indent=2), encoding="utf-8")
    print(f"Split into {len(topics)} topic(s). First: {topics[0]['title'][:60]}")


if __name__ == "__main__":
    main()
