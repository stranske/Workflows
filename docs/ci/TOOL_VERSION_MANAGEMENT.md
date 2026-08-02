# CI/Autofix Tool Version Management

## Overview

All CI and autofix workflows use tool versions defined in a single source of truth to ensure consistency across:
- CI validation (formatting, linting, type checking)
- PR autofix commits
- CI autofix loop
- Local development

## Renovate Intake Validation

Renovate owns routine dependency updates, while `autofix-versions.env` remains the
source for the dev-tool pins it explicitly excludes. The fleet preset uses a bounded
weekly intake window, conservative branch/PR budgets, release-age and update-branch-check
gates, a grouped trusted GitHub Actions lane, and Dependency Dashboard approval for
majors. Vulnerability alerts bypass the routine window and age gate.

Run the same validation used by `scripts/dev_check.sh` after editing either Renovate
entrypoint or the shared preset:

```bash
npx --yes --package renovate@43.285.3 -- renovate-config-validator --no-global \
  renovate.json renovate-presets/fleet.json \
  templates/consumer-repo/.github/renovate.json
```

## Version File

**Location**: `.github/workflows/autofix-versions.env`

This file contains pinned versions for all formatting, linting, and testing tools:

```bash
BLACK_VERSION=25.11.0
RUFF_VERSION=0.14.7
ISORT_VERSION=7.0.0
DOCFORMATTER_VERSION=1.7.7
MYPY_VERSION=1.19.0
PYTEST_VERSION=9.0.1
PYTEST_COV_VERSION=7.0.0
PYTEST_XDIST_VERSION=3.8.0
COVERAGE_VERSION=7.12.0
```

## Workflows Using Version File

### 1. CI Python Validation (`reusable-10-ci-python.yml`)
- Sources `autofix-versions.env` before installing tools
- Runs `black --check`, `ruff check`, `mypy`, and `pytest`
- Falls back to latest versions if version file is missing
- Uses the shared Ruff `E4,E7,E9,F` default family only when a consumer does
  not declare its own Ruff selection, so a tool upgrade cannot silently
  broaden consumer lint requirements.

### 2. PR Autofix (`reusable-18-autofix.yml`)
- Reads version file to install Black and Ruff
- Applies fixes automatically when CI fails
- Uses same tool versions as CI validation

### 3. CI Autofix Loop (`autofix.yml`)
- Extracts Black and Ruff versions from version file
- Runs after Gate workflow failures
- Applies import ordering (Ruff) and formatting (Black)

### 4. Version Check (`maint-50-tool-version-check.yml`)
- Runs weekly on Mondays at 8:00 AM UTC
- Checks PyPI for latest versions of all tools
- Publishes read-only freshness evidence; it never opens or comments on a
  competing update issue or PR

### 5. Canonical Source Proposal (`maint-auto-update-pypi-versions.yml`)
- Runs Mondays at 03:00 UTC, before consumer propagation
- Is the only routine workflow allowed to open or refresh a Workflows dev-tool
  source PR
- Uses one mutable `auto/weekly-dev-tool-update-YYYY-Www` PR per weekly window
- An operator may use the explicit `security_override` dispatch input for an
  urgent security update outside that window
- Always runs `sync_tool_versions.py --check` and
  `sync_dev_dependencies.py --check --lockfile` after applying pin updates and
  before opening or refreshing the source PR (`security_override` cannot skip
  this gate)
- After the canonical source PR exists, closes open Dependabot/Renovate PRs that
  touch the same Workflows-owned pin surfaces so overlapping bot proposals are
  superseded rather than raced

## Update Process

### Automated Monitoring

The source lane is deliberately single-writer:

1. `maint-50-tool-version-check.yml` reports PyPI freshness only.
2. `maint-auto-update-pypi-versions.yml` checks the canonical pin file in the
   Monday batch window and opens or refreshes one source PR for all routine
   updates found together.
3. After that source PR merges and its normal validation succeeds, the
   `maint-52-sync-dev-versions.yml` push trigger propagates the exact settled
   source commit to consumers. Its delivery marker and PR body record that SHA.
4. A security-sensitive update may be manually dispatched with
   `security_override=true`; it remains on the same source lane and still runs
   the normal source validation before propagation.

### Operator Review Steps

When the canonical source lane opens a PR:

1. **Review the canonical source PR** to see which tools have new versions

2. **Inspect the proposed pin set** when local reproduction is useful:
   ```bash
   # Edit .github/workflows/autofix-versions.env
   vim .github/workflows/autofix-versions.env
   
   # Example: Update Black from 25.9.0 to 25.11.0
   BLACK_VERSION=25.11.0
   ```

