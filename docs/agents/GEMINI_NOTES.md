# Gemini Runner Operator Notes

Short reference for operators and maintainers running the Gemini agent via
`reusable-gemini-run.yml` and keepalive routing (`agent:gemini`).

---

## Prerequisites

A repo needs a repository secret named `GEMINI_OAUTH_CREDS` before
`agent:gemini` can run hosted; see `.github/agents/registry.yml` for the registry
entry. Hosted gemini runs on the owner's Gemini **subscription** login, never on an
API key (owner decision 2026-11-11): the Gemini API key belongs to the verify
workflows only, as `VERIFIER_GEMINI_API_KEY`.

---

## CLI Installation

The runner installs Google's Gemini CLI from npm when it is not already on
`PATH`:

```bash
npm install -g @google/gemini-cli@<version>
```

In CI, the **Ensure Gemini CLI** step in `reusable-gemini-run.yml` runs that
install globally into the runner's temporary `agent-cli/gemini` npm prefix.
The workflow input `gemini_cli_version` defaults to the release pinned in
`reusable-gemini-run.yml` (both the input default and the env fallback); Renovate
bumps both weekly (`renovate.json`, custom manager for `@google/gemini-cli`).
Omitting it or passing an empty value selects that pinned release. Pass an explicit
version (for example `1.2.3`) to select a different release.

The **Cache Gemini CLI** step restores that installation by runner OS,
architecture, Node 24 and the resolved CLI version. The prefix's `bin` directory
is added to `PATH` before **Ensure Gemini CLI**, which reuses an available
binary and installs the pinned version when none is found. Changing the version
selects a different cache key; an empty input does not request automatic upgrades.

---

## Authentication

Hosted runs use a cached "Sign in with Google" login, the way codex restores its
ChatGPT login from `CODEX_AUTH_JSON`. The workflow:

1. **Preflight auth** writes `secrets.GEMINI_OAUTH_CREDS` to
   `$HOME/.gemini/oauth_creds.json` (directory 0700, file 0600) and checks that it is a
   JSON object with a `refresh_token`, printing neither. A missing or malformed secret
   fails fast with `Missing Gemini auth: set the GEMINI_OAUTH_CREDS secret`.
2. **Run Gemini** sets `GOOGLE_GENAI_USE_GCA=true`, which makes the CLI select the
   `oauth-personal` auth type in non-interactive mode, and
   `GEMINI_FORCE_ENCRYPTED_FILE_STORAGE=false`, which keeps it on the plain-file path.
3. **Remove Gemini login** deletes the file right after the run (`if: always()`), before
   commit/push, analysis and diagnostics.

Verified against gemini-cli 0.67.0 (`packages/core/src/code_assist/oauth2.ts`
`fetchCachedCredentialsList` / `cacheCredentials`, `packages/core/src/core/contentGenerator.ts`
`getAuthTypeFromEnv`): with no usable cached login the CLI exits 41 with "Manual
authorization is required but the current session is non-interactive" instead of
waiting for a browser.

**Token refresh.** The access token lasts an hour; the CLI refreshes it from the stored
`refresh_token` with google-auth-library, which keeps the existing refresh token
(Google does not rotate it). So, unlike `CODEX_AUTH_JSON`, nothing is written back to
the secret. The secret only needs replacing if the login is revoked or signed out.

**Creating the secret (one-off, owner).** On a machine with a browser, sign in with an
isolated home so no other gemini/agy state is touched, then load the file straight into
the secret without displaying it:

```bash
HOME="$HOME/.codex/gemini-hosted-login" gemini   # choose "Sign in with Google", then /quit
gh secret set GEMINI_OAUTH_CREDS --repo stranske/Workflows < "$HOME/.codex/gemini-hosted-login/.gemini/oauth_creds.json"
```

**Quota.** Runs spend the same personal subscription quota as other sessions on that
Google account; a 429 "quota reached" is a capacity failure, not an auth failure.

**Exposure.** The agent runs with `--approval-mode yolo` in the job that holds the file,
so the agent process can read the login while it runs, the same exposure codex has to
`~/.codex/auth.json`.

---

## Headless Invocation

Keepalive and other callers run the CLI in headless mode with the assembled
prompt passed on the command line:

```bash
gemini -p "<prompt text>" --approval-mode yolo
```

- `-p` runs non-interactively: the CLI applies tools/edits and prints the final
  assistant message to stdout.
- `--approval-mode yolo` lets the CLI apply file edits and run tool calls
  without confirmation (analogous to Claude's `--dangerously-skip-permissions`
  or Cursor's `--force`). Set workflow input `skip_permissions: false` to omit
  this flag for read-only / review mode.

Stdout is captured to `gemini-output*.md` and tee'd to `gemini-session*.log`
for debugging.

---

## Output Path (Plain Text)

The runner deliberately does **not** pass `--output-format json`. Gemini's JSON
output shape has been unstable across CLI releases; the workflow uses the
default plain-text stdout instead.

That text path is shared with Claude and Cursor in `runner_lib`:

- Prompt assembly: `scripts.runner_lib assemble-prompt --provider gemini`
- Output parsing: `scripts.runner_lib parse-output --provider gemini`

The workflow base64-encodes the captured stdout as `final-message`, matching
the cursor/claude text contract (not Codex's JSONL stream).

---

## Related Files

| File | Purpose |
|------|---------|
| `.github/workflows/reusable-gemini-run.yml` | Reusable runner workflow |
| `.github/agents/registry.yml` | Agent registration and `GEMINI_OAUTH_CREDS` requirement |
| `agents-keepalive-loop.yml` | Keepalive dispatch for `agent:gemini` PRs |
| `docs/LABELS.md` | `agent:gemini` label behavior |
| `docs/ci/WORKFLOW_OUTPUTS.md` | Runner output contract |
