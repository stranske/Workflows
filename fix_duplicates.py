#!/usr/bin/env python3
"""Remove duplicate app_token steps and fix other issues."""

import re
from pathlib import Path

base = Path(".github/workflows")


def remove_duplicate_app_tokens(filepath: Path) -> bool:
    """Remove consecutive duplicate Mint GitHub App Token steps."""
    with open(filepath) as f:
        lines = f.readlines()

    output = []
    i = 0
    fixed = False

    while i < len(lines):
        line = lines[i]

        # Check if this is start of Mint GitHub App Token step
        if "- name: Mint GitHub App Token" in line:
            # Collect this step's lines
            j = i + 1
            step_lines = [line]
            while j < len(lines) and not (
                lines[j].strip().startswith("- name:") or re.match(r"^  \w+:", lines[j])
            ):
                step_lines.append(lines[j])
                j += 1

            # Check if next step is also Mint GitHub App Token (duplicate)
            if j < len(lines) and "- name: Mint GitHub App Token" in lines[j]:
                # Skip the duplicate
                k = j + 1
                while k < len(lines) and not (
                    lines[k].strip().startswith("- name:") or re.match(r"^  \w+:", lines[k])
                ):
                    k += 1
                # Keep first, skip duplicate
                output.extend(step_lines)
                i = k
                fixed = True
            else:
                output.extend(step_lines)
                i = j
        else:
            output.append(line)
            i += 1

    if fixed:
        with open(filepath, "w") as f:
            f.writelines(output)

    return fixed


# Process all workflow files
for yml_file in sorted(base.glob("*.yml")):
    if remove_duplicate_app_tokens(yml_file):
        print(f"✓ {yml_file.name}")
