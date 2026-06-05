"""Regression coverage for synced pr_verifier dependencies."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / ".github" / "sync-manifest.yml"
PR_VERIFIER = ROOT / "scripts" / "langchain" / "pr_verifier.py"


def _manifest_sources() -> set[str]:
    sources: set[str] = set()
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("- source: "):
            sources.add(stripped.removeprefix("- source: ").strip())
    return sources


def test_pr_verifier_imports_api_client_from_synced_manifest() -> None:
    tree = ast.parse(PR_VERIFIER.read_text(encoding="utf-8"))

    imports_api_client = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "scripts"
        and any(alias.name == "api_client" for alias in node.names)
        for node in ast.walk(tree)
    )

    assert imports_api_client, "pr_verifier.py should continue importing scripts.api_client"

    sources = _manifest_sources()
    assert "scripts/langchain/pr_verifier.py" in sources
    assert "scripts/api_client.py" in sources
