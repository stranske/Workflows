"""Verify retained shebang-rejection Black, Ruff, and template receipts."""

import json
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/issue-3743/shebang-rejection"
CAPTURE = EVIDENCE / "capture_validation_run.py"
RUN = EVIDENCE / "validation-run"


def load_capture():
    return runpy.run_path(str(CAPTURE))


def test_validation_commands_use_documented_arguments():
    module = load_capture()
    black = Path("/usr/bin/black")
    ruff = Path("/usr/bin/ruff")
    python = Path("/usr/bin/python3")
    assert module["black_argv"](black) == [
        "/usr/bin/black",
        "--check",
        "--line-length",
        "100",
        "--exclude",
        r"(\.workflows-lib|node_modules)",
        ".",
    ]
    assert module["ruff_argv"](ruff)[:2] == ["/usr/bin/ruff", "check"]
    assert module["ruff_argv"](ruff)[2:] == list(module["FOCUSED_RUFF"])
    assert "scripts/check_deliberate_break.py" in module["FOCUSED_RUFF"]
    assert "templates/consumer-repo/scripts/check_deliberate_break.py" in module["FOCUSED_RUFF"]
    assert module["template_argv"](python) == [
        "/usr/bin/python3",
        "scripts/validate_template_completeness.py",
        "--workflows-dir",
        ".github/workflows",
        "--template-dir",
        "templates/consumer-repo/.github/workflows",
        "--manifest",
        ".github/sync-manifest.yml",
        "--source",
        "sync-manifest",
        "--strict",
    ]
    assert module["diff_argv"]() == ["git", "diff", "--check"]


def test_black_file_count_reads_the_unchanged_report():
    module = load_capture()
    stdout = "All done! ✨ 🍰 ✨\n754 files would be left unchanged.\n"
    assert module["black_file_count"](stdout) == 754
    assert module["black_file_count"]("1 file would be left unchanged.\n") == 1
    assert module["black_file_count"]("\n923 files would be left unchanged.\n") == 923
    assert module["black_file_count"]("would reformat file.py\n") is None


def test_retained_validation_receipts_record_exits_and_file_counts():
    module = load_capture()
    summary = module["validate_retained"](ROOT)
    assert summary["cwd"]
    assert summary["check_date"]
    assert summary["historical_unchanged"] is True
    assert summary["production_helpers"]["equal_each_other"] is True
    assert summary["production_helpers"]["root_equals_origin_main"] is True
    assert summary["production_helpers"]["template_equals_origin_main"] is True
    exits = {name: command["exit"] for name, command in summary["commands"].items()}
    assert exits == {"black": 0, "ruff": 0, "template": 0, "diffcheck": 0}
    counts = summary["measured_file_counts"]
    assert counts["black_files"] > 0
    assert counts["ruff_files"] == len(module["FOCUSED_RUFF"])
    assert counts["workflows_directory_yml"] > 0
    assert counts["template_directory_yml"] > 0
    assert counts["manifest_workflow_targets"] > 0
    assert counts["strict_validation_inputs"] == (
        counts["workflows_directory_yml"] + counts["template_directory_yml"] + 1
    )
    for tool in ("python", "black", "ruff"):
        recorded = summary["interpreters"][tool]["path"]
        assert recorded
        assert Path(recorded).is_absolute()
    readme = (RUN / "README.md").read_text(encoding="utf-8")
    assert "Historical" in readme
    assert summary["interpreters"]["python"]["path"] in readme
    assert str(counts["black_files"]) in readme
    stored = json.loads((RUN / "summary.json").read_text(encoding="utf-8"))
    assert stored["measured_file_counts"] == counts
