# Malformed pytest launcher rejection

This test-only increment protects the root and consumer-template import-probe
boundary against empty files, absent shebangs, unclosed quotes, and an unresolved
`env -S python3` interpreter. Each case uses a real executable file and restricted
PATH. It asserts that no probe is available, the runtime is not managed, and a
probe cannot report success. Production helpers and prior proof are unchanged.

The current tests exercise both the bare `pytest` name through real PATH lookup
and its absolute executable path. Any attempt to execute a probe subprocess
fails immediately. The standalone replay uses only the standard library and
rejects DTDs and entity declarations before parsing JUnit. Its 21 companion tests
cover normal XML, declaration rejection in UTF-8 and UTF-16, invalid test identities
and outcomes, restoration after failed RED validation, and all eight real mutation
pairs followed by reuse rejection before any copy or checkout.

Receipts for the replay regression tests, fresh mutation pairs and matched coverage
are retained in `replay-validation/proof.tar.gz`, with current input bindings in
`replay-validation/summary.json`. The earlier PATH lookup receipts in
`path-lookup/` and original `proof.tar.gz` and `summary.json` below remain frozen
historical evidence. This runner has Python 3.14 at
`/opt/hostedtoolcache/Python/3.14.8/x64/bin/python`; it does not have the historical
`/opt/anaconda3/bin/python3`. Fresh receipts record the actual interpreter used.

Run the focused tests:

```sh
python3 -m pytest tests/scripts/test_check_deliberate_break_shebang_rejection.py -q -o addopts= -m "not slow"
```

Reproduce the eight controls in a new output directory:

```sh
python3 docs/evidence/issue-3743/shebang-rejection/replay.py --output /tmp/fresh-shebang-rejection-proof
```

The replay mutates one rejection branch at a time in private source copies.
Each exact module/test/parameter must produce one assertion failure (exit 1,
no errors or skips), then pass (exit 0) after byte-identical restoration. The
output directory is claimed before any source copy or mutation; reuse is
rejected. The frozen reuse audit confirms all 93 existing proof files retained
their bytes.

The historical `summary.json` binds original source, test, replay and coverage configuration
bytes to `proof.tar.gz`. The archive contains exact process argv/cwd/exits,
raw console/JUnit/coverage JSON, all original/mutated/restored source copies,
and `manifest.json` with SHA256 and byte lengths for every other member.
Temporary paths in these records describe the historical execution; reruns
naturally use new paths. Verify the archive SHA256 first, then each member
against its manifest. The README and summary are outside the archive.

Matched coverage uses the same twelve existing helper test modules, adding
only the new test module for the candidate. Baseline: 340 PASS; candidate:
348 PASS, exactly eight added nodes, no changed old outcomes. The same 1,244
statements and 556 branches, with zero exclusions, gain eight covered lines
in the template and five branches (one root, four template); no covered line
or branch regresses. Raw selection and commands are in the archive.

The repair-subject/churn proxy over the last 400 scripts-touching commits
ranked this helper first (74 repair-subject matches, 83 touches). This is not
a verified escaped-defect ranking. The measurement is helper-scope coverage,
not repository-wide 90%, hosted CI, provider acceptance, or deployment proof.
Source #3743 remains open for its broader goal. Keepalive owns subsequent
CI/review; closer owns exact-head gates, the review floor, and actual compare.
