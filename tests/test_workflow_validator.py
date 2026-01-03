"""Tests for workflow_validator module."""

from pathlib import Path

from scripts.workflow_validator import (
    check_deprecated_actions,
    check_hardcoded_secrets,
    check_missing_timeout,
    check_permissions,
    check_unsafe_string_interpolation,
    load_workflow,
    validate_all_workflows,
    validate_workflow,
)


class TestLoadWorkflow:
    """Tests for load_workflow function."""

    def test_load_valid_workflow(self, tmp_path: Path) -> None:
        """Test loading a valid workflow file."""
        workflow_file = tmp_path / "test.yml"
        workflow_file.write_text(
            """
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""
        )

        result = load_workflow(str(workflow_file))
        assert result is not None
        assert result["name"] == "Test"

    def test_load_invalid_yaml(self, tmp_path: Path) -> None:
        """Test loading invalid YAML returns None."""
        workflow_file = tmp_path / "invalid.yml"
        workflow_file.write_text("{{invalid yaml")

        result = load_workflow(str(workflow_file))
        assert result is None

    def test_load_missing_file(self) -> None:
        """Test loading missing file returns None."""
        result = load_workflow("/nonexistent/workflow.yml")
        assert result is None


class TestCheckDeprecatedActions:
    """Tests for check_deprecated_actions function."""

    def test_no_deprecated_actions(self) -> None:
        """Test workflow with no deprecated actions."""
        workflow = {
            "jobs": {"build": {"steps": [{"name": "Checkout", "uses": "actions/checkout@v4"}]}}
        }

        issues = check_deprecated_actions(workflow)
        assert issues == []

    def test_detect_deprecated_checkout(self) -> None:
        """Test detection of deprecated checkout version."""
        workflow = {
            "jobs": {"build": {"steps": [{"name": "Checkout", "uses": "actions/checkout@v2"}]}}
        }

        issues = check_deprecated_actions(workflow)
        assert len(issues) == 1
        assert "checkout@v2" in issues[0][2]

    def test_detect_multiple_deprecated(self) -> None:
        """Test detection of multiple deprecated actions."""
        workflow = {
            "jobs": {
                "build": {
                    "steps": [
                        {"name": "Checkout", "uses": "actions/checkout@v3"},
                        {"name": "Upload", "uses": "actions/upload-artifact@v2"},
                    ]
                }
            }
        }

        issues = check_deprecated_actions(workflow)
        assert len(issues) == 2


class TestCheckMissingTimeout:
    """Tests for check_missing_timeout function."""

    def test_all_jobs_have_timeout(self) -> None:
        """Test workflow where all jobs have timeout."""
        workflow = {
            "jobs": {
                "build": {"timeout-minutes": 30},
                "test": {"timeout-minutes": 60},
            }
        }

        missing = check_missing_timeout(workflow)
        assert missing == []

    def test_detect_missing_timeout(self) -> None:
        """Test detection of jobs without timeout."""
        workflow = {
            "jobs": {
                "build": {"timeout-minutes": 30},
                "test": {},  # No timeout
            }
        }

        missing = check_missing_timeout(workflow)
        assert "test" in missing
        assert "build" not in missing


class TestCheckHardcodedSecrets:
    """Tests for check_hardcoded_secrets function."""

    def test_no_secrets(self) -> None:
        """Test workflow with no hardcoded secrets."""
        workflow = {"jobs": {"build": {"steps": [{"run": "echo hello"}]}}}

        issues = check_hardcoded_secrets(workflow)
        assert issues == []

    def test_detect_github_pat(self) -> None:
        """Test detection of hardcoded GitHub PAT."""
        workflow = {
            "jobs": {"build": {"env": {"TOKEN": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}}}
        }

        issues = check_hardcoded_secrets(workflow)
        assert len(issues) >= 1


class TestCheckPermissions:
    """Tests for check_permissions function."""

    def test_no_permission_issues(self) -> None:
        """Test workflow with appropriate permissions."""
        workflow = {"permissions": {"contents": "read"}, "jobs": {}}

        issues = check_permissions(workflow)
        assert issues == []

    def test_detect_write_all(self) -> None:
        """Test detection of write-all permissions."""
        workflow = {"permissions": "write-all", "jobs": {}}

        issues = check_permissions(workflow)
        assert len(issues) >= 1

    def test_detect_job_write_all(self) -> None:
        """Test detection of job-level write-all permissions."""
        workflow = {"jobs": {"build": {"permissions": "write-all"}}}

        issues = check_permissions(workflow)
        assert issues == ["Job build has write-all permissions"]

    def test_allows_contents_write(self) -> None:
        """Test that contents: write does not raise a permission issue."""
        workflow = {"permissions": {"contents": "write"}, "jobs": {}}

        issues = check_permissions(workflow)
        assert issues == []


class TestValidateWorkflow:
    """Tests for validate_workflow function."""

    def test_validate_good_workflow(self, tmp_path: Path) -> None:
        """Test validation of a well-formed workflow."""
        workflow_file = tmp_path / "good.yml"
        workflow_file.write_text(
            """
name: Good Workflow
on: push
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
"""
        )

        results = validate_workflow(str(workflow_file))
        assert results["deprecated_actions"] == []
        assert results["missing_timeout"] == []
        assert results["errors"] == []

    def test_validate_bad_workflow(self, tmp_path: Path) -> None:
        """Test validation catches multiple issues."""
        workflow_file = tmp_path / "bad.yml"
        workflow_file.write_text(
            """
name: Bad Workflow
on: push
permissions: write-all
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
"""
        )

        results = validate_workflow(str(workflow_file))
        assert len(results["deprecated_actions"]) >= 1
        assert len(results["missing_timeout"]) >= 1
        assert len(results["permission_issues"]) >= 1

    def test_validate_invalid_yaml(self, tmp_path: Path) -> None:
        """Test validation reports errors for invalid YAML."""
        workflow_file = tmp_path / "invalid.yml"
        workflow_file.write_text("{{invalid yaml")

        results = validate_workflow(str(workflow_file))
        assert results["errors"] == [f"Failed to load workflow: {workflow_file}"]


class TestValidateAllWorkflows:
    """Tests for validate_all_workflows function."""

    def test_validate_directory(self, tmp_path: Path) -> None:
        """Test validating all workflows in a directory."""
        # Create test workflows
        (tmp_path / "workflow1.yml").write_text(
            """
name: W1
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
"""
        )
        (tmp_path / "workflow2.yaml").write_text(
            """
name: W2
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
"""
        )

        results = validate_all_workflows(str(tmp_path))
        assert "workflow1.yml" in results
        assert "workflow2.yaml" in results
        # workflow2 should have deprecated action issue
        assert len(results["workflow2.yaml"]["deprecated_actions"]) >= 1

    def test_validate_nonexistent_directory(self) -> None:
        """Test validating nonexistent directory."""
        results = validate_all_workflows("/nonexistent/path")
        assert results == {}


class TestCheckUnsafeStringInterpolation:
    """Tests for check_unsafe_string_interpolation function.

    This validates that we detect patterns like:
        const x = '${{ outputs.something }}'
    which can break when the interpolated value contains backticks,
    quotes, or other special characters.

    The fix is to use env: blocks with process.env instead:
        env:
          MY_VAR: ${{ outputs.something }}
        run: |
          const x = process.env.MY_VAR;
    """

    def test_detects_unsafe_single_quote_interpolation(self) -> None:
        """Test that single-quoted string interpolation is flagged."""
        workflow = {
            "jobs": {
                "build": {
                    "steps": [
                        {
                            "name": "Parse tasks",
                            "run": "const tasks = '${{ needs.run.outputs.tasks }}'",
                        }
                    ]
                }
            }
        }
        issues = check_unsafe_string_interpolation(workflow)
        assert len(issues) == 1
        assert issues[0][0] == "build"
        assert issues[0][1] == "Parse tasks"
        assert "needs.run.outputs.tasks" in issues[0][2]
        assert "env:" in issues[0][2].lower() or "process.env" in issues[0][2]

    def test_detects_unsafe_double_quote_interpolation(self) -> None:
        """Test that double-quoted string interpolation is flagged."""
        workflow = {
            "jobs": {
                "test": {
                    "steps": [
                        {
                            "name": "Get data",
                            "run": 'const data = "${{ steps.fetch.outputs.result }}"',
                        }
                    ]
                }
            }
        }
        issues = check_unsafe_string_interpolation(workflow)
        assert len(issues) == 1
        assert "steps.fetch.outputs.result" in issues[0][2]

    def test_detects_unsafe_template_literal_interpolation(self) -> None:
        """Test that template literal interpolation is flagged."""
        workflow = {
            "jobs": {
                "deploy": {
                    "steps": [
                        {
                            "name": "Process",
                            "run": "const msg = `Result: ${{ outputs.message }}`",
                        }
                    ]
                }
            }
        }
        issues = check_unsafe_string_interpolation(workflow)
        assert len(issues) == 1

    def test_safe_env_block_pattern(self) -> None:
        """Test that env: block with process.env is not flagged."""
        workflow = {
            "jobs": {
                "analyze": {
                    "steps": [
                        {
                            "name": "Parse JSON",
                            "env": {"TASKS_JSON": "${{ outputs.tasks }}"},
                            "run": "const tasks = JSON.parse(process.env.TASKS_JSON);",
                        }
                    ]
                }
            }
        }
        issues = check_unsafe_string_interpolation(workflow)
        assert len(issues) == 0

    def test_safe_condition_pattern(self) -> None:
        """Test that if: conditions are not flagged."""
        workflow = {
            "jobs": {
                "build": {
                    "steps": [
                        {
                            "name": "Conditional",
                            "run": "echo 'running'",
                            "if": "${{ steps.check.outputs.should_run == 'true' }}",
                        }
                    ]
                }
            }
        }
        issues = check_unsafe_string_interpolation(workflow)
        assert len(issues) == 0

    def test_safe_secret_reference(self) -> None:
        """Test that secret references are not flagged as unsafe."""
        workflow = {
            "jobs": {
                "deploy": {
                    "steps": [
                        {
                            "name": "Use secret",
                            "run": "curl -H 'Authorization: ${{ secrets.TOKEN }}'",
                        }
                    ]
                }
            }
        }
        issues = check_unsafe_string_interpolation(workflow)
        # Secrets are controlled, so they're generally safe
        assert len(issues) == 0

    def test_multiple_issues_detected(self) -> None:
        """Test that multiple unsafe patterns in same workflow are all flagged."""
        workflow = {
            "jobs": {
                "job1": {
                    "steps": [
                        {
                            "name": "Step A",
                            "run": "const a = '${{ outputs.a }}'",
                        }
                    ]
                },
                "job2": {
                    "steps": [
                        {
                            "name": "Step B",
                            "run": 'const b = "${{ outputs.b }}"',
                        }
                    ]
                },
            }
        }
        issues = check_unsafe_string_interpolation(workflow)
        assert len(issues) == 2

    def test_no_false_positives_for_plain_scripts(self) -> None:
        """Test that scripts without interpolation are not flagged."""
        workflow = {
            "jobs": {
                "build": {
                    "steps": [
                        {
                            "name": "Normal script",
                            "run": "const x = 'hello'; console.log(x);",
                        }
                    ]
                }
            }
        }
        issues = check_unsafe_string_interpolation(workflow)
        assert len(issues) == 0

    def test_validate_workflow_includes_unsafe_interpolation(self) -> None:
        """Test that validate_workflow includes unsafe_interpolation results."""
        import tempfile

        import yaml

        workflow = {
            "name": "Test",
            "on": "push",
            "jobs": {
                "build": {
                    "runs-on": "ubuntu-latest",
                    "timeout-minutes": 10,
                    "steps": [
                        {"uses": "actions/checkout@v4"},
                        {
                            "name": "Unsafe step",
                            "run": "const x = '${{ outputs.data }}'",
                        },
                    ],
                }
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            yaml.dump(workflow, f)
            path = f.name

        results = validate_workflow(path)
        assert "unsafe_interpolation" in results
        assert len(results["unsafe_interpolation"]) == 1
