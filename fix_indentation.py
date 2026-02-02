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
        if re.match(r"^(\s*)steps:\s*$", line):
            in_steps = True
            steps_indent = len(re.match(r"^(\s*)", line).group(1))
            fixed_lines.append(line)
            continue

        # Check if we exit steps (new job or end of file)
        if in_steps and re.match(r"^(\s*)\S", line):
            indent = len(re.match(r"^(\s*)", line).group(1))
            if indent <= steps_indent:
                in_steps = False

        # Fix step items that are at wrong indentation
        if in_steps and re.match(r"^(\s+)- name:", line):
            expected_indent = steps_indent + 2
            actual_indent = len(re.match(r"^(\s+)", line).group(1))
            if actual_indent != expected_indent:
                # Re-indent this step
                line = " " * expected_indent + line.lstrip()

        # Fix properties under steps that should be indented more
        if in_steps and i > 0:
            prev = fixed_lines[-1] if fixed_lines else ""
            if re.match(r"^(\s+)- name:", prev) and re.match(
                r"^(\s+)(\w+):", line
            ) and not line.strip().startswith("- "):
                # This should be a property of the step
                prev_indent = len(re.match(r"^(\s+)", prev).group(1))
                expected_indent = prev_indent + 2
                actual_indent = len(re.match(r"^(\s+)", line).group(1))
                if actual_indent != expected_indent:
                    line = " " * expected_indent + line.lstrip()

        fixed_lines.append(line)

    with open(filepath, "w") as f:
        f.writelines(fixed_lines)

    print(f"Fixed {filepath}")
