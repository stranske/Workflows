"""README names every folder under .github/actions.

The top-level code homes are listed in docs/STRUCTURE.md's directory index
(tests/docs/test_structure_directory_index.py), the one layout map.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_readme_lists_every_composite_action_folder() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    missing = [
        folder.name
        for folder in sorted((ROOT / ".github" / "actions").iterdir())
        if folder.is_dir() and f"`{folder.name}/`" not in readme
    ]
    assert missing == [], f"README.md does not list: {missing}"
