# User Guides

How-to guides and tutorials for using this workflow system.

This folder is intentionally small right now; most “getting started” and integration material lives at the docs root.

## Start Here (Docs Root)

- [../USAGE.md](../USAGE.md)
- [../INTEGRATION_GUIDE.md](../INTEGRATION_GUIDE.md)
- [../ci-workflow.md](../ci-workflow.md)

## Available Guides

- **[Adding a New Coding Agent](ADD_NEW_AGENT.md)** - Stage-gated checklist for bringing an agent through registry, runner, pipeline wiring, consumer delivery, tests, canaries and the parity review
- **[Agent Readiness Evaluations](agent-readiness/README.md)** - Template and worked evaluations (currently `agy`) that decide whether an agent should be integrated, with re-evaluation triggers
- **[Agent Runner Implementation](AGENT_RUNNER_IMPLEMENTATION.md)** - Technical patterns for building and debugging agent runner workflows (CLI invocation, unpushed commit detection, artifact filtering, push retry)
- **[Dual-Location Sync Gotcha](dual-location-sync-gotcha.md)** - Critical gotcha when updating files that exist in both `.github/` and `templates/consumer-repo/`

## Planned Guides

### Getting Started
- **Quick Start** - Get up and running in 5 minutes
- **Installation** - Setting up workflows in your repository
- **Configuration** - Configuring workflows for your project

### Common Tasks
- **Setting Up Python CI** - Complete guide for Python projects
- **Adding Code Coverage** - Tracking and enforcing coverage
- **Configuring Autofix** - Automated code formatting
- **Health Checks** - Monitoring repository health
- **Release Automation** - Automated releases with tags

### Advanced Topics
- **Custom Workflows** - Creating project-specific workflows
- **Extending Workflows** - Building on top of reusable workflows
- **Troubleshooting** - Debugging workflow issues
- **Performance Optimization** - Making workflows faster
- **Security Best Practices** - Securing workflow configurations

### Integration Guides
- **Migrating from Other CI Systems** - Travis, CircleCI, Jenkins, etc.
- **Integrating with Other Tools** - Codecov, SonarQube, etc.
- **Multi-Repository Setup** - Using workflows across organizations

## Contributing Guides

To add a new guide:

1. Create a markdown file in this directory
2. Follow the guide template structure:
   - Introduction (what and why)
   - Prerequisites
   - Step-by-step instructions
   - Examples
   - Troubleshooting
   - Next steps
3. Update this README with a link to your guide
4. Cross-reference related documentation

## Guide Template Structure

```markdown
# Guide Title

Brief description of what this guide covers.

## What You'll Learn

- Bullet point 1
- Bullet point 2

## Prerequisites

- Requirement 1
- Requirement 2

## Steps

### Step 1: [Action]

Instructions...

### Step 2: [Action]

Instructions...

## Example

Complete working example...

## Troubleshooting

Common issues and solutions...

## Next Steps

- Link to related guide 1
- Link to related guide 2
```

## See Also

- [Workflow Documentation](../workflows/)
- [Examples](../examples/)
- [Reference Documentation](../reference/)
