# PR #4711 regression follow-up — 2026-11-16 UTC

Starting commit: `ec594c0898ee34348159c5b28cb1aad6e59cfb98`.

The progress-review regression omitted `ANTHROPIC_API_KEY`. Adding that key to
the existing in-memory mutation cases reproduced two failures (environment and
script wiring), with ten other Anthropic cases passing. Using the shared
`PROVIDER_KEYS` inventory in the progress-review assertion fixes both cases.

Validation:

```sh
pytest tests/workflows/test_no_api_keys_in_keepalive.py -m 'not slow' -q
# Before changes: 53 passed. After changes: 65 passed, exit 0.
ruff check tests/workflows/test_no_api_keys_in_keepalive.py
# All checks passed.
black --check --line-length 100 tests/workflows/test_no_api_keys_in_keepalive.py
# 1 file would be left unchanged, exit 0.
```

The required repository-wide Black check could not pass in this run. Its default
worker setup raised `PermissionError: Operation not permitted`; a single-worker
retry stalled during source discovery and was interrupted. A verbose retry with
`BLACK_NUM_WORKERS=1 timeout 120s black --check --line-length 100
--exclude '(\.workflows-lib|node_modules)' --verbose .` timed out (exit 124)
during discovery. This does not establish repository-wide formatting success.

The added mutation cases replace the parsed YAML in memory. They do not satisfy
the actual-workflow mutation/restoration acceptance criterion. The protected
Codex workflow was not edited; it still matches the starting commit byte for
byte, SHA-256 `b1c5e9de2a8331cc52d60f0edb3a222ab5b3004a93b8b7c9034deb688e24d7de`.

GitHub reported PR #4711 open, unmerged and ready for review. There is no
delivered merge SHA for this change yet. After delivery, an approved
`agent-high-privilege` run must repeat the named regression, actual-workflow
mutation and exact-byte restoration at that merge SHA, then capture a qualifying
hosted analysis round at the same SHA. This `agent-standard` run cannot mutate
workflow files. No pending acceptance checkbox is completed by these tests.

The GitHub connector rejected adding `needs-human` and posting the blocker
comment: both operations require approval, while this run's approval policy is
`never`. Local staging also failed because `.git` is mounted read-only
(`Unable to create .git/index.lock`). The changes remain uncommitted in the
working tree.

## Receipt regression follow-up — 2026-11-16 UTC

Starting commit: `770db1663fbeb91ebe48c2991cd30b71899bb008`.

Reviewed that commit and its predecessors `ec594c08` and `65659c46` before
continuing. Their verified candidate regression and CLI confinement results
remain separate from the pending delivered-commit and hosted acceptance.
GitHub still reports PR #4711 open, unmerged and ready for review. Its preview
merge commit is not a delivered merge SHA. The first unchecked task therefore
cannot run yet; the actual-workflow mutation also requires an approved
`agent-high-privilege` run.

Added 23 cases to the named API-key regression suite. They execute the exact
Python output-extraction heredoc read from the Codex workflow, using local
analysis JSON. Both API-key variables are independently absent, empty or set to
a noncredential marker. Empty variables must report present; values must never
appear in either output stream. Codex emits the subscription receipt, while a
regex fallback cannot claim subscription authentication. Provider, registry
model, confidence and completed tasks survive JSON extraction, and their job
and reusable-workflow output mappings remain connected.

```sh
pytest tests/workflows/test_no_api_keys_in_keepalive.py -m 'not slow' -q
# Before changes: 65 passed. After changes: 88 passed in 3.30s, exit 0.
black --line-length 100 tests/workflows/test_no_api_keys_in_keepalive.py
# 1 file left unchanged, exit 0.
ruff check tests/workflows/test_no_api_keys_in_keepalive.py
# All checks passed, exit 0.
BLACK_NUM_WORKERS=1 black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
# No output; interrupted with exit 130. Repository-wide formatting is unverified.
```

These local fixture cases do not establish CLI execution, subscription
authentication or hosted acceptance. No pending acceptance checkbox is
completed. The Codex workflow remains byte-identical to the starting commit;
its SHA-256 is still
`b1c5e9de2a8331cc52d60f0edb3a222ab5b3004a93b8b7c9034deb688e24d7de`.

The attempted PR-body reconciliation would reopen the task beginning
"Inspect hosted keepalive Actions logs" because the older hosted run predates
the new receipt. The connector rejected that update, the blocker comment and
the `needs-human` label: approval is required but the run policy is `never`.
Staging the test change failed with `.git/index.lock: Read-only file system`.
No commit was made, and the repository-wide Black gate has not passed.

## Local keepalive round 4

