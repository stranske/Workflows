# Keepalive Observability Contract

Use the workflow run, the PR's Automated Status Summary and the runner receipt to
trace each round. Record the repository, PR, head SHA, workflow run and attempt.
An Actions conclusion describes the workflow. The evaluator decision and worker
evidence describe what happened to the PR.

## Round decisions

[Agents Keepalive Loop](../../.github/workflows/agents-keepalive-loop.yml) is the
Workflows entry point. [Agents Gate Followups](../../templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml)
is the consumer entry point. Gate completion, eligible label events and
[sweep/manual dispatches](GoalsAndPlumbing.md#periodic-re-evaluation-keepalive-sweep)
wake the same evaluator within each lane.

| Stage | What to inspect |
| --- | --- |
| `evaluate` | PR and head binding, `action`, `reason`, Gate conclusion, selected agent and runner dispatch reason. |
| `acceptance-gates` on Workflows | Current-head deterministic acceptance command results. The read-only job provides an artifact to preflight. |
| `preflight` | Selected environment, required credentials, ownership and trusted summary writer. Look for the running summary transition and any challenge receipt. |
| `run-<agent>` | Exact worker attempt, runner outputs, push result and head movement. A skipped job and an executed zero-output job supply different evidence. |
| `finish` | Workflow Summary metrics, task reconciliation, durable PR summary, measured productivity and runner completion. |
| `resolve-target` and `report` in the reporter | The originating run's applicability, exact-attempt worker evidence, and any recovery of the matching authority receipt or running summary. |

The [evaluator](../../.github/scripts/keepalive_loop.js) records decisions such as
`keepalive-disabled`, `missing-agent-label`, `gate-pending`,
`gate-not-success`, `run-cap-zero` and `round-budget-exhausted`. A sweep can
wake evaluation without admitting a worker. Pause labels, head mismatches and
missing evidence remain meaningful after a wake. See the
[activation, run cap and retry contract](GoalsAndPlumbing.md#1-activation-guardrails).

## Comment activation

The [Workflows PR meta manager](../../.github/workflows/agents-pr-meta-v4.yml)
evaluates comments in `keepalive_dispatch` and replays eligible activations
in `keepalive_from_gate`. The [Gate helper](../../.github/scripts/keepalive_gate.js)
checks Gate and dispatch occupancy. The [activation helper](../../.github/scripts/agents_pr_meta_keepalive.js)
checks the activation and author, and the workflow writes the `DISPATCH:`
decision to the run Summary. The [orchestrator helper](../../.github/scripts/agents_pr_meta_orchestrator.js)
handles the reaction lock and submits `codex-pr-comment-command`. The
payload carries the activation comment, agent, instruction, branches, PR
number, round and trace. An accepted event establishes submission. The
[Workflows dispatch handler](../../.github/workflows/agents-keepalive-dispatch-handler.yml)
calls [the post-work remediation helper](../../.github/scripts/keepalive_post_work.js).
Inspect the handler separately for its result.

The [consumer PR Event Hub](../../templates/consumer-repo/.github/workflows/agents-80-pr-event-hub.yml)
calls [reusable PR-meta](../../.github/workflows/reusable-20-pr-meta.yml) for
metadata. That reusable workflow accepts the former activation inputs for
caller compatibility. Consumer keepalive rounds come from Gate Followups.

## Persistent feedback

Keepalive projects durable state into the marked Automated Status Summary on
the PR. A dedicated Keepalive or Workflows App owns the write. Trusted
compatibility readers and migration behavior are documented in the
[authority ledger contract](GoalsAndPlumbing.md#authority-challenge-ledger-v2).
Read the section produced by the trusted writer for iteration, task counts,
outcome, retry state and `running_owner_attempt`. Use the
[metrics schema](METRICS_SCHEMA.md) when consuming the workflow artifact.

The [root reporter](../../.github/workflows/agents-keepalive-loop-reporter.yml)
and [consumer reporter](../../templates/consumer-repo/.github/workflows/agents-keepalive-loop-reporter.yml)
use the [worker evidence helper](../../.github/scripts/keepalive_worker_evidence.js)
to bind a failure or cancellation to its originating attempt. Unresolved target
or worker evidence fails closed. A proven terminal worker that never started
can allow receipt reconciliation. An ordinary run cancelled before any job
existed is reported as not applicable when the exact run and complete empty
job list establish that case.

## 6A) Terminal Disposition Coverage Preflight

The [weekly metrics workflow](../../.github/workflows/agents-weekly-metrics.yml) runs a `workflows-terminal-disposition-coverage/v1` preflight
after downloading agent metrics artifacts. The preflight consumes
`workflows-terminal-disposition/v1` records from verifier and review-thread
handlers and writes both JSON and Markdown reports into the weekly metrics
artifact.

The preflight defaults to `mode=warning-only` and is deliberately non-blocking.
Missing `review-thread:<PR>` source coverage is reported as `status=warning`,
not as a failed check, because local automation remains optional and direct
remote/manual work must stay valid. Hard blocking is only valid when the
machine-readable enforcement policy records `requested_mode=hard-block`,
`hard_block_approved=true`, and no policy blocker such as
`hard-block-approval-required`.

Weekly metrics SHOULD pass the machine-readable
`workflows-weekly-metrics-artifact-selection/v1` selector report into the
preflight. The coverage report records terminal-disposition candidate and
selected artifact counts so `no-data` can be distinguished from selector
failure, download failure, or a real absence of terminal artifacts.

Required report fields:

- `schema=workflows-terminal-disposition-coverage/v1`
- `mode` / `enforcement.mode`: `warning-only` by default; `hard-block` only
  when explicitly approved
- `coverage_status`: the observed terminal coverage result before enforcement
- `enforcement.requested_mode`
- `enforcement.hard_block_approved`
- `enforcement.hard_block_active`
- `enforcement.should_fail`
- `enforcement.policy_blockers[]`
- `policy.schema=workflows-terminal-disposition-enforcement-policy/v1`
- `terminal_record_count`
- `expected_source_count`
- `covered_source_count`
- `missing_source_count`
- `missing_sources[]` with stable `source_key` values
- `artifact_selection` with selector status plus terminal-disposition candidate
  and selected artifact counts when a selector report is available
- `workflows-terminal-disposition/v1` records SHOULD include `artifact_name`
  and `artifact_family` when the emitting workflow uploads them as Actions
  artifacts

### Optional runner capability evidence

Registry-backed runners may additionally expose the v1.1 agent-runner outputs
`capability-id`, `effect-fingerprint`, `evidence-artifact-ref`,
`supervision-mode`, `capability-evidence-status`, and `terminal-disposition`.
These values are typed evidence intended for the existing Orchestrator
completion-event plane. Runner validation and emission do not themselves add
Orchestrator-side ingestion, create a second terminal-disposition record, or
authorize a capability transition. Empty values mean no capability evidence was
supplied.

---

## 8) Orchestrator Contract

For an ordinary hosted round, inspect the reusable worker's publication steps,
then compare the PR's current head to the reserved head. The `finish` job
measures productivity and records completion through
[`runner_lib`](../../scripts/runner_lib/__main__.py). An unchanged head leaves the
PR eligible for a later sweep recheck. An unreadable head prevents recording a
productivity result. Treat a branch update or a new Gate run as evidence only
after binding it to the current PR head.

For a comment-command round that needs branch recovery, use the
[branch-sync gate](GoalsAndPlumbing.md#9-branch-sync-gate). The
[dispatch handler](../../.github/workflows/agents-keepalive-dispatch-handler.yml)
has its own head-change checks and uses `agents:sync-required` when it cannot
establish synchronization. Inspect its Summary and confirm a new Gate result
for the actual head before proceeding.

The [historical connector contract](https://github.com/stranske/Workflows/blob/114af08b46ed714e139691b6691d465fb16ac567/docs/keepalive/Observability_Contract.md)
retains the original instruction, worker and sync marker examples.
