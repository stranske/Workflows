## Current acceptance correction — 2026-10-12

The retained 04:24 packet below is historical skip-diagnostic evidence. It does not
prove issue #3839's visible-failure acceptance. Current workflows promote the
classifier's unverified-unassociated skip into the existing attributed failure
catch, retaining an empty PR lock. The current tests require repository, run,
attempt, conclusion and head, followed by `setFailed`, for six root/consumer
failed/cancelled/timed-out cases. Valid no-report-needed skips are unchanged.

`acceptance-20261012/receipt.json`, raw logs and JUnit prove the actual production
guard removed: six assertion failures, no errors/skips; byte-identical restoration:
six passes. This is local authored-workflow proof, not a hosted consumer cycle or
provider PASS. The historical manifest remains the binding for its original bytes;
the new receipt binds current workflow bytes separately.

# Issue 3839 reporter diagnostics

Observed reporter run [38171655290](https://github.com/stranske/Workflows/actions/runs/38171655290)
failed with `Unassociated run has no verified dispatch classification` before
reporting. The failed-job log is retained unchanged. A contemporaneous upstream
sample [38171612527](https://github.com/stranske/Workflows/actions/runs/38171612527)
is cancelled, has an empty PR association, and was itself triggered by
`workflow_run`. The classifier permits unassociated title recovery only for
verified `workflow_dispatch` producers. This sample explains a real rejected
class; the reporter log does not identify its exact upstream run, so the pair is
not claimed as a proven trigger linkage. Missing associations are not permission
to infer PR ownership.

The root and consumer resolver publish attributed diagnostics for two classes:

- **Unassociated non-dispatch / non-producer runs** (`#3839` + `#3843`): classify
  as skip with `outcome=no-report-needed`, emit notice+job summary naming the
  upstream run/conclusion/reason, leave the PR lock empty, and do **not** fail
  the resolver (avoids the prior red-run noise).
- **Authority-relevant resolution failures**: publish an attributed job summary
  **before** `setFailed`. Both clear the PR lock and distinguish `unresolved` /
  `invalid-input` from resolved or no-report-needed. No classifier, authority
  replay, writer permission, or PR mutation gate was weakened. A summary-writing
  failure preserves both its own error annotation and the original classification
  failure.

## Validation

- `python3 -m pytest tests/workflows/test_keepalive_reporter_unresolved.py tests/workflows/test_keepalive_authority_delivery.py tests/workflows/test_workflow_agents_consolidation.py -q`: **103 passed**; raw log and JUnit retained.
- `node --test .github/scripts/__tests__/keepalive-reporter-applicability.test.js`: **29 passed**; raw log retained.
- `python3 scripts/validate_template_sync.py`: all template files in sync.
- `python3 scripts/validate_template_completeness.py`: consumer workflows templated and manifested.
- `actionlint -shellcheck= -pyflakes= .github/workflows/agents-keepalive-loop-reporter.yml templates/consumer-repo/.github/workflows/agents-keepalive-loop-reporter.yml`: exit 0. External shellcheck/pyflakes disabled; YAML/Actions checks remain active.

## Production mutation proof

`mutation-receipt.json` names the actual test command, exact source hashes,
mutation hashes, six selected-node outcomes and exits. Replacing both production
resolver skip diagnostics with a silent skip branch produced **6 assertion
failures** on
`test_unassociated_workflow_run_reports_attributed_failure_before_failing`, no
errors or skips, exit 1. Byte-identical restoration produced **6 clean passes**,
exit 0. The tests parse the authored YAML and execute its JavaScript against the
real classifier with read-only mocked GitHub data; they require the attributed
notice+summary events for unassociated skips.

This is local behavior and mutation evidence. It does not establish a deployed
consumer cycle, successful live PR reconciliation, hosted CI completion, or
provider acceptance. Current-head CI/review and post-merge comparison remain
required before source issue closure.

## First hosted-check recovery

Health74 run38174980893 found the reporter pair's normalized drift fingerprints
stale after the identical resolver edit. The exact local checker exited1 before
metadata repair and0 after. Only `pair.12` fingerprints and its refresh note/date
changed; the original divergence review date remains2026-09-28. Root subscriptions
and consumer fingerprint/setup differences remain intentional. Thirty existing
drift/allowlist control tests pass. Hosted failure and both full local outputs
are retained; the changed workflow bytes and the six-case production mutation
proof above are unchanged.


## Current replay transport (2026-10-12)

The acceptance-20261012 replay uses a fresh tempfile-owned JUnit path for the
pytest subprocess, then copies the XML to the caller's external output directory.
The caller's output path never enters the child argv. No scanner suppression or
shell quoting is used. The previous explicit-list argv did not invoke a shell;
this change removes the taint boundary that the scanner flagged.

For a portable replay, install the repository dev environment and its replay
parser dependency, then run from the checkout root:

```bash
python3 -m pip install -e '.[dev]' defusedxml==0.7.1
python3 docs/evidence/issue-3839-reporter/acceptance-20261012/replay.py --output /tmp/reporter-replay-NEW
```

The output directory must be fresh and outside the checkout. The current source
contract promotes unverified targetless classifier skips to an attributed failure;
the earlier skip description and original proof above describe historical behavior.
Current raw six-assertion RED, byte-identical restoration and six GREEN are bound
separately in acceptance-20261012/replay-transport-20261012. Hosted scan/checks,
review dispositions and post-merge comparison remain required.