On November 15, 2026 Central time (November 16 UTC), the previous round's
changes were already committed on PR #4711 at
`770db1663fbeb91ebe48c2991cd30b71899bb008`. On that exact head, run the focused
regression with:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/anaconda3/bin/python3 -m pytest tests/workflows/test_no_api_keys_in_keepalive.py
```

The baseline passed all 65 cases (exit 0). Inserting
`OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}` in the real
`.github/workflows/reusable-codex-run.yml` step `llm_analysis.env` caused
`tests/workflows/test_no_api_keys_in_keepalive.py::test_runner_analysis_has_no_api_key_or_second_invocation[codex]`
to fail (exit 1, 64 other cases passed). After exact-byte restoration against
the commit blob, all 65 cases passed again (exit 0). The original and restored
SHA-256 was `b1c5e9de2a8331cc52d60f0edb3a222ab5b3004a93b8b7c9034deb688e24d7de`.

Both slow compatibility jobs on `770db166` failed version freshness because
main still pinned Ruff 0.17.4 and Coverage 7.17.2. Python Tests propagated the
compatibility failure. The sole writer's [version update PR #4705](https://github.com/stranske/Workflows/pull/4705)
was open and carried Ruff 0.17.5 and Coverage 7.17.3. Once that update reaches
main, sync the branch and check compatibility on the refreshed head.
[Selftest CI](https://github.com/stranske/Workflows/actions/runs/43809825675)

PR #4711 was open and ready for review at this check. Repeat the actual-workflow
regression on the delivered merge commit and obtain a hosted keepalive receipt
on that commit for the registry model, JSON-derived outputs, subscription
authentication, and both API-key presence booleans.

## Inherited-environment regression follow-up — 2026-11-16 UTC

Starting commit: `d60c391b4a7fcc2608507b03ad4a203c8de8419d`.

Reviewed the five preceding commits and the current PR body before editing.
PR #4711 remains open, unmerged and ready for review. No delivered merge SHA
exists yet, so the first unchecked task remains blocked. The task beginning
"Inspect hosted keepalive Actions logs" should also be reopened: the recorded
hosted run predates the new receipt. Candidate CLI confinement and mutation
proof remain separate from delivered-commit and hosted acceptance. No pending
acceptance checkbox is completed by this follow-up.

The named API-key regression checked step environments but missed inherited
workflow and runner-job environments. Extended the existing in-memory mutation
matrix to both scopes, then added the missing assertions for all five runners
and progress review. The new cases initially reported 44 failures and four
passes; progress-review job environments were already covered by its whole-job
assertion. These cases use parsed YAML only, without editing workflow files.

```sh
pytest tests/workflows/test_no_api_keys_in_keepalive.py -m 'not slow' -q
# Starting commit: 88 passed in 3.85s, exit 0.
pytest tests/workflows/test_no_api_keys_in_keepalive.py -m 'not slow' \
  -k 'workflow_gate_rejects and (workflow-env or job-env)' -q --tb=no
# Added mutation cases before the fix: 44 failed, 4 passed, 88 deselected; exit 1.
pytest tests/workflows/test_no_api_keys_in_keepalive.py -m 'not slow' -q
# After the fix: 136 passed in 5.80s, exit 0.
black --line-length 100 tests/workflows/test_no_api_keys_in_keepalive.py
# 1 file left unchanged, exit 0.
ruff check tests/workflows/test_no_api_keys_in_keepalive.py
# All checks passed, exit 0.
git diff --check
# Exit 0.
BLACK_NUM_WORKERS=1 timeout 120s black --check --line-length 100 \
  --exclude '(\.workflows-lib|node_modules)' .
# Exit 124: "Aborted!"; 1019 files would be left unchanged.
```

The repository-wide Black command did not exit successfully, so its mandatory
pre-commit gate remains unverified. No commit or push was attempted.

All 134 tracked workflow files still match HEAD byte for byte. The Codex
workflow SHA-256 remains
`b1c5e9de2a8331cc52d60f0edb3a222ab5b3004a93b8b7c9034deb688e24d7de`.
This is preservation evidence, not the required actual-workflow mutation proof.

The connector rejected the PR-body reconciliation, `needs-human` label and
blocker comment because approval is required and this run's policy is `never`.
`findmnt -T .git -n -o TARGET,OPTIONS` confirms the repository's `.git` mount is
read-only, preventing the requested commit. An approved high-privilege run is
still needed for the delivered-commit workflow mutation, followed by a hosted
analysis round on the delivered SHA.

## Hosted evidence consistency checker — 2026-11-16 UTC

Starting commit: `6fcd39fdcc6d89687303a656716a41440c90bb6a`.
Reviewed the recent commits and PR body before continuing. PR #4711 is still
open, unmerged and ready for review. Its preview merge SHA is not delivery.
The first unchecked task remains blocked on merge and an approved workflow
mutation run. No outstanding task or acceptance criterion is completed here.
The checked hosted-inspection and reconciliation tasks should be reopened.

Re-read the native log for job `133074122262` in hosted run `43798812323`.
Its `Uses:` line resolves the reusable Codex workflow to
`3be719f4c750ea1057e40c7287d3f74bbf999508`. It contains no
`subscription-auth=chatgpt` receipt and warns that `llm-completed-tasks` was
suppressed as a possible secret. A downstream default of `[]` therefore cannot
by itself prove that the completed-task output survived delivery.

Added the source-local operator tool
`tools/validate_subscription_analysis_evidence.py` and its regression tests.
The tool compares the runner's resolved reusable-workflow SHA, the runtime
subscription receipt, the delivered registry model, the existing analysis JSON,
and the values actually received by summary consumers. It rejects missing,
duplicated or conflicting receipts, command echoes presented as receipts,
unterminated Actions groups, invalid confidence, and missing or suppressed
summary outputs. Diagnostics never reproduce input contents. The tool does not
perform inference, change workflow behavior, or authenticate supplied evidence.
It is not a distributed consumer file, so no template or manifest changes apply.

Once evidence is available, independently verify delivery and that all inputs
come from the same hosted round. Save the registry from the delivered commit,
the complete runner log, the analysis step log, the existing analysis JSON, and
a JSON object containing the actual received workflow output strings
(`llm-analysis-run`, `llm-provider`, `llm-model`, `llm-confidence`, and
`llm-completed-tasks`). Do not reconstruct outputs from expected values or
substitute fixtures. Run:

```sh
python tools/validate_subscription_analysis_evidence.py \
  --delivered-sha "$DELIVERED_SHA" \
  --runner-log runner.log --analysis-log analysis-step.log \
  --analysis-json analysis.json --summary-json received-summary-outputs.json \
  --registry delivered-registry.yml
```

Exit 0 means the supplied evidence is consistent. It does not establish hosted
provenance, the absence of every API request, or effective CLI confinement.
Those remain separate checks. No delivered-SHA or qualifying new hosted input
is available in this run, so this command has not been run against such inputs.

The connector rejected the PR-body reconciliation, `needs-human` label and
blocker comment because they require approval and this run's policy is `never`.
The `.git` mount is read-only, independently preventing the requested commit.

Local verification:

```sh
pytest tests/workflows/test_no_api_keys_in_keepalive.py -m 'not slow' -q
# Exact starting commit: 136 passed in 7.31s, exit 0.
pytest tests/tools/test_validate_subscription_analysis_evidence.py \
  tests/workflows/test_no_api_keys_in_keepalive.py -m 'not slow' -q
