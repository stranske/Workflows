# Workflow Documentation Template

Use this template when documenting extracted workflows in `docs/workflows/`.

---

# [Workflow Name]

Brief one-sentence description of what this workflow does.

## Overview

A more detailed paragraph explaining:
- The purpose of this workflow
- When you would use it
- What problems it solves
- Key benefits

## Usage

### Basic Usage

```yaml
name: My Project CI
on: [push, pull_request]

jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/WORKFLOW_FILE.yml@v1
    with:
      required-input: value
      optional-input: value
```

### Advanced Usage

```yaml
name: My Project CI with All Options
on: [push, pull_request]

jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/WORKFLOW_FILE.yml@v1
    with:
      # Required inputs
      required-input-1: value1
      required-input-2: value2
      
      # Optional inputs with custom values
      optional-input-1: custom-value
      optional-input-2: 'true'
      
      # Using defaults for other inputs
    secrets:
      SECRET_NAME: ${{ secrets.MY_SECRET }}
```

## Inputs

### Required Inputs

| Input | Type | Description |
|-------|------|-------------|
| `required-input-1` | string | Description of what this input does and why it's required |
| `required-input-2` | number | Another required input |

### Optional Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `optional-input-1` | string | `'default-value'` | Description of this optional input |
| `optional-input-2` | boolean | `false` | Another optional input |
| `optional-input-3` | string | `'tests/'` | Directory configuration example |

## Outputs

| Output | Type | Description |
|--------|------|-------------|
| `output-1` | string | Description of what this output contains |
| `output-2` | number | Another output example |

### Using Outputs

```yaml
jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/WORKFLOW_FILE.yml@v1
    with:
      required-input: value
  
  use-results:
    needs: ci
    runs-on: ubuntu-latest
    steps:
      - name: Use CI results
        run: |
          echo "Result: ${{ needs.ci.outputs.output-1 }}"
```

## Secrets

### Required Secrets

| Secret | Description |
|--------|-------------|
| `REQUIRED_SECRET` | Description of required secret and what it's used for |

### Optional Secrets

| Secret | Default | Description |
|--------|---------|-------------|
| `OPTIONAL_SECRET` | `GITHUB_TOKEN` | Falls back to default token if not provided |

## Artifacts

This workflow produces the following artifacts:

| Artifact | Description | Retention |
|----------|-------------|-----------|
| `artifact-name` | Description of artifact contents | 1 day (PRs) / 7 days (main) |
| `another-artifact` | Another artifact example | Same |

## Requirements

### Repository Requirements

- [ ] Repository must have `[required file/structure]`
- [ ] [Required configuration file] must be present
- [ ] [Optional requirement if applicable]

### Permissions

This workflow requires the following permissions:

```yaml
permissions:
  contents: read      # Required for checkout
  pull-requests: write # Required for [specific feature]
  # Add more as needed
```

## Examples

### Example 1: Python Project

```yaml
name: Python CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/WORKFLOW_FILE.yml@v1
    with:
      python-versions: '["3.11", "3.12"]'
      package-name: my-package
      coverage-min: '80'
```

### Example 2: Different Configuration

```yaml
name: CI with Custom Settings
on: [push, pull_request]

jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/WORKFLOW_FILE.yml@v1
    with:
      # Different configuration example
      custom-setting: value
```

### Example 3: Complex Scenario

```yaml
name: Multi-stage CI
on: [push, pull_request]

jobs:
  test:
    uses: stranske/Workflows/.github/workflows/WORKFLOW_FILE.yml@v1
    with:
      setting: value
  
  deploy:
    needs: test
    if: github.ref == 'refs/heads/main'
    # ... deployment steps
```

## Configuration

### Configuration File

This workflow can be configured using a configuration file (optional):

**`.github/workflow-config.yml`**:
```yaml
setting1: value1
setting2: value2
paths:
  - pattern1
  - pattern2
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENV_VAR_1` | `value` | Description |
| `ENV_VAR_2` | `value` | Description |

## Behavior

### Triggers

This workflow is designed to be called by other workflows using `workflow_call`. It responds to:

- Pull request events
- Push events to specified branches
- Manual workflow dispatch (if enabled)

### Job Flow

1. **Job 1**: Description of first job
2. **Job 2**: Description of second job
3. **Job 3**: Description of final job

Simplified diagram:
```
[Start] → [Job 1] → [Job 2] → [Job 3] → [End]
                       ↓
                  [Optional Job]
```

### Failure Modes

- **If Job 1 fails**: Workflow stops, no artifacts produced
- **If Job 2 fails**: [Describe behavior]
- **If all jobs succeed**: [Describe success behavior]

## Troubleshooting

### Common Issues

#### Issue: Error message or symptom

**Cause**: Explanation of what causes this issue

**Solution**:
```yaml
# Configuration or command to fix the issue
setting: corrected-value
```

#### Issue: Another common problem

**Cause**: What causes this

**Solution**: How to fix it

### Debug Mode

To enable debug logging:

```yaml
jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/WORKFLOW_FILE.yml@v1
    with:
      debug: 'true'
      required-input: value
```

### Getting Help

If you encounter issues:

1. Check this troubleshooting section
2. Review the [examples](#examples)
3. Check workflow run logs
4. Open an issue with:
   - Your workflow configuration
   - Error messages
   - Workflow run link

## Version Compatibility

| Workflow Version | Supported | Notes |
|------------------|-----------|-------|
| v1.x | ✅ Current | Latest features |
| v0.x | ⚠️ Deprecated | Upgrade to v1.x |

### Migration from v0.x to v1.x

If upgrading from v0.x:

1. Update `uses:` line to `@v1`
2. Rename inputs:
   - `old-input-name` → `new-input-name`
3. Review new required inputs
4. Test in a branch before merging

## Implementation Details

_(Optional section for complex workflows)_

### Architecture

Brief explanation of how the workflow is structured internally:

- Job dependencies
- Key steps
- Why certain approaches were taken

### Performance

- Typical runtime: X minutes
- Resource usage: [normal/high/low]
- Parallelization: [yes/no + details]

## Related Workflows

- **[Related Workflow 1](./related-workflow-1.md)**: Brief description of relationship
- **[Related Workflow 2](./related-workflow-2.md)**: How it works together with this one

## Changelog

### v1.1.0 (YYYY-MM-DD)
- Added new feature
- Fixed issue with X

### v1.0.0 (YYYY-MM-DD)
- Initial stable release
- Extracted from Trend_Model_Project

---

**Source**: Extracted from [Trend_Model_Project](https://github.com/stranske/Trend_Model_Project)  
**Original File**: `.github/workflows/ORIGINAL_FILE.yml`  
**Extraction Date**: YYYY-MM-DD  
**Last Updated**: YYYY-MM-DD

## See Also

- [Master Documentation](../README.md)
- [All Workflows](../workflows/)
- [Examples](../examples/)
