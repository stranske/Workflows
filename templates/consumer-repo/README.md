# Consumer Repo Workflow Templates

These templates are designed to be copied to consumer repositories that want to use
the centralized CI and automation workflows from stranske/Workflows.

## Quick Start

1. Copy the relevant workflow files to your repo's `.github/workflows/` directory
2. Configure required secrets in your repository settings
3. Adjust input parameters as needed
4. For agent workflows, copy required scripts (see below)

## Available Templates

### Core CI & Quality

| File | Purpose | Required Secrets |
|------|---------|-----------------|
| `ci.yml` | Python CI (lint, format, tests, typecheck) | None |
| `pr-00-gate.yml` | Gate workflow for merge enforcement | None |
| `autofix.yml` | Auto-fix lint/format issues | `SERVICE_BOT_PAT` |
| `autofix-versions.env` | Pin tool versions for autofix | N/A |

### Agent Workflows (Codex/CLI)

| File | Purpose | Required Secrets |
|------|---------|-----------------|
| `agents-issue-intake.yml` | Creates PRs from labeled issues | `SERVICE_BOT_PAT`, `OWNER_PR_PAT` |
| `agents-keepalive-loop.yml` | Runs Codex CLI after Gate passes | `CODEX_AUTH_JSON` or `WORKFLOWS_APP_*` |
| `agents-pr-meta.yml` | Updates PR status summaries | `SERVICE_BOT_PAT` |
| `agents-orchestrator.yml` | (Legacy) Scheduled keepalive sweeps | `SERVICE_BOT_PAT`, `ACTIONS_BOT_PAT` |
| `agents-bot-comment-handler.yml` | Processes @codex commands | `SERVICE_BOT_PAT` |
| `agents-guard.yml` | Security gate for agent workflows | None |
| `agents-verifier.yml` | Validates agent completions | `SERVICE_BOT_PAT` |
| `agents-autofix-loop.yml` | Autofix integration with keepalive | `SERVICE_BOT_PAT` |

**Note:** `agents-orchestrator.yml` is legacy. New setups should use `agents-keepalive-loop.yml` which integrates with the Gate workflow for more reliable triggering.

## Architecture

### Workflow Pattern: "Thin Caller" + Dual Checkout

These templates follow the **thin caller pattern** with **dual checkout** for script access:
- **Triggers and permissions** are defined locally (required by GitHub)
- **All logic** is delegated to reusable workflows or centralized scripts
- **Consumer repos** use dual checkout: consumer code + Workflows scripts

#### Dual Checkout Example
```yaml
steps:
  - name: Checkout consumer repository
    uses: actions/checkout@v6
    with:
      path: consumer

  - name: Checkout Workflows scripts
    uses: actions/checkout@v6
    with:
      repository: stranske/Workflows
      ref: main
      sparse-checkout: .github/scripts
      path: workflows-lib
```

This pattern allows:
- Consumer repos to remain lightweight (no script duplication)
- Central script updates automatically propagate to all consumers
- Consumer-specific configuration in consumer repo

### Keepalive Architecture

The current keepalive system uses a **Gate-triggered loop** rather than scheduled orchestration:

```
1. PR labeled with agent:codex
2. Gate workflow completes (success/failure)
3. agents-keepalive-loop evaluates conditions
4. If eligible, runs Codex CLI via reusable-codex-run.yml
5. Codex makes changes, pushes commits
6. Gate runs again → loop continues
```

