# Route-weight exploration acceptance

Source issue #3840; implementation PR #3857. The issue's exact command is now a
small entry point into the existing canonical suite, with no duplicated test or
changed production selection behavior:

```sh
node --test .github/scripts/agent_delegation_policy.test.js
node -e "const p=require('./.github/scripts/agent_delegation_policy.js'); console.txt(JSON.stringify(p.pickAgent({taskType:'implement', routeWeights: require('./tests/fixtures/route-weights-with-exploration.json'), seed: 7})))"
```

The second command prints agent `gemini`, `delegationSource` equal to
`route_weights_exploration`, and `policy_version` equal to `exploration-2026-10-06`.

The retained logs record the same unchanged command against three states:

1. `candidate-green.txt`: candidate production behavior passes.
2. `production-exploration-disabled-red.txt`: replace the production statement
   `const exploration = routeWeights.exploration;` with
   `const exploration = undefined;`; the seeded challenger assertions fail.
3. `exact-restoration-green.txt`: restore the original source bytes; the suite passes.

`receipt.json` records exit codes and equal original/restored production hashes.
This is local production-path acceptance. It does not claim an observed deployed
worker cycle or a provider PASS. The original comparison remains CONCERNS/PASS;
this follow-up requires its own exact-head review, checks, merge and comparison.
