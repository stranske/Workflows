# Examples

Complete, runnable examples demonstrating how to use the workflows in different scenarios.

## Structure

Examples organized by project type and use case:

```
examples/
├── python-basic/           # Basic Python project
├── python-coverage/        # Python with coverage requirements
├── python-multi-version/   # Python testing multiple versions
├── python-monorepo/        # Python monorepo structure
├── node-basic/             # Basic Node.js project
├── docker-only/            # Docker-focused project
├── multi-language/         # Projects with multiple languages
└── custom-workflows/       # Examples of extending workflows
```

## Example Structure

Each example directory should contain:

```
example-name/
├── README.md              # Example documentation
├── .github/
│   └── workflows/
│       └── ci.yml         # Workflow configuration
├── [project files]        # Minimal project structure
└── expected-output.md     # What to expect when running
```

## Example Categories

### By Language/Framework

- **Python**: Basic, with coverage, multi-version, monorepo
- **Node.js**: Basic, with npm, with yarn
- **Docker**: Dockerfile projects
- **Go**: Basic Go projects
- **Multi-language**: Projects mixing languages

### By Use Case

- **CI/CD**: Testing and deployment
- **Code Quality**: Linting, formatting, type checking
- **Coverage**: Coverage tracking and enforcement
- **Release**: Automated releases
- **Health Checks**: Repository monitoring

### By Complexity

- **Minimal**: Simplest possible setup
- **Standard**: Common production setup
- **Advanced**: Complex multi-stage pipelines
- **Enterprise**: Large-scale configurations

## Adding Examples

To add a new example:

1. Create a new directory with descriptive name
2. Add complete, working project files
3. Include `.github/workflows/` with workflow configuration
4. Write comprehensive README.md explaining:
   - What the example demonstrates
   - Prerequisites
   - How to use it
   - Expected behavior
   - How to adapt for your project
5. Test the example works as documented
6. Update this README with link to new example

## Example README Template

```markdown
# [Example Name]

Brief description of what this example demonstrates.

## What This Example Shows

- Feature 1
- Feature 2
- Feature 3

## Structure

\`\`\`
[file tree]
\`\`\`

## Prerequisites

- Requirement 1
- Requirement 2

## How to Use

1. Step 1
2. Step 2
3. Step 3

## Workflow Configuration

Explanation of the workflow setup...

\`\`\`yaml
[key parts of configuration]
\`\`\`

## Expected Results

What happens when the workflow runs...

## Adapting for Your Project

How to modify this example for different needs...

## See Also

- Related documentation
- Related examples
```

## Status

Currently empty - examples will be added as workflows are extracted and validated.

## Planned Examples

- [ ] Python basic CI
- [ ] Python with coverage enforcement
- [ ] Python multi-version matrix
- [ ] Docker build and test
- [ ] Node.js with npm
- [ ] Autofix integration
- [ ] Complete gate setup
- [ ] Multi-language project

## See Also

- [Workflow Documentation](../workflows/)
- [User Guides](../guides/)
- [Main README](../README.md)
