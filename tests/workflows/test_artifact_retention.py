"""Keep direct workflow uploads independent of the repository retention default."""

from pathlib import Path

import pytest
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


def test_codex_retention_deletion_reports_file_and_line(tmp_path, monkeypatch):
    """Exercise the named scanner against a copy of the production workflow."""
    relative_path = Path(".github/workflows/reusable-codex-run.yml")
    source_path = ROOT / relative_path
    original = source_path.read_bytes()
    retention_line = b"          retention-days: 14\n"
    assert original.count(retention_line) == 1, "Expected one Codex output retention setting"

    copied_path = tmp_path / relative_path
    copied_path.parent.mkdir(parents=True)
    copied_path.write_bytes(original)
    monkeypatch.setitem(globals(), "ROOT", tmp_path)

    # The unchanged production copy must pass before exercising the deletion.
    test_every_upload_artifact_step_sets_retention_days()
    copied_path.write_bytes(original.replace(retention_line, b"", 1))
    with pytest.raises(AssertionError) as failure:
        test_every_upload_artifact_step_sets_retention_days()
    assert str(failure.value).splitlines()[0] == (
        ".github/workflows/reusable-codex-run.yml:1818: "
        "actions/upload-artifact must set retention-days"
    )

    copied_path.write_bytes(original)
    assert copied_path.read_bytes() == original
    test_every_upload_artifact_step_sets_retention_days()
    assert source_path.read_bytes() == original, "Production workflow must remain unchanged"
