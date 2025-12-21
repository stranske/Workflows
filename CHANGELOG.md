# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Release workflow now refreshes the floating `v1` tag on every `v1.x` release, and the floating-tag maintenance job also runs when a `v1.x` release is published.
- Tests cover creating the floating `v1` tag when it does not yet exist, ensuring it points to the latest `v1.x` release.
- Documentation now outlines the recommended versioning strategy, including when to use pinned (`@v1.0.0`) versus floating (`@v1`) tags in both the README and Integration Guide.

## [1.0.0] - 2024-12-16

### Added

#### Workflows (36 files)
- **CI Workflows**: `ci-python`, `ci-cosmetic`, `ci-gate`
- **Health Checks**: `health-40-*` through `health-50-*` (8 workflows)
- **Maintenance**: `maint-45-*` through `maint-60-*` (10 workflows)
- **Agent Orchestration**: `agents-*` (11 workflows)
- **Reusable Workflows**: Python CI, Docker CI, autofix, agents, issue bridge

#### Composite Actions (12)
- `autofix/` - Automated code formatting
- `python-setup/` - Python environment setup
- `coverage-delta/` - Coverage tracking
- `keepalive-gate/` - Keepalive validation
- And 8 more supporting actions

#### Scripts
- 49 helper scripts in `.github/scripts/`
- 19 standalone tools in `scripts/`
- Validation system: `check_branch.sh`, `dev_check.sh`, `validate_fast.sh`

#### Tests (316 total)
- 128 JavaScript tests
- 188 Python tests
- Comprehensive test fixtures for keepalive, agents, orchestrator

#### Documentation (63 files)
- CI system documentation
- Keepalive system guides
- Workflow templates and examples
- Archive of planning documents

#### Infrastructure
- Pre-commit hooks (black, ruff, yaml validation)
- Devcontainer configuration
- Issue templates (6 templates)

### Notes

This is the initial release, extracted from [Trend_Model_Project](https://github.com/stranske/Trend_Model_Project).
The extraction preserved all functionality while making the workflow system independent and reusable.
