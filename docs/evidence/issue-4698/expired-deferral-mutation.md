# Expired deferral break-and-revert receipt

Verified locally on 2026-11-16 UTC for PR #4704, on `orch/issue-4698`.

The named regression test exercises default and `--strict` modes with three
fixed expiry timestamps. It checks the exact stale finding returned by
`validate_registry`, JSON and text output, and freshness enforcement. The
autouse clock remains fixed at 2026-09-14 UTC.

Temporarily removed only `severity=STALE_SEVERITY` from the
`deferred issue expired` finding in `scripts/validate_backplane_registry.py`,
restoring its default blocking severity. Ran:

```text
python3 -m pytest tests/test_backplane_registry.py::test_expired_deferral_is_stale_warning_not_blocking -q -m "not slow"

> assert vbr.blocking_findings(findings) == []
E Left contains one more item: Finding(path='participants[1].issue_deferred.expires_at', message='deferred issue expired', severity='error')

6 failed in 0.83s
exit 1
```

Restored the validator source byte for byte, including
`severity=STALE_SEVERITY`, and reran the same command:

```text
6 passed in 0.75s
exit 0
```

Then ran the full test file:

```text
python3 -m pytest tests/test_backplane_registry.py -q -m "not slow"
68 passed in 0.86s
exit 0
```

`git diff --exit-code -- scripts/validate_backplane_registry.py` passed,
confirming the deliberate break was fully reverted.

Black 26.10.1 also checked the entire repository with `--check --line-length 100
--exclude '(\.workflows-lib|node_modules)' .`: all 1,019 files would be left
unchanged. The default process pool was denied by the sandbox and the thread
fallback stalled, so this successful run used an in-process executor with the
same Black entry point, file discovery, formatting and safety checks.

The GitHub connector rejected the attempted PR-body update with:
`MCP tool call requires approval, but approval policy is never`. The remaining
PR checkbox therefore still needs reconciliation using this receipt.

Staging and committing these changes were also blocked: `.git` is read-only,
and Git could not create `.git/index.lock`. The test changes and this receipt
remain uncommitted in the workspace.
