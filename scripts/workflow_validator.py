"""Utility for validating workflow YAML files against best practices.

This module checks workflow files for common issues and anti-patterns.
"""

import re
from pathlib import Path

import yaml

# Deprecated action patterns that should be updated
DEPRECATED_ACTIONS = {
    "actions/checkout@v2": "actions/checkout@v4",
    "actions/checkout@v3": "actions/checkout@v4",
    "actions/upload-artifact@v2": "actions/upload-artifact@v6",
    "actions/upload-artifact@v3": "actions/upload-artifact@v6",
    "actions/download-artifact@v2": "actions/download-artifact@v7",
    "actions/download-artifact@v3": "actions/download-artifact@v7",
}
UPLOAD_ARTIFACT_PATTERN = re.compile(r"^actions/upload-artifact@v(?P<major>\d+)(?:[.\w-]+)?$")


def load_workflow(path: str) -> dict | None:
    """Load and parse a workflow YAML file.

    Args:
        path: Path to the workflow file

    Returns:
        Parsed YAML content or None if invalid
    """
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except (OSError, yaml.YAMLError, FileNotFoundError):
        return None


def check_deprecated_actions(workflow: dict) -> list[tuple[str, str, str]]:
    """Check for deprecated action versions.

    Args:
        workflow: Parsed workflow YAML

    Returns:
        List of (job_name, step_name, issue) tuples
    """
    issues: list[tuple[str, str, str]] = []

    jobs = workflow.get("jobs", {})
    for job_name, job in jobs.items():
        steps = job.get("steps", [])
        for i, step in enumerate(steps):
            uses = step.get("uses", "")
            step_name = step.get("name", f"step-{i}")

            for deprecated, replacement in DEPRECATED_ACTIONS.items():
                if uses == deprecated:
                    issues.append(
                        (job_name, step_name, f"Deprecated action {deprecated}, use {replacement}")
                    )

    return issues


def check_missing_timeout(workflow: dict) -> list[str]:
    """Check for jobs without timeout-minutes.

    Args:
        workflow: Parsed workflow YAML

    Returns:
        List of job names missing timeout
    """
    missing = []
    jobs = workflow.get("jobs", {})

    for job_name, job in jobs.items():
        if "timeout-minutes" not in job:
            missing.append(job_name)

    return missing


def check_upload_artifact_major(
    workflow: dict, expected_major: int = 6
) -> list[tuple[str, str, str]]:
    """Check that actions/upload-artifact uses the expected major version.

    Args:
        workflow: Parsed workflow YAML
        expected_major: Required major version number

    Returns:
        List of (job_name, step_name, issue) tuples
    """
    issues: list[tuple[str, str, str]] = []
    jobs = workflow.get("jobs", {})

    for job_name, job in jobs.items():
        steps = job.get("steps", [])
        for i, step in enumerate(steps):
            uses = step.get("uses", "")
            match = UPLOAD_ARTIFACT_PATTERN.match(uses)
            if not match:
                continue

            step_name = step.get("name", f"step-{i}")
            major = int(match.group("major"))
            if major != expected_major:
                issues.append(
                    (
                        job_name,
                        step_name,
                        f"actions/upload-artifact@v{major} should use v{expected_major}",
                    )
                )

    return issues


def check_hardcoded_secrets(workflow: dict) -> list[tuple[str, str]]:
    """Check for potentially hardcoded secrets or tokens.

    Args:
        workflow: Parsed workflow YAML

    Returns:
        List of (location, issue) tuples
    """
    issues = []
    content = yaml.dump(workflow)

    # Patterns that might indicate hardcoded secrets
    patterns = [
        (r"ghp_[a-zA-Z0-9]{36}", "Possible GitHub PAT"),
        (r"github_pat_[a-zA-Z0-9_]{82}", "Possible fine-grained PAT"),
        (r"ghs_[a-zA-Z0-9]{36}", "Possible GitHub App token"),
        (r"sk-[a-zA-Z0-9]{48}", "Possible API key"),
    ]

    for pattern, description in patterns:
        matches = re.findall(pattern, content)
        for match in matches:
            issues.append((match[:10] + "...", description))

    return issues


