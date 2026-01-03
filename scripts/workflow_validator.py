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
    "actions/upload-artifact@v2": "actions/upload-artifact@v4",
    "actions/upload-artifact@v3": "actions/upload-artifact@v4",
    "actions/download-artifact@v2": "actions/download-artifact@v4",
    "actions/download-artifact@v3": "actions/download-artifact@v4",
}


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
    safe_expression_patterns = [
        r"^\s*secrets\.",  # Secret references are controlled
        r"^\s*toJSON\(",  # toJSON produces valid JSON
        r"^\s*fromJSON\(",  # fromJSON is safe
        r"^\s*github\.",  # GitHub context is controlled
        r"^\s*env\.",  # Environment variables are controlled
        r"^\s*inputs\.",  # Workflow inputs are typically controlled
        r"^\s*matrix\.",  # Matrix values are controlled
        r"^\s*runner\.",  # Runner context is controlled
    ]

    jobs = workflow.get("jobs", {})
    for job_name, job in jobs.items():
        steps = job.get("steps", [])
        for i, step in enumerate(steps):
            step_name = step.get("name", f"step-{i}")
            script = step.get("run") or step.get("script", "")

            if not script:
                continue

            # Skip if step uses env: block (safer pattern)
            if step.get("env"):
                # Check if the script uses process.env instead of inline interpolation
                env_vars = step.get("env", {})
                # If env vars contain ${{ }} and script references process.env, that's safe
                has_env_vars_with_expressions = any("${{" in str(v) for v in env_vars.values())
                uses_process_env = "process.env" in script
                if has_env_vars_with_expressions and uses_process_env:
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
