# Capture obligation snapshot and native preflight integration

Verified implementation status for PR #3831:

- [x] Wire manifest emission into verifier input snapshot and expanded native preflight path.
- [x] Native preflight consumes the manifest and fails closed on truncation/overflow gaps (no silent clipping).
- [ ] Add bounded prompt recovery/partitioning for obligations that exceed exact-model capacity.

The Python evaluate/compare CLI records the v1 capture obligation inventory before
client resolution. Existing snapshot metadata is preserved; the raw context hash
must match before adding `capture_obligations`. Duplicate JSON keys, conflicting
recorded obligations, stale identity and changed loaded context abort recording.
A standalone manifest is emitted beside the context. Existing comparison uploads
already retain the embedded manifest through `verifier-input-manifest.json`;
the standalone file is local and is not newly added to workflow upload paths.

Expanded native preflight derives the same manifest from the builder-owned pre-CI
inventory and records every obligation, gap and source reason in capacity receipts.
Capture gaps, incomplete prompt coverage and a prompt differing from the full
prepared request block before counting/generation. Exact-model overflow still
blocks generation, retaining the manifest and native count/output reserve.
Standard invocation behavior and registry routing remain unchanged. The new
helper is declared in the sync manifest and copied exactly into the consumer
template alongside the verifier.

## Validation

Baseline before changes:

```text
python -m pytest tests/tools/test_verifier_capture_obligation_manifest.py tests/scripts/test_pr_verifier_recovery.py tests/scripts/test_native_capacity_recovery.py tests/scripts/test_pr_verifier_sync_manifest.py -m "not slow" --no-cov -q
415 passed, 19 skipped
```

Final focused suites:

```text
python -m pytest tests/tools/test_verifier_capture_obligation_manifest.py tests/scripts/test_verifier_capture_integration.py tests/scripts/test_pr_verifier_recovery.py tests/scripts/test_native_capacity_recovery.py tests/scripts/test_native_capacity_registry.py tests/scripts/test_pr_verifier_sync_manifest.py tests/scripts/test_pr_verifier_config_and_report.py tests/scripts/test_pr_verifier_compare.py tests/scripts/test_pr_verifier_structured_output.py tests/scripts/test_pr_verifier_prompt_coverage.py tests/workflows/test_verifier_evidence_profile.py -m "not slow" --no-cov -q
4547 passed, 19 skipped
```

The skips are the existing owner-local authenticated-capture replay (one) and
Anthropic Models API cases in inapplicable provider parameters (18). Native SDK
regressions simulate transport responses; no paid generation was performed.

After formatting, the manifest/integration/recovery/native-registry/parity subset
passed again: **616 passed, 19 skipped**. Ruff passed on all touched Python files;
`python scripts/validate_template_sync.py` reported all template files in sync.

Black 26.10 formatted the touched files at line length 100. The required full
CLI check (`black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .`)
passed: **698 files would be left unchanged**. The sandbox blocks Black's usual
process scheduler and stalls its async single-worker scheduler. A temporary
`/tmp` launcher replaced only `reformat_many` scheduling with sequential calls
to Black's unmodified `reformat_one`; CLI discovery, formatter, mode, check/report
and exit-status behavior were retained. No repository formatter configuration
was changed.

Deliberate RED/GREEN used archived HEAD `f28d16f9`, with the final integration test
and its capture-fixture utility overlaid. The selected tests collected and ran:
**22 failed** on that prior implementation (pytest exit 1), then **22 passed** on
final source (exit 0). This demonstrates behavioral failures, not collection RED.
Both runs used:

```text
python -m pytest tests/scripts/test_verifier_capture_integration.py -m "not slow" --no-cov -q --tb=short
```

## Limits and follow-up

Lossless partitioning remains incomplete; oversized obligations stay NON_PASS.
Unavailable evidence from the authenticated #3802 capture remains unavailable;
these offline checks establish no live provider acceptance or fleet deployment.
No workflow file or generated consumer PR was changed, and no campaign sync was
triggered.

The JS context suite was attempted with both the normal Node test runner and
direct execution. Direct execution ran 141 tests: 135 passed and six failed because
the sandbox denied `spawnSync git` (`EPERM`) for real-Git diff/rename fixtures.
The context builder and its JS tests are unchanged in this round.

GitHub access is unavailable: `gh pr view 3831 --repo stranske/Workflows` failed
with `error connecting to api.github.com`. PR checkboxes/comments and remote
readiness could not be updated or checked; the verified status above is local.

The canonical `.git` directory is mounted read-only; `git add` and `git commit`
cannot write its index lock. The reviewed source patch is committed in a writable
`/tmp` clone and exported as `/tmp/verifier-capture-obligation-integration.bundle`
for import. The canonical working-tree edits remain present and uncommitted.
