# Issue #4700: repo-wide listing fallback verification

Verified on 2026-11-16 with Node v24.22.2.

- [x] The required weekly metrics artifact test command passes.
- [x] Removing the repo-listing try/catch makes the named 5xx test fail;
  restoring it makes the test pass again.

The additional entry-point tests verify that HTTP 401 and 404 reject `main()`
with the original error, do not start priority workflow discovery, and do not
write TSV, JSON, or Markdown selection outputs.

## Deliberate break and restore

Temporarily replaced the try/catch surrounding `listArtifactsForRepo` in
`collectRepoArtifacts` with the unguarded awaited call. No other production
behavior was changed for the experiment.

```text
node --test .github/scripts/__tests__/weekly-metrics-artifacts.test.js
exit 1 (with the try/catch removed)

node --test --test-isolation=none --test-name-pattern='repo-wide 5xx' .github/scripts/__tests__/weekly-metrics-artifacts.test.js
exit 1 (with the try/catch removed)
failing test: repo-wide 5xx falls back to run-scoped priority artifacts and reports the reason
error: { status: 500 }
tests 1; pass 0; fail 1
```

The mocked HTTP 500 rejected `main()` instead of selecting run-scoped artifacts.
The original source was restored in a `finally` block and checked byte for byte
against the pre-experiment source. The deliberate break is not committed.

```text
node --test .github/scripts/__tests__/weekly-metrics-artifacts.test.js
exit 0 (after restoring the try/catch)

node --test --test-isolation=none .github/scripts/__tests__/weekly-metrics-artifacts.test.js
exit 0 (after restoring the try/catch)
passing test: repo-wide 5xx falls back to run-scoped priority artifacts and reports the reason
passing test: repo-wide HTTP 401 rejects main without writing selection outputs
passing test: repo-wide HTTP 404 rejects main without writing selection outputs
tests 37; pass 37; fail 0
```

This Node build reports file-level results under the default isolated test
runner, including for a minimal standalone failing test. The supplementary
commands disable test isolation to expose the named test results. Both runner
modes detect the deliberate break and pass after restoration.

## Delivery limitations

The workspace permits source edits but mounts `.git` read-only. Both `git add`
and `git commit` failed to create `.git/index.lock` with `Read-only file system`,
so these changes have not been committed or pushed.

Updating PR #4707 with this evidence and the verified acceptance checkboxes was
also rejected: `MCP tool call requires approval, but approval policy is never`.
The PR acceptance criteria therefore remain unchecked remotely; publication of
this evidence and a source commit still require an authorized runner.
