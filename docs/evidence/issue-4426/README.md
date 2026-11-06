# Issue #4426 evidence: recovered #3998 contract

Checked 2026-11-06. This record preserves the original contract from
[issue #3998](https://github.com/stranske/Workflows/issues/3998) before later coverage measurements or test
changes. The complete body is `issue-3998.body.md` (SHA-256
`33b9720780242f03406f5a77c0062cb97ff161598bfe2fc337d2034dd1bf0e08`). Structured fields are `contract-3998.json`.

Retrieval command:

```bash
gh issue view 3998 --repo stranske/Workflows --json title,body,state,number,closedAt,createdAt,url
```

Retrieved issue state: CLOSED. Title: Raise test coverage toward 90% (autopilot round 2, lane D, low blast radius only). Created
2026-10-17T01:44:12Z. Closed 2026-11-03T15:22:19Z.

## Format document

The task cites `docs/AGENT_ISSUE_FORMAT.md`. In this checkout that path is the
consumer target. The docs sync section defaults to the template source tree, and
the manifest entry does not override `source_tree`, so the file that was read is
`templates/consumer-repo/docs/AGENT_ISSUE_FORMAT.md` (SHA-256 `77aa6980fa432c5f5f69a2d7999bcd76e2f9e6e79f987902ddfc212f26df107c`).
`docs/AGENT_ISSUE_FORMAT.md` is absent at the repository root.

Binding quotes from that file:

- `### 1. Tasks must name a real, verified file / function / path`
- `### 2. Acceptance Criteria must include at least one named, observable test gate`
- `#### The deliberate-break pattern (recommended worked form)`
- `### 4. Non-Goals must forbid scaffold-only / partial-completion-claimed-as-done`

Those rules require named artifacts, an observable acceptance gate, a
deliberate-break then named-failure then revert loop, and a non-goal that
forbids scaffold-only completion. They govern how this evidence is recorded.
They do not replace the #3998 coverage contract.

## Baseline definition

Opening snapshot, verbatim:

> Workflows reads 82.29% blended line+branch in CI; reaching 90% needs about 4488 more covered statements+branches.

That snapshot is 82.29% blended line and branch coverage, with about 4488
covered statements plus branches still required to reach 90%. It is the issue's
opening measurement, not a replacement for later Gate artifacts.

Judgment rule, verbatim:

> "Uncovered units" here come from the repository's whole CI run (every test file together). One test module's own suite can already cover more than CI's count shows for that module, and CI's figure is the one this PR is judged on: if your baseline differs, say so in the PR body and use CI's number.

Uncovered units are statements plus branches from the repository's whole CI run,
every test file together. A single test module can cover more than CI shows for
that module. When a local baseline differs, the PR must say so and use CI's
number.

## Ranking method

Order statement, verbatim:

> The target order below is the Orchestrator's own ranking (escaped defects, then churn, then uncovered mass -- unchanged).

Selection rule, verbatim:

```text
Pick the next target by the repo's own coverage-gap ranking (escaped-defect priority, then
   churn, then uncovered mass), not by file size.
```

Sort keys are escaped-defect signals, then churn, then uncovered statement and
branch mass. File size is not the ranking method. The producer is the
Orchestrator coverage-autopilot ranking embedded in issue #3998.
`coverage-autopilot.py` is not in this repository, so the issue text is the
preserved ranking input. The listed bundle is about 398 uncovered statements
and branches.

| Rank | Target | Escaped-defect signals | Churn | Uncovered statements+branches |
| --- | --- | ---: | ---: | ---: |
| 1 | `scripts/sync_test_dependencies.py` | 15 | 16 | 6 |
| 2 | `scripts/langchain/issue_pr_context.py` | 7 | 9 | 30 |
| 3 | `scripts/langchain/verifier_config.py` | 6 | 8 | 16 |
| 4 | `tools/langchain_client.py` | 6 | 7 | 29 |
| 5 | `scripts/langchain/task_validator.py` | 5 | 8 | 36 |
| 6 | `scripts/langchain/pr_verifier.py` | 4 | 8 | 281 |

## Coverage exception

Goal, verbatim: The goal is to improve the code, not a metric.

Exception, verbatim:

```text
If you measure this repo at or above 90% before
starting, say so in a comment on this issue and close it without opening a PR -- do not
manufacture a fix just because a round was requested.
```

If repository coverage is already at least 90% before the round starts, the
original contract says to comment on issue #3998 and close it without opening a
PR. Do not manufacture tests only to meet a numerical target after that
exception applies.

## Exclusion requirements

Non-goals, verbatim:

> No refactors, no exclusions or threshold changes, no files outside the targets, no padding: if a listed target cannot be meaningfully tested (dead code, an external service you cannot fake), say so in the PR body and take the next one.

A skip is allowed only when the target cannot be meaningfully tested. The issue
names two such reasons: dead code, and an external service that cannot be
faked. Say that reason in the PR body and take the next target. Inability to
obtain a terminal local receipt does not satisfy this exclusion.

Reserved files, verbatim:

> Other lanes own other files; do not touch these (in flight or reserved): `scripts/aggregate_agent_metrics.py`, `scripts/check_consumer_sync_drift.py`, `scripts/langchain/followup_issue_generator.py`, `scripts/runner_lib/core.py`.

Do not touch:

- `scripts/aggregate_agent_metrics.py`
- `scripts/check_consumer_sync_drift.py`
- `scripts/langchain/followup_issue_generator.py`
- `scripts/runner_lib/core.py`

Production-change rule, verbatim: Touch only tests, plus a minimal production fix when a test finds a real bug.

Blast radius, verbatim: Low blast radius only -- test-only or tightly-scoped fixes, no refactors.

Chunking, verbatim: One PR per logical chunk of work.

The contract also forbids refactors, coverage exclusions, threshold changes,
files outside the listed targets, and padding.

## Numerical rule

The original numerical rule is about 180 uncovered statements and branches.
This record does not replace that rule with another threshold.

Scope, verbatim:

> Cover as many of these as you can cover FULLY in this one PR, in order, with discriminating tests; stop when about 180 units are covered or the list is exhausted.

Acceptance, verbatim:

> The PR's Gate coverage shows the targets' uncovered statements+branches down by about 180 or more, or the PR body explains each target that could not be meaningfully covered.

Deliberate-break rule, verbatim:

```text
Every new test must FAIL when the code it covers is deliberately broken and PASS when
   reverted -- run that break-and-revert for real and report it, don't assert it.
```

Negative-cache warning, verbatim:

> Watch for the negative-cache pattern (cache.get(key) is None used as a 'not yet cached' check, which can't tell 'never queried' from 'queried and got nothing')

## Repository measurements

Pre-round and current whole-suite figures are in `coverage-measurement.md` and
`coverage-measurement.json`. Checked 2026-11-06. Recovered pre-round Gate
displays are 81.83% and 81.84%, and the issue snapshot is 82.29%. All three are
below 90%, so the close-without-a-PR exception does not apply. Current blended
coverage is 91.08%. The about-180 rule remains the numerical rule.
