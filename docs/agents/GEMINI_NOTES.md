# Gemini Runner Operator Notes

Short reference for operators and maintainers running the Gemini agent via
`reusable-gemini-run.yml` and keepalive routing (`agent:gemini`).

---

## Prerequisites

Consumer repos need a repository secret named `GEMINI_API_KEY` before
`agent:gemini` can run. The Workflows repo uses the same secret name; see
`.github/agents/registry.yml` for the registry entry.

---

## CLI Installation

The runner installs Google's Gemini CLI from npm when it is not already on
`PATH`:

```bash
npm install -g @google/gemini-cli
```

In CI, the **Ensure Gemini CLI** step in `reusable-gemini-run.yml` runs that
install globally. An optional workflow input `gemini_cli_version` pins the
package (for example `@1.2.3`); when empty, npm installs the latest published
release.

---

## Authentication

The Gemini CLI authenticates headlessly via the `GEMINI_API_KEY` environment
variable. The workflow:

1. Reads `secrets.GEMINI_API_KEY` during **Preflight auth**.
2. Exports it to `GEMINI_API_KEY` for the run step.
3. Fails fast with an auth error if the secret is missing.

No interactive login or OAuth flow is required in CI.

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
| `.github/agents/registry.yml` | Agent registration and `GEMINI_API_KEY` requirement |
| `agents-keepalive-loop.yml` | Keepalive dispatch for `agent:gemini` PRs |
| `docs/LABELS.md` | `agent:gemini` label behavior |
| `docs/ci/WORKFLOW_OUTPUTS.md` | Runner output contract |
