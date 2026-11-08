# PR #4535 review and delivery handoff — 2026-11-08

## Raw phase receipt regression continuation

The validator suite now includes 44 additional controls against raw phase
receipts in both arms, for the controller and a worker. They reject null,
boolean, string, negative, nonfinite and reversed boundaries, missing receipts
or receipt hashes, and incorrect process/clock identities. Damaged receipt
bytes are rehashed in the fixture while the valid reported phase summary is
retained, so rejection must come from independent receipt reconciliation rather
than a stale digest. Existing workflow-identity and missing-arm controls remain.
No runtime instrumentation or retained archive was changed.

Local Python 3.14.10 / pytest 9.2.0 results:

```text
python -m pytest tests/scripts/test_validate_hosted_receipts.py -q -m 'not slow'
108 passed in 1.16s

python -m pytest tests/scripts/test_validate_hosted_receipts.py tests/scripts/test_measure_verifier_runtime.py tests/scripts/test_gate_runtime_evidence.py -q -m 'not slow'
437 passed in 26.93s

python -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py -m 'not slow'
2054 passed in 21.49s
```

All five marker-specific options assertions remain unchanged. The exact
Anaconda interpreter path is still absent; these are local equivalent commands,
not evidence that the machine-specific commands exited zero. Ruff and
`git diff --check` pass; the touched test file is Black-formatted at length 100.
After a serial check populated the writable Black cache with the configured
source selection, the required repository-wide command passed:

```text
BLACK_NUM_WORKERS=1 BLACK_CACHE_DIR=/tmp/receipt-black-cache black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
970 files would be left unchanged.
```

The subsequent source/test commit attempt failed at staging with
`Unable to create '.git/index.lock': Read-only file system`. These new test
controls and handoff notes remain uncommitted; no push was made.

PR #4535 was rechecked open with `draft=false` at the unchanged head below.
Publishing its prepared body was again rejected with
`MCP tool call requires approval, but approval policy is never`. The exact-head
check reporter returned UNKNOWN because `api.github.com` was unreachable.
The connector reports successful Gate/guard contexts, but that partial result
does not establish complete expected/required checks. The candidate Git object
is still absent, and an explicit base64 read of the retained new 3.12 archive
returned empty content. Four-archive revalidation and guarded merge remain
unverified. No acceptance checkbox was changed.

PR #4535 remains open and ready for review at
`f3325610782d7d8d57fbd9659cfae8b1e12fe10e` on `closer-r2/issue-4462`.
This checkout is `codex/issue-4541`. No source write to the other branch is
claimed, and its current writer's ownership has not been superseded.
The proposed body in this directory was retrieved unchanged from that exact
head. It correctly distinguishes accepted run 42421935858 from canceled trial
42421695302 and corrects the coverage-report boundary. Publishing it was denied.

## Current-source dispositions

The connector returned these 13 active, unresolved, non-outdated threads.
These are recorded dispositions for the authorized PR writer to apply; no
remote reply or thread resolution succeeded in this run. Source-addressed does
not mean that a reviewer accepted the change or that the merge guard passed.
Thread IDs are GitHub GraphQL review-thread IDs.

| Thread | Current-source assessment and disposition |
| --- | --- |
| `PRRT_kwDOQprj9M607byc` | Addressed in PR source: the controller's actual pytest-cov `summary()` is directly timed inside `pytest_runtestloop`. Final reporting measures `pytest_sessionfinish` for JUnit/terminal only. `execution_phases()` and the README distinguish these intervals, preserve overlap and leave exclusive overhead UNKNOWN. Correct the stale PR body using the retained proposed body before resolving. |
| `PRRT_kwDOQprj9M607fFp` | Optional manual-workflow hardening, declined for this payload. The upload root already matches validator paths. `if-no-files-found: error` applies to the combined upload selection and would not ensure that every phase glob matched when other files exist. The validator rejects missing required files and missing declared phase receipts. Workflow files are protected in this run; no workflow edit is needed for the selected validator repair. |
| `PRRT_kwDOQprj9M607fFs` | Decline cosmetic README wording cleanup. The existing sentence unambiguously describes uploaded hashes; it changes no receipt or acceptance behavior. |
| `PRRT_kwDOQprj9M607fFu` | Decline rewriting historical machine-specific commands in this payload. The task explicitly requests those exact commands; this record separately reports the available interpreter and runnable local equivalents. The missing interpreter prevents claiming the exact-command acceptance criterion locally. |
| `PRRT_kwDOQprj9M607fFy` | Addressed in this branch's validator: non-string and non-full-lowercase-hex identities are rejected with `ValueError` before Git. Both 40- and 64-character commit IDs remain supported. Regression controls cover invalid types, lengths, uppercase, options and delimiters. Still needs delivery to PR #4535. |
| `PRRT_kwDOQprj9M607fF1` | Addressed locally in this round: require manifest/result, both arms' JUnit/coverage files and console logs before reading inputs or calling Git. Match the artifact's exact `verifier-runtime-MAJOR.MINOR` name to its recorded full Python version. Tests cover both 3.12/3.13, missing members/names, invalid names, swapped runtime labels and malformed runtime fields. Still needs delivery. |
| `PRRT_kwDOQprj9M607fF3` | Addressed in this branch: declaring `phase_plugin_sha256` requires both arms' phase measurements. Existing raw-clock, completeness, availability and gap checks remain. Legacy archives alone retain the no-probe UNKNOWN result. Still needs delivery. |
| `PRRT_kwDOQprj9M607fF6` | Addressed locally: the validator has 64 passing fixture-based regression cases, and metadata CLI input explicitly uses UTF-8. Keep `json.dumps` for this CLI; the suggested web-framework `jsonify` is inapplicable. Still needs delivery. |
| `PRRT_kwDOQprj9M607fF9` | Valid optional robustness finding: current PR source accesses `cov.cov_controller` and `summary` without guarding absent private attributes. The controlled harness pins and installs pytest-cov, so the retained successful experiment is not invalidated. A writer choosing to implement hardening should use guarded lookups and preserve UNKNOWN when unavailable; no replacement of this checkout's older runtime script was made. Requires an explicit PR-owner disposition before resolution. |
| `PRRT_kwDOQprj9M607fF_` | Current PR source uses an unguarded `VERIFIER_PHASE_DIR` lookup and locale-default text writes. The harness always supplies that directory, so absent-environment handling concerns standalone reuse rather than the retained experiment. Explicit encoding is optional consistency work. Defer this hardening to the current writer; do not alter archived harness/probe identity. Requires an explicit PR-owner disposition. |
| `PRRT_kwDOQprj9M607fGB` | Locale-default receipt read is present in PR source. Generated JSON is ASCII, so there is no demonstrated receipt failure. Defer this encoding-only cleanup under the task's cosmetic-cleanup limit. |
| `PRRT_kwDOQprj9M607fGE` | Bare phase-clock filenames can select unrelated checkout files. This is valid hardening, but no collision is demonstrated in the retained archives. The writer can constrain those names to a `phase-clocks` parent in a bounded follow-up. Preserve existing artifact exclusions and refusal checks; no runtime-script overwrite was made here. Requires an explicit PR-owner disposition. |
| `PRRT_kwDOQprj9M607fGG` | The PR's tests do not cover plugin absence. Current source safely skips the wrapper when `getplugin('_cov')` returns `None`; absent clocks then remain UNKNOWN. A focused optional test would establish that behavior independently of the real two-arm fixture. Defer to the current writer rather than import or replace its instrumented runtime/tests in this checkout. |

