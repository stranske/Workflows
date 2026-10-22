# Local Core validation

Validated on 2026-10-19, without live provider requests or runtime installation.

```bash
python3 -m pytest tests/scripts/test_closer_runtime.py \
  tests/scripts/test_closer_portable_boundaries.py \
  tests/test_check_checks_reported.py -q
```

Result: **356 passed**. Ruff and Black checks passed for the six touched Python
files; the shipped minimal fixture passed the actual schema/canonical-key CLI
validator; tracked whitespace checks passed. The tests include:

- Real topology collection over complete offline REST fixtures; native CLI and
  optional incumbent provenance; caller PASS/fixture adapters rejected; FAIL and
  UNKNOWN never cached as success; changed criteria/epoch rejected.
- Native HTTP 403 denial, 409/422 CAS rejection, create-only writes, conditional
  update races, timeout-after-write readback, unknown POST/PUT containment, and
  two competing shared claimants. Diagnostic cache cannot grant ownership.
- Mandatory owner/epoch/spec guards; retained denial across heads; caller
  runtime-authorization receipts ignored; read/reconciliation-only unknown
  handoffs; absent desired results remain uncertain; CLI reconciliation uses
  actual fixed read producers instead of caller observations.
- Explicit expiry tests with no eviction; schema, canonical-key, revision, and
  store-boundary corruption; actual killed subprocesses after submission and
  after temporary-file fsync but before atomic replacement.

These results establish local code/test behavior. Provider credentials, branch
policies, deployed shared claims, production queue/verifier integration, and an
end-to-end closer canary remain unverified. Keepalive v2 is unchanged and does
not automatically participate in the portable fence. Core cannot lift a denial
from a caller receipt or independently authorize permission reset or owner
replacement. Earlier scaffold records with incompatible canonical keys require
an explicit preservation-aware migration; none was attempted.

No issue, PR, push, merge, label, shared claim, global scheduling change, session
store access, or delegated worker was part of this local repair.

## Independent-review follow-up (2026-10-19)

Local only: 375 passed (the 356 prior plus 19 in `tests/scripts/test_closer_core_followup.py`,
including real crashed-worker/observer processes and a multiprocess forged-transition test),
mypy clean on the three scripts, Ruff and Black clean. Not live acceptance; no network use.


## Final contract and package review

The combined producer, contract, boundary, recovery, successor-history and package
suite passes **400 tests**. Four source files pass mypy; changed Core/package files
pass Black and Ruff. Independent review identified and corrected a transition that
could otherwise mark an unresolved intent unavailable, missing dependency-version
enforcement and an unrestricted package entrypoint. Regression tests cover both
the public terminal API and direct CAS transition, unsupported versions and a
redirected entrypoint. Package materialization preserves an existing destination.

These are local implementation results. They do not establish live shared-store
integration, desktop qualification, deployed acceptance, or higher throughput.

The subsequent external review added native required-publisher identity coverage,
matching sealed dependency/entrypoint environments, trusted external CLI digest
verification, precise HTTP rate classification and unchanged-fixture key checks.
The combined suite passed 446 tests before the final relative-root regression;
package relocation also exercises the real sealed entrypoint with an inherited
decoy import path. Crash-worker leases allow import/validation overhead before
expiry. Live acceptance remains pending.
