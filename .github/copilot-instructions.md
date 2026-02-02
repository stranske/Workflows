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
| Rate limiting | See "Rate Limiting Architecture" in CLAUDE.md | Token rotation system |
| Sync mechanism | `maint-68-sync-consumer-repos.yml` | Pushes templates to consumers |

## When User Points to Files

If a user says "read X" or "check Y", do it **immediately** as your next action. Not later. Not after you've started something else. Immediately.

## Template Changes

Any change to workflows that consumers use must be reflected in BOTH:
1. `.github/workflows/` (main workflow)
2. `templates/consumer-repo/.github/workflows/` (template)

The `ci-template-drift.yml` workflow will fail if these drift too far apart.
