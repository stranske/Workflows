# Expired deferral break-and-revert verification

Verified on November 16, 2026 for PR #4704 / issue #4698.

The named regression test uses the autouse fixed validator clock
`2026-09-14T00:00:00+00:00`. It checks an earlier UTC timestamp and timestamps
with positive and negative timezone offsets that equal the expiry boundary.
Each case exercises JSON and text output, default validation, `--strict`, and
`--enforce-freshness`.

## Deliberate break

Temporarily removed `severity=STALE_SEVERITY` from the `deferred issue expired`
finding in `scripts/validate_backplane_registry.py`. This restores the default
`error` severity.

```console
$ python3 -m pytest tests/test_backplane_registry.py::test_expired_deferral_is_stale_warning_not_blocking -q -m 'not slow'
3 failed in 0.79s
```

Exit code: **1**. All three cases failed at
`blocking_findings(validate_registry(registry)) == []`. The blocking list contained:

```text
Finding(path='participants[1].issue_deferred.expires_at', message='deferred issue expired', severity='error')
```

## Revert and verification

Restored the original validator source, including `severity=STALE_SEVERITY`.
`git diff --quiet -- scripts/validate_backplane_registry.py` exited **0**,
confirming the deliberate source mutation was fully reverted.

```console
$ python3 -m pytest tests/test_backplane_registry.py::test_expired_deferral_is_stale_warning_not_blocking -q -m 'not slow'
3 passed in 0.73s
$ python3 -m pytest tests/test_backplane_registry.py -q -m 'not slow'
65 passed in 0.78s
```

Both test commands exited **0**. The named test also verifies that the report
contains one stale finding, zero blocking findings, `blocking_ok=true`, and
`ok=false`. No case depends on today's date.

Formatting and lint validation also passed:

```console
$ black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
1019 files would be left unchanged.
$ ruff check tests/test_backplane_registry.py
All checks passed!
```

Black required `BLACK_NUM_WORKERS=1` because the sandbox denied worker-process
startup. Its thread fallback also stalled awaiting event-loop wakeups, including
on a two-file check. A temporary `sitecustomize.py` under `/tmp` scheduled a
50-millisecond asyncio timer so completed formatting work could be collected.
The successful repository-wide invocation used
`PYTHONPATH=/tmp/backplane-black-polling`; no Black formatting or validation logic
was changed, and the workaround is not part of the repository changes.
