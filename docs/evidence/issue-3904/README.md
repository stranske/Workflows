# Issue3904 current evidence

The archive retains two real production-mutant assertion RED/restored GREEN pairs,
raw one-node JUnit and console, original/mutated source bytes, and the exhaustive
projection map audit. Its adjacent manifest binds each archive member by bytes
and SHA256. Production caller bytes are unchanged. The scripts retain the actual
local interpreter and private checkout path as invocation evidence.

This proves the two named causal checks and explicit projection witnesses. It
does not prove all deleted lexical tuples equivalent. The hosted Gate pair is
recorded in hosted-gate-comparison.md. `scripts/langchain/pr_verifier.py`
executed lines stayed 3030 and executed branches stayed 1168, with no lost or
gained arcs. Python 3.13 job wall fell from 674s to 604s and is still 4s over
the 10-minute aim, so that aim is not claimed. See
docs/ci/verifier-grammar-matrices.md.


Current candidate validation: **40,836 PASS**, exit0, 962.25s, Python3.12.2,
four xdist workers/loadgroup, repository coverage configuration. Raw candidate
JUnit, coverage JSON, console and exact runtime versions are retained in
candidate-validation.tar.gz with a member manifest. The CI collection behavior
also has actual base RED (two assertions) / current GREEN from the canonical
Gate deliberate-break checker. Twenty-four focused workflow tests pass.

The matched local baseline remains in progress in the opener run directory at
handoff. Because the two local runs overlap, those local elapsed times are
observational. The hosted pair and verifier branch comparison are in
hosted-gate-comparison.md. The 10-minute python-job aim is missed by 4s.

The complete per-function inventory is now checked by two focused tests in
`tests/scripts/test_pr_verifier_grammar_inventory.py`. Their audit-specific
deliberate breaks (a stale inventory count and a missing emitted lexical witness)
each produce assertion RED and restored GREEN. Console output is retained in
`inventory-audit-validation.txt`; `inventory-audit-validation.json` records the
command, Python version, exit codes and byte-identical restoration hashes.
These audit checks are separate from the production classifier/floor mutations
in the existing archive and from the hosted Gate comparison.
