"""README names every folder under .github/actions, and the top-level code homes."""

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


def test_readme_names_the_top_level_code_homes() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for home in ("tools/", "src/", "packages/", "evidence/"):
        assert f"`{home}`" in readme, home
