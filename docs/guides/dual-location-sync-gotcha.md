# ⚠️ CRITICAL: Dual-Location File Sync Gotcha

## Problem

Files in Workflows repo exist in **TWO locations**:
- `.github/codex/prompts/*.md` (Workflows own copy - used for self-testing)
- `templates/consumer-repo/.github/codex/prompts/*.md` (synced to consumers)

**The sync manifest declares the path as `.github/codex/prompts/file.md`**, but the sync workflow **prepends `templates/consumer-repo/`** when reading files. This means:

1. You update `.github/codex/prompts/fix_merge_conflicts.md` (for Workflows self-testing)
2. Sync reads from `templates/consumer-repo/.github/codex/prompts/fix_merge_conflicts.md` (old version)
3. **Consumers get the OLD version, not your changes!**

## How to Prevent This

**RULE**: When updating files in `.github/`, ALSO update the corresponding file in `templates/consumer-repo/.github/`:

```bash
# After updating a prompt in .github/codex/prompts/
cp .github/codex/prompts/fix_merge_conflicts.md \
   templates/consumer-repo/.github/codex/prompts/fix_merge_conflicts.md

# Or for scripts:
cp .github/scripts/conflict_detector.js \
   templates/consumer-repo/.github/scripts/conflict_detector.js
```

**Files affected by this gotcha:**
- All `.github/codex/prompts/*.md` files
- All `.github/scripts/*.js` files that are also in sync manifest
- Any other file declared in sync manifest with `.github/` path

## Why This Happens

The sync workflow (maint-68-sync-consumer-repos.yml) has this logic:
```python
template_src = Path('workflows/templates/consumer-repo') / source
```

It takes the `source` from sync-manifest.yml and prepends `workflows/templates/consumer-repo/`. So even though the manifest says `.github/codex/prompts/file.md`, it actually reads from `templates/consumer-repo/.github/codex/prompts/file.md`.

## Verification Checklist

Before committing changes to dual-location files:

- [ ] Updated file in `.github/` (for Workflows self-testing)
- [ ] Updated file in `templates/consumer-repo/.github/` (for consumer sync)
- [ ] Verified both files match: `diff .github/path/file templates/consumer-repo/.github/path/file`
- [ ] Committed both files in same PR
- [ ] Triggered sync workflow: `gh workflow run "Maint 68 Sync Consumer Repos" --repo stranske/Workflows`
- [ ] Merged resulting sync PRs: `gh workflow run "Merge Sync PRs" --repo stranske/Workflows`

## Real-World Example: Conflict Resolution Prompt

On 2026-01-10, the conflict resolution prompt was updated in `.github/codex/prompts/fix_merge_conflicts.md` with a critical fix:
- OLD: "Check `git status` first and exit if clean"
- NEW: "Do NOT check git status first! Conflicts only appear DURING merge"

But `templates/consumer-repo/.github/codex/prompts/fix_merge_conflicts.md` was not updated. Result:
- Workflows repo worked fine (used `.github/` copy)
- Consumer repos got old version via sync
- PRs with conflicts failed because agents exited early
- Issue discovered 2026-01-11 when PR #4339 in Trend_Model_Project had conflicts

**Fix**: Always update BOTH locations when making changes.

## Quick Reference

| Location | Used By | Purpose |
|----------|---------|---------|
| `.github/` | Workflows repo | Self-testing and validation |
| `templates/consumer-repo/.github/` | Consumer repos | What gets synced via maint-68 |

**Remember**: Sync manifest paths are misleading! They declare `.github/` but actually read from `templates/consumer-repo/`.
