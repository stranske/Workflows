"""Tracing opt-out regression coverage for shared agent tooling."""

from __future__ import annotations

import os
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from shutil import copyfile
from unittest.mock import patch

import pytest
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


def test_raw_consumer_template_preserves_explicit_tracing_opt_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = Path(__file__).resolve().parents[2] / "templates/consumer-repo/tools/llm_provider.py"
    copied = tmp_path / "llm_provider.py"
    copyfile(source, copied)
    spec = spec_from_file_location("_consumer_template_llm_provider", copied)
    assert spec is not None and spec.loader is not None
    provider = module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, provider)

    with (
        patch.dict(
            os.environ,
            {"LANGSMITH_API_KEY": "ls-key", "LANGCHAIN_TRACING_V2": "false"},
            clear=True,
        ),
        patch("socket.socket", side_effect=AssertionError("network is not part of this test")),
    ):
        spec.loader.exec_module(provider)
        assert (provider.LANGSMITH_ENABLED, os.environ["LANGCHAIN_TRACING_V2"]) == (False, "false")
