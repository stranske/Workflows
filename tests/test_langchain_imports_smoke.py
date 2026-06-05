"""Smoke tests for synced LangChain helper imports."""

from __future__ import annotations

import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANGCHAIN_SCRIPTS = ROOT / "scripts" / "langchain"


def test_pr_verifier_imports_with_synced_api_client() -> None:
    module = importlib.import_module("scripts.langchain.pr_verifier")

    assert module.api_client.__name__ == "scripts.api_client"


def test_langchain_helper_modules_are_importable() -> None:
    module_names = sorted(
        f"scripts.langchain.{path.stem}"
        for path in LANGCHAIN_SCRIPTS.glob("*.py")
        if path.name != "__init__.py"
    )

    assert "scripts.langchain.pr_verifier" in module_names

    for module_name in module_names:
        importlib.import_module(module_name)
