"""Verify delivered shebang-rejection archives and current input bindings."""

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/issue-3743/shebang-rejection"
VERIFIER = EVIDENCE / "verify_archives.py"
NOTE = EVIDENCE / "current-acceptance.md"


def load_verifier():
    return runpy.run_path(str(VERIFIER))


def test_delivered_archives_and_current_bindings_match_the_note():
    module = load_verifier()
    report = module["validate"](ROOT)
    archives = report["archives"]
    assert [item["kind"] for item in archives] == [
        "historical",
        "historical",
        "historical",
        "current",
    ]
    assert all(item["verified"] for item in archives)
    assert all(item["member_mismatches"] == [] for item in archives)
    assert all(item["members"] > 0 for item in archives)
    assert report["problems"] == []
    assert report["historical_input_mismatches"] > 0
    assert report["matched_comparison"] == {
        "added": 8,
        "removed": 0,
        "changed": 0,
        "universes_identical": True,
        "exclusions": 0,
        "line_regressions": 0,
        "branch_regressions": 0,
    }
    note = NOTE.read_text(encoding="utf-8")
    assert note == module["render"](report)
    assert "Historical receipts" in note
    assert "are not current acceptance" in note
    assert "Current acceptance" in note
    for path in report["interpreters"].values():
        assert path in note
        assert Path(path).is_absolute()
    counts = report["measured_file_counts"]
    assert counts["black_files"] > 0
    assert counts["ruff_files"] > 0
    assert counts["workflows_directory_yml"] > 0
    assert counts["template_directory_yml"] > 0
    assert counts["manifest_workflow_targets"] > 0
    assert counts["strict_validation_inputs"] == (
        counts["workflows_directory_yml"] + counts["template_directory_yml"] + 1
    )
    for value in counts.values():
        assert str(value) in note
