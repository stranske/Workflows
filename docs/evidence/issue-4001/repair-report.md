# Closer repair evidence — stranske/Workflows#4001

Checked 2026-11-03. PR [#4012](https://github.com/stranske/Workflows/pull/4012)
merged as `c59f58c692b4cee4c60ecd2d8d11ce4afbf5f65a`. Its six tests and
[existing mutation proof](break-revert-proof.json) are preserved. No production changes.

Operational outcome: complete historical hosted Gate accounting prints **226 before,
153 after, 73 fewer uncovered units**. Commands:

```bash
/opt/anaconda3/bin/python3 docs/evidence/issue-4001/extract_target_coverage.py docs/evidence/issue-4001/gate-ci/before/target-coverage.json
/opt/anaconda3/bin/python3 docs/evidence/issue-4001/extract_target_coverage.py docs/evidence/issue-4001/gate-ci/after/target-coverage.json
```

Stop rule: two failed recovery/validation attempts at the same step or 75 minutes,
then report the first broken step and ask whether to stop. No local full-suite run.

## Successful original CI, commits, command and configuration

Original PR head: `f7c27207cd2e7c06f3cc3c45e651957b0b4c8962`.
Actual checkout: synthetic merge `dfbc0129a28929363d6ca9aa4dc4f17e29f52ae4`,
merging that head into `7b5b63e40fb5f47152290177c1e272fbb0d3efa5`.

[Original Gate 39009963668](https://github.com/stranske/Workflows/actions/runs/39009963668),
[job 117330480545](https://github.com/stranske/Workflows/actions/runs/39009963668/job/117330480545):
**50,791 passed, 25 skipped, 3 xfailed**, 1687.11s, Python 3.12.15, pytest 9.1.1.
The Python 3.13.16 job 117330480528 independently reports the same totals and target
rows (680.89s). Both pytest steps and the workflow concluded success.

Recovered control: [Gate 39009966088](https://github.com/stranske/Workflows/actions/runs/39009966088),
[job 117330369906](https://github.com/stranske/Workflows/actions/runs/39009966088/job/117330369906),
tested `f21f6e6111cbaf3201c5fd91239f365ae7600019`:
**50,819 passed, 25 skipped, 3 xfailed**, 1231.37s, same Python/pytest.
This is PR #4014's synthetic merge, **not pristine main**. It shares base
`7b5b63e40fb5f47152290177c1e272fbb0d3efa5` and lacks #4012's six tests.
Its only additions to that base are tests for reusable_ci_scope, verifier_config
and post_ci_summary. All three target sources, pyproject and both Gate workflows
are byte-identical between control and original PR CI:
[source blob identities](gate-ci/source-identities.json).
Its target rows also match the independently retained complete local baseline.
This is a comparable same-base control, without perfect causal isolation of all tests.

Actual Gate invocation recovered from the tested reusable workflow and job log:

```bash
pytest -p ci_test_growth -m 'not quarantine and not slow' \
  --junitxml=pytest-junit.xml --cov --cov-config=pyproject.toml \
  --cov-report=xml:coverage.xml --cov-report=term-missing \
  --cov-report=json:coverage.json -n auto --dist=loadgroup
```

No positional test paths: pyproject selects `tests` and `.github/scripts/__tests__`,
with `-ra --strict-markers --strict-config`. Coverage enables branches/parallel
data, sources scripts/tools/src, and identical omit/exclude rules on both SHAs.
PYTEST_ARGS was empty. The workflow installs a temporary ci_test_growth collection
observer and prepends its directory and the checkout to PYTHONPATH.
See [workflow/config excerpts](gate-ci/workflow-and-config.txt) and
[before](gate-ci/before/job-excerpt.txt) / [after](gate-ci/after/job-excerpt.txt)
original log excerpts. Today's Python 3.14 Gate did not test #4012.

## Complete hosted Gate target comparison

| Target | Before missing_lines | Before missing_branches | After missing_lines | After missing_branches | Reduction |
| --- | ---: | ---: | ---: | ---: | ---: |
| scripts/aggregate_agent_metrics.py | 5 | 17 | 1 | 5 | 16 |
| scripts/check_consumer_sync_drift.py | 73 | 57 | 37 | 42 | 51 |
| scripts/validate_run_contract.py | 47 | 27 | 41 | 27 | 6 |
| **Combined** | **125** | **101** | **79** | **74** | **73** |

Original artifact listing now returns empty; downloading recorded artifact
12093386109 returns HTTP 404. Therefore `gate-ci/*/target-coverage.json` files
are explicitly labeled **target-summary reconstructions from hosted logs**, not
original coverage.json downloads. Stmts, Miss, Branch, BrPart, percent and printed
missing ranges are recovered verbatim. Missing-branch counts are reconstructed
by enumerating integer counts whose blended percentage rounds to the printed two
decimals; each target has exactly one solution. The focused regression test
independently recomputes candidates from raw log rows.
**BrPart is partial branches, not missing branches** (drift after: 32 vs 42).

Both retained complete local coverage.json files were also processed with the
selected /opt/anaconda3/bin/python3; all three targets are present. Their totals
are **226 → 3**, reduction **223**. These historical local reproductions were at
`f8318e2a02676bd18d9577592250879e914b495c` and
`3e513d30e1b11b30bd6a2fdc224adbca97d85930`, reported Python 3.12.2,
coverage.json metadata 7.16.2, using the prior branch's reported Gate-like selection.
The latter includes later tests **and changed drift source and configuration**,
and its reported suite had three failures. Thus **223 is not #4012's Gate reduction**.
The old referenced local pytest logs were not committed and have not been recovered;
their suite-result claims remain historical, not newly verified.
[All four extraction commands and outputs](coverage-extraction.txt) are retained.

## Shortfall and inspected remaining gaps

The reduction is 107 units below 180. Remaining code is not intrinsically untestable;
the original six meaningful boundary tests did not cover every path.
Locations below refer to the original tested source; raw after rows enumerate
all missing ranges and partial edges.

- **Metrics: 6 units remain.** Line 839 increments the needs-human ledger count.
  Edges 492→481, 844→829, 954→910 and 1011→996 concern iteration/loop exhaustion
  in trace refs, ledger records, cycle records and freshness updates. These
  involve input fixtures, not an unavoidable live artifact-download requirement.
  Later coverage reaches every line and leaves only 492→481, 954→910 and
  1011→996. Additional exhaustion-only assertions offer little new behavioral
  discrimination in this evidence repair.
- **Drift: 79 units remain.** Wrong-encoding remote blobs (155–156),
  directory probes with no file (236, 238–242), token rejection fallbacks
  (296–297), empty path prefix (328), sync-PR API/malformed items (391, 396),
  report/input defaults (769, 836, 848), and CLI manifest/tree comparison,
  missing/non-blob entries, undecodable local bytes, skip/create-only, recursive
  directories and obsolete removals (979–1050) require broader
  manifest/session/filesystem fixtures. These can be meaningfully faked; they
  are not inherently inaccessible external-service paths. The later complete
  snapshot already covers this evolved target fully. Duplicate tests now
  cannot improve the historical Gate result.
- **Contract: 68 units remain.** Document-key type/date arcs (189/191), invalid
  date (194), symlink/resolve/escape/file guards (369–381), missing context and
  malformed artifacts (402–441), unreadable evidence (462–463),
  manifest/registry validation (516, 522–523, 548, 563), CLI modes/output/error
  paths (678–800), registry/identity/manifest loops (836→865, 839→849, 857→849),
  and self-smoke fixture reporting (887) remain in the original Gate.
  Later complete coverage has zero missing units for this unchanged production
  target. Rewriting already-covered fixtures adds no new acceptance behavior.

The criterion's explanatory alternative is used. Further historical reduction
cannot be delivered by adding redundant tests to today's fully covered paths.
The new tests check only evidence extraction/reconstruction; no arbitrary target
tests, production refactor, exclusions or threshold changes are introduced.

## Historical target selection

[Recovered issue body](original-issue-body.md), created 2026-10-17, states:

| Order / target | Escaped-defect signals | Churn | Uncovered units |
| --- | ---: | ---: | ---: |
| 1 / aggregate_agent_metrics | 16 | 45 | 22 |
| 2 / check_consumer_sync_drift | 6 | 14 | 130 |
| 3 / validate_run_contract | 4 | 7 | 74 |

Each is marked as touched by a fix commit. Priority: escaped defects, then churn,
then uncovered mass. These are **recovered historical issue claims**, not today's
ranking. The generator's raw ranking, signal classification and churn window were
not recovered and are not independently certified. The total 226 matches control.
The [complete original PR body](original-pr-body.md) preserves its focused-suite
figures, mutation narrative and CI links. Focused percentages are not Gate counts.

## Prior branch reconciliation and focused validation

Merged all five commits unique to local `closer/issue-4001` before editing, onto
provisioned `closer-r3/issue-4001` from current main. Kept the six-probe RED/GREEN
proof and probe script unchanged, both complete local JSONs and their summaries.
Corrected the 223-unit attribution, wrong baseline-parent description, CI runtime
and command claims, and ranking attribution. Discarded only the unrelated
test-file evidence pointer and local full-suite runner (it omitted actual CI
observer/reports and is outside the authorized local validation scope).
The final diff preserves all six merged tests.

The extractor now rejects absent/ambiguous targets and missing/invalid required
counts before printing any total. Negative control against the inherited extractor:
**15 failed, 1 passed**; restored fix: **16 passed**, under one second.
After moving the focused test into Gate's normal collection, the final run also
checks unique historical reconstruction. See
[negative/restored validation](extractor-validation.txt) and
[final focused checks](focused-validation.txt). The existing six-test mutation
proof was reused. No local full suite or release/verify pipeline was run.

Follow-up observations only: original ZIP unavailable; pristine-base Gate coverage
not recovered; ranking generator inputs unverified; later cumulative local suite
had three reported failures. None is hidden by partial totals or represented as
proof that #4012 reached 180.
