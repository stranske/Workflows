# Command-launch boundary evidence for #3743

Current repair-history ranking selects scripts/check_deliberate_break.py first:
72 repair-subject commits and 82 touches among 400 script-touching commits. This
is a repair-history proxy, not verified escaped-defect frequency. The existing
archive/classification chunk is independently accepted in #3788.

Ten new named cases (five behaviors times root/template) execute real subprocesses
and actual git archives. They protect inherited PYTHONPATH, missing-test preflight,
missing-executable cause preservation, head timeout and archived-base timeout with
private-directory cleanup. Timeout is deliberately shortened to 0.25 seconds by a
local wrapper around the real subprocess runner; child processes are killed by
subprocess.run, and no live service or repository checkout is mutated by tests.

Baseline command:

```sh
python3 -m pytest tests/scripts/test_check_deliberate_break.py tests/scripts/test_check_deliberate_break_archive.py -q -o addopts= --cov=scripts.check_deliberate_break --cov-branch --cov-report=json:<evidence>/wf-focused-before.json --junitxml=<evidence>/wf-focused-before.xml
```

Candidate uses the same command and source scope, adds only
`tests/scripts/test_check_deliberate_break_launch_boundaries.py`, and changes output
names to after. Baseline:256 passed; candidate:266 passed. No failures, errors or
skips. Combined focused line/branch coverage:91.7936694021102% to
92.73153575615474%; 546 to552 covered statements of591 and237 to239 covered branches
of262, zero exclusions. This is not repository-wide90% completion. Both production
copies are byte-identical to the selected base. No production defect was reproduced.

wf-mutation-driver.py contains the exact ten production mutation runs, each selecting
one unique named parameter case. Every actual mutant exits1; finally restores exact
source bytes; every restored command exits0. wf-mutations.json records each argv,
source/mutant hash and exit. This is source sensitivity proof, not a claim that the
new cases failed on an older historical main.

Complete console, JUnit, coverage and history files are losslessly gzip-compressed;
compressed-manifest.json records both encoded and decoded hashes. comparison.json
records exact counts and scope. Template sync/completeness, focused Black/Ruff and
git diff --check pass. Original source3743 and prior provider verdicts remain open
and unchanged. Matching keepalive owns CI/review after PR birth; Reviewed Repo Merge
Verify Closer owns full current-head checks, threads, seven-minute floor, guarded
merge and compare before accepting this bounded chunk.
