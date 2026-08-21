# Consumer Sync Contract Map

> **Status**: Active - Grounded in real Workflows repository files  
> **Owner**: `stranske/Workflows` maintainers  
> **Scope**: Consumer repository synchronization system  
> **Related**: `docs/ops/CONSUMER_REPO_MAINTENANCE.md`, `docs/INTEGRATION_GUIDE.md`

This document maps the contractual interfaces between the Workflows repository and consumer repositories for the sync system. Each contract point is grounded in actual source files with expected behaviors, failure signals, and validation commands.

---

## Overview

The consumer sync system is **manifest-driven**: all synchronization targets are declared in `.github/sync-manifest.yml`. The system ensures that templates, workflows, scripts, and documentation stay aligned across the registered consumer fleet without manual intervention.

**Core Principle**: Fix in Workflows first, sync to consumers second.

---

## Source Contract Points

### 1. Sync Manifest (`./.github/sync-manifest.yml`)

**Source Path**: [`.github/sync-manifest.yml`](/.github/sync-manifest.yml)  
**Contract Type**: Single Source of Truth - Declarative Configuration  
**Consumer Behavior**: Consumer repos receive files declared in this manifest via `maint-68-sync-consumer-repos.yml`

| Aspect | Expected Behavior | Failure Signal | Validation Command |
|--------|-------------------|----------------|---------------------|
| File declaration | Every sync-able file MUST be listed in this manifest | Files missing from manifest are NOT synced to consumers | `python scripts/validate_template_completeness.py` |
| Section categorization | Files grouped by type (workflows, prompts, scripts, docs, etc.) | Files in wrong section may not be processed correctly | `python scripts/validate_template_completeness.py --strict` |
| `sync_mode: create_only` | Files marked create_only are NOT overwritten in existing consumer repos | Existing consumer customizations are preserved | `grep -c "sync_mode: create_only" .github/sync-manifest.yml` |
| `overwrite_repos` | Specified repos ignore create_only and stay byte-aligned | Repos in this list receive updates even for create_only files | `yq '.workflows[].overwrite_repos' .github/sync-manifest.yml` |
| `skip_repos` | Specified repos are excluded from receiving specific files | Files are skipped for listed repos | `yq '.workflows[].skip_repos' .github/sync-manifest.yml` |
| `delivery: runtime` | Files marked runtime are NOT copy-synced; delivered via sparse-checkout at runtime | Double delivery if also in copy-synced section | `python tests/workflows/test_sync_manifest_delivery.py` |

**Validation**: 
```bash
# Validate manifest completeness
python scripts/validate_template_completeness.py

# Run the Health 70 workflow validation
python scripts/validate_template_completeness.py --source sync-manifest

# Check for delivery channel invariants
python -m pytest tests/workflows/test_sync_manifest_delivery.py -v
```

---

### 2. Sync Workflow (`./.github/workflows/maint-68-sync-consumer-repos.yml`)

**Source Path**: [`.github/workflows/maint-68-sync-consumer-repos.yml`](/.github/workflows/maint-68-sync-consumer-repos.yml)  
**Contract Type**: Orchestration - Execution Engine  
**Consumer Behavior**: Reads manifest, compares hashes, creates sync PRs in consumer repos

