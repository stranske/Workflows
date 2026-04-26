import json
from pathlib import Path

from scripts import check_workflow_action_pins

PINNED_CHECKOUT = "de0fac2e4500dabe0009e67214ff5f5447ce83dd"
PINNED_GITHUB_SCRIPT = "3a2844b7e9c422d3c10d287c895573f7108da1b3"


def test_build_report_accepts_sha_pinned_actions_with_version_comments(tmp_path: Path) -> None:
    workflow = tmp_path / "workflow.yml"
    workflow.write_text(
        f"""
name: pinned
on: push
jobs:
  test:
    steps:
      - uses: actions/checkout@{PINNED_CHECKOUT} # v6
      - name: Script
        uses: actions/github-script@{PINNED_GITHUB_SCRIPT} # v9
""",
        encoding="utf-8",
    )

    report = check_workflow_action_pins.build_report([workflow])

    assert report["status"] == "pass"
    assert report["checked_uses_count"] == 2
    assert report["issues"] == []


def test_build_report_flags_floating_action_refs(tmp_path: Path) -> None:
    workflow = tmp_path / "workflow.yml"
    workflow.write_text(
        """
name: floating
on: push
jobs:
  test:
    steps:
      - uses: actions/checkout@v6
""",
        encoding="utf-8",
    )

    report = check_workflow_action_pins.build_report([workflow])

    assert report["status"] == "fail"
    assert report["issues"][0]["reason"] == "floating-ref"
    assert report["issues"][0]["uses"] == "actions/checkout@v6"


def test_build_report_flags_sha_without_readable_version_comment(tmp_path: Path) -> None:
    workflow = tmp_path / "workflow.yml"
    workflow.write_text(
        f"""
name: missing-comment
on: push
jobs:
  test:
    steps:
      - uses: actions/checkout@{PINNED_CHECKOUT}
""",
        encoding="utf-8",
    )

    report = check_workflow_action_pins.build_report([workflow])

    assert report["status"] == "fail"
    assert report["issues"][0]["reason"] == "missing-version-comment"


def test_build_report_ignores_local_actions_and_reusable_workflows(tmp_path: Path) -> None:
    workflow = tmp_path / "workflow.yml"
    workflow.write_text(
        """
name: ignored
on: push
jobs:
  test:
    steps:
      - uses: ./.github/actions/setup-api-client
  reusable:
    uses: stranske/Workflows/.github/workflows/reusable-codex-run.yml@main
""",
        encoding="utf-8",
    )

    report = check_workflow_action_pins.build_report([workflow])

    assert report["status"] == "pass"
    assert report["checked_uses_count"] == 0


def test_main_writes_machine_readable_outputs(tmp_path: Path) -> None:
    workflow = tmp_path / "workflow.yml"
    output_json = tmp_path / "report.json"
    output_md = tmp_path / "report.md"
    workflow.write_text(
        f"""
name: pinned
on: push
jobs:
  test:
    steps:
      - uses: actions/checkout@{PINNED_CHECKOUT} # v6
""",
        encoding="utf-8",
    )

    exit_code = check_workflow_action_pins.main(
        [
            str(workflow),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ]
    )

    assert exit_code == 0
    assert json.loads(output_json.read_text(encoding="utf-8"))["schema"] == (
        "workflow-action-pins/v1"
    )
    assert "Workflow Action Pin Report" in output_md.read_text(encoding="utf-8")


def test_current_consumer_template_actions_are_pinned() -> None:
    report = check_workflow_action_pins.build_report(
        [
            Path(".github/workflows/agents-verify-to-new-pr.yml"),
            Path("templates/consumer-repo/.github/workflows"),
        ]
    )

    assert report["status"] == "pass"
    assert report["checked_file_count"] >= 30
    assert report["checked_uses_count"] >= 1
