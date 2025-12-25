"""Utility for validating workflow YAML files against best practices.

This module checks workflow files for common issues and anti-patterns.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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


def load_workflow(path: str) -> Optional[Dict]:
    """Load and parse a workflow YAML file.

    Args:
        path: Path to the workflow file

    Returns:
        Parsed YAML content or None if invalid
    """
    try:
        with open(path, "r") as f:
            return yaml.safe_load(f)
    except (yaml.YAMLError, FileNotFoundError, IOError):
        return None


def check_deprecated_actions(workflow: Dict) -> List[Tuple[str, str, str]]:
    """Check for deprecated action versions.

    Args:
        workflow: Parsed workflow YAML

    Returns:
        List of (job_name, step_name, issue) tuples
    """
    issues: List[Tuple[str, str, str]] = []

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


def check_missing_timeout(workflow: Dict) -> List[str]:
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


def check_hardcoded_secrets(workflow: Dict) -> List[Tuple[str, str]]:
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


def check_permissions(workflow: Dict) -> List[str]:
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


def validate_workflow(path: str) -> Dict[str, List]:
    """Run all validations on a workflow file.

    Args:
        path: Path to the workflow file

    Returns:
        Dictionary with validation results
    """
    results: Dict[str, List] = {
        "deprecated_actions": [],
        "missing_timeout": [],
        "hardcoded_secrets": [],
        "permission_issues": [],
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

    return results


def validate_all_workflows(directory: str) -> Dict[str, Dict[str, List]]:
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
