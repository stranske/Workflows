<!-- closer-core/v1 repair-of=stranske/Workflows#4462@4527 -->

Refs #4462

- [x] Validate and retain the original successful Python 3.12 artifact alongside the existing Python 3.13 receipts.
- [x] Measure controlled per-arm hosted phases for both requested runtimes without fabricating overlapping-clock remainders.
- [x] Preserve all existing source, dependency, outcome, coverage and timing refusal checks.

The original run 42401537967 succeeded on both runtimes. This retains its actual Python 3.12 archive and independently reconciles raw scoped JUnit totals/outcomes/times, verifier lines/arcs, uploaded hashes, immutable source trees/input hashes, and harness/workflow identity. The archive digest matches GitHub; both arms cover 2,144 lines and 759 arcs, with zero loss. The same checker revalidated the existing 3.13 archive. Four inherited, unuploaded historical log entries remain UNKNOWN.

The identical external probe now directly records each controller/worker's session, collection, execution-loop and final reporting hook boundaries. Final reporting directly measures pytest_sessionfinish (JUnit/terminal). A separate direct probe measures pytest-cov's controller summary call inside the execution loop; coverage finalization and per-test report handling remain unseparated inside execution. Controller and worker intervals overlap and are never subtracted to fabricate exclusive overhead. Startup/teardown outside hooks and unavailable clocks remain UNKNOWN. Phase availability is separate from all preserved refusal checks. Only the upload paths change in the existing manual workflow. No dependency pins or immutable source selections change.

New manual comparison https://github.com/stranske/Workflows/actions/runs/42421935858 succeeded on Python 3.12.16 and 3.13.18, using harness/workflow commit 43fc63febb0522b610a78f9dcac3e3c610937727. Both retained archives independently validate all process clocks, JUnit outcomes/times, coverage, uploaded hashes and immutable source identity. Baseline has 36,268 passing cases; candidate has 35,644, on both runtimes. Both cover 2,144 verifier lines and 759 arcs with zero loss. The earlier trial 42421695302 was canceled after discovering the coverage report boundary gap; its measurements were not accepted. No causal speedup claim is made from one pair per runtime; host load/CPU placement and OS page cache remain uncontrolled.

Prior local work: merged closer-r1/issue-4462 (47135272d) before editing. Kept its external-plugin approach, per-arm receipt intent, and upload intent. Discarded its placeholder 3.12 files, incomplete resource plugin, reporting estimate formed by subtracting overlapping clocks, and assertions that treated unknown receipts as completion. Nothing delivered by merged #4527 was redone or reverted.

Validation (only requested/focused tests; no local full suite or release/verify pipeline):

```text
/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_validate_hosted_receipts.py tests/scripts/test_measure_verifier_runtime.py tests/scripts/test_gate_runtime_evidence.py -q
........................................................................ [ 14%]
........................................................................ [ 28%]
........................................................................ [ 42%]
........................................................................ [ 56%]
........................................................................ [ 70%]
........................................................................ [ 84%]
...................................................................... [ 93%]
.........................................                                        [100%]
537 passed in 28.11s

/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py -q
........................................................................ [  9%]
........................................................................ [ 18%]
........................................................................ [ 27%]
........................................................................ [ 36%]
........................................................................ [ 45%]
........................................................................ [ 54%]
........................................................................ [ 63%]
........................................................................ [ 72%]
........................................................................ [ 81%]
........................................................................ [ 90%]
...................................................................... [100%]
2054 passed in 12.01s
```

Both exact acceptance test commands pass. All five marker-specific options assertions retained. The real two-arm fixture validates all process receipts per arm, alongside bounded missing/invalid/reversed-clock controls. Four-archive validation independently succeeded for all retained Python 3.12/3.13 archives against retained metadata and immutable Git sources.

The current source correction (43fc63feb) also addresses review comment 4504023552: actual hosted coverage-report intervals are independently measured (about 29s on 3.12 and 24.5s on 3.13). The source-head Gate passed. No runtime source changed after the passing requested tests; the last commit retains receipts/documentation. Missing historical log uploads and exclusive overhead remain UNKNOWN.

Evidence and reproduction: docs/evidence/issue-3904/README.md, closer-r2-acceptance.md and validate_hosted_receipts.py. The original 3.13 receipts remain intact.

<!-- workflow-source:local_request -->
