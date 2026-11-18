"""Sealed evidence describes the captured tree even after workflow additions."""

import runpy
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path("docs/evidence/issue-3743/shebang-rejection")


def test_an_added_workflow_file_does_not_fail_the_sealed_evidence(tmp_path):
    relocated = tmp_path / "repository"
    shutil.copytree(
        ROOT,
        relocated,
        ignore=shutil.ignore_patterns(
            ".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache"
        ),
    )
    probe = relocated / ".github/workflows/zz-probe.yml"
    probe.write_text("name: Evidence inventory probe\non: workflow_dispatch\njobs: {}\n")

    verifier = runpy.run_path(str(relocated / EVIDENCE / "verify_archives.py"))
    assert verifier["validate"](relocated)["problems"] == []
    capture = runpy.run_path(str(relocated / EVIDENCE / "capture_validation_run.py"))
    assert capture["validate_retained"](relocated)["measured_file_counts"]
