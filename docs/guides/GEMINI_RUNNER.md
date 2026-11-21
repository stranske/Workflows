# Gemini Runner Operator Notes

Short reference for operators and maintainers running the Gemini agent via
`reusable-gemini-run.yml` and keepalive routing (`agent:gemini`).

---

## Prerequisites

A repo needs a repository secret named `GEMINI_OAUTH_CREDS` before `agent:gemini` can run
hosted; see `.github/agents/registry.yml` for the registry entry. Hosted gemini runs on the
owner's Gemini **subscription**, never on an API key (owner decision 2026-11-11). The Gemini API
key belongs to the verify workflows only, as `VERIFIER_GEMINI_API_KEY`.

**Why the runner is `agy`, not `@google/gemini-cli`.** On 2026-11-11 a real "Sign in with Google"
login with gemini-cli 0.67/0.68 was refused by Google's Code Assist service:
`IneligibleTierError`, `reasonCode: UNSUPPORTED_CLIENT`, "This client is no longer supported for
Gemini Code Assist for individuals. To continue using Gemini, please migrate to the Antigravity
suite of products". The subscription is only reachable through Antigravity's CLI, `agy`, which
the local Orchestrator lanes already use.

---

## CLI installation

`agy` ships from a per-platform release manifest
(`https://antigravity-cli-auto-updater-974169037036.us-central1.run.app/manifests/<platform>.json`
with `version`, `url`, `sha512`), the same manifest Google's installer
(`https://antigravity.google/cli/install.sh`) reads. There is no version pin.

- **Resolve Gemini CLI version** reads the manifest for the runner's platform (`linux_amd64` or
  `linux_arm64`) and exports `GEMINI_CLI_VERSION`, the download URL and the SHA-512.
- **Cache Gemini CLI** restores `${{ runner.temp }}/agent-cli/gemini` keyed on that version
  (the binary only, never the sign-in).
- **Ensure Gemini CLI** reuses the cached binary when `.agy-version` matches. Otherwise it
  downloads the release, refuses it unless the SHA-512 matches the manifest, and unpacks it into
  `agent-cli/gemini/bin`. It skips the installer's `agy install` hand-off, which edits shell
  profiles.
- `AGY_CLI_DISABLE_AUTO_UPDATE=true` stops `agy` replacing itself mid-run.
- `AGY_CLI_HIDE_ACCOUNT_INFO=true` keeps the account out of the logs.

---

## Authentication

`agy` keeps a personal sign-in as a JSON file, `~/.gemini/antigravity-cli/antigravity-oauth-token`:
`{"token": {access_token, token_type, refresh_token, expiry, expires_in}, "auth_method":
"consumer", ...}`.

- **Desktop:** the OS keyring is the primary store.
- **No keyring available:** when it detects a remote or headless session (SSH, container, WSL,
  no D-Bus), `agy` logs "Using file-based token storage because … detected" and uses the file.
- **Documentation:** Google's docs describe only the keyring, so this fallback is real but
  undocumented. The sign-in check fails loudly if a future release drops it.

The workflow:

1. **Preflight auth** writes `secrets.GEMINI_OAUTH_CREDS` to that path (directory 0700, file
   0600). It checks that the value is a JSON object with `token.refresh_token`, printing neither.
   A missing or malformed secret fails fast with `Missing Gemini auth: set the GEMINI_OAUTH_CREDS
   secret …`.
2. **Check Gemini subscription sign-in** runs `agy models` with `SSH_CONNECTION` set, which is
   the signal verified on agy 1.5.6. That call validates the sign-in and spends no quota.
   - It reads `agy`'s own log and prints only yes/no for "Using file-based token storage" and
     "OAuth: authenticated successfully", plus the model count. It never prints the log, which
     names the account.
   - If either check fails, the run step short-circuits with a `Missing Gemini auth: …` message
     that names the remedy.
3. **Run Gemini** runs `agy -p` with the same `SSH_CONNECTION` signal.
4. **Remove Gemini login** deletes the file right after the run (`if: always()`), before
   commit/push, analysis and diagnostics.

**Token refresh.** The access token lasts an hour. `agy` refreshes it from the stored
`refresh_token` and rewrites the file itself. The refresh token does not rotate (verified
2026-11-11 by comparing it before and after a refresh), so, unlike `CODEX_AUTH_JSON`, nothing is
written back to the secret. The secret needs replacing only after a sign-out or revocation.

**Creating or refreshing the secret (owner machine).** Sign in once with `agy` (the local lanes
already are), then load the file straight into the secret without displaying it:

```bash
gh secret set GEMINI_OAUTH_CREDS --repo stranske/Workflows < ~/.gemini/antigravity-cli/antigravity-oauth-token
```

**Quota.** Hosted runs spend the same personal quota as the local `agy` lanes. "RESOURCE_EXHAUSTED
(code 429): Individual quota reached … Resets in Nm" is a capacity window, not an auth failure;
`error_classifier.js` treats it as transient.

**Exposure.** The agent runs with `--dangerously-skip-permissions` in the job that holds the file,
so the agent process can read the sign-in while it runs. That is the same exposure codex has to
`~/.codex/auth.json`.

---

## Headless invocation

```bash
agy -p "<prompt text>" --dangerously-skip-permissions --add-dir "$GITHUB_WORKSPACE" --model <agy id>
```

- **`-p`** runs non-interactively: `agy` applies tools and edits, then prints the final assistant
  message to stdout.
- **`--dangerously-skip-permissions`** lets it edit and run commands without confirmation.
  Headless `agy` otherwise soft-denies them and still exits 0. Set the workflow input
  `skip_permissions: false` to omit it.
- **`--add-dir`** must be the checkout's absolute path. Without it, `agy` works in an internal
  scratch workspace and reports success with the real tree unchanged.
- **Model:** the id comes from the shared model table's `local` surface (for example
  `gemini-4-argon-high`). Those are `agy` ids. The table's `hosted` ids are Gemini API ids, which
  `agy` rejects.

Stdout is captured to `gemini-output*.md` and tee'd to `gemini-session*.log` for debugging.

---

## Output path (plain text)

The runner uses `agy`'s default plain-text stdout and shares the text path with Claude and
Cursor in `runner_lib`:

- Prompt assembly: `scripts.runner_lib assemble-prompt --provider gemini`
- Output parsing: `scripts.runner_lib parse-output --provider gemini`

The workflow base64-encodes the captured stdout as `final-message`, matching the cursor/claude
text contract (not Codex's JSONL stream).

---

## Related files

| File | Purpose |
|------|---------|
| `.github/workflows/reusable-gemini-run.yml` | Reusable runner workflow |
| `.github/agents/registry.yml` | Agent registration and `GEMINI_OAUTH_CREDS` requirement |
| `agents-keepalive-loop.yml` | Keepalive dispatch for `agent:gemini` PRs |
| `docs/guides/agent-readiness/agy.md` | `agy` readiness evaluation |
| `docs/LABELS.md` | `agent:gemini` label behavior |
| `docs/ci/WORKFLOW_OUTPUTS.md` | Runner output contract |
