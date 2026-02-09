#!/usr/bin/env python3
"""Fix github-token in wrong location (after script: | instead of before)."""

import re
from typing import Match

files = [
    "agents-capability-check.yml",
    "health-41-repo-health.yml",
    "health-codex-auth-check.yml",
    "maint-50-tool-version-check.yml",
    "maint-69-sync-labels.yml",
]

for filename in files:
    filepath = f".github/workflows/{filename}"
    with open(filepath) as f:
        content = f.read()

    # Pattern: script: |\n  ...code...\ngithub-token: ...
    # Should be: github-token: ...\nscript: |\n  ...code...

    # Find all instances where github-token comes after script content
    pattern = r"(        uses: actions/github-script@v8\s*\n        with:\s*\n          script: \|[^\n]*\n(?:            [^\n]*\n)*?)          github-token: (\$\{\{ [^}]+ \}\})\n\n(            )"

    def fix_token_placement(match: Match[str]) -> str:
        script_part = match.group(1)
        token = match.group(2)
        code_start = match.group(3)

        # Remove the "with:\n          script:" part temporarily
        script_part_without_with = script_part.split("with:\n          script: |")[1]

        # Rebuild with token first
        return f"        uses: actions/github-script@v8\n        with:\n          github-token: {token}\n          script: |{script_part_without_with}\n{code_start}"

    fixed = re.sub(pattern, fix_token_placement, content)

    if fixed != content:
        with open(filepath, "w") as f:
            f.write(fixed)
        print(f"✓ {filename}")
    else:
        print(f"✗ {filename} - no changes")
