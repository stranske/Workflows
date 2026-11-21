# Monthly audit ranking regression, 2026-11-19

Published baseline: [Workflows #4770](https://github.com/stranske/Workflows/issues/4770),
generated 2026-11-19T15:37:58Z. The issue reports 141642 total runs, 96282 successes,
7071 literal failures, hence 38289 other conclusions. It lists Auto-Label Issues
(0 failures/8050 runs) and Auto-Fix Integration Test Failures (0/4866) under
immediate attention. The issue does not establish the full other-conclusion mix.

## Reproducible red/green fixture

`test_published_november_totals_synthetic_red_green` uses those exact aggregate
counts and workflow volumes with **synthetic** conclusion allocations. This is
not a full replay of November raw data, and synthetic workflow identities and
outcome distributions are not claims about the live workflows. The separate
small fixture also checks genuine failed outcomes and exact path-based detection.

The frozen old production rule (success/all <50%, sorted by volume) identifies
both zero-failure workflows. The new production stats JQ and actual attention
shell exclude both from immediate/review ranking. Published true-positive Duplicate Detection (149/149 failures) ranks first;
Maint 46 Post CI (1380/1883 failures, remaining 503 synthetically assigned success)
also correctly receives attention. The remaining failures are allocated to a
synthetic workflow (5542/6542 decisive). Auto-Label's 201 synthetic successes
reproduce its published rounded 2% overall success. Other exact success and
neutral/skipped/cancelled/unknown allocations are synthetic, not recovered data.
All non-ranked conclusions remain visible in the mix.
Explicit tests also exercise timed_out, startup_failure, action_required, stale,
unknown/future conclusions, zero input, all-skipped, minimum samples and exact
20%/50% boundaries. No collector, issue writer, network or Closer is executed
by the regression fixtures. Checklist rendering executes locally with temp paths.

Reproduce offline:

```sh
python3 -m pytest tests/workflows/test_maint66_monthly_audit_stats.py \
  tests/workflows/test_maint66_monthly_audit_issue_body.py -q --no-cov \
  -o asyncio_default_fixture_loop_scope=function
```

## Bounded genuine spot check, not complete collection

Read-only GitHub queries selected workflow IDs 221540317 (`agents-auto-label.yml`)
and 221022961 (`maint-71-auto-fix-integration.yml`) for the exact created window
2026-10-20T00:00:00Z through 2026-11-19T15:37:58Z, one page of 100 each. Both pages
contained 100 skipped runs, all run_attempt=1. They are latest run records, not
inventories of historical attempts. This corroborates that skipped runs are a
real source of low success/all, but does not prove either complete monthly mix.

Each response reported total_count=2500, not the published 8050/4866. No claim
of full collection or matching aggregate coverage is made: the capped/default
ordering and changed live inventory are not reconciled by these two pages.
No extra pages, broad 141642-run retrieval, workflow dispatch, issue edit or
production audit were performed. The production collector's existing window
subdivision/completeness checks are unchanged by this fix.

Validation: 62 tests passed across the two Maint 66 modules, workflow naming and
untrusted-interpolation checks. `actionlint` on Maint 66, Ruff on changed tests,
and `git diff --check` passed. Local Python 3.12 required the explicit asyncio
fixture-scope override above because of its installed pytest plugin; hosted CI
remains a separate exact-head verification. No application model/API spend.


Independent-review regressions additionally execute the production attention path
on 1,000 synthetic workflows with long Unicode names and 5,000 failures. The issue
sections stay below 32,000 bytes in aggregate, omitted-line counts match, and all
1,000 ranked failures remain in the full artifact files. A render-path test sends
an oversized API report and proves the final 60,000-byte guard exits before writing
issue output. Status-aware null classification, aggregate numerator/denominator,
and artifact-before-publication ordering are separately asserted. Tests remap all
artifact/intermediate paths into per-test temporary directories; no upload or live
issue write is performed by these fixtures.
