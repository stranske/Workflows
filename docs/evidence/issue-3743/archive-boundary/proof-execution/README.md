# Archive proof execution follow-up

The eight existing root/template archive cases now require real execution through
`verify_spec`. The executable cases run a committed shell proof on head and on
the archived base, with an external witness recording exactly `head`, then
`base`. The symlink cases execute real pytest on both trees and require that the
base failure concerns the changed regular file, while the external sentinel
remains byte-identical. Both cases also check that verification preserves head
files.

The parent/absolute escape cases append a hostile member to a real Git archive
containing runnable base code. Only the `git archive` transport is substituted;
head pytest, extraction, and verdict classification execute normally. GREEN
requires an unchanged external sentinel, exactly one head test execution, and
`FAIL_BROKEN` / `archive-extract-failed` before base execution. Removing the
containment guard actually overwrites the disposable sentinel in each RED run.

No production repair was warranted by these reproductions. Both helpers were
restored byte-for-byte after each experiment, with identical SHA-256
`5e90a2c58fea8fe906f538f829c4a929cdc2fc5bb3a2d21fcb61c4fb23bec9ca`.

## Observed sensitivity

Each log names every parameter case. The [mutation manifest](mutation-manifest.json)
records commands, failed/passed cases, exact mutations, and restoration hashes;
the [driver](mutation-driver.txt) reproduces the experiments.

| Source mutation, in both helpers | Observed RED | Byte-identical restored GREEN |
| --- | ---: | ---: |
| Remove executable permission | 2 failed | 2 passed |
| Admit external symlinks | 2 failed | 2 passed |
| Remove path-containment rejection | 4 failed | 4 passed |
| Report head success without execution | 8 failed | 8 passed |
| Report base failure without execution | 4 failed | 4 passed |

The last two experiments independently verify the new witness assertions.
The intentionally appended witness logs are distinct from sentinel files whose
bytes must remain unchanged.

## Focused validation

Python 3.14.7 on Linux passes **252 tests** before and after this change, including
all 244 main-helper tests and eight archive cases. Complete [before](focused-before.txt)
and [after](focused-after.txt) captures and coverage JSON are retained. Identical
focused module coverage remains **91.77%**: statements **544/589 (92.36%)**,
branches **237/262 (90.46%)**, with zero lost lines or branches.

The retained runs used the following pytest scope. For a replay, create a fresh
directory outside the repository so the retained captures and their manifest
hashes remain unchanged:

```sh
replay_dir=$(mktemp -d "${TMPDIR:-/tmp}/archive-proof-replay.XXXXXX")
python3 -m pytest tests/scripts/test_check_deliberate_break.py tests/scripts/test_check_deliberate_break_archive.py -q -o addopts= -m "not slow" --cov=scripts.check_deliberate_break --cov-branch --cov-report="json:$replay_dir/focused-after.json" --cov-report=term-missing
```

The fresh [ranking](ranking.json) still selects this helper by the 400-commit
repair-history proxy: 72 subject hits versus the next module's 29, with 45
uncovered statements at the start of this follow-up. This proxy does not count
escaped incidents. Focused module coverage does not measure the whole repository;
the continuing fleet initiative remains **OPEN**.

[Checks](checks.txt) pass template sync, template completeness, focused
Black/Ruff, and helper byte identity. Repository-wide Black passes all **664
files** using the exact required check options and the retained
[serial-dispatch adapter](black-serial-dispatch.txt), which calls Black's
unchanged formatter/checks. Stock parallel dispatch failed because the sandbox
denies worker sockets; single-worker dispatch stalled and was interrupted.
The template validator's initial attempt also could not write the runner's
read-only summary destination; the successful rerun unsets that destination
locally. Initial failures are retained in [checks-initial.txt](checks-initial.txt).
Final whitespace validation is retained in `whitespace.txt`.

## Verified task and pending acceptance

- [x] Eight root/template archive cases exercise the requested filesystem boundaries.
- [x] Every case fails under a matching semantic source mutation and passes after exact restoration.
- [x] Executable proofs actually run; external sentinels and head files remain unchanged in GREEN.
- [x] Complete focused before/after coverage, ranking, per-case logs, and source hashes are retained.
- [x] Template validation, focused formatting/lint, repository Black, and whitespace checks pass.
- [ ] Repeat the literal `/opt/anaconda3/bin/python3` acceptance command where that interpreter exists.
- [ ] Publish the commit and reconcile the remote PR checklist/readiness in the owning lane.

The requested Anaconda interpreter is absent, as recorded in
[requested-interpreter.txt](requested-interpreter.txt). Available-interpreter
results do not satisfy that literal-path acceptance requirement. GitHub API
access is also unavailable, so this run changes no remote checkbox, comment,
label, or PR state. Original checkout Git metadata is read-only; the source/test
and evidence commit uses writable metadata at
`/tmp/workflows-archive-proof-3788/.git`, with bundle handoff
`/tmp/workflows-archive-proof-3788.bundle`.

The [manifest](manifest.json) records source/test hashes, coverage measurements,
commands, and evidence-file digests. Prior classification regressions and their
independent mutation evidence remain in the adjacent `automation/` directory.
