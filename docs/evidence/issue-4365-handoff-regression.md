# Issue #4365: handoff regression verification

## Continuation acceptance contract (2026-11-06, 21:54 UTC)

Real input: open source PR #4451 on `closer/issue-4365`, initially
`8734263bd9fff4ebac312f953be1c33250901ad5`, and consumer
`stranske/Portable-Alpha-Extension-Model#2454`.

Outcome 1 is established only after current-head review disposition and passing
source gates permit guarded merge, Maint 68 deploys the selected consumer,
and subsequent Maint 71 and sync-core observations show the original thread
absent and no further #4365 bumps. It is currently **unverified**.

Read-only proving commands (each inspection is bounded to two minutes):

```sh
gh pr view 4451 -R stranske/Workflows --json state,headRefOid,isDraft,statusCheckRollup
gh run view 42290128697 -R stranske/Workflows --log
gh pr view 2454 -R stranske/Portable-Alpha-Extension-Model --json state,headRefOid,isDraft
gh run list -R stranske/Workflows --workflow maint-71-merge-sync-prs.yml --limit 5
gh issue view 4365 -R stranske/Workflows --comments
```

The last two commands require inspecting the actual relevant run output and
comment timestamps; an empty search or a successful dispatch alone is insufficient.
Record the selected Maint 68/71 run IDs below after delivery.

Stop rule: one attempt per acceptance step; stop at the first actual failure or
at 22:19 UTC (25 minutes after starting). Preserve the first failure and all
existing implementation; do not expand repairs. Blocked/drainable pair:
merge and deployment are blocked until review and exact-head gates clear;
read-only evidence retrieval and per-thread evidence preparation remain drainable.
No full local suite will be run: use the successful same-head Gate logs.

Verified locally on 2026-11-04 for PR #4447. Reviewed prior commits
`e4c3bf7c`, `3e91bbc9`, `8e055ec0`, and `7d26be7c` before continuing.

## Verified helper behavior

- [x] The source and consumer transition helpers require matching source PR and
  closure identities before selecting `done`.
- [x] Reopening and closing again requires fresh handoff proof, including when
  the same PR closes the issue again.
- [x] Matching malformed identities on both records remain on `verify`.
- [x] Temporarily reintroducing label-only trust fails regression assertions;
  restoring both modules passes all transition tests.

The new tests cover matching invalid closure IDs and source PR numbers on both
records. Earlier malformed-input tests changed only one record, so equality
alone could satisfy those rejection assertions without validating either ID.

Command:

```sh
node --test --test-isolation=none .github/scripts/__tests__/auto-pilot-transitions.test.js
```

Result: **43 passed, 0 failed**. Disabling process isolation exposes individual
test results in this environment; the default reporter displays a file result.

Three temporary mutations were checked separately in each module:

| Temporary regression | Observed result |
| --- | --- |
| Replace current-handoff validation with the handoff-label boolean | Exit 1, regression assertion fails |
| Remove closure-ID equality while retaining PR equality | Exit 1, regression assertion fails |
| Remove positive-ID validation while retaining identity equality | Exit 1, new matching-invalid-identity assertion fails |

All six mutations failed as expected. Both module files were restored in a
`finally` block. `git diff --exit-code` confirmed neither implementation file
retained a mutation, and the complete transition test file passed afterward.

A further mutation retained primitive-type validation while removing only the
positive-ID format check. On each module, the existing malformed-input test
passed while the new matching-invalid-identity test failed. Both modules were
restored, and all 43 tests passed again.

## Gates still incomplete

- [ ] `node --test .github/scripts/__tests__/*.test.js`
- [ ] `python3 -m pytest -q tests/ -m "not slow"`

The full Node run reported failures in `agents-verifier-context.test.js` and
`generated-delivery-seal-action.test.js` before it was interrupted while making
no further visible progress. Running those two files with process isolation
disabled yielded 199 passing and 18 failing tests, including child-process
`EPERM` errors. Those surfaces were not changed by this round.

