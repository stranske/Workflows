"""Smoke tests for synced LangChain helper imports."""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parents[2]
LANGCHAIN_SCRIPTS = ROOT / "scripts" / "langchain"
MANIFEST = ROOT / ".github" / "sync-manifest.yml"
TEMPLATE = ROOT / "templates" / "consumer-repo"


def _manifest_sources() -> set[str]:
    sources: set[str] = set()
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("- source: "):
            sources.add(stripped.removeprefix("- source: ").strip())
    return sources


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


def test_synced_consumer_tree_imports_langchain_helpers(tmp_path: Path) -> None:
    consumer = tmp_path / "consumer"
    shutil.copytree(TEMPLATE, consumer)

    for source in _manifest_sources():
        source_path = ROOT / source
        if not source_path.is_file():
            continue
        destination = consumer / source
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)

    module_names = sorted(
        f"scripts.langchain.{path.stem}"
        for path in (consumer / "scripts" / "langchain").glob("*.py")
        if path.name != "__init__.py"
    )

    script = dedent(f"""
        import importlib

        module_names = {module_names!r}
        assert "scripts.langchain.pr_verifier" in module_names
        verifier = importlib.import_module("scripts.langchain.pr_verifier")
        assert verifier.api_client.__name__ == "scripts.api_client"
        for module_name in module_names:
            importlib.import_module(module_name)
        """)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(consumer)

    subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        cwd=consumer,
        env=env,
    )


def test_raw_consumer_scaffold_handles_capability_text_blocks(tmp_path: Path) -> None:
    consumer = tmp_path / "consumer"
    shutil.copytree(TEMPLATE, consumer)
    script = dedent("""
        import sys
        from types import ModuleType, SimpleNamespace
        from unittest.mock import MagicMock, patch

        from scripts.langchain import capability_check

        payload = '{"recommendation":"REVIEW_NEEDED"}'
        chain = MagicMock()
        template = MagicMock()
        template.__or__.return_value = chain

        class EmptyBlocks:
            content = []

            def __str__(self):
                return '{"recommendation":"PROCEED"}'

        prompts = ModuleType("langchain_core.prompts")
        prompts.ChatPromptTemplate = SimpleNamespace(from_template=lambda _prompt: template)
        with (
            patch.dict(sys.modules, {"langchain_core.prompts": prompts}),
            patch.object(capability_check, "_get_llm_client", return_value=(object(), "test")),
        ):
            tasks = ["Integrate Stripe payments"]
            acceptance = "Confirm payment integration"
            chain.invoke.return_value = SimpleNamespace(content=payload)
            expected = capability_check.classify_capabilities(tasks, acceptance)
            chain.invoke.return_value = SimpleNamespace(content=[
                {"type": "text", "text": payload[:12]},
                {"type": "text", "text": payload[12:]},
            ])
            result = capability_check.classify_capabilities(tasks, acceptance)
            assert result.recommendation == "REVIEW_NEEDED"
            assert result.to_dict() == expected.to_dict()
            chain.invoke.return_value = EmptyBlocks()
            result = capability_check.classify_capabilities(tasks, acceptance)
            assert result.recommendation == "BLOCKED"
            assert "LLM response missing JSON payload" in result.human_actions_needed
        """)
    subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        cwd=consumer,
        env={"PYTHONPATH": str(consumer)},
    )
