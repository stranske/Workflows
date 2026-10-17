# Agent Runner Implementation Guide

**Audience:** Developers and coding agents building or debugging agent runner workflows
**Prerequisites:** Familiarity with [Agent Runner Output Contract](../contracts/agent-runner-output.md) and [Multi-Agent Routing](../keepalive/MULTI_AGENT_ROUTING.md)

This guide covers the implementation patterns that every agent runner workflow (`reusable-*-run.yml`) must follow. It focuses on the mechanics — CLI invocation, commit detection, push logic — that the architecture-level docs intentionally leave out.

---

## Table of Contents

1. [CLI Invocation Patterns](#1-cli-invocation-patterns)
2. [Unpushed Commit Detection](#2-unpushed-commit-detection)
3. [Artifact Filtering](#3-artifact-filtering)
4. [Commit and Push Step](#4-commit-and-push-step)
5. [Push Retry with Rebase](#5-push-retry-with-rebase)
6. [Output Encoding](#6-output-encoding)
7. [Capability Effect Evidence](#7-capability-effect-evidence)
8. [Fail-Closed Guards Before the Agent Runs](#8-fail-closed-guards-before-the-agent-runs)
9. [Common Pitfalls](#9-common-pitfalls)

---

## 1. CLI Invocation Patterns

Each agent CLI has different flags, but the runner must handle the same concerns: prompt delivery, permission escalation, output capture, and session logging.

### Codex CLI

```bash
cmd=(
  codex exec
  --json                       # Stream JSONL events to stdout
  --skip-git-repo-check        # CI checkout is not a normal clone
  --sandbox "$SANDBOX"         # e.g., "workspace-write"
  --output-last-message "$OUTPUT_FILE"  # Final message to file
)
"${cmd[@]}" "$prompt_content" > "$SESSION_JSONL" 2>&1 || CODEX_EXIT=$?
```

Key points:
- `--json` streams structured events (tool calls, messages) to stdout as JSONL.
- `--output-last-message` writes only the final assistant message to a file for downstream parsing.
- `--sandbox workspace-write` lets Codex use `git add` and `git commit` inside its sandbox. The runner must detect these unpushed commits (see §2).

### Claude CLI

```bash
perm_flag=()
if [ "${SKIP_PERMISSIONS:-true}" = "true" ]; then
  perm_flag=("--dangerously-skip-permissions")
fi

claude -p "$prompt_content" \
  "${perm_flag[@]}" \
  "${extra_args[@]}" \
  >"$output_file" 2>&1
status=$?
```

Key points:
- `-p` (or `--print`) is a **fully agentic** mode — Claude can call tools including Bash, which means it can run `git commit`. The name is misleading; it is not a print-only/non-agentic mode.
- `--dangerously-skip-permissions` removes interactive approval prompts, required for unattended CI.
- With `--dangerously-skip-permissions`, Claude can execute arbitrary shell commands. This means it may `git add` and `git commit` during its run, leaving a clean working tree but unpushed commits. The commit step **must** detect this (see §2).

### Cursor CLI

```bash
cursor-agent -p "$prompt_content" --force --output-format text \
  "${extra_args[@]}" >"$output_file" 2>&1
```

`--force` applies edits without confirmation. The API key (`CURSOR_API_KEY`) is read from the
environment; the runner passes it to the run step's own `env:` only.

### Muse CLI

```bash
perm_flag=()
if [ "${SKIP_PERMISSIONS:-true}" = "true" ]; then
  perm_flag=(--disable-approval)        # skips prompts, KEEPS the sandbox
fi

"$MUSE_BIN" exec --prompt-file "$PROMPT_FILE" \
  --no-foreign-personal-context \
  --no-session-log \
  --max-model-steps "${MAX_MODEL_STEPS:-150}" \
  "${perm_flag[@]}" \
  ${MODEL:+--model "$MODEL"} \
  "${extra_args[@]}" \
  2>"$STDERR_FILE" | tee "$SESSION_LOG" > "$output_file"
status=${PIPESTATUS[0]}
```

Key points:
- `muse exec` runs one prompt headlessly and prints the final message to stdout; notices go to
  stderr. The CLI has no usage field in its JSON output, so the runner emits `duration-seconds`.
- Never use the flag that disables both approvals and the sandbox. `--disable-approval` is the
  unattended setting.
- On Linux the CLI needs a working bubblewrap sandbox (see §8). `--no-foreign-personal-context`
  keeps another tool's personal rules and skills out of a fleet worker.
- The CLI may commit on its own, so the unpushed-commit checks in §2 apply, and the commit author
  must be checked (§8).

### Adding a New Agent CLI

When integrating a new agent, determine:

1. **Can the agent commit?** If the agent has filesystem write access and can run shell commands, it can `git commit`. Your runner must implement unpushed commit detection.
2. **What output format?** Prefer structured output (JSONL, JSON) over plain text. Capture session logs separately from the final message.
3. **What sandbox model?** Document the agent's sandbox/permission model in the registry entry, and probe it on the runner (§8).
4. **Does a denial exit non-zero?** Some CLIs exit 0 when a permission is denied; the runner must detect "no work done" itself.
5. **Run the readiness evaluation first** ([Agent Readiness Evaluations](agent-readiness/README.md)).

The complete integration checklist, including everything outside the runner file, is
[Adding a New Coding Agent](ADD_NEW_AGENT.md).

---

## 2. Unpushed Commit Detection

**This is the most critical pattern in the runner.** Agents with shell access can commit during their run. When this happens, `git status --porcelain` shows no changes (clean working tree), but the commits haven't been pushed. Without explicit detection, the runner reports `changes-made=false` and the agent's work is silently lost.

### The Pattern

This check must run at **every** early-exit point where the runner would otherwise report no changes:

```bash
# After determining there are no uncommitted changes (git status clean)
REMOTE_URL="https://x-access-token:${PUSH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
git fetch "$REMOTE_URL" "$TARGET_BRANCH" 2>/dev/null || true

UNPUSHED_COMMITS=0
if git rev-parse "FETCH_HEAD" >/dev/null 2>&1; then
  # Remote branch exists — count commits ahead of remote
  UNPUSHED_COMMITS=$(git rev-list FETCH_HEAD..HEAD --count 2>/dev/null || echo "0")
else
  # Remote branch doesn't exist yet — all local commits are unpushed
  UNPUSHED_COMMITS=$(git rev-list HEAD --count 2>/dev/null || echo "0")
fi

if [ "$UNPUSHED_COMMITS" -gt 0 ]; then
  echo "Found ${UNPUSHED_COMMITS} unpushed commit(s) from agent — pushing them."
  COMMIT_SHA=$(git rev-parse HEAD)
  echo "commit-sha=${COMMIT_SHA}" >> "$GITHUB_OUTPUT"
  echo "changes-made=true" >> "$GITHUB_OUTPUT"

  # Rebase onto remote before pushing (see §5)
  if git rev-parse "FETCH_HEAD" >/dev/null 2>&1; then
    if ! git rebase FETCH_HEAD; then
      git rebase --abort 2>/dev/null || true
      git pull --no-rebase "$REMOTE_URL" "$TARGET_BRANCH" \
        --allow-unrelated-histories || true
    fi
    COMMIT_SHA=$(git rev-parse HEAD)
    echo "commit-sha=${COMMIT_SHA}" >> "$GITHUB_OUTPUT"
  fi
  git push --force-with-lease "$REMOTE_URL" "HEAD:${TARGET_BRANCH}"
  exit 0
fi
```

### Where to Place This Check

The runner has **two** points where it might exit early without pushing:

1. **Zero uncommitted changes** — `git status --porcelain` is empty. Check for unpushed commits here.
2. **All changes are artifacts** — After the shared staging helper runs, `git diff --cached --quiet` is true. Check for unpushed commits here too.

Missing either check means agent work gets silently discarded.

### Reference Implementations

- Codex: `reusable-codex-run.yml` lines ~1202-1243 (zero-changes check) and ~1325-1341 (post-filter check)
- Claude: `reusable-claude-run.yml` lines ~912-917 (zero-changes check) and ~954-961 (post-filter check)

---

## 3. Artifact Filtering

Agent runs produce temporary files that must not be committed. Every normal
runner and Codex's pre-timeout watchdog use the same executable contract:

```bash
python3 .workflows-lib/scripts/stage_agent_changes.py
```

The existing trusted Workflows scripts checkout supplies this helper, including
for consumer repositories. Keep `scripts` in that checkout's sparse paths. A
consumer-local helper or separately synced exclusion list is unnecessary.

### Rules

- Maintain exclusions once in `scripts/stage_agent_changes.py`. Add a new agent's
  root output patterns there so every runner receives the same filtering.
- Root runner outputs, root coverage reports, and auxiliary checkouts are
  excluded. Dependency and cache directories such as `node_modules` are excluded
  at any depth. Intentional source, tests, documentation, and `docs/evidence`
  proof remain eligible; a document under `docs/coverage` is still source.
- Already staged artifacts are unstaged without changing or deleting working
  files. Already staged source blobs retain their original content, including
  partially staged changes. Other eligible modifications, deletions, and
  untracked files are staged with literal, null-delimited Git paths.
- Treat helper failure as a staging failure. Do not fall back to unrestricted
  staging. New runtime outputs should normally be written under `RUNNER_TEMP`
  and uploaded from there instead of extending the exclusion contract.
- Validate changes with `tests/scripts/test_stage_agent_changes.py`, which uses
  real disposable Git repositories, and the runner artifact/wiring guards.

### Pre-timeout checkpoint

The Codex watchdog invokes the same helper and commits only if
`git diff --cached --quiet` reports eligible staged changes. A checkpoint with
only excluded artifacts creates no commit and leaves those artifacts on disk.
Existing unpushed commits retain their push path. A future runner watchdog must
use this contract too.

### Post-Filter Validation

After filtering, check if any staged changes remain:

```bash
if git diff --cached --quiet; then
  echo "No non-artifact changes to commit after filtering."
  # IMPORTANT: Still check for unpushed commits before exiting (see §2)
  ...
  echo "changes-made=false" >> "$GITHUB_OUTPUT"
  exit 0
fi
```

---

## 4. Commit and Push Step

The full commit step follows this sequence:

```
1. Count uncommitted changes (git status --porcelain)
2. If zero → check for unpushed commits → push or exit
3. Verify push token is available
4. Run python3 .workflows-lib/scripts/stage_agent_changes.py
5. Stop on staging failure; preserve staged source blobs and working files
6. If nothing staged → check for unpushed commits → push or exit
7. Show staged diff (::group:: for CI log folding)
8. git commit -m "$message" || exit 1    ← fail loudly, never || true
9. Fetch remote + rebase (§5)
10. Push with retry (§5)
```

### Commit Message Convention

```bash
# Codex:
commit_message="chore(codex-${MODE}): apply updates"
# Claude:
commit_message="Claude (${MODE}) automated update"
# With PR number:
commit_message+=" for PR #${PR_NUMBER}"
```

### Never Swallow Commit Failures

```bash
# WRONG — hides real errors:
git commit -m "$message" || true

# RIGHT — fail loudly so the workflow reports the error:
git commit -m "$message" || { echo "::error::git commit failed"; exit 1; }
```

---

## 5. Push Retry with Rebase

The PR branch may advance while the agent runs (e.g., concurrent autofix, another keepalive iteration). The runner must sync with the remote before pushing and retry on rejection.

### Pre-Push Sync

```bash
REMOTE_URL="https://x-access-token:${PUSH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
git fetch "$REMOTE_URL" "$target_branch" 2>/dev/null || true
if git rev-parse "FETCH_HEAD" >/dev/null 2>&1; then
  if ! git rebase FETCH_HEAD; then
    echo "::warning::Rebase failed; attempting merge strategy."
    git rebase --abort 2>/dev/null || true
    git pull --no-rebase "$REMOTE_URL" "$target_branch" \
      --allow-unrelated-histories || true
  fi
  sha="$(git rev-parse HEAD)"
  echo "commit-sha=$sha" >> "$GITHUB_OUTPUT"
fi
```

### Retry Loop

Wrap the push in a retry loop. On each retry, re-fetch and re-rebase to pick up any further changes:

```bash
for attempt in 1 2 3; do
  echo "Push attempt ${attempt}/3..."
  if git push "$REMOTE_URL" "HEAD:${target_branch}"; then
    echo "::notice::Push succeeded (attempt ${attempt})"
    exit 0
  fi
  echo "::warning::Push failed (attempt ${attempt})"
  if [ "$attempt" -lt 3 ]; then
    sleep $((attempt * 5))
    git fetch "$REMOTE_URL" "$target_branch" 2>/dev/null || true
    if git rev-parse "FETCH_HEAD" >/dev/null 2>&1; then
      if ! git rebase FETCH_HEAD; then
        git rebase --abort 2>/dev/null || true
        git pull --no-rebase "$REMOTE_URL" "$target_branch" \
          --allow-unrelated-histories || true
      fi
      sha="$(git rev-parse HEAD)"
      echo "commit-sha=$sha" >> "$GITHUB_OUTPUT"
    fi
  fi
done
echo "::error::Failed to push after 3 attempts."
exit 1
```

### Why `--force-with-lease` for Unpushed Commits

When pushing agent-created commits (from §2), use `--force-with-lease` rather than plain push. This is safe because we just fetched, so `--force-with-lease` only overwrites what we expect. For the normal commit path (where the runner creates the commit), a regular push suffices since rebase already linearized the history.

---

## 6. Output Encoding

The runner output contract requires base64-encoded `final-message`. Use `base64 -w 0` for single-line encoding (macOS doesn't have `-w`; fall back to `base64 | tr -d '\n'`):

```bash
encoded="$(
  printf '%s' "$output" | base64 -w 0 2>/dev/null || \
  printf '%s' "$output" | base64 | tr -d '\n'
)"
summary="$(
  printf '%s' "$output" | head -c 500 | tr '\n' ' ' | sed 's/  */ /g' || true
)"
```

Set both `final-message` (full, encoded) and `final-message-summary` (first 500 chars, plaintext) as outputs.

---

## 7. Capability Effect Evidence

All registry-backed runners expose the same optional capability/effect fields.
Validate them before invoking the agent:

```bash
PYTHONPATH="${GITHUB_WORKSPACE}/.workflows-lib:${GITHUB_WORKSPACE}" \
  python -m scripts.runner_lib normalize-evidence \
    --capability-id "$CAPABILITY_ID" \
    --effect-fingerprint "$EFFECT_FINGERPRINT" \
    --evidence-artifact-ref "$EVIDENCE_ARTIFACT_REF" \
    --supervision-mode "$SUPERVISION_MODE" \
    --capability-evidence-status "$CAPABILITY_EVIDENCE_STATUS" \
    --terminal-disposition "$TERMINAL_DISPOSITION"
```

An entirely empty record is valid for backwards compatibility. Partial,
malformed, oversized, or secret-like records fail closed. Do not parse these
values from the final message: the caller supplies typed intent and the runner
only validates and relays it. Downstream promotion remains Orchestrator-owned.

## 8. Fail-Closed Guards Before the Agent Runs

The run step normally carries `if: always()` so it can report on earlier failures. That means it
also runs after a setup step failed or was skipped. Make each guard explicit, in this order, and
exit non-zero with a named error and the standard error outputs set:

1. **Missing credential.** The preflight step records `missing=true` and an `error` output
   ("Missing <Agent> auth: set the <SECRET> secret"). The run step checks it first.
2. **Setup outcome.** Pass `steps.<install>.outcome` and `steps.<guard>.outcome` into the run step's
   env. Refuse to run the agent unless the CLI/sandbox step's outcome is exactly `success`. A
   *skipped* step is not a success: if an earlier step failed, GitHub skips the later setup step but
   still starts an `always()` step.
3. **Prompt integrity.** A rejected prompt template must stop the run.

Other rules in the same family:

- **Keep the credential out of `GITHUB_ENV`.** Writing it there exposes it to every later step in
  the job, including third-party actions. Read it from the run step's own `env:` block. A test
  (`test_no_agent_runner_exports_a_credential_through_github_env`) enforces this for every runner.
- **Install by download then run.** `curl -fsSL <url> -o "$file"; bash "$file"`, not a pipe to a
  shell, and pin a version when the vendor allows it.
- **Probe the sandbox, then fail by name.** Where the CLI needs bubblewrap, probe it, relax the
  user-namespace restriction if the runner image blocks it, probe again, and fail with a named
  error rather than continuing unsandboxed.
- **Check commit attribution on the first real commit.** Read `commits/<sha>` and compare the author
  with the agent. A CLI that commits under another vendor's identity makes author-based attribution
  credit the wrong agent; rewrite only *unpushed* commits to the agent's identity if the CLI cannot
  be configured.
- **Assert the work happened.** A CLI that can exit 0 without changing files (a historical failure
  of some agents) needs a runner-side check on the working tree or commit.

## 9. Common Pitfalls

### Silent loss of agent work

**Symptom:** Agent logs show it made changes, but `changes-made=false` and nothing was pushed.
**Cause:** Agent ran `git commit` via its shell tool. Working tree is clean, so the runner's `git status` check exits early without checking for unpushed commits.
**Fix:** Implement unpushed commit detection at every early-exit point (§2).

### Push rejected (fetch first)

**Symptom:** `! [rejected] HEAD -> branch (fetch first)` in the push step.
**Cause:** The remote branch advanced during the agent run (concurrent autofix, parallel keepalive iteration, manual push).
**Fix:** Fetch + rebase before push, with retry loop (§5).

### Artifact files committed

**Symptom:** `codex-output-42.md` or `.coverage` appears in the commit diff.
**Cause:** A commit path bypassed the shared staging helper, or a new runtime output was written inside the checkout without a matching exclusion.
**Fix:** Route the commit path through `scripts/stage_agent_changes.py` (§3). Prefer moving new runtime output to `RUNNER_TEMP`; if an exclusion is needed, update the shared helper and its disposable Git regression.

### `git commit || true` hiding failures

**Symptom:** Runner reports success but no commit SHA, or downstream steps behave unexpectedly.
**Cause:** `|| true` swallowed a commit failure (e.g., empty commit, hook rejection).
**Fix:** Use `|| { echo "::error::git commit failed"; exit 1; }` instead.

### `.workflows-lib` submodule staged

**Symptom:** Commit includes changes to `.workflows-lib` directory (a sparse checkout of the Workflows repo used for shared scripts).
**Cause:** A commit path bypassed the shared staging helper.
**Fix:** Use the helper in §3, which excludes auxiliary checkouts even when previously staged.

### Agent CLI not found

**Symptom:** `command not found: codex` or `command not found: claude` in the runner step.
**Cause:** The CLI installation step failed or used the wrong version.
**Fix:** Check the install step. Codex uses `npm install -g @openai/codex@$VERSION`. Claude uses `npm install -g @anthropic-ai/claude-code@$VERSION`. Version is configurable via the `codex_cli_version` / `claude_cli_version` input.

---

## Checklist for New Agent Runners

When building a new `reusable-<agent>-run.yml`:

- [ ] CLI invocation captures structured session logs (JSONL or equivalent)
- [ ] Unpushed commit detection at **both** early-exit points (zero-changes and post-filter)
- [ ] Shared staging helper includes the new agent's root output patterns
- [ ] Normal and watchdog commit paths invoke the shared helper; scripts checkout includes it
- [ ] Commit failures fail loudly (no `|| true`)
- [ ] Pre-push fetch + rebase handles concurrent branch updates
- [ ] Push retry loop (3 attempts, exponential backoff)
- [ ] Base64 encoding of final message for output contract
- [ ] Error classification step populates `error-category`, `error-type`, `error-recovery`
- [ ] Agent registered in `.github/agents/registry.yml`
- [ ] All outputs from [agent-runner-output.md](../contracts/agent-runner-output.md) are set on every code path
- [ ] Missing credential, failed or skipped CLI/sandbox setup and a rejected prompt each stop the run with a named error (§8)
- [ ] The credential is read only from the run step's `env:` and is never written to `GITHUB_ENV`
- [ ] Installer is downloaded then run; sandbox is probed on Linux
- [ ] The first real commit's author was read back and attributes to the agent
- [ ] `scripts/runner_lib/core.py` `PROVIDERS` includes the agent **and** the change was delivered to consumers (they run their own copy)

---

## See Also

- [Agent Runner Output Contract](../contracts/agent-runner-output.md) — required inputs/outputs
- [Multi-Agent Routing](../keepalive/MULTI_AGENT_ROUTING.md) — how the keepalive loop dispatches to runners
- [Keepalive Agents Guidance](../keepalive/Agents.md) — required reading for keepalive changes
- [Dual-Location Sync Gotcha](dual-location-sync-gotcha.md) — when updating files that exist in both `.github/` and `templates/consumer-repo/`
- [Agent Registry](../../.github/agents/registry.yml) — agent configuration
