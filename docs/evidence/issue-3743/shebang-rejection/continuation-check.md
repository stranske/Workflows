# PR 4472 remaining acceptance

Check date: 2026-11-06.

Outcome 1: the retained real acceptance tree validates offline after relocation;
failed replacement attempts preserve every prior byte and keep separate diagnostics;
isolated evidence corruption is rejected. The existing literal eight-pass and
eight-pair replay receipts remain unchanged.

Command that prints the outcome:
`/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_shebang_rejection_acceptance_inspection.py tests/scripts/test_shebang_rejection_acceptance_run.py tests/scripts/test_shebang_rejection_archive_bindings.py tests/scripts/test_shebang_rejection_matched_comparison.py -q -o addopts=`

Before edits, the real-input run printed `51 passed, 1 skipped in 5.16s`.
That result lacks injected-failure and offline relocation coverage and does not
prove the remaining outcome.

Stop rule: at most three repair/validation cycles or 60 minutes from the start
of this continuation, whichever comes first. Each focused run must finish in
120 seconds. Stop at the first broken step if the rule trips.

Blocking/drainable pair: a failed replacement cannot promote evidence; its
separate attempt directory retains diagnostics while the prior complete tree
remains usable. No scheduling, writer, review, or merge gate is changed.


Validated outcome: `72 passed, 1 skipped in 11.31s`. The skip is the existing
missing-interpreter check because the literal interpreter is present on this
machine. The changed validation helper's focused tests printed
`3 passed in 0.35s`. Full-repository Black reported 928 files unchanged; focused
Ruff reported `All checks passed!`; strict template validation reported
`All consumer workflows are properly templated and manifested`; all four
recorded validation commands exited 0.

`continuation-validation/` retains the exact focused command and console,
plus outputs from `verify_archives.py:validate`,
`capture_acceptance_run.py:validate_retained`, and
`compare_matched.py:validate_retained` (all exit 0). All five delivered archives
verify, with eight added passing nodes and zero removals, changed old outcomes,
exclusions, or covered-line/branch regressions.

The explicit live inspection command is
`/opt/anaconda3/bin/python3 docs/evidence/issue-3743/shebang-rejection/inspect_main_acceptance.py --inspect-base`.
It reads the full commit hash in the frozen map, never fetches, and reports an
error if that commit is unavailable locally. Its retained output names
`7ab99d09429a3b35aa55f7744f8c75b467f42536` and exit 0. General receipt tests
need neither that Git object nor an origin remote.

Failed attempts remain in `.acceptance-attempt-*/` beside `acceptance-run/`,
with raw command diagnostics, staged files, and `failure.json`. The prior tree
is moved only after staged validation and is restored if promotion fails.

Only affected current metadata bindings were refreshed. The three historical
proof archives, frozen map and pre-change record, matched comparison, literal
acceptance command/JUnit receipts, and 93-file mutation proof were retained.
The earlier raw-comparison validation commands remain historical; its previous
bindings are retained as `previous-input-bindings.json`, and its refreshed
bindings identify this continuation's source and tests.
