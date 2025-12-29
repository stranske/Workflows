from __future__ import annotations

from pathlib import Path

import yaml

DOC_PATH = Path("docs/ci/WORKFLOW_OUTPUTS.md")
WORKFLOW_DIR = Path(".github/workflows")

REFERENCE_START = "<!-- OUTPUT-REFERENCE-START -->"
REFERENCE_END = "<!-- OUTPUT-REFERENCE-END -->"
NONE_START = "<!-- OUTPUT-NONE-START -->"
NONE_END = "<!-- OUTPUT-NONE-END -->"


def _load_workflow(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _workflow_outputs(workflow: dict) -> dict:
    triggers = workflow.get("on") or workflow.get(True) or {}
    workflow_call = triggers.get("workflow_call") or {}
    return workflow_call.get("outputs") or {}


def _extract_block(text: str, start: str, end: str) -> str:
    if start not in text or end not in text:
        raise AssertionError(f"Missing output markers: {start} .. {end}")
    return text.split(start, 1)[1].split(end, 1)[0]


def _parse_reference_table(text: str) -> dict[str, set[str]]:
    block = _extract_block(text, REFERENCE_START, REFERENCE_END)
    outputs: dict[str, set[str]] = {}
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        if "Workflow" in line or line.startswith("| ---"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        assert len(cells) >= 5, f"Expected 5 columns in outputs table, got: {cells}"
        workflow, output, output_type, description, example = cells[:5]
        assert workflow, "Workflow name is required for output rows"
        assert output, f"Output name missing for workflow {workflow}"
        assert output_type, f"Type missing for {workflow}.{output}"
        assert description, f"Description missing for {workflow}.{output}"
        assert example, f"Example missing for {workflow}.{output}"
        example_value = example.strip("`")
        output_name = output.strip("`")
        assert (
            "needs." in example_value and ".outputs." in example_value
        ), f"Example should use needs.<job>.outputs.<name> for {workflow}.{output}"
        assert (
            f"outputs.{output_name}" in example_value
        ), f"Example should reference outputs.{output_name} for {workflow}"
        outputs.setdefault(workflow.strip("`"), set()).add(output_name)
    return outputs


def _parse_no_outputs_list(text: str) -> set[str]:
    block = _extract_block(text, NONE_START, NONE_END)
    workflows: set[str] = set()
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("- `"):
            continue
        name = line.split("`", 2)[1]
        if name:
            workflows.add(name)
    return workflows


def test_reusable_workflow_outputs_documented() -> None:
    assert DOC_PATH.exists(), "Workflow outputs reference doc must exist"
    text = DOC_PATH.read_text(encoding="utf-8")

    documented_outputs = _parse_reference_table(text)
    no_output_workflows = _parse_no_outputs_list(text)

    workflows = sorted(WORKFLOW_DIR.glob("reusable-*.yml"))
    assert workflows, "Expected reusable workflows to exist"

    reusable_names = {path.name for path in workflows}
    assert set(documented_outputs) <= reusable_names, "Doc lists unknown workflows"
    assert no_output_workflows <= reusable_names, "Doc lists unknown no-output workflows"

    for path in workflows:
        workflow = _load_workflow(path)
        outputs = _workflow_outputs(workflow)
        if outputs:
            assert path.name in documented_outputs, f"{path.name} outputs missing from docs"
            assert set(outputs.keys()) == documented_outputs[path.name]
        else:
            assert (
                path.name in no_output_workflows
            ), f"{path.name} should be listed as having no outputs"

    assert documented_outputs.keys().isdisjoint(
        no_output_workflows
    ), "Workflows should not appear in both output lists"
