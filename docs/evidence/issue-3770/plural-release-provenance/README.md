# Historical plural release provenance proof

The exact PR #3787 release body uses `historical fixes ([#3782](...))`.
The prior parser required merged PR #3782 as an issue, reproducing production
run 37481681340's source-fetch error. The fixture retains the complete captured
body, title, release branch and SHA. Test origin/auth/REST responses are synthetic.

The shared resolver recognizes the historical plural noun while preserving
explicit metadata, closing/Related-to/branch issue sources, ambiguity, and
malformed/inaccessible required-source failures. Consumer source bytes match.
The real verifier context builder is exercised for both source and consumer.
Original #3769 regression and genuine source controls remain in the named scope.

Validation: `node --test .github/scripts/__tests__/source-context.test.js .github/scripts/__tests__/agents-verifier-context.test.js`
passes all162 tests. Independently replacing ONLY root, then ONLY consumer parser
with original base bytes fails4 tests in each experiment. Byte-identical fixed
restoration passes162 in each. Complete stdout/exit codes and source hashes are
retained. `local_verify.py` also extracts the base, overlays the two test files
and new fixture, and observes RED4/GREEN162; its per-node Python attribution is
unavailable for JavaScript, which is disclosed in its transcript.

Full GitHub scripts suite:1985 passed,1 skipped,0failed (1986 collected).
Template sync/completeness, both source/context `cmp` controls and diff check pass.
The unchanged verifier-context implementation already enforces malformed source
contracts, so no new context production edit is needed.

Replay the named Node command from the repository root; it creates disposable
context outputs outside the retained evidence. Verify `manifest.json` hashes
before assessing captures. No whole-repository coverage or live provider PASS
is asserted. Preserve original runs37400729553/37481681340 CONCERNS/NON_PASS.

After guarded merge, Reviewed Repo Orphan PR Steward owns exactly one repaired-input
comparison for each release3769/3787 with complete source-context/artifact inventories.
Reviewed Repo Merge Verify Closer then dispositions source3770 against actual
provider verdicts. This source issue remains OPEN until all follow-through is met.
