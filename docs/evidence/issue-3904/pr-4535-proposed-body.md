<!-- closer-core/v1 repair-of=stranske/Workflows#4462@4527 -->

Refs #4462

The retained phase instrumentation and strict receipt validator are integrated
on PR #4542 with #4535 head f3325610782d7d8d57fbd9659cfae8b1e12fe10e.
Neither PR is claimed merged. The #4535 branch remains under its existing writer.

- [x] Independently validate all four retained Python 3.12/3.13 archives against authentic unmodified API metadata and immutable Git source.
- [x] Run both exact acceptance commands on the integrated source with all five marker assertions retained.
- [ ] Complete review dispositions, exact-head checks, review floor and guarded delivery of both PRs.

On 2026-11-08 each archive validator exited 0 with `verified: true` and the
matching authentic artifact ID. ZIP bytes are unchanged. Original run
42401537967 uses harness 8142060267fce57561d25735aa2e7c5f457ade14; phase run
42421935858 uses 43fc63febb0522b610a78f9dcac3e3c610937727. Both verify the
unchanged fixed source pair, candidate lock, uploaded hashes, JUnit outcomes,
2,144 verifier lines and 759 arcs in each arm with zero loss.

The probe measures pytest_sessionfinish for final JUnit/terminal reporting and
pytest-cov summary separately inside pytest_runtestloop. Coverage finalization
and per-test report handling remain unseparated inside execution. Concurrent
process intervals overlap and are never subtracted to infer exclusive overhead.
Historical unuploaded entries, original-run phases, startup/teardown outside
hooks and exclusive overhead remain UNKNOWN. One pair per runtime does not
establish causal speedup. Canceled trial 42421695302 is not accepted evidence.

Exact integrated validation (no marker exclusions):

```text
/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_validate_hosted_receipts.py tests/scripts/test_measure_verifier_runtime.py tests/scripts/test_gate_runtime_evidence.py -q
629 passed in 30.03s

/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py
2054 passed in 13.37s
```

All five marker-specific options assertions remain in the unchanged integration
file. See issue-4541-validator-handoff.md, issue-4541-integrated-*.txt and each
hosted directory's validation-verifier-runtime-*.json for fresh evidence.
All earlier acceptance transcripts remain historical records.

<!-- workflow-source:local_request -->
