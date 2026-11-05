# Issue #3898: fork status publication evidence

Check date: 2026-11-04 America/Chicago (2026-11-05 UTC).

Outcome 1: an ineligible fork `pull_request` with a read-only token attempts
zero status writes, including when eligibility never completes or registry
loading would fail before normal eligibility handling. Same-repository and
trusted fork publication must retain their positive and stale-binding controls.

Acceptance command (only local test command used):

```sh
/opt/anaconda3/bin/python3 -m pytest -q -p no:cacheprovider tests/workflows/test_agents_guard_publication.py tests/workflows/test_agents_guard_fork_status_publication.py
```

Initial checked source: `d77a8e3ad93aaf4339fff0180bafa1264e3ec7c0`.
Stop rule recorded before implementation: at most three repair attempts or
60 minutes, whichever occurs first. Report the first broken step if reached.
Local regression runs must complete within two minutes.

## Initial observations

The native finding at Portable-Alpha-Extension-Model#2332 refers to immutable
head `d323b67a17b3fd0a6eee17c1c1dd35244abf455a`. Its publisher uses
`if: always()` and `github.token`. The present source and template already
require a same-repository head or `pull_request_target`; the fix landed in
Workflows PR #3900, commit `8ec052a1`.

Comment 4272936106 was authored against that supplied head
(`original_commit_id` `d323b67a17b3fd0a6eee17c1c1dd35244abf455a`, original line
672, the `github-token` input under `if: always()`). GitHub anchors the same
comment at the PR head `a053f355e2444b28e2a163fc4ae3afabf34b29be`, line 820.
That later file already has the fork guard and two `createCommitStatus` calls
inside the guarded step. Workflow SHA-256 for that head is
`99c44bc679f57a619563dba2b623da2d368121581138d8e8898e9ee051d81ea4`.
Executing its real publisher on an ineligible fork `pull_request` attempts
zero writes. Replacing only its condition with `always()` attempts one denied
write, including the registry-error corrective path that the supplied head's
publisher did not yet contain. The comment text describes the supplied head,
not a remaining defect at the anchor head or in current source.

The focused publication command, run with `python3` 3.14.9 because
`/opt/anaconda3/bin/python3` is not installed here, exited 0:
**644 passed in 41.08s**. The new review-head paths execute inside the
existing parametrized test, so the count stays 644. Source and template
both contributed. No production workflow change was made.

The extracted condition and script are also bound to SHA-256 literals in
`tests/workflows/test_agents_guard_publication.py`. Those literals were
hashed from the immutable workflow bytes (`condition`, a newline, then
`script`), not copied from a digest field in the fixtures. Canary
publisher `1cd4058efe2e9f3b9c5744ab28c0118f2a6651e5a8253bd4b5dae8cc68b7a55d`;
review-anchor publisher
`3199fbaece174be06db1bdb9d733f015581949d5a6c4ba4becaa6035de7af67e`.
A fixture edit that changes either publisher fails that comparison while
the write-count assertions stay in place. Re-running the acceptance
command on that tree with `python3` 3.14.10 (`/opt/anaconda3/bin/python3`
is not installed) exited 0: **644 passed in 49.25s**.

No production change is justified unless the execution regression demonstrates
a remaining defect. Preserve the existing source/template boundary.

## Live delivery boundary

The historical campaign tracker #1836 is closed (2026-10-16T07:46:19Z).
The referenced canary PR #2332 is closed without merge at current head
`a053f355e2444b28e2a163fc4ae3afabf34b29be`. Neither is delivery proof.

Observed Maint 68 run `41975139516` is queued for source
`d77a8e3ad93aaf4339fff0180bafa1264e3ec7c0`; Maint 71 run `41975569433`
is pending for the same source. Do not start a competing delivery writer.
Earlier Maint 71 run `41975106145` failed at **Refresh stale candidate bases**.

Blocking/drainable pair: downstream acceptance is unobserved / the existing
Maint 68/71 owner must finish its queued exact-plan regeneration and publish
canary, promotion, reconciliation and delivered-head verification receipts.
This source evidence cannot authorize reopening the historical campaign or
declare current fleet completion.

## Execution evidence

The initial unchanged-source run passed: **636 passed in 56.31s**. The added
regression run passed: **644 passed in 55.21s**. Both used the acceptance
command above against the recorded source plus this PR's test changes.

`tests/fixtures/agents_guard_3898_canary_publisher.json` retains the actual
publisher condition, token selection and script fetched from the supplied
immutable canary head. The complete upstream workflow SHA-256 was
`9d8e46532ce4d49f7c88087e4e314ebff7be4985731bd9a358ef069395e561dc`.
Retrieve that exact file with the GitHub contents API at the head recorded in
the fixture; no moving branch or latest canary is substituted.

The new test executes the real inline JavaScript behind its actual condition.
The status stub counts attempts **before** rejecting with HTTP 403; successful
write counts alone would conceal this defect. Source and template both make
zero reads and zero writes for the fork event. Missing eligibility/job failure,
denied registry access and malformed registry evidence remain outside the
publication boundary. Deliberately replacing only the condition with
`always()` makes each current publisher attempt one denied write, including
the registry-error corrective path. The retained original canary publisher also
attempts one denied write and marks the step failed in every case. These are
execution fixtures, not evidence of a live fork-token request.

A separate deliberate restoration of `if: always()` in both actual workflow
files made the **same full acceptance command** exit 1: **416 failed, 228 passed
in 40.33s**. The new named regression failed in all eight cases. Both workflow
files were then restored byte-for-byte. The raw temporary failure log was
`/tmp/issue-3898-boundary-removed.log`; the committed regression retains the
repeatable historical and boundary-removal controls.

There are two reachable direct `createCommitStatus` sites: registry-error
correction and normal verdict publication. Both are inside the same skipped
workflow step. The trusted helper remains separate: its existing execution
tests cover successful fork publication, stale head, mismatched event,
run/attempt drift, missing/malformed evidence, denied writes and replay.
Existing tests also verify helper parity and manifest coverage. No remaining
production defect, missing managed-file declaration or changed publication
contract was demonstrated; no source, template, manifest or defining contract
change is warranted.

## Delivery observation update

Maint 68 run `41975139516` subsequently completed successfully, but its success
does not prove canary qualification or consumer merge. Maint 71 run
`41975569433` was cancelled; a subsequent same-source run `41976239018` is
in progress, with `41976433433` pending and `41976435495` queued.

The earlier failed run's exact error is `canary_refresh_native_scope_mismatch`.
Its retained report identifies `candidate_immutable_identity_mismatch` and
metadata/source-commit mismatches on the three configured canaries. Its canary
evidence artifact has no qualified results. Those observations are bound to
that failed run, not assertions about later heads. The live Portable Alpha
candidate #2454 is open and ready at
`99d10a9838cecfb4327a2735d8f3723e393e413e`, which differs from that report's
head. The Maint 68/71 lane remains the writer and must supply fresh evidence.

Source review/CI, source merge, actual post-merge verification, FULL promotion
and final reconciliation remain **unobserved for this PR**. The historical
PR #3900 is merged and has a successful verifier check, but that check alone
does not establish downstream campaign completion or verifier verdict content.
