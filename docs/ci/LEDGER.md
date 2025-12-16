# Ledger Base Hygiene

Codex ledgers capture durable progress for automation issues. Each ledger stores the
branch that automation works from (`branch`) and the repository default (`base`).
The default branch is informational only – the worker always resolves the live
value at runtime – but we keep it aligned so humans and tooling can reason about a
ledger without consulting GitHub.

## Runtime behaviour

* The belt worker resolves the repository default branch for every run.
* Git operations (checkout, placeholder commits, pull request targets) use the
  computed default rather than the value recorded in the ledger.
* When an existing ledger contains a stale `base`, the worker rewrites it to the
  computed default and annotates the job summary.

This guarantees that no automation task depends on historical values that might
still point at `main` after a repository rename.

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

## CI validation

The Codex belt worker executes the migration script in `--check` mode after
checking out the issue branch. The job fails if any ledger still references a
stale default branch and instructs maintainers to run the migration script. This
keeps ledgers up to date even when the repository default changes again in the
future.