The Python gate failed during `langsmith_plugin` startup: Python 3.14 emits an
`asyncio.iscoroutinefunction` deprecation warning, which the repository's warning
policy treats as an error. These results do not establish passing source gates.

The existing handoff integration tests passed separately with only that
third-party plugin disabled:

```sh
python3 -m pytest -q tests/workflows/test_auto_pilot_verify_handoff.py -m "not slow" -p no:langsmith_plugin
```

Result: **8 passed**. These tests exercise existing handoff labeling and lookup;
they do not verify automatic continuation or completion reporting.

**HISTORICAL (RESOLVED):** Maintainer follow-up: protected workflows

- [x] Collect the current closure event and source PR; persist successful handoff
  identity and pass `closure` and `verifyHandoff` to `determineNextStep`.
- [x] Accept eligible `verify:pr-handoff` label events in the gate predicate.
- [x] Admit successful verification handoffs in the redispatch allowlist, or
  complete the done disposition in the same run.
- [x] Validate current handoff identity in the done report before removing
  `agents:auto-pilot` and publishing completion.
- [x] Test event eligibility, scheduled continuation, completion reporting, and
  label cleanup through the workflow.

These integration points are in `.github/workflows/agents-auto-pilot.yml` and
the consumer workflow template. The production caller now passes the full
identity objects required by the helper. The event gate and redispatch 
allowlist have been updated. Helper tests and workflow tests establish 
automatic production completion.

**Note:** This section documents historical requirements that have been completed.
See PR #4451 for the implementation details.

After merge, a maintainer should use Maint 68 to regenerate the selected consumer
payload, then verify Maint 71 and the review outcome for
`stranske/Portable-Alpha-Extension-Model#2454`. These live checks remain pending.

PR-body reconciliation, adding `needs-human`, and posting the workflow blocker
were attempted through the GitHub connector. All three writes were rejected
because the tool approval policy is `never`; this document preserves the
verified status and required follow-up locally. No remote checkbox, label, or
comment update is claimed.

The required commit is also pending: staging the two changed files failed with
`Unable to create .../.git/index.lock: Read-only file system`. The working-tree
test and evidence changes remain available for a runner with Git write access.

## Follow-up: execute the workflow callers

Added two regressions to `auto-pilot-transitions.test.js` that extract and execute
the actual automatic next-step Node caller from the root and consumer workflows.
Each runs a closed issue with retained handoff labels, reopens it, and closes it
with a different linked PR. The caller must select `verify` for the new closure,
and a legacy `verify:evaluate` issue without a bound handoff also remains on
`verify`. These checks exercise the production input mapping rather than supplying
identity objects directly to the helper. They do not establish successful
handoff continuation or completion reporting.

Verification:

- [x] `node --test --test-isolation=none .github/scripts/__tests__/auto-pilot-transitions.test.js`
  reports **45 passed, 0 failed**.
- [x] Replacing the identity guard with label-only trust in each helper separately
  makes its workflow-caller regression fail with `next_step=done`. Both helpers
  were restored in `finally` blocks; the tests pass again and neither helper
  retains a diff.
- [x] The existing workflow JavaScript tests pass alongside the transition suite.
- [x] The eight existing Python handoff tests pass with only the startup-failing
  LangSmith plugin disabled, using the targeted command above.
- [ ] Full source gates remain incomplete. The full Node run again reported
  failures in `agents-verifier-context.test.js` and
  `generated-delivery-seal-action.test.js`, then stopped producing output and was
  interrupted. The two failing files were rerun separately: **199 passed,
  18 failed**, including `spawnSync python3 EPERM` and a missing expected
  delivery-seal refusal message.
  The full Python run again exited during LangSmith plugin startup on the
  Python 3.14 deprecation warning, before collecting tests.

No protected workflow changed. The `needs-human` label and blocker comment were
again rejected by the connector's approval policy (`never`). PR #4447 was read
back as open with `draft=false`. Staging the test change again failed because
`.git/index.lock` cannot be created on the read-only Git metadata filesystem;
the meaningful test change remains uncommitted for the outer runner to collect.

## Follow-up: execute completion reporting

