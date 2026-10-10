# Failed uv executable lookup coverage

Related to Workflows issue 3743. This is the next bounded chunk after PR 3814, whose independent closer acceptance permits continuation while its provider compare CONCERNS remain recorded. The umbrella repository-wide 90% goal is incomplete and full-repository coverage is UNKNOWN here.

## Behavior and scope

Eight root/template cases run a private executable named `uv` as a real subprocess. They verify that a nonzero lookup with plausible stdout, or a successful lookup with whitespace-only stdout (including newline/tab-only blanks), cannot create a PyYAML probe. Both the initial `which pytest` and nested shebang `which python3` boundaries are exercised. The exact lookup arguments, working directory and absence of additional launches are asserted. This is a subprocess boundary test, not an integration claim about an installed uv distribution. Neither production helper changes; both retain SHA256 `cc97119ea26afec275be3c83d22bc75de0d452cd0f4764896cc9d037274ab25a`.

Selection uses the latest 400 scripts-touching commits at base `0543a3f2712e08a83ed2f4eb40e3b72fd06ef14f`. The helper ranks first: 73 repair-subject matches / 82 touches, ahead of pr_verifier 30/36 and runner core 27/37. This is a transparent repair-history proxy, not a count of proven escaped defects. Exact history and interpretation are retained in ranking-history.txt and selection.json.

## Observed validation

- Identical seven-file baseline suite: 300 PASS; adding this one test module: 308 PASS. Exactly eight added nodes; all prior outcomes remain PASS.
- Same 591 statements, 262 branches, zero exclusions. Covered lines 568 → 570 and covered branches 241 → 243. Combined focused helper coverage 94.84% → 95.31%; statement coverage 96.11% → 96.45%; branch coverage 91.98% → 92.75%. New lines 680/685 and arcs 679→680 / 684→685. No previously covered line or branch disappears.
- Eight individual production guard mutations, one per new root/template node: each named test RED exit 1 while the guard is broken, then GREEN exit 0 after exact restoration. The private replay never mutates caller files. JUnit verifies one executed failure for RED and one executed pass for GREEN; collection errors/skips do not count.
- Whole-tree Black: 680 files unchanged. Focused Ruff PASS; template completeness PASS; git diff --check PASS.

## Replay and retained evidence

From repository root, using an environment with pytest, pytest-cov and defusedxml:

```sh
python3 -m pytest tests/scripts/test_check_deliberate_break_uv_resolution.py -q -o addopts= -m "not slow"
python3 docs/evidence/issue-3743/uv-resolution/replay_uv_resolution.py --output /tmp/uv-resolution-fresh-proof
python3 docs/evidence/issue-3743/uv-resolution/replay_suites.py --output /tmp/uv-suites-fresh-proof
```

The replay refuses an existing output directory. `validation.tar.gz` retains baseline/candidate exact argv, raw logs, JUnit and coverage JSON; all sixteen RED/GREEN command receipts/logs/JUnit files; and mutation/source/test/driver identities. `archive-index.json` binds every one of its 61 members by size and SHA256 plus the archive SHA256. `comparison.json` binds the matched outcome/coverage comparison and eight added test nodes. The archived command JSON files are exact historical receipts with the original machine paths; do not execute them verbatim on another machine. To rerun the suites, use `replay_suites.py` from a checkout of this PR, not from a receipts-only extraction. It locates that checkout from its own file, validates all ten production/test input hashes, selects the current Python interpreter, and creates fresh coverage/JUnit/log paths under `--output`. It refuses an existing output path. Report options are quoted through `PYTEST_ADDOPTS`, keeping user-selected artifact paths out of the subprocess executable arguments; paths containing spaces are supported. The receipts archive contains no repository source. The baseline omits only the new module; production bytes and prior seven test files are identical.

Hosted Gate/check topology and provider verifier disposition remain separate acceptance gates. This chunk does not authorize merge, certify repository-wide 90%, or close source 3743.

## Review recovery: optimized proof and quoted report paths

Proof guards now raise explicit errors under `python -O` and `PYTHONOPTIMIZE=1`, including named-case identity. Six invalid-result subprocess regressions fail on the original production replay and pass after restoration of the fix. A seventh CLI transport regression detects broken report quoting for an output path containing spaces (stand-in pytest, not a suite-acceptance claim). The actual optimized production replay independently retains all eight named RED1/GREEN0 pairs. Raw logs, JUnit and command receipts are in `review-recovery.tar.gz`, bound by `review-recovery-index.json`. The original validation archive and matched 300/308 coverage result remain historical and unchanged.

