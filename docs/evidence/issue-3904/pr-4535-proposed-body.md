<!-- closer-core/v1 repair-of=stranske/Workflows#4462@4527 -->

Refs #4462

- [ ] Independently revalidate all four retained Python 3.12/3.13 archives with the immutable Git sources available.
- [ ] Deliver the focused validator/test changes from follow-up #4542 through the existing PR writer.
- [ ] Disposition active review threads and satisfy the existing checks, review floor and guarded merge.
- [x] Preserve all existing source, dependency, outcome, coverage and timing refusal checks.

Current follow-up verification uses Python 3.14.10. The requested Anaconda
interpreter is absent, so the exact acceptance commands have not been rerun here.
The validator and regression changes are on `codex/issue-4541`; they have not been
delivered to this PR's unchanged head `f3325610782d7d8d57fbd9659cfae8b1e12fe10e`.
The local validator rejects invalid workflow identities and incomplete declared
phases before Git. Fourteen CLI regressions exercise those refusals and establish
that self-reported receipts cannot replace independent Git verification.

All four retained ZIPs are now present. Fresh independent validation stops at
missing Git sources: the original run cannot resolve
`8142060267fce57561d25735aa2e7c5f457ade14:scripts/measure_verifier_runtime.py`, and
the new run cannot resolve candidate commit
`8c0afc3ef0263cf85949b6167435ceabed5dd2a3`. Retained successful validation JSON
does not substitute for this missing verification. The immutable source pair and
dependency lock remain unchanged. Historical uploads and exclusive overhead stay
UNKNOWN.

PR #4535 has 13 active unresolved review threads. Its current-head expected-check
reporter returns UNKNOWN because native-gh cannot reach GitHub. The pending
delivery, check and review requirements do not authorize a merge.

Current local validation:

```text
python -m pytest tests/scripts/test_validate_hosted_receipts.py tests/scripts/test_measure_verifier_runtime.py tests/scripts/test_gate_runtime_evidence.py -q -m 'not slow'
561 passed in 24.02s

python -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py -q -m 'not slow'
2054 passed in 12.56s
```

All five marker-specific options assertions remain in the unchanged integration
file. These results apply to the follow-up checkout, not the integrated PR head.
The following experiment narrative and command transcript are retained historical
records, not successful reruns on this runner.

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

The historical transcript records passing commands and all five marker-specific options assertions. The real two-arm fixture checks process receipts alongside bounded missing/invalid/reversed-clock controls. Fresh four-archive validation and exact-command verification remain blocked as described above.

The current source correction (43fc63feb) also addresses review comment 4504023552: actual hosted coverage-report intervals are independently measured (about 29s on 3.12 and 24.5s on 3.13). The source-head Gate passed. No runtime source changed after the passing requested tests; the last commit retains receipts/documentation. Missing historical log uploads and exclusive overhead remain UNKNOWN.

Evidence and reproduction: docs/evidence/issue-3904/README.md, closer-r2-acceptance.md and validate_hosted_receipts.py. The original 3.13 receipts remain intact.

<!-- workflow-source:local_request -->
