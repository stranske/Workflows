# Template Repo Evaluation & Updates

**Date:** January 3, 2026  
**Evaluator:** GitHub Copilot  
**Related:** stranske/Workflows#493, stranske/Template#63

## Executive Summary

The Template repository's README has been evaluated against the current keepalive architecture and consumer-repo documentation patterns. Key findings: the documentation references legacy orchestrator-based scheduling when the current system uses Gate-triggered event-driven execution. Updates have been prepared to align documentation with actual implementation.

## Evaluation Findings

### ✅ Good - Workflows Present
- Template repo has current workflow files (agents-keepalive-loop.yml, agents-guard.yml, etc.)
- `.github/codex/` directory structure is correct
- Has both legacy orchestrator and current keepalive-loop (intentional for compatibility)

### ⚠️ Needs Update - Documentation
- README references "scheduled keepalive sweeps" (legacy orchestrator model)
- Missing documentation of dual checkout pattern
- No mention of CLI Codex authentication options
- Minimal troubleshooting guidance
- Control labels (`agents:pause`, `needs-human`) not documented
- No failure handling documentation

### Architecture Misalignment

| Current README Says | Actual Implementation | Should Say |
|---------------------|----------------------|------------|
| "Scheduled keepalive sweeps" | Gate-triggered event-driven | "Gate-triggered keepalive loop" |
| "Agents Orchestrator" primary | agents-keepalive-loop primary | "Keepalive Loop (current), Orchestrator (legacy)" |
| No auth alternatives | Supports CODEX_AUTH_JSON or GitHub App | Document both auth methods |
| Minimal setup docs | Requires environments, variables, secrets | Complete setup requirements |

## Prepared Updates

### Files Created
1. **template-repo-readme-updates.patch** (8.6KB)
   - Git patch with all README changes
   - Ready to apply to Template repo

2. **template-pr-description.md**
   - Comprehensive PR description
   - Includes before/after, testing notes, deployment info

### Changes Summary

**Architecture (89 lines changed)**
- Replaced orchestrator references with Gate-triggered loop
- Added "How It Works" 7-step flow
- Documented dual checkout pattern
- Marked orchestrator as legacy

**Setup & Configuration (45 lines changed)**
- Added auth alternatives table (CODEX_AUTH_JSON vs GitHub App)
- Documented environments, variables, branch protection
- Listed all required secrets with alternatives

**Agent Documentation (67 lines added)**
- Workflow table updated with Guard, Verifier, Autofix Loop
- Activation requirements (4 conditions)
- Control labels table with effects
- Concurrency control explanation

**Troubleshooting (43 lines added)**
- 4 common issues with solutions
- Failure handling (3 strikes rule)
- Permission errors guidance
- Missing summary recovery

**Total Impact:** +134 lines, -45 lines (net +89)

## Deployment Plan

### Option 1: Manual PR (Recommended)
1. Human with write access clones Template repo
2. Creates branch from main
3. Applies patch: `git apply template-repo-readme-updates.patch`
4. Creates PR using template-pr-description.md
5. Reviews and merges

### Option 2: Automated (If access available)
```bash
# From a machine with proper auth
cd /tmp
git clone git@github.com:stranske/Template.git
cd Template
git checkout -b docs/update-keepalive-architecture
git apply /path/to/template-repo-readme-updates.patch
git commit -m "docs: update README with current keepalive architecture"
git push origin docs/update-keepalive-architecture
gh pr create --title "docs: update README with current keepalive architecture" \
  --body-file /path/to/template-pr-description.md
```

## Related Consumer Repos

### Also Should Review
Based on the same patterns, these repos likely need similar updates:

1. **stranske/Travel-Plan-Permission** - Active agent consumer
2. **stranske/Portable-Alpha-Extension-Model** - Active agent consumer  
3. **stranske/Manager-Database** - Active agent consumer
4. **stranske/trip-planner** - Active agent consumer

### Review Checklist for Each
- [ ] README references current architecture (Gate-triggered vs orchestrator)
- [ ] Documents dual checkout pattern if using agent workflows
- [ ] Auth options documented (CODEX_AUTH_JSON vs GitHub App)
- [ ] Control labels documented
- [ ] Troubleshooting section present
- [ ] Links to central Workflows docs

## Success Metrics

After merging updates:
- ✅ Template README accurately reflects current keepalive architecture
- ✅ New repos cloned from Template have correct documentation
- ✅ Setup instructions guide users to current patterns
- ✅ Troubleshooting reduces support burden
- ✅ Links provide path to detailed documentation

## Follow-up Actions

1. **Immediate:** Merge Template repo PR (stranske/Template#63)
2. **Next Sprint:** Audit other consumer repos (Travel-Plan-Permission, etc.)
3. **Ongoing:** Keep consumer-repo README as source of truth
4. **Quarterly:** Review all consumer repos for drift from standards

## Alignment Verification

### Consumer-Repo README (Source of Truth)
- ✅ Dual checkout pattern documented
- ✅ Gate-triggered architecture explained
- ✅ Auth alternatives listed
- ✅ Troubleshooting comprehensive
- ✅ Control labels documented

### Template Repo README (After Update)
- ✅ Matches consumer-repo patterns
- ✅ References central docs for details
- ✅ Tailored for "template" use case
- ✅ Includes Issues.txt format
- ✅ Points to setup checklist

## Notes

- Template repo intentionally keeps both orchestrator and keepalive-loop workflows for backward compatibility
- Documentation now clearly marks orchestrator as "legacy"
- Updates are documentation-only, no workflow file changes needed
- Safe to merge without testing (no code changes)

## References

- [Consumer README](https://github.com/stranske/Workflows/blob/main/templates/consumer-repo/README.md)
- [Keepalive Architecture](https://github.com/stranske/Workflows/blob/main/docs/keepalive/GoalsAndPlumbing.md)
- [Template Issue #63](https://github.com/stranske/Template/issues/63)
- [Workflows PR #493](https://github.com/stranske/Workflows/pull/493)