Reviewed commits `e4c3bf7c`, `8e055ec0`, `7d26be7c`, `1cb349b9`, and
`935d48cb`. Added tests that execute the actual `Report - Done` script from
both source and consumer workflows against a local GitHub API stub:

- Missing, absent, and incomplete handoffs retain `agents:auto-pilot`, report
  the retry reason, and refuse completion.
- A successful handoff in the current run removes `agents:auto-pilot` from the
  correct issue and posts the completion report.

These tests verify the reporter when invoked. They do not establish that a
successful handoff automatically reaches it or that its label-only input is
bound to the current closure. Those protected workflow tasks remain incomplete.

Verification:

```sh
node --test --test-isolation=none .github/scripts/__tests__/auto-pilot-transitions.test.js tests/workflows/auto_pilot_verify_handoff.test.js
```

Result: **49 passed, 0 failed**. The targeted Python command above also reports
**8 passed** with the startup-failing LangSmith plugin disabled.

Three temporary mutations of the extracted reporter were tested locally:
removing the missing-handoff guard, cleaning up a different label, and replacing
the completion heading. Each failed both new tests (exit 1). The temporary test
edits were restored in `finally`; the full focused suite passes afterward.
No workflow file was modified, even during mutation verification.

The full Node gate again reported failures in `agents-verifier-context.test.js`
and `generated-delivery-seal-action.test.js`, then stopped producing progress
and was interrupted. The full Python gate with `-m "not slow"` exited 3 during
LangSmith plugin startup on the same Python 3.14 deprecation warning. Neither
full source gate is complete.

PR checklist reconciliation was attempted before the new tests. The intended
reconciliation retains verified helper-identity and reopening tests while
unchecking unsupported continuation, event-gate, and end-to-end completion
claims. GitHub rejected the body update, `needs-human` label, and blocker
comment because the connector approval policy is `never`. No remote status
change is claimed. The workflow identity plumbing, event admission, successful
handoff continuation, and post-merge Maint 68/71 checks still require a maintainer.

