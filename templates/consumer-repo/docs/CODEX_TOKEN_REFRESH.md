# Codex OAuth Token Refresh Guide

This document explains how to refresh Codex CLI tokens before they expire.

---

## Quick Reference

| Warning Level | Time Remaining | Action Required |
|---------------|----------------|-----------------|
| ✅ OK | > 2 days | None |
| ⚠️ Notice | 1-2 days | **Refresh today** |
| 🔴 Warning | < 1 day | **Refresh immediately** |
| ❌ Error | Expired | Blocked; must refresh |

---

## How to Refresh

### 1. Re-authenticate Locally

```bash
codex auth logout
codex auth login
```

### 2. Update the GitHub Secret

```bash
# Option A: Using gh CLI
gh secret set CODEX_AUTH_JSON < ~/.codex/auth.json

# Option B: Manual
# 1. Copy: cat ~/.codex/auth.json
# 2. Go to Settings → Secrets → Actions → CODEX_AUTH_JSON → Update
# 3. Paste and save
```

### 3. Verify

```bash
gh workflow run agents-81-gate-followups.yml -f pr_number=<pr-number> -f force_retry=true
# Check logs for new expiration date
```

---

## Why Tokens Expire Unexpectedly

The error:
```
ERROR: Your access token could not be refreshed because your refresh 
token was already used.
```

Occurs because:
1. Access tokens last ~10 days
2. When nearing expiration, Codex CLI auto-refreshes using the refresh token
3. Refresh tokens are **single-use**—once consumed, they're invalid
4. CI runners are ephemeral—new tokens aren't persisted back to secrets

**Solution**: Refresh tokens manually before the 2-day warning, not after.

---

## Multi-Repo Update

If you use the same credentials across repos:

```bash
# Update all repos at once
for repo in Trend_Model_Project Portable-Alpha-Extension-Model Manager-Database; do
  gh secret set CODEX_AUTH_JSON --repo stranske/$repo < ~/.codex/auth.json
done
```

---

## See Also

- Full documentation: [Workflows/docs/ops/CODEX_TOKEN_REFRESH.md](https://github.com/stranske/Workflows/blob/main/docs/ops/CODEX_TOKEN_REFRESH.md)
