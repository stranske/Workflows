# Keepalive approaches

The current CLI keepalive route uses the agent registry to select a runner.
Codex, Claude, Cursor, Muse and Gemini each have a registered workflow; the
[Multi-Agent Routing guide](MULTI_AGENT_ROUTING.md) describes the labels and
current routing. Use [Goals & Plumbing](GoalsAndPlumbing.md) for activation,
repeat and stop rules, and the [Observability Contract](Observability_Contract.md)
for summaries and branch recovery.

The earlier UI connector approach exchanged instructions and results through
PR comments. The current PR metadata code still recognizes connector-bot
checkboxes for compatibility; their presence alone does not identify a PR as
using a separate keepalive implementation. The [original comparison](https://github.com/stranske/Workflows/blob/8e7fcfd78bfe1d22547dc0a17b3edb14a1d0b9e6/docs/keepalive/Keepalive_Approaches.md)
records the older Codex-focused description. See the [PR metadata updater](../../.github/scripts/agents_pr_meta_update_body.js)
for its current connector-comment handling.

For setup and metrics, see the [integration guide](Keepalive_Integration.md) and
[metrics schema](METRICS_SCHEMA.md).
