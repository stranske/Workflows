# Workflow Documentation

Individual documentation files for each extracted workflow.

## Structure

Each workflow should have its own markdown file:

```
workflows/
├── reusable-10-ci-python.md       # Python CI workflow
├── reusable-12-ci-docker.md       # Docker smoke tests
├── reusable-18-autofix.md         # Autofix orchestration
├── health-42-actionlint.md        # Workflow linting
├── maint-52-validate-workflows.md # Workflow validation
└── ...                            # Additional workflows
```

## Documentation Template

Use [../templates/WORKFLOW_TEMPLATE.md](../templates/WORKFLOW_TEMPLATE.md) when creating new workflow documentation.

Each workflow documentation file should include:

1. **Overview** - What the workflow does and why to use it
2. **Usage** - Basic and advanced usage examples
3. **Inputs** - All inputs (required and optional) with descriptions
4. **Outputs** - All outputs with descriptions
5. **Secrets** - Required and optional secrets
6. **Artifacts** - Artifacts produced by the workflow
7. **Examples** - Multiple real-world examples
8. **Troubleshooting** - Common issues and solutions
9. **Version Compatibility** - Supported versions and migration guides

## Naming Convention

File names should match the workflow file names (without the `.yml` extension):

- Workflow: `.github/workflows/reusable-10-ci-python.yml`
- Documentation: `docs/workflows/reusable-10-ci-python.md`

## Status

Currently empty - workflow documentation will be added as workflows are extracted.

## See Also

- [Workflow Template](../templates/WORKFLOW_TEMPLATE.md)
- [Main Documentation README](../README.md)
- [Examples](../examples/)
