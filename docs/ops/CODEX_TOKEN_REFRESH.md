# Codex Auth Token Refresh Guide

This document explains the Codex CLI authentication token lifecycle in CI and how to
refresh `CODEX_AUTH_JSON` before it expires.

---

## Token Lifecycle Overview

| Component | Lifespan | Notes |
|-----------|----------|-------|
| Access Token | ~10 days | JWT with `exp` claim; checked by workflows |
| Refresh Token | Rotates | New refresh token is issued after refresh |

### How It Works

1. **Initial login**: `codex login --device-auth` writes credentials to `~/.codex/auth.json`.
2. **CI usage**: the `CODEX_AUTH_JSON` secret is a snapshot of `~/.codex/auth.json`.
3. **Rotation**: when the CLI refreshes, it writes updated tokens back to `~/.codex/auth.json`.
4. **CI limitation**: runners are ephemeral, so refreshed tokens are not persisted back to GitHub Secrets.

### Why CI Refresh Fails

```
ERROR: Your access token could not be refreshed because your refresh 
token was already used. Please log out and sign in again.
```

This error occurs when:
- A prior run refreshed and rotated the token set
- The rotated token set was only written on the runner
- Subsequent runs keep using the stale secret value

---

## Warning System

The `reusable-codex-run.yml` workflow checks token expiration before running, and emits
log annotations based on the access token's `exp` claim:

| Time Remaining | Level | Action |
|----------------|-------|--------|
| ≥ 5 days | ✅ OK | Proceeds normally |
| 2–4 days | ℹ️ Notice | Plan a refresh soon |
| < 2 days | ⚠️ Warning | Refresh ASAP to avoid agent downtime |
| Expired | ❌ Error | Workflow fails fast until refreshed |

**Important**: when the warning appears, refresh the secret that day. Any automatic
refresh that happens on a runner does not update GitHub Secrets.

---

## How to Refresh Tokens

### Step 1: Re-authenticate locally (device flow)

```bash
# Run device authentication flow
codex login --device-auth
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

After updating the secret, trigger a fast test run:

```bash
gh workflow run "Health 46 Codex Auth Check" --repo stranske/YOUR_REPO
```

Check the job summary confirms the new expiration date.

---

## Troubleshooting

### "refresh token was already used"

**Cause**: The refresh token in your secret has been consumed.

**Fix**: Follow the refresh steps above.

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

- [docs/ci/CHATGPT_SUBSCRIPTION_CI.md](../ci/CHATGPT_SUBSCRIPTION_CI.md) - CI authentication background
- [docs/keepalive/SETUP_CHECKLIST.md](../keepalive/SETUP_CHECKLIST.md) - Consumer setup checklist
- [docs/ops/CONSUMER_REPO_MAINTENANCE.md](./CONSUMER_REPO_MAINTENANCE.md) - Multi-repo maintenance
