#!/usr/bin/env python3
import re

files = [
    ".github/workflows/health-67-integration-sync-check.yml",
    ".github/workflows/health-68-consumer-sync-drift.yml",
    ".github/workflows/health-70-validate-sync-manifest.yml",
]

for filepath in files:
    with open(filepath) as f:
        lines = f.readlines()

    fixed_lines = []
    in_steps = False
    steps_indent = 0

    for i, line in enumerate(lines):
        # Track when we're in a steps section
        steps_match = re.match(r"^(\s*)steps:\s*$", line)
        if steps_match:
            in_steps = True
            steps_indent = len(steps_match.group(1))
            fixed_lines.append(line)
            continue

        # Check if we exit steps (new job or end of file)
        if in_steps:
            indent_match = re.match(r"^(\s*)\S", line)
            if indent_match:
                indent = len(indent_match.group(1))
                if indent <= steps_indent:
                    in_steps = False

        # Fix step items that are at wrong indentation
        step_match = re.match(r"^(\s+)- name:", line)
        if in_steps and step_match:
            expected_indent = steps_indent + 2
            actual_indent = len(step_match.group(1))
            if actual_indent != expected_indent:
                # Re-indent this step
                line = " " * expected_indent + line.lstrip()

        # Fix properties under steps that should be indented more
        if in_steps and i > 0:
            prev = fixed_lines[-1] if fixed_lines else ""
            prev_match = re.match(r"^(\s+)- name:", prev)
            line_match = re.match(r"^(\s+)(\w+):", line)
            if prev_match and line_match and not line.strip().startswith("- "):
                # This should be a property of the step
                prev_indent = len(prev_match.group(1))
                expected_indent = prev_indent + 2
                actual_indent = len(line_match.group(1))
                if actual_indent != expected_indent:
                    line = " " * expected_indent + line.lstrip()

        fixed_lines.append(line)

    with open(filepath, "w") as f:
        f.writelines(fixed_lines)

    print(f"Fixed {filepath}")
