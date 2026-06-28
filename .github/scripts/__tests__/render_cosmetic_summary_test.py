import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "render_cosmetic_summary.py"
SPEC = importlib.util.spec_from_file_location("render_cosmetic_summary", SCRIPT)
render_cosmetic_summary = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(render_cosmetic_summary)


def test_build_summary_lines_with_no_changes():
    lines = render_cosmetic_summary.build_summary_lines({"status": "clean"})

    assert lines == [
        "- Status: **clean**",
        "- No file changes detected.",
    ]


def test_build_summary_lines_with_changed_files_and_pr_url():
    data = {
        "status": "changed",
        "changed_files": [
            ".github/workflows/maint-45-cosmetic-repair.yml",
            "scripts/ci_cosmetic_repair.py",
        ],
        "pr_url": "https://github.com/stranske/Workflows/pull/123",
    }

    lines = render_cosmetic_summary.build_summary_lines(data)

    assert lines == [
        "- Status: **changed**",
        "- Changed files (2):",
        "  - `.github/workflows/maint-45-cosmetic-repair.yml`",
        "  - `scripts/ci_cosmetic_repair.py`",
        "- PR: https://github.com/stranske/Workflows/pull/123",
    ]


def test_build_summary_lines_with_guarded_and_unguarded_instructions():
    data = {
        "status": "instructions",
        "instructions": [
            {
                "kind": "replace",
                "path": ".github/workflows/pr-00-gate.yml",
                "guard": "guarded",
            },
            {
                "kind": "append",
                "path": "README.md",
            },
        ],
    }

    lines = render_cosmetic_summary.build_summary_lines(data)

    assert lines == [
        "- Status: **instructions**",
        "- No file changes detected.",
        "- Instructions processed:",
        "  - `replace` \u2192 `.github/workflows/pr-00-gate.yml` (guarded)",
        "  - `append` \u2192 `README.md`",
    ]


def test_read_summary_parses_valid_json(tmp_path):
    summary_path = tmp_path / "summary.json"
    summary = {
        "status": "changed",
        "changed_files": ["pyproject.toml"],
    }
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    assert render_cosmetic_summary.read_summary(summary_path) == summary


def test_read_summary_raises_system_exit_for_invalid_json(tmp_path):
    summary_path = tmp_path / "summary.json"
    summary_path.write_text("{invalid json", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        render_cosmetic_summary.read_summary(summary_path)

    message = str(excinfo.value)
    assert f"Failed to parse {summary_path}:" in message
    assert "Expecting property name enclosed in double quotes" in message


def test_main_prints_rendered_summary_lines(tmp_path, monkeypatch, capsys):
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "status": "changed",
                "changed_files": ["README.md"],
                "pr_url": "https://github.com/stranske/Workflows/pull/2680",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        ["render_cosmetic_summary.py", str(summary_path)],
    )

    render_cosmetic_summary.main()

    assert capsys.readouterr().out.splitlines() == [
        "- Status: **changed**",
        "- Changed files (1):",
        "  - `README.md`",
        "- PR: https://github.com/stranske/Workflows/pull/2680",
    ]
