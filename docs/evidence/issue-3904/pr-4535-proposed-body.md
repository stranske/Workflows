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
/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_measure_verifier_runtime.py tests/scripts/test_gate_runtime_evidence.py -q
........................................................................ [ 20%]
........................................................................ [ 41%]
........................................................................ [ 62%]
........................................................................ [ 83%]
.......................................................                  [100%]
343 passed in 29.28s

/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py
============================= test session starts ==============================
platform darwin -- Python 3.12.2, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/teacher/.codex/orchestrator/worktrees/stranske__Workflows__4462__closer-repair-2
configfile: pyproject.toml
plugins: hypothesis-6.161.5, cov-7.1.0, xdist-3.8.0, rerunfailures-16.3, anyio-4.14.2, datadir-1.8.0, typeguard-4.5.1, asyncio-1.3.0, langsmith-0.10.10, pytest_httpserver-1.1.3, regressions-2.11.0, Faker-40.39.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 2054 items

tests/scripts/test_pr_verifier_body_overall_integration.py ............. [  0%]
........................................................................ [  4%]
........................................................................ [  7%]
........................................................................ [ 11%]
........................................................................ [ 14%]
........................................................................ [ 18%]
........................................................................ [ 21%]
........................................................................ [ 25%]
........................................................................ [ 28%]
........................................................................ [ 32%]
........................................................................ [ 35%]
........................................................................ [ 39%]
........................................................................ [ 42%]
........................................................................ [ 46%]
........................................................................ [ 49%]
........................................................................ [ 53%]
........................................................................ [ 56%]
........................................................................ [ 60%]
........................................................................ [ 63%]
........................................................................ [ 67%]
........................................................................ [ 70%]
........................................................................ [ 74%]
........................................................................ [ 77%]
........................................................................ [ 81%]
........................................................................ [ 84%]
........................................................................ [ 88%]
........................................................................ [ 91%]
........................................................................ [ 95%]
........................................................................ [ 98%]
.........................                                                [100%]

============================ 2054 passed in 13.68s =============================
```

The first focused run printed 1 failed, 178 passed in 24.93s: its sole failure was the inherited workflow-command expectation after removal of the unused environment setup; corrected before the passing requested run. The real two-arm fixture validates all five process receipts per arm in under two minutes, alongside bounded missing/invalid/reversed-clock controls.

The current source correction (43fc63feb) also addresses review comment 4504023552: actual hosted coverage-report intervals are independently measured (about 29s on 3.12 and 24.5s on 3.13). The source-head Gate passed. No runtime source changed after the passing requested tests; the last commit retains receipts/documentation. Missing historical log uploads and exclusive overhead remain UNKNOWN.

Evidence and reproduction: docs/evidence/issue-3904/README.md, closer-r2-acceptance.md and validate_hosted_receipts.py. The original 3.13 receipts remain intact.

<!-- workflow-source:local_request -->
