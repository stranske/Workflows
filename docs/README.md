# Documentation

This folder contains the source-of-truth documentation for this repository.

## Start Here

| Document | Description |
|----------|-------------|
| [USAGE.md](USAGE.md) | Quick start and common setup patterns |
| [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) | Full integration guide for consumers |
| [ci-workflow.md](ci-workflow.md) | CI workflow wiring and local validation |
| [STRUCTURE.md](STRUCTURE.md) | How the repository is organized |
| [AGENTS_POLICY.md](AGENTS_POLICY.md) | Agent automation policies |

## Structure

### For Users

- **[guides/](guides/)** - How-to guides and tutorials (currently minimal)
- **[ci/](ci/)** - CI reference docs and troubleshooting
- **[keepalive/](keepalive/)** - Keepalive/Codex automation documentation
- **[reference/](reference/)** - Reference docs and analysis notes
- **[workflows/](workflows/)** - Workflow system notes (evaluation, bug reports)
- **[examples/](examples/)** - Runnable examples (placeholder)

### For Contributors

- **[templates/](templates/)** - Templates and checklists
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Contribution guidelines

### Archive

- **[archive/](archive/)** - Historical documents and snapshots

## Documentation Guidelines

### Workflow Documentation

Each workflow should have its own file in `workflows/` using the template from `templates/WORKFLOW_TEMPLATE.md`:

- Clear description of purpose
- Complete input/output documentation
- Working examples
- Troubleshooting guide
- Version compatibility information

### Guides

How-to guides in `guides/` should:

- Address a specific task or goal
- Provide step-by-step instructions
- Include working examples
- Link to related documentation

### Examples

Examples in `examples/` should:

- Represent real-world use cases
- Be complete and runnable
- Cover common scenarios
- Include explanatory comments

## Adding Documentation

1. Use the appropriate template from [templates/](templates/)
2. Keep examples runnable and aligned with the current workflow interfaces
3. Prefer stable references (`@v1`) in consumer-facing examples; reserve `@main` for intentional unreleased testing
4. Cross-link related docs and update this README if you add a new top-level category

## See Also

- Main README: [../README.md](../README.md)
- Templates and checklists: [templates/](templates/)
- Latest workflow audit: [WORKFLOW_AUDIT_2025-12-25.md](WORKFLOW_AUDIT_2025-12-25.md)
