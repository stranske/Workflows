# Bot Comment Handler

Automatically addresses review comments from bots (Copilot, CodeRabbit, etc.) using the configured AI coding agent.

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│         reusable-bot-comment-handler.yml (Workflows repo)       │
│  - Collects unresolved bot comments via GitHub API             │
│  - Detects agent from PR labels (agent:codex, agent:claude)    │
│  - Posts @agent command to trigger fix                          │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
     Label trigger     Gate completion    Manual dispatch
     (one-off PRs)     (agent PRs)       (testing)
```

## Triggers

| Trigger | When | Use Case |
|---------|------|----------|
| `autofix:bot-comments` label | Manual | One-off PRs, ad-hoc fixes |
| Gate workflow completion | Automatic | Agent PRs (has `agent:*` label) |
| `workflow_dispatch` | Manual | Testing, debugging |

## Agent Selection

The workflow reads the PR's labels to determine which agent to use:

| Label | Agent | Workflow |
|-------|-------|----------|
| `agent:codex` | Codex CLI | `reusable-codex-run.yml` |
| (none) | Codex (default) | `reusable-codex-run.yml` |

**To switch agents:** Change the PR label. No workflow changes needed.

Only `agent:codex` is currently implemented in this repository. Other `agent:*` labels may be reserved for future expansion.

## Bot Authors

By default, the workflow processes comments from:
- `copilot[bot]` - GitHub Copilot code review
- `github-actions[bot]` - GitHub Actions (lint, type check suggestions)
- `coderabbitai[bot]` - CodeRabbit AI review

Configure via the `bot_authors` input.

## Behavior

### What Gets Processed

- ✅ Unresolved review comments from known bots
- ✅ Inline code suggestions
- ❌ Comments where a human has already replied (skipped by default)
- ❌ General PR comments (not inline reviews)
- ❌ Resolved threads

### Agent Instructions

The agent is instructed to:
1. **Fix** suggestions that improve the code
2. **Skip** suggestions that don't apply or are incorrect
3. **Document** decisions in the commit message

### After Processing

- Agent commits fixes with message documenting what was addressed vs skipped
- Summary posted to workflow run showing all comments found
- Skipped/complex items are highlighted in the summary for potential follow-up

## Consumer Repo Setup

### 1. Add the workflow

Copy `agents-bot-comment-handler.yml` to `.github/workflows/`:

```bash
curl -sL https://raw.githubusercontent.com/stranske/Workflows/v1/templates/consumer-repo/.github/workflows/agents-bot-comment-handler.yml \
  -o .github/workflows/agents-bot-comment-handler.yml
```

### 2. Add the prompt template

```bash
mkdir -p .github/codex/prompts
curl -sL https://raw.githubusercontent.com/stranske/Workflows/v1/templates/consumer-repo/.github/codex/prompts/fix_bot_comments.md \
  -o .github/codex/prompts/fix_bot_comments.md
```

### 3. Create the label

Create `autofix:bot-comments` label in your repository:
- **Name:** `autofix:bot-comments`
- **Color:** `#7057ff` (purple)
- **Description:** Trigger bot to address review bot comments

## Usage

### One-off PRs

Add the `autofix:bot-comments` label to any PR with bot review comments. The workflow will:
1. Collect all unresolved bot comments
2. Post `@<agent>` command to trigger the agent
3. Remove the label after processing

### Agent PRs (Automatic)

For PRs created by agents (with `agent:*` labels), the workflow automatically runs after Gate completes:
1. Checks if Gate succeeded
2. Collects any bot review comments
3. Dispatches the agent to address them

### Testing

```bash
# Dry run - see what would be processed
gh workflow run agents-bot-comment-handler.yml -f pr_number=123 -f dry_run=true

# Full run
gh workflow run agents-bot-comment-handler.yml -f pr_number=123
```

## Configuration

### Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `pr_number` | (required) | PR number to process |
| `dry_run` | `false` | Preview without triggering agent |
| `bot_authors` | `copilot[bot],github-actions[bot],coderabbitai[bot]` | Bot login names to process |
| `skip_if_human_replied` | `true` | Skip threads with human replies |

### Secrets

