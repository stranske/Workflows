# Fallback implementation target selection

Base `2ac3feafcd9a186518adfc3bce89bdc46be2e6ea` already includes head-launch PR#3866. This independent test-only increment exercises public parse_deliberate_break_spec in root and consumer copies. Whitespace-only quoted revert targets are ignored; contextual YAML implementation paths are preferred over a named Python test file. Every case preserves the named test identity and exact pytest command arguments.

Four exact production target-selection mutations in private copies produce four named assertion REDexit1 and byte-identical restored GREENexit0 pairs, no errors/skips. Raw source/mutant/restored bytes, console, JUnit, argv/cwd/exits and hashes are in proof.tar.gz. Reusing output is rejected before mutation and preserves all29 proof files.

Identical eleven baseline modules:320PASS; candidate adds only this module:324PASS. Four new nodes, no removed/changed incumbent outcomes, and no covered line/branch regression. Root helper statements585→587/591; branches251→253/262; zero exclusions. Production and645 historical evidence files are unchanged. Ranking uses73 repair-subject proxy matches/82 touches over400 scripts-touching commits, not verified escaped defects. This is helper coverage, not repository-wide90% or hosted/provider/native acceptance.

```sh
/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_check_deliberate_break_fallback_target_selection.py -q -o addopts=
/opt/anaconda3/bin/python3 docs/evidence/issue-3743/fallback-target-selection/replay.py --output /tmp/new-fallback-target-proof
```

Full-repositoryBlack (701 files), focusedRuff, strict template completeness and whitespace checks pass. All53 raw archive members verify; summary.json and manifest.json retain exact totals and current-input bindings. Broader source#3743 stays OPEN. Keepalive owns hosted CI/review; closer owns complete exact-head checks, all active review findings, seven-minute floor, guarded merge and actual compare.
