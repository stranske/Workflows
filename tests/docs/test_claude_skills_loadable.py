"""Every folder under .claude/skills holds a loadable SKILL.md.

A skill is only discovered from a file named exactly SKILL.md whose frontmatter has a `name`
matching its folder and a non-empty `description`. langsmith-integration shipped as `skill.md`
with no frontmatter, so it was never loadable.
"""

from pathlib import Path

import yaml

SKILLS_DIR = Path(__file__).resolve().parents[2] / ".claude" / "skills"


def _skill_dirs() -> list[Path]:
    return sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())


def test_there_are_skills_to_check() -> None:
    assert {p.name for p in _skill_dirs()} >= {"fleet-review", "langsmith-integration"}


def test_every_skill_folder_has_a_skill_md_with_frontmatter() -> None:
    for folder in _skill_dirs():
        names = {p.name for p in folder.iterdir() if p.is_file()}
        assert "SKILL.md" in names, f"{folder.name}: SKILL.md missing (found {sorted(names)})"
        text = (folder / "SKILL.md").read_text(encoding="utf-8")
        assert text.startswith("---\n"), f"{folder.name}: no frontmatter"
        frontmatter = yaml.safe_load(text.split("---\n", 2)[1])
        assert frontmatter.get("name") == folder.name, folder.name
        assert str(frontmatter.get("description", "")).strip(), f"{folder.name}: no description"
