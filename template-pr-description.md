# Update Template Repo Documentation

Updates Template repo README to align with current keepalive design and consumer-repo documentation patterns (from stranske/Workflows#493).

## Changes

### Architecture Updates
- ✅ Replace legacy **orchestrator** references with **Gate-triggered keepalive loop**
- ✅ Document **dual checkout pattern** for accessing centralized Workflows scripts  
- ✅ Clarify event-driven triggering vs scheduled polling
- ✅ Mark `agents-orchestrator.yml` as legacy (can be removed)

### Authentication & Setup
- ✅ Add CLI Codex authentication options: `CODEX_AUTH_JSON` vs GitHub App credentials
- ✅ Document required environments (`agent-standard`)
- ✅ List all required secrets with alternatives
- ✅ Add repository variables (`ALLOWED_KEEPALIVE_LOGINS`)
- ✅ Add branch protection recommendations

### Agent Workflow Documentation
- ✅ Update workflow table with current agent workflows (Guard, Verifier, Autofix Loop)
- ✅ Document keepalive activation requirements (4 conditions)
- ✅ Explain task tracking and checkbox reconciliation
- ✅ Add control labels table (`agent:codex`, `agents:pause`, `needs-human`)
- ✅ Document concurrency control (1 run per PR, configurable)

### Process Documentation
- ✅ Document complete Issue-to-PR workflow (7 steps)
- ✅ Update Issues.txt format to use `## Scope` syntax
- ✅ Add "How It Works" section with step-by-step flow
- ✅ Add "Key Components" explaining activation, tracking, failures, concurrency

### Troubleshooting
- ✅ Add comprehensive troubleshooting section with 4 common issues
- ✅ Document failure handling (3 strikes → `needs-human` label)
- ✅ Include solutions for auth errors, missing summaries, keepalive not triggering

### Documentation Links
- ✅ Link to Consumer README for complete setup guide
- ✅ Link to Keepalive Architecture docs for design details
- ✅ Reference Setup Checklist for step-by-step configuration
- ✅ Link to central Workflows repo

## Before/After

### Before
- Referenced "scheduled keepalive sweeps" (orchestrator model)
- No mention of dual checkout pattern
- Missing auth alternatives documentation
- Minimal troubleshooting guidance
- No control labels documented

### After
- Documents Gate-triggered loop (current architecture)
- Explains dual checkout for script access
- Complete auth options (CODEX_AUTH_JSON vs GitHub App)
- Comprehensive troubleshooting (4 sections)
- Full label documentation with effects

## Testing
- ✅ Markdown formatting validated
- ✅ All links point to valid locations
- ✅ Workflow names match actual files in Template repo

## Related
- Based on: stranske/Workflows#493 (consumer-repo README updates)
- Implements recommendations from: docs/keepalive/GoalsAndPlumbing.md

## Deployment
This PR updates documentation only - no workflow changes. Safe to merge.

---

**Branch:** `docs/update-keepalive-architecture`
**Commits:** 1 (bf12394)
**Files Changed:** 1 (README.md: +134, -45)