# Final implementation: 190 passed in 7.27s, exit 0.
black --line-length 100 tools/validate_subscription_analysis_evidence.py
black --line-length 100 tests/tools/test_validate_subscription_analysis_evidence.py
black --check --line-length 100 tools/validate_subscription_analysis_evidence.py
black --check --line-length 100 tests/tools/test_validate_subscription_analysis_evidence.py
# All four single-file commands exit 0.
ruff check tools/validate_subscription_analysis_evidence.py \
  tests/tools/test_validate_subscription_analysis_evidence.py
# All checks passed, exit 0.
git diff --check
# Exit 0.
```

The final test count includes 54 validator fixture cases and 136 named workflow
regressions. It is not hosted acceptance evidence. All 134 tracked workflow
files match HEAD byte for byte; the Codex workflow SHA-256 remains
`b1c5e9de2a8331cc52d60f0edb3a222ab5b3004a93b8b7c9034deb688e24d7de`.
The final GitHub readback still reports PR #4711 open with `isDraft=false`.

The mandatory repository-wide formatting command did not pass:

```sh
BLACK_NUM_WORKERS=1 timeout 90s black --check --line-length 100 \
  --exclude '(\.workflows-lib|node_modules)' .
# Exit 124: "Aborted!"; 1021 files would be left unchanged.
```

A preceding unbounded single-worker invocation was interrupted without output
(exit 130). Single-file formatting passed, but the global gate remains
unverified. No commit was attempted because that gate has not passed and `.git`
is mounted read-only. The tool, tests and this evidence update remain local and
uncommitted.

## Local keepalive round 6 — 2026-11-16 Central

On candidate `c69aed020bb455af0d303aae32db2ad12b651226`, the local worktree
allowed the actual workflow mutation and restoration. Verification commands:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/anaconda3/bin/python3 -m pytest \
  tests/workflows/test_no_api_keys_in_keepalive.py
WORKFLOWS_PINNED_CODEX_BIN=/absolute/path/to/codex \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /opt/anaconda3/bin/python3 -m pytest \
  tests/workflows/test_subscription_llm_pinned_cli_canary.py
```

- The API-key test passed all 136 cases. Adding
  `OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}` to `llm_analysis.env` in
  `.github/workflows/reusable-codex-run.yml` produced exit 1 and the named failure
  `test_runner_analysis_has_no_api_key_or_second_invocation[codex]`, with 135
  other cases passing. Restored bytes matched the committed blob at SHA-256
  `b1c5e9de2a8331cc52d60f0edb3a222ab5b3004a93b8b7c9034deb688e24d7de`.
  The rerun passed all 136 cases.
- Codex CLI 0.160.0 passed all 22 real-CLI confinement cases for both transports
  in 19.58 seconds, with zero skips or expected failures.
