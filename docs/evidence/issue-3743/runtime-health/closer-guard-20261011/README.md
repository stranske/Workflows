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

## Recover the original optimized receipts

The [offline archive](optimized-actual-receipts.tar.gz) contains the original JUnit, stdout and
stderr files from the optimized replay. [Results](optimized-actual/results.json)
and the [original file checksums](guard-proof.json) remain directly available.
Browse individual records in the [original capture](https://github.com/stranske/Workflows/tree/71f89d431dc65873db189cb6fcf1a4405422c4c7/docs/evidence/issue-3743/runtime-health/closer-guard-20261011/optimized-actual).

From the repository root, verify the archive and extract the files into a new
directory with their original paths and modes:

```sh
archive=docs/evidence/issue-3743/runtime-health/closer-guard-20261011/optimized-actual-receipts.tar.gz
printf '%s  %s\n' 'dbc9fd848a28addef823029064ecfe95e5289d8332c3bf696a058f7b526e76f7' "$archive" | shasum -a 256 -c &&
    recovered=$(mktemp -d "${TMPDIR:-/tmp}/issue-3743-runtime-health.XXXXXX") &&
    tar -xpzf "$archive" -C "$recovered" &&
    printf '%s\n' "$recovered"
```
