# Issue #3989 review recovery

The sections below retain the native writer's historical validation at committed
predecessor `3a60cc431d668a52e0690248e04cfcd25b220af4`. The final section records
the subsequent local source-owner verification and remaining receipt correction.

## Empty-current-agent pool filtering (r4301075000)

- [x] Exclude blocked provider pools during initial `agent:auto` selection.

Both the source and consumer-template policy filter pool capacity before concrete
label, route ranking, exploration and registry-default selection. Task-specific
ranking capacity is respected. No eligible runnable pool returns no agent;
exports without capacity data and explicit routing without `agent:auto` retain
their existing behavior. The script is already owned by the sync manifest;
no file was added, removed or re-scoped in the consumer payload.

The paired regressions failed before the source change (42 passed, 6 failed) and
passed afterward (48 passed, 0 failed). Broader validation passed:

```sh
node --experimental-test-isolation=none --test .github/scripts/__tests__/agent-delegation-policy.test.js .github/scripts/__tests__/agent_delegation_policy.test.js tests/scripts/test_agent_delegation_policy_intake.js
# 114 passed, 0 failed

GITHUB_OUTPUT='' NODE_OPTIONS='--require=/tmp/keepalive-test-runtime.cjs --experimental-test-isolation=none' node --test .github/scripts/__tests__/agent-delegation-policy.test.js .github/scripts/__tests__/keepalive-loop.test.js
# 242 passed, 0 failed
```

The full keepalive run uses the same temporary regular-file stdin workaround
described in `issue-3989-completion-classification.md`. No assertions or production
code are replaced by that shim. The ordinary isolated Node command still needs
CI verification. `git diff --check` and source/template byte comparison passed.

The native writer reported GitHub API access failure. Its payload was subsequently
published at the committed predecessor above; current delivery is recorded below.

## Exit-zero quota adjudication (r4301075007)

- [x] Verify exit-zero quota handling against the provider/productivity contract.

The classifier intentionally retains quota detection for zero exits: the runner
contract documents providers exiting zero without work. Exit status alone must
not reopen an exhausted provider. Paired source/template regressions cover quota
text at exit zero, explicit productivity overriding that classification, and the
actual Python writer overriding the workflow's two-argument classification when
it records productive work. This includes successful summaries quoting quota/429
text. No classifier change is warranted under this contract.

The full targeted keepalive command above passed with **244 passed, 0 failed**.

## Runner conditional simplification (r4301075014)

- [x] Remove the unreachable second `produced_work is True` condition.

The outer productive branch already handles that case. Remaining unclassified
results become `no_progress` on success or `failed` otherwise; supplied
`rate_limited` and `failed` reasons survive until real productivity overrides them.
Twelve parameterized cases verify persisted reason, terminal status and quota
expiry. The existing Black **26.10.1** dependency pins are unchanged.

```sh
GITHUB_OUTPUT='' python -m pytest tests/scripts/test_runner_lib.py tests/scripts/test_runner_completion_receipts.py -m 'not slow' -q -o addopts=
# 220 passed
```

Clearing `GITHUB_OUTPUT` avoids writing the hosting job's read-only output file.
Both changed Python files pass Black 26.10.1 at line length 100.

The repository-wide formatting gate also passed on all **765 files**:

```sh
PYTHONPATH=/tmp/keepalive-black-runtime BLACK_CACHE_DIR=/tmp/keepalive-black-cache black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
# 765 files would be left unchanged
```

The temporary `sitecustomize.py` replaces only Black's concurrent dispatch with
serial calls to its own `reformat_one`, retaining CLI source discovery, mode,
formatting, safety checks, reporting and exit status. The sandbox blocks Python
3.14's forkserver socket; threaded execution also stalled. No repository file or
Black dependency was changed for this workaround.

## Generated consistency recovery

- [x] Resolve the four reproduced generated-preset/compiler consistency failures.

The preset generator's ownership equality, stale-preset and check-mode tests
failed because `.github/scripts/rate_limit_receipt.js` and
`.github/scripts/rate_limit_receipt.json` were already declared in the manifest
but missing from the generated preset. Regenerating the preset adds exactly those
two paths and changes its shared managed-path count from 241 to 243. The compiler
test expected 255 copy entries instead of 257; it now also explicitly requires
both receipt files. No source ownership, manifest scope or delivery policy changed;
no new sync prerequisite was admitted.

```sh
python scripts/generate_consumer_renovate_ownership.py --check
# up to date
python -m pytest tests/scripts/test_generate_consumer_renovate_ownership.py tests/scripts/test_sync_manifest_compiler.py tests/scripts/test_sync_manifest_docs.py tests/scripts/test_pr_verifier_sync_manifest.py -m 'not slow' -q -o addopts=
# 93 passed
```

Gate38997906960 itself was inaccessible over the GitHub API; the local failures
are exactly three generated-preset tests plus the compiler-count assertion.

Final combined validation after the source and test changes:

