"""Keep direct workflow uploads independent of the repository retention default."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _mapping(node):
    assert isinstance(node, yaml.MappingNode), "Expected a workflow YAML mapping"
    return {key.value: value for key, value in node.value}


def test_every_upload_artifact_step_sets_retention_days():
    uploads = 0
    missing = []
    for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        workflow = _mapping(yaml.compose(path.read_text(encoding="utf-8")))
        for job in _mapping(workflow["jobs"]).values():
            steps = _mapping(job).get("steps")
            if steps is None:  # Reusable-workflow jobs have no steps.
                continue
            for node in steps.value:
                step = _mapping(node)
                uses = step.get("uses")
                if uses is None or uses.value.split("@", 1)[0] != "actions/upload-artifact":
                    continue
                uploads += 1
                settings = step.get("with")
                retention = _mapping(settings).get("retention-days") if settings else None
                if not isinstance(retention, yaml.ScalarNode) or not retention.value.strip():
                    missing.append(
                        f"{path.relative_to(ROOT)}:{uses.start_mark.line + 1}: "
                        "actions/upload-artifact must set retention-days"
                    )
    assert uploads > 0, "No actions/upload-artifact steps were inspected"
    assert not missing, "\n".join(missing)