The review's outside-diff acceptance-record finding is already clarified by its
terminal section and retained proposed body: successful run 42421935858 carries
the accepted phase receipts. The historical integration transcript used Python
3.12.2 / pytest 9.1.1, while the repository pin is pytest 9.2.0; the local rerun
below uses pytest 9.2.0. The review's docstring-check observation is not evidence
of a required current-head CI failure; check its current conclusion before merge.

## Local verification

Before the new required-member and artifact-name guards, the expanded validator
tests reproduced 19 failures and 37 passes. After the implementation, including
additional malformed-runtime controls, all 64 validator tests pass.

```text
python -m pytest tests/scripts/test_validate_hosted_receipts.py tests/scripts/test_measure_verifier_runtime.py tests/scripts/test_gate_runtime_evidence.py -q -m 'not slow'
393 passed in 20.94s

python -m pytest tests/scripts/test_pr_verifier_body_overall_integration.py -m 'not slow'
2054 passed in 18.94s

python -m ruff check docs/evidence/issue-3904/validate_hosted_receipts.py tests/scripts/test_validate_hosted_receipts.py
All checks passed!
```

These use installed Python 3.14.10 / pytest 9.2.0, not the unavailable
`/opt/anaconda3/bin/python3`. All five marker-specific options assertions remain
unchanged. The runtime harness here predates the instrumented PR head; the local
suite does not establish integrated PR-head acceptance. The two changed Python
files were individually formatted with Black at line length 100.

The required repository-wide formatting command also passed:

```text
BLACK_NUM_WORKERS=1 BLACK_CACHE_DIR=/tmp/receipt-black-cache black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
970 files would be left unchanged.
```

The default multiprocessing attempt was denied by the sandbox. The single-worker
threaded attempt was interrupted after it did not finish; a serial Black check
populated the same writable cache with the repository's configured file selection
and Python 3.13 target before the CLI command above passed. No formatting rule,
exclusion or security setting was changed.

## Delivery limits

The connector reports successful `Gate / gate` and
`Health 45 Agents Guard / guard` contexts at the observed PR head. That partial
list does not establish complete expected/required checks. The prescribed
read-only reporter exited 2 with verdict UNKNOWN:

```text
python scripts/check_checks_reported.py --repo stranske/Workflows --pr 4535 --head f3325610782d7d8d57fbd9659cfae8b1e12fe10e --event pull_request --action synchronize --transport native-gh --output /tmp/pr-4535-checks.json
native-gh read failed: error connecting to api.github.com
```

The PR's last observed update was 2026-11-07T23:45:33Z, but elapsed time alone
does not satisfy the final merge-boundary check. The authorized merge lane must
recheck the unchanged full head, complete expected/required checks, zero active
unresolved findings after owner dispositions, and the seven-minute review floor.
No merge was attempted with UNKNOWN check evidence or unresolved threads.

Only the original 3.13 ZIP is available in this checkout, and the immutable
candidate Git object remains absent. Four-archive revalidation is not established
by this run. Keep all existing PR archives, the immutable source pair and common
dependency lock. Historical unuploaded logs and exclusive overhead remain UNKNOWN.

Staging the focused Python and handoff files failed with:

```text
fatal: Unable to create '/home/runner/work/Workflows/Workflows/.git/index.lock': Read-only file system
```

No commit or push was made. The body update, coverage-boundary reply, blocker
comment and `needs-human` label on source issue #4541 were each rejected with
`MCP tool call requires approval, but approval policy is never`. No CLI or
alternate-account mutation was used to bypass these denials.
No completion checkbox was changed. Apply the focused validator/test delta through
the existing writer, then perform the blocked body/thread/guarded-merge actions
with the necessary authorization.
