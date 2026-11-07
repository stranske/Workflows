"""Static checks for the hosted evaluation receipt boundary.

The reusable verifier workflow has no consumer-template copy. These checks
parse that source, syntax-check every authored shell step, and keep the
pre-existing validator warnings from hiding a new overlength line in the
receipt boundary.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml
from scripts.validate_template_completeness import WORKFLOWS_ONLY, is_consumer_workflow
from scripts.validate_workflow_yaml import (
    check_line_length,
    check_multiline_conditions,
    check_yaml_syntax,
)

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/reusable-agents-verifier.yml"
TEMPLATE = ROOT / "templates/consumer-repo/.github/workflows/reusable-agents-verifier.yml"
PRE_CORRECTION_SHELL = (
    ROOT / "tests/fixtures/verifier_evaluation_transport/pre_correction_llm_evaluate.sh"
)
LINE_LIMIT = 100

# Source lines that belong to this receipt boundary. None of them may exceed
# the workflow line limit, and none may be one of the legacy warnings.
RECEIPT_BOUNDARY_MARKERS = (
    "receipt_exit=0",
    "PYCHECK",
    "PYFALLBACK",
    "original_redacted",
    "retained_redacted",
    "bounded_diagnostic",
    "RECEIPT_FAILURE_STATUS",
    "Require evaluation execution evidence",
    "Missing evaluation evidence file",
    "Evaluation execution receipt is empty",
    "receipt_generation_failed",
    "receipt_validation_failed",
)

# Warnings already present before the receipt change. They stay visible.
LEGACY_OVERLENGTH_LINES = (
    (
        "        description: 'Recover retained output: JSON run_id/run_attempt/"
        "artifact_id selectors; never invokes a provider'"
    ),
    (
        "        if: steps.context.outputs.should_run == 'true' && "
        "(inputs.mode == 'compare' || inputs.mode == 'evaluate')"
    ),
)


def _neutralize_expressions(script: str) -> str:
    return re.sub(r"\$\{\{.*?\}\}", "EXPR", script, flags=re.S)


def _bash_syntax(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-n"],
        input=_neutralize_expressions(script),
        text=True,
        capture_output=True,
        check=False,
    )


def test_verifier_workflow_yaml_and_authored_shell_parse() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert check_yaml_syntax(WORKFLOW) == []
    steps = workflow["jobs"]["verifier"]["steps"]
    names = {step.get("name") for step in steps}
    assert "Run LLM evaluation" in names
    assert "Require evaluation execution evidence" in names
    assert any(step.get("id") == "llm_evaluate" for step in steps)

    run_steps = [step for step in steps if isinstance(step.get("run"), str)]
    assert len(run_steps) >= 20
    for step in run_steps:
        result = _bash_syntax(step["run"])
        name = step.get("id") or step.get("name")
        assert result.returncode == 0, f"{name}\n{result.stderr}"

    fixture = _bash_syntax(PRE_CORRECTION_SHELL.read_text(encoding="utf-8"))
    assert fixture.returncode == 0, fixture.stderr


def test_receipt_boundary_adds_no_overlength_lines() -> None:
    length_issues = check_line_length(WORKFLOW, max_length=LINE_LIMIT)
    format_issues = check_multiline_conditions(WORKFLOW)
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    overlength = {lines[number - 1] for number, _message in length_issues}

    assert LEGACY_OVERLENGTH_LINES[0] in overlength
    assert LEGACY_OVERLENGTH_LINES[1] in overlength
    assert any(
        lines[number - 1] == LEGACY_OVERLENGTH_LINES[1] for number, _message in format_issues
    )

    for marker in RECEIPT_BOUNDARY_MARKERS:
        matched = [line for line in lines if marker in line]
        assert matched, marker
        for line in matched:
            assert len(line.rstrip()) <= LINE_LIMIT, line
            assert line not in overlength


def test_reusable_verifier_stays_out_of_consumer_template_parity() -> None:
    assert WORKFLOW.name in WORKFLOWS_ONLY
    assert is_consumer_workflow(WORKFLOW) is False
    template_dir = TEMPLATE.parent
    assert template_dir.is_dir()
    assert not TEMPLATE.exists()
    manifest = (ROOT / ".github/sync-manifest.yml").read_text(encoding="utf-8")
    assert "reusable-agents-verifier.yml" not in manifest


def test_receipt_sources_have_no_conflict_markers() -> None:
    paths = (
        WORKFLOW,
        PRE_CORRECTION_SHELL,
        ROOT / "tests/workflows/test_verifier_evaluation_transport.py",
        ROOT / "tests/workflows/test_verifier_evaluation_pre_correction.py",
        ROOT / "docs/WORKFLOW_GUIDE.md",
    )
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "<<<<<<<" not in text, path
        assert ">>>>>>>" not in text, path
