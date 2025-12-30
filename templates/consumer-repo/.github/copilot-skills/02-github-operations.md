# Skill: Safe GitHub Operations

**Trigger**: When performing any GitHub operations (push, PR, etc.)

## Pre-Flight Checklist

Before ANY push or PR operation:

1. **Check current branch**:
   ```bash
   git branch --show-current
   ```
   - If on `main` or `master` → Create feature branch first!

2. **Verify authentication**:
   ```bash
   gh auth status
   ```
   - Check if GITHUB_TOKEN or PAT is available
   - Some operations need elevated permissions (PAT)

3. **Check branch protection**:
   ```bash
   gh api repos/{owner}/{repo}/branches/main/protection 2>/dev/null || echo "No protection or no access"
   ```

## Standard Workflow

```bash
# 1. Create branch (use conventional prefix)
git checkout -b {type}/{description}
# Types: fix, feat, chore, docs, refactor, test

# 2. Make changes and commit
git add .
git commit -m "{type}: {description}"

# 3. Push to remote
git push origin {branch-name}

# 4. Create PR
gh pr create --title "{type}: {description}" --body "..."
```

## Common Pitfalls

### "refusing to allow" Error
**Cause**: Branch protection preventing direct push
**Fix**: Always use PR workflow, never push directly to main

### "Permission denied" Error
**Cause**: GITHUB_TOKEN doesn't have required scope
**Fix**: Use PAT with elevated permissions:
```bash
# Set token in environment (don't use inline - avoids shell history exposure)
export GH_TOKEN="$YOUR_PAT"
gh pr create ...
```

### PR Creation Fails
**Cause**: GraphQL API access issue
**Fix**: Set token explicitly:
```bash
# Authenticate via gh CLI (preferred - no token in history)
gh auth login
# Or export token (avoid inline assignment)
export GH_TOKEN="$YOUR_PAT"
gh pr create ...
```

## Key Rule

**Never assume direct push to `main` is allowed.** Always create a feature branch first.
