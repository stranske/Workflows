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

## Follow-up #4462 growth-summary preparation (2026-11-07)

`scripts/ci_test_growth.py::format_growth_summary` now renders missing or
incomplete collection budgets as **UNKNOWN**, including a null review decision
in its rendered JSON. A default `review_required: false` is not evidence of a
within-budget collection when the collection receipt is absent. The formatter
also explicitly renders missing, unreadable or incomplete JUnit timing as
**UNKNOWN**, retaining independently reported case counts and real zero timings.
It preserves receipt diagnostics and does not mutate the input.

Twenty bounded tests cover absent, unreadable, malformed and incomplete
collection receipts, known zero/within-budget/over-budget signals, unknown review
flags, absent/unreadable JUnit receipts and real parsed JUnit with missing,
invalid, zero and positive durations.

This is source preparation, not a deployed workflow fix. The current run has no
explicit `agent-high-privilege` approval. The paired task and missing-runtime
acceptance criterion therefore remain unchecked. An authorized editor must:

1. Embed the formatter in `Record CI summary` in
   `.github/workflows/reusable-10-ci-python.yml`, retaining consumer portability.
2. Initialize `growth["review_required"]` to `None` until a valid complete
   collection establishes its boolean value, so `summary.json` also preserves
   the unknown budget decision.
3. Replace the Markdown/JSON write block with
   `handle.write(format_growth_summary(growth))`.
4. Add bounded actual-summary subprocess controls for absent and unreadable
   collection/JUnit receipts and invalid durations; assert explicit UNKNOWN text,
   null budget decisions, retained counts and unchanged failed gate outcomes.
   Preserve the existing embedded-helper parity and real serial/xdist controls.

Local validation on Python 3.14.10:

```bash
env -u GITHUB_STEP_SUMMARY python -m pytest tests/scripts/test_ci_test_growth.py tests/workflows/test_ci_test_growth.py tests/workflows/test_reusable_ci_workflow.py -q -m 'not slow'
python -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py -q -m 'not slow'
ruff check scripts/ci_test_growth.py tests/scripts/test_ci_test_growth.py
git diff --check
```

Results: **105 passed in 62.71s**, **2,054 passed in 25.27s**, Ruff passed, and
the diff check passed. The initial existing-workflow run had nine failures caused
by an inherited read-only `GITHUB_STEP_SUMMARY` path; clearing only that environment
variable allowed all existing tests to pass without changing or skipping them.
These local tests do not establish Python 3.12/3.13 coverage or controlled hosted
phase timings. Existing evidence archives and their manifests are unchanged.

Black formatted both touched Python files at line length 100, and individual
checks pass. The auxiliary serial checker initially reported an unrelated frozen
evidence file, but it omits the configured `force-exclude` for
`config/verify_paired/representative-v1/`. After warming the cache, the actual
required CLI command passed with **959 files unchanged**, exit **0**:

```bash
BLACK_CACHE_DIR=/tmp/issue-4462-growth-black-cache BLACK_NUM_WORKERS=1 black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

No unrelated formatting was changed. The subsequent requested commit was blocked
at `git add` with `Unable to create '.git/index.lock': Read-only file system`.
This session cannot write the repository's Git metadata, so the validated source,
tests and notes remain uncommitted.

The requested `needs-human` label and blocker comment on PR #4527 were each
rejected with `MCP tool call requires approval, but approval policy is never`.
Neither remote mutation succeeded. The implementation and tests remain local,
with the protected workflow follow-up listed above.
