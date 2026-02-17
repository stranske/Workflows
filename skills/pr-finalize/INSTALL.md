# Installing pr-finalize Skill Globally

The `pr-finalize` skill can be installed globally to work across all repositories.

## Option 1: Symlink from Workflows Repo (Recommended)

If you frequently work with the Workflows repository:

```bash
# Create global skills directory
mkdir -p ~/.claude/skills

# Symlink the skill
ln -s /path/to/Workflows/skills/pr-finalize ~/.claude/skills/pr-finalize

# Verify
ls -la ~/.claude/skills
```

**Benefits:**
- Skill updates automatically when you pull Workflows repo
- Single source of truth
- Works across all repositories

## Option 2: Copy to Global Skills Directory

For standalone installation:

```bash
# Create global skills directory
mkdir -p ~/.claude/skills

# Copy the skill
cp -r skills/pr-finalize ~/.claude/skills/

# Verify
ls -la ~/.claude/skills/pr-finalize
```

**Update process:**
```bash
# When skill updates in Workflows repo
cp -r /path/to/Workflows/skills/pr-finalize ~/.claude/skills/
```

## Option 3: Repository-Local Installation

For repository-specific use:

```bash
# In your repository
mkdir -p skills
cp -r /path/to/Workflows/skills/pr-finalize skills/

# Commit to repo
git add skills/pr-finalize
git commit -m "Add pr-finalize skill"
```

Claude Code will auto-discover skills in:
1. `~/.claude/skills/` (global)
2. `./skills/` (repository-local)
3. `./.claude/skills/` (repository-local, hidden)

## Verification

After installation, verify the skill is discoverable:

```bash
# In a Claude Code session
/skills list

# Or just try to use it
/pr-finalize --help
```

## Repository Requirements

The skill works in any repository with:
- GitHub CLI (`gh`) installed
- GitHub Actions workflows for CI (optional - skips CI fixing if not present)
- Bot reviewers configured (optional - skips bot review handling if not present)
- Verification workflows (optional - skips verification if not present)

**The skill gracefully degrades** - it will skip phases that aren't applicable to your repository.

## Customization

To customize for your repository:

1. **Copy the skill locally**:
   ```bash
   mkdir -p skills
   cp -r ~/.claude/skills/pr-finalize skills/
   ```

2. **Edit `skills/pr-finalize/skill.json`** to change defaults:

   For example, to use faster single-LLM verification by default:
   ```json
   {
     "arguments": [
       {
         "name": "verify_mode",
         "default": "evaluate"
       }
     ]
   }
   ```

3. **Commit your customization**:
   ```bash
   git add skills/pr-finalize
   git commit -m "Customize pr-finalize skill"
   ```

Local skills take precedence over global skills.
