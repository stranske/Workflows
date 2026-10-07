# Runtime-probe evidence for #3743

The fourteen existing root/template cases now observe the real subprocess runner.
They assert the import probe's exact command, working directory, exit code and
stdout sentinel; the original OS exception's identity as well as its ENOENT,
filename and cause; and the absence of any further launch after failed repair.
The unrecognized-command mutation now actually launches that command while
returning False, so its RED result proves the non-launch contract directly.
No production defect was reproduced and no production code was changed.

The original receipts in this directory describe the earlier test and driver
bytes. Fresh receipts for the strengthened tests are under `revalidation/`.
Each command receipt contains the actual argv, cwd, process exit and hashes of
its complete separate stdout/stderr files. JUnit and coverage JSON are retained
without abridgment. `source-provenance.json` verifies that both production copies
and all four baseline test files are byte-identical to base
`98b6ed3de1fdea92e3eb00420c863f873a00a210`.

Replay into a directory that does not already exist:

```sh
python3 docs/evidence/issue-3743/runtime-probes/replay.py --output /tmp/unique-runtime-probe-proof
```

The fresh replay ran in a new temporary directory. Its complete output was then
copied to `revalidation/replay/`; argv and JUnit retain the actual temporary paths.
All fourteen distinct named cases have mutation exit 1 and restoration exit 0.
Each RED JUnit reports one executed failure with zero errors/skips; each GREEN
reports one passing case. Original and restored SHA-256 hashes match in every
record. The driver also retains each phase's separate raw console streams and
asserts source restoration hashes. `replay-verification.json` records the receipt
cross-checks.

Replay stdout/stderr and JUnit files are losslessly gzip-compressed in the
retained copy because pytest failure diagnostics contain trailing whitespace.
`compressed-manifest.json` records both encoded and decoded hashes; decompressed
bytes match the original raw captures and the embedded control receipts exactly.

Verified task checklist:

- [x] Fourteen root/template runtime-probe cases pass, including real private-module
  imports, sentinel semantics, non-launch, missing executable causes and failed
  repair exception preservation without another launch (`runtime-suite.xml`).
- [x] All fourteen production mutations fail and all byte-identical restorations
  pass, with complete console/JUnit/exit/hash receipts (`replay/controls.json`).
- [x] Matched 272-case baseline and 286-case candidate coverage comparison,
  with zero failures/errors/skips (`comparison.json`).

Both coverage commands use `--cov=scripts.check_deliberate_break --cov-branch`
and `-m "not slow"`. Aside from output destinations, the candidate adds only the
new runtime-probe test file. The source, line and branch universes are unchanged:
591 statements, 262 branches and zero excluded lines. Covered lines increase
552 to 563 and covered branches increase 239 to 241, with no covered-set
regressions. Combined coverage increases from 92.73153575615474% to
94.25556858147714%. The table's `Cover` column reports 92.73% and 94.26%,
respectively; both complete coverage JSON files are retained.

The required repository-wide Black command exits 0 for all 674 Python files;
focused Black/Ruff and template sync/completeness checks also exit 0. This
runner's multi-file Black execution stalled, so `revalidation/black_serial.py`
uses the installed formatter's same source discovery, configuration and AST
safety checks serially to populate a writable cache. The unmodified required
CLI then verifies that cache with `BLACK_CACHE_DIR=/tmp/runtime-probes-black-cache`.
The serial and CLI receipts retain the commands, environment overrides and
complete output. `validation.json` records the final checks and
`revalidation/manifest.json` hashes all fresh receipts.

The retained ranking selects `scripts/check_deliberate_break.py` using a
repair-history proxy followed by churn, rather than file size. That proxy does
not establish verified escaped-defect frequency. These measurements cover only
this helper and do not establish repository-wide 90% coverage.

GitHub API access is unavailable, so this local checklist does not claim a remote
PR-body update or verification of PR readiness. The canonical `.git` directory
is read-only; commit handoff uses isolated Git metadata under `/tmp` and a bundle.
