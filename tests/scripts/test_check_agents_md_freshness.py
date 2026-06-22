from __future__ import annotations

from scripts.check_agents_md_freshness import check_agents_md


def _agents_md(*refs: str, prefix: str = "") -> str:
    lines = [
        "# AGENTS.md",
        "<!-- BEGIN orch-playbook -->",
        "<!-- exported by repo_knowledge.py; owner: Orchestrator; freshness owner: keepalive -->",
        "## Orchestrator Repo Playbook (stranske/Example)",
    ]
    lines.extend(f"- Keep `{ref}` fresh." for ref in refs)
    lines.append("<!-- END orch-playbook -->")
    return prefix + "\n".join(lines) + "\n"


def test_dead_path_flagged(tmp_path):
    (tmp_path / "AGENTS.md").write_text(_agents_md("docs/missing.md"), encoding="utf-8")

    findings = check_agents_md(tmp_path)

    assert [finding.as_dict() for finding in findings] == [
        {
            "kind": "path",
            "value": "docs/missing.md",
            "message": "referenced path not found: docs/missing.md",
        }
    ]


def test_existing_path_passes(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("ok\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(_agents_md("docs/guide.md"), encoding="utf-8")

    assert check_agents_md(tmp_path) == []


def test_command_ref_with_equals_path_arg_is_checked(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "x.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        _agents_md("python tools/x.py --config=docs/missing.md"),
        encoding="utf-8",
    )

    findings = check_agents_md(tmp_path)

    assert [finding.as_dict() for finding in findings] == [
        {
            "kind": "path",
            "value": "docs/missing.md",
            "message": "referenced path not found: docs/missing.md",
        }
    ]


def test_managed_section_ignores_stray_end_marker_before_start(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("ok\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        _agents_md("docs/guide.md", prefix="<!-- END orch-playbook -->\n"),
        encoding="utf-8",
    )

    assert check_agents_md(tmp_path) == []