```sh
GITHUB_OUTPUT='' NODE_OPTIONS='--require=/tmp/keepalive-test-runtime.cjs --experimental-test-isolation=none' node --test .github/scripts/__tests__/agent-delegation-policy.test.js .github/scripts/__tests__/keepalive-loop.test.js .github/scripts/__tests__/agent_delegation_policy.test.js tests/scripts/test_agent_delegation_policy_intake.js
# 310 passed, 0 failed
GITHUB_OUTPUT='' python -m pytest tests/scripts/test_runner_lib.py tests/scripts/test_runner_completion_receipts.py tests/scripts/test_generate_consumer_renovate_ownership.py tests/scripts/test_sync_manifest_compiler.py tests/scripts/test_sync_manifest_docs.py tests/scripts/test_pr_verifier_sync_manifest.py -m 'not slow' -q -o addopts=
# 313 passed
```

JavaScript syntax checks, source/template byte comparison and `git diff --check`
also passed.

## Current local source-owner verification

The native payload is committed at `3a60cc431d668a52e0690248e04cfcd25b220af4`.
A fresh paginated all-head reservation/completion read and direct inspection of
all four recorded workflow attempts and all their jobs proved them terminal
before this continuation checked out that head. The existing PR remains open,
ready for review and parent-paused for serial ownership.

The earlier pool-state tests did **not** cover r4301075000's exact persisted
receipt case. This continuation filters active `completion.rate_limit_receipts`
in both policy copies before selecting any available agent. A different
provider's later failed completion and an `ok` route export cannot erase a
receipt. Expiry uses the shared completion-time TTL helper; the completion
loader already drops backoffs superseded by measured progress. Paired tests
exercise concrete labels, ranking, exploration, default selection, no available
runner, expiry and progress cleanup. They fail on the inherited source with
`codex != claude` (2 failures), then pass after the fix (2 passes).

For r4301075007, the actual root and consumer callers send classification plus
`--produced-work`, observed head and task snapshots to the Python writer.
`RunnerResult.success` and measured productivity are separate fields. Both
paired real-writer replays confirm productive exit-zero summaries quoting quota
or HTTP 429 persist `progressed` without a quota expiry, while actual unproductive
quota messages retain backoff even at exit zero. No classifier weakening is
warranted. The runner exposes shell process statuses (`PIPESTATUS[0]` for Cursor),
not HTTP status codes; a direct `SystemExit(429)` probe yielded status 173.
The classifier's numeric-429 arm is defensive synthetic-input handling and is
not evidence that a native process can exit 429.

Validation on the corrected source uses `/opt/anaconda3/bin/python3` and the
portable replay's `PYTHON` override. No runtime shim or assertion replacement:

```sh
PYTHON=/opt/anaconda3/bin/python3 GITHUB_OUTPUT='' node --test --test-reporter=junit .github/scripts/__tests__/agent-delegation-policy.test.js .github/scripts/__tests__/keepalive-loop.test.js
# 246 passed
GITHUB_OUTPUT='' /opt/anaconda3/bin/python3 -m pytest tests/scripts/test_runner_lib.py tests/scripts/test_runner_completion_receipts.py tests/scripts/test_generate_consumer_renovate_ownership.py tests/scripts/test_sync_manifest_compiler.py tests/scripts/test_sync_manifest_docs.py tests/scripts/test_pr_verifier_sync_manifest.py -m 'not slow' -q -o addopts=
# 312 passed, 1 skipped (unrelated live manifest issue-reference check lacks token)
```

The four originally failing consistency tests also pass as a separate exact
four-case run (4 passed), in addition to that combined Python run. The adjacent
policy/intake Node suites pass 66 more tests. Black 26.10.1 and Ruff 0.17.1 pass
on `scripts/runner_lib/core.py`, `tests/scripts/test_runner_lib.py` and
`tests/scripts/test_sync_manifest_compiler.py`. The normal ownership preset
`--check`, `validate_template_sync.py` and `validate_template_completeness.py`
all pass.
The deliberate classifier break and restoration use the identical Node command;
the broken run fails the persisted same-evaluate switch assertion, and restoration
passes all 246 tests. JUnit, captured argv and source SHA-256 bindings are stored
under `~/.codex/orchestrator/measurement/issue-3997-review` alongside the actual
receipt pre-fix RED/restored GREEN.

The runner directory is a manifest-managed directory copy, not an exact local
consumer-template mirror; no new mirror is required. Both existing JavaScript
source/template pairs remain byte-identical. No manifest/compiler semantics,
workflow launch path, model settings or consumer deployment changed.

The requested capability advisor was consulted with this task in plain words,
but its shared registry lock failed with `PermissionError` on
`capabilities.json.lock`. Optional capabilities were declined for this bounded
repair, with a proposed decision receipt saved in the measurement directory for
the parent. No shared registry or permission changes were attempted.

Publication and terminal ownership release are recorded separately in the local
terminal receipt. Local tests do not establish hosted CI, provider PASS, source
acceptance, consumer publication or the post-merge label-timeline criteria.
