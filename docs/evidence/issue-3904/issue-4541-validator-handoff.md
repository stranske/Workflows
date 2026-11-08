# Receipt validator regression handoff — 2026-11-08

## Instrumentation identity regression continuation

Added ten fixture regression cases requiring recorded harness/workflow hashes
and the declared phase-plugin hash to match immutable Git source. Complete,
independently hashed phase receipts cannot substitute for the recorded probe.
No runtime instrumentation, archives, source selections or dependency locks changed.

Verification with installed Python 3.14.10:

```text
python3 -m pytest tests/scripts/test_validate_hosted_receipts.py tests/scripts/test_measure_verifier_runtime.py tests/scripts/test_gate_runtime_evidence.py -q -m 'not slow'
544 passed in 23.39s

python3 -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py -q -m 'not slow'
2054 passed in 15.04s

BLACK_NUM_WORKERS=1 BLACK_CACHE_DIR=/tmp/receipt-4541-black black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
970 files would be left unchanged.
```

Black formatted the touched test at line length 100; Ruff and `git diff --check`
pass. The serial cache warmup honored the configured `force-exclude`; the older
serial helper omitted it and inspected excluded fixtures. No fixture was edited.
All five marker-specific options assertions remain in the unchanged integration
file. The Anaconda interpreter is absent, so the exact acceptance commands remain
unverified.

The retained original 3.13 ZIP matches live GitHub metadata, then independent
validation stops at the missing immutable harness source
`8142060267fce57561d25735aa2e7c5f457ade14:scripts/measure_verifier_runtime.py`.
The three other ZIPs and candidate Git object remain absent locally. Historical
unuploaded logs and exclusive overhead remain UNKNOWN.

Staging the test for the requested commit failed with `.git/index.lock: Read-only
file system`; no commit or push was possible. Automatic approval review rejected
the prepared #4535 body update, reopening the two overstated #4542 task checkboxes,
the blocker comment and the `needs-human` label: `MCP tool call requires approval,
but approval policy is never`. The exact-head expected-check reporter returns
UNKNOWN because native-gh cannot reach GitHub. Partial Gate/guard statuses do not
prove complete expected/required checks; all 13 active review threads remain
unresolved. No remote disposition, acceptance checkbox or merge was completed.

## Phase declaration and legacy fallback boundary

Reviewed the recent keepalive commits and live PR state before editing. The
four-archive revalidation and PR #4535 delivery tasks are still checked despite
missing verification. Reopening those checkboxes was rejected by automatic
approval review: `MCP tool call requires approval, but approval policy is never`.

The validator now rejects phase summaries or raw phase-clock receipts without
`phase_plugin_sha256` before Git. Previously, removing that declaration could
validate an instrumented archive with either arm's summary missing, or classify
raw phase receipts without summaries as legacy UNKNOWN. Nine regression cases
reproduced the missing refusal before the guard. Genuine legacy controls still
pass and retain UNKNOWN for phases, historical uploads and exclusive overhead.

Using installed Python 3.14.10, the three focused suites pass with **534 passed
in 22.03s**; the unchanged integration suite passes with **2054 passed in
13.39s** and all five marker-specific options assertions retained. Both runs
used `-m 'not slow'`. Ruff and `git diff --check` pass. The required Anaconda
interpreter remains absent, so its exact acceptance commands are unverified.

Black formatted both touched Python files at line length 100. After a serial
check populated the writable cache (the threaded CLI stalled), the required
repository-wide command passed without changing formatting rules or exclusions:

```text
BLACK_NUM_WORKERS=1 BLACK_CACHE_DIR=/tmp/receipt-4541-black black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
970 files would be left unchanged.
```

The original 3.13 ZIP matches live GitHub artifact metadata but fails independent
validation at the missing immutable harness source. The other three ZIPs and
the candidate Git object remain absent locally. Four-archive validation remains
unverified; the original source pair and dependency lock are unchanged.

