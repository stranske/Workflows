# Issue 4019 closer repair r3: acceptance (recorded before test edits)

Check date: 2026-11-03, recorded 14:36 CST before any test change.

Outcome: the three ranked targets' combined uncovered statements plus branches
in the hosted Gate `gate-coverage-3.14-1` artifact (`runtimes/3.14/coverage.json`).

Command that prints it (after `gh run download <run> -n gate-coverage-3.14-1 -D <dir>`):

```sh
python3 docs/evidence/issue-4019/r3/target_missing.py <dir>/runtimes/3.14/coverage.json
```

Baseline: Gate 41668857273 at PR 4406 final head `79c84f753` (the tree that
merged as `2bd1aa094`): `TARGET_MISSING 73` (aggregate 0+3, sync drift 0+0,
llm_provider 54+16). See `baseline-41668857273.txt`.

Completion condition: the Gate run on this PR's final head finishes. Pass number:
`TARGET_MISSING` <= 5, every residual unit named with a concrete reason.

Feasibility of "about 180": at the round's base (Gate 41557902073) the three
targets had 3 + 0 + 104 = 107 uncovered units (sync drift's 79 in the issue body
was already covered before the round began). Covering every remaining unit gives
107, not 180. The issue scope forbids files outside the three targets, so the
list is exhausted at 107; that is the per-target reason for the shortfall.

Stop rule: 3 hosted Gate attempts or 17:30 CST, whichever first; then report the
first break. Mutation proofs: each new test run alone under a behavior mutation
(named FAILED), then after `git checkout` restoration (passed).


## #4433 integration acceptance (2026-11-06 CST)

The section above is the original #4431 plan and historical stop rule. The
current plan, check time, commands, and stop rule were recorded before code in
`acceptance-integration.md`, which is authoritative for this integration.
Portable commands assume Python 3.13+ in the selected supported environment;
this owner's local `/opt/anaconda3/bin/python3` is Python 3.12.2, so local tests
do not substitute for hosted Python 3.13/3.14 results.

Final-head hosted tests/coverage and delivered-main acceptance are PENDING.
The prior run's TARGET_MISSING=3 is historical evidence only; re-run
`target_missing.py` on separately identified raw artifacts from the final
integration head and name every residual. Original receipts are retained;
fresh results live in `integration-rerun/`.
