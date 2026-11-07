"""Behavior selected from the verified #4481 final-head Gate missing-line log."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from scripts.langchain import pr_verifier as verifier


@pytest.mark.parametrize(
    ("repaired", "expected"),
    [
        pytest.param(None, None, id="no-repair"),
        pytest.param([{"type": "thinking", "thinking": "metadata"}], None, id="metadata-only"),
        pytest.param([{"type": "text", "text": "   "}], None, id="blank-text"),
        pytest.param(
            [
                {"type": "thinking", "thinking": "private metadata"},
                {"type": "text", "text": '{"verdict":'},
                {"type": "text", "text": '"PASS"}'},
            ],
            '{"verdict":"PASS"}',
            id="text-blocks",
        ),
    ],
)
def test_schema_repair_returns_only_usable_response_text(monkeypatch, repaired, expected) -> None:
    client = object()
    repair = Mock(return_value=repaired)
    factory = Mock(return_value=repair)
    cap = Mock(return_value="bounded raw response")
    monkeypatch.setattr(verifier, "build_repair_callback", factory)
    monkeypatch.setattr(verifier, "_cap_prompt_text", cap)

    callback = verifier._build_verifier_repair_callback(client)
    result = callback("schema", "validation errors", "raw response")

    assert result == expected
    factory.assert_called_once()
    wrapped = factory.call_args.args[0]
    assert isinstance(wrapped, verifier._CapacityCheckedRepairClient)
    assert wrapped.client is client
    cap.assert_called_once_with("raw response", verifier.EVAL_SCHEMA_REPAIR_BUDGET_TOKENS)
    repair.assert_called_once_with("schema", "validation errors", "bounded raw response")
