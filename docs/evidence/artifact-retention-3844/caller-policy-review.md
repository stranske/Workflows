# Caller retention policy review

The caller-limit P1 on PR #3873 was checked against the shipped
`actions/upload-artifact@v7` bundle, tag commit `cf430e030ddbb5b0abf93d22962f4752f3646cd9`.
The artifact library's `getExpiration` reads `GITHUB_RETENTION_DAYS`, clamps
requested retention to that maximum, and emits a warning. It does not reject
an upload just because the requested 14 or 30 days exceeds the caller limit.

[Shipped implementation](https://github.com/actions/upload-artifact/blob/cf430e030ddbb5b0abf93d22962f4752f3646cd9/dist/upload/index.js#L84118-L84143)

Bundle SHA256: `770f388a1d56c622f8bc2c99e923280a29f9931161bc7781ea4de8a8f4cce1b2`.

The exact extracted `getExpiration` and `getRetentionDays` functions were run
in Node's VM with a stub Timestamp conversion and captured warning function.
No upload, credentials, paid call, or repository setting was involved.

| Request | Caller limit | Effective days | Warnings |
| --- | --- | --- | --- |
| 14 | 7 | 7 | 1 |
| 30 | 7 | 7 | 1 |
| 14 | 90 | 14 | 0 |
| 30 | 90 | 30 | 0 |
| 14 | 1 | 1 | 1 |
| 30 | 1 | 1 | 1 |

All six cases passed. This is a direct function-level check of caller clamping,
not evidence that a live consumer upload occurred. Future hosted artifact
creation remains the effectiveness measure. No workflow YAML change is needed
for this review claim. The requested Workflows values remain 14 and 30 days.

The separate duration-regression finding is addressed by 22 independent, named
policy assertions: four runner outputs request 14 days and eighteen other
uploads request 30. Altering either a production Codex 14-day value or an intake
30-day value to 90 triggers the corresponding assertion; production bytes are
restored after each check. Existing all-upload presence checks remain.

Final local validation: 36 retention tests PASS; 139 retention/consolidation/drift
regressions PASS. Ruff, Black and template drift pass.

## Recover the secondary validation reports

The [secondary reports archive](secondary-validation.tar.gz) contains the
14-day and 30-day RED logs and JUnit reports, both passing suites' logs and
JUnit reports, the mutation hash receipt, and the six caller-limit results.
Browse the [original files from PR #3873](https://github.com/stranske/Workflows/tree/0d5eec17ff52fa21e6cfb15735688de7a112e7e0/docs/evidence/artifact-retention-3844)
or run these commands from a Workflows checkout root. They verify the download
and print the directory containing the original filenames.

```bash
archive=docs/evidence/artifact-retention-3844/secondary-validation.tar.gz
out=$(mktemp -d "${TMPDIR:-/tmp}/workflow-retention.XXXXXX") &&
  printf '%s  %s\n' 'a280409d89dabf99fd2d55b2d006033b1a42e7e9b9f87ab7dda491b0235b0857' "$archive" | shasum -a 256 -c - &&
  tar -xzf "$archive" -C "$out" &&
  printf '%s\n' "$out"
```
