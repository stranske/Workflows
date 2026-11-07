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

## Coverage-report boundary correction

Run 42421695302 was canceled before accepting measurements. Inspection of the
installed pytest-cov source showed `cov_controller.summary()` runs inside
`pytest_runtestloop`, not `pytest_sessionfinish`. The draft's claim that the final
hook enclosed coverage reporting was incorrect. The external probe now separately
wraps the controller's actual summary call, with identical instrumentation on
both arms. This interval overlaps the controller loop and is never derived by
subtracting a worker or collection clock. Coverage finalization and per-test
report handling remain inside the loop without invented separate intervals.

After direct coverage-report instrumentation, the requested focused command
printed `343 passed in 29.28s`; the exact integration command printed
============================ 2054 passed in 13.68s =============================
Both exited 0. Raw outputs are retained in the adjacent closer-r2 pytest files.
The original 3.12 archive still independently validates with the updated checker.

## Hosted readback and review limits

Python 3.13 from run 42421935858 independently validates, including the GitHub
archive digest, both source manifests, all scoped JUnit outcomes/times, coverage
lines/arcs, uploaded hashes and all five process phase receipts per arm. Both
arms cover 2,144 lines / 759 arcs with no loss. Coverage reporting is directly
measured at about 24.5s per arm, and final reporting at about 3.2s; neither is an
inferred overlapping-clock remainder. This is one pair, with no causal claim.

The first actual source-head Gate (42421940995, head 43fc63feb...) was observed
completed/success. The seven-minute post-push floor elapsed before readback.
Review comment 4504023552 independently identified the earlier coverage boundary
error, which this head corrects and the real hosted 3.13 receipts now validate.
The GitHub connector refused both the PR-description correction and resolution
of thread PRRT_kwDOQprj9M607byc with
`MCP tool call requires approval, but approval policy is never`.
Neither mutation was performed; that review thread remains unresolved and the
remote PR description retains its earlier pending state. No merge is authorized
by these receipts alone.

CLI REST inspection hit the shared core quota at 22:59 UTC (reset 23:17:51 UTC).
Connected GitHub readbacks remained available, so work continued without waiting
for quota reset. The later raw step-clock readback used:
`gh run view 42421935858 --repo stranske/Workflows --json status,conclusion,jobs`.
The downloadable live 3.12 log was not yet published (404); browser inspection
was unavailable (`native pipe closed before response`). No helper or security
setting was changed.

## Terminal acceptance — 2026-11-07

Outcome 1: PASS. Run 42421935858 completed successfully on both requested
runtimes. Independent validation prints `verified: true` for both retained raw
archives. The new 3.12 digest is
`b2f68c8e230dff23140719b173d8ed3b5de271284a933f7433d45eecbead72c7`;
the new 3.13 digest is
`441a35e21b4399db1f8c6b3db76f8d3a68706517e14c088b9be6da103cf750ba`.
All actual process boundaries reconcile to the result receipts, including the
controller coverage-report method. Source identity, raw scoped JUnit outcomes
and times, coverage line/arc differences, uploaded hashes and embedded probe
identity all independently reconcile. Package stability remains the harness's
recorded observation. Missing inherited historical log uploads remain UNKNOWN.
Raw terminal run/step clocks and connector job/artifact readbacks are retained.

Both new runtime pairs have baseline 36,268 and candidate 35,644 passing cases,
2,144 verifier lines and 759 arcs per arm, and no lost lines/arcs. The README
retains measured phase durations. These overlapping clocks never establish an
exclusive remainder. This is one pair per interpreter with uncontrolled host
load/CPU placement and OS page cache; no causal speedup claim is made.

No runtime source changed after the successful 343-test focused command and
2,054-test integration command. The final commit adds receipts/documentation.
PR #4535 remains the single repair PR on the provisioned branch, ready for review.
GitHub metadata mutation limits above remain separate from source acceptance.

All four retained archives (original/new on both runtimes) were revalidated with
the independent command after copying into this branch; all returned exit 0 and
`verified: true`. The final PR-description update was attempted with the complete
terminal receipts and the final raw test output, and was again rejected by the
connector's approval policy. The exact replacement is retained in
`pr-4535-proposed-body.md`. Apply that body to PR #4535 and resolve addressed
thread PRRT_kwDOQprj9M607byc after reading the source/phase evidence. These are
metadata actions still outstanding; no alternate mutation route was attempted.
