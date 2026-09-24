from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = (
    ROOT / ".github/workflows/agents-auto-pilot.yml",
    ROOT / "templates/consumer-repo/.github/workflows/agents-auto-pilot.yml",
)


def _format_block(text: str) -> str:
    return text.split("- name: Execute step - Format (inline)", 1)[1].split(
        "- name: Metrics - End format timer", 1
    )[0]


def test_contract_rejection_gets_exactly_one_retry_with_unchanged_input() -> None:
    for workflow in WORKFLOWS:
        block = _format_block(workflow.read_text(encoding="utf-8"))
        assert block.count("python scripts/langchain/issue_formatter.py") == 2
        assert block.count("--input-file /tmp/issue_body.md") == 2
        assert block.count("--json > /tmp/format_result.json") == 2
        assert "raise SystemExit(0 if result.get('needs_refinement') else 1)" in block
        assert "format_result_first.json" in block
        assert "after one retry" in block
        assert "first_validation_audit=" in block
        assert "retry_validation_audit=" in block


def test_exhausted_format_retry_pauses_without_inventing_human_authority() -> None:
    for workflow in WORKFLOWS:
        block = _format_block(workflow.read_text(encoding="utf-8"))
        refinement = block.split("if [ -f /tmp/needs_refinement ]; then", 1)[1]
        refinement = refinement.split("# Update issue body", 1)[0]
        assert "labels: ['agents:auto-pilot-pause']" in refinement
        assert "labels: ['needs-human'" not in refinement
        assert "Ownership remains with automation" in refinement
        assert "status:in-progress" in refinement
        assert "nonRoutingAgentLabels" in refinement
        assert "'agent:retry'" in refinement
        assert "label !== 'agent:auto'" in refinement
        assert "format_pause_wakeup=true" in refinement
        assert "stop_autopilot=true" in refinement


def test_pause_reports_outcomes_and_preserves_a_branch_for_safe_reuse() -> None:
    for workflow in WORKFLOWS:
        block = _format_block(workflow.read_text(encoding="utf-8"))
        assert "dispatched=0 formatted=0 paused=1 handed-to-human=0" in block
        assert "preserved for safe reuse" in block
        assert "deleteRef" not in block


def test_prepare_banners_expand_to_integer_step_numbers() -> None:
    for workflow in WORKFLOWS:
        text = workflow.read_text(encoding="utf-8")
        assert "Auto-pilot step $((STEP_COUNT + 1))" not in text
        assert text.count("STEP_NUMBER=$((STEP_COUNT + 1))") == 3
        assert text.count("Auto-pilot step ${STEP_NUMBER}") == 3


def test_healthy_format_path_still_publishes_and_dispatches() -> None:
    for workflow in WORKFLOWS:
        block = _format_block(workflow.read_text(encoding="utf-8"))
        assert "f.write(formatted)" in block
        assert "labels: ['agents:formatted']" in block
        assert "Formatting complete - continuing to next step" in block


def test_root_and_consumer_format_recovery_blocks_stay_aligned() -> None:
    root_block, consumer_block = (
        _format_block(workflow.read_text(encoding="utf-8")) for workflow in WORKFLOWS
    )
    assert root_block == consumer_block


def test_exhausted_format_pause_schedules_bounded_automation_wakeup_job() -> None:
    root_workflow = WORKFLOWS[0].read_text(encoding="utf-8")
    assert "format-pause-wakeup:" in root_workflow
    assert "sleep 1800" in root_workflow
    assert "format_pause_wakeup == 'true'" in root_workflow
    assert "workflow_id: 'agents-auto-pilot.yml'" in root_workflow
    assert "force_step: 'format'" in root_workflow
