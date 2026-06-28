from pathlib import Path

from scripts import workflow_validator as validator


def test_load_workflow_handles_yaml_edge_cases(tmp_path: Path) -> None:
    valid = tmp_path / "valid.yml"
    valid.write_text(
        """
name: Synthetic
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
""",
        encoding="utf-8",
    )

    invalid = tmp_path / "invalid.yml"
    invalid.write_text("name: [unterminated\n", encoding="utf-8")

    non_mapping = tmp_path / "non-mapping.yml"
    non_mapping.write_text("- not\n- a\n- mapping\n", encoding="utf-8")

    assert validator.load_workflow(str(valid))["name"] == "Synthetic"
    assert validator.load_workflow(str(invalid)) is None
    assert validator.load_workflow(str(tmp_path / "missing.yml")) is None
    assert validator.load_workflow(str(non_mapping)) is None


def test_deprecated_actions_reports_explicit_and_fallback_step_names() -> None:
    workflow = {
        "jobs": {
            "lint": {
                "steps": [
                    {"uses": "actions/checkout@v2"},
                    {"name": "Fetch report", "uses": "actions/download-artifact@v3"},
                    {"name": "Current checkout", "uses": "actions/checkout@v4"},
                ]
            }
        }
    }

    assert validator.check_deprecated_actions(workflow) == [
        ("lint", "step-0", "Deprecated action actions/checkout@v2, use actions/checkout@v4"),
        (
            "lint",
            "Fetch report",
            "Deprecated action actions/download-artifact@v3, use actions/download-artifact@v7",
        ),
    ]


def test_missing_timeout_detection_keeps_multiple_job_names() -> None:
    workflow = {
        "jobs": {
            "build": {"steps": []},
            "test": {"timeout-minutes": 20, "steps": []},
            "package": {"runs-on": "ubuntu-latest"},
        }
    }

    assert validator.check_missing_timeout(workflow) == ["build", "package"]


def test_upload_artifact_major_detection_allows_expected_and_flags_others() -> None:
    workflow = {
        "jobs": {
            "artifacts": {
                "steps": [
                    {"name": "Expected", "uses": "actions/upload-artifact@v7"},
                    {"name": "Expected patch", "uses": "actions/upload-artifact@v7.2.1"},
                    {"name": "Old major", "uses": "actions/upload-artifact@v4"},
                    {"name": "Future major", "uses": "actions/upload-artifact@v8-beta"},
                    {"name": "Other action", "uses": "actions/download-artifact@v7"},
                ]
            }
        }
    }

    assert validator.check_upload_artifact_major(workflow) == [
        ("artifacts", "Old major", "actions/upload-artifact@v4 should use v7"),
        ("artifacts", "Future major", "actions/upload-artifact@v8 should use v7"),
    ]


def test_hardcoded_secret_detection_reports_synthetic_tokens() -> None:
    workflow = {
        "jobs": {
            "audit": {
                "env": {
                    "GITHUB_PAT": "ghp_" + ("A" * 36),
                    "APP_TOKEN": "ghs_" + ("B" * 36),
                    "API_KEY": "sk-" + ("C" * 48),
                },
                "steps": [{"run": "echo redacted"}],
            }
        }
    }

    descriptions = {description for _, description in validator.check_hardcoded_secrets(workflow)}

    assert descriptions == {
        "Possible API key",
        "Possible GitHub App token",
        "Possible GitHub PAT",
    }


def test_unsafe_string_interpolation_reports_only_unsafe_synthetic_steps() -> None:
    workflow = {
        "env": {"STATIC_VALUE": "safe-literal"},
        "jobs": {
            "analyze": {
                "steps": [
                    {
                        "name": "Unsafe issue title",
                        "run": "\n".join(
                            [
                                "const title = '${{ github.event.issue.title }}';",
                                "const py = '${{ matrix.python }}';",
                                "const literal = '${{ env.STATIC_VALUE }}';",
                            ]
                        ),
                    },
                    {
                        "run": 'const payload = "${{ steps.collect.outputs.payload }}";',
                    },
                ]
            }
        },
    }

    issues = validator.check_unsafe_string_interpolation(workflow)

    assert len(issues) == 2
    assert issues[0][0:2] == ("analyze", "Unsafe issue title")
    assert "github.event.issue.title" in issues[0][2]
    assert issues[1][0:2] == ("analyze", "step-1")
    assert "steps.collect.outputs.payload" in issues[1][2]