Staging failed with `.git/index.lock: Read-only file system`; no commit or push
was possible. Publishing #4535's retained proposed body, the blocker comment
and the `needs-human` label was rejected by the same approval policy. #4535
still has 13 active unresolved review threads at
`f3325610782d7d8d57fbd9659cfae8b1e12fe10e`. Its exact-head expected-check reporter
returns UNKNOWN because native-gh cannot reach GitHub. No acceptance checkbox,
remote disposition or merge was completed.

Final readback confirms both #4535 and #4542 remain open with `draft=false` at
their unchanged heads.

## Immutable source and dependency-lock regression continuation

Reviewed the seven recent keepalive commits before continuing. The source guards
and their regression tests are implemented, but the checked tasks for four-archive
revalidation and PR #4535 delivery overstate the evidence. Attempting to reopen
those two task checkboxes in PR #4542 was rejected with
`MCP tool call requires approval, but approval policy is never`.

Added 16 regression cases across legacy and phase-enabled archives. They reject
substituted arm commits, trees and source hashes, including forged source hashes
whose reported before/after integrity summaries agree with the substitution.
They also reject replacing the candidate dependency lock before Git. These
controls preserve the independent immutable-source check; they do not establish
that any unavailable hosted archive has passed validation.

```text
python3 -m pytest tests/scripts/test_validate_hosted_receipts.py tests/scripts/test_measure_verifier_runtime.py tests/scripts/test_gate_runtime_evidence.py -q -m 'not slow'
525 passed in 19.10s

python3 -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py -q -m 'not slow'
2054 passed in 11.57s

BLACK_NUM_WORKERS=1 BLACK_CACHE_DIR=/tmp/receipt-4541-black black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
970 files would be left unchanged.
```

Black formatted the touched Python file at line length 100. A serial check
using the configured source selection populated the writable cache before the
required CLI check passed. Ruff and `git diff --check` also pass. Staging the
test and this handoff failed with `.git/index.lock: Read-only file system`, so
these changes remain uncommitted and no push was possible.

The integration file is unchanged and retains all five marker-specific options
assertions. The requested Anaconda interpreter remains absent. The original
3.13 ZIP matches the live GitHub artifact digest but still fails the independent
harness source lookup at `8142060267fce57561d25735aa2e7c5f457ade14`.
Three local ZIPs and the immutable candidate object remain unavailable. The
connector returned an artifact download reference, but its host cannot resolve
from this shell. Historical uploads and exclusive overhead remain UNKNOWN.

PR #4535 remains open and ready at the unchanged
`f3325610782d7d8d57fbd9659cfae8b1e12fe10e`, with 13 active unresolved review
threads. The exact-head expected-check reporter again returns UNKNOWN because
native-gh cannot reach GitHub. Successful connector Gate/guard statuses do not
prove complete expected/required checks. Publishing the retained proposed body,
posting the concrete blocker comment, and adding `needs-human` to PR #4542 were
each rejected by the same approval policy. No remote branch, thread disposition,
acceptance checkbox or merge state changed.

## Hosted runtime and artifact-name format correction

The live artifact metadata for runs 42401537967 and 42421935858 names all four
archives `verifier-runtime-<major.minor>-<run_id>`, matching the pinned workflow.
The retained original 3.13 archive records
`3.13.18 (main, Oct 26 2026, 14:19:33) [GCC 15.2.0]`, matching the harness's
`sys.version` output. The validator previously rejected both formats: it
required a bare version and an artifact name without the run suffix. Fixtures
had reproduced those incorrect assumptions.

The validator now accepts a full version with optional single-line build
details and requires the exact runtime/run artifact name. Valid legacy and
phase-enabled controls use the actual name format, with eight additional build
detail cases; sixteen new controls reject missing, wrong, padded and extra run
suffixes before Git. The build-detail controls reproduced eight failures before
the runtime correction. Immutable source selections, dependency lock, phase
instrumentation and retained archives are unchanged.

Verification with installed Python 3.14.10:

