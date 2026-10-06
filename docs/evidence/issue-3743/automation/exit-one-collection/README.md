# Exit-one collection proof boundary

Real git/archive/pytest runs reproduced a false PASS in both helpers at
`ed99df79`: `--continue-on-collection-errors` lets pytest return exit 1 for a
collection error even though the named base test never executes. The candidate
head executes successfully. An external execution witness requires exactly
one head call and zero base calls in each regression.

`verify_spec` now rejects collection diagnostics without a pytest result for
the selected test as `FAIL_BROKEN` / `base-test-did-not-run`, retaining exit 1
and both base streams. The existing missing-module classification still runs
first. The consumer helper is byte-identical to the root helper, and the
canonical keepalive contract describes the additional boundary. The existing
exact-sync manifest entry already manages this file; its scope is unchanged.

## Observed mutation evidence

The existing exit-code test adds four cases: root and consumer helpers, each
with collection diagnostics on stdout or stderr. The retained
[driver](mutation-driver.txt) restores the prior implementation in both
helpers, runs all four cases, and restores the repaired helpers byte-for-byte.

| Experiment | Failed | Passed |
| --- | ---: | ---: |
| Prior implementation, four new parameter cases | 4 | 0 |
| Exact restoration, four new cases and eight in-test missing-import controls | 0 | 12 |

The [manifest](mutation-manifest.json) records commands, per-case results,
test hashes, and identical before/after restoration hashes. Full pytest
output and JUnit receipts are retained beside it, with trailing spaces trimmed.
The genuine behavioral RED
controls include collection-like text printed inside the executing test on
either stream. No such failure was reclassified as an environment error.

## Focused validation

Available Python 3.14.7 on Linux passes **252 baseline tests** and **256
candidate tests** (248 main-helper cases and eight archive cases). Complete
[before](focused-before.txt) and [after](focused-after.txt) captures and
coverage JSON are retained. Focused module coverage increases from **91.77%**
to **91.79%**: statements **544/589** to **546/591**, branches **237/262**
unchanged. The [manifest](manifest.json) records no lost coverage on unchanged
lines or branches, source hashes, platform, and evidence-file digests.

The fresh [ranking](ranking.json) still selects this helper by the 400-commit
repair-subject proxy: **72 hits** versus the next module's **29**, with **45
uncovered statements** before this repair. This proxy does not count escaped
incidents.

[Checks](checks.txt) pass template sync, completeness, focused Ruff/Black,
helper byte identity, and whitespace validation. Repository Black passes all
**664 files** in [black-all.txt](black-all.txt), using the previously retained
[serial dispatcher](../../archive-boundary/proof-execution/black-serial-dispatch.txt)
with the required check options and unchanged Black formatting. The native
parallel launch fails because the sandbox denies worker sockets; its full
failure is retained in [black-native.txt](black-native.txt).

## Reconciliation and handoff

Recent commit `ed99df79` strengthens execution witnesses for the eight archive
cases and retains their semantic mutation and restored-GREEN evidence under
`archive-boundary/proof-execution/`. Prior merged classification chunk
`8f7c9ed0` and adjacent `automation/` evidence already satisfy the four
unchecked implementation tasks and the collection, exit-code, and template
validation acceptance criteria in the supplied appendix. This follow-up
fixes a newly reproduced classification defect within that scope.

- [x] Review recent commits and retained task evidence.
- [x] Observe false PASS with actual git archives and pytest collection exit 1.
- [x] Add four cases; observe each failing under a real source mutation.
- [x] Restore byte-identical source; verify all four cases and eight behavioral controls pass.
- [x] Mirror the repair to the consumer helper and update the canonical contract.
- [ ] Run the literal Anaconda-path acceptance commands on a host with that interpreter.
- [ ] Apply the prepared remote PR checklist reconciliation and publish this commit.

The requested `/opt/anaconda3/bin/python3` is absent; both literal launch
attempts exit 127 in [requested-interpreter.txt](requested-interpreter.txt).
Available-interpreter checks do not satisfy those literal-path acceptance
criteria. Focused helper coverage does not measure the entire repository;
the continuing fleet initiative remains OPEN.

GitHub read access verifies PR #3788 is open and ready for review. Automatic
approval rejected its checklist update because that mutation requires
approval while this run's approval policy is `never`. The prepared body is
retained at `/tmp/pr-3788-reconciled-body.md`; no remote checkbox was changed.

The original Git metadata is read-only. Writable metadata at
`/tmp/workflows-exit-one-3788.git` and a bundle handoff at
`/tmp/workflows-exit-one-3788.bundle` preserve the commit without changing the
original checkout's index, refs, or unrelated untracked files. Template sync
dispatch requires publishing this source commit first and remains an owning-lane
handoff.