| Aspect | Expected Behavior | Failure Signal | Validation Command |
|--------|-------------------|----------------|---------------------|
| Manifest reading | Workflow MUST read `.github/sync-manifest.yml` for sync targets | Hardcoded file lists create drift | `grep -n "sync-manifest.yml" .github/workflows/maint-68-sync-consumer-repos.yml` |
| Registered repos | `REGISTERED_CONSUMER_REPOS` env var defines target repos | Repos not in list do NOT receive sync | `grep -A 15 "REGISTERED_CONSUMER_REPOS:" .github/workflows/maint-68-sync-consumer-repos.yml` |
| Hash comparison | Template hash compared before creating PRs | Unnecessary PRs created when no changes | `grep -n "template_hash" .github/workflows/maint-68-sync-consumer-repos.yml` |
| Create-only handling | Files with `sync_mode: create_only` skip existing files | Custom Gate files overwritten in Manager-Database, trip-planner, Trend_Model_Project | `grep -n "sync_mode" .github/workflows/maint-68-sync-consumer-repos.yml` |
| Custom repo skips | Hardcoded `custom_gate_repos` list matches manifest skip_repos | Inconsistent skipping between workflow and manifest | `grep -n "custom_gate_repos" .github/workflows/maint-68-sync-consumer-repos.yml` |
| Runtime fetched exclusion | `runtime_fetched` section MUST NOT be processed | Files double-delivered via both copy and runtime | `grep -c "runtime_fetched" .github/workflows/maint-68-sync-consumer-repos.yml` (should be 0) |

**Validation**:
```bash
# Check workflow references manifest
grep -n "sync-manifest.yml" .github/workflows/maint-68-sync-consumer-repos.yml

# Verify registered repos list is non-empty
grep -A 15 "REGISTERED_CONSUMER_REPOS:" .github/workflows/maint-68-sync-consumer-repos.yml | grep -v "^$" | wc -l

# Run sync manifest delivery tests (ensures no double delivery)
python -m pytest tests/workflows/test_sync_manifest_delivery.py::test_no_entry_is_both_runtime_and_copy_synced -v
```

---

### 3. Template Source (`./templates/consumer-repo/`)

**Source Path**: [`templates/consumer-repo/`](templates/consumer-repo/)  
**Contract Type**: Content Source - Canonical Templates  
**Consumer Behavior**: Files here are the source for sync; consumers receive copies

| Aspect | Expected Behavior | Failure Signal | Validation Command |
|--------|-------------------|----------------|---------------------|
| File presence | Every file MUST have corresponding manifest entry | Files without manifest entry are NOT synced | `python scripts/validate_template_completeness.py` |
| Path structure | Template paths match manifest `source:` paths | Sync failures due to path mismatch | `diff <(find templates/consumer-repo -type f | sort) <(yq '.workflows[].source + "\n" + .prompts[].source + "\n" + .scripts[].source + "\n" + .docs[].source' .github/sync-manifest.yml | grep -v null | sort)` |
| Create-only files | `pr-00-gate.yml`, `ci.yml` marked create_only | Existing consumer files overwritten | `yq '.workflows[] | select(.sync_mode == "create_only") | .source' .github/sync-manifest.yml` |
| Runtime dependencies | `scripts/langchain/followup_issue_generator.py` marked delivery: runtime | Not available at runtime in consumers | `yq '.runtime_fetched[] | select(.source == "scripts/langchain/followup_issue_generator.py")' .github/sync-manifest.yml` |
| Consumer docs | Template sources such as `templates/consumer-repo/docs/LABELS.md` sync to consumer paths such as `docs/LABELS.md` | Docs drift across fleet | `ls templates/consumer-repo/docs/` |

**Validation**:
```bash
# List all template files
find templates/consumer-repo -type f | sort

# Check that followup_issue_generator.py is NOT in copy-synced sections
yq '.workflows[].source, .prompts[].source, .scripts[].source, .docs[].source' .github/sync-manifest.yml | grep -c "followup_issue_generator.py" || echo "0 (expected)"

# Verify it IS in runtime_fetched
yq '.runtime_fetched[] | select(.source == "scripts/langchain/followup_issue_generator.py") | .delivery' .github/sync-manifest.yml
```

---

### 4. Manifest Validation (`./.github/workflows/health-70-validate-sync-manifest.yml`)

**Source Path**: [`.github/workflows/health-70-validate-sync-manifest.yml`](/.github/workflows/health-70-validate-sync-manifest.yml)  
**Contract Type**: Guardrail - Completeness Enforcement  
**Consumer Behavior**: Fails PRs that add sync-able files without updating manifest