```text
python3 -m pytest tests/scripts/test_validate_hosted_receipts.py tests/scripts/test_measure_verifier_runtime.py tests/scripts/test_gate_runtime_evidence.py -q -m 'not slow'
509 passed in 17.98s

python3 -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py -q -m 'not slow'
2054 passed in 11.64s

BLACK_NUM_WORKERS=1 BLACK_CACHE_DIR=/tmp/receipt-4541-black black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
970 files would be left unchanged.
```

Both touched Python files were formatted individually with Black at line length
100; Ruff and `git diff --check` pass. A serial Black check honoring the current
configuration populated the cache before the required CLI check passed. All
five marker-specific options assertions remain in the unchanged integration
file. The requested Anaconda interpreter remains absent.

The retained original 3.13 ZIP now passes its GitHub digest and corrected
runtime/name checks, then stops at the unavailable immutable harness source
`8142060267fce57561d25735aa2e7c5f457ade14:scripts/measure_verifier_runtime.py`.
The selected candidate object and three other local ZIPs are still absent.
These fixture results do not establish four-archive validation. Historical
uploads and exclusive overhead remain explicitly UNKNOWN.

Staging the source and test failed with `.git/index.lock: Read-only file
system`; no commit or push was possible. PRs #4535 and #4542 were checked open
and ready. PR #4535 remains at `f3325610782d7d8d57fbd9659cfae8b1e12fe10e`
with 13 active unresolved review threads. The exact-head expected-check reporter
returns UNKNOWN because native-gh cannot reach GitHub; successful connector
Gate/guard statuses do not prove complete expected/required checks. Publishing
the concrete blocker comment on #4535 and adding `needs-human` to #4542 were
rejected with `MCP tool call requires approval, but approval policy is never`.
No remote branch, review thread, acceptance checkbox or merge state was changed.

## Archive and metadata identity regression continuation

Added 10 regression cases across legacy and phase-enabled archives. They reject
changed outer ZIP bytes, duplicate manifest members even with a matching outer
digest, ambiguous matching artifact metadata, divergent result/manifest workflow
identities, and a workflow identity differing from the retained metadata. Every
case verifies rejection before Git. These are fixture controls, not revalidation
of the four hosted archives; the validator and runtime instrumentation are unchanged.

Verification with installed Python 3.14.10:

```text
python -m pytest tests/scripts/test_validate_hosted_receipts.py tests/scripts/test_measure_verifier_runtime.py tests/scripts/test_gate_runtime_evidence.py -q -m 'not slow'
485 passed in 22.91s

python -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py -q -m 'not slow'
2054 passed in 11.75s

BLACK_NUM_WORKERS=1 BLACK_CACHE_DIR=/tmp/receipt-4541-black black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
970 files would be left unchanged.
```

The touched test was formatted with Black at line length 100. Ruff and
`git diff --check` pass, and all five marker-specific options assertions remain
unchanged. The repository-wide CLI formatting check passed after a serial cache
warmup honoring the configured exclusions; the first uncached CLI invocation
stalled and was interrupted.

Staging the test failed with `.git/index.lock: Read-only file system`, so no
commit or push was possible. The requested Anaconda interpreter, three archives
and immutable harness/candidate Git objects remain absent. No acceptance checkbox
was changed. Historical uploads and exclusive overhead remain UNKNOWN.

PR #4535 remains open and ready at the previously recorded head, with 13 active
unresolved review threads. The expected-check reporter returns UNKNOWN because
the shell cannot reach GitHub; successful connector Gate/guard statuses alone do
not establish all required checks. The connector rejected the retained proposed
body update, blocker comment and source issue #4541's `needs-human` label with
`MCP tool call requires approval, but approval policy is never`. No guarded merge
or source write to PR #4535 occurred.

## Historical upload UNKNOWN boundary continuation

Added 16 regression cases across both arms and legacy/phase-enabled archives.
An uploaded historical log must match its retained member hash and must leave
the unavailable-entry list; corrupt uploaded historical or console logs are
rejected even when the outer archive digest matches. Missing neighboring log
paths cannot use the four inherited exceptions. The valid archive controls
now assert the exact four unavailable historical paths, while exclusive
overhead remains UNKNOWN.

