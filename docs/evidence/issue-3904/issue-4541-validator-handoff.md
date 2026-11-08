# Receipt validator regression handoff — 2026-11-08

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
