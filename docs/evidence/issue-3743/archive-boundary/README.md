# Archived-base filesystem proof

This test-only #3743 chunk protects executable proof scripts, omitted external
symlinks, and rejection of parent/absolute tar paths. The latter cases assert
both an unchanged external file and structured `FAIL_BROKEN` rather than valid
acceptance. Root and consumer helpers are exercised independently.

The current 400-commit scripts history ranks this helper first: 72 whole-word
fix/bug/repair/regression/correct subject hits versus the next module's 29.
This is a disclosed repair-history proxy, not an escaped-incident count. Fresh
focused coverage confirms 48 uncovered statements before this chunk. The unique
first ranking tier settles selection before lower-tier uncovered mass; see
`ranking.json` for all history rows.

## Validation

Baseline: 244 passed; candidate: 252 passed. Identical module scope/configuration
and interpreter: `/opt/anaconda3/bin/python3` (3.12.2, macOS). Statement coverage
541/589 (91.850594%) -> 544/589 (92.359932%); branch coverage 235/262 -> 237/262;
combined 91.186839% -> 91.774383%. Newly covered statements:917,922,1056; no lost
coverage. This does not measure whole-repository coverage or complete the broader
90% initiative. A broader scripts-suite attempt was interrupted after 9,973 tests
passed in145s; it is incomplete and supplies no broad PASS claim.

```sh
/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_check_deliberate_break.py -q -o addopts= --cov=scripts.check_deliberate_break --cov-branch --cov-report=json:<outside-repo>/focused-before.json --cov-report=term-missing
/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_check_deliberate_break.py tests/scripts/test_check_deliberate_break_archive.py -q -o addopts= --cov=scripts.check_deliberate_break --cov-branch --cov-report=json:<outside-repo>/focused-after.json --cov-report=term-missing
```

Complete captures and measured JSON are retained beside this document, with
committed-byte hashes in `manifest.json`. Run any replay to a new outside-repo
evidence directory; retained captures are immutable evidence, not replay outputs.
Initial test development assumed git tar modes equal local0755. Git archives
apply their own tar mode policy, so the regression asserts the actual contract:
owner execute permission and successful execution of the extracted proof. No
production behavior was changed to satisfy that test.

## Actual sensitivity experiments

| Guard deliberately broken in both helpers | Observed RED | Exact restored GREEN |
| --- | --- | --- |
| Remove execute mode by chmod0600 | 2 failed | 2 passed |
| Admit external symlink as a regular archive file | 2 failed | 2 passed |
| Remove path containment rejection | 4 failed | 4 passed |

Every new root/template parameter case is accounted for. `mutation-manifest.json`
records exact source replacements, argv, exit codes, and original hashes. All
production bytes were restored after every mutation, including failures. The
root and template hashes match and production has no diff. The hostile archive
fixtures use real tar bytes and the real extractor/verdict path; only git archive
transport and proof-command responses are substituted. Real git commits/archives
are used for executable and symlink cases. No external live service is exercised.

Focused Ruff/Black, repository Black, template sync/completeness, and whitespace
checks are recorded in the PR and automation packet. Source-owned workflows,
coverage floors, thresholds, and exclusions remain unchanged.
