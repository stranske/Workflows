# PR #4175 validation follow-up

Recorded on 2026-10-21. Exact replacements and failing test nodes are in [break-and-revert.json](break-and-revert.json).

The first-ranked target's response test now checks both string and message-object responses, the selected client, preserved input (including braces and Markdown), one invocation, and the `topic_splitter` operation name. No production change or real bug found.

Ran 24 deliberate source mutations, each with a fresh `python -B -m pytest <selected test nodes> -m "not slow" -q --tb=short --junitxml=<report>` process. Every selected case failed (pytest exit 1), and each source was restored in a `finally` block. The union includes all **30 test functions added by this PR**, every added parameterized case, and both variants of the strengthened existing response test (**42 distinct cases**). An AST comparison against base `a17e78df` confirmed that no added test function lacked a failing mutation run.

| Mutation | RED result |
| --- | --- |
| `bootstrap-exception-contracts` | 20 failed |
| `bootstrap-verify-status` | 1 failed |
| `bootstrap-page-preservation` | 1 failed |
| `bootstrap-healthy-status` | 1 failed |
| `tool-latest-output` | 1 failed |
| `tool-offline-fallback` | 1 failed |
| `tool-empty-version` | 1 failed |
| `tool-pypi-version` | 1 failed |
| `metrics-bool-date` | 1 failed |
| `metrics-archive-disabled` | 1 failed |
| `metrics-overflow` | 1 failed |
| `metrics-config-error` | 1 failed |
| `metrics-weekly-count` | 1 failed |
| `metrics-restore-arguments` | 1 failed |
| `metrics-restore-dedupe` | 1 failed |
| `metrics-restore-log` | 1 failed |
| `prune-closed-filter` | 1 failed |
| `prune-missing-directory` | 1 failed |
| `prune-noop-message` | 1 failed |
| `topic-import-fallback` | 2 failed |
| `topic-trace-operation` | 2 failed |
| `topic-string-response` | 1 failed |
| `topic-input-preservation` | 2 failed |
| `topic-selected-client` | 2 failed |

After all reversions, the six targeted test modules passed: **155 passed**. Targeted branch coverage remains **98.83%** (topic splitter and prune 100.00%; bootstrap 99.44%; tool version check 98.08%; retention 97.99%). This is targeted local coverage, not a whole-repository or Gate measurement.

Full-tree Ruff passed with `python -m ruff check --output-format github --extend-exclude .workflows-lib .`. Full-tree Black passed, **820 files unchanged**, with `python -m black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .`. The sandbox blocks process-pool creation and socket wakeups, so Black used one worker, a writable temporary cache, and a temporary event-loop timer; the formatter and its flags were unchanged.

The existing PR head `d47ae4835f2a4c96b07ddafdc1b45caa11df7bd6` passed the Python 3.13 and 3.14 jobs and Gate's summary in [Gate run 39520055465](https://github.com/stranske/Workflows/actions/runs/39520055465). This run does not include the local follow-up test change.

The CI acceptance checkbox remains unchecked until CI passes for the delivered follow-up head and the evidence reaches the PR body. This run could not publish its follow-up: local `.git` is read-only, and the connector rejected both the commit and the PR-body update because they require approval under an approval policy of `never`. PR #4175 remains open and ready for review.
