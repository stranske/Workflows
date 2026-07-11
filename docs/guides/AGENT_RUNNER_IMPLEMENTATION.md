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
8. [Common Pitfalls](#8-common-pitfalls)

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

### Adding a New Agent CLI

When integrating a new agent (e.g., Gemini, GitHub Models), determine:

1. **Can the agent commit?** If the agent has filesystem write access and can run shell commands, it can `git commit`. Your runner must implement unpushed commit detection.
2. **What output format?** Prefer structured output (JSONL, JSON) over plain text. Capture session logs separately from the final message.
3. **What sandbox model?** Document the agent's sandbox/permission model in the registry entry.

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
2. **All changes are artifacts** — After `git add -A` and artifact filtering (`git reset HEAD --`), `git diff --cached --quiet` is true. Check for unpushed commits here too.

Missing either check means agent work gets silently discarded.

### Reference Implementations

- Codex: `reusable-codex-run.yml` lines ~1202-1243 (zero-changes check) and ~1325-1341 (post-filter check)
- Claude: `reusable-claude-run.yml` lines ~912-917 (zero-changes check) and ~954-961 (post-filter check)

---

## 3. Artifact Filtering

Agent runs produce temporary files that must not be committed. Use `git add -A` followed by `git reset HEAD --` to unstage known artifacts. This keeps the files on disk (available for upload as workflow artifacts) while preventing them from entering the commit.

### Exclusion List

```bash
git add -A
git reset HEAD -- \
  claude-output*.md \
  claude-prompt*.md \
  claude-session*.jsonl \
  claude-analysis*.json \
  codex-output*.md \
  codex-prompt*.md \
  codex-session-*.jsonl \
  codex-analysis-*.json \
  .coverage \
  .workflows-lib \
  .github/scripts/node_modules \
  .workflows-lib/.github/scripts/node_modules \
  node_modules \
  coverage.xml \
  pr_body.md \
  autofix_report_enriched.json \
  poetry.lock \
  2>/dev/null || true
```

### Rules

- **Agent-specific artifacts** (e.g., `claude-output*.md`, `codex-session*.jsonl`) — always exclude. These are captured as workflow artifacts separately.
- **Build artifacts** (`.coverage`, `coverage.xml`, `node_modules`) — always exclude. These come from test runs during the agent session.
- **Submodule checkouts** (`.workflows-lib`) — always exclude. This is a separate sparse checkout, not part of the consumer repo.
- **When adding a new agent**, add its output files to this list in **both** runners (Claude and Codex) so cross-agent artifacts from shared workspaces don't leak.
- Use `2>/dev/null || true` because some globs may not match — that's expected.

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
4. git add -A
5. Unstage artifacts (git reset HEAD --)
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

## 8. Common Pitfalls

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
**Cause:** `git add -A` staged everything, and artifact filtering (`git reset HEAD --`) didn't cover the file.
**Fix:** Add the file pattern to the exclusion list in §3. Update **all** runner workflows, not just the one that hit the issue.

### `git commit || true` hiding failures

**Symptom:** Runner reports success but no commit SHA, or downstream steps behave unexpectedly.
**Cause:** `|| true` swallowed a commit failure (e.g., empty commit, hook rejection).
**Fix:** Use `|| { echo "::error::git commit failed"; exit 1; }` instead.

### `.workflows-lib` submodule staged

**Symptom:** Commit includes changes to `.workflows-lib` directory (a sparse checkout of the Workflows repo used for shared scripts).
**Cause:** `git add -A` stages everything, including the separate checkout.
**Fix:** Already in the artifact exclusion list (§3). Verify it's present if you see this.

### Agent CLI not found

**Symptom:** `command not found: codex` or `command not found: claude` in the runner step.
**Cause:** The CLI installation step failed or used the wrong version.
**Fix:** Check the install step. Codex uses `npm install -g @openai/codex@$VERSION`. Claude uses `npm install -g @anthropic-ai/claude-code@$VERSION`. Version is configurable via the `codex_cli_version` / `claude_cli_version` input.

---

## Checklist for New Agent Runners

When building a new `reusable-<agent>-run.yml`:

- [ ] CLI invocation captures structured session logs (JSONL or equivalent)
- [ ] Unpushed commit detection at **both** early-exit points (zero-changes and post-filter)
- [ ] Artifact exclusion list includes new agent's output files
- [ ] Existing runners' exclusion lists updated with new agent's artifacts
- [ ] Commit failures fail loudly (no `|| true`)
- [ ] Pre-push fetch + rebase handles concurrent branch updates
- [ ] Push retry loop (3 attempts, exponential backoff)
- [ ] Base64 encoding of final message for output contract
- [ ] Error classification step populates `error-category`, `error-type`, `error-recovery`
- [ ] Agent registered in `.github/agents/registry.yml`
- [ ] All outputs from [agent-runner-output.md](../contracts/agent-runner-output.md) are set on every code path

---

## See Also

- [Agent Runner Output Contract](../contracts/agent-runner-output.md) — required inputs/outputs
- [Multi-Agent Routing](../keepalive/MULTI_AGENT_ROUTING.md) — how the keepalive loop dispatches to runners
- [Keepalive Agents Guidance](../keepalive/Agents.md) — required reading for keepalive changes
- [Dual-Location Sync Gotcha](dual-location-sync-gotcha.md) — when updating files that exist in both `.github/` and `templates/consumer-repo/`
- [Agent Registry](../../.github/agents/registry.yml) — agent configuration
