# Exact-head collection context regression

The Workflows adapter continues to use the existing Orchestrator reporter's
paginated `_gh_json` transport. The source inspected through the GitHub connector
was `scripts/check_checks_reported.py` at blob
`2759fb74f6f750d25ceec89d3a43e718ac061302`; the locally downloaded source identity
is recorded in each adjacent command receipt. The missing
`docs/AGENT_ISSUE_FORMAT.md` citation and implemented
`.github/scripts/issue_format.py` contract are accounted for in the
[shared source boundary](../../ops/EXPECTED_CHECK_RECEIPTS.md#shared-source-boundary).

The new controls reproduced five false PASS results before repair: retargeting a
base branch without changing either SHA, changing the declared file count,
changing a destination path, introducing a renamed source path, and truncating
the closing path inventory. Collection now enumerates every files page again
and binds it to the closing PR context. Each negative returns UNKNOWN, while a
stable multi-page inventory remains PASS when page order and diff statistics
change. The original four reporter scenarios remain in the focused test suite.

## Supported-command reruns

The connector returned both named PRs as merged and `draft: false`. Orchestrator
#461 retained head `4e82b31b09d5e70a62364b41e3a8c6da369549e1`. Workflows #3756
returned head `b1ab592d177fcd0773a756aeb957f76593a6f09f`, replacing the task's
historical `e4f0c7670566243d9a5d31c5ec7f4c35dd66bed0` pointer. The following actual
commands ran against those freshly observed heads:

```bash
python3 scripts/check_checks_reported.py \
  --repo stranske/Orchestrator --pr 461 \
  --head 4e82b31b09d5e70a62364b41e3a8c6da369549e1 \
  --event pull_request --action synchronize \
  --presence-reporter /tmp/issue-3757-incumbent/check_checks_reported.py \
  --output docs/evidence/issue-3757-context-binding/Orchestrator-461-checks.json

python3 scripts/check_checks_reported.py \
  --repo stranske/Workflows --pr 3756 \
  --head b1ab592d177fcd0773a756aeb957f76593a6f09f \
  --event pull_request --action synchronize \
  --presence-reporter /tmp/issue-3757-incumbent/check_checks_reported.py \
  --output docs/evidence/issue-3757-context-binding/Workflows-3756-checks.json
```

Both exited 2 with UNKNOWN because the incumbent's `gh api` transport could not
connect to `api.github.com`. Connector metadata does not substitute for the
complete paginated check/suite/rule evidence. The temporary source path is local
to this run; later runs should use a trusted Orchestrator checkout as documented.
Event/action is explicitly caller context, not a newly discovered webhook.

Live completeness remains unverified. Neither receipt authorizes a merge or
establishes historical pre-merge checks, review-thread settlement, or the
seven-minute floor. Future merges still require passing expected and required
checks, zero active non-outdated unresolved review threads, and seven elapsed
minutes for the unchanged full head.

## Validation

`python3 -m pytest -q tests/test_check_checks_reported.py -m "not slow"` passed
all 190 tests. The five new negative controls failed before the repair; the
sixth control verifies stable pagination and renamed paths. Ruff on both changed
Python files and `git diff --check` passed.

Both changed Python files were formatted with Black at line length 100. The
required `black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .`
gate passed: 664 files unchanged. This runner's Black worker paths hang or fail
to start. A temporary launcher runs Black's own `reformat_one` sequentially over
every source selected by its normal CLI, preserving its configuration, modes,
exclusions, validation and result reporting. No repository tooling was changed.

This run's checkout mounts `.git` read-only, so staging could not advance its
branch. The verified source changes were committed in a temporary Git checkout
and exported as a bundle; the original workspace retains the same edits.

## CLI scenario follow-up

- [x] Add tests for the four reporter scenarios, enumerate check-run and
  check-suite pages, and bind output to the unchanged full head, event, action
  and changed paths.
- [x] Verify that pytest passes the four scenarios, including FAIL for a
  missing required reporter and a zero-job startup failure.

The follow-up adds 19 cases in `tests/test_check_checks_reported.py`. Each incident
is driven through the CLI into a durable JSON receipt, with both page orders and
two caller actions. The tests retain the authored absence evidence and verify
expected, reported, passing and missing names. Separate controls reject reuse of
an absence for an applicable action and changed head/path closing snapshots.
The startup failure is recovered from a suite beyond the first page, even beside
successful checks.

`python3 -m pytest -q tests/test_check_checks_reported.py -m "not slow"` passes
all 213 tests; Ruff and `git diff --check` pass. Both supported commands above
were rerun after reading current heads through the connector. The adjacent
receipts retain UNKNOWN because local `gh` still cannot connect to GitHub.
Live completeness and the exact-head merge gates remain unverified.

Updating PR #3791's verified checkboxes through the GitHub connector was rejected:
the tool requires approval, while this run's approval policy is `never`. These
local checkboxes record verified work without claiming the remote body changed.

The required repository-wide Black check passes with 664 files unchanged via
the same sequential scheduling workaround described above. The original `.git`
is still read-only; the follow-up commit is exported from a temporary checkout
as `/tmp/issue-3757-cli-receipts.bundle`, with its reviewable patch alongside it.

## Unsupported event/action follow-up (2026-10-07)

- [x] Inspect the Workflows README, missing `docs/AGENT_ISSUE_FORMAT.md` citation,
  implemented `.github/scripts/issue_format.py` validator and linked Orchestrator
  reporter; verify the shared source boundary and supported invocation.
- [x] Retain UNKNOWN for unsupported caller events/actions and invalid authored
  activity types in the existing `check_checks_reported.py` adapter.
- [ ] Establish live completeness and all exact-head merge gates for the named PRs.

The source boundary remains unchanged: the Orchestrator incumbent owns `_gh_json`
pagination and historical reporting; this Workflows adapter owns event-specific
topology receipts. The opener comment was read again and still names Reviewed
Repo Backlog Opener followed by Reviewed Repo Merge Verify Closer, with Orphan
Steward retaining the named PRs. The missing issue-format document was not
invented or substituted for the implemented validator.

New regression controls first reproduced false PASS for empty, misspelled,
uppercase and unrelated caller actions. Collection now validates the context
before any API requests, and `event_applies()` validates it before exempting
even an unrelated workflow. Unsupported CLI events emit durable UNKNOWN JSON
rather than only an argument-parser error. Authored `types` containing unknown
activities, non-string values or an empty list also remain UNKNOWN. Supported
explicit label, close, ready-for-review and queue activities continue to apply.

Validation: `python3 -m pytest -q tests/test_check_checks_reported.py -m "not slow"`
passes all 268 tests, including the original four named reporter scenarios.
The 17 negative cases failed before the implementation change. Ruff on both
changed Python files and `git diff --check` pass. Black formats both files at
line length 100; its repository-wide check uses the sequential scheduling
workaround described above because both process and thread worker paths fail
or hang in this sandbox. Black's normal source discovery and formatter remain
in use; the full check passes with 675 files unchanged. No repository tool
configuration changes.

Both supported commands in this document were rerun against freshly read heads,
using `/tmp/checks-reporter-source/check_checks_reported.py` as the incumbent.
Its bytes were verified against the fetched Git blob
`2759fb74f6f750d25ceec89d3a43e718ac061302` before the final reruns.
The current heads remain `4e82b31b09d5e70a62364b41e3a8c6da369549e1` for
Orchestrator #461 and `b1ab592d177fcd0773a756aeb957f76593a6f09f` for Workflows
#3756. Both PRs are closed, merged and non-draft; they were not changed by this run.
The adjacent refreshed receipts exit 2 with UNKNOWN because `gh api` cannot
connect to GitHub. No check completeness, review settlement or seven-minute
head-age gate is inferred from the connector's PR metadata. Live acceptance
remains incomplete and must be retried where the incumbent transport is available.

This checkout's `.git` is read-only: `git add` cannot create `index.lock`.
The verified change is committed in a temporary local checkout and exported as
`/tmp/issue-3757-event-context.bundle` and `/tmp/issue-3757-event-context.patch`.
The original workspace retains all reviewed edits; no push or PR mutation occurs.
