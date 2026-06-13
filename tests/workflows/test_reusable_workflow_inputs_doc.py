"""Guard that the entry-point docs only document real reusable-10 inputs/secrets.

Sibling to ``test_reusable_workflow_outputs_doc.py``. The hand-written input and
secret tables/examples in ``docs/USAGE.md`` and ``docs/INTEGRATION_GUIDE.md``
have no automated guard, so they drifted to document ``run-tests`` / ``run-lint``
/ ``run-typecheck`` / ``CODECOV_TOKEN`` etc. that do not exist on
``reusable-10-ci-python.yml`` -- a copy-paste of either example yields a
``startup_failure``. This test asserts every documented input/secret name is a
subset of the workflow's real ``on.workflow_call.inputs``/``secrets`` keys.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
USAGE_PATH = REPO_ROOT / "docs/USAGE.md"
INTEGRATION_GUIDE_PATH = REPO_ROOT / "docs/INTEGRATION_GUIDE.md"
WORKFLOW_PATH = REPO_ROOT / ".github/workflows/reusable-10-ci-python.yml"

INPUTS_START = "<!-- REUSABLE-10-INPUTS-START -->"
INPUTS_END = "<!-- REUSABLE-10-INPUTS-END -->"
SECRETS_START = "<!-- REUSABLE-10-SECRETS-START -->"
SECRETS_END = "<!-- REUSABLE-10-SECRETS-END -->"
FULL_CI_MARKER = "### Example: Full CI"


def _load_workflow(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _workflow_call(workflow: dict) -> dict:
    # The `on` key parses as the Python boolean True under PyYAML; mirror the
    # idiom used by tests/workflows/test_reusable_workflow_outputs_doc.py.
    triggers = workflow.get("on") or workflow.get(True) or {}
    return triggers.get("workflow_call") or {}


def _real_inputs(workflow: dict) -> set[str]:
    return set((_workflow_call(workflow).get("inputs") or {}).keys())


def _real_secrets(workflow: dict) -> set[str]:
    return set((_workflow_call(workflow).get("secrets") or {}).keys())


def _extract_block(text: str, start: str, end: str) -> str:
    assert start in text and end in text, f"Missing doc markers: {start} .. {end}"
    return text.split(start, 1)[1].split(end, 1)[0]


def _fenced_yaml_blocks(text: str) -> list[dict]:
    blocks: list[dict] = []
    for part in text.split("```yaml")[1:]:
        body = part.split("```", 1)[0]
        try:
            data = yaml.safe_load(body)
        except yaml.YAMLError:
            continue
        if isinstance(data, dict):
            blocks.append(data)
    return blocks


def _job_keys(data: dict, section: str) -> set[str]:
    names: set[str] = set()
    for job in (data.get("jobs") or {}).values():
        if isinstance(job, dict):
            names.update((job.get(section) or {}).keys())
    return names


def _documented_table_inputs(usage_text: str) -> set[str]:
    block = _extract_block(usage_text, INPUTS_START, INPUTS_END)
    names: set[str] = set()
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        if line.startswith("|---") or line.startswith("| ---"):
            continue
        first = line.strip("|").split("|", 1)[0].strip()
        if not first or first.lower() == "input":
            continue
        names.add(first.strip("`"))
    return names


def _documented_secret_keys(usage_text: str) -> set[str]:
    block = _extract_block(usage_text, SECRETS_START, SECRETS_END)
    names: set[str] = set()
    for data in _fenced_yaml_blocks(block):
        names.update(_job_keys(data, "secrets"))
    return names


def _full_ci_example(guide_text: str) -> dict:
    assert FULL_CI_MARKER in guide_text, "INTEGRATION_GUIDE missing 'Example: Full CI'"
    after = guide_text.split(FULL_CI_MARKER, 1)[1]
    blocks = _fenced_yaml_blocks(after)
    assert blocks, "Full CI example fenced yaml block not found"
    return blocks[0]


def test_workflow_call_surface_is_nonempty() -> None:
    workflow = _load_workflow(WORKFLOW_PATH)
    assert _real_inputs(workflow), "reusable-10-ci-python.yml should declare workflow_call inputs"
    assert _real_secrets(workflow), "reusable-10-ci-python.yml should declare workflow_call secrets"


def test_usage_input_table_inputs_exist() -> None:
    workflow = _load_workflow(WORKFLOW_PATH)
    real_inputs = _real_inputs(workflow)
    documented = _documented_table_inputs(USAGE_PATH.read_text(encoding="utf-8"))
    assert documented, "Expected documented reusable-10 input rows in USAGE.md"
    unknown = documented - real_inputs
    assert not unknown, f"USAGE.md documents nonexistent reusable-10 inputs: {sorted(unknown)}"


def test_usage_secret_example_secrets_exist() -> None:
    workflow = _load_workflow(WORKFLOW_PATH)
    real_secrets = _real_secrets(workflow)
    documented = _documented_secret_keys(USAGE_PATH.read_text(encoding="utf-8"))
    assert documented, "Expected documented reusable-10 secrets in USAGE.md"
    unknown = documented - real_secrets
    assert not unknown, f"USAGE.md documents nonexistent reusable-10 secrets: {sorted(unknown)}"


def test_integration_guide_full_ci_example_uses_real_names() -> None:
    workflow = _load_workflow(WORKFLOW_PATH)
    real_inputs = _real_inputs(workflow)
    real_secrets = _real_secrets(workflow)
    example = _full_ci_example(INTEGRATION_GUIDE_PATH.read_text(encoding="utf-8"))

    example_inputs = _job_keys(example, "with")
    assert example_inputs, "Full CI example should pass at least one input via `with`"
    unknown_inputs = example_inputs - real_inputs
    assert (
        not unknown_inputs
    ), f"INTEGRATION_GUIDE Full CI example uses nonexistent inputs: {sorted(unknown_inputs)}"

    example_secrets = _job_keys(example, "secrets")
    assert example_secrets, "Full CI example should pass at least one secret"
    unknown_secrets = example_secrets - real_secrets
    assert (
        not unknown_secrets
    ), f"INTEGRATION_GUIDE Full CI example uses nonexistent secrets: {sorted(unknown_secrets)}"