Key components:
- **agents-keepalive-loop.yml**: Triggered by Gate completion, PR labels
- **agents-pr-meta.yml**: Updates PR status summary with task progress
- **agents-guard.yml**: Security checks before agent execution
- **.github/codex/prompts/**: Agent instruction templates
- **.github/codex/AGENT_INSTRUCTIONS.md**: Agent-specific guidelines

## Required Scripts for Consumer Repos

### For CI (ci.yml)
Consumer repos must include these scripts for the reusable Python CI workflow:

1. **Create folders** if they don't exist:
   - `scripts/`
   - `tools/`

2. **Copy reference scripts** from templates:
   - `templates/consumer-repo/scripts/sync_test_dependencies.py` → `scripts/sync_test_dependencies.py`
   - `templates/consumer-repo/tools/resolve_mypy_pin.py` → `tools/resolve_mypy_pin.py`

### For Agent Workflows (Codex)
Agent workflows require additional configuration files:

1. **Create .github/codex directory structure**:
   ```
   .github/
   └── codex/
       ├── AGENT_INSTRUCTIONS.md
       └── prompts/
           ├── keepalive_next_task.md
           └── other_prompts.md
   ```

2. **Copy template files**:
   - `templates/consumer-repo/.github/codex/AGENT_INSTRUCTIONS.md`
   - `templates/consumer-repo/.github/codex/prompts/keepalive_next_task.md`

3. **Required scripts directory**:
   - `templates/consumer-repo/.github/scripts/` → `.github/scripts/`
   - Includes: `issue_scope_parser.js`, `issue_context_utils.js`, `prompt_injection_guard.js`

## Security & Workflow Pinning

These templates use `@main` for workflow references (e.g., `stranske/Workflows/.github/workflows/...@main`).
This is intentional for first-party consumer repos owned by the same account, allowing
automatic updates without PR churn.

**For third-party or security-sensitive deployments:**
- Pin to a specific commit SHA: `@abc123def456...`
- Or use version tags when available: `@v1` (points to latest v1.x release)

## Required Secrets

### Core Secrets

| Secret | Purpose | Who provides |
|--------|---------|--------------|
| `SERVICE_BOT_PAT` | Bot account for comments/labels | stranske-automation-bot |
| `OWNER_PR_PAT` | Create PRs on behalf of user | Repository owner |

### Agent Workflow Secrets (Codex CLI)

| Secret | Purpose | Alternative |
|--------|---------|-------------|
| `CODEX_AUTH_JSON` | ChatGPT auth for Codex CLI | Recommended for Codex |
| `WORKFLOWS_APP_ID` | GitHub App ID | Use instead of CODEX_AUTH_JSON |
| `WORKFLOWS_APP_PRIVATE_KEY` | GitHub App private key | Required with APP_ID |

**Note:** Choose either `CODEX_AUTH_JSON` (ChatGPT auth) OR the GitHub App credentials (`WORKFLOWS_APP_ID` + `WORKFLOWS_APP_PRIVATE_KEY`), not both.

### Legacy Secrets (for agents-orchestrator.yml)

| Secret | Purpose | Note |
|--------|---------|------|
| `ACTIONS_BOT_PAT` | Workflow dispatch triggers | Only needed for orchestrator |

## Required Repository Variables

| Variable | Purpose | Default | Example |
|----------|---------|---------|---------|
| `ALLOWED_KEEPALIVE_LOGINS` | Users allowed to trigger keepalive | `stranske` | `user1,user2,user3` |

## Required Environments

Agent workflows use GitHub Environments for approval gates and secret management:

| Environment | Purpose | Required For |
|-------------|---------|--------------|
| `agent-standard` | Standard agent execution | All agent workflows |
| `agent-elevated` | Elevated permissions (if needed) | Security-sensitive operations |

Create these environments in: **Settings** → **Environments** → **New environment**

## Agent Labels

The keepalive system uses PR labels for routing and control:

### Agent Selection
| Label | Agent | Workflow |
|-------|-------|----------|
| `agent:codex` | Codex CLI (gpt-5.2-codex) | `reusable-codex-run.yml` |
| `agent:claude` | Claude (future) | `reusable-claude-run.yml` |

### Control Labels
| Label | Effect |
|-------|--------|
| `agents:pause` | Halts all agent activity on PR |
| `agents:max-parallel:N` | Overrides concurrent run limit (default: 1) |
| `needs-human` | Auto-added after repeated failures, blocks keepalive |

## Keepalive Behavior

### Activation Requirements
Keepalive dispatches an agent only when **ALL** conditions are met:
1. PR has an `agent:*` label (e.g., `agent:codex`)
2. Gate workflow completed successfully
3. PR body contains unchecked tasks in Automated Status Summary
4. Not at concurrency limit (default: 1 concurrent run per PR)
5. No `agents:pause` or `needs-human` labels present

### Progress Tracking
- Agent updates checkboxes in PR body after completing tasks
- `agents-pr-meta.yml` extracts task status and updates summary
- Keepalive stops when all acceptance criteria are checked complete

### Failure Handling
After 3 consecutive failures:
1. Keepalive pauses and adds `needs-human` label
2. Check the failure reason in keepalive summary comment
3. Fix issues, then remove `needs-human` label to resume

### Manual Control
- **Pause**: Add `agents:pause` label
- **Resume**: Remove `agents:pause` or `needs-human` label
- **Restart**: Remove and re-add the `agent:*` label
- **Force retry**: Use workflow_dispatch with PR number

## Customization

### CI Configuration
Adjust inputs in `ci.yml`:
```yaml
with:
  python-version: '3.12'  # Change Python version
  run-mypy: 'true'        # Enable/disable type checking
  working-directory: '.'  # Set working directory
```

### Keepalive Timing
Adjust schedule in `agents-keepalive-loop.yml`:
```yaml
concurrency:
  group: keepalive-${{ github.event.workflow_run.pull_requests[0].number || ... }}
  cancel-in-progress: false  # Never cancel in-progress keepalive
```

**Note:** Don't change the concurrency group pattern - it ensures one keepalive per PR.

### Agent Prompt Customization
Customize agent behavior by editing:
- `.github/codex/AGENT_INSTRUCTIONS.md` - Repository-specific guidelines
- `.github/codex/prompts/keepalive_next_task.md` - Task execution instructions

### Autofix Configuration
Customize commit messages and labels in `autofix.yml`:
```yaml
with:
  commit_prefix: 'style: '
  commit_label: 'autofix'
```

## Issue-to-PR Workflow

When using agent workflows, the recommended flow is:

1. **Create Issue** with structured content:
   ```markdown
   ## Scope
   What needs to be done
   
   ## Tasks
   - [ ] Task 1
   - [ ] Task 2
   
   ## Acceptance Criteria
   - [ ] All tests pass
   - [ ] Code is documented
   ```

2. **Label Issue** with `agent:codex` (or appropriate agent)

3. **agents-issue-intake.yml** creates a PR from the issue

4. **agents-pr-meta.yml** parses issue and updates PR body with Automated Status Summary

5. **Gate workflow** runs (CI checks)

6. **agents-keepalive-loop.yml** triggers after Gate:
   - Evaluates if eligible (checklist has unchecked items)
   - Runs Codex CLI with task context
   - Codex implements changes and pushes

7. **Loop continues** until all tasks checked complete

## Troubleshooting

### Common Issues

**1. Keepalive not triggering**
- Check PR has `agent:*` label
- Verify Gate workflow passed
- Ensure PR body has Automated Status Summary with unchecked tasks
- Check for `agents:pause` or `needs-human` labels
- Review keepalive summary comment for skip reasons

**2. No Automated Status Summary**
- Ensure issue has Scope/Tasks/Acceptance sections
- Run `agents-pr-meta.yml` manually via workflow_dispatch
- Check PR description links to source issue (e.g., `#123`)

**3. Codex not making changes**
- Check `CODEX_AUTH_JSON` secret is configured
- Review Codex session logs in workflow run
- Verify `.github/codex/` prompts are present
- Check for prompt injection blocks (see agents-guard.yml logs)

**4. "Missing repo context" errors**
- Consumer repo using old template without dual checkout
- Update to current `agents-keepalive-loop.yml` template
- Ensure `workflows-lib` checkout step is present

**5. Permission errors**
- Verify required secrets are set (SERVICE_BOT_PAT, etc.)
- Check environment `agent-standard` exists
- Ensure PAT has required scopes: `repo`, `workflow`, `write:packages`

### Debug Mode
Enable debug logging by setting repository variable:
```
DRY_RUN = true
```

This runs workflows in preview mode without making actual changes.

## Migration from Legacy Orchestrator

If migrating from `agents-orchestrator.yml` to `agents-keepalive-loop.yml`:

1. **Add Gate workflow** (`pr-00-gate.yml`) if not present
2. **Copy new keepalive-loop** template
3. **Update concurrency groups** to use PR number
4. **Test with dry_run** enabled
5. **Remove orchestrator** workflow once confirmed working
6. **Remove `ACTIONS_BOT_PAT`** secret (no longer needed)

Key differences:
- Orchestrator: scheduled polling every 30 minutes
- Keepalive Loop: event-driven, triggers after Gate completes
- Loop is more responsive and uses fewer Actions minutes

## Further Reading

- [Keepalive Goals & Plumbing](../../docs/keepalive/GoalsAndPlumbing.md) - Detailed keepalive architecture
- [Workflow System Docs](../../docs/ci/WORKFLOWS.md) - Reusable workflow reference
- [Agent Instructions Template](../.github/codex/AGENT_INSTRUCTIONS.md) - Example agent configuration
- [Multi-Agent Routing](../../docs/keepalive/MULTI_AGENT_ROUTING.md) - Adding new agents
