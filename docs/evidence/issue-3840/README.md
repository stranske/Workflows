# Route-weight exploration acceptance

Source issue #3840; implementation PR #3857. The issue's exact command is now a
small entry point into the existing canonical suite, with no duplicated test or
changed production selection behavior:

```sh
node --test .github/scripts/agent_delegation_policy.test.js
node -e "const p=require('./.github/scripts/agent_delegation_policy.js'); console.log(JSON.stringify(p.pickAgent({taskType:'implement', routeWeights: require('./tests/fixtures/route-weights-with-exploration.json'), seed: 7})))"
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

On 2026-10-12, the named acceptance test was extended to check 100,000 fixed
seeds against the published rate with a 0.3 percentage-point tolerance. It
observed 5,062 exploration selections (5.062%), and checked the challenger,
delegation source and policy version for every selection.

The current sandbox's default Node v24.21.0 test runner reports only a passing
file wrapper. To verify execution of the individual tests, these additional
commands were run:

```sh
node --test --test-isolation=none .github/scripts/agent_delegation_policy.test.js
node --test --test-isolation=none .github/scripts/__tests__/keepalive-loop.test.js
```

All 41 delegation tests and 189 keepalive tests passed. The named acceptance
test also failed with exploration disabled and passed after restoring the
production source; see `rate-mutation-proof.txt`. That proof uses
`--test-isolation=none` and the full acceptance test name as
`--test-name-pattern`, so the wrapper alone cannot supply the result.

The canonical delegation suite now automates the green/red/restored-green proof
in an isolated temporary tree. It runs the named acceptance test directly,
requires the disabled exploration read to fail with the `cursor` vs. `gemini`
assertion, and requires restoration to pass. The test also checks the named TAP
result, so an empty or file-only report cannot count as acceptance. No checkout
source is mutated, and temporary files are removed after the test.

Verified locally on 2026-10-12:

- [x] Seeded exploration selects an eligible, non-reserved published challenger and otherwise retains ranking.
- [x] Exploration returns `route_weights_exploration` and the published `policy_version`.
- [x] The keepalive summary prints the exploration policy version.
- [x] The documented `node --test` command exits 0; direct execution confirms the named case runs.
- [x] The documented seed-7 command returns `gemini`, `route_weights_exploration`, and `exploration-2026-10-06`.
- [x] Disabling exploration fails the named test; restoring it passes, now checked automatically.

Validation: 42 tests pass with `node --test --test-isolation=none
.github/scripts/agent_delegation_policy.test.js`. Another 226 pass with
`node --test --test-isolation=none
.github/scripts/__tests__/agent-delegation-policy.test.js
.github/scripts/__tests__/keepalive-loop.test.js`.