Verification with installed Python 3.14.10:

```text
python -m pytest tests/scripts/test_validate_hosted_receipts.py tests/scripts/test_measure_verifier_runtime.py tests/scripts/test_gate_runtime_evidence.py -q -m 'not slow'
475 passed in 20.36s

python -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py -q -m 'not slow'
2054 passed in 11.48s
```

All five marker-specific options assertions remain in the unchanged integration
file. Black formatted the touched test, Ruff and `git diff --check` pass.
After a serial cache warmup honoring the current configured exclusions, the
required repository-wide CLI check passed with 970 files unchanged, exit 0:

```text
BLACK_NUM_WORKERS=1 BLACK_CACHE_DIR=/tmp/receipt-4541-black black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

The initial uncached CLI invocation stalled and was interrupted; the serial
check and cached CLI check both passed without changing any exclusions.

Staging the test failed with `.git/index.lock: Read-only file system`; no commit
or push was possible. The requested Anaconda interpreter, three archives and
the immutable harness/candidate Git objects remain unavailable here. These are
fixture controls, not four-archive revalidation. The connector rejected the
blocker comment and `needs-human` label with `MCP tool call requires approval,
but approval policy is never`. PRs #4535 and #4542 were rechecked open and ready.
PR #4535's head is unchanged, its review threads remain unresolved, and no
acceptance checkbox or guarded merge was performed.

## Declared phase metadata preflight continuation

Declared phase instrumentation now requires a mapping with `available: true`,
no gaps, and all five controller/worker process entries in each arm before any
Git lookup. Malformed, unavailable or incomplete summaries raise an explicit
arm-specific `ValueError`; raw clock reconciliation remains mandatory afterward.
The 22 added regression cases independently damage each arm's phase metadata,
verify rejection before Git, and retain the valid legacy/phase-enabled controls.
The initial controls reproduced 22 failures before the implementation.

Verification with installed Python 3.14.10:

```text
python -m pytest tests/scripts/test_validate_hosted_receipts.py tests/scripts/test_measure_verifier_runtime.py tests/scripts/test_gate_runtime_evidence.py -q -m 'not slow'
459 passed in 20.39s

python -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py -q -m 'not slow'
2054 passed in 13.76s

python -m pytest tests/scripts/test_validate_hosted_receipts.py -q -m 'not slow'
130 passed in 1.05s
```

The last validator run follows refinement of the new fixtures to corrupt only
one field at a time. All five marker-specific options assertions remain
unchanged. The touched Python files pass Black at line length 100, Ruff and
`git diff --check`. The serial check of the required repository-wide Black
source set reports one unrelated existing formatting failure in
`config/verify_paired/representative-v1/workflows-4265-verified/evidence/current-review-runner.py`
and 973 unchanged files; it was left outside this repair. The exact Black CLI
also timed out after 50 seconds with a writable cache; the repository-wide
formatting gate has not passed.

Staging again failed with `.git/index.lock: Read-only file system`, so these
changes are uncommitted. The requested Anaconda interpreter is still absent.
Only the original 3.13 archive is available locally; its harness Git source and
the selected candidate Git object cannot be resolved. Four-archive validation
is not established. The current-head check reporter returns UNKNOWN because
`api.github.com` is unreachable from the shell. The connector's successful
Gate/guard statuses alone do not establish complete required checks.

PR #4535 remains open and ready at
`f3325610782d7d8d57fbd9659cfae8b1e12fe10e`; this run has not superseded its
writer or changed its branch. PR #4542 is also open and ready. Attempts to
publish #4535's retained proposed body, add its blocker comment, and label
source issue #4541 `needs-human` were each rejected with
`MCP tool call requires approval, but approval policy is never`.
No remote disposition, merge, or acceptance checkbox update was made.

## Earlier regression handoff

The local implementation rejects non-string workflow identities and anything
except a full lowercase 40- or 64-character hexadecimal commit ID before calling
Git. A declared `phase_plugin_sha256` now requires phase measurements in each
arm. Existing raw boundary, availability, completeness, source identity, uploaded
hash, outcome and coverage checks are retained. Archives without phase
instrumentation retain the original UNKNOWN phase result; unavailable historical
uploads and exclusive overhead remain UNKNOWN.

This checkout is `codex/issue-4541`, based on `418aa37f`, rather than PR #4535's
`closer-r2/issue-4462`. The validator was absent here. Its starting contents were
read from PR #4535's exact head
`f3325610782d7d8d57fbd9659cfae8b1e12fe10e` before applying the two guards.
No remote branch was changed, and no claim is made that its current writer has
relinquished ownership. Apply the focused validator delta and the new test file
to that PR through its existing writer before validating the integrated head.
Do not replace that branch's runtime instrumentation or archives with this
checkout's older copies.

## Local verification

The new archive fixtures cover valid legacy and phase-enabled receipts with
both commit-ID lengths; invalid identity types, lengths, case and delimiters;
either or both missing arms; unavailable measurements, explicit gaps, missing
workers and missing controller coverage-report intervals. Before the fix, the
tests produced 21 failures and 12 passes, reproducing both defects. Afterward:

```text
python -m pytest tests/scripts/test_validate_hosted_receipts.py tests/scripts/test_measure_verifier_runtime.py tests/scripts/test_gate_runtime_evidence.py -q -m 'not slow'
362 passed in 19.21s

