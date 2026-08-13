"""Tracing opt-out regression coverage for shared agent tooling."""

from __future__ import annotations

import os
from unittest.mock import patch

from tools.llm_provider import _setup_langsmith_tracing


def test_setup_langsmith_preserves_explicit_tracing_opt_out() -> None:
    """An explicit tracing opt-out disables tracing despite key discovery."""
    with patch.dict(
        os.environ,
        {"LANGSMITH_API_KEY": "ls-key", "LANGCHAIN_TRACING_V2": "false"},
        clear=True,
    ):
        enabled = _setup_langsmith_tracing()
        assert enabled is False
        assert os.environ["LANGCHAIN_TRACING_V2"] == "false"
