# Fork-publisher provenance acceptance

Existing PR3813/source3757, finding4206459739. This evidence extends the prior
cross-event repair; it does not relabel its historical provider verdict.

The production reporter now collects authenticated canonical workflow_run runs
separately from PR-event topology. Immutable default-branch workflow/helper
hashes, independent suite/check/job identities, exact attempts and the successful
publication-step interval bind a new status-ID receipt to the original Gate head.
Old, missing or mismatched receipts remain UNKNOWN. Root/template sources and
manifest semantics are updated together; privileges are unchanged.

`mutation-red.log` records disabling only the production fork-collection call:
the named pull_request and pull_request_target acceptance cases fail with
UNKNOWN instead of PASS (2 assertion failures, no errors). The driver restored
source bytes in finally and verified byte identity; `mutation-proof.json` binds
that restoration. `final-tests.log` records 359 focused PASS after restoration.
The first diagnostic mutation run had a test-message KeyError; it was corrected
and is not counted as acceptance proof. These retained logs are the corrected run.

The producer regression asserts the actual status-write response ID and both
run attempts. Negative controls reject forged IDs/heads/attempts, other workflow
paths/events/repos, wrong source hashes, suites/apps/jobs/checks, step failures
or timing, missing original Gate success, newer statuses and duplicate receipts.
Live read37619684464 confirms the existing publisher metadata uses the trusted
default-branch head9a0219f361e4ba4b9072a554362ef378ff47ec4c, not the PR head.

These are controlled regression/mutation tests. No new-format production fork
publication, hosted current-head PASS, reviewer disposition, merge or provider
PASS is claimed. A new producer must land and sync before a real fork receipt
can qualify. The full expected topology and review floor remain mandatory.
