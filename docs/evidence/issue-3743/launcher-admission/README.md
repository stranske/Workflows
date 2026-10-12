# Missing and opaque pytest launcher admission

Related #3743; broader coverage work stays open.

The current helper is still first in the last400 scripts-touching commit ranking:
73 repair-subject matches and82 touches. These are churn/repair proxies, not
verified escaped-defect counts. The matched current nine-module baseline left
lines355/358 and their branches uncovered. A missing pytest executable or a
shell launcher with no Python identity must not authorize repair of the active
interpreter's PyYAML environment.

Four new root/template cases use a private PATH, genuine missing executable and
executable shell script, real shutil.which and real shebang parsing. Production
code, consumer template, workflow/routing settings, exclusions and633 tracked
historical evidence files are unchanged.

Initial validation used /opt/anaconda3/bin/python3 (Python3.12.2, macOS26.6.2):

- Named new module:4PASS.
- Identical nine existing helper/replay modules:312PASS baseline; with only the
  new module added:316PASS. Exactly4 new nodes, no removed/changed old outcomes
  and no covered-line/branch regressions.
- Root helper:581→583 of591 statements and249→251 of262 branches; zero exclusions.
  These focused measurements are not repository-wide90% coverage.
- Each named new case ran against its corresponding actual production mutation
  (return False→True): assertionREDexit1, exact byte restorationGREENexit0,
  one case and zero errors/skips. Root and consumer copies were mutated only in
  disposable private directories, never the checkout.
- Existing output reuse was refused before mutation;17 proof files remained
  byte-identical.
- Full repositoryBlack (708files), focusedRuff, strict template completeness and
  git diff --check passed.

Replay from the repository root with an available Python interpreter:

```bash
python3 docs/evidence/issue-3743/launcher-admission/replay.py --output /tmp/new-launcher-admission-proof
```

From another working directory, supply the absolute path to the repository:

```bash
repo=/absolute/path/to/Workflows
python3 "$repo/docs/evidence/issue-3743/launcher-admission/replay.py" --output /tmp/new-launcher-admission-proof
```

These commands run a new replay with the selected interpreter; they do not
reproduce the historical macOS interpreter identity by themselves.

The initial archive retained35 raw members: matched command argv/cwd/exits, full console,
JUnit and coverageJSON plus raw coverage databases; four mutation-pair receipts
and logs/JUnit; reuse, focused and validation records; fresh ranking. manifest.json
binds every decoded member and committed source/test/proof file with SHA256.
summary.json records the exact baseline/environment/counts/coverage universe.

The current replay additionally binds each phase to the selected JUnit module
and node, the admission assertion, and the test SHA256. Each pair records an
explicit restored SHA256 and verifies all three private inputs after restoration.
Its standard-library XML parser rejects declarations and external entities;
`tests/scripts/test_launcher_admission_replay.py` exercises wrong nodes, wrong
modules, errors, skips, non-assertion failures, XML declarations and output reuse.

The October 12 Linux revalidation is retained under `revalidation/` in the same
archive. The original 35 raw members remain byte-identical; the original archive,
summary, manifest, README and replay are also retained there. The current
`summary.json` identifies the new interpreter and exact measurements. This runner
does not have `/opt/anaconda3/bin/python3`, so it cannot repeat the two acceptance
commands with that exact interpreter. Their historical macOS evidence is retained.

Full-repository Black checks 709 files. A serial scheduler populates a writable
cache in `/tmp`; the required `black --check --line-length 100 --exclude
'(\.workflows-lib|node_modules)' .` command then passes with that cache and
`BLACK_NUM_WORKERS=1`. No formatter or repository configuration is changed.
The supplemental replay tests are validated separately from the matched coverage
comparison, which adds only the four-case launcher admission module.

The next Linux revalidation is retained under `suite-validation/`. The replay
now requires exactly one suite with one test, the expected failure count, zero
errors/skips, and a single direct assertion outcome for RED. Contradictory totals,
missing totals, extra suites, misplaced outcomes and duplicate failures are
rejected. The 18 new RED/GREEN receipt cases expose 15 failures against the
previous validator; all 27 replay tests pass with the revision. The four launcher
tests and production files are unchanged. All 112 previous raw archive members
are retained byte-identically.

PR reconciliation is retained as `suite-validation/reconciled-pr-body.md` in
the archive. The live update was rejected because this run's approval policy is
`never`; the PR was verified open and ready for review. Six checkboxes have
supporting evidence. The revised replay's exact Anaconda command remains pending
because that interpreter is absent here; its Linux replay is verified separately.

Verified implementation tasks:

- [x] Four paired root/template missing and opaque launcher rejection cases.
- [x] Four production assertion RED/restored GREEN pairs with complete receipts,
  test/source hashes, byte-identical restoration and rejected output reuse.
- [x] Matched nine-module comparison: 312 to 316 PASS, exactly four new nodes,
  no old outcome changes or coverage regressions, unchanged production and history.

Hosted CI, expected-check topology, review-thread disposition, seven-minute
exact-head floor, merge and actual provider comparison remain future delivery
gates. Earlier3832/3838 CONCERNS remain unchanged. This chunk proves no native
acceptance, installed deployment, providerPASS or whole-source completion.
