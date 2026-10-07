# Expected-check receipts for delivery lanes

`scripts/check_checks_reported.py` is the Workflows-owned, read-only adapter for
the existing Orchestrator `scripts/check_checks_reported.py`. The adapter loads
that tracked reporter's `_gh_json` transport, which enumerates every GitHub REST
page. It records the incumbent file's SHA-256 before importing it or collecting
evidence, so import/API failures retain that source identity in UNKNOWN receipts.
Changing the incumbent file during collection also returns UNKNOWN; a later
digest cannot describe the source used for earlier requests. Keep using the
incumbent frequency/ratchet report as an additional warning; frequency and a
visible green list cannot establish event-specific completeness.

Required commit statuses apply to the head across events. When auditing
`pull_request_target`, the adapter independently collects the exact-head
`pull_request` Gate publisher and its latest attempt/jobs for status provenance.
The receipt retains those runs separately as `status_publisher_runs`; they do
not contribute jobs or suite applicability to the target-event topology.
The existing immutable bot/app, run, suite, job/check and reporting-step time
bindings remain mandatory. A failed, stale or incomplete publisher stays UNKNOWN.

## Shared source boundary

The [Orchestrator reporter](https://github.com/stranske/Orchestrator/blob/main/scripts/check_checks_reported.py)
owns historical frequency/ratchet reporting and the paginated `_gh_json` transport.
The Workflows adapter owns event-specific topology, exact-head evidence and receipt
adjudication for an explicitly named repository. It calls only that transport;
it does not invoke the incumbent CLI, its Orchestrator-only `REPO` default, or its
ratchet updates. Pass the trusted tracked reporter from an Orchestrator checkout
with `--presence-reporter`; do not create another transport or historical algorithm.

The [opener's source lookup](https://github.com/stranske/Workflows/issues/3757#issuecomment-5989178591)
establishes this incumbent and routes implementation to Reviewed Repo Backlog
Opener, then live exact-head verification to Reviewed Repo Merge Verify Closer.
Orphan Steward retains the named consumer PRs until their own merge gates are
proved. The adapter command below is the delivery-lane entry point; the
incumbent's `--pr N` command alone does not satisfy this contract.

The issue's `docs/AGENT_ISSUE_FORMAT.md` citation is absent in this checkout.
`.github/scripts/issue_format.py` is the implemented work-order validator:
Tasks must name concrete targets and Acceptance Criteria must name verification
gates. That formatting contract does not establish check completeness. Reporter
behavior belongs in the adapter and `tests/test_check_checks_reported.py`, with
this document and `README.md` defining its supported invocation.

This is a local lane tool, not a consumer workflow or copy-managed template.
No workflow, registry, branch protection, installed mirror, or scheduler changes
are made by the command. Run networked invocations from outside a checkout with
the lane's `detached-net.sh` wrapper. Python 3.11+, PyYAML and authenticated `gh` must
be available; an unavailable incumbent or failed API discovery emits UNKNOWN.
Pass an absolute Python executable if the wrapper's PATH selects an older system
Python. The adapter never substitutes an unsupported interpreter silently.

## Supported invocation

Read the current full head first. Bind the action to the event being audited;
do not substitute `opened` merely to exempt a label-triggered workflow.
GitHub Actions REST does not expose the webhook action: the receipt explicitly
identifies event/action as caller context, which the receiving lane must retain
with its event evidence. A receipt covers that context, not every event over
the PR's lifetime.

```bash
python3 /path/to/Workflows/scripts/check_checks_reported.py \
  --repo stranske/Orchestrator --pr 461 --head FULL_HEAD_SHA \
  --event pull_request --action synchronize \
  --presence-reporter /path/to/Orchestrator/scripts/check_checks_reported.py \
  --output /path/to/evidence/Orchestrator-461-checks.json
```

Where the local lane requires it, prefix the command with that lane's
`detached-net.sh` wrapper; its location is environment-specific.
Replace `FULL_HEAD_SHA` with the freshly read 40-character head before running.

Use the same command with `--repo stranske/Workflows --pr 3756` and its current
head to refresh the issue's other named consumer. Changed heads
must not reuse older receipts. The historically observed heads in issue #3757
are evidence pointers, not current-head assertions.

## Receipt and verdict

An independently recomputed empty scenario selection is supported only after the
existing immutable producer receipt, helper/workflow bytes, complete changed-path
witness and exact run/attempt are verified. The authored zero-count guard must be
unchanged, and GitHub must emit exactly one skipped caller with the same literal
name, head, run/attempt and canonical repository/job-ID check-run URL. The fetched
check object must agree on ID, URL, name, head, completed/skipped state and Actions
app identity; the producer job head must also agree with the run. That caller remains an expected check;
the adapter does not invent child jobs or accept a missing caller. Arbitrary empty
literal matrices, forged receipts, changed guards and incomplete skip evidence
remain UNKNOWN. An internal witnessed type cannot be opted into by workflow YAML.
This is a local read-only adapter change, not a consumer template or manifest change.

The JSON `expected-check-receipt/v1` records:

- Full repository, PR, head/base, base branch, caller event/action and changed paths.
  The complete paginated path inventory is read again before the closing PR
  snapshot. `closing_context` retains the final head/base, branch, declared and
  enumerated file counts, and normalized paths, including renamed sources.
- Required status contexts and app restrictions from current branch protection
  and applicable branch rules. Inaccessible protection/rules evidence is UNKNOWN.
  A ruleset-only branch can report `protected: true` while the classic endpoint
  explicitly returns `Branch not protected (HTTP 404)`. Only that specific
  response records absent classic protection; applicable rules are still read
  independently. Generic 404 and permission errors remain UNKNOWN.
- Base workflow source refs, blob identities and authored YAML documents. Each
  legitimate event/action/branch/path absence records its concrete source and
  reason. A workflow changed in the PR requires merge-ref adjudication, so it
  cannot silently weaken the base topology.
- Expected/reported/passing names, latest states, missing and failing contexts,
  check runs, check suites, and latest workflow runs with every job page.
- Endpoint/page counts and response hashes. `filter=all` includes cancelled check
  attempts; a newer success replaces an older cancelled attempt. Independent
  failed suites remain conservative failures when replacement cannot be proved.
- Explicit `merge_authorization: false`. A PASS establishes only this tool's
  supported context. The receiving lane must still establish all expected event
  contexts, exact-head required/product checks, every active review thread and
  the seven-minute floor immediately before a pinned merge.

An absent required reporter or a current startup failure with zero jobs is FAIL,
even beside green checks. Required contexts must succeed, rather than merely
report `skipped`. A status from another app cannot establish a workflow job's
GitHub Actions provenance. App-restricted contexts require matching app evidence.

## Conservative boundary

Literal job names, Cartesian matrices and nonempty include-only matrices are supported, including JSON
matrix axes supplied by literal caller inputs. Without run bindings, local
reusable workflows recurse at the source ref and external calls require a full
SHA. A completely enumerated latest Actions run can instead bind a floating call
to its exact `referenced_workflows` SHA. Pinned calls must match their declared
SHA; ambiguous or missing bindings remain UNKNOWN. A conditional call requires
an executed child or GitHub's explicit skipped caller job in that same run.
Skipped callers retain their check URL and source as a concrete absence receipt.
Child expectations still come from the bound authored workflow, never from the
set of successful child jobs.

Duplicate display names require independent source-workflow/run/job/check URL
bindings, matching head and GitHub Actions app, and a successful or skipped
conclusion for every origin. One successful check cannot mask another origin's
missing or failing check. The receipt retains each independent claim.

The Python reusable workflow has one supported output-derived matrix contract.
Its immutable `select-scope` job calls the versioned pure
`scripts/reusable_ci_scope.py::select_python_matrix` and emits a
`python-matrix-producer/v1` receipt in its text log. The adapter uses the incumbent
JSON transport for all metadata and one bounded `gh api` text-log read for that
producer job. Raw logs are not retained in the receipt; their digest is retained.
The receipt binds repository, head, run ID, attempt, helper commit and digest,
resolved inputs and selected matrix. The executed helper bytes must equal the
trusted local resolver, and the producer job source must equal the supported
local workflow contract. The adapter recomputes selection independently and
checks literal caller inputs. Dynamic caller values are witnessed by that
source-bound producer, never inferred from the successful child jobs.

A missing Python child is FAIL even when other Python jobs succeeded. One explicitly audited legacy producer/helper pair also supports a complete
Actions checkout/input transcript. The adapter pins both source digests, requires
successful checkout and selector steps in the same exact job/run/attempt, extracts
the checkout commit and five resolved inputs, fetches the helper at that commit,
and recomputes the expected matrix. It retains the log digest and identifies the
receipt as a legacy transcript witness. Child conclusions never supply versions.
Other historical runs lacking either complete witness, changed helper/producer
source, ambiguous or incomplete receipts, empty include matrices and mismatched
recomputation remain UNKNOWN.
The two first-party scenario selectors now emit `scenario-matrix-producer/v1`
receipts. The adapter binds their exact completed job/run/attempt, immutable
checkout and helper/workflow digests, and independently verifies changed paths
against the base-to-checkout compare (an ancestor base and fewer than 300 paths
are required). It reads constant scenario matrices from trusted source without
executing fetched code, then replays the pure selector. Missing children fail;
forged inputs, transformed matrices, incomplete paths or changed sources stay
UNKNOWN. Scheduled and dispatch scenario receipts remain unsupported.

Changed caller roots can retain an expectation only when their complete parsed
source differs solely by the exact local helper checkout pin and the exact
receipt observer additions. Added/removed jobs, conditions, triggers, permissions,
selector logic or other source edits still require separate adjudication. The
receipt retains both authored documents and the narrow adjudication reason.

Other dynamic matrices/names, recursive calls, include/exclude transforms,
unsupported glob syntax and required-workflow rulesets remain UNKNOWN. The workflow and helper must actually have executed the bound contract; local tests or a new PR do not establish historical run provenance.

Ordinary conditional jobs still require a reported skipped/successful check.
Event-only workflows are absent only when the authored event/action or supported
filter proves the absence. Paths include renamed source and destination paths;
incomplete or large path inventories cannot establish Actions path filtering.

The tool collects all check runs/suites and every latest-run job page, rather than
an arbitrary latest-N run sample. Counts must agree with API `total_count` where
provided. Conflicting page totals, invalid counts and repeated object IDs also
remain UNKNOWN: a repeated object can hide an omitted check or suite even when
the final count matches. Every check run and suite on every page must explicitly
report the requested full head, including advisory checks and other apps' suites;
missing or mismatched heads remain UNKNOWN. A changed head/base, base branch,
declared file count or normalized path inventory during collection becomes
UNKNOWN. Equal SHAs cannot prove branch-filter or rules stability after a PR is
retargeted. Page order and unrelated diff statistics do not alter path identity.
Re-run after async completion or obtain concrete source-bound evidence for unsupported
conditions; never relabel UNKNOWN as PASS or waive missing checks.

Merged-head Actions search can return an empty inventory even while its exact-head
check suites still resolve to retained runs. The adapter reconciles every GitHub
Actions suite absent from the head search through the paginated `check_suite_id`
lookup. Each recovered run must match that suite and full head; only the requested
event is included. The receipt records other-event exclusions and every recovery
lookup. Missing, truncated or mismatched suite/run evidence remains UNKNOWN, and
recovered zero-job startup failures remain FAIL beside green checks. Successful
child jobs never supply the expected topology.

## Regression gate

Run `python3 -m pytest -q tests/test_check_checks_reported.py`. The suite contains
the four issue-required controls: missing required check, legitimate label-only
absence (Orchestrator #461's auto-pilot shape), cancelled attempt replaced by
success, and zero-job startup failure. It also checks pagination, truncation,
required app restrictions, reusable children, matrices, and head changes.

For a deliberate-break control, temporarily omit `missing` from the FAIL decision
in `adjudicate()` and run
`python3 -m pytest -q tests/test_check_checks_reported.py::test_missing_required_check_is_fail`.
The test must fail. Restore the implementation and rerun the entire focused suite;
retain both command outputs beside the live receipts. Do not commit the mutation.

## First-party local-call validation

Workflows Gate, reusable CI selftest and integration-consumer workflows invoke
the reusable workflow from the tested tree and pass `workflows_ref: ${{ github.sha }}`.
This keeps the helper checkout on that same tested commit, including before a
new helper API reaches main. Consumer remote calls retain their `@main` default.

### Required Gate commit-status publisher

REST commit statuses do not expose an app foreign key. The local lane adapter
binds the latest successful `Gate / gate` status only for the built-in github.com
GitHub Actions publisher. Authenticated app and bot records must match their
immutable platform IDs. The status repository/head, successful pull-request Gate
run and attempt, Actions suite, summary job/check, and successful status-report
step must agree; the status timestamp must fall inside that step. The receipt
retains these identifiers in `status_provenance`. A target URL, publisher login,
or caller-supplied app ID alone is insufficient. Unbound, stale, ambiguous, or
unavailable evidence remains UNKNOWN; a missing status remains missing and a
failed check cannot be hidden by a successful status.

This is a local lane-adapter change, not a reusable workflow or consumer sync
change. It does not authorize installing an unreviewed helper into a running lane.
