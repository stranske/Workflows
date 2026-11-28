# Compatibility Policy

The [integration guide](INTEGRATION_GUIDE.md#versioning-strategy) defines supported consumer pins. The [earlier version-support proposal](https://github.com/stranske/Workflows/blob/0c0334c6e92588c158f1c9362f1409062477de09/docs/COMPATIBILITY.md) is historical.

## What is a breaking change?

Breaking changes are any change that can alter a consumer’s behavior without them opting in. Examples include:

- Removing or renaming workflow inputs, outputs, jobs, or steps that consumers rely on.
- Changing default values in a way that alters existing behavior (e.g., enabling a check by default that was previously opt-in).
- Adding new required inputs or secrets.
- Dropping support for a runtime, operating system, or toolchain version advertised as supported within the previous major release.
- Renaming or moving published artifacts that consumers download from workflow runs.

## Version support window

`@main` is the single supported consumer pin for reusable workflows. A commit
SHA can be used for a one-off reproducible build or a controlled rollout, but
standard helper checkouts still default to `main`. The floating `@v1` tag is
not a supported consumer pin. See the [versioning strategy](INTEGRATION_GUIDE.md#versioning-strategy)
for the exact scope and tradeoffs.

### Compatibility matrix

The integration guide is the current matrix for supported pins; it does not
promise a parallel supported previous major or a fixed overlap period.

## Deprecation and removal timeline

Consult the current integration guidance and the specific change's documentation
for migration and deprecation details. A release number alone does not establish
a promised removal window.

## Notification channels

Review the change documentation, release notes and relevant workflow warnings
when assessing a migration.

## Recommended consumption strategy

- Use `@main` when you want the current first-party consumer behavior.
- Pin to a specific commit SHA when you need reproducibility; monitor changelog warnings before upgrading.
- Follow the specific change documentation and verify consumer compatibility before migrating.
