# Codex OAuth Token Refresh Guide

This document explains the Codex CLI OAuth token lifecycle and how to refresh tokens
before they expire.

---

## Token Lifecycle Overview

| Component | Lifespan | Notes |
|-----------|----------|-------|
| Access Token | ~10 days | JWT with `exp` claim; checked by workflow |
| Refresh Token | Single-use | Consumed when access token is refreshed |

### How It Works

1. **Initial Login**: `codex auth login` creates both tokens, stored in `~/.codex/auth.json`
2. **CI Usage**: The `CODEX_AUTH_JSON` secret contains a snapshot of `auth.json`
3. **Auto-refresh**: When access token nears expiration (~1-2 days), Codex CLI automatically uses the refresh token
4. **Token Rotation**: A successful refresh generates NEW access AND refresh tokens
5. **CI Problem**: The new tokens are written to the ephemeral CI runner, not back to GitHub Secrets

### Why CI Refresh Fails

```
ERROR: Your access token could not be refreshed because your refresh 
token was already used. Please log out and sign in again.
```

This error occurs when:
- A prior run successfully refreshed (consuming the refresh token)
- The new refresh token was lost (CI runner is ephemeral)
- Subsequent runs try to use the old (now-invalid) refresh token

---

## Warning System

The `reusable-codex-run.yml` workflow checks token expiration before running:

| Time Remaining | Level | Action |
|----------------|-------|--------|
| > 2 days | ✅ OK | Proceeds normally |
| 1-2 days | ⚠️ Notice | Warning in logs; **refresh soon** |
| < 1 day | 🔴 Warning | Urgent; may fail if CLI auto-refreshes |
| Expired | ❌ Error | Will not proceed |

**Important**: When you see the warning, refresh tokens **immediately**. Don't wait—
the Codex CLI may attempt auto-refresh at any time once under 2 days, which will
consume your refresh token.

---

## How to Refresh Tokens

### Step 1: Log Out and Log In Locally

```bash
# Clear existing tokens
codex auth logout

# Re-authenticate (opens browser for OAuth)
codex auth login
```

### Step 2: Copy the New Auth JSON

```bash
# macOS
cat ~/.codex/auth.json | pbcopy

# Linux (with xclip)
cat ~/.codex/auth.json | xclip -selection clipboard

# Or just display it
cat ~/.codex/auth.json
```

### Step 3: Update GitHub Secret

1. Navigate to your repository on GitHub
2. Go to **Settings** → **Secrets and variables** → **Actions**
3. Find `CODEX_AUTH_JSON` and click **Update**
4. Paste the new content from `~/.codex/auth.json`
5. Click **Save**

### Step 4: Update All Consumer Repos (if applicable)

If you use the same Codex credentials across multiple repositories:

```bash
# List repos that need updating
gh repo list stranske --json name -q '.[].name'

# Update each repo's secret (replace VALUE with your auth.json content)
gh secret set CODEX_AUTH_JSON --repo stranske/REPO_NAME < ~/.codex/auth.json
```

---

## Best Practices

### 1. Set Calendar Reminders

Since tokens last ~10 days, set a recurring reminder for every 7-8 days to refresh.

### 2. Refresh Immediately on Warning

Don't wait until the last moment. When CI shows the warning, refresh that day.

### 3. Avoid Concurrent Runs

If multiple CI runs happen simultaneously near token expiration, one may succeed
(consuming the refresh token) while others fail. Consider:
- Pausing non-essential workflows during token refresh
- Updating secrets immediately after local refresh

### 4. Verify After Refresh

After updating the secret, trigger a test run:

```bash
gh workflow run agents-keepalive-loop.yml --repo stranske/YOUR_REPO
```

Check the logs confirm the new token expiration date.

---

## Troubleshooting

### "refresh token was already used"

**Cause**: The refresh token in your secret has been consumed.

**Fix**: Follow the refresh steps above. You must do a full `logout` + `login`.

### "token expired"

**Cause**: The access token's `exp` claim is in the past.

**Fix**: Refresh tokens. The workflow will block execution when expired.

### Warning appeared but runs still succeed

**Cause**: The access token is still valid; warning is preemptive.

**Fix**: This is expected. Refresh soon to avoid issues.

### Multiple repos failing simultaneously

**Cause**: All repos share the same `CODEX_AUTH_JSON`, and one run consumed the
refresh token.

**Fix**: Update the secret in ALL repos after refreshing locally.

---

## Token Structure Reference

The `auth.json` file contains:

```json
{
  "provider": "openai",
  "tokens": {
    "access_token": "eyJ...",    // JWT - decode to check exp
    "refresh_token": "rt_...",   // Single-use; rotates on refresh
    "token_type": "Bearer",
    "expires_in": 864000         // Seconds (10 days = 864000)
  }
}
```

To manually check expiration:

```bash
# Extract and decode the JWT (requires jq)
cat ~/.codex/auth.json | jq -r '.tokens.access_token' | \
  cut -d. -f2 | base64 -d 2>/dev/null | jq '.exp | todate'
```

---

## See Also

- [SETUP_CHECKLIST.md](../templates/SETUP_CHECKLIST.md) - Initial repository setup
- [CONSUMER_REPO_MAINTENANCE.md](./CONSUMER_REPO_MAINTENANCE.md) - Multi-repo management