### Hosted subprocess portability recovery

The e3836e4 hosted Python 3.13 run failed all six optimized proof controls because
its environment lacks `defusedxml`. The fixed synthetic XML unit fixture now
supplies a standard-library parser stand-in and runs the production module in
a `-O -S` child, proving these controls need no site packages. This does not test
XML hardening; the actual eight-mutant replay still uses `defusedxml`.
Removing the stand-in yields six assertion failures; restoration passes all
15 affected tests. Raw logs, JUnit and commands are bound by
`ci-portability.tar.gz` and `ci-portability-index.json`. Fresh hosted Gate is required.

### Failed-proof restoration controls

`tests/scripts/test_uv_resolution_replay_restoration.py` adds eight controls for
timeouts and rejected proofs during RED and GREEN in both helper copies. Each
control checks that both private helpers and caller inputs retain their original
bytes, the original exception propagates, and no successful `controls.json` is
published. These controls replace the proof runner and do not parse XML, so they
need no `defusedxml` installation. Changing the production replay's restoration
write to retain the mutated bytes makes all eight controls fail; byte-identical
restoration makes all eight pass. The three focused test modules pass 23 tests.

The suite replay now selects `-m "not slow"` and prints `term-missing` coverage
alongside JSON. Its CLI regression checks both options while preserving report
paths containing spaces. Fresh matched runs reproduce 300/308 passing tests,
95.31% candidate helper coverage, and no old outcome, line or branch regression.
The seven prior suite inputs, eight boundary cases and production helpers retain
their selected hashes. The replay controls are validated separately from this
matched suite.

`failure-restoration.tar.gz` retains fresh suite reports, focused JUnit/logs,
restoration RED/GREEN receipts, validation drivers, formatting/lint/template
checks and historical integrity verification. `failure-restoration-index.json`
binds every member by size and SHA256, the archive digest and current code input
identities. Run the focused controls from the repository root:

```sh
python3 -m pytest tests/scripts/test_check_deliberate_break_uv_resolution.py \
  tests/scripts/test_uv_resolution_replay_cli.py \
  tests/scripts/test_uv_resolution_replay_restoration.py \
  -q -o addopts= -m "not slow"
```

The retained validation drivers run from the repository root; their historical
artifact paths are receipts, so use a fresh output location for a new run.
The restoration validation driver temporarily changes the replay driver and
restores it in `finally`, verifying its final SHA256. Production helper files
are untouched. The suite comparison driver accepts the fresh suite output path.
Whole-tree Black passes for 682 files using a retained sequential CLI adapter;
the installed Black's parallel execution is blocked and its one-worker event
loop hangs in this sandbox. The adapter uses Black's normal source discovery,
per-file formatting and safety checks. Focused Ruff, template completeness and
diff whitespace checks pass.

The full `replay_uv_resolution.py` command could not be rerun here because
`defusedxml` is absent and PyPI DNS is unavailable. All three historical archives
and their 125 member records were independently verified, including the eight
original production RED/GREEN outcomes and restoration hashes against current
helper bytes. GitHub DNS is also unavailable, so this local acceptance record
does not update the live PR checklist or verify its ready-for-review state.
The requested commit could not be created: staging fails while creating
`.git/index.lock` because `.git` is mounted read-only. The reviewed changes remain
in the worktree.
Hosted Gate remains required; repository-wide coverage remains UNKNOWN, and
these artifacts do not authorize merging or closing issue 3743.

Verified acceptance for this bounded chunk:

- [x] **Tests**
  - [x] Added coverage for failed or blank `uv` lookups in both helper copies.
  - [x] Added replay tests for report paths containing spaces, invalid proof
    results, and restoration after failures or timeouts.
  - [x] Replay checks verify test outcomes and restore temporary changes.
- [x] **Documentation**
  - [x] Retained test evidence, matched coverage comparisons, replay instructions
    and artifact integrity records.
  - [x] Repository-wide coverage remains unmeasured; evidence does not authorize
    merging or closing issue 3743.

### Optimized GREEN result controls

Six additional subprocess controls reject invalid GREEN proof results under
`python -O -S`: nonzero exit, test error, skipped test, wrong case identity,
unexpected failure and duplicate cases. They share the existing RED fixture's
fixed synthetic XML stand-in; the production replay keeps `defusedxml`.
Each control fails when its corresponding production proof guard is weakened in
a private copy, then passes after byte-identical restoration. Caller files are
unchanged. The three focused modules now pass 29 tests. Run them with the focused
command above; the new nodes are `test_optimized_green_replay_rejects_invalid_proof`.

