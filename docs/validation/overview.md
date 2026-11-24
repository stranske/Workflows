# Validation System Overview

Run these commands from the repository root using the development environment
in the [contributor guide](../CONTRIBUTING.md#local-setup). Use local checks while
iterating. See the [CI workflow guide](../ci-workflow.md) for hosted checks,
and open the pull request’s Checks tab to inspect the actual result.

<a id="three-tier-validation-architecture"></a>
<a id="comparison-matrix"></a>

## Quick Reference

| Command | When to use it | Options |
| --- | --- | --- |
| [`./scripts/dev_check.sh`](../../scripts/dev_check.sh) | Quick development and pre-commit checks | `--changed` narrows the checked files. `--fix` applies supported corrections. `--verbose` shows details. |
| [`./scripts/validate_fast.sh`](../../scripts/validate_fast.sh) | Adaptive checks before a push or after a rebase | `--full` selects the full strategy when the diff includes Python or configuration changes. `--commit-range=RANGE` changes the default comparison against `HEAD`. `--fix`, `--verbose` and `--profile` control correction, output and timing. |
| [`./scripts/check_branch.sh`](../../scripts/check_branch.sh) | Broader branch checks before requesting review | `--fast` skips slow checks. `--fix` applies supported changes. `--verbose` shows details. |

### Common Workflows

```bash
./scripts/dev_check.sh --changed
./scripts/validate_fast.sh --commit-range=origin/main...HEAD
./scripts/validate_fast.sh --full
./scripts/validate_fast.sh --profile
./scripts/check_branch.sh --fast
```

With no explicit range, the adaptive validator compares working-tree changes
against `HEAD`. It exits early if the diff has no Python or configuration
changes, even with `--full`. To check committed branch changes, pass an explicit
range as shown above. Use `./scripts/validate_fast.sh --help` for current options. Review the diff
after a `--fix` run. A nonzero exit needs investigation before you rely on the
check.

## Integration Points

### Git Hooks

The [Git hooks guide](../git-hooks/overview.md) covers installation and
stage-specific commands. The commit stage runs `dev-check`. The push stage
runs both `check-remote-sync` and `validate-fast`. Their local checks complement
the required [Gate jobs](../ci/WORKFLOWS.md#gate-job-map).

### Tool Version Synchronization

The tooling uses [the shared version pins](../../.github/workflows/autofix-versions.env).
From the repository root, use `python -m scripts.sync_tool_versions --check`
to diagnose source pin drift. On an intentional repair branch,
`python -m scripts.sync_tool_versions --apply` updates the source files for
review. The [tool version guide](../ci/TOOL_VERSION_MANAGEMENT.md) explains how
that fits with automatic pin proposals and propagation.

## Troubleshooting

- If the shared pin file is missing, confirm you are at the repository root and
  that the checkout includes `.github/workflows/autofix-versions.env`.
- If tools are missing or versions differ, activate the repository’s selected
  environment and run the pin check above. The validation scripts can activate
  an existing `.venv` when none is active and may install a pinned tool when
  it is absent or mismatched.
- If the checked files differ from what you expected, list the working-tree
  changes with `git status --short` and check the requested commit range.
- If an installed hook is absent or a push is rejected by local sync checks,
  use the [hook troubleshooting](../git-hooks/overview.md#troubleshooting).