| Aspect | Expected Behavior | Failure Signal | Validation Command |
|--------|-------------------|----------------|---------------------|
| Trigger paths | Runs on changes to workflows, codex, scripts, templates, manifest | Sync-able files added without manifest update | `grep -A 10 "paths:" .github/workflows/health-70-validate-sync-manifest.yml | head -20` |
| Script invocation | Calls `scripts/validate_template_completeness.py` | Manifest incompleteness not detected | `grep "validate_template_completeness" .github/workflows/health-70-validate-sync-manifest.yml` |
| Policy enforcement | Fails PRs that violate completeness policy | PR merges with incomplete manifest | `grep -i "fail" .github/workflows/health-70-validate-sync-manifest.yml` |

**Validation**:
```bash
# Check what triggers the validation
 grep -A 10 "on:" .github/workflows/health-70-validate-sync-manifest.yml

# Verify it calls the validator script
grep "validate_template_completeness" .github/workflows/health-70-validate-sync-manifest.yml
```

---

### 5. Drift Detection (`./.github/workflows/health-68-consumer-sync-drift.yml`)

**Source Path**: [`.github/workflows/health-68-consumer-sync-drift.yml`](/.github/workflows/health-68-consumer-sync-drift.yml)  
**Contract Type**: Monitoring - Consistency Verification  
**Consumer Behavior**: Compares consumer repos to templates, reports drift

| Aspect | Expected Behavior | Failure Signal | Validation Command |
|--------|-------------------|----------------|---------------------|
| Trigger paths | Runs on template, manifest, script changes and daily | Drift undetected after changes | `grep -A 10 "paths:" .github/workflows/health-68-consumer-sync-drift.yml` |
| Script invocation | Calls `scripts/check_consumer_sync_drift.py` | Consumer drift not detected | `grep "check_consumer_sync_drift" .github/workflows/health-68-consumer-sync-drift.yml` |
| Create-only exclusion | Skips files marked `sync_mode: create_only` | False drift reports for create_only files | `grep -n "create_only" .github/workflows/health-68-consumer-sync-drift.yml` |
| Artifact upload | Uploads `consumer-sync-drift-report.json` artifact | No artifact for manual inspection | `grep -n "consumer-sync-drift-report" .github/workflows/health-68-consumer-sync-drift.yml` |
| Issue creation | Creates/updates drift issue on failure | Drift silently ignored | `grep -n "drift issue" .github/workflows/health-68-consumer-sync-drift.yml` |

**Validation**:
```bash
# Check drift detection triggers
grep -A 10 "on:" .github/workflows/health-68-consumer-sync-drift.yml

# Verify artifact upload
grep "upload-artifact" .github/workflows/health-68-consumer-sync-drift.yml

# Check the drift script itself
python scripts/check_consumer_sync_drift.py --help
```

---

## Coordination Checklist

Use this checklist when making changes that affect the consumer sync contract:

- [ ] **Manifest updated**: Added/removed files in `.github/sync-manifest.yml`
- [ ] **Template updated**: Modified files in `templates/consumer-repo/`
- [ ] **Validation passes**: `python scripts/validate_template_completeness.py` succeeds
- [ ] **Delivery channel correct**: Runtime-fetched files NOT in copy-synced sections
- [ ] **Create-only semantics preserved**: `sync_mode: create_only` entries respect existing consumer files
- [ ] **Custom repo exceptions documented**: `skip_repos` and `overwrite_repos` aligned with known exceptions
- [ ] **Drift detection runs**: Health 68 workflow triggered or will run on schedule
- [ ] **Sync workflow triggered**: Maint 68 workflow run created for affected repos
- [ ] **Integration tests pass**: Consumer-facing workflows still function correctly

---

## Non-Goals

The following are explicitly **NOT** within scope of this contract map:

