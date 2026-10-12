# Fallback implementation target selection

Base `2ac3feafcd9a186518adfc3bce89bdc46be2e6ea` already includes head-launch PR#3866. This independent test-only increment exercises public parse_deliberate_break_spec in root and consumer copies. Whitespace-only quoted revert targets are ignored; contextual YAML implementation paths are preferred over a named Python test file. Every case preserves the named test identity and exact pytest command arguments.

Four exact production target-selection mutations in private copies produce four named assertion REDexit1 and byte-identical restored GREENexit0 pairs, no errors/skips. Raw source/mutant/restored bytes, console, JUnit, argv/cwd/exits and hashes are in proof.tar.gz. Reusing output is rejected before mutation and preserves all29 proof files.

Identical eleven baseline modules:320PASS; candidate adds only this module:324PASS. Four new nodes, no removed/changed incumbent outcomes, and no covered line/branch regression. Root helper statements585→587/591; branches251→253/262; zero exclusions. Production and645 historical evidence files are unchanged. Ranking uses73 repair-subject proxy matches/82 touches over400 scripts-touching commits, not verified escaped defects. This is helper coverage, not repository-wide90% or hosted/provider/native acceptance.

```sh
/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_check_deliberate_break_fallback_target_selection.py -q -o addopts=
/opt/anaconda3/bin/python3 docs/evidence/issue-3743/fallback-target-selection/replay.py --output /tmp/new-fallback-target-proof
```

Full-repositoryBlack (701 files), focusedRuff, strict template completeness and whitespace checks pass. All53 raw archive members verify; summary.json and manifest.json retain exact totals and current-input bindings. Broader source#3743 stays OPEN. Keepalive owns hosted CI/review; closer owns complete exact-head checks, all active review findings, seven-minute floor, guarded merge and actual compare.

The original `proof.tar.gz` and `manifest.json` are retained byte-identically as
historical evidence. The current test checks the entire command tuple, including
the interpreter and `-m pytest` prefix. The current blank-target mutation returns
the empty normalized target directly; its named case fails `assert None is not
None`, while the YAML mutation fails the implementation-path assertion. Each
private production copy is restored byte-identically before its GREEN run.

Current Linux revalidation is recorded separately in `revalidation.tar.gz` and
`revalidation-manifest.json`, with exact commands, console/JUnit, coverage JSON,
original/mutant/restored bytes, current input bytes and hashes, and output-reuse
hash comparisons. `summary.json.revalidation` records the current measurements;
the original top-level measurements describe the retained macOS proof.

The requested `/opt/anaconda3/bin/python3` is absent in this checkout. Current
commands use the installed Python 3.14.8 interpreter. Black uses one worker and a
temporary 50ms event-loop timer to observe thread completion in this sandbox;
its formatting rules and full-repository check are unchanged. The archive
retains that runtime adapter and its environment settings. Strict template
validation writes its GitHub step summary to a writable temporary path.
The local GitHub CLI cannot reach the API. The GitHub connector independently
verified PR #3871 is open and ready for review (`draft=false`).
The workspace's `.git` is read-only, and GitHub write tools require approval
unavailable under this run's `never` policy. The verified changes are committed
in an isolated local checkout; publishing and PR checkbox updates remain pending.

Verified local tasks:

- [x] Check whitespace-only quoted targets, contextual YAML preference, named
  test identity, and the complete command tuple for root and template.
- [x] Replay four exact named assertion RED/restored GREEN pairs and reject
  output reuse without changing existing proof bytes.
- [x] Preserve the matched eleven-module baseline, add only the new module,
  and verify unchanged incumbent outcomes and coverage with complete raw evidence.