| Secret | Required | Description |
|--------|----------|-------------|
| `SERVICE_BOT_PAT` | No | PAT for service bot account |
| `GH_APP_CLIENT_ID` | No | GitHub App client ID (preferred App auth) |
| `GH_APP_ID` | No | Legacy GitHub App ID fallback |
| `GH_APP_PRIVATE_KEY` | No | GitHub App private key |

The canonical Workflows repo wrapper passes `WORKFLOWS_APP_CLIENT_ID`,
`WORKFLOWS_APP_ID`, and `WORKFLOWS_APP_PRIVATE_KEY` into the reusable handler so
the live Workflows path can prove client-ID App auth end to end. Consumer repo
templates still use the optional `GH_APP_*` secrets and continue to fall back to
`SERVICE_BOT_PAT` or `GITHUB_TOKEN` when App auth is not configured.

Each run uploads warning-only App auth coverage artifacts:

- `bot-comment-auth-coverage-wrapper-<run_id>` records the canonical wrapper
  `auth_mode` (`client-id`, `legacy-app-id`, or `none`) plus boolean secret
  coverage for `WORKFLOWS_APP_CLIENT_ID`, `WORKFLOWS_APP_ID`, and
  `WORKFLOWS_APP_PRIVATE_KEY`.
- `bot-comment-auth-coverage-reusable-<run_id>` records the reusable handler
  `auth_mode` plus boolean secret coverage for the App credentials passed by the
  caller. In consumer repos these are typically `GH_APP_CLIENT_ID`,
  `GH_APP_ID`, and `GH_APP_PRIVATE_KEY`.

Both artifacts use schema `workflows-bot-comment-auth-coverage/v1` and do not
include secret values. A `legacy-app-id` mode means migration is still incomplete;
do not remove the legacy fallback until active runs report `client-id` or `none`.
Weekly metrics selects recent bot-comment auth artifacts and writes
`bot-comment-auth-coverage-summary.json` with schema
`workflows-bot-comment-auth-coverage-summary/v1`. The default policy expects the
canonical wrapper to reach `client-id` while allowing reusable calls to remain
`client-id` or `none`; hard blocking remains disabled unless explicitly approved
with repository variables.

Repository variables can make the policy stricter without changing workflow
code:

| Variable | Default | Description |
|----------|---------|-------------|
| `BOT_COMMENT_WRAPPER_EXPECTED_AUTH_MODE` | `client-id` | Expected canonical wrapper mode |
| `BOT_COMMENT_REUSABLE_EXPECTED_AUTH_MODE` | empty | Optional expected reusable caller mode, usually `client-id` or `none` |
| `BOT_COMMENT_REUSABLE_ALLOWED_AUTH_MODES` | `client-id,none` | Allowed reusable caller modes |
| `BOT_COMMENT_AUTH_COVERAGE_MODE` | `warning-only` | Use `hard-block` only after explicit approval |
| `BOT_COMMENT_AUTH_HARD_BLOCK_APPROVED` | `false` | Required confirmation before hard blocking can fail weekly metrics |

The weekly summary also includes `organic_evidence` with schema
`workflows-bot-comment-auth-organic-evidence/v1`. This warning-only contract
counts bot-comment auth records by `event_name` and can require real
`pull_request` and `workflow_run` evidence for the wrapper and reusable handler.
Configure it with:

- `BOT_COMMENT_AUTH_REQUIRED_ORGANIC_EVENTS` (default:
  `pull_request,workflow_run`)
- `BOT_COMMENT_AUTH_ORGANIC_COMPONENTS` (default:
  `agents-bot-comment-handler-wrapper,reusable-bot-comment-handler`)
- `BOT_COMMENT_AUTH_ORGANIC_EXPECTED_MODE` (default: `client-id`)

Missing or legacy organic evidence is reported as blockers such as
`missing-organic-<component>-<event>` or
`legacy-organic-<component>-<event>`. These remain warning-only unless the
overall bot-comment auth coverage hard-block policy is explicitly approved.

## Troubleshooting

### No comments found

- Check that bot authors match exactly (including `[bot]` suffix)
- Verify comments are review comments, not PR comments
- Check if threads were already resolved

### Agent not triggered

- Ensure `dry_run` is not enabled
- Check workflow permissions (needs `pull-requests: write`)
- Verify authentication tokens are configured

### Gate trigger not working

- Ensure PR has an `agent:*` label
- Check that Gate workflow completed successfully
- Verify workflow_run trigger is configured correctly
