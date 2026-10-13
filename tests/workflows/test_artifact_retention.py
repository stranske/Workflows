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
                retention = (
                    _mapping(settings).get("retention-days")
                    if isinstance(settings, yaml.MappingNode)
                    else None
                )
                if (
                    not isinstance(retention, yaml.ScalarNode)
                    or retention.tag == "tag:yaml.org,2002:null"
                    or not retention.value.strip()
                ):
                    missing.append(
                        f"{path.relative_to(ROOT)}:{uses.start_mark.line + 1}: "
                        "actions/upload-artifact must set retention-days"
                    )
    assert uploads > 0, "No actions/upload-artifact steps were inspected"
    assert not missing, "\n".join(missing)


@pytest.mark.parametrize(
    "settings",
    [
        "",
        "        with: {}\n",
        "        with: null\n",
        "        with:\n          name: output\n",
        "        with:\n          retention-days:\n",
        "        with:\n          retention-days: null\n",
        "        with:\n          retention-days: ~\n",
        "        with:\n          retention-days: ''\n",
        "        with:\n          retention-days: '   '\n",
        "        with:\n          retention-days: []\n",
        "        with:\n          retention-days: {}\n",
    ],
    ids=[
        "no-with",
        "empty-with",
        "null-with",
        "missing-key",
        "implicit-null",
        "explicit-null",
        "tilde-null",
        "empty-string",
        "blank-string",
        "sequence",
        "mapping",
    ],
)
def test_missing_retention_value_reports_upload_location(tmp_path, monkeypatch, settings):
    workflow = tmp_path / ".github/workflows/missing-retention.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  upload:\n    steps:\n      - uses: actions/upload-artifact@v7\n" + settings,
        encoding="utf-8",
    )
    monkeypatch.setitem(globals(), "ROOT", tmp_path)

    with pytest.raises(AssertionError) as failure:
        test_every_upload_artifact_step_sets_retention_days()

    assert str(failure.value).splitlines()[0] == (
        ".github/workflows/missing-retention.yml:4: "
        "actions/upload-artifact must set retention-days"
    )


def test_retention_scanner_checks_every_file_job_and_upload(tmp_path, monkeypatch):
    workflows = tmp_path / ".github/workflows"
    workflows.mkdir(parents=True)
    (workflows / "a.yml").write_text(
        "jobs:\n"
        "  reusable:\n"
        "    uses: example/workflows/.github/workflows/build.yml@main\n"
        "  build:\n"
        "    steps:\n"
        "      - run: echo actions/upload-artifact\n"
        "      - uses: example/upload-artifact@v7\n"
        "      - uses: actions/upload-artifact@v7\n"
        "        with:\n"
        "          retention-days: 30\n"
        "  publish:\n"
        "    steps:\n"
        "      - uses: actions/upload-artifact@v7\n",
        encoding="utf-8",
    )
    (workflows / "z.yml").write_text(
        "jobs:\n"
        "  upload:\n"
        "    steps:\n"
        "      - uses: actions/upload-artifact@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          name: missing-retention\n"
        "      - uses: actions/upload-artifact@v7\n"
        "        with:\n"
        "          retention-days: '14'\n",
        encoding="utf-8",
    )
    monkeypatch.setitem(globals(), "ROOT", tmp_path)

    with pytest.raises(AssertionError) as failure:
        test_every_upload_artifact_step_sets_retention_days()

    assert [line.strip() for line in str(failure.value).splitlines()[:2]] == [
        ".github/workflows/a.yml:13: actions/upload-artifact must set retention-days",
        ".github/workflows/z.yml:4: actions/upload-artifact must set retention-days",
    ]


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
