from __future__ import annotations

from scripts.check_agents_md_freshness import check_agents_md


def _agents_md(*refs: str) -> str:
    lines = [
        "# AGENTS.md",
        "<!-- BEGIN orch-playbook -->",
        "<!-- exported by repo_knowledge.py; owner: Orchestrator; freshness owner: keepalive -->",
        "## Orchestrator Repo Playbook (stranske/Example)",
    ]
    lines.extend(f"- Keep `{ref}` fresh." for ref in refs)
    lines.append("<!-- END orch-playbook -->")
    return "\n".join(lines) + "\n"


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
