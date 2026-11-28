# Ledger validation and base maintenance

Existing `.agents/issue-*-ledger.yml` files preserve task and completion evidence.
The `branch` records the branch used for the task. The `base` records the
repository default branch for that ledger and can be aligned when the default changes.

## Runtime validation

[PR Gate](../../.github/workflows/pr-00-gate.yml) runs
`scripts/ledger_validate.py` when issue ledger files are present in the checkout.
The legacy Belt worker was retired in [#5379](https://github.com/stranske/Workflows/pull/5379).
[Maint 74 Ledger Base Sync](../../.github/workflows/maint-74-ledger-base-sync.yml)
owns base migration. It resolves the repository default branch, runs the
migration, and opens a PR for changes. It runs weekly or by manual dispatch.

## Completion evidence

A successful worker process by itself does not prove that a historical task was
completed. For a `done` entry, inspect the cited commit and its changed paths.
File-like artifacts named in the task must be present in that commit's tree.
Their presence in a later checkout does not establish the original completion.

Use the read-only historical audit to find older false completions. It reports
findings and exits non-zero without editing ledgers:

```bash
python scripts/audit_belt_ledger_completion.py --root .
```

Historical ledgers can cite commits that are not present in the local object
store, for example after a squash merge or history rewrite. The audit reports
those entries separately as `unverifiable` and prints their skipped count. An
all-unverifiable audit exits zero because it found no false-completion finding;
that exit status means the available evidence is clean, not that every cited
commit was inspected. A reachable commit that Git cannot inspect remains a hard
audit error rather than being downgraded to `unverifiable`.

Duplicate tasks may name the same artifact, but a `done` claim is fatal when that
artifact is absent from its cited commit. This prevents one false completion from
being hidden by a later `todo` entry for the same file.

## Migration script

`scripts/ledger_migrate_base.py` keeps ledgers in sync with the default branch.
It autodetects the repository default (falling back to the current branch) and
updates any ledgers that have drifted.

```bash
# Update all ledgers in-place
python scripts/ledger_migrate_base.py

# Verify that ledger base values already match the default branch
python scripts/ledger_migrate_base.py --check

# Override detection when the default branch cannot be derived automatically
python scripts/ledger_migrate_base.py --default work
```

The script preserves the original ordering and indentation so that migrations are
minimal and review-friendly.
