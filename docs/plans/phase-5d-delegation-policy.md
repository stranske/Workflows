# Agent delegation policy

The policy runs in [`.github/scripts/agent_delegation_policy.js`](../../.github/scripts/agent_delegation_policy.js).
Issue intake calls it from [Agents 63](../../.github/workflows/agents-63-issue-intake.yml).
The [intake policy suite](../../.github/scripts/__tests__/agent-delegation-policy-intake.test.js)
exercises the current behavior.

Run from the repository root:

```sh
node --test .github/scripts/__tests__/agent-delegation-policy-intake.test.js
```

See the [historical Phase 5D design](../archive/OPERATOR_SOURCE_HISTORY.md).
