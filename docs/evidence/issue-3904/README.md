# Issue3904 current evidence

The archive retains two real production-mutant assertion RED/restored GREEN pairs,
raw one-node JUnit and console, original/mutated source bytes, and the exhaustive
projection map audit. Its adjacent manifest binds each archive member by bytes
and SHA256. Production caller bytes are unchanged. The scripts retain the actual
local interpreter and private checkout path as invocation evidence.

This proves the two named causal checks and explicit projection witnesses. It
does not prove all deleted lexical tuples equivalent. Full matched coverage,
local runtime, both hosted Python jobs and controlled hosted timing remain
separate acceptance. See docs/ci/verifier-grammar-matrices.md and the PR's live
validation record. Source #3904 remains open until that evidence is dispositioned.


Current candidate validation: **40,836 PASS**, exit0, 962.25s, Python3.12.2,
four xdist workers/loadgroup, repository coverage configuration. Raw candidate
JUnit, coverage JSON, console and exact runtime versions are retained in
candidate-validation.tar.gz with a member manifest. The CI collection behavior
also has actual base RED (two assertions) / current GREEN from the canonical
Gate deliberate-break checker. Twenty-four focused workflow tests pass.

The matched local baseline remains in progress in the opener run directory at
handoff. Because the two local runs overlap, elapsed times are observational,
not a controlled speedup measurement. No unchanged branch-coverage/equivalence,
Python3.13, full Gate, provider acceptance or under-ten-minute claim is made.
The original source issue stays open until those remaining results are assessed.

The complete per-function inventory is now checked by two focused tests in
`tests/scripts/test_pr_verifier_grammar_inventory.py`. Their audit-specific
deliberate breaks (a stale inventory count and a missing emitted lexical witness)
each produce assertion RED and restored GREEN. Console output is retained in
`inventory-audit-validation.txt`; `inventory-audit-validation.json` records the
command, Python version, exit codes and byte-identical restoration hashes.
These audit checks are separate from the production classifier/floor mutations
in the existing archive and do not close the outstanding coverage/hosted gates.

## Follow-up #4462 runtime-reader validation (2026-11-07)

The removed `scripts/gate_runtime_evidence.py` and its tests were recovered from
pre-reduction commit `d5c12fec48816701c24635dcc83ce1032d88c4b2`. The restored
six-test baseline passed before changes. The reader now requires explicit
successful job conclusions, complete runtime walls, scheduled-versus-observed
JUnit counts and valid executed-line/branch lists. It validates full lowercase
40/64-character object IDs before Git, handles missing pytest invocation markers,
and verifies source identity inside `build_report`. CLI tests exercise omitted,
matching and mismatched `--repo` identity. See the [reader contract and commands](../../ci/verifier-grammar-matrices.md#controlled-hosted-comparison).

On Python 3.14.10:

```bash
python -m pytest tests/scripts/test_gate_runtime_evidence.py --cov=scripts.gate_runtime_evidence --cov-report=term-missing -m 'not slow' -q
ruff check scripts/gate_runtime_evidence.py tests/scripts/test_gate_runtime_evidence.py
```

Results: **109 passed**, reader coverage **91.04%**, Ruff passed. No coverage
percentage target is specified for this reader task. This is local reader
validation, not the outstanding scoped verifier Python 3.12/3.13 coverage or
controlled hosted phase-timing evidence. Both installed older interpreters lack
pytest; no successful run on either is claimed.
The existing `tests/scripts/test_pr_verifier_body_overall_integration.py` suite
also passes: **2,054 passed in 15.22s**, using `-q -m 'not slow'`.

The next summary task still requires explicit `agent-high-privilege` approval:
update `format_growth_summary` and the embedded summary in
`.github/workflows/reusable-10-ci-python.yml` together so unknown collection
budgets and unreadable JUnit timing render as UNKNOWN. Keep existing checks and
bounded workflow controls. No protected workflow was edited. Attempts to add
`needs-human` and post a blocker comment on PR #4527 were rejected with
`MCP tool call requires approval, but approval policy is never`.

Touched Python files were formatted individually. A serial Black check that
honors all configured exclusions reports **958 files would be left unchanged**.
After populating the writable cache with that source set, the exact required
Black command passed with **958 files unchanged** and exit **0**:

```bash
BLACK_CACHE_DIR=/tmp/issue-4462-black-cache BLACK_NUM_WORKERS=1 black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

Staging the four changed files failed with
`Unable to create '.git/index.lock': Read-only file system`. The validated
changes remain uncommitted in the workspace. No remote task checkbox has been
changed and no hosted acceptance is claimed. PR #4527 was verified open with
`draft=false` at handoff.
