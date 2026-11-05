"""Text extraction shared by provider response consumers."""

from collections.abc import Mapping


def text_from_response_content(content: object, *, separator: str = "") -> str | None:
    """Return provider text, or None when the payload carries no text blocks."""
    if isinstance(content, str):
        return content if content and not content.isspace() else None
    if isinstance(content, Mapping):
        block_type = content.get("type")
        for key in ("text", "content"):
            text = content.get(key)
            if (
                isinstance(text, str)
                and text
                and not text.isspace()
                and block_type in (None, "text", "output_text")
            ):
                return text
        return None
    if isinstance(content, list):
        text_blocks: list[str] = []
        for block in content:
            if isinstance(block, str):
                text = block
            elif isinstance(block, Mapping):
                if block.get("type") not in (None, "text", "output_text"):
                    text = None
                else:
                    text = block.get("text")
                    if not isinstance(text, str):
                        text = block.get("content")
            else:
                if getattr(block, "type", None) not in (None, "text", "output_text"):
                    text = None
                else:
                    text = getattr(block, "text", None)
                    if not isinstance(text, str):
                        text = getattr(block, "content", None)
            if isinstance(text, str):
                text_blocks.append(text)
        if any(block and not block.isspace() for block in text_blocks):
            # Concatenate without a separator: a provider may split one JSON
            # document across blocks, and an inserted newline inside a string
            # literal would make the reassembled payload invalid JSON.
            return separator.join(text_blocks)
    return None
