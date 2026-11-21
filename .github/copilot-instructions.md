# Copilot Instructions for Workflows Repository

## 🚨 MANDATORY FIRST ACTION

**Before doing ANY work in this repository, read CLAUDE.md:**

```bash
cat CLAUDE.md
```

This is not optional. Do this FIRST, before:
- Writing any code
- Creating any files
- Running any commands
- Making any changes

If you skip this step and someone points it out, acknowledge the mistake and read it immediately.

## Architecture Quick Reference

After reading CLAUDE.md, these are the key architectural points:

| Component | Location | Purpose |
|-----------|----------|---------|
| Main workflows | `.github/workflows/` | Run in this repo |
| Consumer templates | `templates/consumer-repo/` | Synced to consumer repos |
| Rate limiting | [Recommended Architecture](../docs/ops/api-rate-limit-management.md#recommended-architecture) | Token rotation system |
| Sync mechanism | `maint-68-sync-consumer-repos.yml` | Pushes templates to consumers |

## When User Points to Files

If a user says "read X" or "check Y", do it **immediately** as your next action. Not later. Not after you've started something else. Immediately.

## Ignore Ledger Tracking Files

Do not review or comment on ledger tracking files used for agent automation:
- `.agents/issue-*-ledger.yml`
- Any file under `.agents/` that is not application code

These files are internal task trackers and should never receive Copilot review comments or suggestions.

## Template Changes

Look up the workflow in the [sync manifest](sync-manifest.yml) to find its
source. Workflow entries normally use `templates/consumer-repo/`. An explicit
`source_tree: root` selects the file in this repository's root tree.

[Health 74 Template Drift](workflows/health-74-template-drift.yml) compares
covered main and consumer workflow pairs. Keep shared behavior aligned. When
a pair intentionally differs, review the change against its
[fingerprinted allowlist entry](../config/template-drift-allowlist.txt).
Run the same check from the repository root:

```sh
python scripts/check_template_drift.py --allowlist config/template-drift-allowlist.txt
```