`green-proof-controls.tar.gz` and `green-proof-controls-index.json` retain the
six individual mutation/restoration pairs, command receipts, JUnit, logs, the
reproducible validation driver and current input hashes. Extract the validation
driver to a temporary directory and run it from the repository root with a fresh
output directory:

```sh
python3 /tmp/validate_green_controls.py /tmp/uv-green-controls-fresh
```

Fresh matched suites again pass 300/308 tests with focused helper coverage
94.84% → 95.31%, unchanged 591 statements / 262 branches / zero exclusions,
and no old outcome, covered-line or covered-branch regressions. Their raw
reports, exact command receipts and verified comparison are retained in the
same archive. The six new replay controls are outside this matched suite.

All four prior indexed archives (159 members) and all ten selected suite input
hashes were verified before this extension. The live PR was open and ready for
review, but updating its acceptance checklist was blocked because the GitHub
connector requires approval and this run's approval policy is `never`.
The requested blocker comment and `needs-human` label hit the same approval block.
The verified local acceptance checklist above remains the reconciliation record.
Whole-tree formatting is verified for 682 files with the retained sequential
Black CLI adapter, which uses normal discovery and per-file safety checks.
The required standard Black invocation fails during worker startup because the
sandbox blocks its forkserver socket; its failure log is retained. Focused Ruff,
template completeness and diff whitespace checks pass. Creating the requested
commit is also blocked: `git add` cannot create `.git/index.lock` on the read-only
Git metadata mount. The code and evidence remain in the worktree.

### JUnit validation and restoration together

Sixteen additional controls call the real `main()` and `run_case()` together.
They supply synthetic pytest results for incorrect outcomes, wrong case names,
malformed XML and timeouts during RED and GREEN for both helper copies. Each
checks byte-identical restoration of both private helpers and caller inputs,
propagation of the rejection, and absence of a success receipt for the rejected
phase or the whole replay. A successful preceding RED receipt remains available
when GREEN fails. The XML parser stand-in handles only fixed fixture text;
these controls do not test XML hardening or execute the pytest child process.

The focused command above passes 45 tests. Three private production mutations
prove that the new tests detect missing restoration (16 failures), ignored
outcomes (four failures) and ignored case identity (four failures). Every
selected test passes after byte-identical restoration; caller files are unchanged.
Fresh matched suites again pass 300/308 tests with helper coverage
94.84% → 95.31%, unchanged 591 statements / 262 branches / zero exclusions,
and no old outcome, covered-line or covered-branch regressions. Their report
directory contains spaces. The new replay controls remain outside this
matched suite.
`junit-restoration.tar.gz` and `junit-restoration-index.json` retain commands,
JUnit, logs, mutation/restoration receipts, a reproducible validation driver,
formatting results and current input identities. Extract
`validate_junit_restoration.py` into a temporary directory and run it from the
repository root with a fresh report directory:

```sh
python3 /tmp/validate_junit_restoration.py /tmp/uv-junit-restoration-fresh
```

Reconciliation verified all 219 members in the five prior indexed archives,
including the original eight named RED/GREEN pairs and restoration digests.
The local checklist above records all seven acceptance items. PR 3817 was open
and ready for review, but its checklist update, blocker comment and
`needs-human` label require connector approval, prohibited by this run's
`never` approval policy. Staging is blocked by read-only `.git` metadata.
The required standard whole-tree Black command fails at sandbox forkserver
startup; sequential Black passes for 682 files, and the changed test passes
standard Black individually. Ruff, template completeness and whitespace checks
pass. No commit or push was made. Repository-wide coverage remains UNKNOWN;
these artifacts do not authorize merging or closing issue 3743.

### Replay interpreter launch failures

Four additional restoration controls inject `FileNotFoundError` at the pytest
process boundary during RED and GREEN in each helper copy. They call the real
`main()` and `run_case()`, verify propagation of the launch failure, restore both
private helpers and caller inputs, and reject success receipts. This is a
synthetic launch-error control, not execution of a missing interpreter.
The focused command above passes 49 tests. Breaking the production driver's
restoration in a private copy makes all four new controls fail; byte-identical
restoration makes the same four pass. Caller files remain unchanged.

Fresh matched suites pass 300/308 tests with focused helper coverage
94.84% → 95.31%, unchanged 591 statements / 262 branches / zero exclusions,
and no old outcome, covered-line or covered-branch regressions. Their report
directory contains spaces. The four new replay controls are outside this
matched suite; its production and test input hashes remain unchanged.

