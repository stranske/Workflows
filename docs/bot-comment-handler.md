# Bot Comment Handler

Automatically addresses review comments from bots (Copilot, CodeRabbit, etc.) using the configured AI coding agent.

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│         reusable-bot-comment-handler.yml (Workflows repo)       │
│  - Collects unresolved bot comments via GitHub API             │
│  - Detects agent from PR labels (agent:codex, agent:claude)    │
│  - Posts @agent command to trigger fix                          │
│  - Creates issue for unaddressable items                        │
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

- Comment threads with fixes are resolved automatically
- Skipped/complex items can be turned into follow-up issues
- Summary posted to workflow run

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

### 4. Ensure secrets

The workflow uses the same secrets as other agent workflows:
- `SERVICE_BOT_PAT` or GitHub App credentials
- Same permissions as keepalive

## Usage

### Manual (Label Trigger)

1. Open a PR with bot review comments
2. Add the `autofix:bot-comments` label
3. Workflow collects comments and dispatches agent
4. Label is automatically removed after processing

### Automatic (Agent PRs)

For PRs with `agent:codex` or other agent labels:
1. Gate workflow completes successfully
2. Bot comment handler checks for unresolved comments
3. If found, dispatches agent to address them
4. Agent fixes flow into normal keepalive cycle

### Manual Dispatch

```bash
gh workflow run agents-bot-comment-handler.yml \
  -f pr_number=123 \
  -f dry_run=true
```

## Integration with Keepalive

The bot comment handler runs **in parallel** with the normal keepalive cycle:

```
Push → Gate runs → Bot comment handler checks for comments
                 → Keepalive evaluates tasks
                 
Both can trigger agent, but concurrency group ensures orderly execution
```

The agent command posted by bot comment handler goes through `agents-pr-meta.yml`, which uses the same concurrency group as keepalive, preventing race conditions.

## Troubleshooting

### No comments found

- Check that bot authors match (case-sensitive)
- Verify comments are review comments (not issue comments)
- Check if human already replied (skipped by default)

### Agent not triggered

- Verify PR has an agent label or workflow is using correct default
- Check secrets are configured
- Review workflow run logs

### Agent doesn't address all comments

- Some suggestions may not have enough context
- Agent may skip suggestions it deems incorrect
- Check commit message for agent's reasoning

## Inputs Reference

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `pr_number` | string | required | PR number to process |
| `dry_run` | boolean | false | Preview without changes |
| `bot_authors` | string | `copilot[bot],github-actions[bot],coderabbitai[bot]` | Bot usernames to process |
| `skip_if_human_replied` | boolean | true | Skip threads with human replies |

## Outputs Reference

| Output | Description |
|--------|-------------|
| `comments_found` | Whether unresolved bot comments were found |
| `comments_count` | Number of comments found |
| `agent_triggered` | Whether agent was dispatched |
