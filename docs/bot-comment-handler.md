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
| `agent:claude` | Claude | `reusable-claude-run.yml` |
| `agent:gemini` | Gemini | `reusable-gemini-run.yml` |
| (none) | Codex (default) | `reusable-codex-run.yml` |

**To switch agents:** Change the PR label. No workflow changes needed.

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
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/workflows/agents-bot-comment-handler.yml \
  -o .github/workflows/agents-bot-comment-handler.yml
```

### 2. Add the prompt template

```bash
mkdir -p .github/codex/prompts
curl -sL https://raw.githubusercontent.com/stranske/Workflows/main/templates/consumer-repo/.github/codex/prompts/fix_bot_comments.md \
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
| `GH_APP_ID` | No | GitHub App ID (alternative auth) |
| `GH_APP_PRIVATE_KEY` | No | GitHub App private key |

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