`launch-restoration.tar.gz` and `launch-restoration-index.json` retain the
focused run, mutation/restoration commands, JUnit, raw logs, input hashes,
fresh suite comparison, validation results and reconciliation record. Extract
`validate_uv_launch_restoration.py` into a temporary directory and run it from
the repository root with a fresh report directory:

```sh
python3 /tmp/validate_uv_launch_restoration.py '/tmp/uv-launch-restoration-fresh reports'
```

Reconciliation verified all 266 members of the six prior indexed archives and
all ten selected suite input hashes. All seven local acceptance items above
remain verified. PR 3817 is open with `isDraft=false`; the connector rejected
its checklist update, blocker comment and `needs-human` label because approval
is required and the policy is `never`.
The edited test passes standard Black individually, and the retained sequential
Black adapter passes for all 682 files. The required standard whole-tree Black
invocation fails at sandbox forkserver startup; its single-worker invocation
hangs and was interrupted. Ruff, template completeness and whitespace checks
pass. Staging fails because `.git/index.lock` is on a read-only filesystem, so
no commit or push was made. The full eight-mutant replay was not rerun because
`defusedxml` is unavailable; its prior indexed evidence was verified.
Repository-wide coverage remains UNKNOWN; the evidence does not authorize
merging or closing issue 3743.

### Successful replay receipts

The mutation replay now selects `-m "not slow"`. A new successful-replay control
calls the real orchestration and proof validator with fixed synthetic pytest
results, using report paths containing spaces. It verifies all eight ordered
RED/GREEN pairs, receipt exits and named cases, caller identities, mutation and
restoration hashes, and unchanged private helpers and caller inputs. This does
not execute child pytest or test XML hardening. The focused command above passes
50 tests. Removing the slow-test selector, corrupting a restoration hash, or
changing a receipt exit in private driver copies makes this new control fail;
byte-identical restoration makes each pass.

Fresh matched suites pass 300/308 tests with focused helper coverage
94.84% → 95.31%, unchanged 591 statements / 262 branches / zero exclusions,
and no old outcome, covered-line or covered-branch regression. The new control
remains outside the matched suite; all ten selected input hashes are unchanged.

`success-receipts.tar.gz` and `success-receipts-index.json` retain the three
mutation/restoration pairs, command receipts, JUnit, logs, validation driver,
formatting results and reconciliation record. Extract
`validate_successful_uv_replay.py` to a temporary directory and run it from the
repository root with a fresh output path:

```sh
python3 /tmp/validate_successful_uv_replay.py '/tmp/uv-success-receipts-fresh reports'
```

Reconciliation verifies seven prior archive hashes, all 306 member hashes, ten
suite input hashes, and the original eight named production RED/GREEN pairs.
The proposed checked PR body is retained in the archive. Its publication, the
blocker comment and `needs-human` label were rejected because the connector
requires approval and this run's policy is `never`. PR 3817 remains open with
`isDraft=false`. Staging is blocked by read-only Git metadata. Standard whole-tree
Black fails at sandbox worker startup; standard single-file Black and sequential
whole-tree Black pass, as do Ruff, template completeness and whitespace checks.
No commit or push was made. Repository-wide coverage remains UNKNOWN; the
evidence does not authorize merging or closing issue 3743.


## October 10 current replay input refresh

PR #3824 strengthened `test_check_deliberate_break_repair_failures.py` at
`02ddf06f43cf0288b65a066b60a52b3f0808887c`. The current suite replay still
pinned its earlier hash and therefore rejected that intentional change before
launching either suite. Hosted Python 3.13 job 114288766200 reproduced the
problem: one failure in 102,270 executed tests.

`selection.json` now pins the strengthened current test and records the previous
hash, source head and reason in `suite_input_refreshes`. Historical archives and
indexes retain their original bytes and input bindings; their results are not
relabelled as current results. The production helper and all other pinned suite
inputs are unchanged. The input-drift guard remains mandatory.

The exact failing CLI test is RED before the refresh and GREEN after it. A fresh
production-data mutation reinstating the stale pin is also RED; byte-identical
restoration is GREEN. The replay CLI plus repair-failure tests pass 19 cases; 29 restoration tests
also pass. The real current replay passes 300 baseline and 308 candidate cases,
with all baseline nodes preserved and no covered-line or branch regressions.
Raw commands, hashes and consoles are in
`docs/verification/pr-3824-replay-binding/`. Hosted CI and the exact new-head
review window must complete before merge; this local receipt is not provider
PASS or full repository CI acceptance.
