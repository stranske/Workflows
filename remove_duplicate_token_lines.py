#!/usr/bin/env python3
import re

files = [
    "agents-capability-check.yml",
    "agents-verify-to-new-pr-autopilot.yml",
    "health-40-repo-selfcheck.yml",
    "health-41-repo-health.yml",
    "health-43-ci-signature-guard.yml",
    "health-71-sync-health-check.yml",
    "health-codex-auth-check.yml",
    "health-keepalive-e2e.yml",
    "maint-39-test-llm-providers.yml",
    "maint-50-tool-version-check.yml",
    "maint-61-create-floating-v1-tag.yml",
    "maint-69-sync-labels.yml",
    "maint-70-fix-integration-formatting.yml",
    "maint-71-auto-fix-integration.yml",
    "maint-74-ledger-base-sync.yml",
    "maint-auto-update-pypi-versions.yml",
    "maint-dependabot-auto-lock.yml",
    "maint-sync-action-versions.yml",
    "maint-sync-env-from-pyproject.yml",
    "reusable-12-ci-docker.yml",
    "selftest-ci.yml",
]

for fname in files:
    fpath = f".github/workflows/{fname}"
    with open(fpath) as f:
        lines = f.readlines()

    fixed_lines = []
    skip_next = False

    for i, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue

        # Check if this line and next line are duplicate token lines
        if (
            i < len(lines) - 1
            and re.match(r"^(\s+)token: \$\{\{ steps\.app_token", line)
            and re.match(r"^(\s+)token: \$\{\{ steps\.app_token", lines[i + 1])
        ):
            # Keep first one, skip second
            fixed_lines.append(line)
            skip_next = True
            print(f"Removed duplicate from {fname} line {i + 2}")
        else:
            fixed_lines.append(line)

    with open(fpath, "w") as f:
        f.writelines(fixed_lines)

print(f"\nFixed {len(files)} files")
