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

## Keepalive revalidation

The existing ten named cases were strengthened to import a real dependency from
inherited PYTHONPATH, preserve the missing executable's errno and filename, inspect
the actual archived base before overlay, require the overlaid candidate test in the
real child process, and compare every candidate file's bytes after archive cleanup.
The byte comparison includes an untracked binary file and a changed test with CRLF.
The production helpers remain unchanged from the selected base.

The mutation driver now resolves this checkout automatically, accepts `--repo` and
`--output`, and retains compressed RED/GREEN captures and restored/test hashes. Run:

```sh
python3 docs/evidence/issue-3743/launch-boundaries/wf-mutation-driver.py
```

Fresh evidence lives in `revalidation/`; the original captures above are retained.
`commands.json` records the matched test/coverage invocations and exits,
`wf-mutations.json` records all ten distinct source mutations, and `validation.json`
records formatting, lint and template checks. Template completeness redirects only
GITHUB_STEP_SUMMARY to a writable file under `/tmp`. The full Black command uses a
writable cache populated by serial calls to the installed formatter because the
sandbox blocks forkserver sockets; all 668 Python files were checked.

Verified task checklist for this round:

- [x] Ten named root/template launch-boundary cases: the exact requested standalone
  pytest command exits 0 with 10 passing cases (`revalidation/launch-suite.log.gz`).
- [x] All ten actual production mutations exit 1; each byte-identical restoration
  exits 0. Exact argv, original/mutant/restored hashes and raw captures are retained.
- [x] Unchanged archive/classification baseline: 256 passed. Including the launch
  suite: 266 passed, with no failures, errors or skips. Both commands use identical
  focused source/branch settings and `-m "not slow"`. Complete coverage JSON, JUnit
  XML and console logs are retained losslessly as gzip files.

`revalidation/comparison.json` records the full comparison: 591 statements,
262 branches and zero excluded lines in both runs; covered lines increase from
546 to 552 and covered branches from 237 to 239. Combined focused coverage rises
from 91.7936694021102% to 92.73153575615474%. The line/branch universes and exclusions
are identical, and the covered sets have no regressions. Both helper hashes remain
`cc97119ea26afec275be3c83d22bc75de0d452cd0f4764896cc9d037274ab25a`, identical to
base `32a525a5b652bf04a432406e6a9d5fd0b343ea68`. All formatting, lint, template
and whitespace checks exit 0. `revalidation/manifest.json` hashes the encoded and
decoded artifacts. GitHub API access is unavailable in this runner, so this local
verified checklist does not claim a remote PR-body update.

The canonical `.git` directory is also read-only in this runner. The change is
committed using isolated Git metadata under `/tmp/workflows-launch-boundaries-commit/`;
a bundle and patch under `/tmp` provide the handoff without changing canonical refs.
