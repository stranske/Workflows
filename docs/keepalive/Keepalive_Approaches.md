# Keepalive approaches

The hosted keepalive loop uses the agent registry to select a runner.
[Workflows uses Agents Keepalive Loop](../../.github/workflows/agents-keepalive-loop.yml).
[Consumers use Agents Gate Followups](../../templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml).
A Gate event or hourly sweep can wake evaluation for an opted-in PR. Use
[Goals & Plumbing](GoalsAndPlumbing.md) for admission, repeat and stop rules,
and [Multi-Agent Routing](MULTI_AGENT_ROUTING.md) for the five registered
workers.

Workflows also has a [PR comment activation path](Observability_Contract.md#comment-activation)
with its own dispatch and remediation evidence.

The earlier UI connector approach exchanged instructions and results through
PR comments. The current PR metadata code still recognizes connector-bot
checkboxes for compatibility. The [original comparison](https://github.com/stranske/Workflows/blob/8e7fcfd78bfe1d22547dc0a17b3edb14a1d0b9e6/docs/keepalive/Keepalive_Approaches.md)
records the older Codex-focused description. See the [PR metadata updater](../../.github/scripts/agents_pr_meta_update_body.js)
for its current connector-comment handling.

For setup and metrics, see the [integration guide](Keepalive_Integration.md) and
[metrics schema](METRICS_SCHEMA.md).
