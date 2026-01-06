#!/usr/bin/env python3
"""
Validate GitHub Actions workflow YAML files.

This script checks workflow files for common syntax errors and issues
that may not be caught by basic YAML parsers but cause failures in GitHub Actions.
"""

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install PyYAML")
    sys.exit(1)


def check_line_length(file_path: Path, max_length: int = 100) -> list[tuple[int, str]]:
    """Check for lines that exceed maximum length (may cause wrapping issues)."""
    issues = []
    with open(file_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if len(line.rstrip()) > max_length:
                issues.append((line_num, f"Line exceeds {max_length} characters"))
    return issues


def check_runs_on_placement(file_path: Path) -> list[tuple[int, str]]:
    """Check that 'runs-on' is properly placed on its own line."""
    issues = []
    with open(file_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            stripped = line.strip()
            if "runs-on:" in stripped:
                # Check if there's content before 'runs-on:' on the same line
                before_runs_on = line.split("runs-on:")[0].strip()
                if before_runs_on and not before_runs_on.endswith("#"):
                    issues.append(
                        (
                            line_num,
                            "runs-on should be on its own line (found text before it)",
                        )
                    )
    return issues


def check_yaml_syntax(file_path: Path) -> list[tuple[int, str]]:
    """Validate basic YAML syntax."""
    issues = []
    try:
        with open(file_path, encoding="utf-8") as f:
            yaml.safe_load(f)
    except yaml.YAMLError as e:
        line_num = getattr(e, "problem_mark", None)
        if line_num:
            issues.append((line_num.line + 1, f"YAML syntax error: {e.problem}"))
        else:
            issues.append((0, f"YAML syntax error: {str(e)}"))
    return issues


def check_multiline_conditions(file_path: Path) -> list[tuple[int, str]]:
    """Check for complex conditions that should use multiline format."""
    issues = []
    with open(file_path, encoding="utf-8") as f:
        lines = f.readlines()
        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            # Only flag if line exceeds repo standard (100 chars) OR continues improperly
            if stripped.startswith("if:") and len(stripped) > 100:
                # Check if it's using multiline format
                if not stripped.endswith("|") and not stripped.endswith(">"):
                    issues.append(
                        (
                            line_num,
                            "Very long 'if' condition should use multiline format (| or >)",
                        )
                    )
            # Check if next line looks like continuation without proper multiline syntax
            elif stripped.startswith("if:") and line_num < len(lines):
                next_line = lines[line_num].strip()
                # Check if 'runs-on:' appears mid-line (indicates malformed wrapping)
                if next_line and "runs-on:" in next_line and not next_line.startswith("runs-on:"):
                    issues.append(
                        (
                            line_num + 1,
                            "Found 'runs-on:' not at start of line - possible malformed multiline 'if'",
                        )
                    )
    return issues


def validate_workflow(file_path: Path, verbose: bool = False) -> bool:
    """Validate a workflow file and return True if valid."""
    all_issues = []

    # Run all checks
    all_issues.extend([(line, f"YAML: {msg}") for line, msg in check_yaml_syntax(file_path)])
    all_issues.extend([(line, f"Length: {msg}") for line, msg in check_line_length(file_path)])
    all_issues.extend(
        [(line, f"Placement: {msg}") for line, msg in check_runs_on_placement(file_path)]
    )
    all_issues.extend(
        [(line, f"Format: {msg}") for line, msg in check_multiline_conditions(file_path)]
    )

    if all_issues:
        print(f"\n❌ {file_path.name}: Found {len(all_issues)} issue(s)")
        for line_num, message in sorted(all_issues):
            if line_num > 0:
                print(f"  Line {line_num}: {message}")
            else:
                print(f"  {message}")
        return False
    else:
        if verbose:
            print(f"✓ {file_path.name}: Valid")
        return True


def main():
    parser = argparse.ArgumentParser(description="Validate GitHub Actions workflow YAML files")
    parser.add_argument(
        "files",
        nargs="+",
        type=Path,
        help="Workflow files to validate",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show validation results for all files",
    )
    args = parser.parse_args()

    all_valid = True
    for file_path in args.files:
        if not file_path.exists():
            print(f"❌ {file_path}: File not found")
            all_valid = False
            continue

        if not validate_workflow(file_path, args.verbose):
            all_valid = False

    if all_valid:
        print(f"\n✓ All {len(args.files)} workflow file(s) validated successfully")
        sys.exit(0)
    else:
        print("\n❌ Validation failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
