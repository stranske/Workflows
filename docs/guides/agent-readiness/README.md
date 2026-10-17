# Agent Readiness Evaluations

Before a new coding agent is wired into Workflows (see
[Adding a New Coding Agent](../ADD_NEW_AGENT.md)), it is evaluated here. An evaluation answers one
question: **can this agent do unattended work in our pipeline, on a clean runner, without spending
money or taking risks the owner has not accepted?** It also records the limitations in a form that
can be re-checked as the agent improves, so a "not yet" today becomes a cheap test later instead of
a new investigation.

## Files

| File | Purpose |
| --- | --- |
| [TEMPLATE.md](TEMPLATE.md) | Copy this to start an evaluation. |
| [agy.md](agy.md) | Worked evaluation of the Antigravity CLI (`agy`), the first one written. |

## Verdicts

| Verdict | Meaning |
| --- | --- |
| **Ready** | Every blocker row passes with evidence; proceed through the stages in the guide. |
| **Ready for local use only** | The agent works under supervision on a machine with a logged-in session, but a blocker prevents hosted CI use. Local lanes may use it; do not add Workflows runner wiring. |
| **Not ready** | A blocker fails or is unknown for both uses. Record what would change the answer. |

## Rules for writing an evaluation

1. **Every cell names its evidence class**: production use, real trial, fixture check, or wiring
   check (defined in the guide). Documentation quotes are wiring checks, however authoritative.
2. **Say "unknown — would need X" instead of leaving a cell out or guessing.** Each unknown must
   name the cheapest probe that would resolve it.
3. **Separate hosted CI from local use.** An agent can be fine on a developer machine with an
   interactive login and unusable on a runner. Evaluate both and say which one a limitation affects.
4. **Never record credentials, device codes, local paths or personal identifiers.** Describe where a
   credential lives generically.
5. **Date the evaluation and name the CLI version.** These tools change monthly. Re-run the
   re-evaluation triggers rather than trusting an old verdict.
6. Do not assume a vendor's own billing statements cover your usage pattern; verify against the
   vendor's usage ledger with a before/after reading when money or a subscription meter is at stake.
