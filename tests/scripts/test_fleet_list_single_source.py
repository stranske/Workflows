from __future__ import annotations

import ast
from pathlib import Path

from scripts import cleanup_labels, langsmith_fleet
from scripts.list_registered_consumer_repos import extract_repos

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / ".github/workflows/maint-68-sync-consumer-repos.yml"


def _assignment_uses_extract_repos(path: Path, target_name: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        value: ast.expr | None = None
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == target_name for target in node.targets
            )
        ) or (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == target_name
        ):
            value = node.value
        if value is not None and any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "extract_repos"
            for child in ast.walk(value)
        ):
            return True
    return False


def test_no_second_consumer_repo_literal() -> None:
    registered = extract_repos(MANIFEST)

    assert MANIFEST.name == "maint-68-sync-consumer-repos.yml"
    assert len(registered) >= 10
    assert registered == cleanup_labels.CONSUMER_REPOS
    assert set(registered) == langsmith_fleet.MANAGED_CONSUMER_REPOS
    assert _assignment_uses_extract_repos(ROOT / "scripts/cleanup_labels.py", "CONSUMER_REPOS")
    assert _assignment_uses_extract_repos(
        ROOT / "scripts/langsmith_fleet.py", "MANAGED_CONSUMER_REPOS"
    )
