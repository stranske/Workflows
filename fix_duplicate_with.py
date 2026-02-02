#!/usr/bin/env python3
import re
import sys

files = [
    'agents-auto-pilot.yml',
    'agents-capability-check.yml',
    'agents-verify-to-issue-v2.yml',
    'agents-verify-to-new-pr.yml',
    'health-40-repo-selfcheck.yml',
    'health-41-repo-health.yml',
    'maint-69-sync-labels.yml',
    'maint-sync-action-versions.yml'
]

for fname in files:
    fpath = f'.github/workflows/{fname}'
    with open(fpath, 'r') as f:
        lines = f.readlines()
    
    fixed_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Check for pattern: with:\n  param:\n with:
        if (i < len(lines) - 2 and
            re.match(r'^(\s+)with:\s*$', line) and
            re.match(r'^(\s+)\w+:', lines[i+1]) and
            re.match(r'^(\s+)with:\s*$', lines[i+2])):
            # Merge: keep first with, skip second
            fixed_lines.append(line)  # first with:
            fixed_lines.append(lines[i+1])  # param
            i += 3  # skip the second "with:"
            print(f"Fixed {fname} around line {i}")
        else:
            fixed_lines.append(line)
            i += 1
    
    with open(fpath, 'w') as f:
        f.writelines(fixed_lines)

print(f"\nProcessed {len(files)} files")