1. **Consumer-specific CI configuration**: `ci.yml` and `autofix-versions.env` are repo-specific and NOT managed via sync manifest
2. **Reusable workflow implementations**: Changes to `reusable-*.yml` files take effect immediately via `@main` reference; these are not synced files
3. **Workflows-repo-only workflows**: Workflows like `agents-keepalive-loop.yml`, `health-70-validate-sync-manifest.yml` are NOT synced to consumers
4. **Manual consumer exceptions**: Repos with documented exceptions (Manager-Database, trip-planner, Trend_Model_Project, Fine-Art-Archive) maintain their custom configurations outside the sync system
5. **Package dependency management**: `app-baseline-kit` and other monorepo packages are managed via git URL pins, not file sync

---

## Escalation Criteria

Escalate to a Workflows maintainer when a change requires **real consumer-repo modifications** beyond file sync:

| Scenario | Escalation Required? | Reason |
|----------|---------------------|--------|
| Adding new workflow to template | No | Manifest update + sync suffices |
| Modifying `pr-00-gate.yml` template | **Yes** | Affects create-only semantics; may break existing consumers |
| Changing reusable workflow inputs | **Yes** | Requires coordinated updates across all callers |
| Updating runtime-fetched script | No | Change in Workflows takes effect immediately |
| Modifying `ci.yml` template | **Yes** | Each consumer customizes CI; changes may conflict |
| Adding new agent workflow | No | Standard sync via manifest |
| Changing autofix-versions.env | **Yes** | Consumer repos maintain their own dependency pins |
| Updating `sync-manifest.yml` structure | **Yes** | May require updates to sync workflow and drift checker |
| Modifying health check workflows | **Yes** | Workflows-repo-only; affects monitoring infrastructure |
| Consumer has custom Gate workflow | **Yes** | Documented exception; changes may require repo-specific adjustments |

**Escalation Path**:
1. Open issue in `stranske/Workflows` with `[consumer-sync]` label
2. Reference the specific contract point(s) affected
3. Include validation command output showing the issue
4. Tag `@stranske/Workflows` maintainers

---

## Validation Commands Summary

Run these commands to validate the entire sync contract:

```bash
# 1. Validate manifest completeness
python scripts/validate_template_completeness.py

# 2. Run sync manifest delivery invariants
python -m pytest tests/workflows/test_sync_manifest_delivery.py -v

# 3. Check template files have manifest entries
python scripts/validate_template_completeness.py --strict --source sync-manifest

# 4. Verify no double delivery
python -m pytest tests/workflows/test_sync_manifest_delivery.py::test_no_entry_is_both_runtime_and_copy_synced -v

# 5. Check Health 70 validation workflow is configured
python -m pytest tests/scripts/test_validate_template_sync.py -v -k "manifest"

# 6. Full sync system test suite
python -m pytest tests/workflows/test_sync_manifest_delivery.py tests/scripts/test_check_consumer_sync_drift.py -v
```

---

## File Inventory

**Contract Source Files** (in Workflows repo):
- `.github/sync-manifest.yml` - Manifest of all sync-able files
- `.github/workflows/maint-68-sync-consumer-repos.yml` - Sync execution workflow
- `.github/workflows/health-68-consumer-sync-drift.yml` - Drift detection
- `.github/workflows/health-70-validate-sync-manifest.yml` - Manifest validation
- `templates/consumer-repo/` - Source templates for consumers
- `scripts/validate_template_completeness.py` - Validation script
- `scripts/check_consumer_sync_drift.py` - Drift checking script
- `scripts/list_registered_consumer_repos.py` - Repo list extraction

**Test Files** (validating contract):
- `tests/workflows/test_sync_manifest_delivery.py` - Delivery channel invariants
- `tests/scripts/test_validate_template_sync.py` - Template sync validation
- `tests/scripts/test_check_consumer_sync_drift.py` - Drift detection tests

---

## Revision History

| Date | Change | Author |
|------|--------|--------|
| 2026-06-27 | Initial document created for issue #2565 | Vibe |