def check_unsafe_string_interpolation(workflow: dict) -> list[tuple[str, str, str]]:
    """Check for unsafe string interpolation patterns in script blocks.

    This detects patterns where GitHub Actions expressions (${{ }}) are
    directly embedded in JavaScript/shell strings, which can break when
    the interpolated value contains special characters like backticks,
    quotes, or newlines.

    Safe pattern: Use env: block and process.env.VAR
    Unsafe pattern: const x = '${{ outputs.something }}'

    Args:
        workflow: Parsed workflow YAML

    Returns:
        List of (job_name, step_name, issue) tuples
    """
    issues: list[tuple[str, str, str]] = []

    # Patterns that indicate unsafe string interpolation
    # These detect ${{ }} expressions inside JS string literals
    unsafe_patterns = [
        # Single-quoted JS strings with interpolation
        (r"'[^']*\$\{\{[^}]+\}\}[^']*'", "Single-quoted string with ${{ }} interpolation"),
        # Double-quoted JS strings with interpolation
        (r'"[^"]*\$\{\{[^}]+\}\}[^"]*"', "Double-quoted string with ${{ }} interpolation"),
        # Template literals with interpolation (backticks)
        (r"`[^`]*\$\{\{[^}]+\}\}[^`]*`", "Template literal with ${{ }} interpolation"),
    ]

    # Known safe expression patterns (check the expression inside ${{ }})
    # IMPORTANT: Be conservative here. Many contexts can contain user-controlled data:
    # - github.event.issue.title, github.event.pull_request.body, etc.
    # - workflow_dispatch inputs can be user-provided
    # - toJSON/fromJSON results may contain special characters
    # Only patterns that are truly controlled should be listed here.
    safe_expression_patterns = [
        r"^\s*secrets\.[A-Za-z0-9_]+\s*$",  # Secret references are controlled (never user-visible)
        r"^\s*matrix\.[A-Za-z0-9_]+\s*$",  # Matrix values are defined in workflow YAML
        r"^\s*runner\.[A-Za-z0-9_]+\s*$",  # Runner context is controlled (os, arch, etc.)
    ]

    def is_static_env_value(value: object) -> bool:
        """Return True when env values are literal and do not interpolate expressions."""
        return isinstance(value, str) and "${{" not in value

    def collect_static_env(*env_dicts: dict) -> set[str]:
        """Collect env keys with static literal values from given env dicts."""
        static_keys: set[str] = set()
        for env_dict in env_dicts:
            if not isinstance(env_dict, dict):
                continue
            for key, value in env_dict.items():
                if is_static_env_value(value):
                    static_keys.add(key)
        return static_keys

    workflow_env = workflow.get("env", {})
    jobs = workflow.get("jobs", {})
    for job_name, job in jobs.items():
        steps = job.get("steps", [])
        job_env = job.get("env", {})
        for i, step in enumerate(steps):
            step_name = step.get("name", f"step-{i}")
            script = step.get("run") or step.get("script", "")
            step_env = step.get("env", {})
            static_env_keys = collect_static_env(workflow_env, job_env, step_env)

            if not script:
                continue

            # Check for unsafe patterns
            for pattern, description in unsafe_patterns:
                matches = re.findall(pattern, script)
                for match in matches:
                    # Extract what's being interpolated
                    expr_match = re.search(r"\$\{\{\s*([^}]+?)\s*\}\}", match)
                    expr = expr_match.group(1).strip() if expr_match else "unknown"

                    # Check if the expression is a known safe pattern
                    is_safe = any(
                        re.search(safe_pat, expr) for safe_pat in safe_expression_patterns
                    )
                    if not is_safe:
                        env_match = re.match(r"^\s*env\.([A-Za-z0-9_]+)\s*$", expr)
                        if env_match and env_match.group(1) in static_env_keys:
                            is_safe = True

                    if not is_safe:
                        issues.append(
                            (
                                job_name,
                                step_name,
                                f"{description}: '{expr}' may contain special characters. "
                                f"Use env: block with process.env instead.",
                            )
                        )

    return issues


def check_permissions(workflow: dict) -> list[str]:
    """Check for overly permissive permissions.

    Args:
        workflow: Parsed workflow YAML

    Returns:
        List of permission issues
    """
    issues = []

    # Check top-level permissions
    permissions = workflow.get("permissions", {})
    if permissions == "write-all":
        issues.append("Top-level permissions set to write-all")
    if isinstance(permissions, dict) and permissions.get("contents") == "write":
        # This might be intentional for autofix workflows
        pass

    # Check job-level permissions
    jobs = workflow.get("jobs", {})
    for job_name, job in jobs.items():
        job_perms = job.get("permissions", {})
        if job_perms == "write-all":
            issues.append(f"Job {job_name} has write-all permissions")

    return issues


def validate_workflow(path: str) -> dict[str, list]:
    """Run all validations on a workflow file.

    Args:
        path: Path to the workflow file

    Returns:
        Dictionary with validation results
    """
    results: dict[str, list] = {
        "deprecated_actions": [],
        "upload_artifact_version": [],
        "missing_timeout": [],
        "hardcoded_secrets": [],
        "permission_issues": [],
        "unsafe_interpolation": [],
        "errors": [],
    }

    workflow = load_workflow(path)
    if workflow is None:
        results["errors"].append(f"Failed to load workflow: {path}")
        return results

    results["deprecated_actions"] = check_deprecated_actions(workflow)
    results["upload_artifact_version"] = check_upload_artifact_major(workflow)
    results["missing_timeout"] = check_missing_timeout(workflow)
    results["hardcoded_secrets"] = check_hardcoded_secrets(workflow)
    results["permission_issues"] = check_permissions(workflow)
    results["unsafe_interpolation"] = check_unsafe_string_interpolation(workflow)

    return results


def validate_all_workflows(directory: str) -> dict[str, dict[str, list]]:
    """Validate all workflow files in a directory.

    Args:
        directory: Path to workflows directory

    Returns:
        Dictionary mapping workflow filename to validation results
    """
    results = {}
    workflows_dir = Path(directory)

    if not workflows_dir.exists():
        return results

    for workflow_file in workflows_dir.glob("*.yml"):
        results[workflow_file.name] = validate_workflow(str(workflow_file))

    for workflow_file in workflows_dir.glob("*.yaml"):
        results[workflow_file.name] = validate_workflow(str(workflow_file))

    return results
