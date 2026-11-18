# Repository Structure

Workflows owns the GitHub side of agent delivery and the files distributed to consumer repositories. Start with the change or symptom below. The [repository contract](../AGENTS.md) defines ownership, versioning and review expectations.

## Change a reusable workflow

A consumer job with `uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main` runs the [shared Python CI workflow](../.github/workflows/reusable-10-ci-python.yml). Edit that workflow for shared behavior. For a caller-specific matrix or coverage setting, check the consumer's own CI configuration. First-party callers tracking `@main` receive a shared change as soon as it merges.

Check the workflow’s declared inputs, its [exported outputs](ci/WORKFLOW_OUTPUTS.md) and [consumer integration guide](INTEGRATION_GUIDE.md). For Python CI, run the [reusable workflow tests](../tests/workflows/test_reusable_ci_workflow.py) and exercise the PR revision through [Maint 62](../.github/workflows/maint-62-integration-consumer.yml). It selects scenarios against the local reusable workflow. Verify which scenarios actually ran. The [workflow topology](ci/WORKFLOWS.md) identifies callers and checks for other reusable workflows.

## Change a file distributed to consumers

Locate the target in the [sync manifest](../.github/sync-manifest.yml) and read its section, `source_tree`, `source`, `target`, mode and exceptions. For example, the consumer PR event hub comes from [its consumer template](../templates/consumer-repo/.github/workflows/agents-80-pr-event-hub.yml). Edit that source. Preserve any required root/template pairing. Change the manifest when adding, renaming, removing or changing delivery scope. The standard [PR Gate template](../templates/consumer-repo/.github/workflows/pr-00-gate.yml) is create-only by default, so existing consumers retain their own Gate policy unless the manifest declares an exception.

Use the [manifest delivery tests](../tests/workflows/test_sync_manifest_delivery.py) and [template drift checker](../scripts/check_template_drift.py) before distribution. Inspect the prospective diff in Maint 68, then verify the configured canaries and their same-plan Maint 71 evidence before promotion. Maint 71 owns sync merges. Maint 82 schedules continuations. [Consumer maintenance](ops/CONSUMER_REPO_MAINTENANCE.md) · [Sync procedure](ops/SYNC_DEPENDENCY_CAMPAIGN.md)

## Diagnose a stalled coding task

Start at the issue and linked PR. Read the opener's start comment, PR labels, current head SHA, latest Gate run, unchecked acceptance criteria and pause or human-hold labels. The required aggregate check is [`summary`](../.github/config/required-contexts.json). Use the [expected-check receipt](ops/EXPECTED_CHECK_RECEIPTS.md) when an expected check is absent or an older result looks green.

- **Local start.** A PR marked `agents:local-loop` gets its iterations from Orchestrator’s local loop. Use the [local lane contract and state locations](ops/LOCAL_LANES.md#state-locations) to find the opener target, controller/lane rounds and closer disposition. Trace the most recent action for that issue and SHA. The local loop can hand the PR to hosted keepalive.
- **Hosted start.** On a PR with `agent:*` and `agents:keepalive`, inspect the [Gate-triggered keepalive loop](../.github/workflows/agents-keepalive-loop.yml), its run summary and the PR state comment. Check the [hourly sweep](../.github/workflows/agents-keepalive-sweep.yml) for recovery when a round produced no new event. The [keepalive contract](keepalive/GoalsAndPlumbing.md) and [operator quick reference](QUICK_REFERENCE.md) explain eligibility, holds and retry behavior.
- **After merge.** Follow the verifier evidence on the PR and the closer's disposition on the issue. A failed acceptance check may lead to a repair, follow-up or reopened issue. The [lane contract](ops/LOCAL_LANES.md#lanes-overview) identifies who acts next.

## Where the other material lives

| Area | What it owns |
|---|---|
| [Workflows](../.github/workflows), [actions](../.github/actions), [GitHub helpers](../.github/scripts) | GitHub event entry points, reusable jobs, composite actions and the scripts they run. The [catalog](WORKFLOW_GUIDE.md) records triggers and purpose. |
| [Agent registry](../.github/agents), [agent instructions and prompts](../.github/codex), [configuration](../config) | Agent selection, model and delivery policies, evaluation inputs, and workflow configuration. |
| [Consumer](../templates/consumer-repo) and [integration templates](../templates/integration-repo), [Renovate presets](../renovate-presets) | Material distributed to other repositories and the integration project that exercises shared CI. |
| [Scripts](../scripts), [tools](../tools), [packages](../packages) | Workflow and operator programs, diagnostics, and libraries consumers install from a repository subdirectory. |
| [Tests](../tests), [fixtures](../fixtures), [autofix samples](../src/trend_analysis/README.md) | Automated checks, shared inputs and deliberately defective samples used to exercise repair. |
| [Belt ledgers](../.agents), [agent stubs](../agents), [skills](../skills), [Claude skills](../.claude/skills) | Per-issue belt records, agent-created stub files and instructions for local tools. The [stub maintenance workflow](../.github/workflows/maint-84-prune-agent-stubs.yml) owns eligible stub removal. |
| [Docs index](README.md), [operator guides](ops), [archived workflows](archive/ARCHIVE_WORKFLOWS.md), [historical files](../archives) | Current guides, operating procedures and the history of retired workflows. |
| [Issue evidence](evidence), [recovery evidence](../evidence), [artifacts](../artifacts) | Retained task records. Some are inputs to replay tools or archive-integrity tests. Trace a record's reader before moving it. |
