# Current shebang-rejection matched comparison

Current matched comparison for the input bytes in input-bindings.json. summary.json, proof.tar.gz, path-lookup/, and replay-validation/ are historical receipts for earlier bytes. They are not this comparison.

Check date: 2026-11-06
cwd: `/home/runner/work/Workflows/Workflows`
Interpreter: `/opt/hostedtoolcache/Python/3.14.10/x64/bin/python3` (3.14.10 (main, Oct 26 2026, 14:17:03) [GCC 15.2.0])
The literal `/opt/anaconda3/bin/python3` path is not this comparison's interpreter.

Selection: the twelve modules in replay-validation `baseline-command.json`,
with only `tests/scripts/test_check_deliberate_break_shebang_rejection.py`
added for the candidate. Both phases use `coverage.ini`, `-q -o addopts=`,
and `-m not slow`.

Baseline nodes: 340 (340 passed)
Candidate nodes: 348 (348 passed)
Added passing nodes: 8
Removed nodes: 0
Changed old outcomes: 0
Universes identical: True
Exclusions: 0
Covered-line regressions: 0
Covered-branch regressions: 0

Raw JUnit, coverage JSON, command receipts, and computed counts/deltas
are in this directory and in `proof.tar.gz`. `summary.json` stays outside
the archive and records the archive hash. Input SHA256 values are in
`input-bindings.json`.
