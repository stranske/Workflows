# Blocked diagnostic partition accounting — 2026-10-11

- [ ] Add bounded prompt recovery/partitioning for obligations that exceed exact-model capacity.

Reviewed `bf56264b` and the preceding capture/reassembly commits. The latest
commit already implements diagnostic execution with `acceptance_sufficient=false`;
it does not establish semantic independence or complete exact-judge acceptance.
No additional task checkbox is justified by that implementation or this change.

The native partition planner previously discarded a rejected range's capacity
receipt and its remaining queue when planning failed. It now retains every
planning attempt, including overflowed parents and unavailable native counts.
On failure, fitted leaves plus pending ranges cover every character of the
loaded context and supplied diff exactly once. The failure records its reason
and attempted range; native-count and range ceilings still block all generation.
The planning-count ceiling is explicitly 127 and also respects the existing
binary-tree bound derived from the 64-request ceiling. Generation behavior,
model selection, output reserves and the NON_PASS floor are unchanged.

The source and consumer verifier copies are byte-identical. The existing
`scripts/langchain/pr_verifier.py` sync-manifest entry covers this change;
no managed path was added, removed or re-scoped. Protected workflows were not
edited. The consumer maintenance guide describes the new report fields.

## Validation

Baseline suite: **36 passed**. Six added regressions exercise range exhaustion,
planning-count exhaustion and a native count failure after an earlier fitted
range, for each configured provider. All six fail behaviorally on the verifier
at `bf56264b330013b01c2279b434517049e133ee71`: partial plans retain `planned`
status, and the independent native-count ceiling is unenforced. The baseline
was installed only for the RED subprocess; final source was restored in
`finally` and checked byte-for-byte before GREEN.

```bash
python -m pytest tests/scripts/test_pr_verifier_partition_recovery.py::test_blocked_plan_accounts_for_every_captured_range -m "not slow" --no-cov -q --tb=short
```

RED: **6 failed**, exit 1. Final-source GREEN: **6 passed**, exit 0. Raw
transcripts are retained locally at `/tmp/verifier-partition-blocked-red.txt`
and `/tmp/verifier-partition-blocked-targeted-green.txt`.

```bash
python -m pytest tests/scripts/test_pr_verifier_partition_recovery.py tests/scripts/test_pr_verifier_recovery.py tests/scripts/test_native_capacity_recovery.py tests/scripts/test_native_capacity_registry.py tests/tools/test_verifier_capture_obligation_manifest.py tests/scripts/test_verifier_capture_integration.py tests/scripts/test_pr_verifier_sync_manifest.py tests/scripts/test_pr_verifier_config_and_report.py tests/scripts/test_pr_verifier_compare.py tests/scripts/test_pr_verifier_structured_output.py tests/scripts/test_pr_verifier_prompt_coverage.py tests/workflows/test_verifier_evidence_profile.py -m "not slow" --no-cov -q
```

**4,624 passed, 19 skipped**. Skips remain the owner-local authenticated capture
replay (one) and provider-inapplicable Anthropic metadata cases (18). The raw
combined transcript is `/tmp/verifier-partition-blocked-green.txt`.

Ruff passed on both verifier copies and the changed test file;
`python scripts/validate_template_sync.py` and `git diff --check` passed.
Black 26.10 formatted the relevant files at line length 100; the full gate passed:

```bash
black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

**701 files would be left unchanged**. The sandbox denies Black's process-pool
scheduler and stalls its thread scheduler. A temporary launcher at
`/tmp/verifier-blocked-black/black` runs the normal Black CLI with only
`black.concurrency.reformat_many` replaced by sequential calls to the unmodified
`black.reformat_one`. Discovery, formatter, exclusions and failure status are
unchanged. Full output: `/tmp/verifier-partition-blocked-black.txt`.

## Remaining boundary and handoff

These simulated native SDK tests establish accounting and fail-closed behavior,
not live provider capacity or reviewer acceptance. Cross-range semantic proof,
missing source evidence and authentic complete native comparison still prevent
checking the recovery/partitioning task. No generated consumer PR was mutated.

GitHub reads confirmed PR #3831 is open with `draft=false`. Updating its body
was automatically rejected: `MCP tool call requires approval, but approval policy
is never`. A proposed reconciled body is retained at
`/tmp/pr3831-partition-accounting-body.md`; remote checkboxes were not changed.

Canonical staging failed because `.git/index.lock` cannot be created on the
read-only mount. The validated changes are preserved in the writable clone
`/tmp/verifier-partition-accounting-3831`, with exports at
`/tmp/verifier-partition-accounting-3831.bundle` and
`/tmp/verifier-partition-accounting-3831.patch`. Canonical source edits remain
available for the authorized automation handoff.
