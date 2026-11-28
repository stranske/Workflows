# User Guides

How-to guides and tutorials for using this workflow system.

This folder is intentionally small right now; most “getting started” and integration material lives at the docs root.

## Start Here (Docs Root)

- [../USAGE.md](../USAGE.md)
- [../INTEGRATION_GUIDE.md](../INTEGRATION_GUIDE.md)
- [../ci-workflow.md](../ci-workflow.md)

## Available Guides

- **[Gemini Runner Operator Notes](GEMINI_RUNNER.md)** - Set up the hosted Gemini runner and troubleshoot its sign-in and output.
- **[Adding a New Coding Agent](ADD_NEW_AGENT.md)** - Stage-gated checklist for bringing an agent through registry, runner, pipeline wiring, consumer delivery, tests, canaries and the parity review
- **[Agent Readiness Evaluations](agent-readiness/README.md)** - Template and worked evaluations (currently `agy`) that decide whether an agent should be integrated, with re-evaluation triggers
- **[Agent Runner Implementation](AGENT_RUNNER_IMPLEMENTATION.md)** - Technical patterns for building and debugging agent runner workflows (CLI invocation, unpushed commit detection, artifact filtering, push retry)
- **[Dual-Location Sync Gotcha](dual-location-sync-gotcha.md)** - Critical gotcha when updating files that exist in both `.github/` and `templates/consumer-repo/`
- [Declaring the app-baseline-kit dependency](BASELINE_KIT_DEPENDENCY.md)

## Contributing guides

Add a guide here for a procedure with an identified owner. Link it from this
index and from the relevant operator documentation.

## See Also

- [Workflow Documentation](../workflows/)
- [Workflow examples](../USAGE.md#examples)
- [Reference Documentation](../reference/)
- [Historical operator source records](../archive/OPERATOR_SOURCE_HISTORY.md)