Staging this round's test and evidence changes failed with `.git/index.lock:
Read-only file system`; no commit was created. PR #4447 was read back as open
with `draft=false`. `git diff --check` passes.

## Follow-up: serialized handoff status

Reviewed the five latest keepalive commits through `3ef2b6ab`. Added source and
consumer-helper regressions for a workflow boundary not previously covered:
matching closure/PR identities must still select `verify` when
`verifyHandoffBound` is the environment string `"false"`. False, missing and
empty values are rejected; boolean and serialized true values permit `done`.

- [x] Focused Node suites: **51 passed, 0 failed** using the command above.
- [x] Replacing handoff-flag normalization with JavaScript truthiness fails the
  new regression separately in each helper. Both files were restored in
  `finally`, then all 51 tests passed again. No implementation mutation remains.
- [x] Targeted Python handoff tests: **8 passed** using the documented command
  with only the startup-failing LangSmith plugin disabled.
- [ ] Full gates: Node again reported the same two failing files and was
  interrupted after progress stopped. Their diagnostic rerun produced
  **199 passed, 18 failed**, including `spawnSync git/python3 EPERM` and the
  missing delivery-seal refusal message. Python exited 3 during LangSmith plugin
  startup on the Python 3.14 deprecation warning, before collection.
- [ ] Remote reconciliation: body update, `needs-human` label and blocker comment
  were rejected because connector approval policy is `never`. Workflow-dependent
  task checkboxes must remain incomplete; helper-only verification is not
  production continuation. No remote update is claimed.
- [ ] Commit: `git add` failed because `.git/index.lock` is on a read-only
  filesystem. The test changes remain in the working tree for the outer runner.

The protected workflow integration and post-merge Maint 68/71 checks listed
above still require a maintainer. No protected file was edited.

## Closer repair (2026-11-04): workflow identity plumbing

Real-input outcome (2026-11-04): closed issue with matching persisted handoff
marker selects `next_step=done` in the production caller; stale closure IDs
stay on `verify`; successful verify persists `auto-pilot-verify-handoff:v1`.

Focused acceptance (under 2 minutes):

```sh
node --test --test-isolation=none .github/scripts/__tests__/auto-pilot-transitions.test.js tests/workflows/auto_pilot_verify_handoff.test.js && /opt/anaconda3/bin/python3 -m pytest -q tests/workflows/test_auto_pilot_verify_handoff.py -p no:langsmith_plugin
```

Result: **57 passed** Node + **12 passed** Python (2026-11-04).

Full gates (preserved failures, not substituted):

- `node --test .github/scripts/__tests__/*.test.js` → **3392 passed, 2 failed** before
  verifier-correction expectation update; **3394 passed, 0 failed** after adding
  empty closure/handoff outputs to the inert context fixture.
- `/opt/anaconda3/bin/python3 -m pytest -q tests/` → **50339 passed, 3 failed**
  (`test_update_versions_from_pypi`, `test_integration_repo_template`), exit=1;
  unrelated to this surface.

Deliberate-break: temporarily removing `hasCurrentVerifyHandoff` identity checks
still fails focused regressions; restoration passes (see earlier table in this doc).

## Closer repair (2026-11-06): trusted marker and one merged source PR

`findLatestVerifyHandoff` ignores markers whose author is outside the keepalive
automation writer class. Determine context, verify, and Report - Done select
the closure source PR with `selectMergedClosingPr`, so a later unmerged
timeline reference cannot disagree with the recorded handoff. The cycle cap
counts the bold `🤖 **Auto-pilot step` comments the workflow writes.

```sh
node --test --test-isolation=none .github/scripts/__tests__/auto-pilot-transitions.test.js tests/workflows/auto_pilot_verify_handoff.test.js
python3 -m pytest -q tests/workflows/test_auto_pilot_verify_handoff.py -p no:langsmith_plugin -m "not slow"
black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

Result: Node **114 passed**, Python **64 passed**, Black **891 files unchanged**.

## Closer continuation (2026-11-06): scripts-path imports and marker parsers

- **Behavioral change:** `auto_pilot_transitions` loads only from
  `WORKFLOWS_SCRIPTS_PATH` / `scriptsPath` in github-script and embedded
  `node` steps; `Determine next step` exports `WORKFLOWS_SCRIPTS_PATH` for the
  whole run step so PR keepalive fetch and transition calls share the selected
  checkout. Verify handoff markers must be a **standalone line** matching the
  workflow JSON shape; quoted copies, blockquotes, and fenced bodies are
  ignored. Keepalive **tasks-complete** detection uses `parseStateComment` on
  standalone lines only (still accepts spaced JSON inside the marker).
- **Deliberate break / restore (local):** Reverting to substring
  `lastIndexOf` for the verify marker or accepting the prior string-match for
  keepalive completion fails the new **quoted / fenced / blockquote** and
  **workflow import path** regressions; restoration passes the focused Node
  file again.

```sh
node --test --test-isolation=none .github/scripts/__tests__/auto-pilot-transitions.test.js tests/workflows/auto_pilot_verify_handoff.test.js
/opt/anaconda3/bin/python3 -m pytest -q tests/workflows/test_auto_pilot_verify_handoff.py -p no:langsmith_plugin
```

Focused results (2026-11-06): Node **120 passed, 0 failed**; pytest **64 passed**.

```sh
node --test .github/scripts/__tests__/*.test.js
/opt/anaconda3/bin/python3 -m pytest -q tests/ -p no:langsmith_plugin
```

Full gates (2026-11-06, same head): Node **3486 passed, 0 failed**, 1 skipped;
pytest **49743 passed, 1 failed, 28 skipped**, exit **1**. The failure is
`tests/test_integration_repo_template.py::test_integration_template_installs_and_tests`:
editable install rejects **Python 3.12.2** because the temp consumer requires
**>=3.13** — host interpreter constraint, not auto-pilot logic. **Maint 71 /
Portable-Alpha-Extension-Model#2454 / sync-core stop bumping #4365** still
require remote observation after merge; not claimed here.

## Continuation evidence and first blocked step (2026-11-06)

Read back PR #4451 as **open, non-draft**, head
`8734263bd9fff4ebac312f953be1c33250901ad5`. Fetch confirmed local and remote
`closer/issue-4365` have zero divergence. No implementation or dependency pin
was changed in this continuation.

### Retrieved source CI evidence

[Gate run 42290128697](https://github.com/stranske/Workflows/actions/runs/42290128697)
completed successfully. Retrieved the actual job logs, rather than inferring
test results from its green aggregate:

- [Node job 128141997036](https://github.com/stranske/Workflows/actions/runs/42290128697/job/128141997036)
  checked out exactly `8734263bd9fff4ebac312f953be1c33250901ad5` and used Node
  **24.22.2**. Exact command: `node --test .github/scripts/__tests__/*.test.js`.
  Final outer summary at 20:41:49 UTC: **3493 tests, 3492 pass, 0 fail,
  1 skipped**. Earlier nested deliberate-failure fixture output is not the
  final outer result. The same job's separate `pytest tests/workflows/github_scripts`
  run printed **123 passed in 0.54s**.
- [Python job 128142242799](https://github.com/stranske/Workflows/actions/runs/42290128697/job/128142242799)
  used **Python 3.14.10**, pytest **9.2.0**, interpreter directory
  `/opt/hostedtoolcache/Python/3.14.10/x64`. It checked out GitHub's synthetic
  merge `09f852b5f96af77b3f7119591c53c19856764ded`, merging the exact PR head
  into base `408651629f027292c94f38f2c5aa0c1d3e24fe79`.
  Actual invocation in the log: `pytest -p ci_test_growth "${args[@]}"`, with
  JUnit/coverage options, four xdist workers (`--dist=loadgroup`), and
  `PYTEST_MARKERS="not quarantine and not slow"`. Final summary at 20:51:42 UTC:
  **49817 passed, 27 skipped, 3 xfailed in 550.41s**; finalization printed
  **Total failures: 0** and **All checks passed!**.

The hosted Python result proves the configured Gate selection on the supported
runtime and integration merge. It does **not** establish the literal unfiltered
`python -m pytest -q tests/` on the branch head. That exact acceptance remains
unverified. No local full suite was run, as requested. The local default
`/opt/anaconda3/bin/python3 --version` printed **Python 3.12.2**, below the
repository's `requires-python = ">=3.13"`; it was not used to repeat the known
consumer-install failure. Historical commands retain their actual interpreter
paths as provenance, not as portable environment setup instructions.

### Per-thread evidence prepared; remote dispositions not applied

Live query returned **16 unresolved threads: 9 current and 7 outdated**.
Outdated status alone is not a disposition. The following are individual
current-head findings, not a blanket dismissal; comment IDs identify the
original review conversations. Paths and line references describe head
`8734263bd9fff4ebac312f953be1c33250901ad5`.

| Review comment | Evidence-backed proposed disposition |
| --- | --- |
| 4472740088 (source author authentication) | Already fixed: `.github/scripts/auto_pilot_transitions.js:356-375` checks login and account type before parsing. `auto-pilot-transitions.test.js:431-467` exercises forged, missing-author, mismatched account type, quoted trusted, and later valid markers for both helpers. |
| 4472740122 (consumer author authentication) | Already fixed in the consumer helper's same `isTrustedVerifyHandoffAuthor` and `findLatestVerifyHandoff` functions. The test loop at `auto-pilot-transitions.test.js:427-431` explicitly loads the consumer module and runs the author rejection cases. |
| 4472740146 (consumer fixture selection) | Already fixed: `tests/workflows/test_auto_pilot_verify_handoff.py:243-246` checks `"consumer-repo" in workflow.parts` and selects the template helper. Python Gate evidence above is scoped to its actual CI selection. |
| 4493674877 (source meta regex) | Inapplicable injection claim: `textReferencesIssue` at source lines 379-385 rejects everything except a positive decimal ID with `/^[1-9]\\d*$/` before interpolation. No regex metacharacter can enter the pattern. Selection regression at `auto-pilot-transitions.test.js:469-478` also rejects prefix issue references. No suppression or regex rewrite needed. |
| 4493674930 (source closing regex) | Same digit-only guard precedes the second `RegExp` at source lines 386-389. Both patterns contain only fixed regex syntax plus validated digits; no attacker-selected quantifier or grouping is interpolated. |
| 4493674949 (consumer meta regex) | Consumer `textReferencesIssue` contains the same positive-decimal guard before the meta pattern; the shared regression loop loads the consumer helper independently. |
| 4493674975 (consumer closing regex) | Consumer closing-reference pattern is also downstream of the same digit-only guard. This finding does not justify changing the existing implementation or security gate. |
| 4493745964 (interpreter path) | Rejected as a change to historical evidence: owner instructions require the actual supported selected interpreter and exact commands. Replacing an observed executable with generic `python3` would obscure the Python 3.12.2 mismatch. Current supported hosted runtime and command are recorded above. |
| 4493745983 (consumer marker position) | Already fixed: `findStandaloneVerifyHandoffMarkerLine` and `lineOutsideStructuralContext` at helper lines 98-139 reject fences/blockquotes and require the anchored marker line. Parser tests and the quoted trusted-bot regression run for both modules; full Node Gate passed. |
| 4472665742 (outdated source PR selection) | Already fixed: `selectMergedClosingPr` is shared by context, Verify, and Done; regression at `auto-pilot-transitions.test.js:469-478` skips newer unmerged and prefix references. |
| 4472740100 (outdated selection and step count) | Same shared selector; both workflows' step-count filter matches the emitted `🤖 **Auto-pilot step` prefix. No new implementation needed. |
| 4472740112 (outdated keepalive docs) | Already fixed: `docs/keepalive/Agents.md:90-103` describes closure identity, trusted marker, event admission, found-only redispatch, and pending Maint 68/71 observations. |
| 4472740135 (outdated consumer PR selection) | Consumer workflow uses `selectMergedClosingPr` for the same caller surfaces; both-module selection and workflow caller regressions are retained. |
| 4493745915 (outdated source import path) | Already fixed: helper imports use `scriptsPath` / `WORKFLOWS_SCRIPTS_PATH`; workflow assertion at `auto-pilot-transitions.test.js:817` checks every transition import for source and consumer. |
| 4493745951 (outdated evidence checklist) | Already fixed near this document's original protected-workflow checklist: explicitly marked HISTORICAL (RESOLVED), five checked items, and a pointer to #4451. Other older run reports remain historical records. |
| 4493745991 (outdated consumer import path) | Same import-path correction and both-workflow assertion as 4493745915; no duplicate rewrite needed. |

### First failed step and retained delivery boundary

The first remote disposition attempt was a specific evidence reply to comment
**4472740088** through `github_reply_to_review_comment`. The connector rejected
it with: **"MCP tool call requires approval, but approval policy is never"**.
No reply was posted, no thread was resolved, and no alternative write route
was attempted. The first-failure stop rule therefore ended acceptance execution.
The local evidence record is preserved on the existing branch for continuation.

Blocking/drainable pair at stop: remote review dispositions are blocked by the
connector approval policy; documenting already retrieved evidence and committing
this evidence-only record remain drainable. Existing review, exact-head checks,
post-push floor, merge guard, and verification requirements remain intact.

- [ ] Apply individually justified remote dispositions using an authorized review writer.
- [ ] Establish the required exact Python source-gate acceptance; hosted marker-filtered CI is recorded without claiming equivalence.
- [ ] Qualify the new documentation commit's checks and review floor before guarded merge.
- [ ] After guarded merge, deploy the named consumer through Maint 68, preserving its canary/promotion contract.
- [ ] Record Maint 68/71 run IDs and actual #2454 thread disposition.
- [ ] Observe subsequent sync-core activity and establish that #4365 bumps cease.

No merge, consumer dispatch, Maint 71 observation, or bump-cessation result is
claimed. PR-body completion claims predating this continuation do not override
these remaining evidence gaps. Resumption requires an authorized review-write
path; the existing closer retains the target and implementation.
