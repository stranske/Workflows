# Using Codex CLI with ChatGPT Pro/Plus Subscription in GitHub CI

## Quick Reference: Token Refresh Process

When your token is expiring (you'll see warnings in CI), follow these steps:

```bash
# 1. Authenticate with device code flow (works in any environment)
codex login --device-auth

# 2. Follow the prompts:
#    - Go to https://auth.openai.com/codex/device
#    - Enter the code displayed in terminal
#    - Complete authentication

# 3. Copy the auth.json content
cat ~/.codex/auth.json

# 4. Update GitHub secret:
#    - Go to: https://github.com/YOUR-ORG/YOUR-REPO/settings/secrets/actions
#    - Update CODEX_AUTH_JSON with the JSON content
```

Token lifetime: **~10 days** from authentication.

---

## Executive Summary

**Current Status (December 2025):** Running Codex CLI with ChatGPT subscription authentication in GitHub Actions **is possible but has significant operational limitations**. The main challenge is **OAuth refresh token rotation** — tokens become invalid after first use, requiring periodic manual re-authentication every ~10 days.

**Alternative:** Use `OPENAI_API_KEY` with pay-as-you-go billing if you need fully automated, long-term CI without manual intervention.

---

## Chronological Evolution of CI Approaches

### Phase 1: API-Only Era (April–August 2025)

**April 2025** — Codex CLI launched requiring `OPENAI_API_KEY` for authentication.

- **Issue [#35](https://github.com/openai/codex/issues/35)** (April 16, 2025): First request for ChatGPT Plus/Pro subscription support
- **Issue [#124](https://github.com/openai/codex/issues/124)** (April 16, 2025): Request for GitHub Actions CI pipeline
- **Issue [#1080](https://github.com/openai/codex/issues/1080)** (May 22, 2025): First reports of CI environment issues (Ink raw mode errors)

At this point, **ChatGPT subscription users could not use Codex CLI at all** — only API key holders.

**May 2025** — OpenAI announced API credits would be bundled with Plus/Pro subscriptions.

---

### Phase 2: ChatGPT Subscription Support Arrives (August 2025)

**August 2025** — OAuth browser-based authentication added for ChatGPT Plus/Pro.

- **Issue [#1976](https://github.com/openai/codex/issues/1976)** (August 7, 2025): "Enable Signing in with ChatGPT account for browserless machines"
- **Issue [#2543](https://github.com/openai/codex/issues/2543)** (August 21, 2025): "How to use GitHub Action with ChatGPT plan?"
- **Issue [#2798](https://github.com/openai/codex/issues/2798)** (August 27, 2025): **Canonical issue** — "Support remote / headless OAuth sign-in" (44+ comments)

**The Problem:** OAuth requires opening a browser on `localhost:1455`, impossible in headless CI environments.

---

### Phase 3: Community Workarounds Era (September–November 2025)

Users developed various workarounds:

#### Workaround A: Copy `auth.json` from Local Machine
```bash
# On local machine with browser
codex login
# Copy ~/.codex/auth.json to CI secret
base64 -w0 ~/.codex/auth.json  # Linux
base64 -i ~/.codex/auth.json | tr -d '\n'  # macOS
```

**Problem:** Token expires after ~10 days; refresh tokens invalidate after single use.

#### Workaround B: SSH Port Forwarding
```bash
# From local machine, forward port 1455 to remote
ssh -N -L 1455:127.0.0.1:1455 user@remote-server
# Then run `codex login` on remote and open URL locally
```

**Problem:** Requires interactive setup; doesn't solve CI automation.

#### Workaround C: VS Code Port Forwarding
Run Codex in VS Code Remote SSH terminal; VS Code auto-forwards `localhost:1455`.

**Problem:** Still manual; not CI-compatible.

#### Workaround D: Curl Token Extraction
Some users extracted tokens via browser developer tools:
```bash
# Copy as cURL from browser auth flow, extract tokens
```

**Problem:** Complex, fragile, not documented.

---

### Phase 4: Refresh Token Rotation Issues (October–November 2025)

**October–November 2025** — Users discovered a critical CI-breaking issue:

- **Issue [#6028](https://github.com/openai/codex/issues/6028)** (October 31, 2025): "Failed to refresh token"
- **Issue [#6036](https://github.com/openai/codex/issues/6036)** (October 31, 2025): "Refresh token already used"
- **Issue [#6393](https://github.com/openai/codex/issues/6393)** (November 8, 2025): "Headless login is broken"
- **Issue [#6498](https://github.com/openai/codex/issues/6498)** (November 11, 2025): "Refresh token was already used after session timed out" (**still open**)

**Root Cause:** OpenAI uses **OAuth Refresh Token Rotation** — each refresh token can only be used once. When you store `auth.json` as a GitHub secret:

1. First CI run uses refresh token → gets new tokens → **GitHub secret is now stale**
2. Second CI run uses old (stale) refresh token → **401 Unauthorized**
3. You must manually re-authenticate and update the secret

**Key Comment from [#3820](https://github.com/openai/codex/issues/3820#issuecomment-2786655882):**
> "The issue here is not how you get authenticated. It's that you have to log in again after a while, breaking automation. Codex is unusable in CI/CD pipeline on a subscription. They are pushing you to use the OPENAI_API_KEY for that." — @dennisvink

---

### Phase 5: Device Code Authentication (December 2025)

**December 8, 2025** — OpenAI announces device code authentication testing:

- **[Comment on #2798](https://github.com/openai/codex/issues/2798#issuecomment-3629482218)** by @mzeng-openai

```bash
# New headless authentication flow
codex login --device-auth
```

**How it works:**
1. Run `codex login --device-auth` in headless environment
2. CLI shows a URL (`https://auth.openai.com/codex/device`) and one-time code
3. Open URL on any browser, enter code, authenticate
4. CLI receives tokens without localhost redirect

**Current Issues (as of December 2025):**
- **Issue [#8158](https://github.com/openai/codex/issues/8158)**: VS Code Remote SSH still has issues
- **Issue [#8112](https://github.com/openai/codex/issues/8112)**: Some users still get localhost redirects
- Some users report 403 errors on first attempt

---

## Current Best Practice (December 2025)

### For CI with ChatGPT Pro Subscription

**This approach works but requires periodic manual intervention (~every 10 days):**

1. **Enable Device Code Login** in ChatGPT settings:
   - Personal: [ChatGPT Security Settings](https://chatgpt.com/#settings/Security)
   - Workspace: [ChatGPT Workspace Permissions](https://chatgpt.com/admin/permissions)

2. **Authenticate using device auth:**
   ```bash
   codex login --device-auth
   ```

3. **Export and encode auth.json:**
   ```bash
   # Linux
   base64 -w0 ~/.codex/auth.json
   
   # macOS
   base64 -i ~/.codex/auth.json | tr -d '\n'
   ```

4. **Store as GitHub Secret:**
   - Repository Settings → Secrets → Actions
   - Create secret named `CODEX_AUTH_JSON`
   - Paste the raw JSON content (not base64)

5. **Use in workflow:**
   ```yaml
   - name: Configure Codex auth
     env:
       CODEX_AUTH_JSON: ${{ secrets.CODEX_AUTH_JSON }}
     run: |
       mkdir -p ~/.codex
       echo "$CODEX_AUTH_JSON" > ~/.codex/auth.json
       chmod 600 ~/.codex/auth.json
   ```

6. **Token lifetime:**
   - Access token: ~10 days
   - Refresh token: Single-use (rotation)
   - **You must re-authenticate before access token expires**

### For Fully Automated CI

Use `OPENAI_API_KEY` with the official [codex-action](https://github.com/openai/codex-action):

```yaml
- uses: openai/codex-action@v1
  with:
    openai-api-key: ${{ secrets.OPENAI_API_KEY }}
    prompt: "Your prompt here"
```

---

## Token Expiration Handling Strategy

Since subscription auth tokens expire, implement expiration detection:

```yaml
- name: Check Codex auth expiration
  id: auth-check
  env:
    CODEX_AUTH_JSON: ${{ secrets.CODEX_AUTH_JSON }}
  run: |
    if [ -z "$CODEX_AUTH_JSON" ]; then
      echo "status=missing" >> $GITHUB_OUTPUT
      exit 0
    fi
    
    # Write and check auth
    mkdir -p ~/.codex
    echo "$CODEX_AUTH_JSON" > ~/.codex/auth.json
    chmod 600 ~/.codex/auth.json
    
    # Check expiration
    EXPIRY=$(python3 -c "
    import json, base64, datetime, sys
    auth = json.load(open('$HOME/.codex/auth.json'))
    token = auth.get('tokens', {}).get('access_token', '')
    if not token:
      print('missing')
      sys.exit(0)
    parts = token.split('.')
    if len(parts) != 3:
      print('invalid')
      sys.exit(0)
    payload = parts[1] + '=' * (4 - len(parts[1]) % 4)
    data = json.loads(base64.urlsafe_b64decode(payload))
    exp = datetime.datetime.fromtimestamp(data['exp'], tz=datetime.timezone.utc)
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    days_left = (exp - now).days
    if days_left < 0:
      print('expired')
    elif days_left < 2:
      print('expiring-soon')
    else:
      print('valid')
    ")
    
    echo "status=$EXPIRY" >> $GITHUB_OUTPUT
    echo "Auth token status: $EXPIRY"
    
    if [ "$EXPIRY" = "expired" ]; then
      echo "::error::CODEX_AUTH_JSON has expired. Run 'codex login --device-auth' and update the secret."
      exit 1
    elif [ "$EXPIRY" = "expiring-soon" ]; then
      echo "::warning::CODEX_AUTH_JSON expires in less than 2 days. Consider refreshing soon."
    fi
```

---

## Community Fork with Subscription Support

[@activadee's fork](https://github.com/activadee/codex-action) adds subscription auth to codex-action:

```yaml
- uses: activadee/codex-action@main
  with:
    codex-auth-json-b64: ${{ secrets.CODEX_AUTH_JSON_B64 }}
    prompt: "Your prompt here"
```

**Note:** This fork is not officially maintained by OpenAI. Use at your own risk.

---

## Key GitHub Issues to Watch

| Issue | Status | Description |
|-------|--------|-------------|
| [#2798](https://github.com/openai/codex/issues/2798) | Open | Canonical headless OAuth issue |
| [#6498](https://github.com/openai/codex/issues/6498) | Open | Refresh token rotation problem |
| [#27](https://github.com/openai/codex-action/issues/27) | Open | Subscription auth for codex-action |
| [#8158](https://github.com/openai/codex/issues/8158) | Open | VS Code Remote SSH auth issues |

---

## Recommendations

1. **For production CI:** Use `OPENAI_API_KEY` with pay-as-you-go billing
2. **For personal/hobby CI:** Use subscription auth with scheduled token refresh reminders
3. **Monitor:** Set up alerts when tokens are expiring (implement expiration check above)
4. **Automate notification:** Create a scheduled workflow that checks expiration and opens an issue when refresh is needed

---

## References

- [Official Codex Authentication Docs](https://github.com/openai/codex/blob/main/docs/authentication.md)
- [Codex GitHub Action](https://github.com/openai/codex-action)
- [@activadee's Subscription Auth Fork](https://github.com/activadee/codex-action)
- [ChatGPT Security Settings](https://chatgpt.com/#settings/Security)

---

*Last updated: December 25, 2025*
