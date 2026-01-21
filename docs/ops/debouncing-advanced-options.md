# Advanced Debouncing Options

## External Debouncer Service

**What it solves:** Cancels duplicate dispatches across repos or workflow types before GitHub Actions starts a run.

**Requirements:**
- Dedicated service/runtime with authenticated ingress.
- Signed event ingestion and idempotent queueing.
- Audit log storage for replay and debugging.
- Per-repo policy configuration with safe defaults.
- Fallback path when the service is unavailable.

**Risks:**
- Introduces a new critical dependency in the automation chain.
- Operational overhead (hosting, scaling, on-call support).

**Decision signals:**
- Need to debounce across multiple repos or workflow families.
- Willing to run and support a 24/7 service with on-call coverage.

**Next steps:**
- Draft an RFC covering ownership, on-call support, and MVP scope.
- Scope MVP to a single repo and single workflow family.

## GitHub App Filtering

**What it solves:** Uses a GitHub App to gate high-frequency events and dispatch workflows only for the latest state.

**Requirements:**
- GitHub App with actions:write and pull_request scopes.
- Webhook receiver to enforce event ordering.
- Logic to collapse duplicate events.
- Persistent store for run locks/state.

**Risks:**
- App rate limits and deployment complexity.
- Requires webhook hosting and storage lifecycle management.

**Decision signals:**
- Need per-event filtering before Actions runners are allocated.
- Have a reliable webhook host and datastore available.

**Next steps:**
- Prototype an event filter for one workflow type.
- Measure dispatch reductions before expanding.
