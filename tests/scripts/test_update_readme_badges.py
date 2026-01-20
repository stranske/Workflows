from __future__ import annotations

from pathlib import Path

from scripts import update_readme_badges


def test_updates_badge_block(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Title",
                "",
                "<!-- METRICS_BADGES_START -->",
                "old badges",
                "<!-- METRICS_BADGES_END -->",
                "",
                "Footer",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = update_readme_badges.main(
        [
            "--readme-path",
            str(readme),
            "--badge-endpoint-base",
            "https://example.com/badges",
        ]
    )

    assert exit_code == 0
    updated = readme.read_text(encoding="utf-8")
    assert "old badges" not in updated
    assert "Success Rate" in updated
    assert "Footer" in updated


def test_requires_markers(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# Title\n", encoding="utf-8")

    exit_code = update_readme_badges.main(
        [
            "--readme-path",
            str(readme),
            "--badge-endpoint-base",
            "https://example.com/badges",
        ]
    )

    assert exit_code == 1
    assert readme.read_text(encoding="utf-8") == "# Title\n"


def test_no_change_when_same_block(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    links = update_readme_badges._build_badge_links("https://example.com/badges")
    block = update_readme_badges._render_badge_block(links)
    readme.write_text(
        "\n".join(
            [
                "# Title",
                "",
                "<!-- METRICS_BADGES_START -->",
                block,
                "<!-- METRICS_BADGES_END -->",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = update_readme_badges.main(
        [
            "--readme-path",
            str(readme),
            "--badge-endpoint-base",
            "https://example.com/badges",
        ]
    )

    assert exit_code == 0
    assert readme.read_text(encoding="utf-8").count("METRICS_BADGES_START") == 1
