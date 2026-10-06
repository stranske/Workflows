# Expected-check receipts for delivery lanes

`scripts/check_checks_reported.py` is the Workflows-owned, read-only adapter for
the existing Orchestrator `scripts/check_checks_reported.py`. The adapter loads
that tracked reporter's `_gh_json` transport, which enumerates every GitHub REST
page. It records the incumbent file's SHA-256 in the receipt. Keep using the
incumbent frequency/ratchet report as an additional warning; frequency and a
visible green list cannot establish event-specific completeness.

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
/Users/teacher/.codex/bin/detached-net.sh python3 /path/to/Workflows/scripts/check_checks_reported.py \
  --repo stranske/Orchestrator --pr 476 --head <current-full-head> \
  --event pull_request --action synchronize \
  --presence-reporter /path/to/Orchestrator/scripts/check_checks_reported.py \
  --output /path/to/evidence/Orchestrator-476-checks.json
```

Use the same command with `--repo stranske/Workflows --pr 3756` and its current
head, or Orchestrator #461, to refresh the issue's named consumers. Changed heads
must not reuse older receipts. The historically observed heads in issue #3757
are evidence pointers, not current-head assertions.

## Receipt and verdict

The JSON `expected-check-receipt/v1` records:

- Full repository, PR, head/base, base branch, caller event/action and changed paths.
- Required status contexts and app restrictions from current branch protection
  and applicable branch rules. Inaccessible protection/rules evidence is UNKNOWN.
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

Literal job names and literal Cartesian matrices are supported. Local reusable
workflows recurse at the same source ref; external reusable calls require a full
SHA. Floating `@main` calls, dynamic inputs/matrices/names, conditional reusable
calls, recursive calls, include/exclude matrix transforms, unsupported glob
syntax, and required-workflow rulesets emit UNKNOWN. This deliberately does not
invent expected child names from whichever children happened to report.

Ordinary conditional jobs still require a reported skipped/successful check.
Event-only workflows are absent only when the authored event/action or supported
filter proves the absence. Paths include renamed source and destination paths;
incomplete or large path inventories cannot establish Actions path filtering.

The tool collects all check runs/suites and every latest-run job page, rather than
an arbitrary latest-N run sample. Counts must agree with API `total_count` where
provided. A changed head/base during collection becomes UNKNOWN. Re-run after
async completion or obtain concrete source-bound evidence for unsupported
conditions; never relabel UNKNOWN as PASS or waive missing checks.

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
