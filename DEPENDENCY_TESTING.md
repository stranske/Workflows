# Dependency Testing Strategy

This document explains how we prevent test failures when dependencies are updated by dependabot.

## Problem

When dependabot updates dependencies in `pyproject.toml`, it can cause cascading test failures if:
1. Lock files don't include all optional dependency groups
2. Tests have hardcoded version expectations
3. Metadata serialization isn't handled correctly

## Solution

### 1. Complete Lock File Generation

The `requirements.lock` file **must** include ALL optional dependency groups:
- `dev` - Development tools (black, mypy, pytest)
- `langchain` - LangChain integration for LLM-enhanced task analysis

**Lock regeneration**: Renovate's `pip-compile` manager keeps `requirements.lock` fresh. On any source-dependency bump it regenerates the lock in the same PR by re-running the command recorded in the lock header, and its `lockFileMaintenance` (enabled by default for this manager, branch topic `pip-compile-refresh`) periodically recompiles the lock from scratch. `.github/workflows/maint-dependabot-auto-lock.yml` is a Workflows-only backstop that re-runs the same header command on `dependabot[bot]`/`renovate[bot]` PR branches. The recorded compile command is:

```yaml
uv pip compile pyproject.toml \
  --extra dev \
  --extra langchain \
  --universal \
  --output-file requirements.lock
```

### 2. Dynamic Version Testing

Tests that verify dependency versions should read from `pyproject.toml` instead of hardcoding versions:

**Bad:**
```python
def test_pandas_version():
    assert pd.__version__ == "2.0.0"  # Breaks when pandas updates
```

**Good:**
```python
def test_pandas_version():
    expected = _get_version_from_pyproject("pandas")
    assert pd.__version__ == expected
```

See `tests/test_dependency_version_alignment.py` for the implementation.

### 3. Metadata Serialization

Pydantic models must be serialized to dicts before being stored in DataFrames or returned from APIs to prevent PyArrow serialization errors:

**Locations:**
- `src/trend_analysis/io/validators.py:260` - `load_and_validate_upload()` return value
- `src/trend_analysis/io/market_data.py:946` - `attach_metadata()` DataFrame.attrs
- `streamlit_app/components/data_schema.py:174` - `_build_meta()` return value

**Pattern:**
```python
metadata.model_dump(mode="json")  # Convert Pydantic → dict
```

## Validation

Run this before merging dependency updates:

```bash
python scripts/validate_dependency_test_setup.py
```

This checks:
- ✓ Lock file includes all optional dependency groups  
- ✓ dependabot-auto-lock.yml has all `--extra` flags
- ✓ Metadata serialization implemented correctly
- ✓ Tests expect dicts, not Pydantic objects

## Testing Against Future PRs

To verify the fix works for upcoming dependabot PRs:

1. Find an open dependabot PR:
   ```bash
   gh pr list --author "app/dependabot" --state open
   ```

2. Check its status:
   ```bash
   gh pr checks <PR_NUMBER>
   ```

3. If it's failing, the validation script should catch the issue

## Common Issues

**Issue**: `test_dependency_version_alignment.py` fails with "Expected X packages, found Y"

**Cause**: Lock file missing optional dependencies

**Fix**: Re-run lock file generation with all `--extra` flags

---

**Issue**: `TypeError: Object of type MarketDataMetadata is not JSON serializable`

**Cause**: Pydantic object stored in DataFrame.attrs or returned from API

**Fix**: Call `.model_dump(mode="json")` before storing/returning

---

**Issue**: Test expects `.mode` attribute but gets `KeyError`

**Cause**: Metadata is now a dict, not a Pydantic object

**Fix**: Change `.mode` to `["mode"]` dict access