python -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py -m 'not slow'
2054 passed in 12.50s

ruff check docs/evidence/issue-3904/validate_hosted_receipts.py tests/scripts/test_validate_hosted_receipts.py
All checks passed!

BLACK_NUM_WORKERS=1 BLACK_CACHE_DIR=/tmp/receipt-black-cache black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
970 files would be left unchanged.
```

These results use installed Python 3.14.10; the requested
`/opt/anaconda3/bin/python3` is absent. All five marker-specific options assertions
remain in the unchanged integration test. The focused results describe this
checkout plus the imported validator, not PR #4535's full instrumented head.
Black formatted the two relevant files individually. A serial Black check
populated its writable cache before the exact repository-wide CLI check, because
the sandbox denied the normal multiprocessing startup and the initial threaded
attempt did not finish. No formatting exclusions or security settings changed.

## Delivery and evidence blockers

Staging the two Python files failed with:

```text
fatal: Unable to create '/home/runner/work/Workflows/Workflows/.git/index.lock': Read-only file system
```

The repository's `.git` is explicitly read-only in this run. Fetch also failed
writing `.git/FETCH_HEAD`. No commit or push was made.

Only the original Python 3.13 archive is present in this checkout. Running the
updated validator against it and the retained artifact metadata read from the
same PR head failed at the independent Git source check:

```text
fatal: path 'scripts/measure_verifier_runtime.py' exists on disk, but not in '8142060267fce57561d25735aa2e7c5f457ade14'
```

The selected candidate commit
`8c0afc3ef0263cf85949b6167435ceabed5dd2a3` is also unavailable locally. The
connector's retained-ZIP file read returned empty content; its blob read failed
decoding binary bytes as UTF-8. Downloading a live workflow artifact returned a
remote file reference, without making the ZIP available to the local validator.
None of these observations establishes four-archive revalidation. Restore the
existing retained archives, artifact metadata and immutable Git objects in the
PR writer's checkout, then run the independent validator on all four archives.
Keep the original source pair and dependency lock unchanged.

PR #4535 was observed open with `draft=false` at the recorded head. Its proposed
body update, review-thread dispositions, final-head CI/review floor and guarded
merge remain outstanding. In particular, local regression fixes do not resolve
remote findings before the source is delivered. No task or acceptance checkbox
was marked complete in the remote PR.

Publishing a blocker comment and adding `needs-human` to source issue #4541 were
both rejected by the connector with `MCP tool call requires approval, but approval
policy is never`. Neither remote mutation occurred.
