# Git Hooks Overview

Workflows uses the pre-commit framework for local checks on commit and push.
The [local validation guide](../validation/overview.md) describes the scripts
those hooks call and how to run them separately.

## Installation

From the repository root, use the development environment set up in the
[contributor guide](../CONTRIBUTING.md). Install both hook stages:

```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
```

<a id="hook-architecture"></a>
<a id="hook-configuration-pre-commit-configyaml"></a>

## Hook Details

The [hook configuration](../../.pre-commit-config.yaml) defines file selection,
versions and stages.

| Stage | Local hook | Purpose |
| --- | --- | --- |
| Commit | `dev-check` | Run `scripts/dev_check.sh` for fast feedback. The framework also applies matching format and file checks. |
| Push | `check-remote-sync` | Run `scripts/check_remote_sync.sh` to check an existing remote branch against the default branch and its remote-only commits. |
| Push | `validate-fast` | Run `scripts/validate_fast.sh` for checks selected by the changes. |

<a id="usage-examples"></a>

## Manual Hook Execution

Use the same hook configuration to reproduce a stage or restrict a diagnosis
to the files you are working on:

```bash
pre-commit run --all-files
pre-commit run dev-check
pre-commit run --hook-stage pre-push check-remote-sync
pre-commit run --hook-stage pre-push validate-fast
pre-commit run --files path/to/file.py
```

The push hook invokes the adaptive validator without a range. A clean working
tree can skip its adaptive checks even when outgoing commits contain code. To
check those commits, use the [explicit range example](../validation/overview.md#common-workflows).

If a formatting hook updates files, review and stage the changes before
committing again.

<a id="comparison-with-ci"></a>

## Integration with Validation Scripts

See the [local validation commands](../validation/overview.md#quick-reference)
for narrower checks, fix modes and commit-range selection. The
[hosted Gate workflow](../ci/WORKFLOWS.md#gate-job-map) is the separate PR check.

## Troubleshooting

- If `pre-commit` is missing, activate the repository’s development environment
  and follow the [contributor setup](../CONTRIBUTING.md#local-setup).
- If hooks do not run, inspect `git config --show-origin --get core.hooksPath`
  and `git rev-parse --git-path hooks`. Repeat the [installation](#installation)
  in the checkout where you need the hooks.
- If a hook cannot execute its script, check that checkout’s tracked executable
  bit and interpreter. The [validation troubleshooting](../validation/overview.md#troubleshooting)
  covers working-directory, environment and pin errors.
- If remote sync blocks a push, fetch and inspect the reported branch before
  integrating missing commits. A newly published branch may have no upstream
  history to check.
