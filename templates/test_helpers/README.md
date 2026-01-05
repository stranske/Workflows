# Shared Test Helpers

This directory contains shared test utilities that are synced to all consumer repos.

## Syncing to Consumer Repos

These files are automatically synced using the `scripts/sync_test_helpers.sh` script.

### In Consumer Repos

Run from the Workflows repo:
```bash
cd /path/to/Workflows
./scripts/sync_test_helpers.sh --repo /path/to/consumer-repo
```

Or from within a consumer repo (if Workflows is cloned):
```bash
cd /path/to/consumer-repo
/path/to/Workflows/scripts/sync_test_helpers.sh --repo .
```

### Check Sync Status

```bash
./scripts/sync_test_helpers.sh --check --repo /path/to/consumer-repo
```

## Available Utilities

### version_utils.py

Version-agnostic dependency testing utilities:

- `get_package_version(package)` - Get installed version as packaging.Version
- `get_declared_version_range(package)` - Extract range from pyproject.toml
- `assert_version_in_declared_range(package)` - Assert installed version matches declared range
- `assert_all_dependencies_within_ranges()` - Check all dependencies at once
- `has_feature(package, min_version)` - Check if version meets minimum requirement

**Example usage:**
```python
from tests.helpers.version_utils import assert_version_in_declared_range

def test_numpy_version():
    # Dynamically checks against pyproject.toml
    assert_version_in_declared_range("numpy")
```

## Adding New Helpers

1. Add the helper file to `templates/test_helpers/` in the Workflows repo
2. Commit and push to Workflows repo
3. Sync to consumer repos using `sync_test_helpers.sh`

## Integration with CI

Consumer repos can add a CI check to ensure helpers stay in sync:

```yaml
- name: Check test helpers sync
  run: |
    git clone https://github.com/stranske/Workflows.git /tmp/Workflows
    /tmp/Workflows/scripts/sync_test_helpers.sh --check --repo .
```

Or integrate into existing sync workflows (maint-52, etc.).
