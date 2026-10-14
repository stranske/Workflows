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
pass. `summary.json` binds the archived test, replay, source, and archive hashes.

`proof.tar.gz` contains raw argv/cwd/exit records, console logs, JUnit,
original/mutant/restored source, input test/replay bytes, coverage inputs, and a
per-member SHA256/length manifest. The first root-only exploratory measurement
and an unsuccessful coverage-config invocation are not the accepted comparison;
the archive contains the corrected matched two-file baseline and candidate.

## Reproduce

Use Python 3.12 or newer, with `pytest` and `defusedxml` installed in the selected
interpreter. Set `PYTHON` to that interpreter's command or absolute path; it
defaults to `python3`. The replay uses `defusedxml` to reject XML entity payloads
before inspecting JUnit results.

```bash
PYTHON="${PYTHON:-python3}"
"$PYTHON" -m pytest tests/scripts/test_check_deliberate_break_probe_option_boundaries.py -q -o addopts=
"$PYTHON" docs/evidence/issue-3743/probe-option-boundaries/replay.py --output /tmp/fresh-probe-option-proof
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

## Archived revalidation (2026-10-14)

The four existing cases now require an import receipt written by the private
`yaml.py` module. The receipt confirms the child interpreter has interactive mode
disabled and preserves the exact warning operand in `sys.warnoptions`. The fixture
clears inherited `PYTHONWARNINGS` so these assertions measure the command options.
The replay also explicitly excludes slow tests.

- [x] Verify the four root/template tests, including exact argv, runtime
  classification, sentinel, empty stderr, and private-module import receipts.
- [x] Verify four exact named assertion RED/restored GREEN pairs and refuse reused
  output before mutation, preserving all 49 proof files.
- [x] Bind current source/test/replay inputs to matched coverage, raw commands,
  console output, JUnit, and archive member hashes and lengths.

Current validation uses Python 3.14.8 at the executable recorded in
`revalidation/runtime.json`; `/opt/anaconda3/bin/python3` is unavailable on this
runner. Both the 322-case baseline and 326-case candidate reproduce the historical
covered-line and branch sets exactly. The original archive is retained byte for
byte as `historical-proof.tar.gz`, and every original archive member is unchanged.
New raw evidence is under `revalidation/`; its `manifest.json` covers every member
except itself. The root `manifest.json` remains the historical member inventory.

Full-repository Black checks all 745 Python files. Its recorded environment uses
one worker and a temporary event-loop heartbeat to handle lost completion wakeups
in this sandbox; formatter behavior and file checks are unchanged. Focused Ruff,
strict template completeness with a writable summary path, and diff checks pass.
All runtime adjustments and exact commands are archived.

## Review repair (2026-10-14)

The runnable replay now parses JUnit with `defusedxml`; XML entities are rejected
instead of expanded. Reproduction commands select the interpreter as described
above. Archived proof, invocation records, manifests, and their recorded replay
inputs remain unchanged; those hashes identify historical inputs, not this
updated replay. A new replay output captures its own current inputs and commands.
