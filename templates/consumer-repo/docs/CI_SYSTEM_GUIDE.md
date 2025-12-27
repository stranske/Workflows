# CI System Guide

This document describes the CI/CD system for this repository and how it
integrates with the [stranske/Workflows](https://github.com/stranske/Workflows)
repository for reusable automation.

## Table of Contents

1. [Overview](#overview)
2. [Workflows Repository Capabilities](#workflows-repository-capabilities)
3. [Local CI Configuration](#local-ci-configuration)
4. [Agent Automation System](#agent-automation-system)
5. [Troubleshooting](#troubleshooting)
6. [Quick Reference](#quick-reference)

---

## Overview

This repository uses a **hybrid CI approach**:

- **Local jobs**: Domain-specific validation for this project
- **Reusable workflows**: Standard CI from stranske/Workflows

```
┌─────────────────────────────────────────────────────────────┐
│                     This Repository                          │
│                    .github/workflows/ci.yml                  │
├─────────────────────────────────────────────────────────────┤
│  Local Jobs                │  Reusable Workflows            │
│  ─────────────────         │  ────────────────────────────  │
│  • Project-specific        │  • python-ci                   │
│    validation              │    (reusable-10-ci-python.yml) │
│  • Custom linting          │  • node-ci                     │
│                            │    (reusable-11-ci-node.yml)   │
├─────────────────────────────────────────────────────────────┤
│                           Gate                               │
│              Aggregates all job results                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Workflows Repository Capabilities

The [stranske/Workflows](https://github.com/stranske/Workflows) repository
provides:

### Reusable CI Workflows

| Workflow | Purpose | When to Use |
|----------|---------|-------------|
| `reusable-10-ci-python.yml` | Python lint (ruff), type check (mypy), test (pytest), coverage | Python projects with pyproject.toml |
| `reusable-11-ci-node.yml` | Node.js lint, format, type check, test | Node.js/TypeScript projects |
| `reusable-12-ci-docker.yml` | Docker build + smoke test | Projects with Dockerfile |
| `reusable-18-autofix.yml` | Automated code formatting fixes | All projects (via autofix label) |

### Agent Automation System

The Workflows repo includes a sophisticated agent automation system:

| Component | Purpose |
|-----------|---------|
| **Agents 63 Issue Intake** | Converts labeled issues into agent work items |
| **Agents 70 Orchestrator** | Central control for readiness, bootstrap, keepalive |
| **Agents 71-73 Codex Belt** | Dispatcher → Worker → Conveyor pipeline for PRs |
| **Keepalive System** | Monitors stalled agent PRs and nudges them |
| **Autofix** | Automatic formatting fixes on PRs |

### Key Features

- **Readiness probes**: Validates agent availability before work
- **Bootstrap**: Creates branches and PRs from labeled issues
- **Keepalive**: Monitors agent PRs and posts reminder comments
- **Conveyor**: Auto-merges successful PRs and cleans up
- **Watchdog**: Detects stalled automation

---

## Local CI Configuration

### Gate Workflow

The `pr-00-gate.yml` workflow aggregates all CI results for branch protection:

```yaml
# Triggered by: push to main, pull_request
# Required status: Gate / gate
```

If your repository has a custom Gate (not using `reusable-10-ci-python.yml`),
it will be specific to your project's needs and is **not synced** automatically.

### Branch Protection

Branch protection on `main` typically requires:
- `Gate / gate` status to succeed
- At least one approving review
- Force pushes blocked to preserve CI integrity

### Adding New Local Jobs

To add a domain-specific job:

1. Edit `.github/workflows/ci.yml` (or create a new workflow file)
2. Add your job with appropriate triggers
3. Include the job in the Gate aggregation (if using custom Gate)

---

## Agent Automation System

### Using Agent Labels

See [docs/LABELS.md](LABELS.md) for the complete label reference.

Quick start:

1. **Create an agent task**: Use the "Agent Task" issue template
2. **Add the label**: Apply `agent:codex` label to trigger automation
3. **Monitor progress**: Watch the linked PR for agent activity
4. **Intervene if needed**: Check for `agent:needs-attention` label

### Agent Workflow

```
Issue created → agent:codex label added
                      ↓
          Issue Intake validates
                      ↓
        Bootstrap creates branch + PR
                      ↓
         Agent works on the code
                      ↓
            CI runs on changes
                      ↓
    ┌─────────────────┴─────────────────┐
    │                                    │
 CI passes                          CI fails
    │                                    │
Conveyor merges               Keepalive nudges agent
```

---

## Troubleshooting

### CI is Failing

1. **Check the Actions tab**: Click on the failing workflow run
2. **Look at job logs**: Expand the failed job to see error details
3. **Try autofix**: Add the `autofix` label to attempt automatic fixes
4. **Check branch protection**: Ensure your branch is up to date with main

### Agent Not Responding

1. **Check issue labels**: Ensure `agent:codex` is present
2. **Look for attention label**: `agent:needs-attention` pauses processing
3. **Check PR status**: The agent works through the linked PR
4. **View keepalive comments**: These indicate agent activity status

### Autofix Not Running

1. **PR must not be a draft**: Convert to ready for review
2. **Must be same-repo PR**: Forks cannot trigger autofix
3. **Remove and re-add label**: Labels only trigger once per addition

### Workflow Sync Issues

Consumer repo workflows are synced from the Workflows repository. If you see
unexpected behavior:

1. **Check sync status**: Look at recent "Sync Consumer Repos" workflow runs
2. **Compare versions**: Check if your workflows match the templates
3. **Report issues**: File an issue in stranske/Workflows

---

## Quick Reference

### Important Files

| Path | Purpose |
|------|---------|
| `.github/workflows/` | All workflow files |
| `.github/ISSUE_TEMPLATE/` | Issue templates including Agent Task |
| `.github/codex/` | Agent configuration |
| `docs/LABELS.md` | Label definitions and triggers |
| `docs/AGENT_ISSUE_FORMAT.md` | How to format issues for agents |

### Key Labels

| Label | Effect |
|-------|--------|
| `autofix` | Triggers automatic code formatting |
| `autofix:clean` | Aggressive autofix mode |
| `agent:codex` | Assigns Codex agent to issue |
| `agent:needs-attention` | Pauses agent, needs human help |

### Helpful Links

- [Workflows Repository](https://github.com/stranske/Workflows)
- [SETUP_CHECKLIST.md](https://github.com/stranske/Workflows/blob/main/docs/templates/SETUP_CHECKLIST.md) - Consumer repo setup guide
- [CONSUMER_REPO_MAINTENANCE.md](https://github.com/stranske/Workflows/blob/main/docs/ops/CONSUMER_REPO_MAINTENANCE.md) - Debugging and maintenance

---

*This document is synced from the Workflows repository.*
*Source of truth: stranske/Workflows*
