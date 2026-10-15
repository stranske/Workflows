# Explicit artifact retention: issue #3844

The source change adds retention to exactly 22 uploads in 18 workflow files:
14 days for the four per-agent runner outputs and 30 days for the other 18.
All 61 existing explicit settings are unchanged. All 83 direct uploads now set
retention. The repository default remains 90 days.

Named regression:

```bash
python3 -m pytest tests/workflows/test_artifact_retention.py -q
```

The [baseline log](retention-baseline-red.log) records the original 22 omissions.
For the deliberate break, delete only `retention-days: 14` from the Codex runner
upload in `.github/workflows/reusable-codex-run.yml`. The regression fails with
that path and upload line 1818 in the [RED log](retention-deliberate-red.log) and
[JUnit](retention-deliberate-red.xml). Restoring the exact corrected bytes passes
in the [GREEN log](retention-restored-green.log) and
[JUnit](retention-restored-green.xml). These runs used the named command above
with `--junitxml=<evidence-file>` to retain structured results.

The [proof receipt](retention-proof.json) binds the corrected and deliberately
broken workflow SHA256 hashes and exit codes. The
[change matrix](retention-changes.json) identifies all 22 newly explicit values.
The upload line in this matrix is its original source line before insertion.

Additional validation: `python3 scripts/check_template_drift.py` exits 0 with
zero unallowlisted drift. Workflow consolidation and template-drift regression
tests pass. This is configuration and regression evidence; future hosted uploads
must demonstrate the effective retention at creation. Existing artifacts keep
their original expiry, so total artifact count is not an immediate success metric.
