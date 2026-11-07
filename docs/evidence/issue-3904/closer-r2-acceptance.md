# Remaining #4462 acceptance — 2026-11-07

Outcome 1: UNKNOWN until independent validation prints `verified: true` for
the original Python 3.12 archive and the new Python 3.12/3.13 phase archives.
Command: `/opt/anaconda3/bin/python3 docs/evidence/issue-3904/validate_hosted_receipts.py ARCHIVE ARTIFACT_METADATA`.
Check date: 2026-11-07. The hosted execution command is
`gh workflow run maint-88-verifier-runtime-comparison.yml --repo stranske/Workflows --ref closer-r2/issue-4462`.

Stop rule: two failed attempts per external retrieval/hosted launch, or 75 minutes
total. Stop at the first broken step. Missing observations stay UNKNOWN.
Blocking/drainable pair: incomplete hosted phase receipts block completion;
original archive validation, bounded instrumentation and focused regression
checks remain drainable. No lock, dependency pin or production gate changes.

The prior local `closer-r1/issue-4462` commit was merged before editing.
Its external-plugin approach and upload intent are retained. Placeholder receipts,
the incomplete resource plugin and its overlap-subtraction reporting estimate
are replaced. Nothing from merged PR #4527 is reverted.

## Local acceptance before hosted launch

Outcome 1: PASS for original archive validation. The retained independent checker
verified the original 3.12 archive against its GitHub digest, raw scoped JUnit,
coverage lines/arcs, uploaded hashes, source trees/input hashes and workflow/harness
identity. It also revalidated the original 3.13 archive successfully. Package
stability is the harness's recorded observation, not a separate package probe.

The inherited plugin's reporting subtraction was replaced by direct hook clocks.
The first focused run reported `1 failed, 178 passed in 24.93s`: the only failure
was the inherited test's obsolete workflow command assertion. After correcting
that assertion, the exact requested command passed:

```text
/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_measure_verifier_runtime.py tests/scripts/test_gate_runtime_evidence.py -q
342 passed in 24.98s
```

The real two-arm fixture produces all five per-process clock receipts for each
arm in under two minutes; missing/invalid/reversed clock controls preserve UNKNOWN
without inventing a reporting remainder. Existing refusal controls all pass.
The initial exact integration command reported `2054 passed in 12.65s`.

```text
/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py
============================ 2054 passed in 12.11s =============================
```
