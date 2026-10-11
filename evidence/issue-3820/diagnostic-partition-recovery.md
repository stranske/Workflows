# Bounded diagnostic partition recovery — 2026-10-11

- [ ] Add bounded prompt recovery/partitioning for obligations that exceed exact-model capacity.

This round advances that task with executable, opt-in diagnostic recovery in the
source verifier and identical consumer template. It does not complete semantic
partition acceptance. Every frozen obligation still depends on all captured
inputs; independent range judgments cannot prove the joint obligation. The task
remains unchecked rather than treating diagnostic execution as acceptance.

Use the existing CLI with `VERIFIER_EVIDENCE_PROFILE=expanded`,
`VERIFIER_PARTITION_RECOVERY=diagnostic` and `--json`. Recovery starts only when
the complete request's native preflight reports overflow. Capture gaps, clipped
required material, unknown capacity and unavailable native counters remain blocked.
Default expanded, standard, registry selection and protected workflows are unchanged.

The planner preserves every character of the loaded context and supplied diff,
including Unicode, CRLF and duplicate embedded/supplied code. Each range carries
the entire global dependency contract, offsets, UTF-8 hash and exact native
request receipt. Planning allows at most 8 MiB of loaded UTF-8 input, 64 ranges
and 127 native counts. Every planned request must fit before generation. Each
generation is counted again and must match its planned request SHA-256; there
are at most 64 generation calls per arm and no schema-repair or config-fallback
generation. Existing SDK transport retry configuration is unchanged.

The JSON `partition_recovery` report preserves the original overflow receipt,
all obligations/gaps, complete planned range identities, every concern, summary,
raw response and execution error. FAIL is retained even if later ranges pass.
Malformed responses remain available and block completeness; transport failures
preserve prior findings and the planned ranges that were never reviewed. Even
`diagnostic_complete` has `acceptance_sufficient=false` and cannot grant PASS.

Runtime hashes explicitly bind `loaded-evaluation-inputs`, whose newline view
can differ from the CLI's independently frozen raw-byte snapshot. This report
does not replace, mutate or claim equality with that raw snapshot contract.
Unavailable evidence from the authenticated #3802 capture remains unavailable.
No live provider acceptance, paid generation, fleet deployment or campaign sync
is established by the simulated native SDK regressions.

## Validation

Before implementation, the existing manifest/recovery/native/parity subset
passed: **439 passed, 19 skipped**. The initial new suite executed with
**26 failures**, rather than failing collection.

Deliberate behavioral RED temporarily used the exact tracked verifier source at
`2b94fa6aebd707345a1d6bc7618e8b665a9023a7`, with restoration guaranteed in
`finally` and byte equality checked. This command executed four provider/operation
cases, all failing because zero diagnostic ranges were generated (pytest exit 1):

```bash
python -m pytest tests/scripts/test_pr_verifier_partition_recovery.py::test_partition_recovery_preflights_all_ranges_and_retains_every_finding -m "not slow" --no-cov -q --tb=short
```

The same four cases pass on final source as part of the new suite, which checks
ordered lossless reassembly, retained findings/raw responses, native model/output
preservation, finite bounds, incomplete capture, late planning failures, fresh
pre-generation checks, transport/schema errors and default/standard behavior:

```bash
python -m pytest tests/scripts/test_pr_verifier_partition_recovery.py -m "not slow" --no-cov -q
```

Final new suite: **36 passed**. Final combined suites:

```bash
python -m pytest tests/scripts/test_pr_verifier_partition_recovery.py tests/scripts/test_pr_verifier_recovery.py tests/scripts/test_native_capacity_recovery.py tests/scripts/test_native_capacity_registry.py tests/tools/test_verifier_capture_obligation_manifest.py tests/scripts/test_verifier_capture_integration.py tests/scripts/test_pr_verifier_sync_manifest.py tests/scripts/test_pr_verifier_config_and_report.py tests/scripts/test_pr_verifier_compare.py tests/scripts/test_pr_verifier_structured_output.py tests/scripts/test_pr_verifier_prompt_coverage.py tests/workflows/test_verifier_evidence_profile.py -m "not slow" --no-cov -q
```

**4,618 passed, 19 skipped**. Skips are the existing owner-local authenticated
capture replay (one) and provider-inapplicable Anthropic metadata cases (18).

Ruff passed on both verifier copies and the new test file;
`python scripts/validate_template_sync.py` passed; `git diff --check` passed.
The existing managed verifier entry in `.github/sync-manifest.yml` is retained
with a diagnostic-contract comment; no managed file is added or re-scoped.

Black 26.10 formatted all touched Python at line length 100. The required full
check passed: **700 files would be left unchanged**:

```bash
black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

The sandbox rejects Black's process scheduler and stalls its single-worker async
scheduler. A temporary `/tmp/verifier-black-bin/black` launcher invokes Black's
normal CLI, replacing only `black.concurrency.reformat_many` with sequential
calls to the unmodified `black.reformat_one`. Discovery, mode, formatting,
checks, reporting and exit status are unchanged. No repo formatter configuration
or file exclusions were changed.

## Handoff limits

Canonical `.git` is mounted read-only: staging failed with an index-lock error.
The meaningful source/test change is committed in the writable local clone
`/tmp/verifier-partition-recovery-3831` and exported as
`/tmp/verifier-partition-recovery-3831.bundle`; canonical working-tree edits
remain uncommitted. GitHub access failed when reading PR #3831, so remote
readiness, comments and task state could not be verified or updated. No PR was
created, closed or changed by this run.
