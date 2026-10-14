# Cancelled reporter proof for issue 3872

The authored root and consumer resolver scripts execute in Node with their own real
`classifyReporterRun` helpers. A successful null immutable-index lookup followed by
an unclassified cancelled origin now emits a notice and summary with `skip=true`
and no PR lock. Failed/timed-out unclassified origins retain attributed visible
failure. Indexed cancellations still resolve to reconciliation; unavailable or
invalid index evidence stays fail-closed. Trigger and mutating-job conditions are
unchanged.

## Commands and observed results

```bash
python3 -m pytest tests/workflows/test_keepalive_reporter_unresolved.py -q -o addopts=
python3 -m pytest tests/workflows/test_keepalive_authority_delivery.py tests/scripts/test_check_template_drift.py -q -o addopts=
python3 scripts/check_template_drift.py
python3 -m black --check tests/workflows/test_keepalive_reporter_unresolved.py
python3 -m ruff check tests/workflows/test_keepalive_reporter_unresolved.py
```

Final resolver suite: 75 PASS. Adjacent authority-delivery/drift tests: 28 PASS.
Template drift: zero unallowlisted differences. Focused Black and Ruff pass.
The initial regression baseline, before the cancellation guards and additional
invalid-index cancellation controls, was 2 assertion failures and 63 passes;
`baseline-red.log` and its JUnit preserve that historical result.

## Production break and byte-identical restoration

For each surface separately, remove only this clause from the resolver:

```javascript
 &&
                  context.payload.workflow_run.conclusion !== 'cancelled'
```

Run the named test with `[root]` or `[consumer]`, matching the changed file:

```bash
python3 -m pytest 'tests/workflows/test_keepalive_reporter_unresolved.py::test_cancelled_unresolvable_run_skips_with_notice[root]' -q -o addopts=
python3 -m pytest 'tests/workflows/test_keepalive_reporter_unresolved.py::test_cancelled_unresolvable_run_skips_with_notice[consumer]' -q -o addopts=
```

Each mutated production script gives one intended assertion failure (exit 1),
then restoring its saved exact bytes gives one PASS (exit 0). The paired raw
logs/JUnit and `proof-hashes.json` record each independent mutation, corrected
workflow SHA256, broken SHA256, and exit status. No classifier source was mutated.
The named regression remained unchanged through the final suite expansion.

This is bounded resolver and authority-control proof. Hosted CI, actual post-merge
provider comparison, and fleet-wide reporter failure-rate improvement remain
unverified until delivery and observation.
