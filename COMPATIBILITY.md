# Compatibility Policy

This repository follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html) for all reusable workflows, composite actions, and helper scripts. The policy below explains what constitutes a breaking change, how long versions are supported, and how consumers are notified about upcoming changes.

## What is a breaking change?

Breaking changes are any change that can alter a consumer’s behavior without them opting in. Examples include:

- Removing or renaming workflow inputs, outputs, jobs, or steps that consumers rely on.
- Changing default values in a way that alters existing behavior (e.g., enabling a check by default that was previously opt-in).
- Adding new required inputs or secrets.
- Dropping support for a runtime, operating system, or toolchain version advertised as supported within the previous major release.
- Renaming or moving published artifacts that consumers download from workflow runs.

## Version support window

We support at least two major versions at any given time:

- **Current major (v1.x)** – Actively maintained with fixes and backward-compatible enhancements. Floating tag `@v1` points to the latest v1.x release.
- **Previous major** – Remains supported for a minimum of 12 months after a new major is released. Only critical fixes and security updates are provided.
- **Older majors** – Enter end-of-life (EOL) after the 12-month overlap window.

### Compatibility matrix

| Major version | Status | Support level | Notes |
| --- | --- | --- | --- |
| v2 (future) | Planned | Pre-release planning only | Breaking changes land here after deprecation periods end. |
| v1 (current) | Active | Full support | Receives all fixes and backward-compatible enhancements. |
| v0 (legacy) | EOL | No updates | Superseded by v1. Upgrade required. |

## Deprecation and removal timeline

1. **Mark and warn** – Deprecated inputs, outputs, or behaviors gain a clear “deprecated” label in documentation and emit workflow warnings when used.
2. **Document the window** – The removal target is documented in the changelog and here (typically deprecated in v1.x, removed no earlier than v2.0.0).
3. **Removal** – The deprecated surface is removed in the next major release after the published deprecation window elapses.

## Notification channels

Consumers are notified of breaking changes and deprecations via:

- **CHANGELOG.md** – Every release notes section calls out breaking changes with a `BREAKING` marker.
- **Release notes** – GitHub releases summarize new features, deprecations, and removals.
- **Repository Discussions/Announcements** – Used for major-impact changes or migration guides.
- **Workflow warnings** – Deprecated inputs emit warnings directly in workflow logs to surface changes during CI runs.

## Recommended consumption strategy

- Use the floating major tag (e.g., `@v1`) for automatic backward-compatible fixes.
- Pin to a specific release (e.g., `@v1.0.0`) when you need reproducibility; monitor changelog warnings before upgrading.
- Start migration while a deprecated feature still emits warnings to avoid surprises when the next major release arrives.
