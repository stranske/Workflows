# Extractor and evidence replay continuation

This continuation adds gzip report input and `--xml` validation to
`docs/evidence/issue-4001/extract_target_coverage.py`. The original JSON-only CLI
remains supported. XML counters are read independently; missing branch exits
are counted from covered/total conditions, rather than partial-branch counts.
Malformed reports and counter disagreements return exit 2 without publishing
an accepted total. XML parsing uses the repository's existing `defusedxml`
dependency. No workflow or target production module was changed.

The 46 new extractor checks exercise plain/compressed input, rejection paths,
the original JSON-only interface, all four retained report pairs, and both
compressed/uncompressed report digests. They pass in the bounded command:

```bash
python -m pytest tests/scripts/test_issue_4001_target_coverage.py -m 'not slow' -q
```

The 268 existing target cases also pass. Their targeted coverage command in
[round2-preflight.md](round2-preflight.md) confirms:

| Target | Statements | Missing statements | Branches | Missing branches | Coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| aggregate_agent_metrics.py | 899 | 0 | 380 | 0 | 100.00% |
| check_consumer_sync_drift.py | 654 | 0 | 298 | 0 | 100.00% |
| validate_run_contract.py | 448 | 0 | 212 | 0 | 100.00% |

The original bounded measurement remains 21 → 0 missing units; the original
full Gate comparison remains 2 → 0. The historical 226-unit baseline is distinct
from this branch's before measurement. Replaying zero missing units does not
attribute another 226-unit reduction to the continuation.

## Full Gate replay

The configured coverage invocation completed with exit 1: **83 failed, 15,794
passed, 25 skipped, 3 xfailed in 404.11s**. All 46 extractor cases passed in this
run. Comparing complete JUnit inventories against the previous final run finds
the exact same 83 failure nodes, with zero new or resolved nodes. CI acceptance
therefore remains open. No unrelated failure was repaired or suppressed.

Complete reports and logs are retained in [replay-after/](replay-after/):
`coverage.json.gz`, `coverage.xml.gz`, `pytest-junit.xml.gz`, `pytest.log.gz`,
`inventory.json`, and `failure-comparison.json`. Unlike the original baseline
recovery, these JSON/XML reports were written directly by pytest-cov.
The bounded and formatting logs are retained alongside them.

After extracting the embedded observer exactly as in README.md, the replay was:

```bash
PYTHONPATH=/tmp/issue-4502-round2/plugin:$PWD \
pytest -p ci_test_growth -m 'not quarantine and not slow' \
  --junitxml=/tmp/issue-4502-round2/gate/pytest-junit.xml \
  --cov --cov-config=pyproject.toml \
  --cov-report=xml:/tmp/issue-4502-round2/gate/coverage.xml \
  --cov-report=term-missing \
  --cov-report=json:/tmp/issue-4502-round2/gate/coverage.json \
  -n auto --dist load \
  --ignore=tests/scripts/test_pr_verifier_delivery_destinations.py \
  --ignore=tests/scripts/test_pr_verifier_prompt_coverage.py \
  --ignore=tests/scripts/test_pr_verifier_body_overall_integration.py \
  -n 4 --dist=loadgroup
python docs/evidence/issue-4001/extract_target_coverage.py \
  docs/evidence/issue-4502/replay-after/coverage.json.gz \
  --xml docs/evidence/issue-4502/replay-after/coverage.xml.gz
```

Both report counters independently reproduce zero missing units for all three
targets; there are no remaining target locations requiring limitation evidence.
Selection, embedded observer, marker, worker/distribution options and coverage
configuration match Gate. Only output destinations are redirected. This local
invocation is not a successful hosted CI receipt.

All nine original deliberate-break probes were rerun after Gate exited. Every
one of the 18 target cases failed under its documented break and passed after
exact byte restoration. Complete fresh transcripts are retained under
`replay-after/mutations/` as `.md.gz` files. The extractor's valid-report command
also failed under temporary branch-count (four cases) and gzip-decoding (three
cases, with the uncompressed case unchanged) regressions, then passed all four
cases after each exact restoration. See
[extractor-red-green.md](replay-after/extractor-red-green.md).

`replay-after/artifact-manifest.json` records report digests, source digests,
runtime versions and results. All six target source/test files were checked
against Git after the probes; every byte matches the checked-out head.

## Formatting

Black formatted both Python files. Its required repository-wide check passed:
**1,009 files would be left unchanged, exit 0**. As in the previous round,
Black's multiprocessing dispatcher stalled in this sandbox; the same temporary
sequential adapter documented in README.md calls Black's own `reformat_one`
with its original mode and AST safety check for every discovered file. The
command was:

```bash
PYTHONPATH=/tmp/issue-4502-round2/black-serial \
BLACK_CACHE_DIR=/tmp/issue-4502-round2/black-cache \
GITHUB_OUTPUT=/tmp/issue-4502-round2/black-output \
black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

Ruff also passed for both Python files. No formatting exclusion, coverage
exclusion, test skip, or production correction was added.

## Provenance and blockers

Checked-out source head: `16be78c0eb19908fe7a383d8c457164286945e6e`, with the
extractor and its new tests in the working tree. The three target modules and
their three target test files match that head byte for byte. Original before
head: `b25657e57ec09b90f6bac8fa5d892f822b3bc34c`. Original preflight main:
`e621d8f0ed8b83b9648b7fa8577b4f236bd57f1d`. Live main was independently checked
through GitHub's branch API during this round:
`8084366d968d5c4f68208536ca8bb3956ce99091`.

The first task remains blocked by absent `docs/AGENT_ISSUE_FORMAT.md`; the
available issue-format guide and template were inspected instead, as recorded
before test edits. The local commit attempt failed with:

```text
fatal: Unable to create '/home/runner/work/Workflows/Workflows/.git/index.lock': Read-only file system
```

The explicit `needs-human` label request was rejected by the GitHub connector:
`MCP tool call requires approval, but approval policy is never`. This also
prevents publishing the prepared PR-body update through that connector.
No final commit SHA or successful publication is claimed. PR #4658 was initially
open and ready for review (`draft=false`), but merged externally at
2026-11-11 21:15:54 UTC with head
`16be78c0eb19908fe7a383d8c457164286945e6e`. The local continuation is not part
of that merged payload. No task or acceptance checkbox was updated on the PR
by this run. A complete proposed body, including the fresh full transcripts,
is retained as `replay-after/pr-body.md.gz` (uncompressed staging copy:
`/tmp/issue-4502-round2/pr-body.md`). It is an unpublished handoff artifact.
