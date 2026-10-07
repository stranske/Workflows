# Issue 3793: durable attempt presence, existing PR 3792

The retained consumer proof compares the original exact head
`6102cc666ac99371d2196f038969ca481b314f20` with the repaired actual consumer helper.
All GitHub responses are simulated; no live API load is generated. The server
retains inventories across helper module reloads and pins their visibility to
commit snapshots. Three ledgerless negative PRs previously required **3,003**
index blob reads. Repair performs one **1,001**-blob complete migration and one
inventory write, then **zero** additional index blob reads across separate later
helper instances. A cached positive PR with a missing ledger still fails.

Run from a checkout with the original commit available locally:

```sh
node docs/evidence/issue-3793-presence/consumer-proof.js
node --test .github/scripts/__tests__/keepalive-attempt-presence.test.js .github/scripts/__tests__/keepalive-authority-state.test.js .github/scripts/__tests__/keepalive-reporter-applicability.test.js
```

`consumer-proof.json` records actual measured mock API counts, not an estimate.
`focused-green.log` records 87 passing authority/presence/reporter tests, including
both source/template surfaces. Mutable-tree tests prove older-writer
negative-to-positive invalidation and rejection of changes during warm reads,
backfill, and publication. Publication failure cases include lost response,
conflicting inventory, and malformed readback. Inventories are create-only;
conflicting publication is accepted only if the complete validated set agrees.

Deliberate control: remove the final warm-read subtree recheck from the production
source helper, then run the `concurrent changes` regression. `warm-guard-red.log`
records exit 1 and the missing rejection; the source was restored byte-for-byte
before the retained 87-test GREEN run. This is an actual source mutation, not a
fixture-only failure or an invented assertion transcript.

Source/template helper bytes match. Template sync, completeness and drift checks
pass. This packet establishes the local bounded protocol repair; the Major thread
and source issue remain open pending exact-head reviewer disposition, complete
hosted CI/topology, seven-minute review floor, squash merge, and actual issue-bound
`verify:compare`. No deployed protection or provider PASS is claimed here.
