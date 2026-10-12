# Runtime-health replay review recovery

PR3838/source3743. Addresses Codex4243073150 and CodeRabbit4243180993.
The old driver treated exit1 as RED, including execution/fixture errors, and
Python optimization disabled its assertions. The driver now requires the exact
selected JUnit node and class, one assertion failure for RED, and one clean pass
for GREEN. Explicit RuntimeError checks run under python -O. Malformed XML,
DOCTYPE/entity declarations, errors, skips, nonassertion exceptions, wrong nodes,
inconsistent outcomes and oversized reports cannot establish success. The Expat
parser rejects declarations/external entities and needs no new dependency.
Every private source copy is restored in finally even when proof validation fails.

Actual driver mutation to original HEAD: six behavioral test failures (DID NOT
RAISE), one valid control. Byte-identical restoration: seven selected controls pass.
All fourteen new guard controls plus runtime-health and prior replay regressions:
30 pass. Actual optimized driver command:
`/opt/anaconda3/bin/python3 -O docs/evidence/issue-3743/runtime-health/replay.py --output <fresh-output>`
ran eight production mutations; every RED has exactly one selected assertion
failure and every GREEN exactly one selected pass, with original/restored SHA256
identical. Full logs, raw JUnit, results and hashes are retained here.

This validates the reusable replay and its existing bounded production controls.
It does not establish whole-source coverage90%, hosted CI, provider PASS or source
3743 completion. Original evidence remains intact; no production check_deliberate_break
behavior was changed in this review fix.
