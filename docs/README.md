# Documentation

Permanent documentation for the Workflows repository.

## Quick Links

| Document | Description |
|----------|-------------|
| [LABELS.md](LABELS.md) | Label reference for PR/issue triggers |
| [WORKFLOW_GUIDE.md](WORKFLOW_GUIDE.md) | Complete workflow usage guide |
| [AGENTS_POLICY.md](AGENTS_POLICY.md) | Agent automation policies |
| [USAGE.md](USAGE.md) | Getting started guide |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guidelines |
| [COMPATIBILITY.md](COMPATIBILITY.md) | Version compatibility |
| [WORKFLOW_AUDIT_2025-12-25.md](WORKFLOW_AUDIT_2025-12-25.md) | Latest workflow audit |

## Structure

### For Users

- **[guides/](guides/)** - How-to guides and tutorials for using the workflows
- **[workflows/](workflows/)** - Individual workflow documentation (one file per workflow)
- **[examples/](examples/)** - Example configurations for different project types
- **[reference/](reference/)** - Reference documentation and API details

### For Contributors

- **[templates/](templates/)** - Templates for creating new documentation
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Contribution guidelines

### Archive

- **[archive/](archive/)** - Working files and historical documents

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

1. Use the appropriate template from `templates/`
2. Follow the existing structure and style
3. Test all examples before committing
4. Update this README if adding new categories
5. Cross-reference related documentation

## Documentation Status

- ✅ Templates created
- ⬜ User guides (to be added as workflows are extracted)
- ⬜ Workflow documentation (to be added per workflow)
- ⬜ Examples (to be created for common use cases)
- ⬜ Reference documentation (to be added)

## Quick Links

- **Main README**: [../README.md](../README.md)
- **Workflow Template**: [templates/WORKFLOW_TEMPLATE.md](templates/WORKFLOW_TEMPLATE.md)
- **Extraction Planning**: [../.extraction/README.md](../.extraction/README.md) (temporary)

---

**Note**: For extraction-phase documentation, see [.extraction/](.extraction/) (temporary directory).
