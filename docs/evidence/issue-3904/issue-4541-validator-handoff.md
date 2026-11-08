# Receipt validator regression handoff — 2026-11-08

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
