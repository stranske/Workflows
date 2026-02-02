#!/usr/bin/env python3
"""
Comprehensive fix for all duplicate parameters and with blocks.
Handles:
1. Duplicate github-token parameters
2. Duplicate token parameters
3. Duplicate with blocks
4. Missing script parameter after github-token
"""

import re

# Get all yml files that were modified
import subprocess

result = subprocess.run(
    ["git", "diff", "--name-only", "99643cb..HEAD"], capture_output=True, text=True
)
files = [
    f.replace(".github/workflows/", "").strip()
    for f in result.stdout.strip().split("\n")
    if f.endswith(".yml") and ".github/workflows/" in f
]

print(f"Processing {len(files)} modified workflow files...")

for fname in files:
    fpath = f".github/workflows/{fname}"
    try:
        with open(fpath) as f:
            content = f.read()
    except:
        continue

    # Pattern 1: Duplicate github-token or token in same with block
    # Remove consecutive duplicate lines
    lines = content.split("\n")
    fixed_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Check if next line is identical (duplicate param)
        if i < len(lines) - 1 and line.strip() and lines[i + 1].strip() == line.strip():
            if re.match(r"\s+(github-token|token):", line):
                fixed_lines.append(line)  # Keep first
                i += 2  # Skip duplicate
                print(f"  {fname}: Removed duplicate param at line {i}")
                continue

        # Pattern 2: with: followed by single param, then another with:
        # Merge them
        if (
            i < len(lines) - 2
            and re.match(r"^(\s+)with:\s*$", line)
            and re.match(r"^(\s+)(github-token|token):", lines[i + 1])
            and re.match(r"^(\s+)with:\s*$", lines[i + 2])
        ):
            # Keep first with and param, skip second with
            fixed_lines.append(line)
            fixed_lines.append(lines[i + 1])
            i += 3
            print(f"  {fname}: Merged duplicate with blocks at line {i}")
            continue

        fixed_lines.append(line)
        i += 1

    fixed_content = "\n".join(fixed_lines)

    with open(fpath, "w") as f:
        f.write(fixed_content)

print("\nDone!")
