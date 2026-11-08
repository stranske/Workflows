WF#4082 verification — 2026-11-07 03:24:22 UTC, checkout `34cd295c`.

Reviewed the recent six commits before editing. They already implement scanner
read-failure reporting and the bounded cancellation collector. The stale PR task
list does not reflect that work. The prepared reconciled body is
[pr-body-round-12.md](pr-body-round-12.md); tasks 1, 2 and 4 are verified locally
and through connected GitHub reads, with the runner gh limitation below.
Publication was rejected; these checkboxes have not been written to GitHub.

The requested issue-format guide resides at
`templates/consumer-repo/docs/AGENT_ISSUE_FORMAT.md`. Root and template Gate
types remain `[opened, synchronize, reopened, ready_for_review]`.
The compiled manifest retains create-only policy, the Template overwrite and
Manager-Database skip. No workflow, manifest or protected file was edited.

Current connected metadata and complete changed-file patches reconcile every
existing campaign PR. Each patch has one addition and one deletion in the sole
`.github/workflows/pr-00-gate.yml` file, removing only `labeled`. No duplicate
PR was created. Dispositions and full heads:

| Campaign PR | Current disposition / mergedAt | Head |
| --- | --- | --- |
| [Counter_Risk#1178](https://github.com/stranske/Counter_Risk/pull/1178) | 2026-10-18T07:55:16Z | `ef4eab34fd00991721e105da3fa709f9c2eaf5be` |
| [Deliverable-Render#101](https://github.com/stranske/Deliverable-Render/pull/101) | 2026-10-18T07:55:21Z | `9b0f192802ba6f0cd9bdac152fd03377b472d2a1` |
| [Doc-Lineage#138](https://github.com/stranske/Doc-Lineage/pull/138) | 2026-10-18T07:55:24Z | `e270e1b586fcb82db93e28891bf29a57f558b4a8` |
| [Fine-Art-Archive#832](https://github.com/stranske/Fine-Art-Archive/pull/832) | 2026-10-18T07:55:29Z | `594688593acb8f31a36f68695c9864d55c02b63e` |
| [Inv-Man-Intake#1037](https://github.com/stranske/Inv-Man-Intake/pull/1037) | 2026-10-18T07:55:34Z | `ffeaf3afb2928c0ffe3e03c1e16b2aa2bc39cbd9` |
| [Manager-Mosaic#116](https://github.com/stranske/Manager-Mosaic/pull/116) | 2026-10-18T07:55:39Z | `338e00b835e007fee9a68de8c7ce0fcf2d66ddb6` |
| [Orchestrator#732](https://github.com/stranske/Orchestrator/pull/732) | 2026-10-18T07:55:43Z | `57efe3a51cce3d6412ca9a69464b5614113370dd` |
| [Pension-Data#979](https://github.com/stranske/Pension-Data/pull/979) | 2026-10-18T07:55:48Z | `85562e99d80956514cfdc2e836478a9f24726e98` |
| [Portable-Alpha-Extension-Model#2390](https://github.com/stranske/Portable-Alpha-Extension-Model/pull/2390) | Open, ready; unmerged | `09298cf6b2e719b90ad661ea62553f4504d5dd96` |
| [Ready#633](https://github.com/stranske/Ready/pull/633) | 2026-10-18T14:51:47Z | `5e341751ff4b79186f5c32e288711a060ae04e18` |
| [Travel-Plan-Permission#1682](https://github.com/stranske/Travel-Plan-Permission/pull/1682) | 2026-10-18T07:55:57Z | `0532bbda4779cef5902005bb45b8607401fb5f16` |
| [Trend_Model_Project#6112](https://github.com/stranske/Trend_Model_Project/pull/6112) | 2026-10-18T07:56:04Z | `d9bb77745d0d7edd5da4b23d37e0f330d7859576` |
| [learning-management-system#775](https://github.com/stranske/learning-management-system/pull/775) | 2026-10-18T07:56:09Z | `677a6ca74735cbefce61f9fbd7447c1ee65f9f6b` |
| [trip-planner#1921](https://github.com/stranske/trip-planner/pull/1921) | 2026-10-18T07:56:14Z | `a784569e22ebd401af22a6739e25bdb85e3e621e` |

Workflows#4084 remains merged at head
`9be36f8556928608485acdd7d1cec6fef1bc69a6`. Its implementation, patch and
Health 68 command were inspected. The registered-repo helper returns 16
consumers. `~/.codex/bin/handoff.sh` is absent, so its additional supported-repo
roster cannot be checked.

Before test changes, recorded the real-input command, check date and stop rule
in `/tmp/issue-4082-round12/outcome.json`: one attempt capped at 110 seconds,
without retrying unavailable networking. Health 68 selects Python 3.14; the
runner interpreter is Python 3.14.10.

```bash
repos_input=$(python3 scripts/list_registered_consumer_repos.py --separator=,)
timeout 110s python3 scripts/check_consumer_sync_drift.py --repos "$repos_input" --summary /tmp/issue-4082-round12/summary.md --report-json /tmp/issue-4082-round12/drift.json
```

At 2026-11-07T03:23:00.971576Z this command exited 1 in 0.268 seconds.
It reported no usable read credential and `unknown (Gate/tree unavailable)`
for every registered consumer: Travel-Plan-Permission, Template, Counter_Risk,
Pension-Data, Inv-Man-Intake, Ready, trip-planner, Manager-Database,
Portable-Alpha-Extension-Model, Trend_Model_Project, learning-management-system,
Fine-Art-Archive, Orchestrator, Doc-Lineage, Deliverable-Render and Manager-Mosaic.
It did not print `gate triggers: all match`.

Also attempted the following for all 14 campaign PRs and Workflows#4084:

```bash
gh pr view PR -R REPOSITORY --json state,isDraft,headRefOid,mergedAt
gh pr diff PR -R REPOSITORY
```

For each of the 16 registered consumers, attempted:

```bash
gh api repos/REPOSITORY/contents/.github/workflows/pr-00-gate.yml --jq .path
```

All 46 commands failed with `error connecting to api.github.com`.
Each command had one attempt and a ten-second timeout, with at most eight
concurrent reads. The full commands and outputs are in
`/tmp/issue-4082-round12/cli-reads.json`. Connected reads supplement campaign
reconciliation and do not establish authenticated Health 68 readback.

No runtime repair was justified by this unavailable-read outcome. Extended the
existing scanner integration test to cover consumers that replace
`synchronize` with `labeled`, preserving list length while introducing both
an extra and a missing trigger. Both cases (Template aligned or drifting) check
the real registry, compiled manifest and template. They require both differences
in stdout, JSON and summary, prohibit all-match in every output, and preserve
create-only/custom-Gate policy and the Template overwrite behavior.

Validation:

```bash
python3 -m pytest tests/scripts/test_check_consumer_sync_drift.py tests/scripts/test_measure_gate_cancellations.py tests/workflows/test_gate_trigger_contract.py tests/workflows/test_consumer_sync_create_only_evidence.py -q -m 'not slow'
```

Baseline: 190 passed in 11.25 seconds. After the test change: 192 passed in
10.92 seconds. Focused Black formatting, Ruff and `git diff --check` pass.
The mandatory repository-wide command was run with a single worker to avoid
the sandbox's previously observed multiprocessing socket restriction:

```bash
BLACK_NUM_WORKERS=1 black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

It produced no result after several minutes and was interrupted at
2026-11-07T03:28:27Z (exit 130). This is an incomplete formatting check, not a
pass. No commit or push was attempted because the mandatory gate did not pass.
The environment also grants read-only access to `.git`. The source/test patch
is available at `/tmp/issue-4082-round12/source-tests.patch` and remains in the
checkout for the authorized parent. PR#4503 was verified open and non-draft at
head `34cd295c24dfa87d9a1a73cda5d72000858e3c47` before handoff.

The campaign remains incomplete while PAEM#2390 is open. Final campaign
mergedAt, exact ensuing 48-hour completion time, numerator, denominator and
percentage remain unknown. No observation collection was run using a guessed
timestamp. An authorized parent must reconcile the remaining PR disposition,
complete the roster check and authenticated live readback, then collect the
complete observation window. Source/test readiness does not establish campaign
acceptance.

Automatic approval review rejected the PR body update, `needs-human` label
and WF#4082 evidence comment: `MCP tool call requires approval, but approval
policy is never`. No remote update is claimed. The prepared body and this note
are available for the authorized parent.