3. **Test locally**:
   ```bash
   # Source the version file
   source .github/workflows/autofix-versions.env
   
   # Install with pinned versions
   pip install "black==${BLACK_VERSION}" "ruff==${RUFF_VERSION}" "mypy==${MYPY_VERSION}"
   
   # Run validation
   black --check .
   ruff check .
   mypy src tests
   ```

4. **Verify CI passes** on that canonical source PR:
   - All Gate checks should pass
   - Autofix should use new versions if it runs
   - No formatting conflicts should occur

5. **Merge the canonical source PR**. Its settled commit is then the only
   input to the Maint 52 consumer-propagation wave; do not create a parallel
   update issue or competing source PR.

## Why Version Pinning?

### Problems Without Version Pinning

1. **Formatter Drift**: Autofix uses Ruff 0.6.2, CI validates with Ruff 0.6.3
   - Result: Autofix commits fail CI validation
   
2. **Breaking Changes**: Tool updates can introduce breaking changes
   - Result: Sudden CI failures across all PRs
   
3. **Inconsistent Local Development**: Developers use different versions
   - Result: "Works on my machine" formatting issues

### Benefits of Centralized Pinning

1. **Consistency**: Same tool versions across all environments
2. **Reproducibility**: Results are deterministic
3. **Controlled Updates**: Updates are deliberate and tested
4. **Clear History**: Git shows when/why versions changed

## Troubleshooting

### Autofix Commits Fail CI

**Symptom**: Autofix creates a commit but CI still reports formatting errors

**Cause**: Autofix and CI are using different tool versions

**Solution**:
1. Check both workflows source `autofix-versions.env`
2. Verify version variables are read correctly
3. Ensure both use the same formatter (Black, not `ruff format`)

### Version File Not Found

**Symptom**: Warning in CI logs about missing version file

**Cause**: Workflow can't find `.github/workflows/autofix-versions.env`

**Solution**:
1. Verify file exists in repository
2. Check workflow is checking out repository code
3. Ensure path is correct (relative to repo root)

### Weekly Check Not Running

**Symptom**: No canonical source PR is being created when a routine update is due

**Cause**: Workflow may be disabled or scheduled incorrectly

**Solution**:
1. Check `maint-auto-update-pypi-versions.yml` is enabled in Actions UI
2. Verify the source-lane cron schedule is correct (`0 3 * * 1`, Mondays 03:00 UTC)
3. Manually trigger that workflow with workflow_dispatch to test

## Architecture Decisions

### Why Shell Sourcing (CI) vs Python Parsing (Autofix)?

- **CI** (`reusable-10-ci-python.yml`): Uses `source` for simplicity
  - Single line: `source .github/workflows/autofix-versions.env`
  - Shell variables are immediately available
  
- **Autofix** (`reusable-18-autofix.yml`, `autofix.yml`): Uses Python parser
  - More complex error handling
  - Needs to set outputs for later steps
  - Works in environments where source may not behave correctly

Both approaches read the same file and produce identical results.

### Why Black Instead of Ruff Format?

While Ruff includes a formatter compatible with Black, there are subtle differences in:
- Line breaking decisions
- Comment handling
- Edge case formatting

To ensure CI validation and autofix produce identical output, both must use the same formatter. We chose Black as the canonical formatter because:
1. It's the established standard in the Python ecosystem
2. More mature and stable
3. Explicit formatting rules prevent ambiguity

## Renovate vs Maint 68 File Ownership

Dev-tool pins are excluded from Renovate (see the fleet preset) because
`autofix-versions.env` owns them. A second, path-level boundary applies to
consumer repos: Maint 68 overwrites every manifest-managed file on each sync, so
a consumer Renovate PR editing one of those files is reverted on the next sync.

`renovate-presets/consumer-managed-paths.json` is generated from
`.github/sync-manifest.yml` and disables dependency extraction for exactly those
paths, per repo. Renovate stays enabled for `create_only`/`skip_repos` paths the
consumer owns and for every canonical source file in `stranske/Workflows`, which
means action and dependency bumps still land here first and reach consumers
through the sync.

Regenerate with `python scripts/generate_consumer_renovate_ownership.py` after
changing the manifest; `--check` runs in `scripts/dev_check.sh` and fails on
drift. Full ownership table:
[Consumer Repository Maintenance](../ops/CONSUMER_REPO_MAINTENANCE.md#renovate-vs-maint-68-path-ownership).

## Related Documentation

- [Autofix System](AUTOFIX.md) - How automatic fixes work
- [Gate Workflow](GATE.md) - CI validation pipeline
- [Ledger System](LEDGER.md) - Agent progress tracking

## Maintenance Schedule

- **Weekly**: One source proposal window (Mondays 03:00 UTC) and read-only
  freshness report (Mondays 08:00 UTC)
- **As Needed**: Explicit `security_override` source-lane dispatch for reviewed
  security updates
- **Quarterly**: Review and update this documentation