- Both slow compatibility jobs on this candidate failed Ruff and Coverage
  freshness, and Python Tests propagated those failures. The designated
  updater's [PR #4705](https://github.com/stranske/Workflows/pull/4705) was
  still open and contained Ruff 0.17.5 and Coverage 7.17.3. Sync the branch
  after that update lands and recheck compatibility.
  [Exact-head Selftest CI](https://github.com/stranske/Workflows/actions/runs/43813481439)
- The Gate run cited in the round input was cancelled on the previous head
  `6fcd39fdcc6d89687303a656716a41440c90bb6a` while its Python logs summary
  was pending. The candidate had a separate Gate run.
  [Previous Gate](https://github.com/stranske/Workflows/actions/runs/43812480191)
  [Candidate Gate](https://github.com/stranske/Workflows/actions/runs/43813481485)
- The earlier hosted job resolved the runner to
  `3be719f4c750ea1057e40c7287d3f74bbf999508` and logged suppression of the
  `llm-completed-tasks` output. The downstream default `[]` cannot establish
  delivery of that output. PR #4711 was open and ready for review with no
  delivered merge SHA, so the delivered-SHA mutation and hosted acceptance
  remain pending.
  [Earlier hosted job](https://github.com/stranske/Workflows/actions/runs/43798812323/job/133074122262)

## Suppressed-output validation follow-up — 2026-11-16 UTC

Starting commit: `aae039e21bd26a3095564bfc17ca0bef0ded5637`.
GitHub reports PR #4711 open, unmerged and ready for review. There is no delivered
merge SHA; its preview merge commit is not delivery evidence. The first unchecked
task therefore remains blocked. This standard-permission run also cannot perform
the required actual-workflow mutation. After delivery, an approved
`agent-high-privilege` run must repeat that proof on the delivered commit and
capture the qualifying hosted analysis at the same commit.

Read back the earlier Codex job's logs and confirmed the runtime warning:
`Skip output 'llm-completed-tasks' since it may contain secret.` The offline
validator previously accepted supplied summary outputs despite this warning,
including a downstream `[]` fallback equal to the analysis's empty task list.
Twenty new negative cases reproduced that false acceptance before the fix.
The validator now rejects suppression of any of its five required outputs,
including warnings inside the runner's output groups. Two additional cases
preserve acceptance for unrelated output warnings and shell command echoes.

```sh
pytest tests/tools/test_validate_subscription_analysis_evidence.py \
  tests/workflows/test_no_api_keys_in_keepalive.py -m 'not slow' -q
# Before changes: 190 passed in 7.15s, exit 0.
# New suppression cases before fix: 20 failed, 56 passed, exit 1.
# After fix: 212 passed in 6.96s, exit 0.
BLACK_NUM_WORKERS=1 black --line-length 100 tools/validate_subscription_analysis_evidence.py
BLACK_NUM_WORKERS=1 black --line-length 100 tests/tools/test_validate_subscription_analysis_evidence.py
BLACK_NUM_WORKERS=1 black --check --line-length 100 tools/validate_subscription_analysis_evidence.py
BLACK_NUM_WORKERS=1 black --check --line-length 100 tests/tools/test_validate_subscription_analysis_evidence.py
ruff check tools/validate_subscription_analysis_evidence.py tests/tools/test_validate_subscription_analysis_evidence.py
# All file-level formatting and lint checks passed.
git diff --check
# Exit 0.
```

These fixture regressions do not establish delivered-SHA or hosted acceptance;
no pending checkbox is completed. The earlier hosted task's checked state should
be reopened because the qualifying new receipt is still missing. The connector
rejected that correction, the blocker comment and `needs-human` labeling because
approval is required and this run's approval policy is `never`.

All 134 tracked workflow files remain byte-identical to HEAD. The Codex workflow
SHA-256 remains `b1c5e9de2a8331cc52d60f0edb3a222ab5b3004a93b8b7c9034deb688e24d7de`.
The filesystem reports `.git` read-only, preventing the requested commit.

The mandatory repository-wide formatting check also remains unverified:

```sh
BLACK_NUM_WORKERS=1 timeout 120s black --check --line-length 100 \
  --exclude '(\.workflows-lib|node_modules)' .
# Exit 124: "Aborted!"; 1021 files would be left unchanged.
```

The initial multi-file formatting invocation failed with `PermissionError`
when Black started its worker process; the file-level single-worker commands
above succeeded. No commit was attempted because the global gate did not pass
and Git metadata is read-only. The implementation, tests and evidence remain
uncommitted in the working tree. Final GitHub readback still reports PR #4711
open with `isDraft=false`.

## Local keepalive round 7 — 2026-11-16 Central

- On `e7a534217b2bc4acfd3cd0a81fb8e44037908e73`, slow compatibility on
  Python 3.13 and 3.14 failed on Ruff 0.17.4 and Coverage 7.17.2. The Python
  Tests rollup reported the compatibility failure. Main still carried those
  pins at `3be719f4c750ea1057e40c7287d3f74bbf999508`. The designated
  updater's [PR #4705](https://github.com/stranske/Workflows/pull/4705) was
  open with Ruff 0.17.5 and Coverage 7.17.3. Compatibility can be rechecked
  after the updater lands on main and this branch incorporates it.
  [Exact-head Selftest CI](https://github.com/stranske/Workflows/actions/runs/43815280385)
- The cited Gate run was cancelled on `aae039e21bd26a3095564bfc17ca0bef0ded5637`.
  The run on `e7a534217b2bc4acfd3cd0a81fb8e44037908e73` was still in
  progress at readback.
  [Cancelled Gate](https://github.com/stranske/Workflows/actions/runs/43814263372)
  [Exact-head Gate](https://github.com/stranske/Workflows/actions/runs/43815280355)
- The pinned Codex CLI 0.160.0 job on `e7a534217b2bc4acfd3cd0a81fb8e44037908e73`
  passed all 22 tests with zero skips, covering the source and consumer
  transports. The runnable commands are in the round 6 section.
  [Exact-head CLI canary](https://github.com/stranske/Workflows/actions/runs/43815280268/job/133125815115)
- PR #4711 is open and ready for review. The delivered merge SHA, the
  API-key mutation proof at that SHA, and the qualifying hosted analysis
  receipt are pending. The earlier hosted job suppressed the completed-task
  output, leaving receipt of that output unverified.
  [Earlier hosted job](https://github.com/stranske/Workflows/actions/runs/43798812323/job/133074122262)

## Reusable-interface regression follow-up — 2026-11-16 UTC

Starting commit: `091c403a39f278570b038f227ef75ce60cc61704`.
GitHub still reports PR #4711 open, unmerged and ready for review. Its preview
merge SHA is not a delivered commit. The first unchecked task remains blocked
on delivery and an approved actual-workflow mutation run. The next hosted task
also requires that delivered SHA. No acceptance checkbox is completed here.

Added 15 in-memory mutation cases to the named API-key regression. Each of the
five reusable runner interfaces is tested with each of the three prohibited
provider-key declarations, without wiring the declaration into a step. These
exercise the existing workflow-call interface assertion independently of the
step and inherited environment assertions. They do not constitute the required
actual-workflow mutation/restoration proof or establish hosted authentication.

```sh
pytest tests/workflows/test_no_api_keys_in_keepalive.py \
  tests/tools/test_validate_subscription_analysis_evidence.py -m 'not slow' -q
# Starting commit: 212 passed in 8.44s, exit 0.
pytest tests/workflows/test_no_api_keys_in_keepalive.py -m 'not slow' -q
# Updated regression: 151 passed in 9.30s, exit 0.
black --line-length 100 tests/workflows/test_no_api_keys_in_keepalive.py
black --check --line-length 100 tests/workflows/test_no_api_keys_in_keepalive.py
ruff check tests/workflows/test_no_api_keys_in_keepalive.py
git diff --check
# All file-level checks passed.
```

Tracked workflows remain unchanged against HEAD; the Codex workflow SHA-256 is
`b1c5e9de2a8331cc52d60f0edb3a222ab5b3004a93b8b7c9034deb688e24d7de`.
The GitHub connector refused the blocker comment and `needs-human` label because
both require approval and this run's approval policy is `never`. The `.git`
mount is read-only, preventing the requested commit. After delivery, an approved
`agent-high-privilege` run must repeat the baseline/mutation/restoration sequence
and capture a qualifying hosted analysis round at the delivered SHA. The checked
hosted-inspection and reconciliation tasks still need reopening because the
recorded hosted run predates the new receipt and suppressed completed-task output.


The mandatory repository-wide Black check did not pass:

```sh
BLACK_NUM_WORKERS=1 timeout 120s black --check --line-length 100 \
  --exclude '(\.workflows-lib|node_modules)' .
# Exit 124: "Aborted!"; 1021 files would be left unchanged.
```

The timeout does not establish formatting success. No commit or push was
attempted because this gate remains unverified and Git metadata is read-only.
The test changes and this evidence update remain uncommitted.

## Analysis log group validation — 2026-11-16 UTC

Starting commit: `47480511b2f916b8c5929604548a0e5e0afac9c1`.
GitHub reports PR #4711 open, unmerged and ready for review. No delivered merge
SHA exists yet; the preview merge SHA cannot satisfy delivery. The first
unchecked task also requires an approved `agent-high-privilege` run for the
actual-workflow mutation. No acceptance checkbox is completed here.

The offline hosted-evidence validator used a boolean for Actions log groups.
Closing an inner group let script text inside the outer group count as runtime
authentication or API-key presence receipts. It also accepted an unclosed outer
group and unmatched end markers. Eight new regression cases failed before the
fix. Tracking group depth now excludes all grouped text, rejects unbalanced
markers and preserves runtime receipts following balanced nested groups.

```sh
pytest tests/workflows/test_no_api_keys_in_keepalive.py \
  tests/tools/test_validate_subscription_analysis_evidence.py -m 'not slow' -q
# Exact starting commit: 227 passed in 7.96s, exit 0.
# With the fix and eight new cases: 235 passed in 8.10s, exit 0.
black --line-length 100 tools/validate_subscription_analysis_evidence.py
black --line-length 100 tests/tools/test_validate_subscription_analysis_evidence.py
black --check --line-length 100 tools/validate_subscription_analysis_evidence.py
black --check --line-length 100 tests/tools/test_validate_subscription_analysis_evidence.py
ruff check tools/validate_subscription_analysis_evidence.py \
  tests/tools/test_validate_subscription_analysis_evidence.py
git diff --check
# All file-level checks passed.
```

These fixture tests do not establish hosted provenance, subscription
authentication or actual-workflow mutation/restoration. All 134 tracked workflow
files remain byte-identical to HEAD. The Codex workflow SHA-256 remains
`b1c5e9de2a8331cc52d60f0edb3a222ab5b3004a93b8b7c9034deb688e24d7de`.

The connector rejected the `needs-human` label and blocker comment because
approval is required while this run's policy is `never`. Git metadata is mounted
read-only, independently preventing the requested commit. The checked hosted
inspection and reconciliation tasks still need reopening; the old hosted run
predates the new receipt and suppressed completed-task output.

The mandatory repository-wide Black gate did not exit successfully:

```sh
BLACK_NUM_WORKERS=1 timeout 120s black --check --line-length 100 \
  --exclude '(\.workflows-lib|node_modules)' .
# Exit 124: "Aborted!"; 1021 files would be left unchanged.
```

The default multi-file formatter first failed with a sandbox `PermissionError`;
the single-file formatters succeeded. The global timeout does not establish a
passing gate. No commit or push was attempted. The source fix, tests and this
evidence update remain uncommitted.

## Local keepalive round 8 — 2026-11-16 Central

On `3c8ae57a44a056da0605a0577def2c0b8a85172b`, the Python 3.13 and
3.14 slow compatibility jobs both rejected Ruff 0.17.4 and Coverage 7.17.2.
Python Tests propagated that failure. `main` still carried those versions at
`3be719f4c750ea1057e40c7287d3f74bbf999508`. The designated updater's
[PR #4705](https://github.com/stranske/Workflows/pull/4705) was open at
`2011b8629271ade204acb7cb1c34c9508f98991c`, with Ruff 0.17.5 and Coverage
7.17.3 and passing slow compatibility on both Python versions. Once those pins
reach `main`, sync this branch and check the three jobs on the refreshed head.
[Failing Selftest run](https://github.com/stranske/Workflows/actions/runs/43818584224)

The earlier hosted job used the runner at `3be719f4c750ea1057e40c7287d3f74bbf999508`
and explicitly reported that `llm-completed-tasks` was suppressed as a possible
secret. The summary fallback `[]` cannot establish receipt. T6 requires a
hosted round after delivery with the runtime subscription and API-key presence
receipts and all four analysis outputs. A1 also requires the actual-workflow
mutation and restoration sequence on that delivered SHA.
[Earlier hosted job](https://github.com/stranske/Workflows/actions/runs/43798812323/job/133074122262)

## Runner revision consistency — 2026-11-16 UTC

Starting commit: `07834b2256aa706a16086341e30de02f0b03ea35`.
Reviewed the recent commits and current PR body before editing. PR #4711 is
open, unmerged and ready for review; there is no delivered merge SHA. The first
unchecked task remains blocked on delivery and approval for the actual-workflow
mutation. The checked hosted-inspection task should be reopened: the older
hosted round predates the receipt and suppressed completed-task output. No
remaining acceptance checkbox is completed here.

The offline evidence validator accepted a resolved workflow revision copied
inside an Actions script-echo group. Grouped script text could also make a real
runtime revision appear ambiguous. Seven new cases reproduced these failures
and acceptance of unbalanced runner-log groups. Revision extraction now uses
the existing runtime-line filter; output-suppression warnings remain checked
inside groups. The complete older native runner log has balanced groups and
one ungrouped resolved-workflow line, so that format remains supported. This
check of log structure does not establish the pending hosted acceptance.

```sh
pytest tests/workflows/test_no_api_keys_in_keepalive.py \
  tests/tools/test_validate_subscription_analysis_evidence.py -m 'not slow' -q
# Starting commit: 235 passed in 8.09s, exit 0.
# With the fix and seven new cases: 242 passed in 8.10s, exit 0.
pytest tests/tools/test_validate_subscription_analysis_evidence.py \
  -m 'not slow' -k 'workflow_revision_evidence or runtime_workflow_revision or runner_log_groups' \
  -q --tb=short
# Before the source fix: 7 failed, 1 passed, 83 deselected; exit 1.
black --line-length 100 tools/validate_subscription_analysis_evidence.py
black --line-length 100 tests/tools/test_validate_subscription_analysis_evidence.py
black --check --line-length 100 tools/validate_subscription_analysis_evidence.py
black --check --line-length 100 tests/tools/test_validate_subscription_analysis_evidence.py
ruff check tools/validate_subscription_analysis_evidence.py \
  tests/tools/test_validate_subscription_analysis_evidence.py
git diff --check
# All file-level checks passed.
```

All 134 protected workflows remain byte-identical to HEAD. The Codex workflow
SHA-256 remains `b1c5e9de2a8331cc52d60f0edb3a222ab5b3004a93b8b7c9034deb688e24d7de`.
No actual-workflow mutation was performed in this agent-standard run.

Automatic approval review rejected the PR-body correction, needs-human label
and blocker comment because these operations require approval and the run's
policy is never. The repository's Git metadata is mounted read-only,
independently preventing the requested source commit. The changes remain in
the working tree for the authorized runner to commit after the required Black
gate passes.

The mandatory repository-wide formatting gate did not pass:

```sh
BLACK_NUM_WORKERS=1 timeout 120s black --check --line-length 100 \
  --exclude '(\.workflows-lib|node_modules)' .
# Exit 124: "Aborted!"; 1021 files would be left unchanged.
```

The unchanged-file count does not establish a successful exit. The initial
multi-file formatter hit a sandbox PermissionError; formatting and checking
each changed Python file separately succeeded. No commit or push was attempted.

## SHA-only runner revision support — 2026-11-16 UTC

Starting commit: `efc65e0970bb5d744a9f02745e482b4808678a22`.
Reviewed the recent commits and current PR body before editing. PR #4711 is
open, unmerged and ready for review. There is no delivered merge SHA, so the
first unchecked task remains blocked on delivery and an approved workflow
mutation run. The checked hosted-inspection and reconciliation tasks should
be reopened: the older hosted round predates the receipt and suppressed
completed-task output. No outstanding acceptance checkbox is completed here.

The evidence validator rejected a SHA-only `Uses: <workflow>@<sha>` line and
ignored duplicate or conflicting revisions when the two reference formats
were mixed. Twelve added cases cover that format, mixed-format ambiguity,
malformed references and grouped script text. Three failed before the fix.
Both accepted formats now require a complete SHA and use the existing runtime
line filter; malformed parenthesis pairs remain invalid. These fixture cases
do not establish hosted provenance, delivery, authentication or CLI confinement.

```sh
pytest tests/tools/test_validate_subscription_analysis_evidence.py \
  -m 'not slow' -k 'sha_only or across_runner_formats or malformed_workflow_reference' \
  -q --tb=short
# Before the source fix: 3 failed, 9 passed, 91 deselected; exit 1.
pytest tests/workflows/test_no_api_keys_in_keepalive.py \
  tests/tools/test_validate_subscription_analysis_evidence.py -m 'not slow' -q
# Exact starting commit: 242 passed in 10.98s, exit 0.
# Final implementation: 254 passed in 10.93s, exit 0.
black --line-length 100 tools/validate_subscription_analysis_evidence.py
black --line-length 100 tests/tools/test_validate_subscription_analysis_evidence.py
black --check --line-length 100 tools/validate_subscription_analysis_evidence.py
black --check --line-length 100 tests/tools/test_validate_subscription_analysis_evidence.py
ruff check tools/validate_subscription_analysis_evidence.py \
  tests/tools/test_validate_subscription_analysis_evidence.py
git diff --check
# All file-level checks passed.
```

All 134 protected workflows remain byte-identical to HEAD. The Codex workflow
SHA-256 remains `b1c5e9de2a8331cc52d60f0edb3a222ab5b3004a93b8b7c9034deb688e24d7de`.
No actual-workflow mutation was performed in this agent-standard run.

Automatic approval review rejected the PR-body checkbox correction,
`needs-human` label and blocker comment because those actions require approval
while the run policy is `never`. Git metadata is mounted read-only, preventing
the requested commit. The source fix, tests and this evidence remain local.

The mandatory repository-wide Black check timed out:

```sh
BLACK_NUM_WORKERS=1 timeout 120s black --check --line-length 100 \
  --exclude '(\.workflows-lib|node_modules)' .
# Exit 124: "Aborted!"; 1021 files would be left unchanged.
```

The unchanged-file count does not establish a passing formatting gate. No
commit or push was attempted. Final PR readback reports open, `draft=false`,
unmerged, with head `efc65e0970bb5d744a9f02745e482b4808678a22`.

## Local keepalive round 9 — 2026-11-16 Central

GitHub reported no named failure on candidate
`1537f8d6f64315f526dfb2fb2854635f35d528eb`. Selftest CI reported success for
Python Tests and slow compatibility on Python 3.13 and 3.14. This branch
incorporates `main` at `d3e915ae8365a017ff922dcf467927a036af62ee`, including
the designated updater's merged PR #4705.
[Candidate Selftest CI](https://github.com/stranske/Workflows/actions/runs/43822144429)

The pinned Codex CLI 0.160.0 canary on the starting candidate passed all 22
cases across the source and consumer transports. Use the canary command in
round 6. See the PR body for the API-key mutation and restoration receipt on
the updated candidate.
[Candidate CLI canary](https://github.com/stranske/Workflows/actions/runs/43822144248/job/133147447029)

PR #4711 had no merge commit at this check. The earlier hosted job suppressed
`llm-completed-tasks` as a possible secret. T6 and A3–A5 still require a
hosted keepalive round running the delivered revision. A1 still requires the
API-key mutation and restoration sequence on the delivered SHA.
[Earlier hosted job](https://github.com/stranske/Workflows/actions/runs/43798812323/job/133074122262)

## Ambiguous JSON evidence follow-up — 2026-11-16 UTC

Starting commit: `071cf193fa0553923b346edc26ee8188a44efa89`.
PR #4711 remains open, unmerged and ready for review (`draft=false`). Its preview
merge SHA is not a delivered commit. The first unchecked task remains blocked;
no outstanding task or acceptance criterion is completed by this follow-up.

Re-read native hosted job `133074122262` in run `43798812323`. Its `Uses:` line
resolves the reusable Codex workflow to
`3be719f4c750ea1057e40c7287d3f74bbf999508`, it has no
`subscription-auth=chatgpt` receipt, and it warns that `llm-completed-tasks`
was suppressed. It cannot establish the pending hosted acceptance. The candidate
registry resolves `subscription_analysis.codex.execution_profile=codex-extract`
to `gpt-6-luna`; this local lookup is not an observation of a hosted model.

The offline evidence checker silently retained the last duplicate JSON field.
Conflicting provider, model, confidence, task or analysis-run values could
therefore disappear before validation. Eighteen CLI-level regressions reproduced
false acceptance for duplicate fields in the analysis and received-summary JSON.
The checker now rejects both identical and conflicting duplicates without
printing input contents. These fixture tests do not establish hosted provenance,
subscription authentication, delivery or CLI confinement.

```sh
pytest tests/tools/test_validate_subscription_analysis_evidence.py \
  tests/workflows/test_no_api_keys_in_keepalive.py -m 'not slow' -q
# Exact starting commit: 254 passed in 7.93s, exit 0.
pytest tests/tools/test_validate_subscription_analysis_evidence.py \
  -m 'not slow' -k duplicate_json_fields -q --tb=short
# Added cases before source fix: 18 failed, 103 deselected, exit 1.
pytest tests/tools/test_validate_subscription_analysis_evidence.py \
  tests/workflows/test_no_api_keys_in_keepalive.py -m 'not slow' -q
# After fix: 272 passed in 7.87s, exit 0.
black --line-length 100 tools/validate_subscription_analysis_evidence.py
black --line-length 100 tests/tools/test_validate_subscription_analysis_evidence.py
ruff check tools/validate_subscription_analysis_evidence.py \
  tests/tools/test_validate_subscription_analysis_evidence.py
git diff --check
# All single-file formatting, lint and whitespace checks passed.
```

All 134 tracked workflows remain byte-identical to HEAD. The Codex workflow
SHA-256 remains `b1c5e9de2a8331cc52d60f0edb3a222ab5b3004a93b8b7c9034deb688e24d7de`.
The delivered-SHA actual-workflow mutation still requires an approved
`agent-high-privilege` run after merge, followed by a qualifying hosted round
at that revision. No workflow mutation was attempted under standard permissions.

The connector rejected the `needs-human` label and blocker comment because they
require approval while this run's approval policy is `never`. Git metadata is
mounted read-only, preventing the requested commit.

The mandatory repository-wide formatting gate did not pass:

```sh
BLACK_NUM_WORKERS=1 timeout 120s black --check --line-length 100 \
  --exclude '(\.workflows-lib|node_modules)' .
# Exit 124: "Aborted!"; 1021 files would be left unchanged.
```

An initial two-file Black invocation failed because process-worker startup
raised `PermissionError: Operation not permitted`. Formatting and checking the
two files individually passed. The repository-wide unchanged-file count does
not establish an exit-0 formatting check. No commit or push was attempted;
the source fix, regressions and this evidence remain uncommitted.

## Action-input regression follow-up — 2026-11-16 UTC

Starting commit: `6ede5597e222185cec73773fdd3f659a6c9119a2`.
GitHub reports PR #4711 open, unmerged and ready for review. There is still no
delivered merge SHA, so the first unchecked task remains blocked. The actual
workflow mutation also requires an approved `agent-high-privilege` run.

The named API-key gate scanned step environments and shell scripts but omitted
action inputs. Added in-memory mutations to existing `with.script` inputs,
exporting each prohibited variable through `core.exportVariable`. Before the
fix, 20 cases failed because the five runner gates accepted those mutations;
four progress-review cases already rejected them. The runner gate now scans
action inputs too, and all 24 new cases pass. These parsed-YAML mutations do
not establish actual-workflow mutation/restoration or hosted acceptance.

```sh
pytest tests/workflows/test_no_api_keys_in_keepalive.py -m 'not slow' -q
# Exact starting commit: 151 passed in 5.40s, exit 0.
pytest tests/workflows/test_no_api_keys_in_keepalive.py \
  -m 'not slow' -k action-script -q --tb=short
# New cases before the gate fix: 20 failed, 4 passed, 151 deselected; exit 1.
pytest tests/workflows/test_no_api_keys_in_keepalive.py \
  tests/tools/test_validate_subscription_analysis_evidence.py -m 'not slow' -q
# After the fix: 296 passed in 6.46s, exit 0.
black --line-length 100 tests/workflows/test_no_api_keys_in_keepalive.py
ruff check tests/workflows/test_no_api_keys_in_keepalive.py
git diff --check
# File formatting, lint and whitespace checks passed.
```

All 134 tracked workflows remain unchanged against HEAD. The Codex workflow
matches the committed bytes with SHA-256
`b1c5e9de2a8331cc52d60f0edb3a222ab5b3004a93b8b7c9034deb688e24d7de`.
No pending task or acceptance checkbox is completed. After delivery, repeat the
actual-workflow mutation/restoration proof and capture a qualifying hosted round
at that delivered SHA. The older hosted round cannot supply the new receipt.

The connector rejected both the `needs-human` label and blocker comment because
approval is required while this run's policy is `never`. The `.git` mount is
read-only, independently preventing the requested commit.

The required repository-wide Black check also failed to exit successfully:

```sh
BLACK_NUM_WORKERS=1 timeout 120s black --check --line-length 100 \
  --exclude '(\.workflows-lib|node_modules)' .
# Exit 124: "Aborted!"; 1021 files would be left unchanged.
```

The changed-file Black check passes, but that does not establish the global
formatting gate. No commit or push was attempted. Final PR readback confirms
open, `draft=false`, unmerged, at the starting head above.

## Runner/analysis receipt consistency follow-up — 2026-11-16 UTC

Starting commit: `c6f5d3899def7e419f2e17ffd18d6d4b5f6c2ce0`.
GitHub still reports PR #4711 open, unmerged and ready for review at this head.
The first unchecked task remains blocked: no delivered merge SHA exists, and
the actual-workflow mutation requires an explicitly approved
`agent-high-privilege` run. No pending acceptance checkbox is completed here.

The existing hosted-evidence validator accepted valid-looking receipts in the
analysis-step log even when the supplied full runner log omitted or contradicted
them. Sixteen fixture regressions reproduced that false acceptance before the
fix. The validator now matches all four runtime receipts, including their
original timestamps, between the two logs. Missing, conflicting, duplicated,
echoed and other-round receipts are rejected. A CLI regression verifies that
the failure does not reproduce log contents. Preserve the original analysis-step
timestamps when preparing inputs for the existing validator command; CRLF
runner logs remain supported. This is a source-local evidence tool, with no
consumer template or sync-manifest change.

```sh
pytest tests/workflows/test_no_api_keys_in_keepalive.py \
  tests/tools/test_validate_subscription_analysis_evidence.py -m 'not slow' -q
# Exact starting commit: 296 passed in 7.69s, exit 0.
pytest tests/tools/test_validate_subscription_analysis_evidence.py \
  -m 'not slow' -k analysis_receipts_must_appear -q --tb=short
# First 16 added cases before source fix: 16 failed, 122 deselected, exit 1.
pytest tests/tools/test_validate_subscription_analysis_evidence.py \
  tests/workflows/test_no_api_keys_in_keepalive.py -m 'not slow' -q
# Final implementation: 322 passed in 7.76s, exit 0.
ruff check tools/validate_subscription_analysis_evidence.py \
  tests/tools/test_validate_subscription_analysis_evidence.py
git diff --check
# Lint and whitespace checks pass.
```

Re-read the complete earlier hosted job `133074122262` in run `43798812323`.
Its resolved reusable workflow SHA remains
`3be719f4c750ea1057e40c7287d3f74bbf999508`; no runtime subscription-auth or
API-key-absence receipts appear. It reports suppression of
`llm-completed-tasks`. That job cannot satisfy the new hosted acceptance, and
fixture regressions cannot substitute for an actual qualifying round.

All 134 tracked workflows remain byte-identical to HEAD. The Codex workflow
SHA-256 remains `b1c5e9de2a8331cc52d60f0edb3a222ab5b3004a93b8b7c9034deb688e24d7de`.
The `.git` mount is read-only, independently preventing the requested commit.
The connector rejected the `needs-human` label, blocker comment and PR-body
correction reopening the premature hosted/reconciliation checkboxes: approval
is required while this run's policy is `never`.

Both Python files were formatted separately with Black at line length 100, and
both single-file `black --check --line-length 100` commands exited 0. A two-file
formatting invocation stalled and was interrupted (exit 130); the successful
single-file commands followed it. The mandatory repository-wide gate did not
pass:

```sh
BLACK_NUM_WORKERS=1 timeout 120s black --check --line-length 100 \
  --exclude '(\.workflows-lib|node_modules)' .
# Exit 124: "Aborted!"; 1021 files would be left unchanged.
```

No commit or push was attempted because the global gate remains unverified and
Git metadata is read-only. The source fix, tests and this evidence update remain
local. Final GitHub readback confirms PR #4711 open with `isDraft=false`.

## Local keepalive round 10 — November 16, 2026 Central

Outcome T6: **not satisfied**. Checked candidate
`fb0c529e772811fad47247d1b8637220ad52b7f4` on `orch/issue-4432`.
PR #4711 is open, unmerged and ready for review; there is no delivered merge SHA.
The precheck's completed A3/A4 claims and the checked hosted-inspection task are
not supported by the recorded hosted evidence.

The single acceptance outcome remains a hosted round at the delivered runner
SHA showing `llm-analysis-run=true`, `provider=codex`, the resolved registry
cheap-tier model, all four JSON-derived summary outputs, subscription auth and
both API-key-presence booleans false. This inspection was bounded to two evidence
checks or 20 minutes. It stopped after two checks; no code was changed and no
provider inference or hosted dispatch was started.

Runnable read-only inspection commands (each below two minutes in this check):

```sh
gh pr view 4711 --repo stranske/Workflows --json state,isDraft,headRefOid,mergeCommit
gh run list --repo stranske/Workflows --workflow agents-keepalive-loop.yml --limit 5 --json databaseId,headSha,status,conclusion,url,createdAt
gh run view 43827694560 --repo stranske/Workflows --json jobs,headSha,url
gh run view 43798812323 --repo stranske/Workflows --job 133074122262 --log > /tmp/4711-old-runner.log
git diff origin/main HEAD -- .github/workflows/reusable-codex-run.yml
```

- [Latest successful keepalive run 43827694560](https://github.com/stranske/Workflows/actions/runs/43827694560)
  used head `1aa2f778cd322f56877abb87659d9f0186e9ee42`. Its Codex job
  `133165463385` was skipped. Overall run success is not analysis acceptance.
- Re-read the full [earlier Codex job 133074122262](https://github.com/stranske/Workflows/actions/runs/43798812323/job/133074122262).
  Its `Uses:` resolves the reusable runner to
  `3be719f4c750ea1057e40c7287d3f74bbf999508`. It reports
  `Skip output 'llm-completed-tasks' since it may contain secret.` It has no
  runtime subscription or key-presence receipts. No credential values were
  printed into this record.
- Fetched main is `c223e1022aa7be1c408be0b60b7a1b6a74740b40`.
  Comparing its runner with this candidate confirms the subscription and
  key-presence receipt is still a PR change. Neither a preview merge nor
  a branch dispatch can establish the required post-merge result.

Blocking/drainable pair: delivered runner and hosted receipt are missing;
read-only inspection and truthful evidence reconciliation remain drainable.
No new hold, lock or permit was introduced. Local confinement evidence remains
separate and was not rerun or upgraded to hosted authentication acceptance.
T6 remains unchecked, as do delivered-SHA A1 and hosted A3–A5. Completion requires
observed delivered-state evidence; this round does not claim it.

Fetch updated main but could not prune a stale remote ref because the sandbox
cannot create `packed-refs.lock`. No ref deletion or permission workaround was
attempted. The PR branch was synchronized with its remote before this edit.
Validation for this documentation-only change: `git diff --check`.
