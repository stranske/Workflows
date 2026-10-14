# Python import-probe option boundaries

This is a separate test-only increment for Related #3743, based on main
`04c137f0422e2e89ede139a8d0b78315709ed980`. It covers repeated interactive
flags (`-ii`) leaving an empty option and a warning-filter operand containing
capital `I` being mistaken for isolated import mode. Root and distributed
copies both build exact probe argv, classify the original pytest runtime, and
execute a real private `yaml.py` import with the expected sentinel.

Production root/template bytes remain equal and unchanged. No workflow,
dependency, exclusion, threshold, model, or source-capture behavior changes.
The source issue remains open for the broader coverage goal.

## Results

Matched baseline: **322 PASS**. Candidate: **326 PASS**, exactly four new
nodes, no removed nodes or changed old outcomes, errors, or skips. Both runs
measure the same two files, 1,182 statements and 524 branches, zero exclusions.
Root coverage gains one line/one branch (587/253 to 588/254); template coverage
gains fourteen lines/twelve branches (418/157 to 432/169). These are helper-scope
measurements, not repository-wide 90% coverage or native provider acceptance.

Four exact named production mutations produce assertion RED (exit 1), followed
by restored GREEN (exit 0). Original/restored source bytes and hashes match.
Reusing the output directory fails before mutation and preserves all 49 files.
Full-repository Black, focused Ruff, strict template completeness, and diff checks
pass. `summary.json` binds the test, replay, source, and archive hashes.

`proof.tar.gz` contains raw argv/cwd/exit records, console logs, JUnit,
original/mutant/restored source, input test/replay bytes, coverage inputs, and a
per-member SHA256/length manifest. The first root-only exploratory measurement
and an unsuccessful coverage-config invocation are not the accepted comparison;
the archive contains the corrected matched two-file baseline and candidate.

## Reproduce

```bash
/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_check_deliberate_break_probe_option_boundaries.py -q -o addopts=
/opt/anaconda3/bin/python3 docs/evidence/issue-3743/probe-option-boundaries/replay.py --output /tmp/fresh-probe-option-proof
```

The replay requires a new output path. It creates only a temporary private source
copy and cleans it on completion. Its JUnit parser requires exactly one executed
named case per phase, no errors/skips, assertion failure on RED, and PASS on GREEN.
Archive invocation records preserve the exact original commands; repeat matched
coverage with `--cov --cov-branch --cov-config=docs/evidence/issue-3743/probe-option-boundaries/coverage.ini`.
Baseline excludes only the new module; candidate adds only that module.

Keepalive owns asynchronous checks/review. Closer must revalidate current full
head, complete topology, every active review body, zero active findings and the
seven-minute floor before guarded merge and actual `verify:compare`. Historical
provider CONCERNS and source-capture ownership remain unchanged.
